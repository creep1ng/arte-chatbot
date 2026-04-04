"""
ARTE Chatbot Backend
FastAPI server with /health and /chat endpoints.
"""

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from rag import (
    DEFAULT_ESCALATION_MESSAGE,
    default_detector,
)
from backend.app.llm_client import (
    LLMClient,
    LLMServiceError,
)
from backend.app.logging_config import setup_logging
from backend.app.auth import verify_api_key
from backend.app.s3_client import S3Client, S3DownloadError
from backend.app.file_inputs import FileInputsClient, FileUploadError
from backend.app.session import session_manager
from backend.app.queue import MessageQueue, ChatMessage
from backend.app.config import settings

# Configure logging (reads LOG_LEVEL from centralized settings)
setup_logging()

logger = logging.getLogger(__name__)

# Initialize clients
llm_client = LLMClient()
s3_client = S3Client()
file_inputs_client = FileInputsClient()


class ChatRequest(BaseModel):
    """Request model for /chat endpoint."""

    message: str = Field(..., min_length=1)
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Response model for /chat endpoint."""

    response: str
    escalate: bool = False
    reason: Optional[str] = None
    session_id: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for app startup and shutdown.
    
    Startup: Initialize and start MessageQueue workers
    Shutdown: Stop workers and clean up
    """
    # Startup
    queue_manager = MessageQueue(
        max_workers=settings.queue_workers,
        max_queue_size=settings.max_queue_size,
        llm_client=llm_client,
        s3_client=s3_client,
        file_inputs_client=file_inputs_client,
        session_manager=session_manager,
    )
    await queue_manager.start()
    app.state.queue_manager = queue_manager
    logger.info("Message queue started with %d workers", settings.queue_workers)
    
    yield
    
    # Shutdown
    await queue_manager.stop()
    logger.info("Message queue stopped")


app = FastAPI(title="ARTE Chatbot Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check() -> JSONResponse:
    """Health check endpoint for CI/CD pipeline."""
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "service": "arte-chatbot-backend",
            "version": "1.0.0",
        },
    )


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {"message": "ARTE Chatbot Backend API", "docs": "/docs"}


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, api_key: str = Depends(verify_api_key)):
    """
    Chat endpoint that handles user messages asynchronously.

    Enqueues the message for processing by a worker and waits for the result
    with a 60-second timeout.
    """
    session_id = request.session_id or str(uuid.uuid4())
    request_id = str(uuid.uuid4())

    logger.debug(
        "Incoming request: request_id=%s, session_id=%s, message_preview=%s",
        request_id,
        session_id,
        request.message[:100],
    )

    # Detect escalation (synchronous, fast check)
    escalation_result = default_detector.detect(request.message)

    if escalation_result.escalate:
        logger.info(
            "Escalation detected: request_id=%s, session_id=%s, reason=%s",
            request_id,
            session_id,
            escalation_result.reason,
        )
        # Save escalation in session history
        await session_manager.add_turn(
            session_id=session_id,
            question=request.message,
            answer=DEFAULT_ESCALATION_MESSAGE,
            source_documents=[],
        )
        return ChatResponse(
            response=DEFAULT_ESCALATION_MESSAGE,
            escalate=True,
            reason=escalation_result.reason,
            session_id=session_id,
        )

    try:
        # Create chat message with asyncio.Future
        chat_msg = ChatMessage(
            request_id=request_id,
            session_id=session_id,
            message=request.message,
            future=asyncio.Future(),
        )

        # Enqueue message for processing
        queue_manager = app.state.queue_manager
        await queue_manager.enqueue(chat_msg)

        logger.debug(
            "Message enqueued: request_id=%s, session_id=%s",
            request_id,
            session_id,
        )

        # Wait for worker to process with 60-second timeout
        try:
            result = await asyncio.wait_for(chat_msg.future, timeout=60.0)
            logger.debug(
                "Message processed: request_id=%s, session_id=%s",
                request_id,
                session_id,
            )
            return ChatResponse(
                response=result["response"],
                escalate=result["escalate"],
                session_id=session_id,
            )
        except asyncio.TimeoutError:
            logger.error(
                "Message processing timeout: request_id=%s, session_id=%s",
                request_id,
                session_id,
            )
            raise HTTPException(
                status_code=504,
                detail="Request processing timeout. Please try again.",
            )

    except LLMServiceError as e:
        logger.error(
            "LLM service error: request_id=%s, session_id=%s, error=%s",
            request_id,
            session_id,
            e,
        )
        raise HTTPException(status_code=503, detail=str(e))
    except S3DownloadError as e:
        logger.error(
            "S3 download error: request_id=%s, session_id=%s, error=%s",
            request_id,
            session_id,
            e,
        )
        return ChatResponse(
            response=(
                "Lo siento, no pude acceder a la ficha técnica del "
                "producto solicitado. El archivo no está disponible "
                "en nuestro catálogo. Por favor, contacta al equipo "
                "de ventas para más información."
            ),
            escalate=False,
            session_id=session_id,
        )
    except FileUploadError as e:
        logger.error(
            "File upload error: request_id=%s, session_id=%s, error=%s",
            request_id,
            session_id,
            e,
        )
        return ChatResponse(
            response=(
                "Lo siento, tuve problemas al procesar la ficha técnica. "
                "Por favor, intenta novamente o contacta al equipo de ventas."
            ),
            escalate=False,
            session_id=session_id,
        )
    except Exception:
        logger.exception(
            "Unexpected error in chat endpoint: request_id=%s, session_id=%s",
            request_id,
            session_id,
        )
        raise HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
