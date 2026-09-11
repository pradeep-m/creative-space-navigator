from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class FailureCase:
    """One concrete miss, carried into report.md so the report is not only aggregates."""

    kind: str
    context_id: str
    product: str
    target_audience: str
    map_summary: str
    selection: str
    concept: str
    scores: str
    judge_reason: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class SuiteResult:
    suite: str
    metrics: dict = field(default_factory=dict)
    failures: list[FailureCase] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["failures"] = [f.to_dict() for f in self.failures]
        return payload
