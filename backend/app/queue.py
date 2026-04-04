"""
Message queue system for async request processing.

Provides MessageQueue class that manages a pool of async workers
consuming from an asyncio.Queue, processing chat requests in parallel.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.app.config import settings
from backend.app.file_inputs import FileInputsClient, FileUploadError
from backend.app.llm_client import (
    ARTE_SYSTEM_PROMPT,
    LLMClient,
    LLMServiceError,
)
from backend.app.s3_client import S3Client, S3DownloadError
from backend.app.session import SessionManager
from rag import DEFAULT_ESCALATION_MESSAGE

logger = logging.getLogger(__name__)


@dataclass
class ChatMessage:
    """Message enqueued for processing by a worker."""

    request_id: str
    session_id: str
    message: str
    future: asyncio.Future = field(default_factory=asyncio.Future)


class MessageQueue:
    """Queue of messages with pool of async workers."""

    def __init__(
        self,
        max_workers: int,
        max_queue_size: int,
        llm_client: LLMClient,
        s3_client: S3Client,
        file_inputs_client: FileInputsClient,
        session_manager: SessionManager,
    ):
        """Initialize MessageQueue with injected dependencies.

        Args:
            max_workers: Number of concurrent worker tasks
            max_queue_size: Maximum queue size before backpressure
            llm_client: LLM client for OpenAI calls
            s3_client: S3 client for downloading PDFs
            file_inputs_client: File inputs client for OpenAI file handling
            session_manager: Session manager for storing conversation history
        """
        self.max_workers = max_workers
        self.max_queue_size = max_queue_size
        self.llm_client = llm_client
        self.s3_client = s3_client
        self.file_inputs_client = file_inputs_client
        self.session_manager = session_manager

        self.queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self.workers: list[asyncio.Task] = []
        self._running = False

    async def start(self) -> None:
        """Start worker tasks.

        Creates max_workers coroutines that consume from the queue
        until stop() is called.
        """
        if self._running:
            logger.warning("MessageQueue already running")
            return

        self._running = True
        logger.info("Starting MessageQueue with %d workers", self.max_workers)

        for worker_id in range(self.max_workers):
            task = asyncio.create_task(self._worker(worker_id))
            self.workers.append(task)

    async def stop(self) -> None:
        """Stop all workers gracefully.

        Cancels all worker tasks and waits for them to finish.
        """
        if not self._running:
            logger.warning("MessageQueue not running")
            return

        self._running = False
        logger.info("Stopping MessageQueue")

        # Cancel all worker tasks
        for task in self.workers:
            task.cancel()

        # Wait for all workers to finish
        try:
            await asyncio.gather(*self.workers, return_exceptions=True)
        except asyncio.CancelledError:
            pass

        self.workers.clear()
        logger.info("MessageQueue stopped")

    async def enqueue(self, message: ChatMessage) -> None:
        """Enqueue a message for processing.

        Blocks if queue is full (backpressure).

        Args:
            message: ChatMessage to enqueue
        """
        if not self._running:
            raise RuntimeError("MessageQueue is not running")

        logger.debug(
            "Enqueueing message: request_id=%s, session_id=%s",
            message.request_id,
            message.session_id,
        )
        await self.queue.put(message)

    async def _worker(self, worker_id: int) -> None:
        """Main worker loop.

        1. Get message from queue
        2. Process message (escalation, LLM calls, tool calls)
        3. Resolve future with result or exception
        4. Mark task as done
        """
        logger.info("Worker %d started", worker_id)

        try:
            while self._running:
                try:
                    # Get message from queue (blocks until available)
                    message = await asyncio.wait_for(
                        self.queue.get(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    # Timeout is normal when queue is empty
                    continue

                request_id = message.request_id
                session_id = message.session_id
                user_message = message.message

                logger.debug(
                    "Worker %d processing: request_id=%s, session_id=%s",
                    worker_id,
                    request_id,
                    session_id,
                )

                try:
                    # Get session context for improved prompt
                    context_string = self.session_manager.get_context_string(
                        session_id
                    )

                    # First LLM call with tools
                    logger.debug(
                        "Worker %d calling LLM with tools: request_id=%s",
                        worker_id,
                        request_id,
                    )
                    llm_response = (
                        await self.llm_client.get_llm_response_with_tools(
                            message=user_message,
                            session_id=session_id,
                            system_prompt=ARTE_SYSTEM_PROMPT,
                            context=context_string,
                        )
                    )

                    # Check if response contains tool calls
                    tool_calls = llm_response.get("tool_calls")

                    if not tool_calls:
                        # No tool call needed - return normal response
                        content = llm_response.get("output_text", "")
                        await self.session_manager.add_turn(
                            session_id=session_id,
                            question=user_message,
                            answer=content,
                            source_documents=[],
                        )
                        message.future.set_result(
                            {"response": content, "escalate": False}
                        )
                    else:
                        # Process tool calls
                        final_response = await self._process_tool_calls(
                            tool_calls=tool_calls,
                            user_message=user_message,
                            session_id=session_id,
                            worker_id=worker_id,
                            request_id=request_id,
                        )
                        await self.session_manager.add_turn(
                            session_id=session_id,
                            question=user_message,
                            answer=final_response,
                            source_documents=[],
                        )
                        message.future.set_result(
                            {"response": final_response, "escalate": False}
                        )

                except Exception as e:
                    logger.exception(
                        "Worker %d error processing message: request_id=%s, session_id=%s",
                        worker_id,
                        request_id,
                        session_id,
                    )
                    # Set exception on future instead of result
                    if not message.future.done():
                        message.future.set_exception(e)
                finally:
                    self.queue.task_done()

        except asyncio.CancelledError:
            logger.info("Worker %d cancelled", worker_id)
        except Exception as e:
            logger.exception("Worker %d unexpected error", worker_id, exc_info=e)

    async def _process_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
        user_message: str,
        session_id: str,
        worker_id: int,
        request_id: str,
    ) -> str:
        """Process tool calls asynchronously.

        Currently handles 'leer_ficha_tecnica' tool call.

        Args:
            tool_calls: List of tool calls from LLM response
            user_message: Original user message
            session_id: Session identifier
            worker_id: ID of processing worker (for logging)
            request_id: Request identifier (for logging)

        Returns:
            Final LLM response after processing tool calls

        Raises:
            S3DownloadError: If PDF cannot be downloaded
            FileUploadError: If PDF cannot be uploaded
            LLMServiceError: If LLM call fails
        """
        for tool_call in tool_calls:
            function_name = tool_call.get("function", {}).get("name")

            if function_name != "leer_ficha_tecnica":
                logger.warning(
                    "Worker %d unknown tool: %s", worker_id, function_name
                )
                continue

            # Parse tool arguments
            arguments = json.loads(
                tool_call.get("function", {}).get("arguments", "{}")
            )
            ruta_s3 = arguments.get("ruta_s3")
            categoria = arguments.get("categoria")
            fabricante = arguments.get("fabricante")
            modelo = arguments.get("modelo")

            logger.debug(
                "Worker %d tool call parameters: function=%s, ruta_s3=%s, "
                "categoria=%s, fabricante=%s, modelo=%s, request_id=%s",
                worker_id,
                function_name,
                ruta_s3,
                categoria,
                fabricante,
                modelo,
                request_id,
            )

            if not ruta_s3:
                raise ValueError("Missing ruta_s3 in tool arguments")

            # Download PDF from S3
            pdf_bytes = await self.s3_client.download_pdf(ruta_s3)

            # Generate filename from ruta_s3
            filename = ruta_s3.split("/")[-1] if "/" in ruta_s3 else ruta_s3

            # Upload PDF to OpenAI
            file_id = await self.file_inputs_client.upload_pdf(
                pdf_bytes, filename
            )

            # Second LLM call with file
            try:
                response = await self.llm_client.get_llm_response_with_file(
                    message=user_message,
                    file_id=file_id,
                    session_id=session_id,
                )
                return response
            finally:
                # Clean up: delete the uploaded file
                try:
                    await self.file_inputs_client.delete_file(file_id)
                except Exception as e:
                    logger.warning(
                        "Worker %d failed to delete file: file_id=%s, session_id=%s, error=%s",
                        worker_id,
                        file_id,
                        session_id,
                        e,
                    )

        # If we get here with tool_calls but none were processed
        return "No tools were processed"
