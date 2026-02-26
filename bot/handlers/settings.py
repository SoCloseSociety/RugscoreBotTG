"""Handler for /settings command — ADMIN ONLY — bot configuration."""

import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from sqlalchemy import select, func

from config.settings import settings
from database.db import async_session
from database.models import User, Watchlist
from bot.keyboards.menus import settings_keyboard

logger = logging.getLogger(__name__)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /settings — admin-only bot configuration panel."""
    user = update.effective_user
    if not user or not settings.is_admin(user.id):
        await update.message.reply_text("\u26d4 Admin only ser.")
        return

    # Gather current config
    async with async_session() as session:
        user_count = await session.execute(select(func.count(User.id)))
        total_users = user_count.scalar() or 0

        watch_count = await session.execute(select(func.count(Watchlist.id)))
        total_watches = watch_count.scalar() or 0

    admin_count = len(settings.admin_id_set)
    helius_status = "\u2705 configured" if settings.helius_api_key else "\u274c missing"
    rpc_short = settings.solana_rpc_url[:40] + "..." if len(settings.solana_rpc_url) > 40 else settings.solana_rpc_url

    # Get current admin's threshold
    threshold = 50
    try:
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == user.id)
            )
            db_user = result.scalar_one_or_none()
            if db_user:
                threshold = db_user.alert_threshold or 50
    except Exception as e:
        logger.warning(f"Failed to fetch admin threshold: {e}")

    sep = "\u2501" * 22
    text = (
        f"{sep}\n"
        f" \u2699\ufe0f ADMIN SETTINGS\n"
        f"{sep}\n"
        f"\U0001f916 @{settings.bot_username}\n"
        f"\U0001f465 {total_users:,} users \u2022 \U0001f440 {total_watches:,} watches\n"
        f"\U0001f6e1\ufe0f {admin_count} admin(s)\n\n"
        f"Helius: {helius_status}\n"
        f"RPC: {rpc_short}\n"
        f"Timeout: {settings.analysis_timeout_seconds}s \u2022 Cache: {settings.cache_ttl_seconds}s\n"
        f"Concurrent: {settings.max_concurrent_analyses} \u2022 Log: {settings.log_level}\n\n"
        f"Alert threshold: {threshold}/100\n"
        f"{sep}"
    )

    keyboard = settings_keyboard(threshold)
    await update.message.reply_text(text, reply_markup=keyboard)


async def callback_threshold(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle threshold change callbacks — admin only."""
    query = update.callback_query
    user = query.from_user

    if not settings.is_admin(user.id):
        await query.answer("\u26d4 Admin only", show_alert=True)
        return

    await query.answer()

    data = query.data
    if not data.startswith("threshold_"):
        return

    try:
        new_threshold = int(data.replace("threshold_", ""))
    except ValueError:
        return

    if not 0 <= new_threshold <= 100:
        await query.answer("\u274c Threshold must be 0-100", show_alert=True)
        return

    logger.info(f"[ADMIN] @{user.username} (ID:{user.id}) changed threshold to {new_threshold}")

    try:
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == user.id)
            )
            db_user = result.scalar_one_or_none()
            if db_user:
                db_user.alert_threshold = new_threshold
                await session.commit()
    except Exception as e:
        logger.error(f"Settings update error: {e}")

    sep = "\u2501" * 22
    text = (
        f"{sep}\n"
        f" \u2699\ufe0f ADMIN SETTINGS\n"
        f"{sep}\n"
        f"\u2705 Alert threshold: {new_threshold}\n"
        f"Tokens below {new_threshold}/100 trigger alerts.\n"
        f"{sep}"
    )

    keyboard = settings_keyboard(new_threshold)
    try:
        await query.edit_message_text(text, reply_markup=keyboard)
    except BadRequest:
        pass
