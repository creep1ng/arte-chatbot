"""Channel profile model for per-inbox Chatwoot configuration.

Each inbox can be configured with its own behavior: buffer window,
message formatting, tool calling, and prompt suffixes.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class ChannelProfile(BaseModel):
    """Per-inbox channel configuration profile.

    Attributes:
        inbox_id: The Chatwoot inbox identifier.
        channel_type: Communication channel (whatsapp, web, email, api).
        system_prompt_suffix: Optional text appended to the system prompt.
        message_formatter: Output formatting style (compact, standard, verbose).
        buffer_window_seconds: Debounce window for incoming messages (1–60s).
        enable_tool_calling: Whether the LLM may invoke tools for this channel.
        max_turns: Maximum conversation turns to keep in context.
        custom_attributes: Free-form key-value attributes for extensibility.
    """

    inbox_id: str
    channel_type: Literal["whatsapp", "web", "email", "api"] = "web"
    system_prompt_suffix: Optional[str] = None
    message_formatter: Literal["compact", "standard", "verbose"] = "standard"
    buffer_window_seconds: int = 5
    enable_tool_calling: bool = True
    max_turns: int = 20
    custom_attributes: dict[str, str] = Field(default_factory=dict)

    @field_validator("buffer_window_seconds")
    @classmethod
    def _validate_buffer_window(cls, value: int) -> int:
        if value <= 0 or value > 60:
            raise ValueError("buffer_window_seconds must be > 0 and <= 60")
        return value

    def apply_to_system_prompt(self, base_prompt: str) -> str:
        """Append the configured suffix to *base_prompt*, if any.

        Args:
            base_prompt: The original system prompt text.

        Returns:
            The prompt with suffix appended when present and non-empty.
        """
        if self.system_prompt_suffix:
            return f"{base_prompt}\n\n{self.system_prompt_suffix}"
        return base_prompt


def get_default_channel_profile() -> ChannelProfile:
    """Return a default channel profile with sensible defaults.

    Returns:
        A ``ChannelProfile`` instance with inbox_id="default".
    """
    return ChannelProfile(inbox_id="default")
