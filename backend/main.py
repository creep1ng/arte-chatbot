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

# Load environment variables from .env file
from dotenv import load_dotenv

load_dotenv()

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
from backend.app.schemas import SourceDocument
from backend.app.auth import verify_api_key
from backend.app.s3_client import S3Client, S3DownloadError
from backend.app.file_inputs import FileInputsClient, FileUploadError
from backend.app.tools import DATASHEET_CATEGORIES, get_tool_definitions
from backend.app.session import session_manager
from backend.app.catalog import CatalogError, get_catalog

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

MAX_AGENTIC_ITERATIONS = int(os.getenv("MAX_AGENTIC_ITERATIONS", "5"))


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
    num_sources: int = 0


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


def _parse_tool_arguments(tool_call: dict[str, Any]) -> dict[str, Any]:
    """Parse and validate tool arguments from a tool call.

    Args:
        tool_call: The tool call dict from LLM response.

    Returns:
        Dictionary of parsed arguments.

    Raises:
        ValueError: If arguments cannot be parsed.
    """
    try:
        arguments_str = tool_call.get("function", {}).get("arguments", "{}")
        return json.loads(arguments_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid tool arguments JSON: {e}") from e


def _safe_float(value: Any) -> Optional[float]:
    """Safely convert a value to float.

    Args:
        value: The value to convert.

    Returns:
        The float value or None if conversion fails.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _process_buscar_producto(
    arguments: dict[str, Any],
    session_id: str,
) -> str:
    """Process a buscar_producto tool call.

    Args:
        arguments: The tool arguments containing search criteria.
        session_id: The session identifier.

    Returns:
        A formatted string with search results.
    """
    categoria = arguments.get("categoria")
    fabricante = arguments.get("fabricante")
    capacidad_min = _safe_float(arguments.get("capacidad_min"))
    capacidad_max = _safe_float(arguments.get("capacidad_max"))
    tipo = arguments.get("tipo")
    modelo_contiene = arguments.get("modelo_contiene")

    logger.debug(
        "buscar_producto call: categoria=%s, fabricante=%s, capacidad_min=%s, "
        "capacidad_max=%s, tipo=%s, modelo_contiene=%s, session_id=%s",
        categoria,
        fabricante,
        capacidad_min,
        capacidad_max,
        tipo,
        modelo_contiene,
        session_id,
    )

    if not categoria:
        return "Error: Se requiere especificar una categoría (paneles, inversores, controladores, baterias)."

    try:
        catalog = get_catalog()
        results = catalog.search(
            categoria=categoria,
            fabricante=fabricante,
            capacidad_min=capacidad_min,
            capacidad_max=capacidad_max,
            tipo=tipo,
            modelo_contiene=modelo_contiene,
        )

        if not results:
            return (
                "No se encontraron productos que coincidan con los criterios "
                "de búsqueda especificados. Prueba con otros filtros o contacta "
                "al equipo de ventas de Arte Soluciones Energéticas."
            )

        # Format results for the LLM
        lines = [
            f"Se encontraron {len(results)} producto(s) en la categoría '{categoria}':\n"
        ]

        for product in results:
            lines.append(f"\n## {product.nombre_comercial} ({product.fabricante})")
            if product.descripcion:
                lines.append(f"Descripción: {product.descripcion}")
            lines.append(f"Modelos disponibles:")
            for variante in product.variantes:
                modelo = variante.get("modelo", "Sin nombre")
                params = variante.get("parametros_clave", {})
                params_str = ", ".join(f"{k}: {v}" for k, v in params.items())
                lines.append(f"  - {modelo} ({params_str})")
            lines.append(
                f"  → Para ver más detalles, usa leer_ficha_tecnica con ruta_s3: {product.ruta_s3}"
            )

        return "\n".join(lines)

    except CatalogError as e:
        logger.error(
            "Catalog error in buscar_producto: session_id=%s, error=%s",
            session_id,
            e,
        )
        return (
            "Lo siento, no pude consultar el catálogo de productos. "
            "Por favor, intenta más tarde o contacta al equipo de ventas."
        )


def _process_leer_ficha_tecnica(
    tool_call: dict[str, Any],
    user_message: str,
    session_id: str,
) -> tuple[str, list[str]]:
    """Process a tool call for reading a technical datasheet.

    Args:
        tool_call: The tool call dict from OpenAI response.
        user_message: The original user message.
        session_id: The session identifier.

    Returns:
        Tuple of (llm_response_text, list_of_s3_paths_used).

    Raises:
        S3DownloadError: If the PDF cannot be downloaded from S3.
        FileUploadError: If the PDF cannot be uploaded to OpenAI.
        LLMServiceError: If the LLM call fails.
        ValueError: If ruta_s3 is missing and no products found in catalog.
    """
    function_name = tool_call.get("function", {}).get("name")
    if function_name != "leer_ficha_tecnica":
        raise ValueError(f"Unknown tool: {function_name}")

    # Parse tool arguments
    arguments = _parse_tool_arguments(tool_call)
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

    # If ruta_s3 is not provided, try to find it via catalog search
    if not ruta_s3:
        logger.info(
            "No ruta_s3 provided, searching catalog: categoria=%s, "
            "fabricante=%s, modelo=%s, session_id=%s",
            categoria,
            fabricante,
            modelo,
            session_id,
        )

        if not categoria:
            raise ValueError(
                "Missing ruta_s3 in tool arguments. When ruta_s3 is not "
                "provided, categoria is required to search the catalog."
            )

        try:
            catalog = get_catalog()
            # Search by categoria and optionally fabricante/modelo
            modelo_contiene = modelo if modelo else None
            results = catalog.search(
                categoria=categoria,
                fabricante=fabricante,
                modelo_contiene=modelo_contiene,
            )

            if not results:
                raise ValueError(
                    f"No products found in catalog for categoria='{categoria}'"
                    + (f", fabricante='{fabricante}'" if fabricante else "")
                    + (f", modelo containing '{modelo}'" if modelo else "")
                )

            if len(results) == 1:
                # Single product found, use its ruta_s3
                ruta_s3 = results[0].ruta_s3
                logger.info(
                    "Found single product, using ruta_s3=%s, session_id=%s",
                    ruta_s3,
                    session_id,
                )
            else:
                # Multiple products found - select first one deterministically
                ruta_s3 = results[0].ruta_s3
                logger.warning(
                    "Multiple products found when resolving ruta_s3, selecting first: "
                    "ruta_s3=%s, session_id=%s, available=%d, products=%s",
                    ruta_s3,
                    session_id,
                    len(results),
                    [p.nombre_comercial for p in results],
                )
        except CatalogError as e:
            logger.error(
                "Catalog error when resolving ruta_s3: session_id=%s, error=%s",
                session_id,
                e,
            )
            raise ValueError(f"Failed to search catalog: {e}") from e

    # Download PDF from S3
    try:
        pdf_bytes = s3_client.download_pdf(ruta_s3)
    except S3DownloadError:
        # Fallback: if direct download fails, search catalog using other parameters
        logger.info(
            "Direct download failed for ruta_s3=%s, trying catalog fallback: "
            "categoria=%s, fabricante=%s, modelo=%s, session_id=%s",
            ruta_s3,
            categoria,
            fabricante,
            modelo,
            session_id,
        )

        if categoria:
            catalog = get_catalog()
            modelo_contiene = modelo if modelo else None
            results = catalog.search(
                categoria=categoria,
                fabricante=fabricante,
                modelo_contiene=modelo_contiene,
            )

            if len(results) == 1:
                # Single product found, use its ruta_s3 and retry
                ruta_s3 = results[0].ruta_s3
                logger.info(
                    "Fallback successful, using ruta_s3=%s, session_id=%s",
                    ruta_s3,
                    session_id,
                )
                pdf_bytes = s3_client.download_pdf(ruta_s3)
            else:
                # Multiple products found - pick first one as fallback (deterministic)
                ruta_s3 = results[0].ruta_s3
                logger.warning(
                    "Multiple products found during fallback, selecting first: "
                    "ruta_s3=%s, session_id=%s, available_products=%d",
                    ruta_s3,
                    session_id,
                    len(results),
                )
                pdf_bytes = s3_client.download_pdf(ruta_s3)
        else:
            # No categoria to search with, re-raise original error
            raise

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
        return response, [ruta_s3]
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


# Alias for backward compatibility with tests
_process_tool_call = _process_leer_ficha_tecnica


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest, api_key: str = Depends(verify_api_key)):
    """
    Chat endpoint that handles user messages.

    Implements an agentic loop pattern with tool calling:
    1. LLM call checks if tools need to be invoked
    2. Process tool calls (buscar_producto or leer_ficha_tecnica)
    3. Loop back to LLM with tool results until no more tools called
    4. Return final response
    """
    session_id = request.session_id or str(uuid.uuid4())
    request_id = str(uuid.uuid4())

    logger.debug(
        "Incoming request: request_id=%s, session_id=%s, message_preview=%s",
        request_id,
        session_id,
        request.message[:100],
    )

    # Detect escalation
    escalation_result = default_detector.detect(request.message)

    if escalation_result.escalate:
        logger.info(
            "Escalation detected: request_id=%s, session_id=%s, reason=%s",
            request_id,
            session_id,
            escalation_result.reason,
        )
        # Guardamos la consulta en la sesión aunque vayamos a escalar
        session_manager.add_turn(
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
            source_documents=[],
            num_sources=0,
        )

    system_message = {"role": "system", "content": ARTE_SYSTEM_PROMPT}
    conversation_history: list[dict[str, Any]] = [
        system_message,
        {"role": "user", "content": request.message},
    ]
    source_docs: list[SourceDocument] = []

    try:
        # Agentic loop: keep calling LLM until no more tool calls
        iteration = 0
        tool_results_summary = ""
        last_output_text = ""

        while iteration < MAX_AGENTIC_ITERATIONS:
            iteration += 1
            logger.debug(
                "Agentic loop iteration %d: request_id=%s, session_id=%s",
                iteration,
                request_id,
                session_id,
            )
            
            # Obtener contexto de la sesión para mejorar el prompt
            context_string = session_manager.get_context_string(session_id)

            # Build user input with context and tool results if available
            if iteration == 1:
                # First iteration: use original message with context
                user_input = request.message
                if context_string:
                    user_input = (
                        f"Contexto de la conversación:\n{context_string}\n\n"
                        f"Pregunta actual: {request.message}"
                    )
            else:
                # Subsequent iterations: include previous tool results
                user_input = (
                    f"Resultados de las herramientas invocadas anteriormente:\n"
                    f"{tool_results_summary}\n\n"
                    f"Pregunta original: {request.message}\n"
                    f"Considera los resultados anteriores y proporciona una respuesta final."
                )

            # First LLM call with tools
            logger.debug(
                "Calling LLM with tools: request_id=%s, session_id=%s, "
                "model=%s, iteration=%d",
                request_id,
                session_id,
                llm_client.model,
                iteration,
            )
            llm_response = llm_client.get_llm_response_with_tools(
                message=user_input,
                session_id=session_id,
                system_prompt=ARTE_SYSTEM_PROMPT,
                context=context_string,
            )

            last_output_text = llm_response.get("output_text", "")
            tool_calls = llm_response.get("tool_calls", [])

            if not tool_calls:
                # No tool call needed - return normal response
                content = llm_response.get("output_text", "")
                session_manager.add_turn(
                    session_id=session_id,
                    question=request.message,
                    answer=content,
                    source_documents=[],
                )
                return ChatResponse(
                    response=content,
                    escalate=False,
                    session_id=session_id,
                    source_documents=source_docs,
                    num_sources=len(source_docs),
                )

            # Process tool calls and collect results
            tool_results: list[dict[str, Any]] = []

            for tool_call in tool_calls:
                function_name = tool_call.get("function", {}).get("name")
                tool_call_id = tool_call.get("id", "")
                arguments = _parse_tool_arguments(tool_call)

                logger.info(
                    "Processing tool call: request_id=%s, session_id=%s, "
                    "function=%s, iteration=%d",
                    request_id,
                    session_id,
                    function_name,
                    iteration,
                )

                try:
                    if function_name == "buscar_producto":
                        result_content = _process_buscar_producto(
                            arguments=arguments,
                            session_id=session_id,
                        )
                        tool_results.append(
                            {
                                "tool_call_id": tool_call_id,
                                "function_name": function_name,
                                "content": result_content,
                                "success": True,
                            }
                        )

                    elif function_name == "leer_ficha_tecnica":
                        final_response, new_source_docs = _process_leer_ficha_tecnica(
                            tool_call=tool_call,
                            user_message=request.message,
                            session_id=session_id,
                        )
                        # Track source documents
                        source_docs.extend([SourceDocument(ruta=ruta) for ruta in new_source_docs])
                        
                        tool_results.append(
                            {
                                "tool_call_id": tool_call_id,
                                "function_name": function_name,
                                "content": final_response,
                                "success": True,
                            }
                        )

                    else:
                        logger.warning(
                            "Unknown tool called: %s, request_id=%s, session_id=%s",
                            function_name,
                            request_id,
                            session_id,
                        )
                        tool_results.append(
                            {
                                "tool_call_id": tool_call_id,
                                "function_name": function_name,
                                "content": f"Error: Herramienta desconocida '{function_name}'",
                                "success": False,
                            }
                        )
                except S3DownloadError as e:
                    logger.error(
                        "S3 download error in tool call: request_id=%s, "
                        "session_id=%s, function=%s, error=%s",
                        request_id,
                        session_id,
                        function_name,
                        e,
                    )
                    tool_results.append(
                        {
                            "tool_call_id": tool_call_id,
                            "function_name": function_name,
                            "content": (
                                "Lo siento, no pude acceder a la ficha técnica del "
                                "producto solicitado. El archivo no está disponible "
                                "en nuestro catálogo. Por favor, contacta al equipo "
                                "de ventas para más información."
                            ),
                            "success": False,
                        }
                    )
                except FileUploadError as e:
                    logger.error(
                        "File upload error in tool call: request_id=%s, "
                        "session_id=%s, function=%s, error=%s",
                        request_id,
                        session_id,
                        function_name,
                        e,
                    )
                    tool_results.append(
                        {
                            "tool_call_id": tool_call_id,
                            "function_name": function_name,
                            "content": (
                                "Lo siento, tuve problemas al procesar la ficha técnica. "
                                "Por favor, intenta novamente o contacta al equipo de ventas."
                            ),
                            "success": False,
                        }
                    )
                except ValueError as e:
                    # ValueError includes cases like missing ruta_s3 with catalog fallback
                    logger.warning(
                        "ValueError in tool call: request_id=%s, session_id=%s, "
                        "function=%s, error=%s",
                        request_id,
                        session_id,
                        function_name,
                        e,
                    )
                    tool_results.append(
                        {
                            "tool_call_id": tool_call_id,
                            "function_name": function_name,
                            "content": str(e),
                            "success": False,
                        }
                    )
                except Exception as e:
                    logger.exception(
                        "Error processing tool call: request_id=%s, session_id=%s, "
                        "function=%s, error=%s",
                        request_id,
                        session_id,
                        function_name,
                        e,
                    )
                    tool_results.append(
                        {
                            "tool_call_id": tool_call_id,
                            "function_name": function_name,
                            "content": (
                                "Ocurrió un error al procesar tu solicitud. "
                                "Por favor, intenta más tarde."
                            ),
                            "success": False,
                        }
                    )

            # Check if all tools failed - if so, return error response
            if all(not r["success"] for r in tool_results):
                error_content = "\n".join(
                    f"- {r['function_name']}: {r['content']}" for r in tool_results
                )
                session_manager.add_turn(
                    session_id=session_id,
                    question=request.message,
                    answer=error_content,
                    source_documents=[],
                )
                return ChatResponse(
                    response=error_content,
                    escalate=False,
                    session_id=session_id,
                    source_documents=source_docs,
                    num_sources=len(source_docs),
                )

            # Build tool results summary for next iteration
            tool_results_summary = "\n\n".join(
                f"## Resultado de {r['function_name']}:\n{r['content']}"
                for r in tool_results
            )
            logger.debug(
                "Tool results collected: num_results=%d, iteration=%d",
                len(tool_results),
                iteration,
            )

        # Max iterations reached
        logger.warning(
            "Max agentic iterations reached: request_id=%s, session_id=%s, "
            "iterations=%d",
            request_id,
            session_id,
            iteration,
        )
        return ChatResponse(
            response=(
                "Se alcanzó el límite de iteraciones. Por favor, reformula "
                "tu pregunta o contacta al equipo de ventas."
            ),
            escalate=False,
            session_id=session_id,
            source_documents=source_docs,
            num_sources=len(source_docs),
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
