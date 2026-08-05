"""Focused tests for the pre-upload File Input byte guard."""

import logging

import pytest

from backend.app.file_input_budget import ContextBudgetError, validate_file_input_size


def test_byte_guard_accepts_exact_boundary(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="backend.app.file_input_budget")

    validate_file_input_size(file_size_bytes=1_000, max_file_size_bytes=1_000)

    assert "file_size_bytes=1000" in caplog.text
    assert "is_accepted=True" in caplog.text
    assert "reason=accepted" in caplog.text


def test_byte_guard_rejects_before_upload_without_logging_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "cliente@example.com"
    caplog.set_level(logging.INFO, logger="backend.app.file_input_budget")

    with pytest.raises(ContextBudgetError, match="file_size_exceeds_limit"):
        validate_file_input_size(file_size_bytes=1_001, max_file_size_bytes=1_000)

    assert "is_accepted=False" in caplog.text
    assert "reason=file_size_exceeds_limit" in caplog.text
    assert secret not in caplog.text
