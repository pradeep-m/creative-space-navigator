from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Judgment:
    """One blind 1-5 placement of one concept on one axis.

    Carries no field naming the selected quadrant, the desired pole or the arm the concept
    came from, which is how the blinding requirement is enforced structurally rather than
    by trusting prompt wording.
    """

    judgment_id: str
    concept_id: str
    map_id: str
    axis: str  # "x" | "y"
    score: int
    reason: str
    grounded: bool  # whether the map rationale was supplied as axis grounding
    judge_model: str
    judge_temperature: float | None
    judge_prompt_version: str
    repeat: int = 0  # >0 marks a self-consistency re-draw, not a primary judgment

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class AxisQualityJudgment:
    context_id: str
    map_id: str
    relevance: int
    polarity: int
    actionability: int
    axis_distinctness: int
    reason: str
    non_redundancy: int | None = None
    redundancy_reason: str = ""

    #: The four criteria that gate the predeclared high-quality rate; non-redundancy is
    #: reported separately per the PRD.
    GATING = ("relevance", "polarity", "actionability", "axis_distinctness")

    @property
    def high_quality(self) -> bool:
        return all(getattr(self, name) >= 4 for name in self.GATING)

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "high_quality": self.high_quality}
