"""Typed token counting primitives backed by local tiktoken encodings."""

from typing import Protocol

import tiktoken

TOKEN_COUNTER_LOAD_ERRORS: tuple[type[Exception], ...] = (
    KeyError,
    OSError,
    RuntimeError,
    ValueError,
)


class TokenCounter(Protocol):
    """Contract for deterministic text token counting."""

    def count(self, text: str) -> int:
        """Count encoded tokens in ``text``."""
        ...


class TiktokenTokenCounter:
    """Token counter backed by a named tiktoken encoding."""

    def __init__(self, encoding_name: str) -> None:
        self._encoding = tiktoken.get_encoding(encoding_name)

    def count(self, text: str) -> int:
        """Return the deterministic number of encoded tokens in ``text``."""
        return len(self._encoding.encode(text))
