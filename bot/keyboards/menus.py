"""Inline keyboard buttons and navigation menus."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config.settings import settings

# Deep link base for sharing
_BOT = settings.bot_username


def _share_button(ca: str) -> InlineKeyboardButton:
    """Share button using inline query — lets users share a scan into another chat."""
    return InlineKeyboardButton(
        "\U0001f4e4 Share",
        switch_inline_query=ca,
    )


def _deep_link_button(ca: str) -> InlineKeyboardButton:
    """Deep link button — opens a full scan in the bot's DM."""
    return InlineKeyboardButton(
        "\U0001f50d Scan in DM",
        url=f"https://t.me/{_BOT}?start=scan_{ca}",
    )


def analysis_keyboard(ca: str) -> InlineKeyboardMarkup:
    """Inline buttons for a full analysis result."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\U0001f504 Refresh", callback_data=f"refresh_{ca}"),
            InlineKeyboardButton("\U0001f440 Watch", callback_data=f"watch_{ca}"),
        ],
        [
            InlineKeyboardButton("\U0001f4b0 Dev Wallet", callback_data=f"dev_{ca}"),
            InlineKeyboardButton("\U0001f465 Top Holders", callback_data=f"holders_{ca}"),
        ],
        [
            InlineKeyboardButton("\u26a1 Axiom", url=f"https://axiom.trade/t/{ca}"),
            InlineKeyboardButton("\U0001f4c8 GMGN", url=f"https://gmgn.ai/sol/token/{ca}"),
        ],
        [_share_button(ca)],
    ])


def quick_keyboard(ca: str) -> InlineKeyboardMarkup:
    """Inline buttons for a quick score result."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\U0001f50e Full Scan", callback_data=f"scan_{ca}"),
            InlineKeyboardButton("\U0001f440 Watch", callback_data=f"watch_{ca}"),
        ],
        [
            InlineKeyboardButton("\u26a1 Axiom", url=f"https://axiom.trade/t/{ca}"),
            InlineKeyboardButton("\U0001f4c8 GMGN", url=f"https://gmgn.ai/sol/token/{ca}"),
        ],
        [_share_button(ca)],
    ])


def dev_wallet_keyboard(ca: str) -> InlineKeyboardMarkup:
    """Inline buttons shown after dev wallet analysis — keep user engaged."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\U0001f504 Rescan Token", callback_data=f"scan_{ca}"),
            InlineKeyboardButton("\U0001f465 Top Holders", callback_data=f"holders_{ca}"),
        ],
        [
            InlineKeyboardButton("\U0001f440 Watch", callback_data=f"watch_{ca}"),
        ],
        [
            InlineKeyboardButton("\u26a1 Axiom", url=f"https://axiom.trade/t/{ca}"),
            InlineKeyboardButton("\U0001f4c8 GMGN", url=f"https://gmgn.ai/sol/token/{ca}"),
        ],
    ])


def holders_keyboard(ca: str) -> InlineKeyboardMarkup:
    """Inline buttons shown after top holders view — keep user engaged."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\U0001f504 Rescan Token", callback_data=f"scan_{ca}"),
            InlineKeyboardButton("\U0001f4b0 Dev Wallet", callback_data=f"dev_{ca}"),
        ],
        [
            InlineKeyboardButton("\U0001f440 Watch", callback_data=f"watch_{ca}"),
        ],
        [
            InlineKeyboardButton("\u26a1 Axiom", url=f"https://axiom.trade/t/{ca}"),
            InlineKeyboardButton("\U0001f4c8 GMGN", url=f"https://gmgn.ai/sol/token/{ca}"),
        ],
    ])


def wallet_keyboard(wallet_address: str) -> InlineKeyboardMarkup:
    """Inline buttons shown after standalone /wallet analysis."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "\U0001f50d Solscan",
                url=f"https://solscan.io/account/{wallet_address}",
            ),
            InlineKeyboardButton(
                "\U0001f4c8 GMGN",
                url=f"https://gmgn.ai/sol/address/{wallet_address}",
            ),
        ],
    ])


def watchlist_keyboard() -> InlineKeyboardMarkup:
    """Inline buttons for watchlist view."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\U0001f504 Refresh All", callback_data="refresh_watchlist"),
        ],
    ])


def settings_keyboard(current_threshold: int = 50) -> InlineKeyboardMarkup:
    """Inline buttons for admin settings panel."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                f"Alert Threshold: {current_threshold}",
                callback_data="settings_threshold",
            ),
        ],
        [
            InlineKeyboardButton("Set 30", callback_data="threshold_30"),
            InlineKeyboardButton("Set 50", callback_data="threshold_50"),
            InlineKeyboardButton("Set 70", callback_data="threshold_70"),
        ],
        [
            InlineKeyboardButton("\U0001f3e5 Health", callback_data="admin_health"),
            InlineKeyboardButton("\U0001f5d1 Clear Cache", callback_data="admin_clear_cache"),
        ],
        [
            InlineKeyboardButton("\U0001f4ca Stats", callback_data="admin_stats"),
            InlineKeyboardButton("\U0001f4e2 Broadcast", callback_data="admin_broadcast"),
        ],
    ])
