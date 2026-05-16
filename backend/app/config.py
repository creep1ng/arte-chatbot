"""Centralized configuration module using Pydantic Settings.

Provides a singleton `settings` instance that loads and validates
all environment variables required by the backend application.

The `settings` proxy is lazy: it instantiates `Settings()` on first
attribute access, which ensures environment variables patched by tests
(via `patch.dict(os.environ, ...)`) are read at access time, not at
import time.
"""

import warnings
from typing import Any, Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Pydantic Settings automatically reads from:
    1. Environment variables (highest priority)
    2. .env file (if configured)

    Sensitive fields default to None. Clients that require them
    validate at runtime and raise descriptive errors if missing.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # OpenAI
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")
    llm_model: str = Field(default="gpt-5.4-nano", description="LLM model identifier")

    # AWS
    aws_access_key_id: Optional[str] = Field(
        default=None, description="AWS access key ID"
    )
    aws_secret_access_key: Optional[str] = Field(
        default=None, description="AWS secret access key"
    )
    aws_bucket_name: str = Field(
        default="arte-chatbot-fichas-tecnicas",
        description="S3 bucket name for technical datasheets",
    )
    aws_region: str = Field(default="us-east-1", description="AWS region")

    # Auth
    chat_api_key: Optional[str] = Field(
        default=None, description="API key for authenticating /chat endpoint clients"
    )

    # App
    log_level: str = Field(default="INFO", description="Logging level")

    # Escalation thresholds
    escalation_confidence_threshold: float = Field(
        default=0.4,
        description="Minimum confidence to trust LLM intent classification",
    )
    false_positive_limit: float = Field(
        default=0.15,
        description="Maximum acceptable false positive rate (15%)",
    )
    false_negative_limit: float = Field(
        default=0.10,
        description="Maximum acceptable false negative rate (10%)",
    )

    # WhatsApp — Formatting (P1)
    whatsapp_formatter_enabled: bool = Field(
        default=False,
        description="Enable WhatsApp markdown-to-native formatting filter",
    )

    # WhatsApp — Conversational Splitting (P2)
    split_messages_enabled: bool = Field(
        default=False,
        description="Enable enviar_mensajes tool for conversational splitting",
    )
    msg_delay_min_ms: int = Field(
        default=3000,
        ge=1000,
        le=10000,
        description="Minimum delay between split messages in milliseconds",
    )
    msg_delay_max_ms: int = Field(
        default=5000,
        ge=1000,
        le=15000,
        description="Maximum delay between split messages in milliseconds",
    )

    # WhatsApp — Greeting (P3)
    greeting_enabled: bool = Field(
        default=False,
        description="Enable first-contact greeting",
    )
    greeting_timezone: str = Field(
        default="America/Bogota",
        description="IANA timezone for time-of-day greeting",
    )

    # WhatsApp — Multi-Message Buffer (P4)
    multi_message_buffer_enabled: bool = Field(
        default=False,
        description="Enable multi-message input buffering",
    )
    buffer_window_seconds: int = Field(
        default=5,
        ge=1,
        le=15,
        description="Buffer window in seconds for multi-message accumulation",
    )

    # Conversation Logging
    conversation_logging_enabled: bool = Field(
        default=False,
        description="Enable async conversation logging to S3",
    )
    conversation_log_prefix: str = Field(
        default="conversations",
        description="S3 key prefix for conversation log files",
    )
    git_commit_hash: str = Field(
        default="",
        description="Git commit hash for traceability in conversation logs",
    )

    # Chatwoot
    chatwoot_enabled: bool = Field(
        default=False,
        description="Enable Chatwoot integration",
    )
    chatwoot_api_url: Optional[str] = Field(
        default=None,
        description="URL of the Chatwoot instance (no trailing slash)",
    )
    chatwoot_agent_bot_token: Optional[str] = Field(
        default=None,
        description="AgentBot access token from Chatwoot",
    )
    chatwoot_account_id: Optional[int] = Field(
        default=None,
        description="Numeric account ID",
    )
    chatwoot_inbox_id: Optional[int] = Field(
        default=None,
        description="Numeric inbox ID for WhatsApp",
    )
    chatwoot_webhook_secret: Optional[str] = Field(
        default=None,
        description="Webhook secret for HMAC signature verification",
    )
    chatwoot_handoff_team_id: Optional[int] = Field(
        default=None,
        description="Team ID for human escalation handoff",
    )
    chatwoot_bot_label: str = Field(
        default="bot",
        description="Label assigned by the bot",
    )
    chatwoot_escalated_label: str = Field(
        default="escalated",
        description="Label for escalated conversations",
    )
    chatwoot_technical_label: str = Field(
        default="technical",
        description="Label for technical conversations",
    )

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )
    redis_password: Optional[str] = Field(
        default=None,
        description="Redis password",
    )

    @model_validator(mode="after")
    def _validate_delay_bounds(self) -> "Settings":
        """Ensure msg_delay_min_ms <= msg_delay_max_ms."""
        if self.msg_delay_min_ms > self.msg_delay_max_ms:
            raise ValueError(
                f"msg_delay_min_ms ({self.msg_delay_min_ms}) must be <= "
                f"msg_delay_max_ms ({self.msg_delay_max_ms})"
            )
        return self

    @model_validator(mode="after")
    def _validate_greeting_timezone(self) -> "Settings":
        """Ensure greeting_timezone is a valid IANA timezone."""
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(self.greeting_timezone)
        except (KeyError, ZoneInfoNotFoundError):
            raise ValueError(f"Invalid IANA timezone: {self.greeting_timezone}")
        return self

    @model_validator(mode="after")
    def _validate_chatwoot_config(self) -> "Settings":
        """Warn if Chatwoot is enabled but required fields are missing."""
        if not self.chatwoot_enabled:
            return self

        missing: list[str] = []
        if not self.chatwoot_api_url:
            missing.append("CHATWOOT_API_URL")
        if not self.chatwoot_agent_bot_token:
            missing.append("CHATWOOT_AGENT_BOT_TOKEN")
        if self.chatwoot_account_id is None:
            missing.append("CHATWOOT_ACCOUNT_ID")
        if self.chatwoot_inbox_id is None:
            missing.append("CHATWOOT_INBOX_ID")
        if not self.chatwoot_webhook_secret:
            missing.append("CHATWOOT_WEBHOOK_SECRET")

        if missing:
            warnings.warn(
                f"Chatwoot is enabled but the following required settings are missing: {', '.join(missing)}",
                UserWarning,
                stacklevel=2,
            )

        return self


class _SettingsProxy:
    """Lazy proxy that defers Settings() instantiation to first attribute access.

    This ensures that environment variables set via patch.dict(os.environ, ...)
    in tests are available when Settings() is instantiated, since the
    instantiation happens at access time rather than at import time.
    """

    _instance: Optional[Settings] = None

    def reset(self) -> None:
        """Invalidate the cached Settings instance.

        Call this in test fixtures when environment variables have been
        patched (e.g., via monkeypatch.setenv) so that the next attribute
        access creates a fresh Settings() that reads the updated env.
        """
        self._instance = None

    def _ensure_instance(self) -> Settings:
        if self._instance is None:
            self._instance = Settings()
        return self._instance

    def __getattr__(self, name: str) -> Any:
        return getattr(self._ensure_instance(), name)

    def __dir__(self) -> list[str]:
        return dir(self._ensure_instance())

    def __repr__(self) -> str:
        return repr(self._ensure_instance())


settings = _SettingsProxy()
