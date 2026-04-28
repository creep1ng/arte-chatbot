"""Configuration module for the evaluation harness.

Provides a singleton `harness_settings` instance that loads and validates
environment variables specific to the evaluation harness.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_HARNESS_DIR = Path(__file__).parent


class HarnessSettings(BaseSettings):
    """Evaluation harness settings loaded from environment variables.

    These settings are independent from the backend settings and
    specific to the evaluation workflow.
    """

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
        default=_HARNESS_DIR / "dataset.json",
        description="Path to the evaluation dataset JSON file",
    )
    output_dir: Path = Field(
        default=_HARNESS_DIR / "output",
        description="Directory to save evaluation results",
    )
    chat_api_key: str = Field(
        default="",
        description="API key for the /chat endpoint",
    )


harness_settings = HarnessSettings()
