"""Small in-memory rate limiter for API-key scoped endpoints."""

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class RateLimitDecision:
    """Result of a rate-limit check."""

    allowed: bool
    retry_after_seconds: int = 0


class InMemoryRateLimiter:
    """Sliding-window limiter scoped by principal.

    This limiter is intentionally process-local. It protects local and single-node
    deployments; horizontally scaled deployments should replace it with Redis/API
    gateway enforcement while keeping the same endpoint behavior.
    """

    def __init__(self) -> None:
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(
        self, principal: str, *, limit: int, window_seconds: int
    ) -> RateLimitDecision:
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
