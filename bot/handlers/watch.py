"""Handlers for /watch, /unwatch, /watchlist commands."""

import logging
from datetime import datetime

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes
from sqlalchemy import select, and_

from database.db import async_session
from database.models import User, Watchlist, TokenAnalysis
from bot.formatters.display import format_watchlist
from bot.keyboards.menus import watchlist_keyboard
from bot.group_guard import smart_reply, group_throttle
from utils.helpers import is_valid_solana_address, shorten_address

logger = logging.getLogger(__name__)

MAX_WATCHLIST_SIZE = 20


@group_throttle
async def watch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /watch <CA> — add a token to the user's watchlist."""
    if not context.args:
        await smart_reply(
            update,
            "Usage: /watch <contract_address>\n"
            "Add a token to your watchlist for score change alerts.",
        )
        return

    token_mint = context.args[0].strip()
    if not is_valid_solana_address(token_mint):
        await smart_reply(update, "\u274c Invalid Solana address.")
        return

    user = update.effective_user

    try:
        async with async_session() as session:
            # Get or create user
            result = await session.execute(
                select(User).where(User.telegram_id == user.id)
            )
            db_user = result.scalar_one_or_none()
            if not db_user:
                db_user = User(telegram_id=user.id, username=user.username)
                session.add(db_user)
                await session.flush()

            # Check if already watching
            existing = await session.execute(
                select(Watchlist).where(
                    and_(
                        Watchlist.user_id == db_user.id,
                        Watchlist.contract_address == token_mint,
                    )
                )
            )
            if existing.scalar_one_or_none():
                await update.message.reply_text(
                    f"\u26a0\ufe0f Already watching {shorten_address(token_mint)}"
                )
                return

            # Check watchlist size
            count_result = await session.execute(
                select(Watchlist).where(Watchlist.user_id == db_user.id)
            )
            count = len(count_result.scalars().all())
            if count >= MAX_WATCHLIST_SIZE:
                await update.message.reply_text(
                    f"\u274c Watchlist full ({MAX_WATCHLIST_SIZE} max). "
                    "Use /unwatch to remove a token first."
                )
                return

            # Add to watchlist
            watch = Watchlist(
                user_id=db_user.id,
                contract_address=token_mint,
                created_at=datetime.utcnow(),
            )
            session.add(watch)
            await session.commit()

        await update.message.reply_text(
            f"\U0001f440 Added {shorten_address(token_mint)} to your watchlist.\n"
            "You'll be notified if the score changes significantly."
        )
    except Exception as e:
        logger.error(f"Watch error: {e}")
        await update.message.reply_text("\u274c Failed to add to watchlist. Try again.")


