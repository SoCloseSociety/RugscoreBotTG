"""Known smart money wallet database — curated list + CRUD operations."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from database.db import async_session
from database.models import SmartMoneyWallet

logger = logging.getLogger(__name__)

# In-memory cache of smart money addresses for fast lookups
_smart_money_cache: Optional[set[str]] = None


# Initial curated list of known profitable wallets
# Sources: GMGN leaderboard, Birdeye top traders, community knowledge
INITIAL_SMART_MONEY = [
    # These are example placeholder addresses — replace with real addresses
    # scraped from GMGN.ai top traders or Birdeye leaderboards
]


def get_smart_money_set() -> set[str]:
    """Get the set of all known smart money wallet addresses.

    Returns an in-memory set for O(1) lookups during scoring.
    """
    global _smart_money_cache
    if _smart_money_cache is None:
        _smart_money_cache = set(INITIAL_SMART_MONEY)
    return _smart_money_cache


async def load_from_db():
    """Load smart money wallets from database into memory cache."""
    global _smart_money_cache
    try:
        async with async_session() as session:
            result = await session.execute(select(SmartMoneyWallet.wallet_address))
            addresses = {row[0] for row in result.fetchall()}
            _smart_money_cache = addresses | set(INITIAL_SMART_MONEY)
            if _smart_money_cache:
                logger.info(f"Loaded {len(_smart_money_cache)} smart money wallets")
            else:
                logger.warning(
                    "Smart money wallet list is empty — criterion will score neutral. "
                    "Add wallets via DB or populate INITIAL_SMART_MONEY in wallet_list.py"
                )
    except Exception as e:
        logger.warning(f"Failed to load smart money from DB: {e}")
        _smart_money_cache = set(INITIAL_SMART_MONEY)


async def add_wallet(address: str, label: str = "", source: str = "manual") -> bool:
    """Add a new smart money wallet."""
    global _smart_money_cache
    try:
        async with async_session() as session:
            existing = await session.execute(
                select(SmartMoneyWallet).where(
                    SmartMoneyWallet.wallet_address == address
                )
            )
            if existing.scalar_one_or_none():
                return False

            wallet = SmartMoneyWallet(
                wallet_address=address,
                label=label,
                source=source,
                last_updated=datetime.utcnow(),
            )
            session.add(wallet)
            await session.commit()

        # Update cache
        if _smart_money_cache is not None:
            _smart_money_cache.add(address)
        return True
    except Exception as e:
        logger.error(f"Failed to add smart money wallet: {e}")
        return False


async def remove_wallet(address: str) -> bool:
    """Remove a smart money wallet."""
    global _smart_money_cache
    try:
        async with async_session() as session:
            result = await session.execute(
                select(SmartMoneyWallet).where(
                    SmartMoneyWallet.wallet_address == address
                )
            )
            wallet = result.scalar_one_or_none()
            if wallet:
                await session.delete(wallet)
                await session.commit()
                if _smart_money_cache:
                    _smart_money_cache.discard(address)
                return True
        return False
    except Exception as e:
        logger.error(f"Failed to remove smart money wallet: {e}")
        return False
