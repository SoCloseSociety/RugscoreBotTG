"""Criterion 6 — Social Legitimacy (weight: 10%).

Validates Twitter, Telegram, Website from token metadata.
Data source: HTTP checks + metadata URI parsing (FREE).
"""

import logging
from typing import Optional

from analysis.criteria import CriterionResult
from config.constants import (
    TWITTER_FOLLOWERS_GOOD, TWITTER_FOLLOWERS_GREAT,
)
from data.social_checker import check_all_socials
from utils.helpers import clamp

logger = logging.getLogger(__name__)


async def score_social(metadata: dict) -> CriterionResult:
    """Analyze social presence for a token.

    Checks:
    - has_twitter: Valid Twitter/X link (+15), followers bonus (+10/+15)
    - has_telegram: Valid Telegram group (+15)
    - has_website: Valid website with SSL (+15)
    - all_present: Bonus if all 3 present (+10)
    """
    score = 0.0
    flags = []
    details = {}

    # Check all social links in parallel
    socials = await check_all_socials(metadata)

    # --- Twitter ---
    twitter = socials.get("twitter", {})
    details["twitter"] = twitter
    if twitter.get("exists") and twitter.get("accessible"):
        score += 15
        followers = twitter.get("followers_estimate", 0)
        if followers >= TWITTER_FOLLOWERS_GREAT:
            score += 15
            flags.append(f"\u2705 Twitter ({followers:,} followers)")
        elif followers >= TWITTER_FOLLOWERS_GOOD:
            score += 10
            flags.append(f"\u2705 Twitter ({followers:,} followers)")
        else:
            flags.append("\u2705 Twitter (accessible)")
    elif twitter.get("exists"):
        score += 5
        flags.append("\u26a0\ufe0f Twitter link exists but not accessible")
    else:
        flags.append("\u274c No Twitter")

    # --- Telegram ---
    telegram = socials.get("telegram", {})
    details["telegram"] = telegram
    if telegram.get("exists") and telegram.get("accessible"):
        score += 15
        members = telegram.get("member_count_estimate", 0)
        if members > 0:
            flags.append(f"\u2705 Telegram ({members:,} members)")
        else:
            flags.append("\u2705 Telegram group (active)")
    elif telegram.get("exists"):
        score += 5
        flags.append("\u26a0\ufe0f Telegram link exists but not accessible")
    else:
        flags.append("\u274c No Telegram group")

    # --- Website ---
    website = socials.get("website", {})
    details["website"] = website
    if website.get("exists") and website.get("accessible"):
        score += 15
        if website.get("has_ssl"):
            flags.append("\u2705 Website (SSL \u2705)")
        else:
            score -= 5
            flags.append("\u26a0\ufe0f Website (no SSL)")
    elif website.get("exists"):
        score += 5
        flags.append("\u26a0\ufe0f Website link exists but not accessible")
    else:
        flags.append("\u274c No website")

    # --- All socials present bonus ---
    all_present = (
        twitter.get("accessible", False)
        and telegram.get("accessible", False)
        and website.get("accessible", False)
    )
    details["all_socials_present"] = all_present
    if all_present:
        score += 10
        flags.append("\u2705 All social channels present")

    return CriterionResult(
        name="Social",
        score=clamp(score),
        flags=flags,
        details=details,
    )
