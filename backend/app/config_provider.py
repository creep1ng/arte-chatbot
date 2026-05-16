"""ConfigProvider abstraction and environment-based implementation.

Provides a protocol/ABC for configuration access so that future
admin-panel-backed providers can be swapped in without changing
consumer code.
"""

from dataclasses import dataclass
from typing import Any, Optional, Protocol

from backend.app.config import Settings, settings


@dataclass
class ChannelProfile:
    """Simple channel profile with safe defaults."""

    name: str = "default"
    supports_html: bool = False
    max_message_length: int = 4096


class ConfigProvider(Protocol):
    """Protocol for configuration providers.

    Implementations may read from environment variables, Redis, or
    an admin panel backend.
    """

    def get(self, key: str) -> Any:
        """Return the raw value for a setting key, or None."""
        ...

    def get_label(self, name: str) -> str:
        """Resolve a semantic label name to its configured value.

        Supported names: ``bot``, ``escalated``, ``technical``.
        """
        ...

    def get_channel_profile(self, inbox_id: str) -> ChannelProfile:
        """Return the channel profile for the given inbox ID."""
        ...

    def get_handoff_target(self) -> Optional[int]:
        """Return the team ID to assign on human handoff, if any."""
        ...

    def is_chatwoot_enabled(self) -> bool:
        """Return whether the Chatwoot integration is active."""
        ...


class EnvConfigProvider:
    """ConfigProvider backed by the existing Pydantic Settings.

    Args:
        settings_obj: A ``Settings`` instance (or the lazy ``settings`` proxy).
            Defaults to the module-level ``settings`` singleton.
    """

    def __init__(self, settings_obj: Optional[Settings] = None) -> None:
        self._settings = settings_obj or settings

    def get(self, key: str) -> Any:
        """Return the attribute named *key* from Settings, or None."""
        return getattr(self._settings, key, None)

    def get_label(self, name: str) -> str:
        """Resolve label names using Settings fields."""
        mapping = {
            "bot": self._settings.chatwoot_bot_label,
            "escalated": self._settings.chatwoot_escalated_label,
            "technical": self._settings.chatwoot_technical_label,
        }
        return mapping.get(name, name)

    def get_channel_profile(self, inbox_id: str) -> ChannelProfile:
        """Return a default channel profile.

        Future implementations may lookup per-inbox overrides.
        """
        return ChannelProfile()

    def get_handoff_target(self) -> Optional[int]:
        """Return the configured handoff team ID."""
        return self._settings.chatwoot_handoff_team_id

    def is_chatwoot_enabled(self) -> bool:
        """Return whether Chatwoot integration is enabled."""
        return self._settings.chatwoot_enabled
