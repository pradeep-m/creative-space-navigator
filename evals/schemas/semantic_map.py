from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Axis:
    name: str
    low_label: str
    high_label: str

    def pole(self, side: str) -> str:
        return self.high_label if side == "high" else self.low_label


@dataclass(frozen=True)
class SemanticMap:
    """A production 2x2.

    Production emits one map-level `rationale` covering both axes rather than the per-axis
    description the PRD data model assumes, so the eval carries the production shape.
    """

    context_id: str
    map_id: str
    title: str
    x_axis: Axis
    y_axis: Axis
    rationale: str

    @classmethod
    def from_production(cls, context_id: str, map_id: str, raw: dict) -> SemanticMap:
        return cls(
            context_id=context_id,
            map_id=map_id,
            title=raw.get("title", map_id),
            x_axis=Axis(**{k: raw["x_axis"][k] for k in ("name", "low_label", "high_label")}),
            y_axis=Axis(**{k: raw["y_axis"][k] for k in ("name", "low_label", "high_label")}),
            rationale=raw.get("rationale", ""),
        )

    def axis(self, which: str) -> Axis:
        return self.x_axis if which == "x" else self.y_axis

    def to_prompt_dict(self) -> dict[str, object]:
        """The exact dict shape production prompt helpers expect."""
        return {
            "id": self.map_id,
            "title": self.title,
            "x_axis": asdict(self.x_axis),
            "y_axis": asdict(self.y_axis),
            "rationale": self.rationale,
        }

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class QuadrantSelection:
    map_id: str
    x_side: str  # "low" | "high"
    y_side: str

    def side(self, axis: str) -> str:
        return self.x_side if axis == "x" else self.y_side

    def flipped(self, axis: str) -> QuadrantSelection:
        opposite = {"low": "high", "high": "low"}
        if axis == "x":
            return QuadrantSelection(self.map_id, opposite[self.x_side], self.y_side)
        return QuadrantSelection(self.map_id, self.x_side, opposite[self.y_side])

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @staticmethod
    def all_quadrants(map_id: str) -> list[QuadrantSelection]:
        return [
            QuadrantSelection(map_id, x, y)
            for x in ("low", "high")
            for y in ("low", "high")
        ]
