"""Shared run state and the judging helper every suite goes through."""

from __future__ import annotations

from dataclasses import dataclass, field

from evals import config, store
from evals.adapters import judge
from evals.adapters.navigator import NavigatorAdapter
from evals.config import Profile
from evals.metrics.adherence import ConstraintOutcome, normalize
from evals.schemas import (
    Concept,
    Context,
    Generation,
    Judgment,
    QuadrantSelection,
    SemanticMap,
)
from evals.store import RunStore, gather_limited


@dataclass
class RunContext:
    run_id: str
    profile: Profile
    store: RunStore
    adapter: NavigatorAdapter
    contexts: list[Context]
    maps: dict[str, list[SemanticMap]] = field(default_factory=dict)
    # Cross-suite handoff: steering leaves its outcomes here for the ablation and
    # calibration suites, which would otherwise have to re-derive them.
    artifacts: dict[str, object] = field(default_factory=dict)

    def context(self, context_id: str) -> Context:
        return next(c for c in self.contexts if c.id == context_id)

    def map_by_id(self, context_id: str, map_id: str) -> SemanticMap:
        return next(m for m in self.maps[context_id] if m.map_id == map_id)

    def record_generation(self, generation: Generation) -> Generation:
        self.store.append("generations", generation.to_dict())
        return generation

    def record_judgments(self, judgments: list[Judgment]) -> list[Judgment]:
        self.store.append_many("judgments", (j.to_dict() for j in judgments))
        return judgments


async def judge_axes(
    rc: RunContext,
    context: Context,
    concepts: list[Concept],
    targets: list[tuple[SemanticMap, str]],
    *,
    grounded: bool = True,
    repeat: int = 0,
) -> list[Judgment]:
    """Score every concept on every (map, axis) target. One API call per pair.

    The judgment cache is content-addressed on concept text plus axis definition, so a
    concept scored by two suites costs one call.
    """
    tasks = [
        judge.score_axis(
            product=context.product,
            audience=context.target_audience,
            concept_id=concept.concept_id,
            concept_text=concept.text,
            smap=smap,
            axis=axis,
            grounded=grounded,
            repeat=repeat,
        )
        for concept in concepts
        for smap, axis in targets
    ]
    judgments = await gather_limited(tasks)
    return rc.record_judgments(judgments)


def selected_targets(
    maps: list[SemanticMap], selections: list[QuadrantSelection]
) -> list[tuple[SemanticMap, str]]:
    by_id = {m.map_id: m for m in maps}
    return [
        (by_id[s.map_id], axis) for s in selections for axis in ("x", "y")
    ]


def outcomes_from(
    context_id: str,
    judgments: list[Judgment],
    selections: list[QuadrantSelection],
) -> list[ConstraintOutcome]:
    """Attach the selected pole to each judgment and normalise toward it."""
    sides = {s.map_id: s for s in selections}
    outcomes = []
    for judgment in judgments:
        selection = sides.get(judgment.map_id)
        if selection is None:
            continue
        side = selection.side(judgment.axis)
        outcomes.append(
            ConstraintOutcome(
                context_id=context_id,
                concept_id=judgment.concept_id,
                map_id=judgment.map_id,
                axis=judgment.axis,
                raw_score=judgment.score,
                normalized=normalize(judgment.score, side),
                reason=judgment.reason,
            )
        )
    return outcomes


async def build_maps(rc: RunContext) -> dict[str, list[SemanticMap]]:
    """One production map-generation call per context, shared by every suite."""
    results = await gather_limited(
        [rc.adapter.generate_maps(ctx, rc.profile.maps_per_context) for ctx in rc.contexts]
    )
    maps = {ctx.id: result for ctx, result in zip(rc.contexts, results)}
    for context_id, context_maps in maps.items():
        for smap in context_maps:
            rc.store.append("maps", {**smap.to_dict(), "run_id": rc.run_id})
    return maps


def sample_quadrants(
    context_id: str, smap: SemanticMap, count: int
) -> list[QuadrantSelection]:
    """Deterministic quadrant choice, keyed so the same run seed always picks the same ones."""
    quadrants = QuadrantSelection.all_quadrants(smap.map_id)
    generator = config.rng("quadrants", context_id, smap.map_id)
    generator.shuffle(quadrants)
    return quadrants[:count]
