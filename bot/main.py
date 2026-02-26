"""Bot entry point — initialization, handler registration, startup."""

import asyncio
import logging
import os
import sys
import time as _time

# Ensure project root is in sys.path so all imports work
# regardless of how the script is invoked (python bot/main.py, python -m bot.main, etc.)
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from telegram import BotCommand, BotCommandScopeChat, BotCommandScopeAllGroupChats, MenuButtonCommands
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    InlineQueryHandler,
    filters,
)

from config.settings import settings
from database.db import init_db
from data.cache import cache
from smart_money.wallet_list import load_from_db

# Handlers
from bot.handlers.start import start_command, help_command
from bot.handlers.analyze import (
    scan_command,
    auto_detect_handler,
    callback_refresh,
    callback_scan,
)
from bot.handlers.quick import quick_command
from bot.handlers.watch import (
    watch_command,
    unwatch_command,
    watchlist_command,
    callback_watch,
)
from bot.handlers.trending import trending_command
from bot.handlers.wallet import wallet_command, callback_dev_wallet, callback_holders
from bot.handlers.settings import settings_command, callback_threshold
from bot.handlers.stats import stats_command
from bot.handlers.myid import myid_command
from bot.handlers.admin import broadcast_command, health_command, testreports_command, callback_admin
from bot.handlers.donate import donate_command
from bot.handlers.inline import inline_query_handler
from bot.handlers.watch import callback_refresh_watchlist
from bot.jobs.channel_reports import (
    post_trending_report,
    post_most_scanned_report,
    TRENDING_INTERVAL,
    MOST_SCANNED_INTERVAL,
)

logger = logging.getLogger(__name__)


def setup_logging():
    """Configure logging for the bot."""
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        level=log_level,
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)


async def _setup_bot_profile(application):
    """Configure bot profile for Telegram discoverability (SEO equivalent).

    - Description: shown when a user opens the bot BEFORE pressing Start (landing page)
    - Short description: shown in search results, forwards, and inline mentions (bio/meta)
    - Menu button: the button in the chat input bar
    """
    bot = application.bot

    # ── Description (max 512 chars) ──
    # Shown on the bot's profile page BEFORE the user presses Start.
    # This is your "landing page" — convince the user to press Start.
    description = (
        "\u26a1 The fastest anti-rug scanner on Solana \u26a1\n"
        "\n"
        "\U0001f50d Paste any token CA \u2192 instant safety score\n"
        "\U0001f4ca 8-criteria deep analysis in seconds\n"
        "\U0001f6e1\ufe0f Rug detection powered by real on-chain data\n"
        "\U0001f40b Smart money tracking\n"
        "\U0001f525 Live trending tokens\n"
        "\n"
        "\U0001f4af 100% FREE \u2014 no token, no paywall, no limits\n"
        "\n"
        "\u2328\ufe0f Works in groups too! Add me to your degen chat.\n"
        "\n"
        "Built for degens, by degens \U0001f91d\n"
        "NFA \u2014 DYOR \u2014 WAGMI"
    )
    try:
        await bot.set_my_description(description)
    except Exception as e:
        logger.warning(f"Could not set bot description: {e}")

    # ── Short description (max 120 chars) ──
    # Shown in Telegram search results, when someone shares/forwards the bot,
    # and in the bot's "About" mini-profile. This is your meta description.
    short_description = (
        "\u26a1 Solana anti-rug scanner \u2014 Paste a CA, get instant safety score. "
        "8 criteria, 100% free. Built for degens."
    )
    try:
        await bot.set_my_short_description(short_description)
    except Exception as e:
        logger.warning(f"Could not set short description: {e}")

    # ── Menu button ──
    # Shows "Menu" button in the chat input bar that opens the commands list.
    try:
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
    except Exception as e:
        logger.warning(f"Could not set menu button: {e}")

    logger.info("Bot profile configured (description, bio, menu)")


