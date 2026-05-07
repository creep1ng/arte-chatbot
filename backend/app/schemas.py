from typing import Any, Optional

from pydantic import BaseModel, Field


class LLMResponse(BaseModel):
    """Unified response model for all LLM client methods.

    Attributes:
        text: The LLM output text.
        tool_calls: List of tool call dicts from the LLM response.
        input_tokens: Number of input tokens used.
        output_tokens: Number of output tokens generated.
        total_tokens: Total tokens consumed (input + output).
    """

    text: str = ""
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class SourceDocument(BaseModel):
    ruta: str
    contenido_relevante: Optional[str] = None
