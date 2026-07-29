"""Stable runtime configuration contract for context budgeting."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextBudgetConfig:
    """Validated runtime controls consumed by context budget policies."""

    ratio: float
    hard_cap_tokens: int
    output_reserve_tokens: int
    non_history_reserve_tokens: int
    max_turns: int
