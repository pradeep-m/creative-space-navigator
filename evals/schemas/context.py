from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Context:
    """One fixed product x audience benchmark entry."""

    id: str
    product: str
    target_audience: str
    additional_context: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def load_contexts(path: Path, limit: int | None = None) -> list[Context]:
    raw = json.loads(Path(path).read_text())
    contexts = [Context(**entry) for entry in raw]
    ids = [c.id for c in contexts]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate context ids in fixture file")
    return contexts[:limit] if limit else contexts
