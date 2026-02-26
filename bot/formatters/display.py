"""Result formatting for Telegram — HTML mode with degen culture."""

from __future__ import annotations

from html import escape as _html_escape

from analysis.criteria import CriterionResult
from utils.helpers import shorten_address, format_number, score_bar

TELEGRAM_MAX_LENGTH = 4096

# Emoji mapping for criteria display
CRITERION_EMOJI = {
    "Contract": "\U0001f4dc",
    "Liquidity": "\U0001f4a7",
    "Holders": "\U0001f465",
    "Dev Wallet": "\U0001f9d1\u200d\U0001f4bb",
    "Volume": "\U0001f4ca",
    "Social": "\U0001f426",
    "Metadata": "\U0001f3f7\ufe0f",
    "Smart Money": "\U0001f40b",
}


def _esc(text) -> str:
    """Escape HTML special characters in user-provided text."""
    return _html_escape(str(text)) if text else ""


def _truncate_message(text: str, max_length: int = TELEGRAM_MAX_LENGTH) -> str:
    """Truncate message to fit Telegram's character limit (HTML-safe)."""
    if len(text) <= max_length:
        return text
    suffix = "\n\n<i>... (truncated)</i>"
    cut = max_length - len(suffix)
    # Cut at last newline to avoid splitting mid-HTML-tag
    safe_cut = text.rfind("\n", 0, cut)
    if safe_cut < cut // 2:
        safe_cut = cut
    return text[:safe_cut] + suffix


def _links_bar(mint: str) -> str:
    """Generate rows of clickable site links for a token."""
    research = (
        f'<a href="https://dexscreener.com/solana/{mint}">DexS</a>'
        f' \u00b7 <a href="https://gmgn.ai/sol/token/{mint}">GMGN</a>'
        f' \u00b7 <a href="https://axiom.trade/t/{mint}">Axiom</a>'
        f' \u00b7 <a href="https://app.bubblemaps.io/sol/token/{mint}">Bubbles</a>'
        f' \u00b7 <a href="https://rugcheck.xyz/tokens/{mint}">RugCheck</a>'
        f' \u00b7 <a href="https://x.com/search?q={mint}">X</a>'
    )
    trade = (
        f'\U0001f4b8 <a href="https://t.me/paris_trojanbot?start={mint}">Trojan</a>'
        f' \u00b7 <a href="https://t.me/bonkbot_bot?start={mint}">BonkBot</a>'
        f' \u00b7 <a href="https://t.me/photon_sol_bot?start={mint}">Photon</a>'
    )
    return f"{research}\n{trade}"


def format_full_analysis(analysis: dict) -> str:
    """Format a complete analysis result for Telegram display (HTML)."""
    name = _esc(analysis.get("token_name") or "Unknown")
    symbol = _esc(analysis.get("token_symbol") or "???")
    mint = analysis.get("token_mint", "")
    total = analysis.get("total_score") or 0
    emoji = analysis.get("risk_emoji") or "\u26a0\ufe0f"
    label = _esc(analysis.get("risk_label") or "UNKNOWN")
    risk_desc = _esc(analysis.get("risk_desc") or "")
    elapsed = analysis.get("analysis_time") or 0
    from_cache = analysis.get("from_cache", False)
    criteria = analysis.get("criteria", {})
    data_quality = analysis.get("data_quality", 100)
    estimated_criteria = analysis.get("estimated_criteria", [])

    # Header
    lines = [
        "<b>\u26a1 RUGSCORE \u2501\u2501\u2501 DEGEN SCANNER \u26a1</b>",
        "",
        f"<b>{name}</b> (${symbol})",
        f"<code>{shorten_address(mint)}</code>",
        "",
        f"{emoji} <b>SCORE: {total:.0f}/100</b> \u2014 {label}",
        f"<code>{score_bar(total, 14)}</code>",
    ]
    if risk_desc:
        lines.append(f"<i>{risk_desc}</i>")

    # Data quality warning if analysis is incomplete
    if data_quality < 100 and estimated_criteria:
        lines.append("")
        lines.append(
            f"\u26a0\ufe0f <b>Data quality: {data_quality}%</b> \u2014 "
            f"some checks had limited data"
        )

    lines.append("")

    # Market data
    price = analysis.get("price_usd")
    mcap = analysis.get("market_cap")
    liq = analysis.get("liquidity_usd")
    vol = analysis.get("volume_24h")

    if price or mcap:
        lines.append("<b>\U0001f4b0 MARKET DATA</b>")
        if price:
            price_str = f"${price:.8f}" if price < 0.01 else f"${price:.4f}"
            lines.append(f"  \U0001f4b2 Price: {price_str}")
        if mcap:
            lines.append(f"  \U0001f4c8 MCap: {format_number(mcap)}")
        if liq:
            lines.append(f"  \U0001f4a7 Liq: {format_number(liq)}")
        if vol:
            lines.append(f"  \U0001f4ca Vol 24h: {format_number(vol)}")
        lines.append("")

    # Criteria breakdown
    lines.append("<b>\U0001f50d BREAKDOWN</b>")
    lines.append("")

    criterion_order = [
        "contract", "liquidity", "holders", "dev_wallet",
        "volume", "social", "metadata", "smart_money",
    ]

    for crit_name in criterion_order:
        result = criteria.get(crit_name)
        if not result:
            continue
        lines.append(format_criterion(result))
        lines.append("")

    # Links bar
    lines.append(_links_bar(mint))
    lines.append("")

    # Footer with speed branding
    cache_indicator = "cached \u267b\ufe0f" if from_cache else "live"
    lines.append(f"<i>\u26a1 Scanned in {elapsed}s | {cache_indicator} | NFA \u2014 DYOR</i>")

    return _truncate_message("\n".join(lines))


