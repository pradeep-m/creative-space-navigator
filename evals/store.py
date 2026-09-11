"""Run artifacts on disk, plus the concurrency limiter shared by every suite."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
from collections.abc import Awaitable, AsyncIterator, Iterable
from pathlib import Path
from typing import Any, TypeVar

from evals import config

T = TypeVar("T")

_semaphore: asyncio.Semaphore | None = None


def _limiter() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(config.MAX_CONCURRENCY)
    return _semaphore


@asynccontextmanager
async def api_limit() -> AsyncIterator[None]:
    """Cap in-flight API calls. Must be used at the call site, not around batches.

    Wrapping a batch that itself waits on more limited calls deadlocks: the parents
    hold every slot while the children wait for a slot that will never free.
    """
    async with _limiter():
        yield


async def gather_limited(tasks: Iterable[Awaitable[T]]) -> list[T]:
    """Run a batch of coroutines. Concurrency is enforced inside each API call."""
    return await asyncio.gather(*tasks)


class RunStore:
    """Append-only JSONL artifacts for one run."""

    def __init__(self, run_id: str, root: Path | None = None) -> None:
        self.run_id = run_id
        self.dir = (root or config.OUTPUT_ROOT) / run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self._handles: dict[str, Any] = {}

    def append(self, name: str, record: dict) -> None:
        handle = self._handles.get(name)
        if handle is None:
            handle = self._handles[name] = (self.dir / f"{name}.jsonl").open("a")
        handle.write(json.dumps(record, default=str) + "\n")
        handle.flush()

    def append_many(self, name: str, records: Iterable[dict]) -> None:
        for record in records:
            self.append(name, record)

    def write_json(self, name: str, payload: object) -> Path:
        path = self.dir / name
        path.write_text(json.dumps(payload, indent=2, default=str))
        return path

    def write_text(self, name: str, text: str) -> Path:
        path = self.dir / name
        path.write_text(text)
        return path

    def read_jsonl(self, name: str) -> list[dict]:
        path = self.dir / f"{name}.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def close(self) -> None:
        for handle in self._handles.values():
            handle.close()
        self._handles.clear()


def cache_dir(kind: str) -> Path:
    """maps / generations / judgments, kept separate so re-judging never regenerates."""
    path = config.CACHE_ROOT / kind
    path.mkdir(parents=True, exist_ok=True)
    return path
