"""In-memory TTL cache — zero dependencies, zero cost."""

from __future__ import annotations

import time
import asyncio
from typing import Any, Optional


class TTLCache:
    """Simple in-memory cache with per-key TTL and periodic cleanup."""

    def __init__(self, default_ttl: int = 60, cleanup_interval: int = 300):
        self._cache: dict[str, tuple[Any, float]] = {}
        self._default_ttl = default_ttl
        self._cleanup_interval = cleanup_interval
        self._cleanup_task: Optional[asyncio.Task] = None

    def get(self, key: str) -> Optional[Any]:
        """Get a value if it exists and hasn't expired."""
        if key in self._cache:
            value, expiry = self._cache[key]
            if time.time() < expiry:
                return value
            del self._cache[key]
        return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set a value with optional custom TTL."""
        actual_ttl = ttl if ttl is not None else self._default_ttl
        self._cache[key] = (value, time.time() + actual_ttl)

    def delete(self, key: str):
        """Delete a key from cache."""
        self._cache.pop(key, None)

    def clear(self):
        """Clear all cached entries."""
        self._cache.clear()

    def cleanup(self):
        """Remove all expired entries."""
        now = time.time()
        expired = [k for k, (_, exp) in self._cache.items() if now >= exp]
        for k in expired:
            del self._cache[k]

    async def _periodic_cleanup(self):
        """Background task for periodic cleanup."""
        import logging
        _logger = logging.getLogger(__name__)
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                self.cleanup()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                _logger.warning(f"Cache cleanup error (will retry): {e}")

    def start_cleanup_task(self):
        """Start the periodic cleanup background task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

    def stop_cleanup_task(self):
        """Stop the periodic cleanup background task."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()

    @property
    def size(self) -> int:
        return len(self._cache)


# Global cache instance
cache = TTLCache(default_ttl=60)
