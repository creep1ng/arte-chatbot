"""Centralized configuration module using Pydantic Settings.

Provides a singleton `settings` instance that loads and validates
all environment variables required by the backend application.

The `settings` proxy is lazy: it instantiates `Settings()` on first
attribute access, which ensures environment variables patched by tests
(via `patch.dict(os.environ, ...)`) are read at access time, not at
import time.
"""

from typing import Any, Optional

from pydantic import Field
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


class _SettingsProxy:
    """Lazy proxy that defers Settings() instantiation to first attribute access.

    This ensures that environment variables set via patch.dict(os.environ, ...)
    in tests are available when Settings() is instantiated, since the
    instantiation happens at access time rather than at import time.
    """

    _instance: Optional[Settings] = None

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
