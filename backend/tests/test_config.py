"""Unit tests for backend configuration fields.

Validates that Settings exposes runtime configuration fields with safe defaults.
"""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

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


class TestRuntimeCorsConfig:
    """Tests for deployment runtime URL and CORS settings."""

    def test_app_env_defaults_to_local(self) -> None:
        """app_env defaults to local to preserve developer ergonomics."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            assert settings.app_env == "local"

    def test_local_cors_origins_default_to_development_hosts(self) -> None:
        """Local config allows common frontend development origins."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            assert settings.allowed_cors_origins == [
                "http://localhost:3000",
                "http://localhost:5173",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:5173",
            ]

    def test_allowed_cors_origins_parse_comma_separated_env(self) -> None:
        """ALLOWED_CORS_ORIGINS accepts comma-separated origins from ECS env."""
        env = {
            "ALLOWED_CORS_ORIGINS": (
                "https://app.artesolutions.com.co, https://admin.artesolutions.com.co"
            )
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()
            assert settings.allowed_cors_origins == [
                "https://app.artesolutions.com.co",
                "https://admin.artesolutions.com.co",
            ]

    def test_public_runtime_urls_are_configurable(self) -> None:
        """Public API/frontend/admin URLs are read from environment."""
        env = {
            "PUBLIC_API_URL": "https://api.artesolutions.com.co",
            "PUBLIC_FRONTEND_URL": "https://app.artesolutions.com.co",
            "PUBLIC_ADMIN_URL": "https://admin.artesolutions.com.co",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()
            assert settings.public_api_url == "https://api.artesolutions.com.co"
            assert settings.public_frontend_url == "https://app.artesolutions.com.co"
            assert settings.public_admin_url == "https://admin.artesolutions.com.co"

    def test_production_requires_explicit_allowed_cors_origins(self) -> None:
        """Production fails fast instead of falling back to local origins."""
        with patch.dict(os.environ, {"APP_ENV": "production"}, clear=True):
            with pytest.raises(ValidationError, match="ALLOWED_CORS_ORIGINS"):
                Settings()

    def test_production_rejects_wildcard_cors_origin(self) -> None:
        """Production must not allow wildcard browser origins."""
        env = {"APP_ENV": "production", "ALLOWED_CORS_ORIGINS": "*"}
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValidationError, match="wildcard"):
                Settings()

    def test_production_accepts_explicit_cloudflare_origins(self) -> None:
        """Production accepts explicit frontend and admin Cloudflare origins."""
        env = {
            "APP_ENV": "production",
            "ALLOWED_CORS_ORIGINS": (
                "https://app.artesolutions.com.co,https://admin.artesolutions.com.co"
            ),
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()
            assert settings.allowed_cors_origins == [
                "https://app.artesolutions.com.co",
                "https://admin.artesolutions.com.co",
            ]
