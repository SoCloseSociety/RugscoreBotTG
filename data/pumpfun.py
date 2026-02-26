"""PumpPortal WebSocket client + Pump.fun data — free, no API key needed."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Optional

import websockets

from data.cache import cache

logger = logging.getLogger(__name__)

PUMPPORTAL_WS_URL = "wss://pumpportal.fun/api/data"


class PumpFunStream:
    """WebSocket client for real-time Pump.fun events."""

    def __init__(self):
        self._ws = None
        self._running = False
        self._callbacks: dict[str, list[Callable]] = {
            "new_token": [],
            "migration": [],
            "trade": [],
        }
        self._reconnect_delay = 5
        self._max_reconnect_delay = 120

    def on_new_token(self, callback: Callable):
        """Register a callback for new token creation events."""
        self._callbacks["new_token"].append(callback)

    def on_migration(self, callback: Callable):
        """Register a callback for migration (graduation to Raydium) events."""
        self._callbacks["migration"].append(callback)

    def on_trade(self, callback: Callable):
        """Register a callback for trade events."""
        self._callbacks["trade"].append(callback)

    async def start(self):
        """Start the WebSocket connection with auto-reconnect and exponential backoff."""
        self._running = True
        delay = self._reconnect_delay
        while self._running:
            try:
                await self._connect()
                delay = self._reconnect_delay  # Reset on successful connection
            except Exception as e:
                logger.error(f"PumpPortal WebSocket error: {e}")
                if self._running:
                    logger.info(f"Reconnecting in {delay}s...")
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, self._max_reconnect_delay)

    async def _connect(self):
        """Connect and listen for events."""
        async with websockets.connect(PUMPPORTAL_WS_URL) as ws:
            self._ws = ws
            logger.info("Connected to PumpPortal WebSocket")

            # Subscribe to new token creations
            await ws.send(json.dumps({"method": "subscribeNewToken"}))
            # Subscribe to migrations (graduation to Raydium)
            await ws.send(json.dumps({"method": "subscribeMigration"}))

            async for message in ws:
                if not self._running:
                    break
                try:
                    data = json.loads(message)
                    await self._dispatch(data)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from PumpPortal: {message[:100]}")

    async def _dispatch(self, data: dict):
        """Dispatch events to registered callbacks."""
        event_type = data.get("txType", "")

        if event_type == "create":
            for cb in self._callbacks["new_token"]:
                try:
                    await cb(data)
                except Exception as e:
                    logger.error(f"new_token callback error: {e}")
        elif event_type == "migrate":
            for cb in self._callbacks["migration"]:
                try:
                    await cb(data)
                except Exception as e:
                    logger.error(f"migration callback error: {e}")
        elif event_type in ("buy", "sell"):
            for cb in self._callbacks["trade"]:
                try:
                    await cb(data)
                except Exception as e:
                    logger.error(f"trade callback error: {e}")

    async def stop(self):
        """Stop the WebSocket connection."""
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None
        logger.info("PumpPortal WebSocket stopped")


async def get_bonding_curve_progress(mint: str) -> Optional[float]:
    """Get bonding curve progress for a Pump.fun token.

    Returns progress as percentage (0-100) or None if not a Pump.fun token.
    This is fetched from the PumpPortal REST-like data if available.
    """
    # Bonding curve data comes from the WebSocket stream
    # For on-demand queries, check cache from recent stream data
    cache_key = f"bonding_curve:{mint}"
    return cache.get(cache_key)


# Global stream instance
pump_stream = PumpFunStream()
