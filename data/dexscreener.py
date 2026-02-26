"""DexScreener API client — free, no API key needed."""

import logging
from typing import Optional

import httpx

from utils.rate_limiter import get_limiter
from data.cache import cache

logger = logging.getLogger(__name__)

BASE_URL = "https://api.dexscreener.com"

_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=5.0,
            limits=httpx.Limits(max_connections=10),
            headers={"Accept": "application/json"},
        )
    return _client


async def get_token_data(contract_address: str) -> Optional[dict]:
    """Fetch token data from DexScreener.

    Returns: pairs, price, volume, liquidity, txns, etc.
    Free, no key, 300 req/min limit.
    """
    cache_key = f"dex:{contract_address}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    limiter = get_limiter("dexscreener")
    url = f"{BASE_URL}/tokens/v1/solana/{contract_address}"

    async with limiter:
        try:
            resp = await _get_client().get(url)
            resp.raise_for_status()
            data = resp.json()

            # DexScreener returns a list of pairs
            if isinstance(data, list) and data:
                # Use the pair with highest liquidity
                pairs = sorted(
                    data,
                    key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0),
                    reverse=True,
                )
                result = {
                    "pairs": pairs,
                    "primary_pair": pairs[0] if pairs else None,
                }
                cache.set(cache_key, result, ttl=30)
                return result
            return None
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.warning(f"DexScreener failed for {contract_address}: {e}")
            return None


async def get_trending_tokens(limit: int = 10) -> list[dict]:
    """Fetch trending Solana tokens from DexScreener boosts + pair data.

    1. GET /token-boosts/top/v1  → top boosted tokens (trending)
    2. Filter to Solana only
    3. Batch-fetch pair data via /tokens/v1/solana/{addresses}
    Returns list of dicts with name, symbol, price, volume, liquidity, ca, etc.
    """
    cache_key = "dex:trending"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    limiter = get_limiter("dexscreener")

    # Step 1: Fetch boosted (trending) tokens
    async with limiter:
        try:
            resp = await _get_client().get(f"{BASE_URL}/token-boosts/top/v1")
            resp.raise_for_status()
            boosts = resp.json()
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.warning(f"DexScreener trending fetch failed: {e}")
            return []

    if not isinstance(boosts, list) or not boosts:
        return []

    # Step 2: Filter Solana tokens, deduplicate, take top N
    seen = set()
    solana_addresses = []
    for item in boosts:
        if item.get("chainId") != "solana":
            continue
        addr = item.get("tokenAddress", "")
        if addr and addr not in seen:
            seen.add(addr)
            solana_addresses.append(addr)
        if len(solana_addresses) >= limit:
            break

    if not solana_addresses:
        return []

    # Step 3: Batch-fetch pair data (API supports comma-separated addresses)
    addresses_str = ",".join(solana_addresses)
    async with limiter:
        try:
            resp = await _get_client().get(
                f"{BASE_URL}/tokens/v1/solana/{addresses_str}"
            )
            resp.raise_for_status()
            pairs_data = resp.json()
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.warning(f"DexScreener batch fetch failed: {e}")
            return []

    if not isinstance(pairs_data, list):
        return []

    # Group pairs by base token address, pick highest-liquidity pair
    best_pair: dict[str, dict] = {}
    for pair in pairs_data:
        base = pair.get("baseToken", {}).get("address", "")
        if not base:
            continue
        liq = float(pair.get("liquidity", {}).get("usd", 0) or 0)
        existing = best_pair.get(base)
        if not existing or liq > float(existing.get("liquidity", {}).get("usd", 0) or 0):
            best_pair[base] = pair

    # Build result in boost-rank order
    result = []
    for addr in solana_addresses:
        pair = best_pair.get(addr)
        if not pair:
            continue
        base = pair.get("baseToken", {})
        volume = pair.get("volume", {})
        liq = pair.get("liquidity", {})
        result.append({
            "token_name": base.get("name", "Unknown"),
            "token_symbol": base.get("symbol", "???"),
            "contract_address": addr,
            "price_usd": _safe_float(pair.get("priceUsd")),
            "volume_24h": _safe_float(volume.get("h24")),
            "liquidity_usd": _safe_float(liq.get("usd")),
            "market_cap": _safe_float(pair.get("marketCap")),
            "price_change_24h": _safe_float(pair.get("priceChange", {}).get("h24")),
            "pair_url": pair.get("url"),
        })

    cache.set(cache_key, result, ttl=120)
    return result


