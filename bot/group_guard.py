"""Group chat support: detection helpers, per-group rate limiting, reply context."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from functools import wraps
from typing import Callable

from telegram import Update, Chat
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

# ─── Group detection ───


def is_group_chat(update: Update) -> bool:
    """Check if the update comes from a group or supergroup."""
    chat = update.effective_chat
    if not chat:
        return False
    return chat.type in (Chat.GROUP, Chat.SUPERGROUP)


def is_private_chat(update: Update) -> bool:
    """Check if the update comes from a private (DM) chat."""
    chat = update.effective_chat
    if not chat:
        return False
    return chat.type == Chat.PRIVATE


# ─── Reply helper ───


async def smart_reply(update: Update, text: str, **kwargs):
    """Send a reply — in groups, reply to the original message for context.

    In private chats, just sends a regular message.
    Returns the sent Message object.
    """
    reply_to = None
    if is_group_chat(update) and update.message:
        reply_to = update.message.message_id

    return await update.message.reply_text(
        text,
        reply_to_message_id=reply_to,
        **kwargs,
    )


# ─── Per-group rate limiter ───

# {chat_id: [timestamp, timestamp, ...]}
_group_usage: dict[int, list[float]] = defaultdict(list)

# Defaults: 10 commands per 60 seconds per group
GROUP_RATE_LIMIT = 10
GROUP_RATE_WINDOW = 60  # seconds


def _check_group_rate(chat_id: int) -> bool:
    """Check if a group is within rate limits. Returns True if allowed."""
    now = time.monotonic()
    timestamps = _group_usage[chat_id]

    # Prune old entries
    cutoff = now - GROUP_RATE_WINDOW
    _group_usage[chat_id] = [t for t in timestamps if t > cutoff]
    timestamps = _group_usage[chat_id]

    if len(timestamps) >= GROUP_RATE_LIMIT:
        return False

    timestamps.append(now)
    return True


def group_throttle(handler: Callable) -> Callable:
    """Decorator: apply per-group rate limiting. No-op for private chats.

    When rate-limited, sends a short notice and returns without executing.
    """

    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if is_group_chat(update):
            chat_id = update.effective_chat.id
            if not _check_group_rate(chat_id):
                # Silently drop or send a brief notice (only once per burst)
                logger.info(
                    f"Group {chat_id} rate-limited (>{GROUP_RATE_LIMIT}/{GROUP_RATE_WINDOW}s)"
                )
                # Send a gentle notice — but only reply, don't spam
                try:
                    await update.message.reply_text(
                        "\u23f3 Slow down fren! Too many requests in this group. "
                        "Try again in a minute.",
                        reply_to_message_id=update.message.message_id,
                    )
                except Exception:
                    pass
                return
        return await handler(update, context)

    return wrapper
