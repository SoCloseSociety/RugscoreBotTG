"""Scoring criteria modules — each returns a CriterionResult."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CriterionResult:
    """Result from a single scoring criterion."""
    name: str
    score: float  # 0-100
    flags: list[str] = field(default_factory=list)  # Green/yellow/red flags
    details: dict = field(default_factory=dict)  # Raw details for display
    estimated: bool = False  # True if score is based on incomplete/estimated data
