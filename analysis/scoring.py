"""Composite score calculation — weighted average of all criteria."""

from __future__ import annotations

import logging
from typing import Optional

from analysis.criteria import CriterionResult
from config.constants import SCORING_WEIGHTS, RISK_LABELS
from utils.helpers import clamp

logger = logging.getLogger(__name__)


def calculate_composite_score(criteria_results: dict[str, CriterionResult]) -> dict:
    """Calculate the weighted composite score from individual criteria.

    Args:
        criteria_results: Dict of criterion_name -> CriterionResult

    Returns dict with total_score, risk info, criteria, flags, and data_quality.
    """
    total_score = 0.0
    total_weight = 0.0
    all_flags = []
    estimated_criteria = []

    for name, weight in SCORING_WEIGHTS.items():
        result = criteria_results.get(name)
        if result:
            total_score += result.score * weight
            total_weight += weight
            all_flags.extend(result.flags)
            if result.estimated:
                estimated_criteria.append(name)

    # Handle missing criteria: treat as SUSPICIOUS (25) — not neutral
    # Missing data = can't verify = risky
    if total_weight > 0 and total_weight < 0.99:
        missing_weight = 1.0 - total_weight
        total_score = total_score + (missing_weight * 25)
    elif total_weight == 0:
        total_score = 25

    total_score = clamp(round(total_score, 1))

    # Data quality: % of criteria with real (non-estimated) data
    total_criteria = len(SCORING_WEIGHTS)
    real_criteria = total_criteria - len(estimated_criteria)
    data_quality = round((real_criteria / total_criteria) * 100) if total_criteria > 0 else 0

    # Get risk label
    risk = get_risk_label(total_score)

    return {
        "total_score": total_score,
        "risk_label": risk["label"],
        "risk_emoji": risk["emoji"],
        "risk_desc": risk["desc"],
        "criteria": criteria_results,
        "all_flags": all_flags,
        "data_quality": data_quality,
        "estimated_criteria": estimated_criteria,
    }


def get_risk_label(score: float) -> dict:
    """Get the risk label for a given score."""
    for (low, high), label_info in RISK_LABELS.items():
        if low <= score <= high:
            return label_info
    # Default fallback
    return {"emoji": "\u26a0\ufe0f", "label": "UNKNOWN", "desc": "Score out of range"}
