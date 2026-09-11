"""Quadrant coverage and balance for Eval 6."""

from __future__ import annotations

import math
from collections import Counter

QUADRANTS = [("low", "low"), ("high", "low"), ("low", "high"), ("high", "high")]


def assign(x_score: int, y_score: int) -> tuple[str, str] | None:
    """Quadrant from two 1-5 scores; None when either axis is ambiguous."""
    if x_score == 3 or y_score == 3:
        return None
    return ("high" if x_score > 3 else "low", "high" if y_score > 3 else "low")


def normalized_entropy(assignments: list[tuple[str, str]]) -> float | None:
    """H over the quadrant distribution divided by log(4): 0 concentrated, 1 balanced."""
    if not assignments:
        return None
    counts = Counter(assignments)
    total = len(assignments)
    entropy = -sum(
        (count / total) * math.log(count / total) for count in counts.values() if count
    )
    return entropy / math.log(4)


def summarize(scored: list[tuple[int, int]]) -> dict[str, object]:
    """scored is a list of (x_score, y_score) for every concept in one condition."""
    assignments = [a for a in (assign(x, y) for x, y in scored) if a is not None]
    ambiguous = len(scored) - len(assignments)
    counts = Counter(assignments)
    return {
        "n_concepts": len(scored),
        "quadrant_coverage": len(counts) / 4 if scored else None,
        "quadrants_represented": len(counts),
        "balanced_coverage": normalized_entropy(assignments),
        "ambiguity_rate": ambiguous / len(scored) if scored else None,
        "distribution": {f"{x}_{y}": counts[(x, y)] for x, y in QUADRANTS},
    }
