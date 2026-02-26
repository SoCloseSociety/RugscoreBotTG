"""Criterion 3 — Holder Distribution (weight: 15%).

Checks top holder concentration, sniper detection, holder count.
Data source: Solana RPC getTokenLargestAccounts (FREE).
"""

from __future__ import annotations

import logging
from typing import Optional

from analysis.criteria import CriterionResult
from config.constants import (
    TOP10_CONCENTRATION_EXCELLENT, TOP10_CONCENTRATION_CAUTION,
    TOP1_HOLDER_EXCELLENT, TOP1_HOLDER_OK,
    HOLDER_COUNT_GOOD, HOLDER_COUNT_MODERATE, HOLDER_COUNT_LOW,
    KNOWN_EXCLUDE_ADDRESSES,
)
from data.solana_rpc import get_token_largest_accounts, get_token_supply
from data.helius_client import get_holder_count_estimate
from data.dexscreener import extract_market_data
from utils.helpers import clamp, format_percentage, shorten_address

logger = logging.getLogger(__name__)


async def score_holders(
    token_mint: str,
    dex_data: Optional[dict] = None,
    top_holders: Optional[list] = None,
    supply_data: Optional[dict] = None,
    is_pumpfun: bool = False,
) -> CriterionResult:
    """Analyze holder distribution for a token.

    Checks:
    - top10_concentration: % held by top 10 (excl. LP/burn) (+30/+15/+0)
    - top1_holder_pct: Largest single holder (+20/+10/+0)
    - holder_count: Total holders (+25/+15/+5)
    - sniper_detection: Top holders bought in first txns (+25/+0)
    """
    score = 0.0
    flags = []
    details = {}

    # Use pre-fetched data or fetch if not provided
    if top_holders is None:
        top_holders = await get_token_largest_accounts(token_mint)
    if supply_data is None:
        supply_data = await get_token_supply(token_mint)

    total_supply = 0.0
    if supply_data:
        total_supply = float(supply_data.get("uiAmount", 0) or 0)

    if not top_holders or total_supply == 0:
        # Fallback: use DexScreener data for a smarter estimate
        return _fallback_from_dex(dex_data, is_pumpfun=is_pumpfun)

    # Filter out known addresses (LP, burn, bonding curve)
    filtered_holders = []
    for holder in top_holders:
        address = holder.get("address", "")
        if address not in KNOWN_EXCLUDE_ADDRESSES:
            filtered_holders.append(holder)

    # --- Top 10 concentration ---
    top10 = filtered_holders[:10]
    top10_amount = sum(float(h.get("uiAmount", 0) or 0) for h in top10)
    top10_pct = (top10_amount / total_supply * 100) if total_supply > 0 else 0

    details["top10_concentration"] = round(top10_pct, 1)
    if top10_pct < TOP10_CONCENTRATION_EXCELLENT:
        score += 30
        flags.append(f"\u2705 Top 10 hold {top10_pct:.1f}% (distributed)")
    elif top10_pct < TOP10_CONCENTRATION_CAUTION:
        score += 15
        flags.append(f"\u26a0\ufe0f Top 10 hold {top10_pct:.1f}%")
    else:
        flags.append(f"\u274c Top 10 hold {top10_pct:.1f}% (concentrated)")

    # --- Top 1 holder ---
    if filtered_holders:
        top1_amount = float(filtered_holders[0].get("uiAmount", 0) or 0)
        top1_pct = (top1_amount / total_supply * 100) if total_supply > 0 else 0
        top1_address = filtered_holders[0].get("address", "")

        details["top1_holder_pct"] = round(top1_pct, 1)
        details["top1_holder_address"] = top1_address

        if top1_pct < TOP1_HOLDER_EXCELLENT:
            score += 20
            flags.append(f"\u2705 Largest holder: {top1_pct:.1f}%")
        elif top1_pct < TOP1_HOLDER_OK:
            score += 10
            flags.append(f"\u26a0\ufe0f Largest holder: {top1_pct:.1f}% ({shorten_address(top1_address)})")
        else:
            flags.append(f"\u274c Largest holder: {top1_pct:.1f}% ({shorten_address(top1_address)})")

    # --- Holder count ---
    holder_count = 0

    # Try Helius for accurate count
    try:
        holder_count = await get_holder_count_estimate(token_mint)
    except Exception:
        pass

    # Fallback to DexScreener maker count
    if holder_count == 0 and dex_data:
        market = extract_market_data(dex_data)
        holder_count = market.get("maker_count", 0)

    # Last resort: use the number of holders we got from top accounts
    if holder_count == 0:
        holder_count = len(top_holders)

    details["holder_count"] = holder_count
    if holder_count >= HOLDER_COUNT_GOOD:
        score += 25
        flags.append(f"\u2705 ~{holder_count:,} holders")
    elif holder_count >= HOLDER_COUNT_MODERATE:
        score += 15
        flags.append(f"\u26a0\ufe0f ~{holder_count:,} holders (moderate)")
    elif holder_count >= HOLDER_COUNT_LOW:
        score += 10
        flags.append(f"\u26a0\ufe0f ~{holder_count:,} holders (low)")
    else:
        score += 5
        flags.append(f"\u274c ~{holder_count:,} holders (very early)")

    # --- Sniper detection ---
    # Heuristic: if multiple top holders have very similar amounts, possible snipers
    sniper_detected = _detect_snipers(filtered_holders, total_supply)
    details["sniper_detected"] = sniper_detected
    if not sniper_detected:
        score += 25
        flags.append("\u2705 No sniper wallets detected")
    else:
        flags.append("\u274c Possible sniper wallets in top holders")

    return CriterionResult(
        name="Holders",
        score=clamp(score),
        flags=flags,
        details=details,
    )


