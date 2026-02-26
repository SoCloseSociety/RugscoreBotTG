"""RugCheck.xyz API client — free basic tier for cross-reference."""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from utils.rate_limiter import get_limiter
from data.cache import cache

logger = logging.getLogger(__name__)

BASE_URL = "https://api.rugcheck.xyz/v1"

_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=5.0,
            limits=httpx.Limits(max_connections=5),
            headers={"Accept": "application/json"},
        )
    return _client


async def get_token_report(mint: str) -> Optional[dict]:
    """Get RugCheck report for a token.

    Returns risk assessment, detected issues, etc.
    """
    cache_key = f"rugcheck:{mint}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    limiter = get_limiter("http_scrape")
    async with limiter:
        try:
            resp = await _get_client().get(f"{BASE_URL}/tokens/{mint}/report/summary")
            resp.raise_for_status()
            data = resp.json()
            cache.set(cache_key, data, ttl=300)
            return data
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.warning(f"RugCheck failed for {mint}: {e}")
            return None


def extract_rugcheck_risks(report: Optional[dict]) -> list[str]:
    """Extract risk indicators from RugCheck report."""
    if not report:
        return []

    risks = []
    # RugCheck returns various risk fields depending on version
    if report.get("risks"):
        for risk in report["risks"]:
            name = risk.get("name", "")
            level = risk.get("level", "")
            if level in ("danger", "warn"):
                risks.append(f"{name} ({level})")

    if report.get("score") is not None:
        rugcheck_score = report["score"]
        if rugcheck_score < 30:
            risks.append(f"RugCheck score: {rugcheck_score}/100")

    return risks


async def close():
    """Close the HTTP client."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
