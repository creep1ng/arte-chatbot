"""Unit tests for request-scoped monotonic deadlines."""

from dataclasses import FrozenInstanceError

import pytest

from backend.app.request_deadline import RequestDeadline, RequestDeadlineExceeded


class FakeClock:
    def __init__(self, now: float = 100.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _deadline(clock: FakeClock, lambda_remaining_ms: object = None) -> RequestDeadline:
    return RequestDeadline.from_budget(
        25.0, 2.0, 3.0, 1.0, lambda_remaining_ms, clock
    )


def test_local_deadline_uses_configured_budget_and_immutable_cutoffs() -> None:
    clock = FakeClock()
    deadline = _deadline(clock)
    assert deadline.hard_at == 123.0
    assert deadline.work_at == 120.0
    with pytest.raises(FrozenInstanceError):
        deadline.hard_at = 999.0  # type: ignore[misc]


def test_positive_lambda_remaining_time_caps_configured_budget() -> None:
    clock = FakeClock()
    deadline = _deadline(clock, lambda_remaining_ms=10_000)
    assert deadline.hard_at == 108.0
    assert deadline.work_at == 105.0


@pytest.mark.parametrize("remaining", [None, "bad", 0, -1, float("nan")])
def test_malformed_lambda_remaining_time_falls_back_to_configured_budget(
    remaining: object,
) -> None:
    assert _deadline(FakeClock(), remaining).hard_at == 123.0


def test_require_work_returns_allocation_when_minimum_margin_remains() -> None:
    clock = FakeClock()
    deadline = _deadline(clock)
    clock.now = 119.0
    assert deadline.require_work("openai", iteration=2) == 1.0


def test_require_work_raises_typed_sanitized_failure_below_margin() -> None:
    clock = FakeClock()
    deadline = _deadline(clock)
    clock.now = 119.01
    with pytest.raises(RequestDeadlineExceeded) as exc_info:
        deadline.require_work("openai", iteration=3)
    failure = exc_info.value
    assert (failure.operation, failure.timeout_class, failure.iteration) == (
        "openai",
        "work_budget_exhausted",
        3,
    )
    assert str(failure) == "request deadline exceeded"


def test_cleanup_allocation_uses_remaining_hard_cutoff() -> None:
    clock = FakeClock()
    deadline = _deadline(clock)
    clock.now = 121.5
    assert (deadline.remaining_work_seconds(), deadline.remaining_cleanup_seconds()) == (
        0.0,
        1.5,
    )
    clock.now = 124.0
    assert deadline.remaining_cleanup_seconds() == 0.0
