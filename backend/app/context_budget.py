"""Conservative, fail-closed token selection for complete history turns."""

import json
import logging
import math
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from backend.app.context_budget_config import ContextBudgetConfig
from backend.app.model_capabilities import get_model_capabilities
from backend.app.token_counter import (
    TOKEN_COUNTER_LOAD_ERRORS,
    TiktokenTokenCounter,
    TokenCounter,
)

logger = logging.getLogger(__name__)

_REQUEST_FRAMING_TOKENS = 16
_TURN_FRAMING_TOKENS = 8
_TURN_SEPARATOR = "\n\n"


class HistoryTurn(Protocol):
    """Minimum stored-turn shape required by the selector."""

    @property
    def question(self) -> str: ...

    @property
    def answer(self) -> str: ...

    @property
    def source_documents(self) -> Sequence[str]: ...


@dataclass(frozen=True)
class ContextBudgetDecision:
    """PII-free metrics produced by one history selection."""

    model: str
    history_budget_tokens: int
    known_overhead_tokens: int
    applied_non_history_reserve_tokens: int
    selected_history_tokens: int
    selected_turns: int
    available_turns: int
    was_truncated: bool
    stop_reason: str
    registry_version: str | None


@dataclass(frozen=True)
class SelectedContext:
    """Selected complete turns, formatted context, and decision metrics."""

    turns: tuple[HistoryTurn, ...]
    context: str
    decision: ContextBudgetDecision


def format_turn(turn: HistoryTurn, number: int) -> str:
    """Serialize one complete user/assistant turn with optional sources."""
    parts = [
        f"Turno {number}:",
        f"Usuario: {turn.question}",
        f"Asistente: {turn.answer}",
    ]
    if turn.source_documents:
        parts.append(f"Fuentes: {', '.join(turn.source_documents)}")
    return "\n".join(parts)


def format_turns(turns: Sequence[HistoryTurn]) -> str:
    """Serialize turns chronologically without splitting them."""
    return _TURN_SEPARATOR.join(
        format_turn(turn, number) for number, turn in enumerate(turns, 1)
    )


def estimate_text_request_tokens(
    counter: TokenCounter,
    system_prompt: str,
    tools: Sequence[dict[str, Any]],
    current_message: str,
    history_context: str = "",
) -> int:
    """Estimate textual request tokens with deterministic framing overhead."""
    serialized_tools = json.dumps(
        tools, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    return _REQUEST_FRAMING_TOKENS + sum(
        counter.count(text)
        for text in (
            system_prompt,
            serialized_tools,
            current_message,
            history_context,
        )
    )


def select_history(
    *,
    turns: Sequence[HistoryTurn],
    model: str,
    config: ContextBudgetConfig,
    system_prompt: str,
    tools: Sequence[dict[str, Any]],
    current_message: str,
    token_counter: TokenCounter | None = None,
) -> SelectedContext:
    """Select the newest contiguous suffix of complete turns that fits."""
    capabilities = get_model_capabilities(model)
    if capabilities is None:
        return _closed_decision(model, len(turns), "unknown_model")

    try:
        counter = token_counter or TiktokenTokenCounter(capabilities.encoding)
    except TOKEN_COUNTER_LOAD_ERRORS:
        return _closed_decision(
            model,
            len(turns),
            "unknown_tokenizer",
            capabilities.registry_version,
        )

    known_overhead = estimate_text_request_tokens(
        counter, system_prompt, tools, current_message
    )
    applied_reserve = max(config.non_history_reserve_tokens, known_overhead)
    gross_budget = min(
        config.hard_cap_tokens,
        math.floor(capabilities.context_window_tokens * config.ratio),
    )
    history_budget = max(
        0, gross_budget - config.output_reserve_tokens - applied_reserve
    )
    candidates = turns[-config.max_turns :]
    selected_reversed: list[HistoryTurn] = []
    selected_tokens = 0
    stop_reason = "all_candidates_fit"

    for turn in reversed(candidates):
        turn_tokens = counter.count(format_turn(turn, 1)) + _TURN_FRAMING_TOKENS
        if selected_reversed:
            turn_tokens += counter.count(_TURN_SEPARATOR)
        if selected_tokens + turn_tokens > history_budget:
            stop_reason = "turn_exceeds_remaining_budget"
            break
        selected_reversed.append(turn)
        selected_tokens += turn_tokens

    selected = tuple(reversed(selected_reversed))
    was_truncated = len(selected) < len(turns)
    if not was_truncated and stop_reason == "all_candidates_fit":
        stop_reason = "all_history_fit"
    elif len(turns) > config.max_turns and len(selected) == len(candidates):
        stop_reason = "max_turns_ceiling"

    decision = ContextBudgetDecision(
        model=model,
        history_budget_tokens=history_budget,
        known_overhead_tokens=known_overhead,
        applied_non_history_reserve_tokens=applied_reserve,
        selected_history_tokens=selected_tokens,
        selected_turns=len(selected),
        available_turns=len(turns),
        was_truncated=was_truncated,
        stop_reason=stop_reason,
        registry_version=capabilities.registry_version,
    )
    _log_decision(decision)
    return SelectedContext(selected, format_turns(selected), decision)


def _closed_decision(
    model: str,
    available_turns: int,
    reason: str,
    registry_version: str | None = None,
) -> SelectedContext:
    decision = ContextBudgetDecision(
        model=model,
        history_budget_tokens=0,
        known_overhead_tokens=0,
        applied_non_history_reserve_tokens=0,
        selected_history_tokens=0,
        selected_turns=0,
        available_turns=available_turns,
        was_truncated=available_turns > 0,
        stop_reason=reason,
        registry_version=registry_version,
    )
    _log_decision(decision)
    return SelectedContext((), "", decision)


def _log_decision(decision: ContextBudgetDecision) -> None:
    logger.info("Context budget decision: %s", decision)
