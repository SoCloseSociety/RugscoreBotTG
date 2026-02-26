"""Handler for /quick command — fast score only."""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from analysis.engine import quick_score
from bot.formatters.display import format_quick_score
from bot.keyboards.menus import quick_keyboard
from bot.group_guard import smart_reply, group_throttle
from utils.helpers import is_valid_solana_address

logger = logging.getLogger(__name__)


@group_throttle
async def quick_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /quick <CA> — fast score with minimal checks. Works in groups + DMs."""
    if not context.args:
        await smart_reply(
            update,
            "\u26a1 Usage: /quick <contract_address>\n"
            "Lightning fast score check \u26a1",
        )
        return

    token_mint = context.args[0].strip()

    if not is_valid_solana_address(token_mint):
        await smart_reply(update, "\u274c Invalid CA ser!")
        return

    status_msg = await smart_reply(update, "\u26a1 Speed-checking this one... \u26a1")

    try:
        result = await quick_score(token_mint)
        text = format_quick_score(result)
        keyboard = quick_keyboard(token_mint)
        await status_msg.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Quick scan failed for {token_mint}: {e}", exc_info=True)
        await status_msg.edit_text(
            f"\u274c Quick scan failed ser. Try /scan {token_mint}",
            parse_mode="HTML",
        )
