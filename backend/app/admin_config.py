"""Admin configuration endpoints with safe secret redaction."""

import os
from typing import Annotated, Any

from fastapi import APIRouter, Depends

from backend.app.admin_auth import verify_admin_key
from backend.app.admin_schemas import (
    CurrentSettingsSnapshot,
    ImmutableSettings,
    MutableSettings,
)
from backend.app.config import settings

config_router = APIRouter()
REDACTED = "***REDACTED***"

MUTABLE_ENV_NAMES = {
    "llm_model": "LLM_MODEL",
    "log_level": "LOG_LEVEL",
    "escalation_confidence_threshold": "ESCALATION_CONFIDENCE_THRESHOLD",
    "false_positive_limit": "FALSE_POSITIVE_LIMIT",
    "false_negative_limit": "FALSE_NEGATIVE_LIMIT",
    "whatsapp_formatter_enabled": "WHATSAPP_FORMATTER_ENABLED",
    "split_messages_enabled": "SPLIT_MESSAGES_ENABLED",
    "msg_delay_min_ms": "MSG_DELAY_MIN_MS",
    "msg_delay_max_ms": "MSG_DELAY_MAX_MS",
    "greeting_enabled": "GREETING_ENABLED",
    "greeting_timezone": "GREETING_TIMEZONE",
    "multi_message_buffer_enabled": "MULTI_MESSAGE_BUFFER_ENABLED",
    "buffer_window_seconds": "BUFFER_WINDOW_SECONDS",
    "conversation_logging_enabled": "CONVERSATION_LOGGING_ENABLED",
    "conversation_log_prefix": "CONVERSATION_LOG_PREFIX",
    "admin_api_key": "ADMIN_API_KEY",
}
SECRET_FIELDS = {
    "admin_api_key",
    "openai_api_key",
    "aws_access_key_id",
    "aws_secret_access_key",
    "chat_api_key",
}


def _redact(value: str | None) -> str | None:
    """Redact a configured secret while preserving missing values as None."""
    if value is None or value == "":
        return None
    return REDACTED


def _env_value(value: Any) -> str:
    """Serialize a Pydantic setting value into an environment variable string."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _is_redacted_secret_update(value: Any) -> bool:
    """Return whether an incoming update is only the redacted placeholder.

    Admin config responses intentionally redact secrets before sending them to
    the browser. If the browser submits a full form payload back unchanged, the
    redacted placeholder MUST NOT overwrite the real runtime secret.
    """
    return isinstance(value, str) and value == REDACTED


def _current_settings_snapshot() -> CurrentSettingsSnapshot:
    """Build a settings snapshot with all sensitive values redacted.

    Runtime persistence for Slice 3 is process-local via ``os.environ`` followed
    by ``settings.reload()``. It intentionally does not rewrite .env or any
    external secret store; container restarts still require real env config.
    """
    mutable_values = {field: getattr(settings, field) for field in MUTABLE_ENV_NAMES}
    if mutable_values.get("admin_api_key"):
        mutable_values["admin_api_key"] = REDACTED

    immutable = ImmutableSettings(
        openai_api_key=_redact(settings.openai_api_key),
        aws_access_key_id=_redact(settings.aws_access_key_id),
        aws_secret_access_key=_redact(settings.aws_secret_access_key),
        aws_bucket_name=settings.aws_bucket_name,
        aws_region=settings.aws_region,
        chat_api_key=_redact(settings.chat_api_key),
        git_commit_hash=settings.git_commit_hash,
    )
    return CurrentSettingsSnapshot(
        mutable=MutableSettings(**mutable_values),
        immutable=immutable,
    )


@config_router.get("/config", response_model=CurrentSettingsSnapshot)
async def get_config(
    _admin_key: Annotated[str, Depends(verify_admin_key)],
) -> CurrentSettingsSnapshot:
    """Return current mutable and immutable backend settings."""
    return _current_settings_snapshot()


@config_router.put("/config", response_model=CurrentSettingsSnapshot)
async def put_config(
    data: MutableSettings,
    _admin_key: Annotated[str, Depends(verify_admin_key)],
) -> CurrentSettingsSnapshot:
    """Update mutable settings and hot-reload the settings proxy.

    Args:
        data: Partial mutable settings payload. Unset fields are ignored.

    Returns:
        Redacted current settings snapshot after reload.
    """
    updates = data.model_dump(exclude_unset=True)
    for field_name, value in updates.items():
        if value is None:
            continue
        if field_name in SECRET_FIELDS and _is_redacted_secret_update(value):
            continue
        env_name = MUTABLE_ENV_NAMES[field_name]
        os.environ[env_name] = _env_value(value)

    settings.reload()
    return _current_settings_snapshot()
