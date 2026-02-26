"""Handler for /donate command — tip the devs, degen style."""

from telegram import Update
from telegram.ext import ContextTypes

from config.settings import settings

DONATE_MESSAGE = """\
\U0001f4b8\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\U0001f4b8
   SUPPORT THE DEVS
\U0001f4b8\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\U0001f4b8

Yo fren \U0001f91d

We built this bot deep in the trenches,
between rugs and honeypots \U0001f480
While shitcoin devs were dumping
on everyone, we were building
tools for the community \U0001f6e1\ufe0f

This bot is 100% FREE, no token,
no presale, no "utility NFT"
\u2014 just pure alpha for free \U0001f4af

If we saved you from a rug,
if you dodged a honeypot,
or if you just wanna tip the devs
grinding for you in the trenches...

\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501

\U0001f4b0 <b>SOL Wallet (Solana)</b>
<code>{wallet}</code>

\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501\u2501

Every tip = one more dev who hodls
instead of rage quitting \U0001f4aa

Thanks for the support fam \u2764\ufe0f
We stay in the trenches
for you \U0001f3af

NFA \u2014 DYOR \u2014 WAGMI \U0001f680"""

NO_WALLET_MESSAGE = """\
\U0001f4b8 DONATE

Thanks for the love fren!
Donation wallet is not set up yet.
Check back soon \U0001f91d"""


async def donate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /donate — show donation wallet with degen flair."""
    wallet = settings.donate_wallet
    if not wallet:
        await update.message.reply_text(NO_WALLET_MESSAGE)
        return

    await update.message.reply_text(
        DONATE_MESSAGE.format(wallet=wallet),
        parse_mode="HTML",
    )
