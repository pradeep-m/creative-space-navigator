"""Normalisation toward the selected pole, and adherence rates.

The judge always scores 1 = low_label, 5 = high_label and never learns which pole was
wanted. Flipping to "distance toward the selected pole" happens here, after the fact.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

ADHERENCE_THRESHOLD = 4


def normalize(score: int, side: str) -> int:
    """Re-express a 1-5 axis score as distance toward the selected pole."""
    return score if side == "high" else 6 - score


def adheres(normalized: int) -> bool:
    return normalized >= ADHERENCE_THRESHOLD


@dataclass
class ConstraintOutcome:
    """One selected pole, judged."""

    context_id: str
    concept_id: str
    map_id: str
    axis: str
    raw_score: int
    normalized: int
    reason: str = ""

    @property
    def adhered(self) -> bool:
        return adheres(self.normalized)

    @property
    def ambiguous(self) -> bool:
        return self.raw_score == 3


def by_concept(outcomes: list[ConstraintOutcome]) -> dict[str, list[ConstraintOutcome]]:
    grouped: dict[str, list[ConstraintOutcome]] = defaultdict(list)
    for outcome in outcomes:
        grouped[outcome.concept_id].append(outcome)
    return dict(grouped)


def joint_adherence_flags(outcomes: list[ConstraintOutcome]) -> dict[str, bool]:
    """Per concept: did every selected pole land at 4 or better?"""
    return {
        concept_id: all(o.adhered for o in items)
        for concept_id, items in by_concept(outcomes).items()
    }


def partial_adherence_rates(outcomes: list[ConstraintOutcome]) -> dict[str, float]:
    """Per concept: fraction of selected constraints satisfied."""
    return {
        concept_id: sum(o.adhered for o in items) / len(items)
        for concept_id, items in by_concept(outcomes).items()
    }


def _rate(values: list[bool]) -> float | None:
    return sum(values) / len(values) if values else None


def summarize(outcomes: list[ConstraintOutcome]) -> dict[str, object]:
    if not outcomes:
        return {"n_constraints": 0, "n_concepts": 0}

    per_axis = {axis: [o.adhered for o in outcomes if o.axis == axis] for axis in ("x", "y")}
    joint = list(joint_adherence_flags(outcomes).values())
    partial = list(partial_adherence_rates(outcomes).values())

    return {
        "n_constraints": len(outcomes),
        "n_concepts": len(joint),
        "x_adherence": _rate(per_axis["x"]),
        "y_adherence": _rate(per_axis["y"]),
        "per_axis_adherence": _rate([o.adhered for o in outcomes]),
        "joint_adherence": _rate(joint),
        "mean_constraint_adherence": sum(partial) / len(partial) if partial else None,
        "average_normalized_target_score": sum(o.normalized for o in outcomes) / len(outcomes),
        "ambiguous_rate": _rate([o.ambiguous for o in outcomes]),
    }


def group_by_context(outcomes: list[ConstraintOutcome]) -> dict[str, list[ConstraintOutcome]]:
    grouped: dict[str, list[ConstraintOutcome]] = defaultdict(list)
    for outcome in outcomes:
        grouped[outcome.context_id].append(outcome)
    return dict(grouped)


def joint_groups_by_context(outcomes: list[ConstraintOutcome]) -> dict[str, list[bool]]:
    """Per-concept joint adherence flags, bucketed by context for the bootstrap."""
    grouped: dict[str, list[bool]] = defaultdict(list)
    for context_id, items in group_by_context(outcomes).items():
        grouped[context_id] = list(joint_adherence_flags(items).values())
    return dict(grouped)


def constraint_groups_by_context(outcomes: list[ConstraintOutcome]) -> dict[str, list[bool]]:
    """Per-constraint adherence flags, bucketed by context."""
    grouped: dict[str, list[bool]] = defaultdict(list)
    for outcome in outcomes:
        grouped[outcome.context_id].append(outcome.adhered)
    return dict(grouped)
