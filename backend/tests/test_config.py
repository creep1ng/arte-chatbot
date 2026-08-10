"""Unit tests for backend configuration fields.

Validates that Settings exposes runtime configuration fields with safe defaults.
"""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from backend.app.config import Settings
from backend.app.context_budget_config import ContextBudgetConfig


class TestDotenvIsolationConfig:
    """Tests for deterministic pytest configuration loading."""

    def test_disable_dotenv_ignores_local_env_file(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """ARTE_CHATBOT_DISABLE_DOTENV makes Settings ignore local `.env`."""
        (tmp_path / ".env").write_text("LOG_LEVEL=DEBUG\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ARTE_CHATBOT_DISABLE_DOTENV", "1")
        monkeypatch.delenv("LOG_LEVEL", raising=False)

        assert Settings().log_level == "INFO"


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


class TestContextBudgetConfig:
    """Tests for preliminary model-aware context budget settings."""

    def test_context_budget_preliminary_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()

        assert settings.context_budget_ratio == 0.10
        assert settings.context_hard_cap_tokens == 32_000
        assert settings.llm_max_output_tokens == 2_000
        assert settings.context_output_reserve_tokens == 2_000
        assert settings.context_non_history_reserve_tokens == 12_000
        assert settings.context_file_input_max_bytes == 5 * 1024 * 1024
        assert settings.context_max_turns == 20

    def test_context_budget_fields_are_configurable(self) -> None:
        env = {
            "CONTEXT_BUDGET_RATIO": "0.2",
            "CONTEXT_HARD_CAP_TOKENS": "64000",
            "LLM_MAX_OUTPUT_TOKENS": "4000",
            "CONTEXT_OUTPUT_RESERVE_TOKENS": "5000",
            "CONTEXT_NON_HISTORY_RESERVE_TOKENS": "16000",
            "CONTEXT_FILE_INPUT_MAX_BYTES": "4194304",
            "CONTEXT_MAX_TURNS": "12",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()

        assert settings.context_budget_ratio == 0.2
        assert settings.context_hard_cap_tokens == 64_000
        assert settings.llm_max_output_tokens == 4_000
        assert settings.context_output_reserve_tokens == 5_000
        assert settings.context_non_history_reserve_tokens == 16_000
        assert settings.context_file_input_max_bytes == 4_194_304
        assert settings.context_max_turns == 12

    def test_output_reserve_must_be_below_hard_cap(self) -> None:
        env = {
            "CONTEXT_HARD_CAP_TOKENS": "2000",
            "CONTEXT_OUTPUT_RESERVE_TOKENS": "2000",
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValidationError, match="CONTEXT_OUTPUT_RESERVE_TOKENS"):
                Settings()

    def test_max_output_must_fit_reserved_output_budget(self) -> None:
        env = {
            "LLM_MAX_OUTPUT_TOKENS": "2001",
            "CONTEXT_OUTPUT_RESERVE_TOKENS": "2000",
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValidationError, match="LLM_MAX_OUTPUT_TOKENS"):
                Settings()

    def test_output_reserve_respects_known_model_capability(self) -> None:
        env = {
            "LLM_MODEL": "gpt-5.4-nano",
            "CONTEXT_HARD_CAP_TOKENS": "200000",
            "LLM_MAX_OUTPUT_TOKENS": "128001",
            "CONTEXT_OUTPUT_RESERVE_TOKENS": "128001",
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValidationError, match="registered model output"):
                Settings()

    def test_file_input_byte_cap_cannot_exceed_upload_cap(self) -> None:
        env = {
            "MAX_PDF_BYTES": "1048576",
            "CONTEXT_FILE_INPUT_MAX_BYTES": "1048577",
        }
        with patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValidationError, match="CONTEXT_FILE_INPUT_MAX_BYTES"):
                Settings()

    def test_context_budget_config_uses_validated_runtime_values(self) -> None:
        env = {
            "CONTEXT_BUDGET_RATIO": "0.25",
            "CONTEXT_HARD_CAP_TOKENS": "48000",
            "CONTEXT_OUTPUT_RESERVE_TOKENS": "3000",
            "CONTEXT_NON_HISTORY_RESERVE_TOKENS": "9000",
            "CONTEXT_MAX_TURNS": "8",
        }
        with patch.dict(os.environ, env, clear=True):
            config = Settings().context_budget_config()

        assert config == ContextBudgetConfig(
            ratio=0.25,
            hard_cap_tokens=48_000,
            output_reserve_tokens=3_000,
            non_history_reserve_tokens=9_000,
            max_turns=8,
        )


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


class TestServerlessStateConfig:
    """Tests for Lambda state and secret reference settings."""

    def test_state_backend_defaults_to_memory(self) -> None:
        """Local execution keeps the existing in-memory behavior by default."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            assert settings.state_backend == "memory"

    def test_processing_lease_defaults_to_sixty_seconds(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            assert Settings().buffer_processing_lease_seconds == 60

    def test_processing_lease_rejects_non_positive_duration(self) -> None:
        with patch.dict(
            os.environ, {"BUFFER_PROCESSING_LEASE_SECONDS": "0"}, clear=True
        ):
            with pytest.raises(ValidationError):
                Settings()

    def test_request_deadline_defaults_preserve_positive_work_budget(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
        assert (
            settings.request_response_safety_seconds,
            settings.request_cleanup_reserve_seconds,
            settings.request_min_operation_margin_seconds,
        ) == (2.0, 3.0, 1.0)

    @pytest.mark.parametrize(
        "name",
        [
            "REQUEST_RESPONSE_SAFETY_SECONDS",
            "REQUEST_CLEANUP_RESERVE_SECONDS",
            "REQUEST_MIN_OPERATION_MARGIN_SECONDS",
        ],
    )
    def test_request_deadline_reserves_must_be_positive(self, name: str) -> None:
        with pytest.raises(ValidationError):
            Settings(**{name.lower(): 0})

    def test_lambda_budget_must_exceed_all_request_reserves(self) -> None:
        with pytest.raises(ValidationError, match="LAMBDA_TIMEOUT_SECONDS"):
            Settings(
                lambda_timeout_seconds=6,
                request_response_safety_seconds=2,
                request_cleanup_reserve_seconds=3,
                request_min_operation_margin_seconds=1,
            )

    def test_dynamodb_state_backend_requires_table_name(self) -> None:
        """DynamoDB state must fail fast when the table name is missing."""
        with patch.dict(os.environ, {"STATE_BACKEND": "dynamodb"}, clear=True):
            with pytest.raises(ValidationError, match="DYNAMODB_STATE_TABLE_NAME"):
                Settings()

    def test_dynamodb_state_config_from_env(self) -> None:
        """DynamoDB state settings are read from environment variables."""
        env = {
            "STATE_BACKEND": "DYNAMODB",
            "DYNAMODB_STATE_TABLE_NAME": "arte-chatbot-state",
            "DYNAMODB_STATE_KEY_PREFIX": "#local-staging#",
            "SESSION_TTL_SECONDS": "7200",
            "BUFFER_TTL_SECONDS": "600",
            "RATE_LIMIT_TTL_SECONDS": "300",
            "LAMBDA_TIMEOUT_SECONDS": "28",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()
            assert settings.state_backend == "dynamodb"
            assert settings.dynamodb_state_table_name == "arte-chatbot-state"
            assert settings.dynamodb_state_key_prefix == "local-staging"
            assert settings.session_ttl_seconds == 7200
            assert settings.buffer_ttl_seconds == 600
            assert settings.rate_limit_ttl_seconds == 300
            assert settings.lambda_timeout_seconds == 28

    def test_lambda_secret_references_are_configurable(self) -> None:
        """Runtime secret refs are configurable without plaintext secrets."""
        env = {
            "OPENAI_API_KEY_SECRET_REF": "/arte/prod/openai-api-key",
            "CHAT_API_KEY_SECRET_REF": "/arte/prod/chat-api-key",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings()
            assert settings.openai_api_key_secret_ref == "/arte/prod/openai-api-key"
            assert settings.chat_api_key_secret_ref == "/arte/prod/chat-api-key"

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
