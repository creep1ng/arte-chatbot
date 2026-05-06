"""Configuration module for the evaluation orchestrator.

Provides settings loaded from environment variables using Pydantic.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ORCHESTRATOR_DIR = Path(__file__).parent


class OrchestratorSettings(BaseSettings):
    """Settings for the evaluation orchestrator."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    api_base_url: str = Field(
        default="http://localhost:8000",
        description="Base URL of the ARTE Chatbot API",
    )
    dataset_path: Path = Field(
        default=_ORCHESTRATOR_DIR.parent / "dataset.json",
        description="Path to the unified evaluation dataset JSON file",
    )
    output_dir: Path = Field(
        default=_ORCHESTRATOR_DIR / "output",
        description="Directory to save evaluation results",
    )
    chat_api_key: str = Field(
        default="",
        description="API key for the /chat endpoint",
    )
    max_concurrent_requests: int = Field(
        default=10,
        description="Maximum number of concurrent requests to the /chat endpoint",
    )
    request_timeout: float = Field(
        default=30.0,
        description="Timeout for each request to the /chat endpoint in seconds",
    )


orchestrator_settings = OrchestratorSettings()