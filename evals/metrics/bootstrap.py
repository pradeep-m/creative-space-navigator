"""Context-level bootstrap.

Benchmark context is the resampling unit, so hundreds of generations drawn from ten product
domains cannot masquerade as hundreds of independent domains.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from typing import TypeVar

from evals import config

T = TypeVar("T")

ITERATIONS = 2000


def bootstrap_ci(
    groups: dict[str, Sequence[T]],
    statistic: Callable[[list[T]], float | None],
    *,
    iterations: int = ITERATIONS,
    seed_parts: tuple[object, ...] = ("bootstrap",),
    alpha: float = 0.05,
) -> dict[str, float | None]:
    """Resample whole contexts with replacement and re-evaluate the statistic."""
    keys = [k for k, v in groups.items() if v]
    if len(keys) < 2:
        point = statistic([item for key in keys for item in groups[key]]) if keys else None
        return {"point": point, "low": None, "high": None, "n_contexts": len(keys)}

    rng = random.Random(config.derive_seed(*seed_parts))
    point = statistic([item for key in keys for item in groups[key]])

    samples: list[float] = []
    for _ in range(iterations):
        drawn = [rng.choice(keys) for _ in keys]
        pooled = [item for key in drawn for item in groups[key]]
        value = statistic(pooled)
        if value is not None:
            samples.append(value)

    if not samples:
        return {"point": point, "low": None, "high": None, "n_contexts": len(keys)}

    samples.sort()
    low = samples[int((alpha / 2) * (len(samples) - 1))]
    high = samples[int((1 - alpha / 2) * (len(samples) - 1))]
    return {"point": point, "low": low, "high": high, "n_contexts": len(keys)}


def paired_difference_ci(
    a_groups: dict[str, Sequence[T]],
    b_groups: dict[str, Sequence[T]],
    statistic: Callable[[list[T]], float | None],
    *,
    iterations: int = ITERATIONS,
    seed_parts: tuple[object, ...] = ("bootstrap", "difference"),
    alpha: float = 0.05,
) -> dict[str, float | None]:
    """CI on (a - b), resampling the same contexts in both arms on each draw.

    Pairing matters: the arms share contexts, so resampling them independently would
    inflate the interval with between-context variance that cancels out in practice.
    """
    keys = [k for k in a_groups if a_groups.get(k) and b_groups.get(k)]
    if len(keys) < 2:
        return {"point": None, "low": None, "high": None, "n_contexts": len(keys)}

    def combined(selected: list[str]) -> float | None:
        a_value = statistic([item for key in selected for item in a_groups[key]])
        b_value = statistic([item for key in selected for item in b_groups[key]])
        if a_value is None or b_value is None:
            return None
        return a_value - b_value

    rng = random.Random(config.derive_seed(*seed_parts))
    point = combined(keys)

    samples = []
    for _ in range(iterations):
        drawn = [rng.choice(keys) for _ in keys]
        value = combined(drawn)
        if value is not None:
            samples.append(value)

    if not samples:
        return {"point": point, "low": None, "high": None, "n_contexts": len(keys)}

    samples.sort()
    return {
        "point": point,
        "low": samples[int((alpha / 2) * (len(samples) - 1))],
        "high": samples[int((1 - alpha / 2) * (len(samples) - 1))],
        "n_contexts": len(keys),
    }


def mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def rate(flags: list[bool]) -> float | None:
    return sum(flags) / len(flags) if flags else None
