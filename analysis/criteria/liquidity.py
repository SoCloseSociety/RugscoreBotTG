"""Criterion 2 — Liquidity Health (weight: 15%).

Checks LP liquidity depth, MCap/Liq ratio, LP burn status, pair age.
Data source: DexScreener API (FREE, no key).
"""

import asyncio
import logging
import time
from typing import Optional

from analysis.criteria import CriterionResult
from config.constants import (
    LIQUIDITY_EXCELLENT, LIQUIDITY_GOOD, LIQUIDITY_LOW,
    MCAP_LIQ_RATIO_HEALTHY, MCAP_LIQ_RATIO_CAUTION,
    BURN_ADDRESSES,
)
from data.dexscreener import extract_market_data
from data.solana_rpc import get_token_largest_accounts, get_token_account_owner
from utils.helpers import clamp, format_number

logger = logging.getLogger(__name__)


async def score_liquidity(
    dex_data: Optional[dict], is_pumpfun: bool = False
) -> CriterionResult:
    """Analyze liquidity health for a token.

    Checks:
    - liquidity_usd: Total liquidity in USD (+30 excellent, +20 good, +5 low)
    - mcap_to_liq_ratio: MCap / Liquidity (+25 healthy, +15 caution, +0 dangerous)
    - lp_burned: LP tokens sent to burn address (+30 burned, +15 partial, +0 none)
    - pair_age: How old is the pair (+15 established, +10 recent, +0 very new)
    """
    market = extract_market_data(dex_data)
    score = 0.0
    flags = []
    details = {}

    liq = market["liquidity_usd"]
    mcap = market["market_cap"]

    # Also detect from DexScreener dex_id if not already flagged
    if not is_pumpfun:
        dex_id = market.get("dex_id", "")
        if dex_id == "pumpfun":
            is_pumpfun = True

    # --- Liquidity depth ---
    details["liquidity_usd"] = liq
    if liq is not None and liq > 0:
        if liq >= LIQUIDITY_EXCELLENT:
            score += 30
            flags.append(f"\u2705 Liquidity {format_number(liq)} (excellent)")
        elif liq >= LIQUIDITY_GOOD:
            score += 20
            flags.append(f"\u2705 Liquidity {format_number(liq)} (good)")
        elif liq >= LIQUIDITY_LOW:
            score += 10
            flags.append(f"\u26a0\ufe0f Liquidity {format_number(liq)} (low)")
        else:
            score += 5
            flags.append(f"\u274c Liquidity {format_number(liq)} (very low)")
    elif is_pumpfun:
        score += 10
        flags.append("\u2139\ufe0f Pump.fun bonding curve \u2014 liquidity managed by AMM")
    elif mcap and mcap > 0:
        score += 5
        flags.append("\u26a0\ufe0f No liquidity pool detected")
    else:
        flags.append("\u274c No DEX data \u2014 token may not be tradeable")
        score += 5

    # --- MCap to Liquidity ratio ---
    if liq and mcap and liq > 0:
        ratio = mcap / liq
        details["mcap_liq_ratio"] = round(ratio, 1)
        if ratio < MCAP_LIQ_RATIO_HEALTHY:
            score += 25
            flags.append(f"\u2705 MCap/Liq ratio: {ratio:.1f}x (healthy)")
        elif ratio < MCAP_LIQ_RATIO_CAUTION:
            score += 15
            flags.append(f"\u26a0\ufe0f MCap/Liq ratio: {ratio:.1f}x (caution)")
        else:
            flags.append(f"\u274c MCap/Liq ratio: {ratio:.1f}x (dangerous)")
    else:
        score += 10  # Neutral
        details["mcap_liq_ratio"] = None

    # --- LP burn check ---
    if is_pumpfun:
        # Pump.fun uses bonding curve mechanics, no LP to burn
        score += 10
        flags.append("\u2139\ufe0f Pump.fun \u2014 bonding curve mechanics")
        details["lp_burned_pct"] = None
    else:
        lp_burned_pct = await _check_lp_burn(dex_data)
        details["lp_burned_pct"] = lp_burned_pct
        if lp_burned_pct is not None:
            if lp_burned_pct >= 95:
                score += 30
                flags.append(f"\u2705 LP burned {lp_burned_pct:.0f}%")
            elif lp_burned_pct >= 50:
                score += 15
                flags.append(f"\u26a0\ufe0f LP partially burned {lp_burned_pct:.0f}%")
            else:
                flags.append(f"\u274c LP not burned ({lp_burned_pct:.0f}%)")
        else:
            score += 10  # Can't determine — neutral
            flags.append("\u26a0\ufe0f LP burn status unknown")

    # --- Pair age ---
    pair_created = market["pair_created_at"]
    if pair_created:
        try:
            age_seconds = time.time() - (pair_created / 1000)  # DexScreener uses ms
            age_hours = age_seconds / 3600
            details["pair_age_hours"] = round(age_hours, 1)
            if age_hours > 24:
                score += 15
                flags.append(f"\u2705 Pair age: {age_hours:.0f}h (established)")
            elif age_hours > 1:
                score += 10
                flags.append(f"\u26a0\ufe0f Pair age: {age_hours:.1f}h (recent)")
            else:
                score += 0
                flags.append(f"\u274c Pair age: {age_hours * 60:.0f}m (just launched)")
        except (TypeError, ValueError):
            score += 5
    else:
        score += 5

    return CriterionResult(
        name="Liquidity",
        score=clamp(score),
        flags=flags,
        details=details,
    )


async def _check_lp_burn(dex_data: Optional[dict]) -> Optional[float]:
    """Check LP burn percentage.

    Queries top LP token holders and checks for known burn addresses.
    Uses parallel owner lookups for speed (max 3 holders).
    """
    if not dex_data or not dex_data.get("primary_pair"):
        return None

    pair = dex_data["primary_pair"]

    # Skip for Pump.fun bonding curve tokens
    if pair.get("dexId") == "pumpfun":
        return None

    # DexScreener sometimes includes liquidity lock/burn info
    liquidity_info = pair.get("liquidity", {})
    if "locked" in liquidity_info:
        locked = liquidity_info["locked"]
        # DexScreener returns either a boolean or a percentage float
        if isinstance(locked, bool):
            return 100.0 if locked else 0.0
        try:
            return float(locked)
        except (TypeError, ValueError):
            pass

    # Try to get LP mint and check holders
    lp_address = pair.get("pairAddress")
    if not lp_address:
        return None

    try:
        lp_holders = await get_token_largest_accounts(lp_address)
        if not lp_holders:
            return None

        total = sum(float(h.get("uiAmount", 0) or 0) for h in lp_holders)
        if total == 0:
            return None

        # Check top 3 holders in PARALLEL for speed
        burn_set = set(BURN_ADDRESSES)
        top_lp = [
            h for h in lp_holders[:3]
            if float(h.get("uiAmount", 0) or 0) > 0
        ]

        owners = await asyncio.gather(
            *[get_token_account_owner(h.get("address", "")) for h in top_lp],
            return_exceptions=True,
        )

        burned = 0.0
        for holder, owner in zip(top_lp, owners):
            if isinstance(owner, Exception) or not owner:
                continue
            amount = float(holder.get("uiAmount", 0) or 0)
            if owner in burn_set:
                burned += amount

        return (burned / total) * 100
    except Exception as e:
        logger.debug(f"LP burn check failed: {e}")
        return None
