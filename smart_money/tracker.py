"""Smart money detection logic — cross-reference and tracking."""

from __future__ import annotations

import logging
from typing import Optional

from smart_money.wallet_list import get_smart_money_set
from data.solana_rpc import get_token_largest_accounts

logger = logging.getLogger(__name__)


async def find_smart_money_in_token(token_mint: str) -> list[dict]:
    """Find known smart money wallets among a token's top holders.

    Returns list of {address, amount, pct} for each smart money match.
    """
    smart_wallets = get_smart_money_set()
    if not smart_wallets:
        return []

    top_holders = await get_token_largest_accounts(token_mint)
    if not top_holders:
        return []

    matches = []
    for holder in top_holders:
        address = holder.get("address", "")
        if address in smart_wallets:
            matches.append({
                "address": address,
                "amount": float(holder.get("uiAmount", 0) or 0),
            })

    return matches


async def check_smart_money_activity(
    token_mint: str, top_holders: Optional[list[dict]] = None
) -> dict:
    """Check smart money activity for a token.

    Returns summary of smart money presence and direction.
    """
    smart_wallets = get_smart_money_set()

    if top_holders is None:
        top_holders = await get_token_largest_accounts(token_mint) or []

    sm_holders = []
    for holder in top_holders:
        address = holder.get("address", "")
        if address in smart_wallets:
            sm_holders.append({
                "address": address,
                "amount": float(holder.get("uiAmount", 0) or 0),
            })

    return {
        "count": len(sm_holders),
        "wallets": sm_holders,
        "total_held": sum(h["amount"] for h in sm_holders),
        "signal": "strong" if len(sm_holders) >= 3 else "moderate" if sm_holders else "none",
    }
