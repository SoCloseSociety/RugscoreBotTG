"""Utility helpers: Solana address validation, formatting, etc."""

from __future__ import annotations

import re
import base58

# Matches Solana base58 addresses (32-44 chars, no 0/O/I/l)
SOLANA_ADDRESS_REGEX = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")


def is_valid_solana_address(address: str) -> bool:
    """Validate a Solana base58 address."""
    if not SOLANA_ADDRESS_REGEX.fullmatch(address):
        return False
    try:
        decoded = base58.b58decode(address)
        return len(decoded) == 32
    except Exception:
        return False


def extract_solana_addresses(text: str) -> list[str]:
    """Extract all potential Solana addresses from text."""
    candidates = SOLANA_ADDRESS_REGEX.findall(text)
    return [addr for addr in candidates if is_valid_solana_address(addr)]


def shorten_address(address: str, chars: int = 4) -> str:
    """Shorten address to first/last N chars: HxR4...j7kP"""
    if len(address) <= chars * 2 + 3:
        return address
    return f"{address[:chars]}...{address[-chars:]}"


def format_number(n: float) -> str:
    """Format number with K/M/B suffixes."""
    if n is None:
        return "N/A"
    if abs(n) >= 1_000_000_000:
        return f"${n / 1_000_000_000:.1f}B"
    if abs(n) >= 1_000_000:
        return f"${n / 1_000_000:.1f}M"
    if abs(n) >= 1_000:
        return f"${n / 1_000:.1f}K"
    return f"${n:.0f}"


def format_percentage(value: float) -> str:
    """Format a percentage value."""
    if value is None:
        return "N/A"
    return f"{value:.1f}%"


def score_bar(score: int, total: int = 10) -> str:
    """Generate a Unicode progress bar. score 0-100, bar length = total chars."""
    filled = round(score / 100 * total)
    return "\u2588" * filled + "\u2591" * (total - filled)


def clamp(value: float, min_val: float = 0, max_val: float = 100) -> float:
    """Clamp a value between min and max."""
    return max(min_val, min(max_val, value))
