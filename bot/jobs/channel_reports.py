"""Scheduled channel reports — trending + most scanned tokens."""

import logging
from datetime import datetime, timedelta

from telegram.ext import ContextTypes
from sqlalchemy import select, func

from config.settings import settings
from database.db import async_session
from database.models import TokenAnalysis
from data.dexscreener import get_trending_tokens
from utils.helpers import format_number

logger = logging.getLogger(__name__)

# ── Interval constants (seconds) ──────────────────
TRENDING_INTERVAL = 3 * 60 * 60       # 3 hours
MOST_SCANNED_INTERVAL = 90 * 60       # 1h30


def _fmt_price(price) -> str:
    if not price:
        return ""
    return f"${price:.8f}" if price < 0.01 else f"${price:.4f}"


def _token_links(ca: str) -> str:
    """Build a compact row of research links for a token."""
    return (
        f'   <a href="https://dexscreener.com/solana/{ca}">DexS</a>'
        f' \u00b7 <a href="https://gmgn.ai/sol/token/{ca}">GMGN</a>'
        f' \u00b7 <a href="https://axiom.trade/t/{ca}">Axiom</a>'
        f' \u00b7 <a href="https://app.bubblemaps.io/sol/token/{ca}">Bubbles</a>'
        f' \u00b7 <a href="https://x.com/search?q={ca}">X</a>'
    )


def _score_label(score) -> str:
    """Return a degen-style risk tag from a numeric score."""
    if score is None:
        return ""
    if score >= 90:
        return "\U0001f7e2 SAFU"
    if score >= 70:
        return "\U0001f7e1 Looks Good"
    if score >= 50:
        return "\U0001f7e0 Sketchy"
    if score >= 25:
        return "\U0001f534 Danger"
    return "\u26d4 Likely Rug"


# ──────────────────────────────────────────────────
#  JOB 1: Trending report (every 3h)
# ──────────────────────────────────────────────────

async def post_trending_report(context: ContextTypes.DEFAULT_TYPE):
    """Fetch DexScreener trending tokens and post to channel."""
    channel = settings.channel_id
    if not channel:
        return

    try:
        tokens = await get_trending_tokens(limit=10)
        if not tokens:
            logger.info("[CHANNEL] No trending tokens to report")
            return

        now = datetime.utcnow().strftime("%H:%M UTC")
        sep = "\u2501" * 24

        lines = [
            f"\U0001f525\U0001f525\U0001f525 <b>WHAT'S HOT ON SOLANA</b> \U0001f525\U0001f525\U0001f525",
            f"<i>The degens are aping into these rn</i>",
            f"<i>{now} \u2022 updates every 3h</i>",
            "",
            sep,
            "",
        ]

        for i, t in enumerate(tokens[:10], 1):
            name = t.get("token_name", "Unknown")
            symbol = t.get("token_symbol", "???")
            ca = t.get("contract_address", "")
            price = t.get("price_usd")
            mcap = t.get("market_cap")
            vol = t.get("volume_24h")
            change = t.get("price_change_24h")

            # Price change with degen flair
            if change is not None:
                if change >= 100:
                    tag = "\U0001f680 SENDING IT"
                elif change >= 20:
                    tag = "\U0001f7e2 pumping"
                elif change >= 0:
                    tag = "\U0001f7e2 up"
                elif change > -20:
                    tag = "\U0001f534 dipping"
                else:
                    tag = "\U0001f534 dumping"
                change_str = f"  {tag} ({change:+.1f}%)"
            else:
                change_str = ""

            lines.append(f"<b>{i}. {name}</b> ${symbol}{change_str}")

            # Market data — compact single line
            parts = []
            if price:
                parts.append(_fmt_price(price))
            if mcap:
                parts.append(f"MC {format_number(mcap)}")
            if vol:
                parts.append(f"Vol {format_number(vol)}")
            if parts:
                dot = " \u2022 "
                lines.append(f"   {dot.join(parts)}")

            if ca:
                lines.append(_token_links(ca))
                lines.append(
                    f'   <a href="https://t.me/{settings.bot_username}?start=scan_{ca}">\U0001f50d Scan it</a>'
                    f" \u2022 <code>{ca[:4]}...{ca[-4:]}</code>"
                )
            lines.append("")

        lines.append(sep)
        lines.append("")
        lines.append(
            "\U0001f6e1 <b>Before you ape, scan it first</b>"
            f"\n\U0001f916 @{settings.bot_username} \u2014 free degen scanner"
            "\n<i>NFA \u2022 DYOR \u2022 WAGMI</i>"
        )

        await context.bot.send_message(
            chat_id=channel,
            text="\n".join(lines),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        logger.info("[CHANNEL] Trending report posted")

    except Exception as e:
        logger.error(f"[CHANNEL] Trending report failed: {e}", exc_info=True)


# ──────────────────────────────────────────────────
#  JOB 2: Most scanned report (every 1h30)
# ──────────────────────────────────────────────────

async def post_most_scanned_report(context: ContextTypes.DEFAULT_TYPE):
    """Query DB for most scanned tokens in last 3h and post to channel."""
    channel = settings.channel_id
    if not channel:
        return

    try:
        since = datetime.utcnow() - timedelta(hours=3)

        async with async_session() as session:
            rows = (await session.execute(
                select(
                    TokenAnalysis.contract_address,
                    TokenAnalysis.token_name,
                    TokenAnalysis.token_symbol,
                    func.count(TokenAnalysis.id).label("scan_count"),
                    func.avg(TokenAnalysis.total_score).label("avg_score"),
                    func.max(TokenAnalysis.total_score).label("latest_score"),
                )
                .where(TokenAnalysis.analyzed_at >= since)
                .group_by(TokenAnalysis.contract_address)
                .order_by(func.count(TokenAnalysis.id).desc())
                .limit(10)
            )).all()

        if not rows:
            logger.info("[CHANNEL] No scanned tokens to report")
            return

        now = datetime.utcnow().strftime("%H:%M UTC")
        sep = "\u2501" * 24

        lines = [
            f"\U0001f50d\U0001f50d\U0001f50d <b>DEGENS ARE SCANNING THESE</b> \U0001f50d\U0001f50d\U0001f50d",
            f"<i>Most checked tokens in the last 3h</i>",
            f"<i>{now} \u2022 updates every 1h30</i>",
            "",
            sep,
            "",
        ]

        for i, row in enumerate(rows, 1):
            ca = row.contract_address
            name = row.token_name or "Unknown"
            symbol = row.token_symbol or "???"
            count = row.scan_count
            avg = row.avg_score
            latest = row.latest_score

            # Score tag
            label = _score_label(latest)
            score_str = f"  {label}" if label else ""

            lines.append(f"<b>{i}. {name}</b> ${symbol}{score_str}")

            # Scan count + avg score
            scan_word = "scan" if count == 1 else "scans"
            avg_str = f" \u2022 avg score {avg:.0f}/100" if avg is not None else ""
            lines.append(f"   \U0001f4ca {count} {scan_word}{avg_str}")

            if ca:
                lines.append(_token_links(ca))
                lines.append(
                    f'   <a href="https://t.me/{settings.bot_username}?start=scan_{ca}">\U0001f50d Scan it</a>'
                    f" \u2022 <code>{ca[:4]}...{ca[-4:]}</code>"
                )
            lines.append("")

        lines.append(sep)
        lines.append("")
        lines.append(
            "\U0001f4a1 <b>If degens are scanning it, you should too</b>"
            f"\n\U0001f916 @{settings.bot_username} \u2014 free degen scanner"
            "\n<i>NFA \u2022 DYOR \u2022 WAGMI</i>"
        )

        await context.bot.send_message(
            chat_id=channel,
            text="\n".join(lines),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        logger.info("[CHANNEL] Most-scanned report posted")

    except Exception as e:
        logger.error(f"[CHANNEL] Most-scanned report failed: {e}", exc_info=True)
