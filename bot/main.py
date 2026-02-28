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
    # These are the Telegram "SEO" equivalents — what users see in search results.
    try:
        await _setup_bot_profile(application)
    except Exception as e:
        logger.warning(f"Could not set up bot profile: {e}")

    # Tracking tokens list (HTML) with live market data.
    if not tokens:
        return "No trending Solana tokens right now."

    lines = [
        "<b>\U0001f525 TRENDING SOLANA TOKENS \U0001f525</b>",
        "",
    ]

    for i, token in enumerate(tokens[:10], 1):
        name = _esc(token.get("token_name") or "Unknown")
        symbol = _esc(token.get("token_symbol") or "???")
        ca = token.get("contract_address", "")
        price = token.get("price_usd")
        mcap = token.get("market_cap")
        vol = token.get("volume_24h")
        change = token.get("price_change_24h")

        # Price change indicator
        if change is not None:
            arrow = "\U0001f7e2" if change >= 0 else "\U0001f534"
            change_str = f" {arrow} {change:+.1f}%"
        else:
            change_str = ""

        lines.append(f"{i}. <b>{name}</b> (${symbol}){change_str}")

        # Market data line
        parts = []
        if price:
            price_str = f"${price:.8f}" if price < 0.01 else f"${price:.4f}"
            parts.append(price_str)

        if mcap:
            parts.append(f"MCap: {format_number(mcap)}")

        if vol:
            parts.append(f"Vol 24h: {format_number(vol)}")

        lines.append("  " + " | ".join(parts))

    return _truncate_message("
    ".join(lines))

async def post_shutdown(application):
    """Run before bot shutdown — clean up resources."""
    cache.stop_cleanup_task()

    logger.info("Bot is shutting down...")

def main():
    """Main function to run the bot."""
    application = Application.builder().token(settings.BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("scan", scan_command))
    application.add_handler(CommandHandler("quick", quick_command))
    application.add_handler(CommandHandler("watch", watch_command))
    application.add_handler(CommandHandler("unwatch", unwatch_command))
    application.add_handler(CommandHandler("watchlist", watchlist_command))
    application.add_handler(CommandHandler("trending", trending_command))
    application.add_handler(CommandHandler("wallet", wallet_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("myid", myid_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("health", health_command))
    application.add_handler(CommandHandler("testreports", testreports_command))
    application.add_handler(CommandHandler("donate", donate_command))
    application.add_handler(InlineQueryHandler(inline_query_handler))

    # Start the bot
    application.run_polling()

if __name__ == "__main__":
    main()