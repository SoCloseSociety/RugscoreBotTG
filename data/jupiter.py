"""Jupiter Price API client — free, no API key needed."""

import logging
from typing import Optional

import httpx

from utils.rate_limiter import get_limiter
from data.cache import cache

logger = logging.getLogger(__name__)

BASE_URL = "https://api.jup.ag/price/v2"

_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=5.0, limits=httpx.Limits(max_connections=5))
    return _client


async def get_price(mint: str) -> Optional[float]:
    """Get token price in USD from Jupiter.

    Backup for DexScreener price data.
    """
    cache_key = f"jupiter_price:{mint}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    limiter = get_limiter("dexscreener")  # Share dex rate limit
    async with limiter:
        try:
            resp = await _get_client().get(BASE_URL, params={"ids": mint})
            resp.raise_for_status()
            data = resp.json()
            price_data = data.get("data", {}).get(mint)
            if price_data:
                price = float(price_data.get("price", 0))
                cache.set(cache_key, price, ttl=30)
                return price
            return None
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.warning(f"Jupiter price failed for {mint}: {e}")
            return None


async def close():
    """Close the HTTP client."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
