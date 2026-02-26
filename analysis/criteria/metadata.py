"""Criterion 7 — Metadata Quality (weight: 5%).

Checks metadata completeness, copycat detection, image presence.
Data source: Helius getAsset (DAS API, free tier) or metadata URI.
"""

import asyncio
import logging
from typing import Optional

from fuzzywuzzy import fuzz

from analysis.criteria import CriterionResult
from config.constants import KNOWN_TOKEN_NAMES, DESCRIPTION_MIN_LENGTH
from utils.helpers import clamp

logger = logging.getLogger(__name__)


async def score_metadata(asset_data: Optional[dict]) -> CriterionResult:
    """Analyze metadata quality for a token.

    Checks:
    - has_complete_metadata: name + symbol + image + description (+40/+20/+5)
    - name_not_copycat: Not imitating known tokens (+25/+5)
    - image_exists: Token image accessible (+15)
    - description_quality: Description length and coherence (+20/+5)
    """
    score = 0.0
    flags = []
    details = {}

    if not asset_data:
        return CriterionResult(
            name="Metadata",
            score=25,
            flags=["\u274c Metadata unavailable \u2014 cannot verify token identity"],
            details={},
            estimated=True,
        )

    # Extract metadata fields
    content = asset_data.get("content", {})
    metadata = content.get("metadata", {})
    json_uri = content.get("json_uri", "")

    name = metadata.get("name", "") or asset_data.get("name", "")
    symbol = metadata.get("symbol", "") or asset_data.get("symbol", "")
    description = metadata.get("description", "")
    image = _extract_image(content)

    details["name"] = name
    details["symbol"] = symbol
    details["has_description"] = bool(description)
    details["has_image"] = bool(image)

    # --- Completeness ---
    fields_present = sum(bool(x) for x in [name, symbol, image, description])
    details["fields_present"] = fields_present

    if fields_present == 4:
        score += 40
        flags.append("\u2705 Complete metadata")
    elif fields_present >= 2:
        score += 20
        flags.append("\u26a0\ufe0f Partial metadata")
    else:
        score += 5
        flags.append("\u274c Minimal metadata")

    # --- Copycat detection (run in executor to avoid blocking event loop) ---
    loop = asyncio.get_running_loop()
    is_copycat = await loop.run_in_executor(None, _check_copycat, name, symbol)
    details["is_copycat"] = is_copycat

    if not is_copycat:
        score += 25
        flags.append("\u2705 Original name")
    else:
        score += 5
        flags.append("\u26a0\ufe0f Name similar to known token")

    # --- Image ---
    if image:
        score += 15
    else:
        flags.append("\u26a0\ufe0f No token image")

    # --- Description quality ---
    if description and len(description) >= DESCRIPTION_MIN_LENGTH:
        score += 20
        flags.append("\u2705 Good description")
    elif description:
        score += 10
        flags.append("\u26a0\ufe0f Short description")
    else:
        score += 5

    return CriterionResult(
        name="Metadata",
        score=clamp(score),
        flags=flags,
        details=details,
    )


def _check_copycat(name: str, symbol: str) -> bool:
    """Check if token name/symbol is suspiciously similar to known tokens."""
    if not name and not symbol:
        return False

    check_str = (name + " " + symbol).upper()

    for known in KNOWN_TOKEN_NAMES:
        # Exact match of symbol
        if symbol.upper() == known:
            return True
        # Fuzzy match of name
        if fuzz.ratio(name.upper(), known) > 80:
            return True
        # Partial match
        if fuzz.partial_ratio(check_str, known) > 90:
            return True

    return False


def _extract_image(content: dict) -> Optional[str]:
    """Extract image URL from asset content."""
    # Try files array
    files = content.get("files", [])
    for f in files:
        if isinstance(f, dict):
            mime = f.get("mime", "")
            if "image" in mime:
                return f.get("uri")

    # Try links
    links = content.get("links", {})
    if links.get("image"):
        return links["image"]

    # Try metadata image field
    metadata = content.get("metadata", {})
    return metadata.get("image")
