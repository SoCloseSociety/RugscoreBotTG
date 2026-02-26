"""Handler for /myid command — shows user's Telegram ID."""

from telegram import Update
from telegram.ext import ContextTypes


async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /myid — display the user's Telegram ID for admin setup."""
    user = update.effective_user
    if not user:
        return
    await update.message.reply_text(
        f"\U0001f194 Your Telegram ID: <code>{user.id}</code>\n\n"
        f"Send this to the bot owner to be added as admin.",
        parse_mode="HTML",
    )
