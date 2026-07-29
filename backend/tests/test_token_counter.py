"""Deterministic tests for the local tokenizer foundation."""

from unittest.mock import Mock, patch

import pytest

from backend.app.token_counter import (
    TOKEN_COUNTER_LOAD_ERRORS,
    TiktokenTokenCounter,
    TokenCounter,
)


def test_tiktoken_counter_uses_named_encoding_and_counts_encoded_tokens() -> None:
    encoding = Mock()
    encoding.encode.return_value = [101, 202, 303]

    with patch(
        "backend.app.token_counter.tiktoken.get_encoding",
        return_value=encoding,
    ) as get_encoding:
        counter: TokenCounter = TiktokenTokenCounter("test_encoding")

    assert counter.count("energía solar") == 3
    get_encoding.assert_called_once_with("test_encoding")
    encoding.encode.assert_called_once_with("energía solar")


def test_expected_load_errors_are_explicit() -> None:
    assert TOKEN_COUNTER_LOAD_ERRORS == (
        KeyError,
        OSError,
        RuntimeError,
        ValueError,
    )


@pytest.mark.parametrize("error_type", TOKEN_COUNTER_LOAD_ERRORS)
def test_tiktoken_counter_propagates_expected_load_errors(
    error_type: type[Exception],
) -> None:
    expected_error = error_type("encoding unavailable")

    with (
        patch(
            "backend.app.token_counter.tiktoken.get_encoding",
            side_effect=expected_error,
        ),
        pytest.raises(error_type) as raised,
    ):
        TiktokenTokenCounter("missing_encoding")

    assert raised.value is expected_error
