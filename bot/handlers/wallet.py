"""Handler for /wallet command — developer wallet analysis."""

import logging
from html import escape as _html_escape

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from analysis.criteria.dev_wallet import score_dev_wallet
from bot.formatters.display import format_wallet_analysis
from bot.keyboards.menus import dev_wallet_keyboard, holders_keyboard, wallet_keyboard
from bot.group_guard import smart_reply, group_throttle
from data.solana_rpc import get_address_type
from utils.helpers import is_valid_solana_address, shorten_address

logger = logging.getLogger(__name__)


@group_throttle
async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /wallet <address> — analyze a developer wallet. Works in groups + DMs."""
    if not context.args:
        await smart_reply(
            update,
            "Usage: /wallet <wallet_address>\n"
            "Analyze a developer's wallet history.",
        )
        return

    address = context.args[0].strip()

    if not is_valid_solana_address(address):
        await smart_reply(update, "\u274c Invalid Solana address.")
        return

    status_msg = await smart_reply(
        update, f"\U0001f50d Checking {shorten_address(address)}..."
    )

    # Check if the address is actually a wallet
    addr_type = await get_address_type(address)
    if addr_type == "token":
        await status_msg.edit_text(
            f"\u26a0\ufe0f That's a token contract, not a wallet ser.\n\n"
            f"Use <code>/scan {address}</code> to analyze the token.",
            parse_mode="HTML",
        )
        return
    elif addr_type == "program":
        await status_msg.edit_text(
            "\u26a0\ufe0f That's a program address, not a wallet."
        )
        return

    await status_msg.edit_text(
        f"\U0001f50d Analyzing wallet {shorten_address(address)}..."
    )

    try:
        result = await score_dev_wallet(address)

        wallet_data = {
            "address": address,
            "wallet_age_days": result.details.get("wallet_age_days"),
            "tokens_created": result.details.get("tokens_created", 0),
            "recent_sells": result.details.get("recent_sells", 0),
            "flagged": result.details.get("rug_risk", False),
            "score": result.score,
        }

        text = format_wallet_analysis(wallet_data)

        # Add flags (escaped for HTML safety)
        if result.flags:
            escaped_flags = [_html_escape(str(f)) for f in result.flags]
            text += "\n\n<b>Details:</b>\n" + "\n".join(f"  {f}" for f in escaped_flags)

        await status_msg.edit_text(
            text, reply_markup=wallet_keyboard(address), parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Wallet analysis failed for {address}: {e}")
        await status_msg.edit_text(
            "\u274c Wallet analysis failed. Please try again.",
            parse_mode="HTML",
        )


async def callback_dev_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle dev wallet button callback from analysis results."""
    query = update.callback_query
    await query.answer()

    ca = query.data[4:]  # Remove "dev_" prefix
    if not is_valid_solana_address(ca):
        return

    # Need to find the creator of this token
    from data.helius_client import get_asset_creator

    try:
        await query.edit_message_text(
            f"\U0001f50d Looking up creator wallet for {shorten_address(ca)}..."
        )
    except BadRequest:
        return

    try:
        creator = await get_asset_creator(ca)
        if not creator:
            await query.edit_message_text(
                "\u26a0\ufe0f Could not identify the creator wallet.\n"
                "Token may be too new or created via a program.",
                reply_markup=dev_wallet_keyboard(ca),
            )
            return

        # Validate the creator is actually a wallet, not a program
        addr_type = await get_address_type(creator)
        if addr_type != "wallet":
            await query.edit_message_text(
                f"\u26a0\ufe0f Creator is a {addr_type} address, not a user wallet.\n"
                f"<code>{creator}</code>",
                reply_markup=dev_wallet_keyboard(ca),
                parse_mode="HTML",
            )
            return

        result = await score_dev_wallet(creator)

        wallet_data = {
            "address": creator,
            "wallet_age_days": result.details.get("wallet_age_days"),
            "tokens_created": result.details.get("tokens_created", 0),
            "recent_sells": result.details.get("recent_sells", 0),
            "flagged": result.details.get("rug_risk", False),
            "score": result.score,
        }

        text = format_wallet_analysis(wallet_data)
        if result.flags:
            escaped_flags = [_html_escape(str(f)) for f in result.flags]
            text += "\n\n<b>Details:</b>\n" + "\n".join(f"  {f}" for f in escaped_flags)

        await query.edit_message_text(
            text, reply_markup=dev_wallet_keyboard(ca), parse_mode="HTML"
        )
    except BadRequest:
        logger.debug("Dev wallet callback: message was deleted")
    except Exception as e:
        logger.error(f"Dev wallet callback failed: {e}")
        try:
            await query.edit_message_text(
                "\u274c Failed to analyze dev wallet.",
                parse_mode="HTML",
            )
        except BadRequest:
            pass


async def callback_holders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'Top Holders' button callback — show top holder breakdown."""
    query = update.callback_query
    await query.answer()

    ca = query.data[8:]  # Remove "holders_" prefix
    if not is_valid_solana_address(ca):
        return

    try:
        await query.edit_message_text(
            f"\U0001f465 Fetching top holders for {shorten_address(ca)}..."
        )
    except BadRequest:
        return

    try:
        from data.solana_rpc import get_token_largest_accounts, get_token_supply
        from config.constants import KNOWN_EXCLUDE_ADDRESSES

        top_holders = await get_token_largest_accounts(ca)
        supply_data = await get_token_supply(ca)

        if not top_holders:
            await query.edit_message_text(
                "\u26a0\ufe0f Could not fetch holder data.",
                reply_markup=holders_keyboard(ca),
            )
            return

        total_supply = 0.0
        if supply_data:
            total_supply = float(supply_data.get("uiAmount", 0) or 0)

        lines = [
            "<b>\U0001f465 TOP HOLDERS \U0001f465</b>",
            "",
        ]

        for i, holder in enumerate(top_holders[:10], 1):
            address = holder.get("address", "")
            amount = float(holder.get("uiAmount", 0) or 0)
            pct = (amount / total_supply * 100) if total_supply > 0 else 0

            tag = ""
            if address in KNOWN_EXCLUDE_ADDRESSES:
                tag = " <i>(LP/Burn)</i>"

            lines.append(f"{i}. {pct:.1f}%{tag}")
            lines.append(f"<code>{address}</code>")
            lines.append("")

        await query.edit_message_text(
            "\n".join(lines), reply_markup=holders_keyboard(ca), parse_mode="HTML"
        )
    except BadRequest:
        logger.debug("Holders callback: message was deleted")
    except Exception as e:
        logger.error(f"Holders callback failed: {e}")
        try:
            await query.edit_message_text(
                "\u274c Failed to fetch holder data.",
                parse_mode="HTML",
            )
        except BadRequest:
            pass
