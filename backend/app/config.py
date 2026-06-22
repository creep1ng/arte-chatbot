"""Centralized configuration module using Pydantic Settings.

Provides a singleton `settings` instance that loads and validates
all environment variables required by the backend application.

The `settings` proxy is lazy: it instantiates `Settings()` on first
attribute access, which ensures environment variables patched by tests
(via `patch.dict(os.environ, ...)`) are read at access time, not at
import time.
"""

import os
import warnings
from typing import Annotated, Any, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


LOCAL_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]


def _env_flag_enabled(name: str) -> bool:
    """Return whether a boolean-like environment flag is enabled."""
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _settings_env_file() -> Optional[str]:
    """Return the dotenv path unless tests explicitly disable dotenv loading."""
    if _env_flag_enabled("ARTE_CHATBOT_DISABLE_DOTENV"):
        return None
    return ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Pydantic Settings automatically reads from:
    1. Environment variables (highest priority)
    2. .env file (if configured)

    Sensitive fields default to None. Clients that require them
    validate at runtime and raise descriptive errors if missing.
    """

    model_config = SettingsConfigDict(
        env_file=_settings_env_file(),
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

    # Lambda/serverless state
    state_backend: str = Field(
        default="memory",
        description="State backend to use: memory or dynamodb",
    )
    dynamodb_state_table_name: Optional[str] = Field(
        default=None,
        description="DynamoDB table name for durable chatbot state",
    )
    dynamodb_state_key_prefix: str = Field(
        default="",
        description="Optional key prefix for staging/prod state isolation",
    )
    session_ttl_seconds: int = Field(
        default=30 * 24 * 60 * 60,
        ge=60,
        description="TTL for persisted session items in seconds",
    )
    buffer_ttl_seconds: int = Field(
        default=24 * 60 * 60,
        ge=60,
        description="TTL for persisted buffer items in seconds",
    )
    rate_limit_ttl_seconds: int = Field(
        default=24 * 60 * 60,
        ge=60,
        description="TTL for shared rate-limit counter items in seconds",
    )
    lambda_timeout_seconds: int = Field(
        default=25,
        ge=1,
        le=900,
        description="Configured Lambda timeout budget in seconds",
    )

    # Runtime secret references for Lambda/Terraform wiring.
    openai_api_key_secret_ref: Optional[str] = Field(
        default=None,
        description="SSM/Secrets Manager reference for OPENAI_API_KEY",
    )
    chat_api_key_secret_ref: Optional[str] = Field(
        default=None,
        description="SSM/Secrets Manager reference for CHAT_API_KEY",
    )
    chatwoot_agent_bot_token_secret_ref: Optional[str] = Field(
        default=None,
        description="SSM/Secrets Manager reference for CHATWOOT_AGENT_BOT_TOKEN",
    )
    chatwoot_webhook_secret_ref: Optional[str] = Field(
        default=None,
        description="SSM/Secrets Manager reference for CHATWOOT_WEBHOOK_SECRET",
    )

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
        description="AgentBot access token from Chatwoot for local development",
    )
    chatwoot_account_id: Optional[int] = Field(
        default=None,
        description="Numeric Chatwoot account ID",
    )
    chatwoot_inbox_id: Optional[int] = Field(
        default=None,
        description="Numeric Chatwoot inbox ID for WhatsApp",
    )
    chatwoot_webhook_secret: Optional[str] = Field(
        default=None,
        description="Chatwoot webhook HMAC secret for local development",
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
    chatwoot_quote_label: str = Field(
        default="quote",
        description="Label for quote conversations",
    )
    chatwoot_order_label: str = Field(
        default="order",
        description="Label for order conversations",
    )

    @field_validator("app_env", mode="before")
    @classmethod
    def _normalize_app_env(cls, value: str) -> str:
        """Normalize app_env for simple production checks."""
        return str(value).strip().lower()

    @field_validator("state_backend", mode="before")
    @classmethod
    def _normalize_state_backend(cls, value: str) -> str:
        """Normalize the state backend selector."""
        return str(value).strip().lower()

    @field_validator("dynamodb_state_key_prefix", mode="before")
    @classmethod
    def _normalize_state_key_prefix(cls, value: str) -> str:
        """Avoid accidental duplicate separators in DynamoDB partition keys."""
        return str(value or "").strip().strip("#")

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

    @field_validator(
        "chatwoot_account_id",
        "chatwoot_inbox_id",
        "chatwoot_handoff_team_id",
        mode="before",
    )
    @classmethod
    def _parse_optional_int(cls, value: Any) -> Any:
        """Treat empty optional integer settings as not configured."""
        if value == "":
            return None
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
    def _validate_state_backend(self) -> "Settings":
        """Validate state backend specific configuration."""
        if self.state_backend not in {"memory", "dynamodb"}:
            raise ValueError("STATE_BACKEND must be 'memory' or 'dynamodb'")
        if self.state_backend == "dynamodb" and not self.dynamodb_state_table_name:
            raise ValueError(
                "DYNAMODB_STATE_TABLE_NAME is required when STATE_BACKEND=dynamodb"
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
        if not (
            self.chatwoot_agent_bot_token or self.chatwoot_agent_bot_token_secret_ref
        ):
            missing.append(
                "CHATWOOT_AGENT_BOT_TOKEN or CHATWOOT_AGENT_BOT_TOKEN_SECRET_REF"
            )
        if self.chatwoot_account_id is None:
            missing.append("CHATWOOT_ACCOUNT_ID")
        if self.chatwoot_inbox_id is None:
            missing.append("CHATWOOT_INBOX_ID")
        if not (self.chatwoot_webhook_secret or self.chatwoot_webhook_secret_ref):
            missing.append("CHATWOOT_WEBHOOK_SECRET or CHATWOOT_WEBHOOK_SECRET_REF")

        if missing:
            warnings.warn(
                "Chatwoot is enabled but the following required settings are missing: "
                + ", ".join(missing),
                UserWarning,
                stacklevel=2,
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