async def post_init(application):
    """Run after bot initialization — setup DB, cache, smart money list."""
    application.bot_data["start_time"] = _time.time()

    logger.info("Initializing database...")
    await init_db()

    logger.info("Loading smart money wallets...")
    await load_from_db()

    # Start cache cleanup
    cache.start_cleanup_task()

    # ─── Bot Profile: Description, Short Bio, Menu Button ───
    # These are the Telegram "SEO" equivalents — what users see in search,
    # before pressing Start, and when sharing the bot.
    await _setup_bot_profile(application)

    # Register PUBLIC commands in Telegram menu (visible to everyone in DMs)
    public_commands = [
        BotCommand("scan", "\U0001f50d Full degen scan"),
        BotCommand("quick", "\u26a1 Speed check"),
        BotCommand("wallet", "\U0001f4b0 Check a dev wallet"),
        BotCommand("watch", "\U0001f440 Track a token"),
        BotCommand("watchlist", "\U0001f4cb View tracked tokens"),
        BotCommand("unwatch", "\u274c Stop tracking"),
        BotCommand("trending", "\U0001f525 Hot tokens"),
        BotCommand("myid", "\U0001f194 Show my Telegram ID"),
        BotCommand("donate", "\U0001f4b8 Tip the devs"),
        BotCommand("help", "\U0001f4d6 Full guide"),
    ]
    await application.bot.set_my_commands(public_commands)

    # Register GROUP commands — subset visible in group command menu
    group_commands = [
        BotCommand("scan", "\U0001f50d Full degen scan"),
        BotCommand("quick", "\u26a1 Speed check"),
        BotCommand("wallet", "\U0001f4b0 Check a dev wallet"),
        BotCommand("trending", "\U0001f525 Hot tokens"),
        BotCommand("help", "\U0001f4d6 Full guide"),
    ]
    try:
        await application.bot.set_my_commands(
            group_commands,
            scope=BotCommandScopeAllGroupChats(),
        )
        logger.info("Group commands registered")
    except Exception as e:
        logger.warning(f"Could not set group commands: {e}")

    # Register ADMIN commands (public + admin, visible only to admin users)
    admin_commands = public_commands + [
        BotCommand("settings", "\u2699\ufe0f Admin settings"),
        BotCommand("stats", "\U0001f4ca Admin stats"),
        BotCommand("broadcast", "\U0001f4e2 Broadcast message"),
        BotCommand("health", "\U0001f3e5 Bot health"),
        BotCommand("testreports", "\U0001f9ea Test channel reports"),
    ]
    for admin_id in settings.admin_id_set:
        try:
            await application.bot.set_my_commands(
                admin_commands,
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except Exception as e:
            logger.warning(f"Could not set admin commands for {admin_id}: {e}")

    logger.info(
        f"Bot commands registered ({len(settings.admin_id_set)} admins)"
    )

    logger.info("RugScore Bot initialized successfully!")


async def post_shutdown(application):
    """Cleanup on shutdown."""
    # Cancel all tracked background tasks
    from bot.task_registry import cancel_all
    await cancel_all()

    cache.stop_cleanup_task()

    # Close HTTP clients
    from data import solana_rpc, helius_client, dexscreener, jupiter, social_checker, rugcheck_client
    await solana_rpc.close()
    await helius_client.close()
    await dexscreener.close()
    await jupiter.close()
    await social_checker.close()
    await rugcheck_client.close()

    logger.info("RugScore Bot shut down.")


def main():
    """Start the bot."""
    setup_logging()

    # Startup validation
    for warning in settings.validate_startup():
        logger.warning(warning)
    if not settings.telegram_bot_token:
        logger.error("Cannot start without TELEGRAM_BOT_TOKEN!")
        sys.exit(1)

    logger.info("Starting RugScore Bot...")

    # Build the application
    app = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .concurrent_updates(True)
        .build()
    )

    # --- Register command handlers ---
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("scan", scan_command))
    app.add_handler(CommandHandler("quick", quick_command))
    app.add_handler(CommandHandler("watch", watch_command))
    app.add_handler(CommandHandler("unwatch", unwatch_command))
    app.add_handler(CommandHandler("watchlist", watchlist_command))
    app.add_handler(CommandHandler("wallet", wallet_command))
    app.add_handler(CommandHandler("trending", trending_command))
    app.add_handler(CommandHandler("myid", myid_command))
    app.add_handler(CommandHandler("donate", donate_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("health", health_command))
    app.add_handler(CommandHandler("testreports", testreports_command))

    # --- Register callback query handlers ---
    # Regex requires 32-44 char base58 address after prefix to avoid collisions
    app.add_handler(CallbackQueryHandler(callback_refresh, pattern=r"^refresh_[1-9A-HJ-NP-Za-km-z]{32,44}$"))
    app.add_handler(CallbackQueryHandler(callback_scan, pattern=r"^scan_[1-9A-HJ-NP-Za-km-z]{32,44}$"))
    app.add_handler(CallbackQueryHandler(callback_watch, pattern=r"^watch_[1-9A-HJ-NP-Za-km-z]{32,44}$"))
    app.add_handler(CallbackQueryHandler(callback_dev_wallet, pattern=r"^dev_[1-9A-HJ-NP-Za-km-z]{32,44}$"))
    app.add_handler(CallbackQueryHandler(callback_holders, pattern=r"^holders_[1-9A-HJ-NP-Za-km-z]{32,44}$"))
    app.add_handler(CallbackQueryHandler(callback_refresh_watchlist, pattern=r"^refresh_watchlist$"))
    app.add_handler(CallbackQueryHandler(callback_threshold, pattern=r"^threshold_\d+$"))
    app.add_handler(CallbackQueryHandler(callback_admin, pattern=r"^admin_"))
    app.add_handler(CallbackQueryHandler(
        lambda u, c: u.callback_query.answer(), pattern=r"^settings_"
    ))

    # --- Inline mode: @YourBot <CA> in any chat ---
    # Enables viral sharing — users can scan tokens inline in any conversation
    app.add_handler(InlineQueryHandler(inline_query_handler))

    # --- Auto-detect Solana addresses in messages (private chats only) ---
    # In groups, auto-detect is disabled to prevent spam.
    # Users must use /scan or /quick explicitly.
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        auto_detect_handler,
    ))

    # --- Schedule channel reports ---
    if settings.channel_id:
        jq = app.job_queue
        jq.run_repeating(
            post_trending_report,
            interval=TRENDING_INTERVAL,
            first=TRENDING_INTERVAL,
            name="trending_report",
        )
        jq.run_repeating(
            post_most_scanned_report,
            interval=MOST_SCANNED_INTERVAL,
            first=MOST_SCANNED_INTERVAL,
            name="most_scanned_report",
        )
        logger.info(
            f"Channel reports scheduled -> {settings.channel_id} "
            f"(trending: {TRENDING_INTERVAL // 3600}h, "
            f"scanned: {MOST_SCANNED_INTERVAL // 60}min)"
        )
    else:
        logger.info("CHANNEL_ID not set — channel reports disabled")

    # --- Start polling ---
    logger.info("Bot is running! Press Ctrl+C to stop.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
