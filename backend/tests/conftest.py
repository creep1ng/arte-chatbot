"""Shared test configuration for backend tests.

Emits a warning if required environment variables are missing,
since FileInputsClient() is instantiated at module level in backend.main
and will raise FileUploadError without OPENAI_API_KEY.
"""

import os
from typing import Any, Optional

import pytest

from backend.app.schemas import LLMResponse


def make_llm_response(
    text: str = "",
    tool_calls: Optional[list[dict[str, Any]]] = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int = 0,
) -> LLMResponse:
    """Create an LLMResponse for test mocking.

    Helper to avoid repeating LLMResponse(...) with defaults in every test.
    Token defaults are 0 to match the model's Pydantic defaults.

    Args:
        text: The LLM output text.
        tool_calls: List of tool call dicts. Defaults to empty list.
        input_tokens: Input token count.
        output_tokens: Output token count.
        total_tokens: Total token count.

    Returns:
        An LLMResponse instance.
    """
    return LLMResponse(
        text=text,
        tool_calls=tool_calls or [],
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


@pytest.fixture
def llm_response_factory():
    """Pytest fixture that provides make_llm_response for dependency injection."""
    return make_llm_response


def pytest_configure(config):
    """Warn if required environment variables are not set before test collection."""
    missing = []
    for var in ("OPENAI_API_KEY", "CHAT_API_KEY"):
        if not os.environ.get(var):
            missing.append(var)

    if missing:
        import warnings as _warnings

        _warnings.warn(
            f"Missing environment variables: {', '.join(missing)}. "
            "Tests that import backend.main will fail during collection. "
            "Create a .env file (see .env.example) or export the variables before running tests.",
            stacklevel=1,
        )