def format_criterion(result: CriterionResult) -> str:
    """Format a single criterion result with score bar and flags."""
    emoji = CRITERION_EMOJI.get(result.name, "\u2022")
    bar = score_bar(result.score, 10)
    est_tag = " \u2248" if result.estimated else ""
    header = f"{emoji} <b>{_esc(result.name)}</b>  {result.score:.0f}{est_tag}  <code>{bar}</code>"

    flag_lines = []
    for flag in result.flags[:4]:
        flag_lines.append(f"  {_esc(flag)}")

    return header + "\n" + "\n".join(flag_lines)


def format_quick_score(result: dict) -> str:
    """Format a quick score result (HTML)."""
    name = _esc(result.get("token_name") or "Unknown")
    symbol = _esc(result.get("token_symbol") or "???")
    mint = result.get("token_mint", "")
    total = result.get("total_score") or 0
    emoji = result.get("risk_emoji") or "\u26a0\ufe0f"
    label = _esc(result.get("risk_label") or "UNKNOWN")
    elapsed = result.get("analysis_time") or 0

    price = result.get("price_usd")
    mcap = result.get("market_cap")
    liq = result.get("liquidity_usd")

    lines = [
        f"\u26a1 <b>{name}</b> (${symbol})",
        f"{emoji} Score: <b>{total:.0f}/100</b> \u2014 {label}",
        f"<code>{score_bar(total, 14)}</code>",
        "",
    ]

    if price:
        price_str = f"${price:.8f}" if price < 0.01 else f"${price:.4f}"
        lines.append(f"\U0001f4b2 Price: {price_str}")
    if mcap:
        lines.append(f"\U0001f4c8 MCap: {format_number(mcap)}")
    if liq:
        lines.append(f"\U0001f4a7 Liq: {format_number(liq)}")

    lines.append("")
    lines.append(_links_bar(mint))
    lines.append(f"\n<i>\u26a1 {elapsed}s | /scan for full degen report | NFA</i>")

    return "\n".join(lines)


def format_wallet_analysis(wallet_data: dict) -> str:
    """Format a wallet analysis result (HTML)."""
    address = wallet_data.get("address", "")
    age = wallet_data.get("wallet_age_days")
    created = wallet_data.get("tokens_created", 0)
    flagged = wallet_data.get("flagged", False)
    score = wallet_data.get("score")
    recent_sells = wallet_data.get("recent_sells", 0)

    flag_emoji = "\U0001f6a9" if flagged else "\u2705"
    flag_text = "RUG PATTERN DETECTED" if flagged else "No rug pattern"

    lines = [
        "<b>\u26a1 WALLET CHECK \u26a1</b>",
        "",
        f"<code>{_esc(address)}</code>",
        "",
    ]

    # Show score if available
    if score is not None:
        lines.append(f"{flag_emoji} <b>Dev Score: {score:.0f}/100</b> \u2014 {flag_text}")
        lines.append(f"<code>{score_bar(score, 14)}</code>")
    else:
        lines.append(f"{flag_emoji} <b>{flag_text}</b>")
    lines.append("")

    # Wallet stats
    if age is not None:
        lines.append(f"  \U0001f4c5 Wallet age: {age:.0f} days")
    else:
        lines.append("  \U0001f4c5 Wallet age: unknown")
    lines.append(f"  \U0001f4dc Tokens created: {created}")
    if recent_sells > 0:
        lines.append(f"  \u26a0\ufe0f Recent sells: {recent_sells}")

    # Explorer link
    lines.append("")
    lines.append(f'<a href="https://solscan.io/account/{_esc(address)}">View on Solscan</a>')

    return "\n".join(lines)


def format_watchlist(items: list[dict]) -> str:
    """Format the user's watchlist (HTML)."""
    if not items:
        return "Your watchlist is empty fren.\n\nUse /watch &lt;CA&gt; to start tracking."

    lines = [
        "<b>\U0001f440 YOUR WATCHLIST</b>",
        "",
    ]

    for i, item in enumerate(items, 1):
        symbol = _esc(item.get("symbol") or "???")
        name = _esc(item.get("name") or "")
        ca = item.get("contract_address", "")
        score = item.get("last_score")
        if score is not None:
            score_str = f"{score:.0f}/100"
        else:
            score_str = "not scored"
        display = f"{name} (${symbol})" if name and name != "Unknown" else f"${symbol}"
        lines.append(f"  {i}. <b>{display}</b> \u2014 {score_str}")
        lines.append(f"  <code>{ca}</code>")
        lines.append(f"  /scan {ca}")
        lines.append("")

    lines.append(f"Tracking {len(items)} token{'s' if len(items) != 1 else ''} \U0001f440")

    return _truncate_message("\n".join(lines))


def format_trending(tokens: list[dict]) -> str:
    """Format trending tokens list (HTML) with live market data."""
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
            parts.append(f"MC {format_number(mcap)}")
        if vol:
            parts.append(f"Vol {format_number(vol)}")
        if parts:
            sep = " \u2022 "
            lines.append(f"   {sep.join(parts)}")

        if ca:
            lines.append(f"   <code>{shorten_address(ca)}</code>")
        lines.append("")

    lines.append("<i>Data: DexScreener \u2022 Tap scan to analyze</i>")

    return _truncate_message("\n".join(lines))
