"""Handler for /stats command — ADMIN ONLY — bot statistics."""

import logging
import time as _time
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy import select, func, and_

from config.settings import settings
from database.db import async_session
from database.models import User, TokenAnalysis, Watchlist
from data.cache import cache

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


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats — admin-only bot statistics dashboard."""
    user = update.effective_user
    if not user or not settings.is_admin(user.id):
        await update.message.reply_text("\u26d4 Admin only ser.")
        return

    try:
        now = datetime.utcnow()
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)

        async with async_session() as session:
            # Total users
            total_users = (await session.execute(
                select(func.count(User.id))
            )).scalar() or 0

            # New users last 24h
            new_users_24h = (await session.execute(
                select(func.count(User.id)).where(User.created_at >= last_24h)
            )).scalar() or 0

            # Active users last 7d
            active_7d = (await session.execute(
                select(func.count(User.id)).where(User.last_active >= last_7d)
            )).scalar() or 0

            # Total analyses
            total_analyses = (await session.execute(
                select(func.count(TokenAnalysis.id))
            )).scalar() or 0

            # Analyses last 24h
            analyses_24h = (await session.execute(
                select(func.count(TokenAnalysis.id)).where(
                    TokenAnalysis.analyzed_at >= last_24h
                )
            )).scalar() or 0

            # Unique tokens analyzed
            total_unique = (await session.execute(
                select(func.count(func.distinct(TokenAnalysis.contract_address)))
            )).scalar() or 0

            # Average score
            average = (await session.execute(
                select(func.avg(TokenAnalysis.total_score))
            )).scalar()
            avg_str = f"{average:.1f}" if average else "N/A"

            # Score distribution
            safu = (await session.execute(
                select(func.count(TokenAnalysis.id)).where(
                    TokenAnalysis.total_score >= 90
                )
            )).scalar() or 0

            danger = (await session.execute(
                select(func.count(TokenAnalysis.id)).where(
                    TokenAnalysis.total_score < 25
                )
            )).scalar() or 0

            # Active watchlist entries
            total_watches = (await session.execute(
                select(func.count(Watchlist.id))
            )).scalar() or 0

            # Top scanner (most scans)
            top_user_result = await session.execute(
                select(User.username, User.total_scans)
                .where(User.total_scans > 0)
                .order_by(User.total_scans.desc())
                .limit(1)
            )
            top_user = top_user_result.first()

        top_scanner = f"@{top_user[0]} ({top_user[1]:,})" if top_user and top_user[0] else "N/A"

        # Uptime + cache
        start_time = context.bot_data.get("start_time", _time.time())
        uptime_str = _format_uptime(int(_time.time() - start_time))
        cache_size = cache.size

        sep = "\u2501" * 22
        text = (
            f"{sep}\n"
            f" \U0001f4ca ADMIN STATS\n"
            f"{sep}\n"
            f"\U0001f3e5 Uptime: {uptime_str} \u2022 \U0001f4be Cache: {cache_size}\n\n"
            f"\U0001f465 {total_users:,} users \u2022 \U0001f195 {new_users_24h:,} new (24h)\n"
            f"\u26a1 {active_7d:,} active (7d) \u2022 \U0001f451 {top_scanner}\n\n"
            f"\U0001f50d {total_analyses:,} scans \u2022 \U0001f4c8 {analyses_24h:,} (24h)\n"
            f"\U0001f4b0 {total_unique:,} tokens \u2022 Avg: {avg_str}\n\n"
            f"\U0001f7e2 SAFU: {safu:,} \u2022 \u26d4 Rug: {danger:,}\n"
            f"\U0001f440 {total_watches:,} watches\n"
            f"{sep}"
        )

        logger.info(f"[ADMIN] @{user.username} viewed stats")
        await update.message.reply_text(text)

    except Exception as e:
        logger.error(f"Stats error: {e}", exc_info=True)
        await update.message.reply_text("\u274c Failed to load statistics.")
