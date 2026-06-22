"""Rate limiters for API-key scoped endpoints."""

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock
from typing import Optional

from backend.app.state_repository import ChatbotStateRepository


@dataclass(frozen=True)
class RateLimitDecision:
    """Result of a rate-limit check."""

    allowed: bool
    retry_after_seconds: int = 0


class InMemoryRateLimiter:
    """Sliding-window limiter scoped by principal.

    This limiter is intentionally process-local. It protects local and single-node
    deployments; horizontally scaled deployments should use the shared state
    repository or API Gateway enforcement while keeping the same endpoint behavior.
    """

    def __init__(self) -> None:
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self.state_repository: Optional[ChatbotStateRepository] = None
        self._lock = Lock()

    def set_state_repository(
        self, state_repository: Optional[ChatbotStateRepository]
    ) -> None:
        """Configure a shared repository for Lambda-safe rate counters."""
        with self._lock:
            self.state_repository = state_repository

    def check(
        self, principal: str, *, limit: int, window_seconds: int
    ) -> RateLimitDecision:
        if self.state_repository is not None:
            decision = self.state_repository.check_rate_limit(
                principal, limit=limit, window_seconds=window_seconds
            )
            return RateLimitDecision(
                allowed=decision.allowed,
                retry_after_seconds=decision.retry_after_seconds,
            )

        now = time.monotonic()
        cutoff = now - window_seconds

        with self._lock:
            timestamps = self._requests[principal]
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()

            if len(timestamps) >= limit:
                retry_after = max(1, int(window_seconds - (now - timestamps[0])))
                return RateLimitDecision(False, retry_after)

            timestamps.append(now)
            return RateLimitDecision(True)

    def reset(self) -> None:
        """Clear all tracked requests. Intended for tests."""
        with self._lock:
            self._requests.clear()


rate_limiter = InMemoryRateLimiter()