def extract_market_data(dex_data: Optional[dict]) -> dict:
    """Extract key market data from DexScreener response.

    Aggregates liquidity, volume, and transaction counts across ALL pairs
    so tokens listed on multiple DEXes get accurate totals.
    """
    empty = {
        "price_usd": None,
        "liquidity_usd": None,
        "market_cap": None,
        "fdv": None,
        "volume_24h": None,
        "volume_6h": None,
        "volume_1h": None,
        "txns_24h_buys": 0,
        "txns_24h_sells": 0,
        "pair_created_at": None,
        "pair_address": None,
        "dex_id": None,
        "maker_count": 0,
        "pair_url": None,
    }

    if not dex_data or not dex_data.get("primary_pair"):
        return empty

    pair = dex_data["primary_pair"]
    txns = pair.get("txns", {})
    volume = pair.get("volume", {})

    # Aggregate liquidity, volume, txns, and makers across ALL pairs
    all_pairs = dex_data.get("pairs", [pair])
    total_liquidity = 0.0
    total_vol_24h = 0.0
    total_vol_6h = 0.0
    total_vol_1h = 0.0
    total_buys = 0
    total_sells = 0
    total_makers = 0

    for p in all_pairs:
        liq = _safe_float(p.get("liquidity", {}).get("usd"))
        if liq and liq > 0:
            total_liquidity += liq
        v = p.get("volume", {})
        v24 = _safe_float(v.get("h24"))
        v6 = _safe_float(v.get("h6"))
        v1 = _safe_float(v.get("h1"))
        if v24 and v24 > 0:
            total_vol_24h += v24
        if v6 and v6 > 0:
            total_vol_6h += v6
        if v1 and v1 > 0:
            total_vol_1h += v1
        pt = p.get("txns", {}).get("h24", {})
        if isinstance(pt, dict):
            total_buys += pt.get("buys", 0) or 0
            total_sells += pt.get("sells", 0) or 0
        # makers can be dict {"h24": N} or int depending on API version
        pm = p.get("makers")
        if isinstance(pm, dict):
            total_makers += pm.get("h24", 0) or 0
        elif isinstance(pm, (int, float)):
            total_makers += int(pm)

    # Resolve primary pair makers for fallback
    pair_makers = pair.get("makers")
    if isinstance(pair_makers, dict):
        pair_maker_fallback = pair_makers.get("h24", 0) or 0
    elif isinstance(pair_makers, (int, float)):
        pair_maker_fallback = int(pair_makers)
    else:
        pair_maker_fallback = 0

    return {
        "price_usd": _safe_float(pair.get("priceUsd")),
        "liquidity_usd": total_liquidity if total_liquidity > 0 else _safe_float(pair.get("liquidity", {}).get("usd")),
        "market_cap": _safe_float(pair.get("marketCap")),
        "fdv": _safe_float(pair.get("fdv")),
        "volume_24h": total_vol_24h if total_vol_24h > 0 else _safe_float(volume.get("h24")),
        "volume_6h": total_vol_6h if total_vol_6h > 0 else _safe_float(volume.get("h6")),
        "volume_1h": total_vol_1h if total_vol_1h > 0 else _safe_float(volume.get("h1")),
        "txns_24h_buys": total_buys if total_buys > 0 else (txns.get("h24", {}).get("buys", 0) or 0),
        "txns_24h_sells": total_sells if total_sells > 0 else (txns.get("h24", {}).get("sells", 0) or 0),
        "pair_created_at": pair.get("pairCreatedAt"),
        "pair_address": pair.get("pairAddress"),
        "dex_id": pair.get("dexId"),
        "maker_count": total_makers if total_makers > 0 else pair_maker_fallback,
        "pair_url": pair.get("url"),
    }


def extract_social_data(dex_data: Optional[dict]) -> dict:
    """Extract social links from DexScreener pair info.

    DexScreener API returns:
      pair.info.socials = [{"type": "twitter", "url": "..."}, ...]
      pair.info.websites = [{"label": "...", "url": "..."}]
    """
    result = {
        "twitter": None,
        "telegram": None,
        "website": None,
    }

    if not dex_data or not dex_data.get("primary_pair"):
        return result

    pair = dex_data["primary_pair"]
    info = pair.get("info", {})
    if not isinstance(info, dict):
        return result

    # Extract from socials array
    socials = info.get("socials", [])
    if isinstance(socials, list):
        for social in socials:
            if not isinstance(social, dict):
                continue
            social_type = social.get("type", "").lower()
            url = social.get("url", "")
            if not url:
                continue
            if "twitter" in social_type or social_type == "x":
                result["twitter"] = url
            elif "telegram" in social_type:
                result["telegram"] = url

    # Extract from websites array
    websites = info.get("websites", [])
    if isinstance(websites, list):
        for site in websites:
            if isinstance(site, dict) and site.get("url"):
                result["website"] = site["url"]
                break
            elif isinstance(site, str) and site:
                result["website"] = site
                break

    return result


def _safe_float(value) -> Optional[float]:
    """Safely convert a value to float."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


async def close():
    """Close the HTTP client."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
