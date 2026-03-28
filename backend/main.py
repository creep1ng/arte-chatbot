"""
ARTE Chatbot Backend
FastAPI server with /health and /chat endpoints.
"""

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

import json
import os
import uuid
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv(override=False)

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
from backend.app.schemas import SourceDocument
from backend.app.auth import verify_api_key
from backend.app.catalog import CatalogSearch
from backend.app.s3_client import S3Client, S3DownloadError
from backend.app.file_inputs import FileInputsClient, FileUploadError
from backend.app.tools import DATASHEET_CATEGORIES, get_tool_definitions

logger = logging.getLogger(__name__)

app = FastAPI(title="ARTE Chatbot Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Diagnostic logging for environment configuration
def _log_environment_configuration() -> None:
    required_env_vars = [
        "CHAT_API_KEY",
        "OPENAI_API_KEY",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_BUCKET_NAME",
    ]
    for env_var in required_env_vars:
        status = "set" if os.getenv(env_var) else "missing"
        logger.info("Environment check: %s is %s", env_var, status)


_log_environment_configuration()


def _log_tool_definitions() -> None:
    tools = get_tool_definitions()
    for tool in tools:
        function_block = tool.get("function", {})
        name = function_block.get("name")
        tool_type = tool.get("type")
        has_parameters = isinstance(function_block.get("parameters"), dict)
        logger.info(
            "Tool configuration: name=%s, type=%s, has_parameters=%s",
            name,
            tool_type,
            has_parameters,
        )


_log_tool_definitions()

# Initialize clients
llm_client = LLMClient()
s3_client = S3Client()
file_inputs_client = FileInputsClient()
catalog_search = CatalogSearch()

MAX_AGENTIC_ITERATIONS = int(os.getenv("MAX_AGENTIC_ITERATIONS", "5"))

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
    source_documents: list[SourceDocument] = Field(default_factory=list)


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

    logger.info(
        f"Processing tool call: {function_name} - "
        f"ruta_s3={ruta_s3}, categoria={categoria}, "
        f"fabricante={fabricante}, modelo={modelo}"
    )

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


def _parse_tool_arguments(tool_call: dict[str, Any]) -> dict[str, Any]:
    function = tool_call.get("function", {})
    arguments_raw = function.get("arguments", "{}")
    if isinstance(arguments_raw, dict):
        return arguments_raw
    try:
        return json.loads(arguments_raw or "{}")
    except json.JSONDecodeError as exc:
        logger.warning("Invalid JSON arguments for tool %s: %s", function.get("name"), exc)
        return {}


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _handle_buscar_producto_tool(tool_call: dict[str, Any]) -> tuple[str, bool]:
    arguments = _parse_tool_arguments(tool_call)
    categoria = arguments.get("categoria")
    if not isinstance(categoria, str):
        return ("No se pudo determinar la categoría para buscar productos.", False)
    categoria = categoria.strip()
    if categoria not in DATASHEET_CATEGORIES:
        categorias_validas = ", ".join(DATASHEET_CATEGORIES)
        return (
            f"La categoría proporcionada no es válida. Usa una de: {categorias_validas}.",
            False,
        )

    fabricante = arguments.get("fabricante")
    if isinstance(fabricante, str):
        fabricante = fabricante.strip() or None
    else:
        fabricante = None

    tipo = arguments.get("tipo")
    if isinstance(tipo, str):
        tipo = tipo.strip() or None
    else:
        tipo = None

    capacidad_min = _safe_float(arguments.get("capacidad_min"))
    capacidad_max = _safe_float(arguments.get("capacidad_max"))

    productos = catalog_search.search(
        categoria=categoria,
        fabricante=fabricante,
        capacidad_min=capacidad_min,
        capacidad_max=capacidad_max,
        tipo=tipo,
    )

    if not productos:
        return (
            "No encontré productos que coincidan con los filtros proporcionados. ",
            False,
        )

    return (json.dumps({"productos": productos}), False)


def _handle_leer_ficha_tecnica_tool(
    tool_call: dict[str, Any],
    *,
    user_message: str,
    session_id: str,
) -> tuple[str, bool, bool]:
    arguments = _parse_tool_arguments(tool_call)
    ruta_s3 = arguments.get("ruta_s3")

    if not ruta_s3:
        return (
            "No cuento con la ruta_s3 del producto. Ejecuta buscar_producto para obtenerla antes de volver a solicitar la ficha técnica.",
            False,
            False,
        )

    try:
        final_response = _process_tool_call(
            tool_call=tool_call,
            user_message=user_message,
            session_id=session_id,
        )
        return (final_response, True, True)
    except S3DownloadError as exc:
        logger.error("S3 download error: %s", exc)
        return (
            "Lo siento, no pude acceder a la ficha técnica del producto solicitado. El archivo no está disponible en nuestro catálogo. Por favor, contacta al equipo de ventas para más información.",
            True,
            False,
        )
    except FileUploadError as exc:
        logger.error("File upload error: %s", exc)
        return (
            "Lo siento, tuve problemas al procesar la ficha técnica. Por favor, intenta novamente o contacta al equipo de ventas.",
            True,
            False,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Error processing leer_ficha_tecnica tool: %s", exc)
        return (
            "Ocurrió un error al procesar tu solicitud. Por favor, intenta más tarde.",
            True,
            False,
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

    # Initialize session if needed
    if session_id not in _sessions:
        _sessions[session_id] = []

    # Detect escalation
    escalation_result = default_detector.detect(request.message)

    if escalation_result.escalate:
        return ChatResponse(
            response=DEFAULT_ESCALATION_MESSAGE,
            escalate=True,
            reason=escalation_result.reason,
            session_id=session_id,
            source_documents=[],
        )

    system_message = {"role": "system", "content": ARTE_SYSTEM_PROMPT}
    conversation_history: list[dict[str, Any]] = [
        system_message,
        {"role": "user", "content": request.message},
    ]
    source_docs: list[SourceDocument] = []

    try:
        last_output_text = ""
        for iteration in range(1, MAX_AGENTIC_ITERATIONS + 1):
            logger.info("Agentic iteration %s started", iteration)
            llm_response = llm_client.get_llm_response_with_tools(
                messages=conversation_history,
                session_id=session_id,
                system_prompt=ARTE_SYSTEM_PROMPT,
            )
            last_output_text = llm_response.get("output_text", "")
            tool_calls = llm_response.get("tool_calls", [])

            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": last_output_text,
            }
            if tool_calls:
                assistant_message["tool_calls"] = tool_calls
            conversation_history.append(assistant_message)

            if not tool_calls:
                return ChatResponse(
                    response=last_output_text,
                    escalate=False,
                    session_id=session_id,
                    source_documents=source_docs,
                )

            for tool_call in tool_calls:
                function = tool_call.get("function", {})
                function_name = function.get("name")
                tool_call_id = tool_call.get("id")
                arguments = _parse_tool_arguments(tool_call)
                logger.info(
                    "Agentic iteration %s invoking tool %s",
                    iteration,
                    function_name,
                )

                if function_name == "buscar_producto":
                    handler_output, is_terminal = _handle_buscar_producto_tool(
                        tool_call
                    )
                elif function_name == "leer_ficha_tecnica":
                    (
                        handler_output,
                        is_terminal,
                        include_source_doc,
                    ) = _handle_leer_ficha_tecnica_tool(
                        tool_call,
                        user_message=request.message,
                        session_id=session_id,
                    )
                    if include_source_doc:
                        ruta_s3 = arguments.get("ruta_s3")
                        if ruta_s3:
                            source_docs.append(SourceDocument(ruta=ruta_s3))
                else:
                    handler_output, is_terminal = (
                        f"Herramienta desconocida: {function_name}",
                        False,
                    )

                if is_terminal:
                    return ChatResponse(
                        response=handler_output,
                        escalate=False,
                        session_id=session_id,
                        source_documents=source_docs,
                    )

                if handler_output:
                    conversation_history.append(
                        {
                            "role": "tool",
                            "content": handler_output,
                            "tool_call_id": tool_call_id,
                        }
                    )

        logger.warning(
            "Agentic loop exhausted %s iterations without terminal response",
            MAX_AGENTIC_ITERATIONS,
        )
        return ChatResponse(
            response=last_output_text,
            escalate=False,
            session_id=session_id,
            source_documents=source_docs,
        )

    except LLMServiceError as exc:
        logger.error("LLM service error: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error in chat endpoint: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
