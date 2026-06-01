"""Centralized configuration module using Pydantic Settings.

Provides a singleton `settings` instance that loads and validates
all environment variables required by the backend application.

The `settings` proxy is lazy: it instantiates `Settings()` on first
attribute access, which ensures environment variables patched by tests
(via `patch.dict(os.environ, ...)`) are read at access time, not at
import time.
"""

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
    openai_timeout_seconds: float = Field(
        default=30.0,
        ge=1.0,
        le=120.0,
        description="Timeout for OpenAI API calls in seconds",
    )

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
    s3_connect_timeout_seconds: int = Field(
        default=5,
        ge=1,
        le=30,
        description="S3 connection timeout in seconds",
    )
    s3_read_timeout_seconds: int = Field(
        default=30,
        ge=1,
        le=120,
        description="S3 read timeout in seconds",
    )

    # Auth
    chat_api_key: Optional[str] = Field(
        default=None, description="API key for authenticating /chat endpoint clients"
    )
    admin_api_key: Optional[str] = Field(
        default=None, description="API key for authenticating /admin endpoint clients"
    )

    # App
    log_level: str = Field(default="INFO", description="Logging level")
    max_chat_message_chars: int = Field(
        default=4000,
        ge=1,
        le=20000,
        description="Maximum accepted characters in a chat message",
    )
    max_session_id_chars: int = Field(
        default=128,
        ge=36,
        le=256,
        description="Maximum accepted characters in a session identifier",
    )
    rate_limit_requests: int = Field(
        default=120,
        ge=1,
        le=10000,
        description="Maximum requests per principal in the rate limit window",
    )
    rate_limit_window_seconds: int = Field(
        default=60,
        ge=1,
        le=3600,
        description="Rate limit sliding window in seconds",
    )
    max_pdf_bytes: int = Field(
        default=10 * 1024 * 1024,
        ge=1024,
        description="Maximum allowed PDF size before File Inputs processing",
    )

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
    conversation_log_redaction_enabled: bool = Field(
        default=True,
        description="Redact sensitive values before persisting conversation logs",
    )
    git_commit_hash: str = Field(
        default="",
        description="Git commit hash for traceability in conversation logs",
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

    def reload(self) -> None:
        """Atomically reload settings from environment variables.

        Creates a new Settings() instance and swaps the internal reference.
        Concurrent reads are safe because Python reference assignment is
        atomic under the GIL; readers will see either the old or new
        instance, never a partially constructed one.
        """
        self._instance = Settings()

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
