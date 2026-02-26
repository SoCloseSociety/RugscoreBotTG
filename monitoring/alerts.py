"""Alert system — sends notifications for score changes and events."""

import logging
from typing import Optional

from utils.helpers import shorten_address, format_number

logger = logging.getLogger(__name__)


async def send_score_alert(
    bot,
    telegram_id: int,
    analysis: dict,
    old_score: Optional[float],
    new_score: float,
):
    """Send a score change alert to a user.

    Args:
        bot: The telegram Bot instance.
        telegram_id: User's Telegram ID.
        analysis: The analysis result dict.
        old_score: Previous score (None if first check).
        new_score: Current score.
    """
    name = analysis.get("token_name", "Unknown")
    symbol = analysis.get("token_symbol", "???")
    mint = analysis.get("token_mint", "")
    emoji = analysis.get("risk_emoji", "\u26a0\ufe0f")

    if old_score is not None:
        change = new_score - old_score
        direction = "\U0001f4c8" if change > 0 else "\U0001f4c9"
        change_str = f"{'+' if change > 0 else ''}{change:.0f}"

        text = (
            f"{direction} SCORE ALERT\n\n"
            f"{emoji} {name} (${symbol})\n"
            f"{shorten_address(mint)}\n\n"
            f"Score: {old_score:.0f} \u2192 {new_score:.0f} ({change_str})\n"
            f"Status: {analysis.get('risk_label', 'UNKNOWN')}\n\n"
            f"Use /scan {mint} for full analysis."
        )
    else:
        text = (
            f"\U0001f514 WATCHLIST UPDATE\n\n"
            f"{emoji} {name} (${symbol})\n"
            f"{shorten_address(mint)}\n\n"
            f"Score: {new_score:.0f}/100\n"
            f"Status: {analysis.get('risk_label', 'UNKNOWN')}\n\n"
            f"Use /scan {mint} for full analysis."
        )

    try:
        await bot.send_message(chat_id=telegram_id, text=text)
        logger.info(f"Alert sent to {telegram_id} for {symbol}")
    except Exception as e:
        logger.warning(f"Failed to send alert to {telegram_id}: {e}")


async def send_dev_sell_alert(
    bot,
    telegram_id: int,
    token_name: str,
    token_symbol: str,
    mint: str,
    sell_amount: float,
):
    """Send an alert when a dev wallet sells tokens."""
    text = (
        f"\U0001f6a8 DEV SELLING ALERT\n\n"
        f"{token_name} (${token_symbol})\n"
        f"{shorten_address(mint)}\n\n"
        f"Dev sold {format_number(sell_amount)}\n\n"
        f"Use /scan {mint} for updated analysis."
    )

    try:
        await bot.send_message(chat_id=telegram_id, text=text)
    except Exception as e:
        logger.warning(f"Failed to send dev sell alert to {telegram_id}: {e}")
