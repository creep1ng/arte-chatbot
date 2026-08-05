"""Tests for model-aware, complete-turn history selection."""

import logging
from dataclasses import dataclass
from unittest.mock import patch

from backend.app.context_budget import format_turn, select_history
from backend.app.context_budget_config import ContextBudgetConfig


@dataclass(frozen=True)
class Turn:
    question: str
    answer: str = "respuesta"
    source_documents: tuple[str, ...] = ()


class CharacterTokenCounter:
    def count(self, text: str) -> int:
        return len(text)


def _config(history_budget: int, max_turns: int = 20) -> ContextBudgetConfig:
    # Character counting sees 16 request-framing tokens plus two for serialized tools.
    return ContextBudgetConfig(1.0, history_budget + 18, 0, 0, max_turns)


def _select(turns: list[Turn], history_budget: int = 10_000, max_turns: int = 20):
    return select_history(
        turns=turns,
        model="gpt-5.4-nano",
        config=_config(history_budget, max_turns),
        system_prompt="",
        tools=[],
        current_message="",
        token_counter=CharacterTokenCounter(),
    )


def _turn_cost(turn: Turn) -> int:
    return len(format_turn(turn, 1)) + 8


def test_short_history_is_returned_chronologically() -> None:
    turns = [Turn("uno"), Turn("dos")]
    selected = _select(turns)

    assert selected.turns == tuple(turns)
    assert selected.context.index("Usuario: uno") < selected.context.index(
        "Usuario: dos"
    )
    assert selected.decision.stop_reason == "all_history_fit"


def test_budget_selects_newest_contiguous_suffix_in_order() -> None:
    turns = [Turn("antigua"), Turn("media"), Turn("nueva")]
    budget = _turn_cost(turns[1]) + _turn_cost(turns[2]) + len("\n\n")

    selected = _select(turns, budget)

    assert selected.turns == tuple(turns[1:])
    assert selected.decision.was_truncated is True


def test_oversized_newest_turn_stops_without_skipping_it() -> None:
    selected = _select([Turn("corta"), Turn("larga", "x" * 500)], 100)

    assert selected.turns == ()
    assert selected.decision.stop_reason == "turn_exceeds_remaining_budget"


def test_exact_budget_boundary_includes_turn() -> None:
    turn = Turn("límite", "exacto")
    exact_cost = _turn_cost(turn)

    assert _select([turn], exact_cost).turns == (turn,)
    assert _select([turn], exact_cost - 1).turns == ()


def test_spanish_unicode_turn_is_counted_and_preserved() -> None:
    turn = Turn(
        "¿Qué batería rinde mejor con días nublados? ☀️",
        "La batería de litio conserva más ciclos y energía útil.",
    )

    selected = _select([turn])

    assert selected.turns == (turn,)
    assert "¿Qué batería" in selected.context
    assert selected.decision.selected_history_tokens > 0


def test_sources_are_included_in_context_and_token_cost() -> None:
    plain = Turn("pregunta")
    sourced = Turn("pregunta", source_documents=("raw/paneles/a.pdf", "raw/b/b.pdf"))

    plain_selection = _select([plain])
    sourced_selection = _select([sourced])

    assert sourced_selection.decision.selected_history_tokens > (
        plain_selection.decision.selected_history_tokens
    )
    assert "Fuentes: raw/paneles/a.pdf, raw/b/b.pdf" in sourced_selection.context


def test_unknown_model_fails_closed_without_logging_content(caplog) -> None:
    secret = "correo@example.com pregunta privada"
    caplog.set_level(logging.INFO, logger="backend.app.context_budget")

    selected = select_history(
        turns=[Turn(secret)],
        model="unknown-model",
        config=_config(10_000),
        system_prompt=secret,
        tools=[],
        current_message=secret,
        token_counter=CharacterTokenCounter(),
    )

    assert selected.turns == ()
    assert selected.decision.stop_reason == "unknown_model"
    assert secret not in caplog.text


def test_unknown_tokenizer_fails_closed() -> None:
    with patch(
        "backend.app.context_budget.TiktokenTokenCounter",
        side_effect=ValueError("encoding unavailable"),
    ):
        selected = select_history(
            turns=[Turn("pregunta")],
            model="gpt-5.4-nano",
            config=_config(10_000),
            system_prompt="",
            tools=[],
            current_message="",
        )

    assert selected.turns == ()
    assert selected.decision.stop_reason == "unknown_tokenizer"


def test_cold_cache_failure_fails_closed_without_pii(caplog) -> None:
    secret = "cliente@example.com necesita una batería"
    caplog.set_level(logging.INFO, logger="backend.app.context_budget")

    with patch(
        "backend.app.token_counter.tiktoken.get_encoding",
        side_effect=OSError("simulated offline cold cache"),
    ):
        selected = select_history(
            turns=[Turn(secret)],
            model="gpt-5.4-nano",
            config=_config(10_000),
            system_prompt=secret,
            tools=[],
            current_message=secret,
        )

    assert selected.decision.stop_reason == "unknown_tokenizer"
    assert secret not in caplog.text


def test_known_overhead_uses_greater_configured_reserve() -> None:
    config = ContextBudgetConfig(0.10, 32_000, 2_000, 12_000, 20)

    selected = select_history(
        turns=[],
        model="gpt-5.4-nano",
        config=config,
        system_prompt="short",
        tools=[],
        current_message="short",
        token_counter=CharacterTokenCounter(),
    )

    assert selected.decision.known_overhead_tokens == 28
    assert selected.decision.applied_non_history_reserve_tokens == 12_000
    assert selected.decision.history_budget_tokens == 18_000


def test_max_turns_is_a_secondary_ceiling() -> None:
    selected = _select([Turn(str(number)) for number in range(3)], max_turns=2)

    assert [turn.question for turn in selected.turns] == ["1", "2"]
    assert selected.decision.stop_reason == "max_turns_ceiling"


def test_success_logs_metrics_without_turn_content(caplog) -> None:
    secret = "dato-privado@example.com"
    caplog.set_level(logging.INFO, logger="backend.app.context_budget")

    _select([Turn(secret)])

    assert "selected_turns=1" in caplog.text
    assert "stop_reason='all_history_fit'" in caplog.text
    assert secret not in caplog.text