def _fallback_from_dex(
    dex_data: Optional[dict], is_pumpfun: bool = False
) -> CriterionResult:
    """Estimate holder score from DexScreener data when RPC fails.

    Returns conservative scores — estimated data is always marked as such.
    """
    if not dex_data:
        if is_pumpfun:
            return CriterionResult(
                name="Holders",
                score=30,
                flags=[
                    "\u2139\ufe0f Pump.fun bonding curve \u2014 holder data limited",
                    "\u274c On-chain holder data unavailable",
                ],
                details={"is_pumpfun": True},
                estimated=True,
            )
        return CriterionResult(
            name="Holders",
            score=25,
            flags=["\u274c Holder data unavailable \u2014 cannot verify distribution"],
            details={},
            estimated=True,
        )

    market = extract_market_data(dex_data)
    makers = market.get("maker_count", 0) or 0
    buys = market.get("txns_24h_buys", 0) or 0
    sells = market.get("txns_24h_sells", 0) or 0
    total_txns = buys + sells

    score = 0.0
    flags = []

    # Estimate from maker count (unique traders) — capped lower than real data
    if makers >= 500:
        score += 40
        flags.append(f"\u26a0\ufe0f ~{makers:,} unique traders (estimated)")
    elif makers >= 100:
        score += 30
        flags.append(f"\u26a0\ufe0f ~{makers:,} unique traders (estimated)")
    elif makers >= 20:
        score += 20
        flags.append(f"\u26a0\ufe0f ~{makers:,} unique traders (low, estimated)")
    elif makers > 0:
        score += 10
        flags.append(f"\u274c ~{makers:,} unique traders (very low)")
    else:
        score += 5

    # Buy/sell ratio as health signal
    if total_txns > 0:
        buy_ratio = buys / total_txns
        if 0.4 <= buy_ratio <= 0.7:
            score += 15
            flags.append(f"\u2705 Balanced buy/sell ratio ({buys}/{sells})")
        elif buy_ratio > 0.7:
            score += 5
            flags.append(f"\u26a0\ufe0f Heavy buying ({buys}/{sells})")
        else:
            flags.append(f"\u274c Heavy selling ({buys}/{sells})")

    flags.append("\u26a0\ufe0f On-chain holder data unavailable (estimated from DEX)")

    return CriterionResult(
        name="Holders",
        score=clamp(score),
        flags=flags,
        details={"estimated_from_dex": True, "maker_count": makers},
        estimated=True,
    )


def _detect_snipers(holders: list[dict], total_supply: float) -> bool:
    """Detect potential sniper wallets.

    Heuristic: if 3+ top holders each hold very similar amounts (within 5%),
    it's suspicious as it suggests coordinated buying.
    """
    if len(holders) < 3 or total_supply == 0:
        return False

    amounts = [float(h.get("uiAmount", 0) or 0) for h in holders[:10]]
    if not amounts:
        return False

    # Check for clusters of similar amounts
    similar_count = 0
    for i in range(len(amounts)):
        for j in range(i + 1, len(amounts)):
            if amounts[j] == 0:
                continue
            ratio = amounts[i] / amounts[j] if amounts[j] > 0 else 0
            if 0.95 <= ratio <= 1.05:  # Within 5%
                similar_count += 1

    # If 3+ pairs are suspiciously similar
    return similar_count >= 3
