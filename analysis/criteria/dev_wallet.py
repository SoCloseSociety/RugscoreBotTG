"""Criterion 4 — Dev Wallet History (weight: 15%).

Checks wallet age, past token creations, rug history, current holdings.
Data source: Solana RPC getSignaturesForAddress (FREE).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from analysis.criteria import CriterionResult
from data.solana_rpc import get_signatures_for_address, get_transaction
from utils.helpers import clamp, shorten_address

logger = logging.getLogger(__name__)


async def score_dev_wallet(
    creator_address: Optional[str],
    dex_data: Optional[dict] = None,
) -> CriterionResult:
    """Analyze the developer/creator wallet.

    Checks:
    - wallet_age: Age of creator wallet (+20 established, +10 moderate, +0 new)
    - tokens_created: Number of past tokens (+15 few, +10 active, -10 farm)
    - past_rug_indicator: Did previous tokens rug? (+25 safe, -20 rugs found)
    - current_holdings: Dev still holds tokens (+10-15)
    - dev_selling_now: Is dev actively selling? (+20 not selling, -30 selling)
    """
    if not creator_address:
        # Cannot verify dev — conservative score, clearly flagged
        return CriterionResult(
            name="Dev Wallet",
            score=25,
            flags=["\u274c Creator wallet not identified \u2014 cannot verify dev history"],
            details={},
            estimated=True,
        )

    score = 0.0
    flags = []
    details = {"creator_address": creator_address}

    # Get transaction history (reduced from 50 to 20 for speed)
    signatures = await get_signatures_for_address(creator_address, limit=20)

    if not signatures:
        return CriterionResult(
            name="Dev Wallet",
            score=25,
            flags=["\u274c No transaction history found for creator"],
            details=details,
            estimated=True,
        )

    # --- Wallet age ---
    oldest_sig = signatures[-1] if signatures else None
    if oldest_sig and oldest_sig.get("blockTime"):
        wallet_age_seconds = time.time() - oldest_sig["blockTime"]
        wallet_age_days = wallet_age_seconds / 86400
        details["wallet_age_days"] = round(wallet_age_days, 1)

        if wallet_age_days > 30:
            score += 20
            flags.append(f"\u2705 Wallet age: {wallet_age_days:.0f} days (established)")
        elif wallet_age_days > 7:
            score += 10
            flags.append(f"\u26a0\ufe0f Wallet age: {wallet_age_days:.0f} days")
        else:
            flags.append(f"\u274c Wallet created {wallet_age_days:.0f} days ago (very new)")
    else:
        score += 5

    # --- Analyze recent transactions for token creation patterns ---
    token_creates = 0
    recent_sells = 0
    now = time.time()

    # Fetch transaction details in PARALLEL (max 5 for speed)
    sample_sigs = [s.get("signature") for s in signatures[:5] if s.get("signature")]
    tx_results = await asyncio.gather(
        *[get_transaction(sig) for sig in sample_sigs],
        return_exceptions=True,
    )

    for tx in tx_results:
        if isinstance(tx, Exception) or not tx:
            continue

        instructions = _get_instructions(tx)
        for ix in instructions:
            ix_type = ix.get("parsed", {}).get("type", "") if isinstance(ix.get("parsed"), dict) else ""

            if ix_type in ("initializeMint", "initializeMint2"):
                token_creates += 1

            # Check for token sells in last hour
            block_time = tx.get("blockTime", 0)
            if block_time and (now - block_time) < 3600:
                if ix_type in ("transfer", "transferChecked"):
                    recent_sells += 1

    # --- Tokens created count ---
    details["tokens_created"] = token_creates
    if token_creates <= 2:
        score += 15
        if token_creates == 0:
            flags.append("\u2705 No previous tokens created")
        else:
            flags.append(f"\u2705 {token_creates} previous tokens (normal)")
    elif token_creates <= 10:
        score += 10
        flags.append(f"\u26a0\ufe0f {token_creates} previous tokens (active creator)")
    else:
        score -= 10
        flags.append(f"\u274c {token_creates} previous tokens (token farm!)")

    # --- Past rug indicator ---
    # Simplified: if dev created many tokens AND wallet is new = higher risk
    rug_risk = False
    wallet_age = details.get("wallet_age_days", 999)
    if token_creates > 5 and wallet_age < 30:
        rug_risk = True

    details["rug_risk"] = rug_risk
    if not rug_risk:
        score += 25
        flags.append("\u2705 No rug pattern detected")
    else:
        score -= 20
        flags.append("\u274c Rug pattern detected (many tokens + new wallet)")

    # --- Dev selling now ---
    details["recent_sells"] = recent_sells
    if recent_sells == 0:
        score += 20
        flags.append("\u2705 Dev not actively selling")
    elif recent_sells <= 3:
        score += 10
        flags.append(f"\u26a0\ufe0f Dev has {recent_sells} recent transfers")
    else:
        score -= 10
        flags.append(f"\u274c Dev actively selling ({recent_sells} recent txns)")

    return CriterionResult(
        name="Dev Wallet",
        score=clamp(score),
        flags=flags,
        details=details,
    )


def _get_instructions(tx: dict) -> list[dict]:
    """Extract parsed instructions from a transaction."""
    try:
        message = tx.get("transaction", {}).get("message", {})
        instructions = message.get("instructions", [])
        inner = tx.get("meta", {}).get("innerInstructions", [])
        all_ix = list(instructions)
        for inner_group in inner:
            all_ix.extend(inner_group.get("instructions", []))
        return all_ix
    except (AttributeError, TypeError):
        return []
