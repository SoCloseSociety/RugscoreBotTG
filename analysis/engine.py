"""Main scoring orchestrator — parallel data fetch + scoring pipeline."""

import asyncio
import logging
import time
from typing import Optional

from analysis.criteria import CriterionResult
from analysis.criteria.contract import score_contract
from analysis.criteria.liquidity import score_liquidity
from analysis.criteria.holders import score_holders
from analysis.criteria.dev_wallet import score_dev_wallet
from analysis.criteria.volume import score_volume
from analysis.criteria.social import score_social
from analysis.criteria.metadata import score_metadata
from analysis.criteria.smart_money import score_smart_money
from analysis.scoring import calculate_composite_score
from data.dexscreener import get_token_data, extract_market_data, extract_social_data
from data.helius_client import get_asset, get_asset_creator
from data.solana_rpc import get_token_largest_accounts, get_token_supply
from data.cache import cache
from config.settings import settings
from config.constants import CACHE_TTL_ANALYSIS, PUMP_FUN_AUTHORITY, PUMP_FUN_PROGRAM

logger = logging.getLogger(__name__)

# Per-criterion timeout (seconds). Slow criteria don't kill fast ones.
CRITERION_TIMEOUT = 10


async def _safe_criterion(name: str, coro) -> CriterionResult:
    """Run a single criterion with its own timeout and error handling.

    Returns a conservative low score on failure — never a fake neutral 50.
    """
    try:
        return await asyncio.wait_for(coro, timeout=CRITERION_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning(f"Criterion {name} timed out ({CRITERION_TIMEOUT}s)")
        return CriterionResult(
            name=name.replace("_", " ").title(),
            score=20,
            flags=["\u274c Data unavailable (timed out)"],
            estimated=True,
        )
    except Exception as e:
        logger.warning(f"Criterion {name} error: {e}")
        return CriterionResult(
            name=name.replace("_", " ").title(),
            score=20,
            flags=["\u274c Data unavailable (error)"],
            estimated=True,
        )


async def analyze_token(token_mint: str) -> dict:
    """Run a full analysis on a token.

    Pipeline:
    1. Check cache
    2. Parallel data fetch (all free APIs)
    3. Score each criterion (per-criterion timeouts)
    4. Calculate composite score
    5. Cache and return result

    Returns complete analysis result dict.
    """
    start_time = time.time()

    # --- Cache check ---
    cache_key = f"analysis:{token_mint}"
    cached = cache.get(cache_key)
    if cached:
        cached["from_cache"] = True
        return cached

    # --- Phase 1: Parallel data fetch ---
    timeout = settings.analysis_timeout_seconds

    try:
        dex_data, asset_data, top_holders, supply_data, account_info = (
            await asyncio.wait_for(
                asyncio.gather(
                    get_token_data(token_mint),
                    get_asset(token_mint),
                    get_token_largest_accounts(token_mint),
                    get_token_supply(token_mint),
                    _safe_get_account_info(token_mint),
                    return_exceptions=True,
                ),
                timeout=timeout,
            )
        )
    except asyncio.TimeoutError:
        logger.warning(f"Data fetch timeout for {token_mint}")
        dex_data = asset_data = top_holders = supply_data = account_info = None

    # Handle exceptions from gather — replace with None and log
    for label, val in [
        ("DexScreener", dex_data), ("Helius", asset_data),
        ("Top holders", top_holders), ("Supply", supply_data),
        ("Account info", account_info),
    ]:
        if isinstance(val, Exception):
            logger.warning(f"{label} error: {val}")
    if isinstance(dex_data, Exception):
        dex_data = None
    if isinstance(asset_data, Exception):
        asset_data = None
    if isinstance(top_holders, Exception):
        top_holders = None
    if isinstance(supply_data, Exception):
        supply_data = None
    if isinstance(account_info, Exception):
        account_info = None

    # Get total supply for calculations
    total_supply = 0.0
    if supply_data and isinstance(supply_data, dict):
        total_supply = float(supply_data.get("uiAmount", 0) or 0)

    # Get creator address
    creator = None
    try:
        creator = await get_asset_creator(token_mint)
    except Exception as e:
        logger.warning(f"Creator fetch error: {e}")

    # Detect Pump.fun token (multiple signals)
    is_pumpfun = _detect_pumpfun(dex_data, asset_data)

    # Extract token metadata for social checks (Helius + DexScreener fallback)
    token_metadata = _extract_social_metadata(asset_data)
    dex_socials = extract_social_data(dex_data)
    for key in ("twitter", "telegram", "website"):
        if not token_metadata.get(key) and dex_socials.get(key):
            token_metadata[key] = dex_socials[key]
    token_name = token_metadata.get("name", "Unknown")
    token_symbol = token_metadata.get("symbol", "???")

    # --- Phase 2: Score all criteria in parallel (per-criterion timeouts) ---
    criteria_names = [
        "contract", "liquidity", "holders", "dev_wallet",
        "volume", "social", "metadata", "smart_money",
    ]

    results = await asyncio.gather(
        _safe_criterion("contract", score_contract(
            token_mint, account_info=account_info, asset_data=asset_data)),
        _safe_criterion("liquidity", score_liquidity(
            dex_data, is_pumpfun=is_pumpfun)),
        _safe_criterion("holders", score_holders(
            token_mint, dex_data, top_holders=top_holders,
            supply_data=supply_data, is_pumpfun=is_pumpfun)),
        _safe_criterion("dev_wallet", score_dev_wallet(
            creator, dex_data=dex_data)),
        _safe_criterion("volume", score_volume(dex_data)),
        _safe_criterion("social", score_social(token_metadata)),
        _safe_criterion("metadata", score_metadata(asset_data)),
        _safe_criterion("smart_money", score_smart_money(
            token_mint, top_holders, total_supply)),
    )

    criteria_results = dict(zip(criteria_names, results))

    # --- Phase 3: Calculate composite score ---
    analysis = calculate_composite_score(criteria_results)

    # Add metadata to result
    elapsed = round(time.time() - start_time, 1)
    market = extract_market_data(dex_data)

    analysis.update({
        "token_mint": token_mint,
        "token_name": token_name,
        "token_symbol": token_symbol,
        "price_usd": market["price_usd"],
        "market_cap": market["market_cap"],
        "liquidity_usd": market["liquidity_usd"],
        "volume_24h": market["volume_24h"],
        "pair_address": market["pair_address"],
        "dex_id": market["dex_id"],
        "creator_address": creator,
        "analysis_time": elapsed,
        "from_cache": False,
    })

    # --- Cache the result ---
    cache.set(cache_key, analysis, ttl=CACHE_TTL_ANALYSIS)

    logger.info(
        f"Analyzed {token_symbol} ({token_mint[:8]}...): "
        f"score={analysis['total_score']}, time={elapsed}s"
    )

    return analysis


def _detect_pumpfun(
    dex_data: Optional[dict], asset_data: Optional[dict]
) -> bool:
    """Detect if a token is a Pump.fun token from multiple signals."""
    # Signal 1: DexScreener reports dexId as "pumpfun"
    if dex_data and dex_data.get("primary_pair"):
        if dex_data["primary_pair"].get("dexId") == "pumpfun":
            return True

    # Signal 2: Helius DAS authorities contain Pump.fun address
    if asset_data:
        pf_addrs = {PUMP_FUN_AUTHORITY, PUMP_FUN_PROGRAM}
        for auth in asset_data.get("authorities", []):
            if auth.get("address") in pf_addrs:
                return True

        # Signal 3: Metadata URI points to Pump.fun / IPFS (common for Pump.fun)
        json_uri = asset_data.get("content", {}).get("json_uri", "")
        if "pump.fun" in json_uri:
            return True

    return False


async def _safe_get_account_info(token_mint: str):
    """Fetch raw account info for contract scoring (pre-fetch in Phase 1)."""
    from data.solana_rpc import get_account_info
    return await get_account_info(token_mint)


async def quick_score(token_mint: str) -> dict:
    """Get a quick score with minimal checks (contract + liquidity + holders only).

    Faster than full analysis — for /quick command.
    """
    cache_key = f"quick:{token_mint}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    start_time = time.time()

    # Only fetch essential data
    dex_data, top_holders, supply_data = await asyncio.gather(
        get_token_data(token_mint),
        get_token_largest_accounts(token_mint),
        get_token_supply(token_mint),
        return_exceptions=True,
    )

    if isinstance(dex_data, Exception):
        dex_data = None
    if isinstance(top_holders, Exception):
        top_holders = None
    if isinstance(supply_data, Exception):
        supply_data = None

    # Detect Pump.fun for quick score too
    try:
        asset = await get_asset(token_mint)
    except Exception:
        asset = None
    is_pumpfun = _detect_pumpfun(dex_data, asset)

    # Score only critical criteria (per-criterion timeouts)
    contract_result, liquidity_result, holders_result = await asyncio.gather(
        _safe_criterion("contract", score_contract(token_mint)),
        _safe_criterion("liquidity", score_liquidity(
            dex_data, is_pumpfun=is_pumpfun)),
        _safe_criterion("holders", score_holders(
            token_mint, dex_data, top_holders=top_holders,
            supply_data=supply_data, is_pumpfun=is_pumpfun)),
    )

    # Quick composite (equal weight for 3 criteria)
    scores = [r.score for r in [contract_result, liquidity_result, holders_result]]
    quick = round(sum(scores) / len(scores), 1) if scores else 25

    market = extract_market_data(dex_data)
    token_metadata = _extract_social_metadata(asset)
    dex_socials = extract_social_data(dex_data)
    for key in ("twitter", "telegram", "website"):
        if not token_metadata.get(key) and dex_socials.get(key):
            token_metadata[key] = dex_socials[key]

    result = {
        "total_score": quick,
        "token_mint": token_mint,
        "token_name": token_metadata.get("name", "Unknown"),
        "token_symbol": token_metadata.get("symbol", "???"),
        "price_usd": market["price_usd"],
        "market_cap": market["market_cap"],
        "liquidity_usd": market["liquidity_usd"],
        "analysis_time": round(time.time() - start_time, 1),
        "is_quick": True,
    }

    # Import here to avoid circular
    from analysis.scoring import get_risk_label
    risk = get_risk_label(quick)
    result.update({
        "risk_label": risk["label"],
        "risk_emoji": risk["emoji"],
        "risk_desc": risk["desc"],
    })

    cache.set(cache_key, result, ttl=CACHE_TTL_ANALYSIS)
    return result


def _extract_social_metadata(asset_data: Optional[dict]) -> dict:
    """Extract social links and token info from Helius asset data."""
    if not asset_data:
        return {}

    content = asset_data.get("content", {})
    metadata = content.get("metadata", {})
    links = content.get("links", {})

    result = {
        "name": metadata.get("name", "") or asset_data.get("name", ""),
        "symbol": metadata.get("symbol", "") or asset_data.get("symbol", ""),
        "description": metadata.get("description", ""),
    }

    # Extract social links from various possible locations
    # Pump.fun tokens store these in metadata attributes
    attributes = metadata.get("attributes", [])
    if isinstance(attributes, list):
        for attr in attributes:
            if isinstance(attr, dict):
                trait = attr.get("trait_type", "").lower()
                value = attr.get("value", "")
                if "twitter" in trait or "x.com" in trait:
                    result["twitter"] = value
                elif "telegram" in trait:
                    result["telegram"] = value
                elif "website" in trait or "url" in trait:
                    result["website"] = value

    # Also check links object
    if links:
        if not result.get("twitter"):
            result["twitter"] = links.get("twitter") or links.get("x")
        if not result.get("telegram"):
            result["telegram"] = links.get("telegram")
        if not result.get("website"):
            result["website"] = links.get("website") or links.get("external_url")

    # Check top-level metadata fields
    if not result.get("website"):
        result["website"] = metadata.get("external_url")

    return result
