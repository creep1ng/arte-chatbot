"""Contract tests for deterministic, offline context-budget replay."""

import json
import os
import subprocess
import sys

import pytest

from backend.app.context_budget_config import ContextBudgetConfig
from evaluation.context_budget.simulation import (
    PinnedCorpusTokenCounter,
    REPLAY_PATH,
    generate_report,
    load_replay,
    serialize_report,
)

RESULTS_PATH = REPLAY_PATH.with_name("results.json")


def test_replay_pins_twenty_spanish_exchanges_and_metadata() -> None:
    replay = load_replay(REPLAY_PATH)

    assert len(replay.exchanges) == 20
    assert all(
        10 <= len(exchange.question.split()) <= 30 for exchange in replay.exchanges
    )
    spanish_marks = set("áéíóúñ")
    assert all(
        exchange.question.startswith(("¿", "Necesito")) for exchange in replay.exchanges
    )
    assert all(
        exchange.answer.strip() and spanish_marks.intersection(exchange.answer.lower())
        for exchange in replay.exchanges
    )
    assert (
        replay.metadata.model,
        replay.metadata.registry_version,
        replay.metadata.encoding,
        replay.metadata.tokenizer_version,
        replay.metadata.config,
    ) == (
        "gpt-5.4-nano-2026-03-17",
        "2026-07-28",
        "o200k_base",
        "0.13.0",
        ContextBudgetConfig(0.1, 32_000, 2_000, 12_000, 20),
    )
    assert replay.metadata.tokenizer_source.endswith("/o200k_base.tiktoken")
    assert replay.metadata.tokenizer_source_sha256 == (
        "446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d"
    )
    assert len(replay.metadata.fixture_sha256) == 64
    assert "especialista técnico" in replay.metadata.system_prompt
    assert replay.metadata.tools[0]["name"] == "leer_ficha_tecnica"


def test_counter_fails_closed_outside_the_exact_pinned_corpus() -> None:
    replay = load_replay(REPLAY_PATH)
    counter = PinnedCorpusTokenCounter(replay.token_counts)

    with pytest.raises(ValueError, match="^text is outside the pinned replay corpus$"):
        counter.count("texto que no pertenece al corpus")


def test_report_has_per_turn_final_and_cumulative_metrics() -> None:
    report = generate_report(load_replay(REPLAY_PATH))

    assert len(report["turns"]) == 20
    cumulative_input = cumulative_output = cumulative_total = 0
    for number, turn in enumerate(report["turns"], 1):
        assert turn["turn"] == number
        assert turn["input_tokens"] > 0
        assert turn["output_tokens"] > 0
        assert turn["total_tokens"] == turn["input_tokens"] + turn["output_tokens"]
        cumulative_input += turn["input_tokens"]
        cumulative_output += turn["output_tokens"]
        cumulative_total += turn["total_tokens"]
        assert turn["cumulative_input_tokens"] == cumulative_input
        assert turn["cumulative_output_tokens"] == cumulative_output
        assert turn["cumulative_total_tokens"] == cumulative_total
        assert 0 <= turn["selected_history_turns"] <= min(number - 1, 20)

    assert report["cumulative"] == {
        "input_tokens": cumulative_input,
        "output_tokens": cumulative_output,
        "total_tokens": cumulative_total,
    }
    assert report["final_context"]["selected_history_turns"] == 20
    assert report["turns"][-1]["input_tokens"] < cumulative_input
    assert cumulative_total == cumulative_input + cumulative_output


def test_committed_report_matches_regenerated_bytes() -> None:
    generated = serialize_report(generate_report(load_replay(REPLAY_PATH)))

    assert RESULTS_PATH.read_bytes() == generated


def test_generation_is_cold_process_offline_and_byte_identical(tmp_path) -> None:
    code = """
import os, socket, urllib.request
def denied(*args, **kwargs): raise AssertionError("network forbidden")
socket.create_connection = denied
socket.socket.connect = denied
urllib.request.urlopen = denied
class Guarded(dict):
    def __getitem__(self, key):
        if key.endswith("API_KEY"): raise AssertionError("API key read")
        return super().__getitem__(key)
    def get(self, key, default=None):
        if key.endswith("API_KEY"): raise AssertionError("API key read")
        return super().get(key, default)
os.environ = Guarded(os.environ)
from evaluation.context_budget.simulation import main
main()
"""
    outputs = []
    for run in range(2):
        cache = tmp_path / str(run)
        cache.mkdir()
        environment = os.environ.copy()
        environment["TIKTOKEN_CACHE_DIR"] = str(cache)
        environment["OPENAI_API_KEY"] = "must-not-be-read"
        environment["ANTHROPIC_API_KEY"] = "must-not-be-read"
        outputs.append(
            subprocess.check_output(
                [sys.executable, "-c", "import sys\n" + code],
                env=environment,
            )
        )
        assert list(cache.iterdir()) == []

    first, second = outputs
    assert first == second
    assert first.endswith(b"\n")
    assert b"timestamp" not in first
    assert b"must-not-be-read" not in first


def test_tampered_fixture_hash_fails_closed(tmp_path) -> None:
    payload = json.loads(REPLAY_PATH.read_text(encoding="utf-8"))
    payload["exchanges"][0]["user"] += " alterado"
    tampered = tmp_path / "replay.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="^replay fixture hash mismatch$"):
        load_replay(tampered)
