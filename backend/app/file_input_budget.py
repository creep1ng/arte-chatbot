"""Conservative guards for File Input requests."""

import logging
import math
from dataclasses import dataclass

from backend.app.context_budget_config import ContextBudgetConfig
from backend.app.model_capabilities import get_model_capabilities

logger = logging.getLogger(__name__)


class ContextBudgetError(ValueError):
    """Raised before a File Input request that cannot fit its budget."""


@dataclass(frozen=True)
class FileInputBudgetDecision:
    model: str
    input_limit_tokens: int
    counted_input_tokens: int
    output_reserve_tokens: int
    is_accepted: bool
    reason: str
    registry_version: str | None


def validate_file_input_size(
    *,
    file_size_bytes: int,
    max_file_size_bytes: int,
) -> None:
    """Reject files above the configured pre-upload byte ceiling."""
    is_accepted = file_size_bytes <= max_file_size_bytes
    reason = "accepted" if is_accepted else "file_size_exceeds_limit"
    logger.info(
        "File Input byte guard: file_size_bytes=%d max_file_size_bytes=%d "
        "is_accepted=%s reason=%s",
        file_size_bytes,
        max_file_size_bytes,
        is_accepted,
        reason,
    )
    if not is_accepted:
        raise ContextBudgetError(
            "File Input request rejected by context budget: file_size_exceeds_limit"
        )


def validate_file_input_token_count(
    *, model: str, config: ContextBudgetConfig, counted_input_tokens: int
) -> FileInputBudgetDecision:
    capabilities = get_model_capabilities(model)
    if capabilities is None:
        return _reject(model, "unknown_model")

    gross_limit = min(
        config.hard_cap_tokens,
        math.floor(capabilities.context_window_tokens * config.ratio),
    )
    input_limit = max(0, gross_limit - config.output_reserve_tokens)
    reason = "accepted"
    if config.output_reserve_tokens > capabilities.max_output_tokens:
        reason = "output_reserve_exceeds_model"
    elif counted_input_tokens < 0:
        reason = "invalid_input_token_count"
    elif counted_input_tokens > input_limit:
        reason = "input_tokens_exceed_limit"

    decision = FileInputBudgetDecision(
        model,
        input_limit,
        counted_input_tokens,
        config.output_reserve_tokens,
        reason == "accepted",
        reason,
        capabilities.registry_version,
    )
    _log_decision(decision)
    if not decision.is_accepted:
        raise ContextBudgetError(
            f"File Input request rejected by context budget: {decision.reason}"
        )
    return decision


def _reject(model: str, reason: str) -> FileInputBudgetDecision:
    decision = FileInputBudgetDecision(model, 0, 0, 0, False, reason, None)
    _log_decision(decision)
    raise ContextBudgetError(
        f"File Input request rejected by context budget: {decision.reason}"
    )


def _log_decision(decision: FileInputBudgetDecision) -> None:
    logger.info(
        "File Input budget decision: model=%s registry_version=%s "
        "input_limit_tokens=%d counted_input_tokens=%d output_reserve_tokens=%d "
        "is_accepted=%s reason=%s",
        decision.model,
        decision.registry_version,
        decision.input_limit_tokens,
        decision.counted_input_tokens,
        decision.output_reserve_tokens,
        decision.is_accepted,
        decision.reason,
    )
