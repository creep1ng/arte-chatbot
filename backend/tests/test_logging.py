"""
Tests for the centralized logging configuration module.
"""

import logging
import os

import pytest

from backend.app.config import settings
from backend.app.logging_config import (
    LOG_FORMAT,
    DATE_FORMAT,
    _DEFAULT_LOG_LEVEL,
    _VALID_LOG_LEVELS,
    get_log_level,
    setup_logging,
)


class TestGetLogLevel:
    """Tests for get_log_level() function."""

    @pytest.fixture(autouse=True)
    def _reset_settings(self) -> None:
        """Reset the cached Settings instance before each test.

        This ensures monkeypatch.setenv/delenv changes to LOG_LEVEL
        are picked up by the Pydantic Settings singleton.
        """
        settings.reset()

    def test_default_level_is_info(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that INFO is the default log level when LOG_LEVEL is unset."""
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        settings.reset()
        assert get_log_level() == logging.INFO

    def test_reads_debug_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test reading DEBUG level from environment."""
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        assert get_log_level() == logging.DEBUG

    def test_reads_warning_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test reading WARNING level from environment."""
        monkeypatch.setenv("LOG_LEVEL", "WARNING")
        assert get_log_level() == logging.WARNING

    def test_reads_error_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test reading ERROR level from environment."""
        monkeypatch.setenv("LOG_LEVEL", "ERROR")
        assert get_log_level() == logging.ERROR

    def test_reads_critical_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test reading CRITICAL level from environment."""
        monkeypatch.setenv("LOG_LEVEL", "CRITICAL")
        assert get_log_level() == logging.CRITICAL

    def test_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that log level parsing is case-insensitive."""
        monkeypatch.setenv("LOG_LEVEL", "debug")
        assert get_log_level() == logging.DEBUG

    def test_strips_whitespace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that surrounding whitespace is stripped."""
        monkeypatch.setenv("LOG_LEVEL", "  WARNING  ")
        assert get_log_level() == logging.WARNING

    def test_invalid_level_falls_back_to_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that an invalid level string falls back to INFO."""
        monkeypatch.setenv("LOG_LEVEL", "INVALID_LEVEL")
        assert get_log_level() == logging.INFO

    def test_empty_string_falls_back_to_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that an empty LOG_LEVEL falls back to INFO."""
        monkeypatch.setenv("LOG_LEVEL", "")
        assert get_log_level() == logging.INFO


class TestSetupLogging:
    """Tests for setup_logging() function."""

    @pytest.fixture(autouse=True)
    def _clean_root_logger(self) -> None:
        """Remove handlers from root logger before each test."""
        root = logging.getLogger()
        original_handlers = root.handlers[:]
        original_level = root.level
        settings.reset()
        yield
        # Restore original state
        root.handlers = original_handlers
        root.setLevel(original_level)

    def test_returns_root_logger(self) -> None:
        """Test that setup_logging returns the root logger."""
        root = logging.getLogger()
        root.handlers.clear()
        result = setup_logging()
        assert result is root

    def test_configures_handler(self) -> None:
        """Test that a StreamHandler is added to the root logger."""
        root = logging.getLogger()
        root.handlers.clear()
        setup_logging()
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0], logging.StreamHandler)

    def test_handler_format(self) -> None:
        """Test that the handler uses the expected format string."""
        root = logging.getLogger()
        root.handlers.clear()
        setup_logging()
        formatter = root.handlers[0].formatter
        assert formatter is not None
        assert formatter._fmt == LOG_FORMAT
        assert formatter.datefmt == DATE_FORMAT

    def test_idempotent(self) -> None:
        """Test that calling setup_logging() multiple times does not add duplicate handlers."""
        root = logging.getLogger()
        root.handlers.clear()
        setup_logging()
        setup_logging()
        setup_logging()
        assert len(root.handlers) == 1

    def test_respects_log_level_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that the root logger level is set from LOG_LEVEL env var."""
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        root = logging.getLogger()
        root.handlers.clear()
        setup_logging()
        assert root.level == logging.DEBUG

    def test_suppresses_noisy_loggers(self) -> None:
        """Test that noisy third-party loggers are suppressed."""
        root = logging.getLogger()
        root.handlers.clear()
        setup_logging()

        noisy_loggers = ["httpx", "httpcore", "openai", "botocore", "boto3", "urllib3"]
        for name in noisy_loggers:
            assert logging.getLogger(name).level == logging.WARNING
