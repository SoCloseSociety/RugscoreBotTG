"""Social presence validation — Twitter/TG/Website via HTTP checks. All free."""

import asyncio
import logging
import re
from typing import Optional

import httpx

from utils.rate_limiter import get_limiter
from data.cache import cache

logger = logging.getLogger(__name__)

_client: Optional[httpx.AsyncClient] = None

# Cache TTL for social checks (5 minutes)
SOCIAL_CACHE_TTL = 300


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=5.0,
            limits=httpx.Limits(max_connections=5),
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; RugScoreBot/1.0)",
            },
        )
    return _client


def _normalize_twitter_url(url: str) -> str:
    """Normalize Twitter/X URL to a consistent format."""
    url = url.strip()
    if not url.startswith("http"):
        handle = url.lstrip("@/")
        url = f"https://x.com/{handle}"
    url = url.replace("twitter.com", "x.com")
    # Strip trailing slashes and query params for cleaner URLs
    url = url.split("?")[0].rstrip("/")
    return url


def _extract_twitter_handle(url: str) -> Optional[str]:
    """Extract Twitter handle from URL."""
    match = re.search(r"(?:x\.com|twitter\.com)/(@?\w+)", url)
    if match:
        return match.group(1).lstrip("@")
    return None


async def check_twitter(url: Optional[str]) -> dict:
    """Validate a Twitter/X link and extract basic info.

    Strategy:
    1. Check X.com directly (HTTP HEAD for accessibility)
    2. Try to scrape follower count from page (unreliable — X blocks scrapers)
    3. If no follower data, mark as accessible but unknown followers

    Returns: {exists, accessible, followers_estimate, account_age_days}
    """
    result = {
        "exists": False,
        "accessible": False,
        "followers_estimate": 0,
        "account_age_days": None,
        "url": url,
    }

    if not url:
        return result

    url = _normalize_twitter_url(url)
    result["exists"] = True
    result["url"] = url

    # Check cache first
    cache_key = f"social:twitter:{url}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    handle = _extract_twitter_handle(url)

    limiter = get_limiter("http_scrape")
    async with limiter:
        try:
            # HEAD request first — fast check if the profile exists
            resp = await _get_client().head(url)
            if resp.status_code == 200:
                result["accessible"] = True
            elif resp.status_code in (301, 302, 303, 307, 308):
                # Redirects are common on X.com — consider accessible
                result["accessible"] = True
            elif resp.status_code == 404:
                result["accessible"] = False
            else:
                # Try GET for more info
                resp = await _get_client().get(url)
                if resp.status_code == 200:
                    result["accessible"] = True
                    text = resp.text
                    # Try to extract follower count from various patterns
                    for pattern in [
                        r'"followers_count":(\d+)',
                        r'(\d[\d,]*)\s*(?:Followers|followers)',
                        r'followersCount["\s:]+(\d+)',
                    ]:
                        follower_match = re.search(pattern, text)
                        if follower_match:
                            count_str = follower_match.group(1).replace(",", "")
                            try:
                                result["followers_estimate"] = int(count_str)
                            except ValueError:
                                pass
                            break
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.debug(f"Twitter check failed for {url}: {e}")

    cache.set(cache_key, result, ttl=SOCIAL_CACHE_TTL)
    return result


async def check_telegram(url: Optional[str]) -> dict:
    """Validate a Telegram group/channel link.

    Telegram t.me pages are public and reliably return member counts.

    Returns: {exists, accessible, member_count_estimate}
    """
    result = {
        "exists": False,
        "accessible": False,
        "member_count_estimate": 0,
        "url": url,
    }

    if not url:
        return result

    url = url.strip()
    if not url.startswith("http"):
        url = f"https://t.me/{url.lstrip('@/')}"

    result["exists"] = True
    result["url"] = url

    # Check cache
    cache_key = f"social:telegram:{url}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    limiter = get_limiter("http_scrape")
    async with limiter:
        try:
            resp = await _get_client().get(url)
            if resp.status_code == 200:
                result["accessible"] = True
                text = resp.text
                # Telegram pages reliably show member counts in various formats
                for pattern in [
                    r'(\d[\d\s,]*)\s*(?:members|subscribers|membre)',
                    r'class="tgme_page_extra">(\d[\d\s,]*)',
                ]:
                    member_match = re.search(pattern, text, re.IGNORECASE)
                    if member_match:
                        count_str = member_match.group(1).replace(",", "").replace(" ", "")
                        try:
                            result["member_count_estimate"] = int(count_str)
                        except ValueError:
                            pass
                        break
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.debug(f"Telegram check failed for {url}: {e}")

    cache.set(cache_key, result, ttl=SOCIAL_CACHE_TTL)
    return result


async def check_website(url: Optional[str]) -> dict:
    """Validate a website URL — check HTTP response and SSL.

    Returns: {exists, accessible, has_ssl, domain}
    """
    result = {
        "exists": False,
        "accessible": False,
        "has_ssl": False,
        "domain": None,
        "url": url,
    }

    if not url:
        return result

    url = url.strip()
    if not url.startswith("http"):
        url = f"https://{url}"

    result["exists"] = True
    result["url"] = url

    # Extract domain
    domain_match = re.search(r"https?://([^/]+)", url)
    if domain_match:
        result["domain"] = domain_match.group(1)

    # Check cache
    cache_key = f"social:website:{url}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    limiter = get_limiter("http_scrape")
    async with limiter:
        try:
            resp = await _get_client().head(url)
            result["accessible"] = resp.status_code < 400
            result["has_ssl"] = url.startswith("https")
        except httpx.ConnectError:
            # Try without SSL if HTTPS fails
            if url.startswith("https"):
                try:
                    http_url = url.replace("https://", "http://", 1)
                    resp = await _get_client().head(http_url)
                    result["accessible"] = resp.status_code < 400
                    result["has_ssl"] = False
                except (httpx.HTTPError, httpx.TimeoutException):
                    pass
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.debug(f"Website check failed for {url}: {e}")

    cache.set(cache_key, result, ttl=SOCIAL_CACHE_TTL)
    return result


async def check_all_socials(metadata: dict) -> dict:
    """Check all social links from token metadata in parallel.

    Args:
        metadata: Token metadata containing twitter, telegram, website fields.

    Returns: {twitter: {...}, telegram: {...}, website: {...}}
    """
    twitter_url = metadata.get("twitter") or metadata.get("twitter_url")
    telegram_url = metadata.get("telegram") or metadata.get("telegram_url")
    website_url = metadata.get("website") or metadata.get("website_url")

    results = await asyncio.gather(
        check_twitter(twitter_url),
        check_telegram(telegram_url),
        check_website(website_url),
        return_exceptions=True,
    )

    return {
        "twitter": results[0] if not isinstance(results[0], Exception) else {"exists": False, "accessible": False},
        "telegram": results[1] if not isinstance(results[1], Exception) else {"exists": False, "accessible": False},
        "website": results[2] if not isinstance(results[2], Exception) else {"exists": False, "accessible": False},
    }


async def close():
    """Close the HTTP client."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
