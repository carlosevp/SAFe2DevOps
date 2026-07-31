from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from app.core.errors import AppError


class InMemoryRateLimiter:
    """Process-local sliding-window limiter for lightweight public endpoints."""

    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, *, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            bucket = self._events[key]
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                raise AppError(
                    code="rate_limited",
                    message="Too many requests. Please wait and try again.",
                    status_code=429,
                    details={"retry_after_seconds": window_seconds},
                )
            bucket.append(now)


rate_limiter = InMemoryRateLimiter()
