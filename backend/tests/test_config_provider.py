"""Tests for ConfigProvider protocol and EnvConfigProvider implementation.

Validates that EnvConfigProvider correctly delegates to Settings and
provides sensible defaults for labels, channel profiles, and handoff.
"""

import os
from unittest.mock import patch

from backend.app.config import Settings
from backend.app.channel_profile import ChannelProfile
from backend.app.config_provider import ConfigProvider, EnvConfigProvider


class TestChannelProfile:
    """ChannelProfile must expose safe defaults."""

    def test_defaults(self) -> None:
        profile = ChannelProfile(inbox_id="1")
        assert profile.inbox_id == "1"
        assert profile.channel_type == "web"
        assert profile.buffer_window_seconds == 5
        assert profile.enable_tool_calling is True
        assert profile.max_turns == 20


class TestEnvConfigProvider:
    """EnvConfigProvider must resolve values from Settings."""

    def test_get_returns_setting_value(self) -> None:
        settings = Settings()
        provider = EnvConfigProvider(settings)
        assert provider.get("escalation_confidence_threshold") == 0.4

    def test_get_missing_key_returns_none(self) -> None:
        settings = Settings()
        provider = EnvConfigProvider(settings)
        assert provider.get("nonexistent_key") is None

    def test_get_label_bot(self) -> None:
        settings = Settings()
        provider = EnvConfigProvider(settings)
        assert provider.get_label("bot") == "bot"

    def test_get_label_escalated(self) -> None:
        settings = Settings()
        provider = EnvConfigProvider(settings)
        assert provider.get_label("escalated") == "escalated"

    def test_get_label_technical(self) -> None:
        settings = Settings()
        provider = EnvConfigProvider(settings)
        assert provider.get_label("technical") == "technical"

    def test_get_label_unknown_returns_name(self) -> None:
        settings = Settings()
        provider = EnvConfigProvider(settings)
        assert provider.get_label("unknown") == "unknown"

    def test_get_channel_profile_returns_default(self) -> None:
        settings = Settings()
        provider = EnvConfigProvider(settings)
        profile = provider.get_channel_profile("1")
        assert isinstance(profile, ChannelProfile)
        assert profile.inbox_id == "default"
        assert profile.channel_type == "web"

    def test_get_handoff_target_defaults_none(self) -> None:
        settings = Settings()
        provider = EnvConfigProvider(settings)
        assert provider.get_handoff_target() is None

    def test_get_handoff_target_from_env(self) -> None:
        env = {"CHATWOOT_HANDOFF_TEAM_ID": "5"}
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()
            provider = EnvConfigProvider(settings)
            assert provider.get_handoff_target() == 5

    def test_is_chatwoot_enabled_defaults_false(self) -> None:
        settings = Settings()
        provider = EnvConfigProvider(settings)
        assert provider.is_chatwoot_enabled() is False

    def test_is_chatwoot_enabled_true(self) -> None:
        env = {"CHATWOOT_ENABLED": "true"}
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()
            provider = EnvConfigProvider(settings)
            assert provider.is_chatwoot_enabled() is True


class TestConfigProviderProtocol:
    """EnvConfigProvider must satisfy the ConfigProvider protocol."""

    def test_is_instance_of_protocol(self) -> None:
        provider: ConfigProvider = EnvConfigProvider(Settings())
        assert provider.is_chatwoot_enabled() is False
