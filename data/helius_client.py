"""Helius free tier client — DAS API + enhanced transactions."""

import logging
from typing import Any, Optional

import httpx

from config.settings import settings
from config.constants import KNOWN_PROGRAM_ADDRESSES
from utils.rate_limiter import get_limiter
from data.cache import cache

logger = logging.getLogger(__name__)

_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=5.0, limits=httpx.Limits(max_connections=20))
    return _client


async def _das_call(method: str, params: dict) -> Any:
    """Make a DAS API call to Helius."""
    if not settings.helius_api_key:
        logger.warning("No Helius API key configured")
        return None

    limiter = get_limiter("helius")
    url = settings.helius_rpc_url
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}

    async with limiter:
        try:
            resp = await _get_client().post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                logger.warning(f"Helius DAS error {method}: {data['error']}")
                return None
            return data.get("result")
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.warning(f"Helius DAS {method} failed: {e}")
            return None


async def get_asset(mint: str) -> Optional[dict]:
    """Get complete token asset data via DAS API.

    Returns metadata, authorities, ownership, content, etc.
    Cost: 1 Helius credit.
    """
    cache_key = f"helius_asset:{mint}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = await _das_call("getAsset", {"id": mint})
    if result:
        cache.set(cache_key, result, ttl=120)
    return result


async def get_token_accounts(
    mint: str, page: int = 1, limit: int = 1000
) -> Optional[dict]:
    """Get token accounts (holders) via DAS API.

    Used for holder count estimation. Paginated.
    Cost: 1 Helius credit per page.
    """
    cache_key = f"helius_token_accounts:{mint}:p{page}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = await _das_call(
        "getTokenAccounts",
        {"mint": mint, "page": page, "limit": limit},
    )
    if result:
        cache.set(cache_key, result, ttl=120)
    return result


def _is_real_wallet(address: Optional[str]) -> bool:
    """Check if an address is a real wallet (not a program/authority)."""
    return bool(address) and address not in KNOWN_PROGRAM_ADDRESSES


async def get_asset_creator(mint: str) -> Optional[str]:
    """Extract the creator/deployer address from asset data.

    Multi-fallback strategy:
    1. Helius DAS — authorities with "creator" scope
    2. Helius DAS — creators list (Metaplex)
    3. Mint authority from raw account data (SPL Token)
    4. First transaction signer (Pump.fun and other new tokens)

    All results are filtered against known program addresses.
    """
    # --- 1 & 2: Helius DAS ---
    asset = await get_asset(mint)
    if asset:
        authorities = asset.get("authorities", [])
        for auth in authorities:
            if "creator" in auth.get("scopes", []):
                addr = auth.get("address")
                if _is_real_wallet(addr):
                    return addr

        creators = asset.get("creators", [])
        for creator in creators:
            addr = creator.get("address")
            if _is_real_wallet(addr):
                return addr

    # --- 3: Mint authority from raw account data ---
    try:
        from data.solana_rpc import get_account_info, parse_mint_account
        account = await get_account_info(mint)
        if account:
            data = account.get("data", [])
            if isinstance(data, list) and len(data) >= 1:
                parsed = parse_mint_account(data[0])
                mint_auth = parsed.get("mint_authority")
                if _is_real_wallet(mint_auth):
                    return mint_auth
    except Exception as e:
        logger.debug(f"Mint authority fallback failed: {e}")

    # --- 4: First transaction signer (works for Pump.fun) ---
    try:
        from data.solana_rpc import get_signatures_for_address, get_transaction

        # Fetch enough sigs to reach the creation tx (newest first).
        # For recent tokens, 1000 should reach the very first tx.
        sigs = await get_signatures_for_address(mint, limit=1000)
        if not sigs:
            return None

        # Paginate once more if we got a full page (token has >1000 txs)
        if len(sigs) >= 1000:
            last_sig = sigs[-1].get("signature")
            if last_sig:
                more = await get_signatures_for_address(mint, limit=1000, before=last_sig)
                if more:
                    sigs.extend(more)

        # Oldest signature = last in the list = creation tx
        oldest = sigs[-1]
        oldest_sig = oldest.get("signature")
        if not oldest_sig:
            return None
        tx = await get_transaction(oldest_sig)
        if tx:
            message = tx.get("transaction", {}).get("message", {})
            account_keys = message.get("accountKeys", [])
            # jsonParsed format: [{"pubkey": "...", "signer": true}, ...]
            for key in account_keys:
                if isinstance(key, dict) and key.get("signer"):
                    addr = key.get("pubkey")
                    if _is_real_wallet(addr):
                        return addr
            # Plain string list: first non-program key = fee payer = creator
            for key in account_keys:
                if isinstance(key, str) and _is_real_wallet(key):
                    return key
    except Exception as e:
        logger.debug(f"First-tx signer fallback failed: {e}")

    return None


async def get_holder_count_estimate(mint: str) -> int:
    """Estimate total holder count using paginated getTokenAccounts.

    Fetches first page to see total, then estimates.
    """
    result = await get_token_accounts(mint, page=1, limit=1000)
    if not result:
        return 0

    # If result has total field
    if isinstance(result, dict) and "total" in result:
        return result["total"]

    # If result is a list of accounts
    if isinstance(result, list):
        return len(result)

    # Check token_accounts field
    accounts = result.get("token_accounts", [])
    return len(accounts)


async def close():
    """Close the HTTP client."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
