"""Watchlist monitoring service — background polling for score changes."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from sqlalchemy import select

from database.db import async_session
from database.models import Watchlist, User
from analysis.engine import analyze_token
from monitoring.alerts import send_score_alert

logger = logging.getLogger(__name__)

WATCH_INTERVAL = 300  # Check every 5 minutes
SCORE_CHANGE_THRESHOLD = 10  # Alert on 10+ point change


class WatchlistMonitor:
    """Background service that periodically checks watched tokens."""

    def __init__(self, bot):
        self._bot = bot
        self._running = False
        self._task = None

    async def start(self):
        """Start the monitoring loop."""
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Watchlist monitor started")

    async def stop(self):
        """Stop the monitoring loop."""
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("Watchlist monitor stopped")

    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                await self._check_all_watched()
            except Exception as e:
                logger.error(f"Watchlist monitor error: {e}")
            await asyncio.sleep(WATCH_INTERVAL)

    async def _check_all_watched(self):
        """Check all watched tokens for score changes."""
        try:
            async with async_session() as session:
                result = await session.execute(
                    select(Watchlist, User)
                    .join(User, Watchlist.user_id == User.id)
                )
                watches = result.all()

            if not watches:
                return

            # Group by token to avoid duplicate analyses
            tokens: dict[str, list[tuple]] = {}
            for watch, user in watches:
                ca = watch.contract_address
                if ca not in tokens:
                    tokens[ca] = []
                tokens[ca].append((watch, user))

            # Analyze each unique token, collect score updates and alerts
            score_updates = {}  # {watch_id: new_score}
            alerts_to_send = []

            for ca, watch_users in tokens.items():
                try:
                    analysis = await analyze_token(ca)
                    new_score = analysis.get("total_score", 0)

                    for watch, user in watch_users:
                        old_score = watch.last_score
                        score_updates[watch.id] = new_score

                        # Check if alert needed
                        if old_score is not None:
                            change = new_score - old_score
                            if abs(change) >= SCORE_CHANGE_THRESHOLD:
                                alerts_to_send.append(
                                    (user.telegram_id, analysis, old_score, new_score)
                                )

                        # Also alert if score drops below user threshold
                        if new_score < (user.alert_threshold or 50) and (
                            old_score is None or old_score >= (user.alert_threshold or 50)
                        ):
                            alerts_to_send.append(
                                (user.telegram_id, analysis, old_score, new_score)
                            )

                except Exception as e:
                    logger.warning(f"Watch check failed for {ca}: {e}")

                # Small delay between tokens to avoid rate limits
                await asyncio.sleep(2)

            # Batch update all scores in a single DB session
            if score_updates:
                try:
                    async with async_session() as session:
                        for watch_id, new_score in score_updates.items():
                            db_watch = await session.get(Watchlist, watch_id)
                            if db_watch:
                                db_watch.last_score = new_score
                                db_watch.last_checked = datetime.utcnow()
                        await session.commit()
                except Exception as e:
                    logger.error(f"Batch score update failed: {e}")

            # Send alerts after DB update
            for tg_id, analysis, old, new in alerts_to_send:
                try:
                    await send_score_alert(self._bot, tg_id, analysis, old, new)
                except Exception as e:
                    logger.warning(f"Alert send failed for {tg_id}: {e}")

        except Exception as e:
            logger.error(f"Watchlist check error: {e}")
