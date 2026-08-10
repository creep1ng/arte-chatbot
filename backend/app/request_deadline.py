"""Request-scoped monotonic deadline primitives."""

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Optional


class RequestDeadlineExceeded(RuntimeError):
    """Typed, sanitized failure raised when work cannot be admitted."""

    def __init__(
        self,
        operation: str,
        timeout_class: str = "work_budget_exhausted",
        iteration: Optional[int] = None,
    ) -> None:
        super().__init__("request deadline exceeded")
        self.operation = operation
        self.timeout_class = timeout_class
        self.iteration = iteration


@dataclass(frozen=True)
class RequestDeadline:
    """Immutable hard/work cutoffs derived from one monotonic start time."""

    hard_at: float
    work_at: float
    minimum_operation_margin_seconds: float
    clock: Callable[[], float] = field(
        default=time.monotonic, repr=False, compare=False
    )

    @classmethod
    def from_budget(
        cls,
        configured_total_seconds: float,
        response_safety_seconds: float,
        cleanup_reserve_seconds: float,
        minimum_operation_margin_seconds: float,
        lambda_remaining_ms: object = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> "RequestDeadline":
        """Build cutoffs, falling back when Lambda remaining time is invalid."""
        effective_total = configured_total_seconds
        try:
            lambda_seconds = float(lambda_remaining_ms) / 1000.0
        except (TypeError, ValueError):
            lambda_seconds = 0.0
        if math.isfinite(lambda_seconds) and lambda_seconds > 0:
            effective_total = min(configured_total_seconds, lambda_seconds)

        started_at = clock()
        hard_at = started_at + effective_total - response_safety_seconds
        return cls(
            hard_at=hard_at,
            work_at=hard_at - cleanup_reserve_seconds,
            minimum_operation_margin_seconds=minimum_operation_margin_seconds,
            clock=clock,
        )

    def remaining_work_seconds(self) -> float:
        """Return non-negative work time remaining."""
        return max(0.0, self.work_at - self.clock())

    def remaining_cleanup_seconds(self) -> float:
        """Return non-negative time remaining before the hard cutoff."""
        return max(0.0, self.hard_at - self.clock())

    def require_work(self, operation: str, iteration: Optional[int] = None) -> float:
        """Return the available allocation or reject work below its margin."""
        remaining = self.remaining_work_seconds()
        if remaining < self.minimum_operation_margin_seconds:
            raise RequestDeadlineExceeded(operation=operation, iteration=iteration)
        return remaining
