"""Handler for /scan command and auto CA detection."""

import asyncio
import logging
from html import escape as _html_escape

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from analysis.engine import analyze_token
from bot.formatters.display import format_full_analysis
from bot.keyboards.menus import analysis_keyboard
from bot.group_guard import is_group_chat, is_private_chat, smart_reply, group_throttle
from utils.helpers import is_valid_solana_address, extract_solana_addresses
from database.db import async_session
from database.models import User, TokenAnalysis
from bot.task_registry import track_task
from sqlalchemy import select
from datetime import datetime

logger = logging.getLogger(__name__)

# Auto-refresh config
_AUTO_REFRESH_DELAY = 10    # seconds between retries
_AUTO_REFRESH_MAX = 2       # max retry attempts


@group_throttle
async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /scan <CA> command — full token analysis. Works in groups + DMs."""
    if not context.args:
        await smart_reply(
            update,
            "\u26a1 Usage: /scan <contract_address>\n"
            "Example: /scan DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
        )
        return

    token_mint = context.args[0].strip()
    await _run_analysis(update, token_mint)


async def auto_detect_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Auto-detect Solana addresses pasted in chat and trigger analysis.

    DISABLED in groups to prevent spam — only active in private DMs.
    In groups, users must use /scan or /quick explicitly.
    """
    if not update.message or not update.message.text:
        return

    # Skip auto-detect in groups — too spammy
    if is_group_chat(update):
        return

    text = update.message.text.strip()

    # Skip if it starts with / (command)
    if text.startswith("/"):
        return

    # Extract Solana addresses from the message
    addresses = extract_solana_addresses(text)
    if not addresses:
        return

    # Analyze the first detected address (private chat only)
    await _run_analysis(update, addresses[0])


async def _run_analysis(update: Update, token_mint: str):
    """Run a full analysis and send the result."""
    if not is_valid_solana_address(token_mint):
        await smart_reply(update, "\u274c Invalid Solana address ser. Send a valid CA!")
        return

    # Send "analyzing" message (reply in groups for context)
    status_msg = await smart_reply(
        update, "\U0001f50d Scanning the chain... one sec fren \u26a1"
    )

    try:
        # Run the analysis
        result = await analyze_token(token_mint)

        # Format and send
        text = format_full_analysis(result)
        keyboard = analysis_keyboard(token_mint)

        # If data is incomplete, add auto-refresh indicator
        incomplete = _is_incomplete(result)
        if incomplete:
            text += "\n\n<i>\U0001f504 Data incomplete \u2014 auto-refreshing...</i>"

        await status_msg.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

        # Update user stats
        await _increment_user_scans(update.effective_user.id)

        # Save analysis to DB
        await _save_analysis(result)

        # Spawn background auto-refresh for new tokens with missing data
        if incomplete:
            track_task(asyncio.create_task(
                _auto_refresh(status_msg, token_mint)
            ))

    except Exception as e:
        logger.error(f"Analysis failed for {token_mint}: {e}", exc_info=True)
        await status_msg.edit_text(
            f"\u274c Scan failed ser: {_html_escape(str(e)[:100])}\n\nTry again fren!",
            parse_mode="HTML",
        )


async def callback_refresh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle refresh button callback."""
    query = update.callback_query
    await query.answer()

    ca = query.data[8:]  # Remove "refresh_" prefix
    if not is_valid_solana_address(ca):
        return

    try:
        await query.edit_message_text("\U0001f504 Rescanning... fresh data incoming \u26a1")
    except BadRequest:
        return

    try:
        # Force fresh analysis by clearing cache
        from data.cache import cache
        cache.delete(f"analysis:{ca}")

        result = await analyze_token(ca)
        text = format_full_analysis(result)
        keyboard = analysis_keyboard(ca)
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    except BadRequest:
        logger.debug("Refresh callback: message was deleted")
    except Exception as e:
        logger.error(f"Refresh failed for {ca}: {e}")
        try:
            await query.edit_message_text(
                f"\u274c Refresh failed ser. Try /scan {ca}",
                parse_mode="HTML",
            )
        except BadRequest:
            pass


async def callback_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'Full Scan' button from quick results."""
    query = update.callback_query
    await query.answer()

    ca = query.data[5:]  # Remove "scan_" prefix
    if not is_valid_solana_address(ca):
        return

    try:
        await query.edit_message_text("\U0001f50d Running full degen scan... \u26a1")
    except BadRequest:
        return

    try:
        result = await analyze_token(ca)
        text = format_full_analysis(result)
        keyboard = analysis_keyboard(ca)
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="HTML")
    except BadRequest:
        logger.debug("Full scan callback: message was deleted")
    except Exception as e:
        logger.error(f"Full scan failed for {ca}: {e}")
        try:
            await query.edit_message_text(
                f"\u274c Scan failed ser. Try /scan {ca}",
                parse_mode="HTML",
            )
        except BadRequest:
            pass


