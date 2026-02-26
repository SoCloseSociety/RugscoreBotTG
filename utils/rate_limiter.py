"""Async rate limiter with per-second throttling and concurrency control."""

from __future__ import annotations

import asyncio
import time
from collections import deque


class RateLimiter:
    """Rate limiter combining concurrency semaphore with per-second throttling."""

    def __init__(self, max_concurrent: int = 5, per_second: int = 10):
        self._max_concurrent = max_concurrent
        self._per_second = per_second
        self._timestamps: deque[float] = deque()
        # Lazy init for asyncio primitives (Python 3.9 compat)
        self._semaphore: asyncio.Semaphore | None = None
        self._lock: asyncio.Lock | None = None

    def _ensure_primitives(self):
        """Create asyncio primitives lazily within the running event loop."""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrent)
        if self._lock is None:
            self._lock = asyncio.Lock()

    async def acquire(self):
        """Acquire both semaphore slot and rate limit slot."""
        self._ensure_primitives()
        await self._semaphore.acquire()

        sleep_time = 0.0
        async with self._lock:
            now = time.monotonic()
            # Remove timestamps older than 1 second
            while self._timestamps and self._timestamps[0] < now - 1.0:
                self._timestamps.popleft()
            # If at rate limit, calculate wait time
            if len(self._timestamps) >= self._per_second:
                sleep_time = 1.0 - (now - self._timestamps[0])

        # Sleep outside the lock to avoid blocking other coroutines (BUG 27 fix)
        if sleep_time > 0:
            await asyncio.sleep(sleep_time)

        async with self._lock:
            self._timestamps.append(time.monotonic())

    def release(self):
        """Release the semaphore slot."""
        if self._semaphore:
            self._semaphore.release()

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.release()


# Global rate limiters per API source
_limiters: dict[str, RateLimiter] = {}


def get_limiter(source: str) -> RateLimiter:
    """Get or create a rate limiter for a given API source."""
    from config.constants import RATE_LIMITS

    if source not in _limiters:
        config = RATE_LIMITS.get(source, {"max_concurrent": 5, "per_second": 10})
        _limiters[source] = RateLimiter(
            max_concurrent=config["max_concurrent"],
            per_second=config["per_second"],
        )
    return _limiters[source]
