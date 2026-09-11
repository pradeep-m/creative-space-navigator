from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class Concept:
    concept_id: str
    generation_id: str
    headline: str
    body: str
    angle: str

    @property
    def text(self) -> str:
        """What the judge sees.

        `angle` is deliberately excluded: it states the strategic move in the open
        ("reframes price as cost per use") and would leak the intended pole.
        """
        return f"{self.headline}\n{self.body}".strip()

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "text": self.text}


@dataclass
class Generation:
    """One generator API call and the concepts it produced."""

    generation_id: str
    run_id: str
    context_id: str
    suite: str
    arm: str
    condition: str
    rep: int
    selections: list[dict] = field(default_factory=list)
    map_ids: list[str] = field(default_factory=list)
    concepts: list[Concept] = field(default_factory=list)
    model: str = ""
    temperature: float | None = None
    prompt_hash: str = ""
    production_prompt_hash: str = ""
    cache_key: str = ""
    raw_response: object = None
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["concepts"] = [c.to_dict() for c in self.concepts]
        return payload
