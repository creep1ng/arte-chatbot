"""Centralized configuration module using Pydantic Settings.

Provides a singleton `settings` instance that loads and validates
all environment variables required by the backend application.

The `settings` proxy is lazy: it instantiates `Settings()` on first
attribute access, which ensures environment variables patched by tests
(via `patch.dict(os.environ, ...)`) are read at access time, not at
import time.
"""

from typing import Annotated, Any, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


LOCAL_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]


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
    app_env: str = Field(default="local", description="Runtime environment name")
    public_api_url: Optional[str] = Field(
        default=None, description="Public API URL published for deployed clients"
    )
    public_frontend_url: Optional[str] = Field(
        default=None, description="Public frontend URL allowed to call the API"
    )
    public_admin_url: Optional[str] = Field(
        default=None, description="Public admin URL allowed to call the API"
    )
    allowed_cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: LOCAL_CORS_ORIGINS.copy(),
        description="Comma-separated browser origins allowed by CORS",
    )
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

    @field_validator("app_env", mode="before")
    @classmethod
    def _normalize_app_env(cls, value: str) -> str:
        """Normalize app_env for simple production checks."""
        return str(value).strip().lower()

    @field_validator("allowed_cors_origins", mode="before")
    @classmethod
    def _parse_allowed_cors_origins(cls, value: Any) -> list[str]:
        """Parse comma-separated CORS origins from environment."""
        if value is None:
            return LOCAL_CORS_ORIGINS.copy()
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        if isinstance(value, list):
            return [str(origin).strip() for origin in value if str(origin).strip()]
        return value

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
            raise ValueError(
                f"Invalid IANA timezone: {self.greeting_timezone}"
            )
        return self

    @model_validator(mode="after")
    def _validate_production_cors_origins(self) -> "Settings":
        """Require explicit non-wildcard CORS origins in production."""
        is_production = self.app_env in {"prod", "production"}
        if not is_production:
            return self

        has_default_origins = self.allowed_cors_origins == LOCAL_CORS_ORIGINS
        if not self.allowed_cors_origins or has_default_origins:
            raise ValueError(
                "ALLOWED_CORS_ORIGINS must be explicitly configured in production"
            )

        if "*" in self.allowed_cors_origins:
            raise ValueError("CORS wildcard origins are forbidden in production")

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
