"""Human-vs-judge agreement, and judge-vs-production-placement agreement.

Implemented directly rather than pulled from scipy so the harness keeps the app's three
dependencies.
"""

from __future__ import annotations

import math


def _ranks(values: list[float]) -> list[float]:
    """Average ranks, so ties do not distort the correlation."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        average = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = average
        i = j + 1
    return ranks


def pearson(a: list[float], b: list[float]) -> float | None:
    if len(a) != len(b) or len(a) < 2:
        return None
    mean_a, mean_b = sum(a) / len(a), sum(b) / len(b)
    num = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
    den = math.sqrt(sum((x - mean_a) ** 2 for x in a) * sum((y - mean_b) ** 2 for y in b))
    return num / den if den else None


def spearman(a: list[float], b: list[float]) -> float | None:
    if len(a) != len(b) or len(a) < 2:
        return None
    return pearson(_ranks(a), _ranks(b))


def summarize(human: list[float], judge: list[float]) -> dict[str, object]:
    """Agreement between two 1-5 score series aligned index-for-index."""
    if not human or len(human) != len(judge):
        return {"n": 0}

    errors = [abs(h - j) for h, j in zip(human, judge)]
    return {
        "n": len(human),
        "mean_absolute_error": sum(errors) / len(errors),
        "exact_agreement": sum(e == 0 for e in errors) / len(errors),
        "within_one_agreement": sum(e <= 1 for e in errors) / len(errors),
        "spearman_rho": spearman(human, judge),
        "meets_targets": (
            sum(errors) / len(errors) <= 0.75
            and sum(e <= 1 for e in errors) / len(errors) >= 0.85
            and (spearman(human, judge) or 0) >= 0.60
        ),
    }


def sign_agreement(production: list[float], judge: list[float]) -> float | None:
    """Do production's -1..+1 placement and the blind 1-5 judge pick the same side?

    Scores of exactly 3 (judge) or 0 (production) are excluded as genuinely undecided
    rather than counted as disagreements.
    """
    pairs = [
        (p, j) for p, j in zip(production, judge) if j != 3 and p != 0
    ]
    if not pairs:
        return None
    return sum((p > 0) == (j > 3) for p, j in pairs) / len(pairs)
