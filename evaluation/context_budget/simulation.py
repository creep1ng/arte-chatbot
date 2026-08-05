"""Pure, API-key-free generation of deterministic context-budget evidence."""

import json
from hashlib import sha256
from dataclasses import asdict, dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, cast

from backend.app.context_budget import estimate_text_request_tokens, select_history
from backend.app.context_budget_config import ContextBudgetConfig
from backend.app.model_capabilities import get_model_capabilities

REPLAY_PATH = Path(__file__).with_name("replay.json")


@dataclass(frozen=True)
class ReplayMetadata:
    """Pinned registry, tokenizer, request, and budget inputs."""

    model: str
    registry_version: str
    tokenizer_version: str
    tokenizer_source: str
    tokenizer_source_sha256: str
    encoding: str
    fixture_sha256: str
    config: ContextBudgetConfig
    system_prompt: str
    tools: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class ReplayExchange:
    """One committed Spanish user/assistant exchange."""

    question: str
    answer: str
    source_documents: tuple[str, ...]


@dataclass(frozen=True)
class Replay:
    """Validated replay inputs loaded from the committed fixture."""

    metadata: ReplayMetadata
    exchanges: tuple[ReplayExchange, ...]
    token_counts: Mapping[str, int]


class PinnedCorpusTokenCounter:
    """Fail-closed token counter for only the audited replay corpus."""

    def __init__(self, token_counts: Mapping[str, int]) -> None:
        self._token_counts = token_counts

    def count(self, text: str) -> int:
        """Return a pinned count, rejecting text outside the exact corpus."""
        count = self._token_counts.get(sha256(text.encode("utf-8")).hexdigest())
        if not isinstance(count, int) or count < 0:
            raise ValueError("text is outside the pinned replay corpus")
        return count


def load_replay(path: Path = REPLAY_PATH) -> Replay:
    """Load replay inputs and verify their pinned production capabilities."""
    payload = cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    raw_metadata = payload["metadata"]
    if _fixture_hash(payload) != raw_metadata["fixture_sha256"]:
        raise ValueError("replay fixture hash mismatch")
    raw_config = raw_metadata["config"]
    tokenizer = raw_metadata["tokenizer"]
    metadata = ReplayMetadata(
        model=raw_metadata["model"],
        registry_version=raw_metadata["registry_version"],
        tokenizer_version=tokenizer["version"],
        tokenizer_source=tokenizer["source"],
        tokenizer_source_sha256=tokenizer["source_sha256"],
        encoding=tokenizer["encoding"],
        fixture_sha256=raw_metadata["fixture_sha256"],
        config=ContextBudgetConfig(**raw_config),
        system_prompt=raw_metadata["system_prompt"],
        tools=tuple(cast(dict[str, Any], tool) for tool in raw_metadata["tools"]),
    )
    capabilities = get_model_capabilities(metadata.model)
    if capabilities is None or (
        capabilities.registry_version,
        capabilities.encoding,
    ) != (metadata.registry_version, metadata.encoding):
        raise ValueError("replay capability pins do not match the versioned registry")
    exchanges = tuple(
        ReplayExchange(item["user"], item["assistant"], tuple(item["sources"]))
        for item in payload["exchanges"]
    )
    counts = MappingProxyType(cast(dict[str, int], payload["token_counts"]))
    return Replay(metadata, exchanges, counts)


def generate_report(replay: Replay) -> dict[str, Any]:
    """Generate stable per-request, final-context, and consumption metrics."""
    metadata = replay.metadata
    counter = PinnedCorpusTokenCounter(replay.token_counts)
    history: list[ReplayExchange] = []
    rows: list[dict[str, int | str | bool]] = []
    cumulative_input = cumulative_output = cumulative_total = 0

    for number, exchange in enumerate(replay.exchanges, 1):
        selected = select_history(
            turns=history,
            model=metadata.model,
            config=metadata.config,
            system_prompt=metadata.system_prompt,
            tools=metadata.tools,
            current_message=exchange.question,
            token_counter=counter,
        )
        input_tokens = estimate_text_request_tokens(
            counter,
            metadata.system_prompt,
            metadata.tools,
            exchange.question,
            selected.context,
        )
        output_tokens = counter.count(exchange.answer)
        total_tokens = input_tokens + output_tokens
        cumulative_input += input_tokens
        cumulative_output += output_tokens
        cumulative_total += total_tokens
        rows.append(
            {
                "turn": number,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "selected_history_tokens": selected.decision.selected_history_tokens,
                "selected_history_turns": selected.decision.selected_turns,
                "history_was_truncated": selected.decision.was_truncated,
                "stop_reason": selected.decision.stop_reason,
                "cumulative_input_tokens": cumulative_input,
                "cumulative_output_tokens": cumulative_output,
                "cumulative_total_tokens": cumulative_total,
            }
        )
        history.append(exchange)

    final_selection = select_history(
        turns=history,
        model=metadata.model,
        config=metadata.config,
        system_prompt=metadata.system_prompt,
        tools=metadata.tools,
        current_message="",
        token_counter=counter,
    )
    final_input = estimate_text_request_tokens(
        counter, metadata.system_prompt, metadata.tools, "", final_selection.context
    )
    return {
        "metadata": asdict(metadata),
        "turns": rows,
        "final_context": {
            "input_tokens": final_input,
            "selected_history_tokens": final_selection.decision.selected_history_tokens,
            "selected_history_turns": final_selection.decision.selected_turns,
            "available_turns": final_selection.decision.available_turns,
            "was_truncated": final_selection.decision.was_truncated,
        },
        "cumulative": {
            "input_tokens": cumulative_input,
            "output_tokens": cumulative_output,
            "total_tokens": cumulative_total,
        },
    }


def serialize_report(report: Mapping[str, Any]) -> bytes:
    """Serialize a report canonically without timestamps or platform variance."""
    return (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _fixture_hash(payload: Mapping[str, Any]) -> str:
    """Hash every fixture field except the self-referential audit hash."""
    metadata = dict(cast(dict[str, Any], payload["metadata"]))
    metadata.pop("fixture_sha256")
    audited = {**payload, "metadata": metadata}
    canonical = json.dumps(
        audited, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    return sha256(canonical.encode("utf-8")).hexdigest()
