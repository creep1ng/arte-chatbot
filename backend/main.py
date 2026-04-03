"""
ARTE Chatbot Backend
FastAPI server with /health and /chat endpoints.
"""

import json
import logging
import uuid
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.config.settings import Settings
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
from backend.app.catalog import CatalogSearch
from backend.app.session_manager import SessionManager

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
settings = Settings()
llm_client = LLMClient(model=settings.llm_model)
s3_client = S3Client()
file_inputs_client = FileInputsClient()
catalog_search = CatalogSearch(s3_client=s3_client)
session_manager = SessionManager()

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
    arguments = _parse_tool_arguments(
        tool_call.get("function", {}).get("arguments")
    )
    ruta_s3 = arguments.get("ruta_s3")
    categoria = arguments.get("categoria")
    fabricante = arguments.get("fabricante")
    modelo = arguments.get("modelo")

    logger.info(
        f"Processing tool call: {function_name} - "
        f"ruta_s3={ruta_s3}, categoria={categoria}, "
        f"fabricante={fabricante}, modelo={modelo}"
    )

    if not ruta_s3:
        return "Error: se necesita ruta_s3 para leer la ficha técnica. Usa buscar_producto primero."

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
            logger.warning(f"Failed to delete file {file_id}: {e}")


def _parse_tool_arguments(raw_arguments: Any) -> dict[str, Any]:
    """Parse tool arguments coming from the LLM payload."""

    if isinstance(raw_arguments, dict):
        return raw_arguments

    if raw_arguments is None:
        return {}

    if isinstance(raw_arguments, str):
        try:
            return json.loads(raw_arguments)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON in tool arguments: %s", raw_arguments)
            return {}

    logger.warning("Unexpected tool arguments type: %s", type(raw_arguments))
    return {}


def _safe_float(raw_value: Any) -> float | None:
    """Convert raw tool argument into float when possible."""

    if raw_value is None:
        return None
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return None


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest, api_key: str = Depends(verify_api_key)):
    """Chat endpoint implementing iterative agentic tool loop."""
    session_id = request.session_id or str(uuid.uuid4())

    # Initialize session if needed
    if session_id not in _sessions:
        _sessions[session_id] = []

    # Detect escalation
    escalation_result = default_detector.detect(request.message)

    if escalation_result.escalate:
        session_manager.add_turn(session_id, "user", request.message)
        return ChatResponse(
            response=DEFAULT_ESCALATION_MESSAGE,
            escalate=True,
            reason=escalation_result.reason,
            session_id=session_id,
        )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": ARTE_SYSTEM_PROMPT},
        {"role": "user", "content": request.message},
    ]

    # Track user message in session
    session_manager.add_turn(session_id, "user", request.message)

    iteration = 0
    last_completion_text = ""

    try:
        while iteration < settings.max_agentic_iterations:
            llm_response = llm_client.get_llm_response_with_tools(
                messages=messages,
                session_id=session_id,
            )

            last_completion_text = llm_response.get("output_text", "")
            tool_calls = llm_response.get("tool_calls") or []

            if not tool_calls:
                session_manager.add_turn(session_id, "assistant", last_completion_text)
                return ChatResponse(
                    response=last_completion_text,
                    escalate=False,
                    session_id=session_id,
                )

            # Track assistant turn including tool calls for the LLM.
            messages.append(
                {
                    "role": "assistant",
                    "content": last_completion_text,
                    "tool_calls": tool_calls,
                }
            )

            for tool_call in tool_calls:
                function_payload = tool_call.get("function", {})
                function_name = function_payload.get("name")

                if function_name == "buscar_producto":
                    arguments = _parse_tool_arguments(
                        function_payload.get("arguments")
                    )

                    categoria = arguments.get("categoria")
                    if not categoria:
                        tool_result = (
                            "Error: se requiere la categoría para buscar productos."
                        )
                    else:
                        resultados = catalog_search.search(
                            categoria=categoria,
                            fabricante=arguments.get("fabricante"),
                            capacidad_min=_safe_float(arguments.get("capacidad_min")),
                            capacidad_max=_safe_float(arguments.get("capacidad_max")),
                            tipo=arguments.get("tipo"),
                        )
                        if resultados:
                            tool_result = json.dumps(resultados, ensure_ascii=False)
                        else:
                            tool_result = (
                                "No se encontraron productos que cumplan los criterios."
                            )

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.get("id"),
                            "content": tool_result,
                        }
                    )

                elif function_name == "leer_ficha_tecnica":
                    try:
                        final_response = _process_tool_call(
                            tool_call=tool_call,
                            user_message=request.message,
                            session_id=session_id,
                        )
                        session_manager.add_turn(session_id, "assistant", final_response)
                        return ChatResponse(
                            response=final_response,
                            escalate=False,
                            session_id=session_id,
                        )
                    except S3DownloadError:
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
                    except FileUploadError:
                        return ChatResponse(
                            response=(
                                "Lo siento, tuve problemas al procesar la ficha técnica. "
                                "Por favor, intenta nuevamente o contacta al equipo de ventas."
                            ),
                            escalate=False,
                            session_id=session_id,
                        )
                    except Exception:
                        logger.exception("Error inesperado procesando leer_ficha_tecnica")
                        return ChatResponse(
                            response=(
                                "Ocurrió un error al procesar tu solicitud. "
                                "Por favor, intenta más tarde."
                            ),
                            escalate=False,
                            session_id=session_id,
                        )
                else:
                    logger.warning("Unhandled tool call: %s", function_name)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.get("id"),
                            "content": "Error: herramienta no soportada.",
                        }
                    )

            iteration += 1

        # Max iterations reached – return the last completion text as fallback.
        session_manager.add_turn(session_id, "assistant", last_completion_text)
        return ChatResponse(
            response=last_completion_text,
            escalate=False,
            session_id=session_id,
        )

    except LLMServiceError as e:
        logger.error("LLM service error: %s", e)
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error in chat endpoint: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
