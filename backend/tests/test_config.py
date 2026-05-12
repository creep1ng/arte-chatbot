"""Unit tests for conversation logging config fields.

Validates that Settings exposes the new conversation logging fields
with correct defaults.
"""

import os
from unittest.mock import patch

from backend.app.config import Settings


class TestConversationLoggingConfig:
    """Tests for conversation logging settings."""

    def test_conversation_logging_enabled_defaults_false(self) -> None:
        """conversation_logging_enabled must default to False (safe rollout)."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            assert settings.conversation_logging_enabled is False

    def test_conversation_log_prefix_defaults_to_conversations(self) -> None:
        """conversation_log_prefix must default to 'conversations'."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            assert settings.conversation_log_prefix == "conversations"

    def test_git_commit_hash_defaults_to_empty_string(self) -> None:
        """git_commit_hash must default to empty string."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            assert settings.git_commit_hash == ""

    def test_conversation_logging_enabled_from_env(self) -> None:
        """conversation_logging_enabled can be set via env var."""
        env = {"CONVERSATION_LOGGING_ENABLED": "true"}
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()
            assert settings.conversation_logging_enabled is True

    def test_conversation_log_prefix_from_env(self) -> None:
        """conversation_log_prefix can be overridden via env var."""
        env = {"CONVERSATION_LOG_PREFIX": "audit_logs"}
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()
            assert settings.conversation_log_prefix == "audit_logs"

    def test_git_commit_hash_from_env(self) -> None:
        """git_commit_hash can be set via env var for traceability."""
        env = {"GIT_COMMIT_HASH": "abc1234"}
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()
            assert settings.git_commit_hash == "abc1234"
