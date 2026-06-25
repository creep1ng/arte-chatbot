"""Tests for ConfigProvider dependency injection in backend/main.py.

Validates that the ``get_config_provider`` dependency returns an
``EnvConfigProvider`` wired to the application settings.
"""

from backend.app.config_provider import EnvConfigProvider
from backend.main import get_config_provider


class TestGetConfigProvider:
    """``get_config_provider`` must expose the EnvConfigProvider singleton."""

    def test_returns_env_config_provider(self) -> None:
        provider = get_config_provider()
        assert isinstance(provider, EnvConfigProvider)

    def test_provider_reads_settings(self) -> None:
        provider = get_config_provider()
        assert provider.is_chatwoot_enabled() is False
