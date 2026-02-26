"""RPC endpoint rotation for free tier rate limit management."""

from __future__ import annotations

import asyncio
import logging
import time

from config.settings import settings
from config.constants import FALLBACK_RPC_ENDPOINTS

logger = logging.getLogger(__name__)


class RPCRotator:
    """Rotates between free Solana RPC endpoints to avoid rate limits."""

    def __init__(self):
        self._endpoints: list[str] = []
        self._current_index: int = 0
        self._failures: dict[str, int] = {}
        self._cooldowns: dict[str, float] = {}
        # Lazy init for asyncio.Lock (Python 3.9 compat — BUG 20 fix)
        self._lock: asyncio.Lock | None = None
        self._initialize_endpoints()

    def _ensure_lock(self):
        if self._lock is None:
            self._lock = asyncio.Lock()

    def _initialize_endpoints(self):
        """Build the endpoint list with Helius primary + fallbacks."""
        if settings.helius_api_key:
            self._endpoints.append(settings.helius_rpc_url)
        self._endpoints.extend(FALLBACK_RPC_ENDPOINTS)

    @property
    def primary(self) -> str:
        """Return the primary (Helius) endpoint."""
        return self._endpoints[0] if self._endpoints else FALLBACK_RPC_ENDPOINTS[0]

    async def get_endpoint(self) -> str:
        """Get the next available RPC endpoint, skipping those on cooldown."""
        self._ensure_lock()
        async with self._lock:
            now = time.monotonic()
            for _ in range(len(self._endpoints)):
                endpoint = self._endpoints[self._current_index]
                cooldown_until = self._cooldowns.get(endpoint, 0)
                if now >= cooldown_until:
                    return endpoint
                self._current_index = (self._current_index + 1) % len(self._endpoints)
            # All on cooldown — return the one with the shortest remaining cooldown
            logger.warning("All RPC endpoints on cooldown, using primary")
            return self._endpoints[0]

    async def report_failure(self, endpoint: str):
        """Report a failure for an endpoint, potentially putting it on cooldown."""
        self._ensure_lock()
        async with self._lock:
            self._failures[endpoint] = self._failures.get(endpoint, 0) + 1
            consecutive = self._failures[endpoint]
            # Exponential backoff: 5s, 10s, 20s, max 60s
            cooldown = min(5 * (2 ** (consecutive - 1)), 60)
            self._cooldowns[endpoint] = time.monotonic() + cooldown
            self._current_index = (self._current_index + 1) % len(self._endpoints)
            logger.warning(
                f"RPC {endpoint[:40]}... failed ({consecutive}x), cooldown {cooldown}s"
            )

    async def report_success(self, endpoint: str):
        """Reset failure count on success."""
        self._ensure_lock()
        async with self._lock:
            self._failures[endpoint] = 0
            self._cooldowns.pop(endpoint, None)


# Global singleton
rpc_rotator = RPCRotator()
