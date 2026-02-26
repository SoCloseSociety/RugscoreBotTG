"""Inline mode handler — allows @YourBot <CA> in any Telegram chat.

This is the #1 feature for organic discoverability. When a user types
@YourBot followed by a Solana contract address in ANY chat
(even chats where the bot isn't a member), Telegram shows a quick score
result that can be shared inline. This makes the bot viral.
"""

import logging
from uuid import uuid4

from telegram import (
    Update,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import ContextTypes

from analysis.engine import quick_score
from bot.formatters.display import format_quick_score
from config.settings import settings
from utils.helpers import is_valid_solana_address, extract_solana_addresses

logger = logging.getLogger(__name__)


async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline queries: @YourBot <CA>.

    Shows a quick score article that can be shared into any chat.
    """
    query = update.inline_query
    if not query:
        return

    text = (query.query or "").strip()

    # If no query, show a helpful prompt
    if not text:
        await query.answer(
            results=[
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="\u26a1 RugScore \u2014 Paste a Solana CA",
                    description="Type a token contract address to get an instant safety score",
                    input_message_content=InputTextMessageContent(
                        message_text=(
                            "\u26a1 <b>RugScore \u2014 Degen Scanner</b>\n\n"
                            "Paste any Solana token CA to get an instant safety score!\n\n"
                            f"\U0001f449 @{settings.bot_username}"
                        ),
                        parse_mode="HTML",
                    ),
                )
            ],
            cache_time=300,
            is_personal=False,
        )
        return

    # Try to extract a Solana address from the query
    addresses = extract_solana_addresses(text)
    if not addresses and is_valid_solana_address(text):
        addresses = [text]

    if not addresses:
        await query.answer(
            results=[
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="\u274c Not a valid Solana address",
                    description="Paste a valid token contract address (32-44 chars, base58)",
                    input_message_content=InputTextMessageContent(
                        message_text="\u274c Invalid Solana address. Try again fren!",
                    ),
                )
            ],
            cache_time=10,
            is_personal=False,
        )
        return

    ca = addresses[0]

    try:
        result = await quick_score(ca)
        total = result.get("total_score") or 0
        name = result.get("token_name") or "Unknown"
        symbol = result.get("token_symbol") or "???"
        emoji = result.get("risk_emoji") or "\u26a0\ufe0f"
        label = result.get("risk_label") or "UNKNOWN"

        # Format the full result for the shared message
        msg_text = format_quick_score(result)
        msg_text += f"\n\n\U0001f916 Scanned via @{settings.bot_username}"

        # Deep link button so recipients can do a full scan
        deep_link = f"https://t.me/{settings.bot_username}?start=scan_{ca}"
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("\U0001f50d Full Scan", url=deep_link),
                InlineKeyboardButton(
                    "\u26a1 Try RugScore",
                    url=f"https://t.me/{settings.bot_username}",
                ),
            ]
        ])

        await query.answer(
            results=[
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title=f"{emoji} {name} (${symbol}) \u2014 {total:.0f}/100 {label}",
                    description=f"Score: {total:.0f}/100 \u2014 Tap to share in this chat",
                    input_message_content=InputTextMessageContent(
                        message_text=msg_text,
                        parse_mode="HTML",
                    ),
                    reply_markup=keyboard,
                )
            ],
            cache_time=60,
            is_personal=False,
        )

    except Exception as e:
        logger.error(f"Inline query failed for {ca}: {e}")
        deep_link = f"https://t.me/{settings.bot_username}?start=scan_{ca}"
        await query.answer(
            results=[
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title=f"\u26a0\ufe0f Scan failed \u2014 tap to try in DM",
                    description="Could not scan this token inline. Try in DM instead.",
                    input_message_content=InputTextMessageContent(
                        message_text=(
                            f"\u26a0\ufe0f Could not scan this token inline.\n\n"
                            f"\U0001f449 <a href=\"{deep_link}\">Tap here to scan in DM</a>"
                        ),
                        parse_mode="HTML",
                    ),
                )
            ],
            cache_time=10,
            is_personal=False,
        )