async def _increment_user_scans(telegram_id: int):
    """Increment the user's total scan count."""
    try:
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_id)
            )
            user = result.scalar_one_or_none()
            if user:
                user.total_scans += 1
                user.last_active = datetime.utcnow()
                await session.commit()
    except Exception as e:
        logger.debug(f"Failed to update user scans: {e}")


async def _save_analysis(result: dict):
    """Save analysis result to database."""
    try:
        criteria = result.get("criteria", {})

        def _get_score(name):
            cr = criteria.get(name)
            return cr.score if cr else None

        analysis = TokenAnalysis(
            contract_address=result.get("token_mint", ""),
            token_name=result.get("token_name"),
            token_symbol=result.get("token_symbol"),
            score_contract=_get_score("contract"),
            score_liquidity=_get_score("liquidity"),
            score_holders=_get_score("holders"),
            score_dev_wallet=_get_score("dev_wallet"),
            score_volume=_get_score("volume"),
            score_social=_get_score("social"),
            score_metadata=_get_score("metadata"),
            score_smart_money=_get_score("smart_money"),
            total_score=result.get("total_score"),
            risk_label=result.get("risk_label"),
            flags=list(result.get("all_flags", [])),
        )
        async with async_session() as session:
            session.add(analysis)
            await session.commit()
    except Exception as e:
        logger.debug(f"Failed to save analysis: {e}")


# ─── Auto-refresh for new tokens ───


def _is_incomplete(result: dict) -> bool:
    """Check if analysis has significant missing data that might improve with time.

    Returns True if 2+ criteria have estimated/unavailable data.
    """
    estimated = result.get("estimated_criteria", [])
    if len(estimated) >= 2:
        return True

    # Also check flags for "too new" signals
    criteria = result.get("criteria", {})
    incomplete_count = 0
    for _name, cr in criteria.items():
        if cr.estimated:
            incomplete_count += 1
            continue
        flags_lower = " ".join(cr.flags).lower()
        if any(
            kw in flags_lower
            for kw in ("too new", "not yet", "unavailable", "no trading data")
        ):
            incomplete_count += 1
    return incomplete_count >= 2


async def _auto_refresh(message, token_mint: str):
    """Background task: auto-refresh scan for new tokens with missing data.

    Waits, clears stale caches, re-scans, and edits the original message.
    Stops once data is complete or after max retries.
    """
    from data.cache import cache

    for attempt in range(_AUTO_REFRESH_MAX):
        await asyncio.sleep(_AUTO_REFRESH_DELAY)

        # Clear caches so we hit the APIs fresh
        cache.delete(f"analysis:{token_mint}")
        cache.delete(f"dex:{token_mint}")
        cache.delete(f"helius_asset:{token_mint}")

        try:
            result = await analyze_token(token_mint)
            text = format_full_analysis(result)
            keyboard = analysis_keyboard(token_mint)

            still_incomplete = _is_incomplete(result)
            if still_incomplete and attempt < _AUTO_REFRESH_MAX - 1:
                text += "\n\n<i>\U0001f504 Still refreshing...</i>"

            try:
                await message.edit_text(
                    text, reply_markup=keyboard, parse_mode="HTML"
                )
            except BadRequest:
                logger.debug(f"Auto-refresh: message deleted for {token_mint}")
                return

            # Save updated result
            await _save_analysis(result)

            if not still_incomplete:
                logger.debug(f"Auto-refresh complete for {token_mint}")
                return

        except Exception as e:
            # Message deleted, chat gone, etc. — stop silently
            logger.debug(f"Auto-refresh {attempt + 1} failed: {e}")
            return

    logger.debug(f"Auto-refresh exhausted for {token_mint}")
