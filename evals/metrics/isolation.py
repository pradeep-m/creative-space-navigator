"""Axis-isolation movement for Eval 4."""

from __future__ import annotations

from dataclasses import dataclass

TARGET_MOVEMENT_MIN = 2.0
NON_TARGET_MOVEMENT_MAX = 0.75


@dataclass
class Intervention:
    """One matched pair: same map, one axis flipped, the other held."""

    context_id: str
    map_id: str
    target_axis: str
    preserved_axis: str
    target_before: list[int]
    target_after: list[int]
    preserved_before: list[int]
    preserved_after: list[int]

    @staticmethod
    def _mean(values: list[int]) -> float | None:
        return sum(values) / len(values) if values else None

    @property
    def target_movement(self) -> float | None:
        before, after = self._mean(self.target_before), self._mean(self.target_after)
        return None if before is None or after is None else abs(after - before)

    @property
    def non_target_movement(self) -> float | None:
        before, after = self._mean(self.preserved_before), self._mean(self.preserved_after)
        return None if before is None or after is None else abs(after - before)

    @property
    def complete(self) -> bool:
        return self.target_movement is not None and self.non_target_movement is not None

    @property
    def meets_criteria(self) -> bool:
        if not self.complete:
            return False
        return (
            self.target_movement >= TARGET_MOVEMENT_MIN
            and self.non_target_movement <= NON_TARGET_MOVEMENT_MAX
        )

    @property
    def isolation_ratio(self) -> float | None:
        """Descriptive only, never pass/fail. Floored so a zero denominator cannot blow up."""
        if not self.complete:
            return None
        return self.target_movement / max(self.non_target_movement, 0.25)

    def to_dict(self) -> dict[str, object]:
        return {
            "context_id": self.context_id,
            "map_id": self.map_id,
            "target_axis": self.target_axis,
            "preserved_axis": self.preserved_axis,
            "target_movement": self.target_movement,
            "non_target_movement": self.non_target_movement,
            "isolation_ratio": self.isolation_ratio,
            "meets_criteria": self.meets_criteria,
        }


def summarize(interventions: list[Intervention]) -> dict[str, object]:
    complete = [i for i in interventions if i.complete]
    if not complete:
        return {"n_interventions": 0}

    target = [i.target_movement for i in complete]
    non_target = [i.non_target_movement for i in complete]
    ratios = [i.isolation_ratio for i in complete]

    return {
        "n_interventions": len(complete),
        "target_movement": sum(target) / len(target),
        "non_target_movement": sum(non_target) / len(non_target),
        "median_isolation_ratio": sorted(ratios)[len(ratios) // 2],
        "pct_meeting_both": sum(i.meets_criteria for i in complete) / len(complete),
        "meets_target_movement": (sum(target) / len(target)) >= TARGET_MOVEMENT_MIN,
        "meets_non_target_movement": (
            sum(non_target) / len(non_target)
        ) <= NON_TARGET_MOVEMENT_MAX,
    }
