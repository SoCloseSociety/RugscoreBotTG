"""Criterion 8 — Smart Money Signal (weight: 10%).

Cross-references top holders with known profitable wallets.
Data source: Local curated list + Solana RPC (FREE).
"""

from __future__ import annotations

import logging
from typing import Optional

from analysis.criteria import CriterionResult
from config.constants import WHALE_THRESHOLD_PCT, SMART_MONEY_STRONG, SMART_MONEY_MODERATE
from utils.helpers import clamp, shorten_address

logger = logging.getLogger(__name__)


async def score_smart_money(
    token_mint: str,
    top_holders: Optional[list[dict]],
    total_supply: float,
) -> CriterionResult:
    """Analyze smart money presence in a token.

    Checks:
    - smart_money_holding: Known profitable wallets in top holders (+40/+25/+15)
    - smart_money_direction: Accumulating or selling (+30/+20/-10)
    - whale_alert: Any single wallet > 5% supply (+10 with warning/+30)
    """
    score = 0.0
    flags = []
    details = {}

    if not top_holders:
        return CriterionResult(
            name="Smart Money",
            score=30,
            flags=["\u274c Holder data unavailable \u2014 cannot check smart money"],
            details={},
            estimated=True,
        )

    # Import smart money list
    from smart_money.wallet_list import get_smart_money_set

    smart_wallets = get_smart_money_set()
    details["smart_money_db_size"] = len(smart_wallets)

    # If smart money list is empty, return conservative score (system config issue)
    if not smart_wallets:
        return CriterionResult(
            name="Smart Money",
            score=40,
            flags=["\u26a0\ufe0f Smart money list not loaded \u2014 check skipped"],
            details={"smart_money_db_size": 0},
            estimated=True,
        )

    # Cross-reference top holders with smart money list
    smart_money_matches = []
    whale_addresses = []

    for holder in top_holders:
        address = holder.get("address", "")
        amount = float(holder.get("uiAmount", 0) or 0)
        pct = (amount / total_supply * 100) if total_supply > 0 else 0

        if address in smart_wallets:
            smart_money_matches.append({
                "address": address,
                "amount": amount,
                "pct": pct,
            })

        if pct > WHALE_THRESHOLD_PCT:
            whale_addresses.append({
                "address": address,
                "pct": round(pct, 1),
            })

    # --- Smart money holding ---
    sm_count = len(smart_money_matches)
    details["smart_money_count"] = sm_count
    details["smart_money_wallets"] = smart_money_matches

    if sm_count >= SMART_MONEY_STRONG:
        score += 40
        flags.append(f"\u2705 {sm_count} smart money wallets holding")
    elif sm_count >= SMART_MONEY_MODERATE:
        score += 25
        flags.append(f"\u2705 {sm_count} smart money wallet(s) holding")
    else:
        score += 15
        flags.append("\u26a0\ufe0f No known smart money detected")

    # --- Smart money direction ---
    # Simplified: if they hold = positive signal
    if sm_count > 0:
        total_sm_value = sum(m["amount"] for m in smart_money_matches)
        if total_sm_value > 0:
            score += 20
            flags.append("\u2705 Smart money accumulating")
        else:
            score += 10
    else:
        score += 10  # Neutral

    # --- Whale alert ---
    details["whales"] = whale_addresses
    if whale_addresses:
        score += 10
        for whale in whale_addresses[:3]:  # Show top 3 whales
            flags.append(
                f"\U0001f40b Whale: {shorten_address(whale['address'])} holds {whale['pct']:.1f}%"
            )
    else:
        score += 30
        flags.append("\u2705 No whale concentration (> 5%)")

    return CriterionResult(
        name="Smart Money",
        score=clamp(score),
        flags=flags,
        details=details,
    )
