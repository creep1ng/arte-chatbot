"""Configuration settings for ARTE Chatbot Backend.

This module defines application-wide configuration using Pydantic v2's
BaseSettings, enabling automatic environment variable loading and validation.
All settings can be overridden via environment variables.
"""

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration settings loaded from environment variables.

    Attributes:
        max_agentic_iterations: Maximum number of iterations allowed for
            the agentic tool loop. Controls how many times the LLM can
            invoke tools in a single chat exchange before returning a final
            response. Defaults to 5.
        llm_model: The LLM model identifier to use for generating responses.
            Supports OpenAI model identifiers like 'gpt-4o-mini' or 'gpt-4'.
            Defaults to 'gpt-4o-mini'.
        log_level: Logging verbosity level. Accepts standard Python logging
            levels: 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'.
            Defaults to 'INFO'.
    """

    max_agentic_iterations: int = 5
    llm_model: str = "gpt-4o-mini"
    log_level: str = "INFO"

    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )
