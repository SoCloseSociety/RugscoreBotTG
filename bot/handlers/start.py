"""Handler for /start and /help commands."""

import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from database.db import async_session
from database.models import User
from bot.group_guard import is_group_chat, smart_reply
from sqlalchemy import select

logger = logging.getLogger(__name__)

WELCOME_MESSAGE = """\
\u26a1\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u26a1
   RUGSCORE \u2014 DEGEN SCANNER
\u26a1\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u26a1

Yo fren! \U0001f44b The fastest anti-rug
scanner on Solana is here \u26a1

\U0001f50d Paste a CA \u2192 instant analysis
\U0001f4ca 8 criteria deep-scan
\U0001f6e1\ufe0f Rug detection in seconds
\U0001f4af 100% FREE \u2014 no limits

\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501
\u2328\ufe0f COMMANDS

/scan <CA>     Full degen scan
/quick <CA>    Speed check \u26a1
/watch <CA>    Track a token
/wallet <addr> Check a dev
/trending      Hot tokens \U0001f525
/donate        Tip the devs \U0001f4b8
/myid          Show my Telegram ID
/help          Full guide

\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501

\U0001f4a1 Just paste any CA and I'll scan
it before you can say LFG \u26a1

Built for degens, by degens \U0001f91d
NFA \u2014 DYOR \u2014 WAGMI"""

HELP_MESSAGE = """\
\u26a1\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u26a1
  RUGSCORE \u2014 FULL GUIDE
\u26a1\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u26a1

\U0001f50d COMMANDS

/scan <CA>
  Full 8-criteria degen scan.
  Deep analysis in seconds \u26a1

/quick <CA>
  Lightning fast score check.
  Contract + Liquidity + Holders.

/watch <CA>
  Add to your watchlist.
  Get alerts on score changes.

/unwatch <CA>
  Remove from watchlist.

/watchlist
  View all tracked tokens.

/wallet <address>
  Deep check on a dev wallet.
  Rug history, token farm detection.

/trending
  Top 10 recently scanned tokens \U0001f525

/donate
  Tip the devs \U0001f4b8

\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501

\U0001f3af AUTO-DETECT
Just paste any Solana CA and
I'll scan it instantly \u26a1

\U0001f4ca SCORING (0-100)
\U0001f7e2 90-100  SAFU
\U0001f7e1 70-89   LOOKS GOOD
\U0001f7e0 50-69   SKETCHY
\U0001f534 25-49   DANGER
\u26d4 0-24    LIKELY RUG

\U0001f52c 8 CRITERIA
1. \U0001f4dc Contract Safety (20%)
2. \U0001f4a7 Liquidity Health (15%)
3. \U0001f465 Holder Distribution (15%)
4. \U0001f9d1\u200d\U0001f4bb Dev Wallet History (15%)
5. \U0001f4ca Volume Authenticity (10%)
6. \U0001f426 Social Legitimacy (10%)
7. \U0001f3f7\ufe0f Metadata Quality (5%)
8. \U0001f40b Smart Money Signal (10%)

\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501
\U0001f4af Free \u2014 No paywall \u2014 Ultra-fast \u26a1
\U0001f91d Built for degens, by degens
NFA \u2014 DYOR \u2014 WAGMI
\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501"""

# Shorter welcome for groups — no spam
GROUP_WELCOME = """\
\u26a1 RUGSCORE \u2014 DEGEN SCANNER \u26a1

The fastest anti-rug scanner on Solana!

\u2328\ufe0f COMMANDS (use in this group):
/scan <CA>     Full degen scan
/quick <CA>    Speed check \u26a1
/trending      Hot tokens \U0001f525
/help          Full guide

\U0001f4a1 In groups, use /scan or /quick.
Auto-detect is DM only \u2014 tap me for instant CA scans!

NFA \u2014 DYOR \u2014 WAGMI"""


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command — welcome message + user registration."""
    user = update.effective_user
    if not user:
        return

    # Register or update user
    try:
        async with async_session() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == user.id)
            )
            db_user = result.scalar_one_or_none()
            if not db_user:
                db_user = User(
                    telegram_id=user.id,
                    username=user.username,
                )
                session.add(db_user)
                await session.commit()
                logger.info(f"New user registered: {user.id} (@{user.username})")
            else:
                db_user.last_active = datetime.utcnow()
                await session.commit()
    except Exception as e:
        logger.error(f"User registration error: {e}")

    # Handle deep links: /start scan_<CA>
    if context.args and context.args[0].startswith("scan_"):
        ca = context.args[0][5:]  # strip "scan_" prefix
        if ca:
            from bot.handlers.analyze import _run_analysis
            await _run_analysis(update, ca)
            return

    # Shorter message in groups to avoid spam
    if is_group_chat(update):
        await smart_reply(update, GROUP_WELCOME)
    else:
        await update.message.reply_text(WELCOME_MESSAGE)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command — full usage guide."""
    if is_group_chat(update):
        await smart_reply(update, GROUP_WELCOME)
    else:
        await update.message.reply_text(HELP_MESSAGE)
