"""Admin-only handlers: broadcast, health check, cache management."""

import logging
import time as _time

from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy import select

from config.settings import settings
from database.db import async_session
from database.models import User
from data.cache import cache
from bot.jobs.channel_reports import post_trending_report, post_most_scanned_report

logger = logging.getLogger(__name__)


def _format_uptime(seconds: int) -> str:
    """Format seconds into human-readable uptime string."""
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /broadcast <message> — send a message to all registered users."""
    user = update.effective_user
    if not user or not settings.is_admin(user.id):
        await update.message.reply_text("\u26d4 Admin only ser.")
        return

    if not context.args:
        await update.message.reply_text(
            "\U0001f4e2 Usage: /broadcast <message>\n"
            "Sends a message to all registered users."
        )
        return

    message_text = " ".join(context.args)
    logger.info(f"[ADMIN] @{user.username} (ID:{user.id}) broadcasting: {message_text[:50]}...")

    status = await update.message.reply_text("\U0001f4e2 Broadcasting...")

    async with async_session() as session:
        result = await session.execute(select(User.telegram_id))
        user_ids = [row[0] for row in result.fetchall()]

    sent = 0
    failed = 0
    for tg_id in user_ids:
        try:
            await context.bot.send_message(
                chat_id=tg_id,
                text=f"\U0001f4e2 <b>Announcement</b>\n\n{message_text}",
                parse_mode="HTML",
            )
            sent += 1
        except Exception:
            failed += 1

    logger.info(f"[ADMIN] Broadcast done: {sent} sent, {failed} failed")
    await status.edit_text(
        f"\u2705 Broadcast complete\n"
        f"Sent: {sent} | Failed: {failed}"
    )


async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /health — show bot health status."""
    user = update.effective_user
    if not user or not settings.is_admin(user.id):
        await update.message.reply_text("\u26d4 Admin only ser.")
        return

    start_time = context.bot_data.get("start_time", _time.time())
    uptime_str = _format_uptime(int(_time.time() - start_time))
    cache_size = cache.size

    helius_ok = "\u2705" if settings.helius_api_key else "\u274c"
    rpc_ok = "\u2705" if settings.solana_rpc_url else "\u274c"

    sep = "\u2501" * 22
    text = (
        f"{sep}\n"
        f" \U0001f3e5 BOT HEALTH\n"
        f"{sep}\n"
        f"Status: \u2705 ONLINE\n"
        f"Uptime: {uptime_str}\n"
        f"Cache: {cache_size} entries\n\n"
        f"Helius API: {helius_ok}\n"
        f"Solana RPC: {rpc_ok}\n"
        f"Log level: {settings.log_level}\n"
        f"{sep}"
    )

    logger.info(f"[ADMIN] @{user.username} checked health")
    await update.message.reply_text(text)


async def testreports_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /testreports — manually trigger both channel reports to verify they work."""
    user = update.effective_user
    if not user or not settings.is_admin(user.id):
        await update.message.reply_text("\u26d4 Admin only ser.")
        return

    if not settings.channel_id:
        await update.message.reply_text(
            "\u274c CHANNEL_ID is not set in .env\n"
            "Add it and restart the bot."
        )
        return

    status = await update.message.reply_text(
        f"\U0001f50d Testing reports to {settings.channel_id}..."
    )

    results = []

    # Test trending report
    try:
        await post_trending_report(context)
        results.append("\u2705 Trending report sent")
    except Exception as e:
        results.append(f"\u274c Trending report failed: {e}")

    # Test most-scanned report
    try:
        await post_most_scanned_report(context)
        results.append("\u2705 Most-scanned report sent")
    except Exception as e:
        results.append(f"\u274c Most-scanned report failed: {e}")

    logger.info(f"[ADMIN] @{user.username} tested channel reports")
    await status.edit_text(
        f"\U0001f9ea <b>Report Test Results</b>\n\n"
        + "\n".join(results)
        + f"\n\nChannel: {settings.channel_id}",
        parse_mode="HTML",
    )


async def callback_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin panel button callbacks."""
    query = update.callback_query
    user = query.from_user

    if not settings.is_admin(user.id):
        await query.answer("\u26d4 Admin only", show_alert=True)
        return

    action = query.data

    if action == "admin_health":
        await query.answer()
        start_time = context.bot_data.get("start_time", _time.time())
        uptime_str = _format_uptime(int(_time.time() - start_time))
        text = (
            f"\U0001f3e5 Bot ONLINE\n"
            f"Uptime: {uptime_str}\n"
            f"Cache: {cache.size} entries"
        )
        await query.answer(text, show_alert=True)
        logger.info(f"[ADMIN] @{user.username} checked health via panel")

    elif action == "admin_clear_cache":
        old_size = cache.size
        cache.clear()
        logger.info(f"[ADMIN] @{user.username} cleared cache ({old_size} entries)")
        await query.answer(
            f"\u2705 Cache cleared ({old_size} entries)",
            show_alert=True,
        )

    elif action == "admin_broadcast":
        await query.answer(
            "\U0001f4e2 Use: /broadcast <message>",
            show_alert=True,
        )

    elif action == "admin_stats":
        await query.answer(
            "\U0001f4ca Use: /stats",
            show_alert=True,
        )

    else:
        await query.answer()
