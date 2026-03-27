"""
ARTE Chatbot Backend
FastAPI server with /health and /chat endpoints.
"""

import json
import logging
import uuid
from typing import Any, Optional

from backend.app.logging_config import setup_logging

# Configure logging before anything else (reads LOG_LEVEL from centralized settings)
setup_logging()

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from rag import (
    DEFAULT_ESCALATION_MESSAGE,
    EscalationDetector,
    default_detector,
)
from backend.app.llm_client import (
    LLMClient,
    LLMServiceError,
    ARTE_SYSTEM_PROMPT,
)
from backend.app.auth import verify_api_key
from backend.app.s3_client import S3Client, S3DownloadError
from backend.app.file_inputs import FileInputsClient, FileUploadError
from backend.app.tools import get_tool_definitions

logger = logging.getLogger(__name__)

app = FastAPI(title="ARTE Chatbot Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize clients
llm_client = LLMClient()
s3_client = S3Client()
file_inputs_client = FileInputsClient()

# Session storage (in-memory for Sprint 1)
# TODO: Replace with PostgreSQL in future sprints
_sessions: dict[str, list[dict[str, Any]]] = {}


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


def _process_tool_call(
    tool_call: dict[str, Any],
    user_message: str,
    session_id: str,
) -> str:
    """Process a tool call for reading a technical datasheet.

    Args:
        tool_call: The tool call dict from OpenAI response.
        user_message: The original user message.
        session_id: The session identifier.

    Returns:
        The LLM response based on the datasheet content.

    Raises:
        S3DownloadError: If the PDF cannot be downloaded from S3.
        FileUploadError: If the PDF cannot be uploaded to OpenAI.
        LLMServiceError: If the LLM call fails.
    """
    function_name = tool_call.get("function", {}).get("name")
    if function_name != "leer_ficha_tecnica":
        raise ValueError(f"Unknown tool: {function_name}")

    # Parse tool arguments
    arguments = json.loads(tool_call.get("function", {}).get("arguments", "{}"))
    ruta_s3 = arguments.get("ruta_s3")
    categoria = arguments.get("categoria")
    fabricante = arguments.get("fabricante")
    modelo = arguments.get("modelo")

    logger.debug(
        "Tool call parameters: function=%s, ruta_s3=%s, categoria=%s, "
        "fabricante=%s, modelo=%s, session_id=%s",
        function_name,
        ruta_s3,
        categoria,
        fabricante,
        modelo,
        session_id,
    )

    if not ruta_s3:
        raise ValueError("Missing ruta_s3 in tool arguments")

    # Download PDF from S3
    pdf_bytes = s3_client.download_pdf(ruta_s3)

    # Generate filename from ruta_s3
    filename = ruta_s3.split("/")[-1] if "/" in ruta_s3 else ruta_s3

    # Upload PDF to OpenAI
    file_id = file_inputs_client.upload_pdf(pdf_bytes, filename)

    # Second LLM call with file
    try:
        response = llm_client.get_llm_response_with_file(
            message=user_message,
            file_id=file_id,
            session_id=session_id,
        )
        return response
    finally:
        # Clean up: delete the uploaded file
        try:
            file_inputs_client.delete_file(file_id)
        except Exception as e:
            logger.warning(
                "Failed to delete file: file_id=%s, session_id=%s, error=%s",
                file_id,
                session_id,
                e,
            )


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest, api_key: str = Depends(verify_api_key)):
    """
    Chat endpoint that handles user messages.

    Implements two-call LLM pattern:
    1. First call checks if tools need to be invoked
    2. If tool call present, process it and make second call
    """
    session_id = request.session_id or str(uuid.uuid4())
    request_id = str(uuid.uuid4())

    logger.debug(
        "Incoming request: request_id=%s, session_id=%s, message_preview=%s",
        request_id,
        session_id,
        request.message[:100],
    )

    # Initialize session if needed
    if session_id not in _sessions:
        _sessions[session_id] = []

    # Detect escalation
    escalation_result = default_detector.detect(request.message)

    if escalation_result.escalate:
        logger.info(
            "Escalation detected: request_id=%s, session_id=%s, reason=%s",
            request_id,
            session_id,
            escalation_result.reason,
        )
        return ChatResponse(
            response=DEFAULT_ESCALATION_MESSAGE,
            escalate=True,
            reason=escalation_result.reason,
            session_id=session_id,
        )

    try:
        # First LLM call with tools
        logger.debug(
            "Calling LLM with tools: request_id=%s, session_id=%s, model=%s",
            request_id,
            session_id,
            llm_client.model,
        )
        llm_response = llm_client.get_llm_response_with_tools(
            message=request.message,
            session_id=session_id,
            system_prompt=ARTE_SYSTEM_PROMPT,
        )

        # Check if the response contains tool calls
        choices = llm_response.get("choices", [])
        if not choices:
            raise LLMServiceError("Invalid LLM response: no choices")

        message = choices[0].get("message", {})
        tool_calls = message.get("tool_calls")

        if not tool_calls:
            # No tool call needed - return normal response
            content = message.get("content", "")
            return ChatResponse(
                response=content,
                escalate=False,
                session_id=session_id,
            )

        # Process tool calls
        for tool_call in tool_calls:
            function_name = tool_call.get("function", {}).get("name")

            if function_name == "leer_ficha_tecnica":
                try:
                    final_response = _process_tool_call(
                        tool_call=tool_call,
                        user_message=request.message,
                        session_id=session_id,
                    )
                    return ChatResponse(
                        response=final_response,
                        escalate=False,
                        session_id=session_id,
                    )
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
                except Exception as e:
                    logger.exception(
                        "Error processing tool call: request_id=%s, session_id=%s, error=%s",
                        request_id,
                        session_id,
                        e,
                    )
                    return ChatResponse(
                        response=(
                            "Ocurrió un error al procesar tu solicitud. "
                            "Por favor, intenta más tarde."
                        ),
                        escalate=False,
                        session_id=session_id,
                    )

        # If we get here with tool_calls but none were processed
        return ChatResponse(
            response=message.get("content", ""),
            escalate=False,
            session_id=session_id,
        )

    except LLMServiceError as e:
        logger.error(
            "LLM service error: request_id=%s, session_id=%s, error=%s",
            request_id,
            session_id,
            e,
        )
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception(
            "Unexpected error in chat endpoint: request_id=%s, session_id=%s",
            request_id,
            session_id,
        )
        raise HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
