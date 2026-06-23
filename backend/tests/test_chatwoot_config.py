"""Tests for Chatwoot configuration settings.

Validates Settings fields, defaults, env mapping, and the
model validator that warns when Chatwoot is enabled but misconfigured.
"""

import os
import warnings
from unittest.mock import patch

import pytest

from backend.app.config import Settings


class TestChatwootSettingsDefaults:
    """Settings must expose safe defaults when env vars are absent."""

    def test_chatwoot_enabled_defaults_false(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            assert settings.chatwoot_enabled is False

    def test_chatwoot_api_url_defaults_none(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            assert settings.chatwoot_api_url is None

    def test_chatwoot_agent_bot_token_defaults_none(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            assert settings.chatwoot_agent_bot_token is None

    def test_chatwoot_account_id_defaults_none(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            assert settings.chatwoot_account_id is None

    def test_chatwoot_inbox_id_defaults_none(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            assert settings.chatwoot_inbox_id is None

    def test_chatwoot_webhook_secret_defaults_none(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            assert settings.chatwoot_webhook_secret is None

    def test_chatwoot_handoff_team_id_defaults_none(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            assert settings.chatwoot_handoff_team_id is None

    def test_chatwoot_bot_label_defaults_bot(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            assert settings.chatwoot_bot_label == "bot"

    def test_chatwoot_escalated_label_defaults_escalated(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            assert settings.chatwoot_escalated_label == "escalated"

    def test_chatwoot_technical_label_defaults_technical(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            assert settings.chatwoot_technical_label == "technical"

    def test_chatwoot_secret_refs_default_none(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            assert settings.chatwoot_agent_bot_token_secret_ref is None
            assert settings.chatwoot_webhook_secret_ref is None


class TestChatwootSettingsFromEnv:
    """Settings must read Chatwoot values from environment."""

    def test_chatwoot_fields_from_env(self) -> None:
        env = {
            "CHATWOOT_ENABLED": "true",
            "CHATWOOT_API_URL": "https://chatwoot.example.com",
            "CHATWOOT_AGENT_BOT_TOKEN": "token123",
            "CHATWOOT_ACCOUNT_ID": "42",
            "CHATWOOT_INBOX_ID": "7",
            "CHATWOOT_WEBHOOK_SECRET": "secret",
            "CHATWOOT_HANDOFF_TEAM_ID": "3",
            "CHATWOOT_BOT_LABEL": "bot_label",
            "CHATWOOT_ESCALATED_LABEL": "esc_label",
            "CHATWOOT_TECHNICAL_LABEL": "tech_label",
            "CHATWOOT_QUOTE_LABEL": "quote_label",
            "CHATWOOT_ORDER_LABEL": "order_label",
            "CHATWOOT_AGENT_BOT_TOKEN_SECRET_REF": "/arte/prod/chatwoot-token",
            "CHATWOOT_WEBHOOK_SECRET_REF": "/arte/prod/chatwoot-webhook",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()
            assert settings.chatwoot_enabled is True
            assert settings.chatwoot_api_url == "https://chatwoot.example.com"
            assert settings.chatwoot_agent_bot_token == "token123"
            assert settings.chatwoot_account_id == 42
            assert settings.chatwoot_inbox_id == 7
            assert settings.chatwoot_webhook_secret == "secret"
            assert settings.chatwoot_handoff_team_id == 3
            assert settings.chatwoot_bot_label == "bot_label"
            assert settings.chatwoot_escalated_label == "esc_label"
            assert settings.chatwoot_technical_label == "tech_label"
            assert settings.chatwoot_quote_label == "quote_label"
            assert settings.chatwoot_order_label == "order_label"
            assert settings.chatwoot_agent_bot_token_secret_ref == (
                "/arte/prod/chatwoot-token"
            )
            assert settings.chatwoot_webhook_secret_ref == (
                "/arte/prod/chatwoot-webhook"
            )


class TestChatwootSettingsValidator:
    """The model validator must warn when Chatwoot is enabled but missing core config."""

    def test_chatwoot_enabled_warns_on_missing_required_fields(self) -> None:
        env = {"CHATWOOT_ENABLED": "true"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.warns(UserWarning, match="Chatwoot is enabled but"):
                Settings()

    def test_chatwoot_enabled_no_warning_when_fully_configured(self) -> None:
        env = {
            "CHATWOOT_ENABLED": "true",
            "CHATWOOT_API_URL": "https://chatwoot.example.com",
            "CHATWOOT_AGENT_BOT_TOKEN": "token",
            "CHATWOOT_ACCOUNT_ID": "1",
            "CHATWOOT_INBOX_ID": "1",
            "CHATWOOT_WEBHOOK_SECRET": "secret",
        }
        with patch.dict(os.environ, env, clear=True):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                Settings()
                chatwoot_warnings = [
                    warning
                    for warning in w
                    if issubclass(warning.category, UserWarning)
                    and "Chatwoot is enabled but" in str(warning.message)
                ]
                assert len(chatwoot_warnings) == 0

    def test_chatwoot_secret_refs_satisfy_required_secret_config(self) -> None:
        env = {
            "CHATWOOT_ENABLED": "true",
            "CHATWOOT_API_URL": "https://chatwoot.example.com",
            "CHATWOOT_AGENT_BOT_TOKEN_SECRET_REF": "/arte/prod/chatwoot-token",
            "CHATWOOT_ACCOUNT_ID": "1",
            "CHATWOOT_INBOX_ID": "1",
            "CHATWOOT_WEBHOOK_SECRET_REF": "/arte/prod/chatwoot-webhook",
        }
        with patch.dict(os.environ, env, clear=True):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                Settings()
                chatwoot_warnings = [
                    warning
                    for warning in w
                    if issubclass(warning.category, UserWarning)
                    and "Chatwoot is enabled but" in str(warning.message)
                ]
                assert len(chatwoot_warnings) == 0
