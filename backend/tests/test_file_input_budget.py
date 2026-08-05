"""Focused tests for the pre-upload File Input byte guard."""

import logging

import pytest

from backend.app.context_budget_config import ContextBudgetConfig
from backend.app.file_input_budget import (
    ContextBudgetError,
    validate_file_input_size,
    validate_file_input_token_count,
)


TOKEN_CONFIG = ContextBudgetConfig(1.0, 32_000, 2_000, 0, 1)


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


def test_token_guard_accepts_exact_effective_boundary() -> None:
    decision = validate_file_input_token_count(
        model="gpt-5.4-nano",
        config=TOKEN_CONFIG,
        counted_input_tokens=30_000,
    )
    assert decision.input_limit_tokens == 30_000
    assert decision.is_accepted is True


@pytest.mark.parametrize(
    ("model", "counted_tokens", "reason"),
    [
        ("gpt-5.4-nano", 30_001, "input_tokens_exceed_limit"),
        ("unknown-model", 1, "unknown_model"),
        ("gpt-5.4-nano", -1, "invalid_input_token_count"),
    ],
)
def test_token_guard_fails_closed_for_unprovable_counts(
    model: str,
    counted_tokens: int,
    reason: str,
) -> None:
    with pytest.raises(ContextBudgetError, match=reason):
        validate_file_input_token_count(
            model=model,
            config=TOKEN_CONFIG,
            counted_input_tokens=counted_tokens,
        )
