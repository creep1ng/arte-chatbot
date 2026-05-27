"""
ARTE Chatbot Backend
FastAPI server with /health and /chat endpoints.
"""

import asyncio
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from backend.app.auth import verify_api_key, verify_chatwoot_signature
from backend.app.catalog import CatalogError, get_catalog
from backend.app.chatwoot_client import ChatwootClient
from backend.app.chatwoot_handler import ChatwootHandler
from backend.app.config import settings
from backend.app.config_provider import EnvConfigProvider
from backend.app.conversation_logger import ConversationLogEntry, ConversationLogger
from backend.app.escalation_handler import EscalationHandler
from backend.app.file_inputs import FileInputsClient, FileUploadError
from backend.app.greeting import maybe_prepend_greeting
from backend.app.llm_client import (
    _WHATSAPP_SPLIT_INSTRUCTIONS,
    ARTE_SYSTEM_PROMPT,
    LLMClient,
    LLMServiceError,
    expand_query_with_context,
)
from backend.app.logging_config import setup_logging
from backend.app.message_buffer import (
    RedisMessageBuffer,
    add_to_buffer,
    clear_pending_chat_response,
    clear_processing,
    flush_buffer,
    get_buffer_count,
    is_buffering,
    is_processing,
    pop_pending_chat_response,
    schedule_flush,
    set_pending_chat_response,
    set_processing,
)
from backend.app.message_splitter import process_split_messages
from backend.app.redis_cache import RedisCache
from backend.app.s3_client import S3Client, S3DownloadError
from backend.app.schemas import (
    ChatwootWebhookPayload,
    ConversationCreatedPayload,
    ConversationStatusChangedPayload,
    LLMResponse,
    MessageCreatedPayload,
    SourceDocument,
)
from backend.app.session import session_manager
from backend.app.tools import get_tool_definitions, validate_s3_path
from backend.app.user_profiler import PROFILE_INSTRUCTIONS, infer_user_profile
from backend.app.whatsapp_formatter import format_for_whatsapp
from rag import (
    DEFAULT_ESCALATION_MESSAGE,
    default_detector,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

load_dotenv()

# Configure logging before anything else (reads LOG_LEVEL from centralized settings)
setup_logging()

logger = logging.getLogger(__name__)

INTENT_TYPES = [
    "FAQ",
    "product_info",
    "escalate_quote",
    "escalate_technical",
    "escalate_order",
    "fuera_de_dominio",
]

OUT_OF_DOMAIN_MESSAGE = (
    "Lo siento, no puedo responder preguntas sobre ese tema. "
    "Estoy especializado en ayudarte con información sobre energía solar, "
    "como paneles, inversores, controladores, baterías, fichas técnicas "
    "de productos y consultas generales sobre sistemas de energía solar. "
    "¿Hay algo relacionado con energía solar en lo que pueda ayudarte?"
)

INTENT_MARKER_RE = re.compile(r"\[INTENT:\s*(\w+)\]")


def _extract_intent_type(text: str) -> tuple[str, str]:
    """Extract intent_type from LLM output text.

    The LLM is instructed to prefix responses with [INTENT: <type>].
    This function parses the marker and returns the cleaned response.

    Args:
        text: Raw LLM output text.

    Returns:
        Tuple of (intent_type, cleaned_response_text).
    """
    match = INTENT_MARKER_RE.search(text)
    if match:
        intent = match.group(1)
        if intent in INTENT_TYPES:
            cleaned = INTENT_MARKER_RE.sub("", text).strip()
            return intent, cleaned
    return "FAQ", text


ESCALATE_INTENTS = {"escalate_quote", "escalate_technical", "escalate_order"}


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

# Module-level clients maintained for backward compatibility with existing tests.
# New code should prefer dependency injection via FastAPI Depends().
llm_client = LLMClient()
s3_client = S3Client()
file_inputs_client = FileInputsClient()

# Conversation logger (lazy, gated by settings flag)
conversation_logger: Optional[ConversationLogger] = None
if settings.conversation_logging_enabled:
    conversation_logger = ConversationLogger(
        s3_client=s3_client,
        bucket=settings.aws_bucket_name,
        prefix=settings.conversation_log_prefix,
    )


def get_llm_client() -> LLMClient:
    """Dependency that provides a LLMClient instance."""
    return llm_client


def get_s3_client() -> S3Client:
    """Dependency that provides a S3Client instance."""
    return s3_client


def get_file_inputs_client() -> FileInputsClient:
    """Dependency that provides a FileInputsClient instance."""
    return file_inputs_client


def get_config_provider() -> EnvConfigProvider:
    """Dependency that provides a ConfigProvider instance."""
    return EnvConfigProvider()


def get_redis_cache() -> RedisCache:
    """Dependency that provides a RedisCache instance for Chatwoot state."""
    account_id = settings.chatwoot_account_id or "unconfigured"
    return RedisCache(
        redis_url=settings.redis_url,
        password=settings.redis_password,
        account_id=account_id,
    )


def get_chatwoot_client() -> ChatwootClient:
    """Dependency that provides a configured Chatwoot API client."""
    if (
        not settings.chatwoot_api_url
        or not settings.chatwoot_agent_bot_token
        or settings.chatwoot_account_id is None
    ):
        raise RuntimeError("Chatwoot API client is not configured")

    return ChatwootClient(
        base_url=settings.chatwoot_api_url,
        agent_bot_token=settings.chatwoot_agent_bot_token,
        account_id=settings.chatwoot_account_id,
        redis_cache=get_redis_cache(),
    )


def get_chatwoot_handler() -> ChatwootHandler:
    """Dependency that wires Chatwoot webhook handling services."""
    redis_cache = get_redis_cache()
    config_provider = get_config_provider()
    chatwoot_client = get_chatwoot_client()
    message_buffer = RedisMessageBuffer(redis_cache, config_provider)
    escalation_handler = EscalationHandler(
        chatwoot_client=chatwoot_client,
        config_provider=config_provider,
        session_manager=session_manager,
    )
    return ChatwootHandler(
        chatwoot_client=chatwoot_client,
        redis_cache=redis_cache,
        config_provider=config_provider,
        message_buffer=message_buffer,
        session_manager=session_manager,
        escalation_handler=escalation_handler,
    )


# Lazy-load catalog to allow /health to work without AWS credentials in CI
_catalog_search: Optional[Any] = None


def get_catalog_search() -> Any:
    """Lazy loader for catalog to enable CI testing without AWS credentials."""
    global _catalog_search
    if _catalog_search is None:
        _catalog_search = get_catalog()
    return _catalog_search


MAX_AGENTIC_ITERATIONS = int(os.getenv("MAX_AGENTIC_ITERATIONS", "5"))


def _fire_conversation_log(
    session_id: str,
    user_message: str,
    bot_response: str,
    intent_type: str,
    escalate: bool,
    source_documents: list[str],
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
    response_time_ms: float,
    user_profile: Optional[str] = None,
) -> None:
    """Fire-and-forget conversation log. Never blocks or raises."""
    if conversation_logger is None:
        return
    turn_number = len(session_manager.get_history(session_id))
    entry = ConversationLogEntry(
        session_id=session_id,
        turn_number=turn_number,
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        user_message=user_message,
        bot_response=bot_response,
        intent_type=intent_type,
        escalate=escalate,
        source_documents=source_documents,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        response_time_ms=response_time_ms,
        model=llm_client.model,
        git_commit_hash=settings.git_commit_hash,
        user_profile=user_profile,
    )
    asyncio.create_task(conversation_logger.log_turn(entry))


class ChatRequest(BaseModel):
    """Request model for /chat endpoint."""

    message: str = Field(..., min_length=1)
    session_id: Optional[str] = None
    is_final: Optional[bool] = Field(
        default=None,
        description="Hint to flush multi-message buffer immediately",
    )


class ChatResponse(BaseModel):
    """Response model for /chat endpoint."""

    response: str
    escalate: bool = False
    intent_type: str = "FAQ"
    reason: Optional[str] = None
    session_id: str
    source_documents: list[SourceDocument] = Field(default_factory=list)
    num_sources: int = 0
    user_profile: Optional[str] = None
    messages: list[str] = Field(default_factory=list)
    delays_ms: list[int] = Field(default_factory=list)
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class BufferingResponse(BaseModel):
    """Response returned while multi-message buffer is active."""

    status: str = "buffering"
    session_id: str
    poll_url: Optional[str] = Field(
        default=None,
        description="URL to poll for the processed result after window expires",
    )


class BufferResultResponse(BaseModel):
    """Response returned when polling a buffered result."""

    status: str = Field(
        default="pending",
        description="One of: pending, ready, not_found",
    )
    session_id: str
    result: Optional[str] = Field(
        default=None,
        description="The joined message when status is ready",
    )


@app.get("/buffer-result/{session_id}", response_model=BufferResultResponse)
async def get_buffer_result(session_id: str) -> BufferResultResponse:
    """Poll for buffered message processing result.

    After a 202 response from /chat, the client should poll this endpoint.
    When the buffer window expires, the backend processes the joined message
    with the chatbot and stores the response for pickup.
    """
    chat_response_json = pop_pending_chat_response(session_id)
    if chat_response_json:
        return BufferResultResponse(
            status="ready",
            session_id=session_id,
            result=chat_response_json,
        )

    if is_buffering(session_id):
        return BufferResultResponse(
            status="pending",
            session_id=session_id,
        )

    if is_processing(session_id):
        return BufferResultResponse(
            status="pending",
            session_id=session_id,
        )

    return BufferResultResponse(
        status="not_found",
        session_id=session_id,
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


def _parse_chatwoot_payload(raw_payload: bytes) -> ChatwootWebhookPayload:
    """Parse a raw Chatwoot webhook body into the matching schema."""
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        logger.warning("chatwoot_payload_invalid_json size=%s", len(raw_payload))
        raise HTTPException(status_code=422, detail="Invalid Chatwoot payload") from exc

    if not isinstance(payload, dict):
        logger.warning(
            "chatwoot_payload_invalid_type payload_type=%s",
            type(payload).__name__,
        )
        raise HTTPException(status_code=422, detail="Invalid Chatwoot payload")

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "chatwoot_payload_received %s", _summarize_chatwoot_payload(payload)
        )

    event = payload.get("event")
    schema_by_event = {
        "message_created": MessageCreatedPayload,
        "conversation_created": ConversationCreatedPayload,
        "conversation_status_changed": ConversationStatusChangedPayload,
    }
    schema = schema_by_event.get(str(event))
    if event == "message_created":
        payload = _normalize_message_created_payload(payload)
    try:
        if schema is None:
            return ChatwootWebhookPayload.model_validate(payload)
        return schema.model_validate(payload)
    except ValidationError as exc:
        logger.warning(
            "chatwoot_payload_validation_failed event=%s schema=%s errors=%s summary=%s",
            event,
            schema.__name__ if schema is not None else ChatwootWebhookPayload.__name__,
            exc.errors(),
            _summarize_chatwoot_payload(payload),
        )
        if schema is not None and event is not None:
            return ChatwootWebhookPayload.model_validate(
                {
                    "event": str(event),
                    "account": payload.get("account")
                    if isinstance(payload.get("account"), dict)
                    else {},
                }
            )
        raise HTTPException(status_code=422, detail=exc.errors()) from exc


def _normalize_message_created_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize Chatwoot's flat message webhook shape to internal schema."""
    normalized = dict(payload)
    if "message" not in normalized:
        normalized["message"] = {
            "id": normalized.get("id"),
            "content": normalized.get("content"),
            "content_type": normalized.get("content_type", "text"),
            "message_type": _normalize_chatwoot_message_type(
                normalized.get("message_type", "incoming")
            ),
            "private": normalized.get("private", False),
        }
    elif isinstance(normalized["message"], dict):
        normalized["message"] = {
            **normalized["message"],
            "message_type": _normalize_chatwoot_message_type(
                normalized["message"].get("message_type", "incoming")
            ),
        }

    sender = normalized.get("sender")
    if isinstance(sender, dict):
        sender_type = sender.get("type")
        if isinstance(sender_type, str):
            normalized["sender"] = {**sender, "type": sender_type.lower()}
        elif _looks_like_chatwoot_contact(sender):
            normalized["sender"] = {**sender, "type": "contact"}

    conversation = normalized.get("conversation")
    if isinstance(conversation, dict) and conversation.get("contact_id") is None:
        contact_inbox = conversation.get("contact_inbox")
        if isinstance(contact_inbox, dict):
            normalized["conversation"] = {
                **conversation,
                "contact_id": contact_inbox.get("contact_id"),
            }

    return normalized


def _normalize_chatwoot_message_type(value: Any) -> Any:
    """Normalize Chatwoot Rails enum values to API string values."""
    if isinstance(value, int):
        return {
            0: "incoming",
            1: "outgoing",
            2: "activity",
        }.get(value, value)
    return value


def _looks_like_chatwoot_contact(sender: dict[str, Any]) -> bool:
    """Return true when a Chatwoot sender dict has contact-only fields."""
    return (
        any(
            sender.get(key) is not None
            for key in (
                "phone_number",
                "email",
                "identifier",
            )
        )
        or "blocked" in sender
    )


def _summarize_chatwoot_payload(payload: dict[str, Any]) -> str:
    """Return a PII-light summary for webhook diagnostics."""
    conversation = payload.get("conversation")
    message = payload.get("message")
    sender = payload.get("sender")
    return (
        f"event={payload.get('event')!r} "
        f"keys={sorted(payload.keys())} "
        f"conversation_keys="
        f"{sorted(conversation.keys()) if isinstance(conversation, dict) else None} "
        f"message_keys={sorted(message.keys()) if isinstance(message, dict) else None} "
        f"sender_keys={sorted(sender.keys()) if isinstance(sender, dict) else None} "
        f"has_top_level_message_fields="
        f"{any(key in payload for key in ('id', 'content', 'content_type', 'message_type'))}"
    )


@app.post("/webhook/chatwoot")
async def chatwoot_webhook(
    request: Request,
    x_chatwoot_signature: Annotated[Optional[str], Header()] = None,
    x_chatwoot_timestamp: Annotated[Optional[str], Header()] = None,
    x_hub_signature_256: Annotated[Optional[str], Header()] = None,
) -> JSONResponse:
    """Receive, verify, validate, and dispatch Chatwoot webhooks.

    The handler is intentionally awaited instead of scheduled with
    ``BackgroundTasks`` so processing failures return HTTP 500. Chatwoot can
    then retry the webhook instead of receiving a false-positive 200 ack.
    """
    if not settings.chatwoot_enabled:
        return JSONResponse(
            status_code=503,
            content={"detail": "Chatwoot integration disabled"},
        )

    raw_payload = await request.body()
    signature = x_chatwoot_signature or x_hub_signature_256
    if not verify_chatwoot_signature(
        raw_payload,
        signature,
        settings.chatwoot_webhook_secret,
        timestamp=x_chatwoot_timestamp,
    ):
        raise HTTPException(status_code=401, detail="Invalid Chatwoot signature")

    payload = _parse_chatwoot_payload(raw_payload)
    dependency = (
        request.app.dependency_overrides.get(get_chatwoot_handler)
        or get_chatwoot_handler
    )
    handler = dependency()
    try:
        await handler.handle_event(payload)
    except Exception as exc:
        logger.exception("Chatwoot webhook handler failed: %s", exc)
        raise HTTPException(status_code=500, detail="Chatwoot handler failed") from exc

    return JSONResponse(status_code=200, content={"status": "accepted"})


@app.get("/health/chatwoot")
async def chatwoot_health(
    redis_cache: Annotated[RedisCache, Depends(get_redis_cache)],
) -> JSONResponse:
    """Report Chatwoot integration health without external API calls."""
    if not settings.chatwoot_enabled:
        return JSONResponse(
            status_code=200,
            content={
                "status": "disabled",
                "chatwoot_enabled": False,
                "redis": "not_configured",
                "chatwoot_api": "not_configured",
            },
        )

    has_chatwoot_config = bool(
        settings.chatwoot_api_url
        and settings.chatwoot_agent_bot_token
        and settings.chatwoot_account_id is not None
    )
    redis_status = "healthy" if await redis_cache.health_check() else "unavailable"
    chatwoot_api_status = "configured" if has_chatwoot_config else "not_configured"
    status_value = (
        "healthy"
        if redis_status == "healthy" and chatwoot_api_status == "configured"
        else "degraded"
    )

    return JSONResponse(
        status_code=200,
        content={
            "status": status_value,
            "chatwoot_enabled": True,
            "redis": redis_status,
            "chatwoot_api": chatwoot_api_status,
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


def _handle_buscar_producto_tool(
    tool_call: dict[str, Any],
) -> tuple[str, bool]:
    """Handle a buscar_producto tool call (for testing compatibility).

    Args:
        tool_call: The tool call dict from OpenAI response.

    Returns:
        Tuple of (output_text, is_terminal).
        is_terminal is always False for buscar_producto as it's not a final tool.
    """
    arguments = _parse_tool_arguments(tool_call)

    categoria = arguments.get("categoria")
    fabricante = arguments.get("fabricante")
    capacidad_min = _safe_float(arguments.get("capacidad_min"))
    capacidad_max = _safe_float(arguments.get("capacidad_max"))
    tipo = arguments.get("tipo")
    modelo_contiene = arguments.get("modelo_contiene")

    if not categoria:
        return (
            "Error: Se requiere especificar una categoría (paneles, inversores, controladores, baterias).",
            False,
        )

    try:
        # Use catalog_search.search() which can be mocked in tests
        results = get_catalog_search().search(
            categoria=categoria,
            fabricante=fabricante,
            capacidad_min=capacidad_min,
            capacidad_max=capacidad_max,
            tipo=tipo,
            modelo_contiene=modelo_contiene,
        )

        if not results:
            return (
                "No encontré productos que coincidan con los criterios de búsqueda especificados. "
                "Prueba con otros filtros o contacta al equipo de ventas de Arte Soluciones Energéticas.",
                False,
            )

        # Format results for the LLM
        lines = [
            f"Se encontraron {len(results)} producto(s) en la categoría '{categoria}':\n"
        ]

        for product in results:
            lines.append(f"\n## {product.nombre_comercial} ({product.fabricante})")
            if product.descripcion:
                lines.append(f"Descripción: {product.descripcion}")
            lines.append("Modelos disponibles:")
            for variante in product.variantes:
                modelo = variante.get("modelo", "Sin nombre")
                params = variante.get("parametros_clave", {})
                params_str = ", ".join(f"{k}: {v}" for k, v in params.items())
                lines.append(f"  - {modelo} ({params_str})")
            lines.append(
                f"  → Para ver más detalles, usa leer_ficha_tecnica con ruta_s3: {product.ruta_s3}"
            )

        return ("\n".join(lines), False)

    except CatalogError as e:
        logger.error("Catalog error in buscar_producto: error=%s", e)
        return (
            "Lo siento, no pude consultar el catálogo de productos. "
            "Por favor, intenta más tarde o contacta al equipo de ventas.",
            False,
        )


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
            lines.append("Modelos disponibles:")
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


async def _process_leer_ficha_tecnica(
    tool_call: dict[str, Any],
    user_message: str,
    session_id: str,
    llm_client: LLMClient,
    s3_client: S3Client,
    file_inputs_client: FileInputsClient,
) -> tuple[LLMResponse, list[str]]:
    """Process a tool call for reading a technical datasheet.

    Args:
        tool_call: The tool call dict from OpenAI response.
        user_message: The original user message.
        session_id: The session identifier.

    Returns:
        Tuple of (LLMResponse, list_of_s3_paths_used).

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

    # Validate ruta_s3 for path traversal attacks (OWASP LLM07)
    if ruta_s3:
        validate_s3_path(ruta_s3)

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
                validate_s3_path(ruta_s3)
                logger.info(
                    "Found single product, using ruta_s3=%s, session_id=%s",
                    ruta_s3,
                    session_id,
                )
            else:
                # Multiple products found - select first one deterministically
                ruta_s3 = results[0].ruta_s3
                validate_s3_path(ruta_s3)
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
        pdf_bytes = await asyncio.to_thread(s3_client.download_pdf, ruta_s3)
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
                validate_s3_path(ruta_s3)
                logger.info(
                    "Fallback successful, using ruta_s3=%s, session_id=%s",
                    ruta_s3,
                    session_id,
                )
                pdf_bytes = await asyncio.to_thread(s3_client.download_pdf, ruta_s3)
            elif len(results) > 1:
                # Multiple products found - pick first one as fallback (deterministic)
                ruta_s3 = results[0].ruta_s3
                validate_s3_path(ruta_s3)
                logger.warning(
                    "Multiple products found during fallback, selecting first: "
                    "ruta_s3=%s, session_id=%s, available_products=%d",
                    ruta_s3,
                    session_id,
                    len(results),
                )
                pdf_bytes = await asyncio.to_thread(s3_client.download_pdf, ruta_s3)
            else:
                # No results found in catalog fallback
                raise ValueError(
                    "No se encontraron productos en el catálogo con los criterios "
                    "especificados. El archivo solicitado no está disponible."
                )
        else:
            # No categoria to search with, re-raise original error
            raise

    # Generate filename from ruta_s3
    filename = ruta_s3.split("/")[-1] if "/" in ruta_s3 else ruta_s3

    # Upload PDF to OpenAI
    file_id = await asyncio.to_thread(
        file_inputs_client.upload_pdf, pdf_bytes, filename
    )

    # Second LLM call with file
    try:
        llm_response = await asyncio.to_thread(
            llm_client.get_llm_response_with_file,
            message=user_message,
            file_id=file_id,
            session_id=session_id,
        )
        return llm_response, [ruta_s3]
    finally:
        # Clean up: delete the uploaded file
        try:
            await asyncio.to_thread(file_inputs_client.delete_file, file_id)
        except Exception as e:
            logger.warning(
                "Failed to delete file: file_id=%s, session_id=%s, error=%s",
                file_id,
                session_id,
                e,
            )


# Alias for backward compatibility with tests
_process_tool_call = _process_leer_ficha_tecnica


async def _process_chat_message(
    session_id: str,
    message: str,
    llm_client: LLMClient,
    s3_client: S3Client,
    file_inputs_client: FileInputsClient,
    request_id: Optional[str] = None,
) -> ChatResponse:
    """Core chat processing logic shared between endpoint and buffer callback."""
    request_id = request_id or str(uuid.uuid4())
    request_start = time.time()

    logger.debug(
        "Incoming request: request_id=%s, session_id=%s, message_preview=%s",
        request_id,
        session_id,
        message[:100],
    )

    # Infer user profile if not already inferred for this session
    existing_profile = session_manager.get_user_profile(session_id)
    if existing_profile is None:
        history = session_manager.get_history(session_id)
        history_dicts = [{"role": "user", "content": turn.question} for turn in history]
        inferred_profile = infer_user_profile(history_dicts)
        session_manager.set_user_profile(session_id, inferred_profile)
        logger.info(
            "User profile inferred: session_id=%s, profile=%s, turn_count=%d",
            session_id,
            inferred_profile,
            len(history),
        )
    else:
        inferred_profile = existing_profile

    # Build system prompt with profile instructions
    profile_instructions = PROFILE_INSTRUCTIONS.get(
        inferred_profile, PROFILE_INSTRUCTIONS["intermedio"]
    )
    system_prompt_with_profile = f"{ARTE_SYSTEM_PROMPT}\n\n## Adaptación al perfil del usuario\n{profile_instructions}"

    # P2: Append WhatsApp split instructions if enabled
    if settings.split_messages_enabled:
        system_prompt_with_profile += _WHATSAPP_SPLIT_INSTRUCTIONS

    # Detect escalation
    escalation_result = default_detector.detect(message)

    if escalation_result.escalate:
        logger.info(
            "Escalation detected: request_id=%s, session_id=%s, reason=%s",
            request_id,
            session_id,
            escalation_result.reason,
        )
        session_manager.add_turn(
            session_id=session_id,
            question=message,
            answer=DEFAULT_ESCALATION_MESSAGE,
            source_documents=[],
        )
        response_time_ms = (time.time() - request_start) * 1000
        _fire_conversation_log(
            session_id=session_id,
            user_message=message,
            bot_response=DEFAULT_ESCALATION_MESSAGE,
            intent_type="escalate_technical",
            escalate=True,
            source_documents=[],
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
            response_time_ms=response_time_ms,
            user_profile=inferred_profile,
        )
        return ChatResponse(
            response=DEFAULT_ESCALATION_MESSAGE,
            escalate=True,
            intent_type="escalate_technical",
            reason=escalation_result.reason,
            session_id=session_id,
            source_documents=[],
            num_sources=0,
            user_profile=inferred_profile,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
        )

    # Expandir query con contexto anafórico
    history = session_manager.get_history(session_id)
    expanded_query = expand_query_with_context(message, history)

    logger.debug(
        "Query expandida: original='%s', expandida='%s', session_id=%s",
        message[:100],
        expanded_query[:100],
        session_id,
    )

    source_docs: list[SourceDocument] = []

    try:
        iteration = 0
        tool_results_summary = ""
        last_output_text = ""
        acc_input_tokens = 0
        acc_output_tokens = 0
        acc_total_tokens = 0

        while iteration < MAX_AGENTIC_ITERATIONS:
            iteration += 1
            logger.debug(
                "Agentic loop iteration %d: request_id=%s, session_id=%s",
                iteration,
                request_id,
                session_id,
            )

            context_string = session_manager.get_context_string(session_id)

            if iteration == 1:
                user_input = expanded_query
                if context_string:
                    user_input = (
                        f"Contexto de la conversación:\n{context_string}\n\n"
                        f"Pregunta actual: {expanded_query}"
                    )
            else:
                user_input = (
                    f"Resultados de las herramientas invocadas anteriormente:\n"
                    f"{tool_results_summary}\n\n"
                    f"Pregunta original: {expanded_query}\n"
                    f"Considera los resultados anteriores y proporciona una respuesta final."
                )

            logger.debug(
                "Calling LLM with tools: request_id=%s, session_id=%s, "
                "model=%s, iteration=%d",
                request_id,
                session_id,
                llm_client.model,
                iteration,
            )
            llm_response = await asyncio.to_thread(
                llm_client.get_llm_response_with_tools,
                message=user_input,
                session_id=session_id,
                system_prompt=system_prompt_with_profile,
                context=context_string,
            )

            last_output_text = llm_response.text
            tool_calls = llm_response.tool_calls

            acc_input_tokens += llm_response.input_tokens
            acc_output_tokens += llm_response.output_tokens
            acc_total_tokens += llm_response.total_tokens

            if not tool_calls:
                content = llm_response.text
                intent_type, cleaned_content = _extract_intent_type(content)

                if intent_type in ESCALATE_INTENTS:
                    session_manager.add_turn(
                        session_id=session_id,
                        question=message,
                        answer=DEFAULT_ESCALATION_MESSAGE,
                        source_documents=[],
                    )
                    session_manager.add_token_usage(
                        session_id,
                        acc_input_tokens,
                        acc_output_tokens,
                        acc_total_tokens,
                    )
                    response_time_ms = (time.time() - request_start) * 1000
                    _fire_conversation_log(
                        session_id=session_id,
                        user_message=message,
                        bot_response=DEFAULT_ESCALATION_MESSAGE,
                        intent_type=intent_type,
                        escalate=True,
                        source_documents=[s.ruta for s in source_docs],
                        input_tokens=acc_input_tokens,
                        output_tokens=acc_output_tokens,
                        total_tokens=acc_total_tokens,
                        response_time_ms=response_time_ms,
                        user_profile=inferred_profile,
                    )
                    return ChatResponse(
                        response=DEFAULT_ESCALATION_MESSAGE,
                        escalate=True,
                        intent_type=intent_type,
                        reason=f"Intent classified as {intent_type}",
                        session_id=session_id,
                        source_documents=source_docs,
                        num_sources=len(source_docs),
                        input_tokens=acc_input_tokens,
                        output_tokens=acc_output_tokens,
                        total_tokens=acc_total_tokens,
                    )

                if intent_type == "fuera_de_dominio":
                    session_manager.add_turn(
                        session_id=session_id,
                        question=message,
                        answer=OUT_OF_DOMAIN_MESSAGE,
                        source_documents=[],
                    )
                    session_manager.add_token_usage(
                        session_id,
                        acc_input_tokens,
                        acc_output_tokens,
                        acc_total_tokens,
                    )
                    response_time_ms = (time.time() - request_start) * 1000
                    _fire_conversation_log(
                        session_id=session_id,
                        user_message=message,
                        bot_response=OUT_OF_DOMAIN_MESSAGE,
                        intent_type=intent_type,
                        escalate=False,
                        source_documents=[],
                        input_tokens=acc_input_tokens,
                        output_tokens=acc_output_tokens,
                        total_tokens=acc_total_tokens,
                        response_time_ms=response_time_ms,
                        user_profile=inferred_profile,
                    )
                    return ChatResponse(
                        response=OUT_OF_DOMAIN_MESSAGE,
                        escalate=False,
                        intent_type=intent_type,
                        session_id=session_id,
                        source_documents=source_docs,
                        num_sources=len(source_docs),
                        user_profile=inferred_profile,
                        input_tokens=acc_input_tokens,
                        output_tokens=acc_output_tokens,
                        total_tokens=acc_total_tokens,
                    )

                response_text = cleaned_content
                if settings.whatsapp_formatter_enabled:
                    response_text = format_for_whatsapp(cleaned_content)

                split_messages, split_delays = process_split_messages(
                    text=response_text,
                    intent_type=intent_type,
                    llm_regenerate_fn=None,
                )

                escalate = intent_type in ESCALATE_INTENTS
                if split_messages:
                    split_messages[0] = maybe_prepend_greeting(
                        session_id=session_id,
                        response_text=split_messages[0],
                        intent_type=intent_type,
                        escalate=escalate,
                    )
                    response_text = "\n\n".join(split_messages)
                else:
                    response_text = maybe_prepend_greeting(
                        session_id=session_id,
                        response_text=response_text,
                        intent_type=intent_type,
                        escalate=escalate,
                    )

                session_manager.add_turn(
                    session_id=session_id,
                    question=message,
                    answer=response_text,
                    source_documents=[],
                )
                session_manager.add_token_usage(
                    session_id, acc_input_tokens, acc_output_tokens, acc_total_tokens
                )
                response_time_ms = (time.time() - request_start) * 1000
                _fire_conversation_log(
                    session_id=session_id,
                    user_message=message,
                    bot_response=response_text,
                    intent_type=intent_type,
                    escalate=False,
                    source_documents=[s.ruta for s in source_docs],
                    input_tokens=acc_input_tokens,
                    output_tokens=acc_output_tokens,
                    total_tokens=acc_total_tokens,
                    response_time_ms=response_time_ms,
                    user_profile=inferred_profile,
                )
                return ChatResponse(
                    response=response_text,
                    escalate=False,
                    intent_type=intent_type,
                    session_id=session_id,
                    source_documents=source_docs,
                    num_sources=len(source_docs),
                    user_profile=inferred_profile,
                    messages=split_messages,
                    delays_ms=split_delays,
                    input_tokens=acc_input_tokens,
                    output_tokens=acc_output_tokens,
                    total_tokens=acc_total_tokens,
                )

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
                        (
                            ficha_response,
                            new_source_docs,
                        ) = await _process_leer_ficha_tecnica(
                            tool_call=tool_call,
                            user_message=expanded_query,
                            session_id=session_id,
                            llm_client=llm_client,
                            s3_client=s3_client,
                            file_inputs_client=file_inputs_client,
                        )
                        acc_input_tokens += ficha_response.input_tokens
                        acc_output_tokens += ficha_response.output_tokens
                        acc_total_tokens += ficha_response.total_tokens

                        source_docs.extend(
                            [SourceDocument(ruta=ruta) for ruta in new_source_docs]
                        )

                        tool_results.append(
                            {
                                "tool_call_id": tool_call_id,
                                "function_name": function_name,
                                "content": ficha_response.text,
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

            if all(not r["success"] for r in tool_results):
                error_content = "\n".join(
                    f"- {r['function_name']}: {r['content']}" for r in tool_results
                )
                session_manager.add_turn(
                    session_id=session_id,
                    question=message,
                    answer=error_content,
                    source_documents=[],
                )
                session_manager.add_token_usage(
                    session_id, acc_input_tokens, acc_output_tokens, acc_total_tokens
                )
                response_time_ms = (time.time() - request_start) * 1000
                _fire_conversation_log(
                    session_id=session_id,
                    user_message=message,
                    bot_response=error_content,
                    intent_type="error_tool_failure",
                    escalate=False,
                    source_documents=[s.ruta for s in source_docs],
                    input_tokens=acc_input_tokens,
                    output_tokens=acc_output_tokens,
                    total_tokens=acc_total_tokens,
                    response_time_ms=response_time_ms,
                    user_profile=inferred_profile,
                )
                return ChatResponse(
                    response=error_content,
                    escalate=False,
                    session_id=session_id,
                    source_documents=source_docs,
                    num_sources=len(source_docs),
                    user_profile=inferred_profile,
                    input_tokens=acc_input_tokens,
                    output_tokens=acc_output_tokens,
                    total_tokens=acc_total_tokens,
                )

            tool_results_summary = "\n\n".join(
                f"## Resultado de {r['function_name']}:\n{r['content']}"
                for r in tool_results
            )
            logger.debug(
                "Tool results collected: num_results=%d, iteration=%d",
                len(tool_results),
                iteration,
            )

        logger.warning(
            "Max agentic iterations reached: request_id=%s, session_id=%s, "
            "iterations=%d",
            request_id,
            session_id,
            iteration,
        )
        intent_type, cleaned_text = _extract_intent_type(last_output_text)

        if intent_type in ESCALATE_INTENTS:
            session_manager.add_turn(
                session_id=session_id,
                question=message,
                answer=DEFAULT_ESCALATION_MESSAGE,
                source_documents=[],
            )
            session_manager.add_token_usage(
                session_id, acc_input_tokens, acc_output_tokens, acc_total_tokens
            )
            response_time_ms = (time.time() - request_start) * 1000
            _fire_conversation_log(
                session_id=session_id,
                user_message=message,
                bot_response=DEFAULT_ESCALATION_MESSAGE,
                intent_type=intent_type,
                escalate=True,
                source_documents=[s.ruta for s in source_docs],
                input_tokens=acc_input_tokens,
                output_tokens=acc_output_tokens,
                total_tokens=acc_total_tokens,
                response_time_ms=response_time_ms,
                user_profile=inferred_profile,
            )
            return ChatResponse(
                response=DEFAULT_ESCALATION_MESSAGE,
                escalate=True,
                intent_type=intent_type,
                reason=f"Intent classified as {intent_type}",
                session_id=session_id,
                source_documents=source_docs,
                num_sources=len(source_docs),
                input_tokens=acc_input_tokens,
                output_tokens=acc_output_tokens,
                total_tokens=acc_total_tokens,
            )

        session_manager.add_token_usage(
            session_id, acc_input_tokens, acc_output_tokens, acc_total_tokens
        )
        response_time_ms = (time.time() - request_start) * 1000
        _fire_conversation_log(
            session_id=session_id,
            user_message=message,
            bot_response=(
                "Se alcanzó el límite de iteraciones. Por favor, reformula "
                "tu pregunta o contacta al equipo de ventas."
            ),
            intent_type=intent_type,
            escalate=False,
            source_documents=[s.ruta for s in source_docs],
            input_tokens=acc_input_tokens,
            output_tokens=acc_output_tokens,
            total_tokens=acc_total_tokens,
            response_time_ms=response_time_ms,
            user_profile=inferred_profile,
        )
        return ChatResponse(
            response=(
                "Se alcanzó el límite de iteraciones. Por favor, reformula "
                "tu pregunta o contacta al equipo de ventas."
            ),
            escalate=False,
            intent_type=intent_type,
            session_id=session_id,
            source_documents=source_docs,
            num_sources=len(source_docs),
            user_profile=inferred_profile,
            input_tokens=acc_input_tokens,
            output_tokens=acc_output_tokens,
            total_tokens=acc_total_tokens,
        )

    except LLMServiceError as e:
        logger.error(
            "LLM service error: request_id=%s, session_id=%s, error=%s",
            request_id,
            session_id,
            e,
        )
        raise
    except Exception as e:
        logger.exception(
            "Unexpected error in chat processing: request_id=%s, session_id=%s, error=%s",
            request_id,
            session_id,
            e,
        )
        raise


async def _on_buffer_window_expired(session_id: str, joined_message: str) -> None:
    """Callback when buffer window expires.

    Processes the joined message with the chatbot in the background
    and stores the response for polling by the client.
    """
    logger.info(
        "Buffer window expired for session %s: %d chars accumulated, "
        "processing in background",
        session_id,
        len(joined_message),
    )
    set_processing(session_id)
    try:
        response = await _process_chat_message(
            session_id=session_id,
            message=joined_message,
            llm_client=llm_client,
            s3_client=s3_client,
            file_inputs_client=file_inputs_client,
        )
        set_pending_chat_response(session_id, response.model_dump_json())
        logger.info(
            "Buffered message processed for session %s, response stored for polling",
            session_id,
        )
    except Exception as e:
        logger.exception(
            "Error processing buffered message for session %s: %s",
            session_id,
            e,
        )
        # Store a lightweight error response so the frontend does not hang
        # until the 60-second timeout; the user sees an error immediately.
        error_response = ChatResponse(
            response=(
                "Lo siento, ocurrió un error al procesar tu mensaje. "
                "Por favor, intenta de nuevo o contacta al equipo de ventas."
            ),
            escalate=False,
            intent_type="error_tool_failure",
            session_id=session_id,
            source_documents=[],
            num_sources=0,
            user_profile=None,
            input_tokens=0,
            output_tokens=0,
            total_tokens=0,
        )
        set_pending_chat_response(session_id, error_response.model_dump_json())
    finally:
        clear_processing(session_id)


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request: ChatRequest,
    api_key: Annotated[str, Depends(verify_api_key)],
    llm_client: Annotated[LLMClient, Depends(get_llm_client)],
    s3_client: Annotated[S3Client, Depends(get_s3_client)],
    file_inputs_client: Annotated[FileInputsClient, Depends(get_file_inputs_client)],
):
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

    # P4: Multi-message buffer — intercept before normal processing
    if settings.multi_message_buffer_enabled:
        current_count = get_buffer_count(session_id)

        if request.is_final or current_count >= 4:
            overflow_result = await add_to_buffer(session_id, request.message)
            joined = overflow_result or await flush_buffer(session_id)
            if joined:
                request = ChatRequest(
                    message=joined,
                    session_id=session_id,
                    is_final=request.is_final,
                )
        else:
            # Clear any stale pending response from a previous buffer window
            clear_pending_chat_response(session_id)
            clear_processing(session_id)
            await add_to_buffer(session_id, request.message)
            schedule_flush(
                session_id,
                settings.buffer_window_seconds,
                _on_buffer_window_expired,
            )
            return JSONResponse(
                status_code=202,
                content=BufferingResponse(
                    session_id=session_id,
                    poll_url=f"/buffer-result/{session_id}",
                ).model_dump(),
            )

    try:
        return await _process_chat_message(
            session_id=session_id,
            message=request.message,
            llm_client=llm_client,
            s3_client=s3_client,
            file_inputs_client=file_inputs_client,
            request_id=request_id,
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
            "Unexpected error in chat endpoint: request_id=%s, session_id=%s, error=%s",
            request_id,
            session_id,
            e,
        )
        raise HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
