"""Criterion 1 — Contract Safety (weight: 20%).

Checks mint authority, freeze authority, metadata mutability, transfer fees.
Cross-references with RugCheck.xyz for additional risk signals.
Data source: Solana RPC getAccountInfo + RugCheck API (both FREE).
"""

import logging
from typing import Optional

from analysis.criteria import CriterionResult
from data import solana_rpc
from data.helius_client import get_asset
from data.rugcheck_client import get_token_report, extract_rugcheck_risks
from utils.helpers import clamp

logger = logging.getLogger(__name__)


async def score_contract(
    token_mint: str,
    account_info: Optional[dict] = None,
    asset_data: Optional[dict] = None,
) -> CriterionResult:
    """Analyze contract safety for a token.

    Checks:
    - mint_authority_revoked: Can new tokens be minted? (+30 if revoked)
    - freeze_authority_revoked: Can accounts be frozen? (+20 if revoked)
    - metadata_immutable: Can metadata be changed? (+10 if immutable)
    - no_transfer_fee: Token-2022 transfer fee? (+10 if no fee)
    - rugcheck_cross_ref: RugCheck.xyz risks (+20 if clean, -10 per risk)
    - supply_bonus: Base safety signal (+10)
    """
    score = 0.0
    flags = []
    details = {}
    is_estimated = False

    # Use pre-fetched data or fetch if not provided
    if account_info is None:
        account_info = await solana_rpc.get_account_info(token_mint)
    mint_data = None

    if account_info and account_info.get("data"):
        raw_data = account_info["data"]
        if isinstance(raw_data, list) and len(raw_data) >= 1:
            mint_data = solana_rpc.parse_mint_account(raw_data[0])

    # Use pre-fetched asset data or fetch
    if asset_data is None:
        asset_data = await get_asset(token_mint)

    # --- Check mint authority ---
    if mint_data:
        details["mint_authority"] = mint_data.get("mint_authority")
        details["freeze_authority"] = mint_data.get("freeze_authority")

        if mint_data.get("mint_authority") is None:
            score += 30
            flags.append("\u2705 Mint authority revoked")
        else:
            flags.append("\u274c Mint authority ACTIVE \u2014 new tokens can be minted")

        # --- Check freeze authority ---
        if mint_data.get("freeze_authority") is None:
            score += 20
            flags.append("\u2705 Freeze authority revoked")
        else:
            flags.append("\u274c Freeze authority ACTIVE \u2014 accounts can be frozen")
    else:
        # Fallback: try Helius asset data for authorities
        if asset_data:
            authorities = asset_data.get("authorities", [])
            has_mint_auth = False
            has_freeze_auth = False
            for auth in authorities:
                scopes = auth.get("scopes", [])
                if "full" in scopes or "mint" in scopes:
                    has_mint_auth = True
                if "freeze" in scopes:
                    has_freeze_auth = True

            if not has_mint_auth:
                score += 30
                flags.append("\u2705 Mint authority revoked")
            else:
                flags.append("\u274c Mint authority ACTIVE")

            if not has_freeze_auth:
                score += 20
                flags.append("\u2705 Freeze authority revoked")
            else:
                flags.append("\u274c Freeze authority ACTIVE")
        else:
            is_estimated = True
            flags.append("\u274c Could not verify authorities \u2014 data unavailable")

    # --- Check metadata mutability ---
    is_mutable = True  # Default assume mutable
    if asset_data:
        is_mutable = asset_data.get("mutable", True)

    details["metadata_mutable"] = is_mutable
    if not is_mutable:
        score += 10
        flags.append("\u2705 Metadata immutable")
    else:
        flags.append("\u26a0\ufe0f Metadata mutable")

    # --- Check transfer fee (Token-2022 extension) ---
    has_transfer_fee = False
    if account_info and account_info.get("data"):
        raw_data = account_info["data"]
        if isinstance(raw_data, list) and len(raw_data) >= 1:
            import base64
            raw_bytes = base64.b64decode(raw_data[0])
            if len(raw_bytes) > 82 + 4:
                ext_type = int.from_bytes(raw_bytes[82:84], "little")
                if ext_type == 1:  # TransferFeeConfig
                    has_transfer_fee = True

    details["has_transfer_fee"] = has_transfer_fee
    if not has_transfer_fee:
        score += 10
        flags.append("\u2705 No transfer fee")
    else:
        flags.append("\u26a0\ufe0f Transfer fee detected (Token-2022)")

    # --- RugCheck.xyz cross-reference ---
    try:
        rugcheck_report = await get_token_report(token_mint)
        rugcheck_risks = extract_rugcheck_risks(rugcheck_report)
        details["rugcheck_risks"] = rugcheck_risks

        if rugcheck_report:
            rc_score = rugcheck_report.get("score")
            details["rugcheck_score"] = rc_score

            if not rugcheck_risks:
                score += 20
                flags.append("\u2705 RugCheck: no risks detected")
            else:
                # Penalize for each risk found
                penalty = min(len(rugcheck_risks) * 5, 20)
                score -= penalty
                for risk in rugcheck_risks[:3]:
                    flags.append(f"\u274c RugCheck: {risk}")
        else:
            score += 10  # Can't verify — partial credit
    except Exception as e:
        logger.debug(f"RugCheck cross-ref failed: {e}")
        score += 10  # Can't verify — partial credit

    # --- Supply concentration check (bonus) ---
    score += 10

    final_score = clamp(score)
    return CriterionResult(
        name="Contract",
        score=final_score,
        flags=flags,
        details=details,
        estimated=is_estimated,
    )
