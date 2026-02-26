"""Handler for /trending command — real-time trending Solana tokens."""

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from data.dexscreener import get_trending_tokens
from bot.formatters.display import format_trending
from bot.group_guard import smart_reply, group_throttle

logger = logging.getLogger(__name__)


@group_throttle
async def trending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /trending — show top trending Solana tokens from DexScreener."""
    msg = await smart_reply(update, "\U0001f525 Fetching trending tokens...")

    try:
        tokens = await get_trending_tokens(limit=10)

        if not tokens:
            await msg.edit_text(
                "No trending Solana tokens right now.\n"
                "Try again in a few minutes!"
            )
            return

        text = format_trending(tokens)

        # Build inline buttons: each trending token gets a quick-scan button
        buttons = []
        for t in tokens[:5]:
            symbol = t.get("token_symbol", "???")
            ca = t.get("contract_address", "")
            if ca:
                buttons.append([
                    InlineKeyboardButton(
                        f"\U0001f50d Scan ${symbol}",
                        callback_data=f"scan_{ca}",
                    )
                ])

        keyboard = InlineKeyboardMarkup(buttons) if buttons else None
        await msg.edit_text(text, parse_mode="HTML", reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Trending error: {e}", exc_info=True)
        await msg.edit_text("\u274c Failed to load trending data.")