@group_throttle
async def unwatch_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /unwatch <CA> — remove from watchlist."""
    if not context.args:
        await smart_reply(update, "Usage: /unwatch <contract_address>")
        return

    token_mint = context.args[0].strip()
    user = update.effective_user

    try:
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == user.id)
            )
            db_user = result.scalar_one_or_none()
            if not db_user:
                await update.message.reply_text("You have no watchlist.")
                return

            watch_result = await session.execute(
                select(Watchlist).where(
                    and_(
                        Watchlist.user_id == db_user.id,
                        Watchlist.contract_address == token_mint,
                    )
                )
            )
            watch = watch_result.scalar_one_or_none()
            if watch:
                await session.delete(watch)
                await session.commit()
                await update.message.reply_text(
                    f"\u2705 Removed {shorten_address(token_mint)} from watchlist."
                )
            else:
                await update.message.reply_text(
                    f"\u26a0\ufe0f {shorten_address(token_mint)} is not in your watchlist."
                )
    except Exception as e:
        logger.error(f"Unwatch error: {e}")
        await update.message.reply_text("\u274c Failed to remove. Try again.")


@group_throttle
async def watchlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /watchlist — show all watched tokens."""
    user = update.effective_user

    try:
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == user.id)
            )
            db_user = result.scalar_one_or_none()
            if not db_user:
                await update.message.reply_text(
                    "Your watchlist is empty.\n\nUse /watch <CA> to add a token."
                )
                return

            watches = await session.execute(
                select(Watchlist).where(Watchlist.user_id == db_user.id)
            )
            items = watches.scalars().all()

            # Enrich with token names/symbols from most recent analysis
            ca_list = [w.contract_address for w in items]
            token_info = {}
            if ca_list:
                analyses = await session.execute(
                    select(TokenAnalysis)
                    .where(TokenAnalysis.contract_address.in_(ca_list))
                    .order_by(TokenAnalysis.analyzed_at.desc())
                )
                for a in analyses.scalars().all():
                    if a.contract_address not in token_info:
                        token_info[a.contract_address] = {
                            "symbol": a.token_symbol or "???",
                            "name": a.token_name or "Unknown",
                        }

        watch_data = [
            {
                "contract_address": w.contract_address,
                "last_score": w.last_score,
                "symbol": token_info.get(w.contract_address, {}).get("symbol", "???"),
                "name": token_info.get(w.contract_address, {}).get("name", "Unknown"),
            }
            for w in items
        ]

        text = format_watchlist(watch_data)
        keyboard = watchlist_keyboard() if watch_data else None
        await update.message.reply_text(text, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Watchlist error: {e}")
        await update.message.reply_text("\u274c Failed to load watchlist.")


async def callback_watch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle watch button callback from analysis results."""
    query = update.callback_query
    ca = query.data[6:]  # Remove "watch_" prefix

    if not is_valid_solana_address(ca):
        await query.answer("\u274c Invalid address", show_alert=True)
        return

    user = query.from_user

    try:
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == user.id)
            )
            db_user = result.scalar_one_or_none()
            if not db_user:
                db_user = User(telegram_id=user.id, username=user.username)
                session.add(db_user)
                await session.flush()

            existing = await session.execute(
                select(Watchlist).where(
                    and_(
                        Watchlist.user_id == db_user.id,
                        Watchlist.contract_address == ca,
                    )
                )
            )
            if existing.scalar_one_or_none():
                await query.answer("\u26a0\ufe0f Already in watchlist", show_alert=True)
                return

            # Check watchlist size limit
            count_result = await session.execute(
                select(Watchlist).where(Watchlist.user_id == db_user.id)
            )
            if len(count_result.scalars().all()) >= MAX_WATCHLIST_SIZE:
                await query.answer(
                    f"\u274c Watchlist full ({MAX_WATCHLIST_SIZE} max)",
                    show_alert=True,
                )
                return

            watch = Watchlist(
                user_id=db_user.id,
                contract_address=ca,
                created_at=datetime.utcnow(),
            )
            session.add(watch)
            await session.commit()

        await query.answer("\U0001f440 Added to watchlist!", show_alert=True)
    except Exception as e:
        logger.error(f"Callback watch error: {e}")
        await query.answer("\u274c Failed to add", show_alert=True)


async def callback_refresh_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'Refresh All' button from watchlist view."""
    query = update.callback_query
    await query.answer("\U0001f504 Refreshing watchlist...")

    user = query.from_user

    try:
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == user.id)
            )
            db_user = result.scalar_one_or_none()
            if not db_user:
                await query.edit_message_text("Your watchlist is empty.")
                return

            watches = await session.execute(
                select(Watchlist).where(Watchlist.user_id == db_user.id)
            )
            items = watches.scalars().all()

        if not items:
            await query.edit_message_text("Your watchlist is empty.")
            return

        # Re-score each token and save scores back to DB
        from analysis.engine import quick_score

        watch_data = []
        score_updates = {}  # {watchlist_id: new_score}

        for w in items:
            try:
                result = await quick_score(w.contract_address)
                new_score = result.get("total_score")
                watch_data.append({
                    "contract_address": w.contract_address,
                    "last_score": new_score,
                    "symbol": result.get("token_symbol", "???"),
                })
                if new_score is not None:
                    score_updates[w.id] = new_score
            except Exception:
                watch_data.append({
                    "contract_address": w.contract_address,
                    "last_score": w.last_score,
                    "symbol": "???",
                })

        # Persist updated scores to database
        if score_updates:
            try:
                async with async_session() as session:
                    for watch_id, new_score in score_updates.items():
                        result = await session.execute(
                            select(Watchlist).where(Watchlist.id == watch_id)
                        )
                        db_watch = result.scalar_one_or_none()
                        if db_watch:
                            db_watch.last_score = new_score
                            db_watch.last_checked = datetime.utcnow()
                    await session.commit()
            except Exception as e:
                logger.error(f"Failed to save watchlist scores: {e}")

        text = format_watchlist(watch_data)
        keyboard = watchlist_keyboard() if watch_data else None
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    except BadRequest:
        logger.debug("Refresh watchlist: message was deleted")
    except Exception as e:
        logger.error(f"Refresh watchlist error: {e}")
        try:
            await query.edit_message_text("\u274c Failed to refresh watchlist.")
        except BadRequest:
            pass
