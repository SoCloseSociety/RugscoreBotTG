"""Native Solana RPC client — free, no API key required."""

from __future__ import annotations

import logging
import struct
from typing import Any, Optional

import base58
import httpx

from utils.rate_limiter import get_limiter
from utils.rpc_rotator import rpc_rotator
from data.cache import cache

logger = logging.getLogger(__name__)

# Shared httpx client (connection pooling)
_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=5.0, limits=httpx.Limits(max_connections=20))
    return _client


async def _rpc_call(method: str, params: list, use_helius: bool = False) -> Any:
    """Make a JSON-RPC call to a Solana RPC endpoint with rotation and rate limiting."""
    limiter = get_limiter("helius" if use_helius else "solana_rpc")
    endpoint = await rpc_rotator.get_endpoint() if not use_helius else rpc_rotator.primary
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}

    async with limiter:
        try:
            resp = await _get_client().post(endpoint, json=payload)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                logger.warning(f"RPC error {method}: {data['error']}")
                return None
            await rpc_rotator.report_success(endpoint)
            return data.get("result")
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.warning(f"RPC call {method} failed on {endpoint[:40]}...: {e}")
            await rpc_rotator.report_failure(endpoint)
            # Retry on fallback (with rate limiting)
            fallback = await rpc_rotator.get_endpoint()
            if fallback != endpoint:
                async with limiter:
                    try:
                        resp = await _get_client().post(fallback, json=payload)
                        resp.raise_for_status()
                        data = resp.json()
                        if "error" not in data:
                            await rpc_rotator.report_success(fallback)
                            return data.get("result")
                    except Exception:
                        pass
            return None


async def get_account_info(address: str) -> Optional[dict]:
    """Fetch raw account info for a Solana account."""
    cache_key = f"account_info:{address}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = await _rpc_call("getAccountInfo", [address, {"encoding": "base64"}])
    if result and result.get("value"):
        cache.set(cache_key, result["value"], ttl=120)
        return result["value"]
    return None


async def get_token_largest_accounts(mint: str) -> Optional[list[dict]]:
    """Get the top 20 largest token holders. FREE — no API key needed."""
    cache_key = f"largest_accounts:{mint}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = await _rpc_call("getTokenLargestAccounts", [mint])
    if result and result.get("value"):
        accounts = result["value"]
        cache.set(cache_key, accounts, ttl=120)
        return accounts
    return None


async def get_token_supply(mint: str) -> Optional[dict]:
    """Get total token supply."""
    cache_key = f"token_supply:{mint}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = await _rpc_call("getTokenSupply", [mint])
    if result and result.get("value"):
        cache.set(cache_key, result["value"], ttl=120)
        return result["value"]
    return None


async def get_signatures_for_address(
    address: str, limit: int = 20, before: Optional[str] = None
) -> Optional[list[dict]]:
    """Get recent transaction signatures for an address."""
    params: dict[str, Any] = {"limit": limit}
    if before:
        params["before"] = before
    result = await _rpc_call("getSignaturesForAddress", [address, params])
    return result if result else None


async def get_transaction(signature: str) -> Optional[dict]:
    """Get full transaction details by signature."""
    cache_key = f"tx:{signature}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = await _rpc_call(
        "getTransaction",
        [signature, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
    )
    if result:
        cache.set(cache_key, result, ttl=600)  # Transactions are immutable
        return result
    return None


def parse_mint_account(data_b64: str) -> dict:
    """Parse raw Mint account data to extract mint_authority and freeze_authority.

    SPL Token Mint layout (82 bytes):
    - [0:4]   option<COption> for mint_authority (4 bytes: 0=None, 1=Some)
    - [4:36]  mint_authority pubkey (32 bytes)
    - [36:44] supply (u64)
    - [44:45] decimals (u8)
    - [45:46] is_initialized (bool)
    - [46:50] option<COption> for freeze_authority
    - [50:82] freeze_authority pubkey (32 bytes)
    """
    import base64

    raw = base64.b64decode(data_b64)
    if len(raw) < 82:
        return {"mint_authority": None, "freeze_authority": None, "supply": 0, "decimals": 0}

    # Mint authority
    mint_auth_option = struct.unpack_from("<I", raw, 0)[0]
    mint_authority = None
    if mint_auth_option == 1:
        mint_authority = base58.b58encode(raw[4:36]).decode()

    # Supply and decimals
    supply = struct.unpack_from("<Q", raw, 36)[0]
    decimals = raw[44]

    # Freeze authority
    freeze_auth_option = struct.unpack_from("<I", raw, 46)[0]
    freeze_authority = None
    if freeze_auth_option == 1:
        freeze_authority = base58.b58encode(raw[50:82]).decode()

    return {
        "mint_authority": mint_authority,
        "freeze_authority": freeze_authority,
        "supply": supply,
        "decimals": decimals,
    }


async def get_token_account_owner(token_account_address: str) -> Optional[str]:
    """Resolve the owner wallet address of a token account (ATA).

    getTokenLargestAccounts returns token account addresses, not owners.
    This function fetches the parsed account info to extract the owner.
    """
    cache_key = f"token_acc_owner:{token_account_address}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = await _rpc_call(
        "getAccountInfo",
        [token_account_address, {"encoding": "jsonParsed"}],
    )
    if result and result.get("value"):
        try:
            parsed = result["value"]["data"]["parsed"]["info"]
            owner = parsed.get("owner")
            if owner:
                cache.set(cache_key, owner, ttl=300)
                return owner
        except (KeyError, TypeError):
            pass
    return None


_SYSTEM_PROGRAM = "11111111111111111111111111111111"
_TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
_TOKEN_2022 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"


async def get_address_type(address: str) -> str:
    """Determine what type of Solana account an address is.

    Returns: 'wallet', 'token', 'program', or 'unknown'.
    """
    account = await get_account_info(address)
    if not account:
        return "wallet"  # No on-chain account = unfunded wallet

    owner = account.get("owner", "")
    if owner == _SYSTEM_PROGRAM:
        return "wallet"
    elif owner in (_TOKEN_PROGRAM, _TOKEN_2022):
        return "token"
    else:
        return "program"


async def close():
    """Close the HTTP client."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
