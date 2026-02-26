"""Criterion 5 — Volume Authenticity (weight: 10%).

Detects wash trading, analyzes buy/sell ratio, volume consistency.
Data source: DexScreener API (FREE, no key).
"""

import logging
from typing import Optional

from analysis.criteria import CriterionResult
from config.constants import (
    VOLUME_TX_ACTIVE, VOLUME_TX_MODERATE,
    BUY_SELL_RATIO_MIN, BUY_SELL_RATIO_MAX,
    VOLUME_MCAP_HEALTHY_MIN, VOLUME_MCAP_HEALTHY_MAX, VOLUME_MCAP_SUSPICIOUS,
)
from data.dexscreener import extract_market_data
from utils.helpers import clamp, format_number

logger = logging.getLogger(__name__)


def _format_ratio(value: float) -> str:
    """Format a ratio with adaptive precision for display."""
    if value >= 1.0:
        return f"{value:.2f}x"
    elif value >= 0.01:
        return f"{value:.3f}x"
    else:
        return f"{value:.4f}x"


async def score_volume(dex_data: Optional[dict]) -> CriterionResult:
    """Analyze volume authenticity for a token.

    Checks:
    - unique_transactions: Buy + Sell count in 24h (+25/+15/+5)
    - buy_sell_ratio: buys / total (+25 balanced, +10 one-sided)
    - volume_to_mcap: 24h volume / mcap (+25 healthy, +5 suspicious)
    - volume_consistency: h1 vs h6 vs h24 growth (+25 organic, +10 spike)
    """
    market = extract_market_data(dex_data)
    score = 0.0
    flags = []
    details = {}

    buys = market["txns_24h_buys"]
    sells = market["txns_24h_sells"]
    total_txns = buys + sells

    vol_24h = market["volume_24h"]
    vol_6h = market["volume_6h"]
    vol_1h = market["volume_1h"]
    mcap = market["market_cap"]

    # --- Unique transactions ---
    details["total_txns_24h"] = total_txns
    details["buys_24h"] = buys
    details["sells_24h"] = sells

    if total_txns >= VOLUME_TX_ACTIVE:
        score += 25
        flags.append(f"\u2705 {total_txns:,} trades (24h) \u2014 active")
    elif total_txns >= VOLUME_TX_MODERATE:
        score += 15
        flags.append(f"\u26a0\ufe0f {total_txns:,} trades (24h) \u2014 moderate")
    elif total_txns > 0:
        score += 5
        flags.append(f"\u274c {total_txns:,} trades (24h) \u2014 low activity")
    else:
        # Zero trades: brand new token or no DEX data — both are red flags
        has_any_data = bool(vol_24h or mcap)
        if has_any_data:
            score += 5
            flags.append("\u274c 0 trades (24h) \u2014 no activity despite listing")
        else:
            score += 5
            flags.append("\u274c No trading data \u2014 token not yet on DEX")

    # --- Buy/sell ratio ---
    if total_txns > 0:
        buy_ratio = buys / total_txns
        details["buy_sell_ratio"] = round(buy_ratio, 2)
        if BUY_SELL_RATIO_MIN <= buy_ratio <= BUY_SELL_RATIO_MAX:
            score += 25
            flags.append(f"\u2705 Buy/sell ratio balanced ({buy_ratio:.0%})")
        else:
            score += 10
            direction = "buy-heavy" if buy_ratio > BUY_SELL_RATIO_MAX else "sell-heavy"
            flags.append(f"\u26a0\ufe0f Buy/sell ratio {direction} ({buy_ratio:.0%})")
    else:
        score += 5
        details["buy_sell_ratio"] = None

    # --- Volume to MCap ratio ---
    if vol_24h and mcap and mcap > 0:
        vol_mcap = vol_24h / mcap
        details["volume_mcap_ratio"] = round(vol_mcap, 4)
        ratio_str = _format_ratio(vol_mcap)
        if VOLUME_MCAP_HEALTHY_MIN <= vol_mcap <= VOLUME_MCAP_HEALTHY_MAX:
            score += 25
            flags.append(f"\u2705 Volume/MCap: {ratio_str} (healthy)")
        elif vol_mcap > VOLUME_MCAP_SUSPICIOUS:
            # Possible wash trading if high volume but low unique transactions
            if total_txns < VOLUME_TX_MODERATE:
                score += 0
                flags.append(f"\u274c Volume/MCap: {ratio_str} \u2014 likely wash trading")
            else:
                score += 10
                flags.append(f"\u26a0\ufe0f Volume/MCap: {ratio_str} (high)")
        else:
            score += 15
            flags.append(f"\u26a0\ufe0f Volume/MCap: {ratio_str}")
    else:
        score += 15  # Neutral for new tokens — don't penalize
        details["volume_mcap_ratio"] = None

    # --- Volume consistency ---
    if vol_1h and vol_6h and vol_24h and vol_24h > 0:
        # Check if volume is growing organically or spiking
        h1_ratio = vol_1h / (vol_24h / 24) if vol_24h > 0 else 0
        details["volume_spike_ratio"] = round(h1_ratio, 2)

        if 0.5 <= h1_ratio <= 3.0:
            score += 25
            flags.append("\u2705 Volume growth consistent")
        elif h1_ratio > 5.0:
            score += 10
            flags.append("\u26a0\ufe0f Sudden volume spike detected")
        else:
            score += 15
            flags.append("\u26a0\ufe0f Volume declining")
    else:
        score += 10

    return CriterionResult(
        name="Volume",
        score=clamp(score),
        flags=flags,
        details=details,
    )
