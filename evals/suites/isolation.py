"""Eval 4 - can one dimension be moved without dragging the other along?

The two interventions for a context share one base condition rather than generating a
separate control each. Same matched-pair logic, one fewer generation per pair, and both
interventions are measured against an identical baseline.
"""

from __future__ import annotations

from evals import config
from evals.harness import RunContext, judge_axes
from evals.metrics import isolation as isolation_metrics
from evals.schemas import Concept, Context, QuadrantSelection, SemanticMap
from evals.schemas.result import FailureCase, SuiteResult
from evals.store import gather_limited

NAME = "isolation"
OTHER = {"x": "y", "y": "x"}


async def _condition(
    rc: RunContext,
    context: Context,
    smap: SemanticMap,
    selection: QuadrantSelection,
    label: str,
) -> dict[str, list[int]]:
    """Generate for one quadrant and return raw 1-5 scores per axis.

    Raw, not normalised: movement is a before/after comparison on the same scale, and the
    selected side flips between the two halves of the pair.
    """
    generations = await gather_limited(
        [
            rc.adapter.generate_concepts(
                context,
                [smap],
                [selection],
                rc.profile.concepts_per_generation,
                suite=NAME,
                arm="navigator",
                condition=label,
                rep=rep,
            )
            for rep in range(rc.profile.isolation_reps)
        ]
    )
    concepts: list[Concept] = []
    for generation in generations:
        rc.record_generation(generation)
        concepts.extend(generation.concepts)

    judgments = await judge_axes(rc, context, concepts, [(smap, "x"), (smap, "y")])
    scores = {"x": [], "y": []}
    for judgment in judgments:
        scores[judgment.axis].append(judgment.score)
    return {**scores, "concepts": concepts, "judgments": judgments}


async def run(rc: RunContext) -> SuiteResult:
    interventions: list[isolation_metrics.Intervention] = []
    evidence = []

    for context in rc.contexts:
        maps = rc.maps[context.id]
        generator = config.rng(NAME, context.id)
        smap = generator.choice(maps)
        base = generator.choice(QuadrantSelection.all_quadrants(smap.map_id))

        before = await _condition(rc, context, smap, base, "base")
        for target_axis in ("x", "y"):
            flipped = base.flipped(target_axis)
            after = await _condition(
                rc, context, smap, flipped, f"flip_{target_axis}"
            )
            preserved = OTHER[target_axis]
            intervention = isolation_metrics.Intervention(
                context_id=context.id,
                map_id=smap.map_id,
                target_axis=target_axis,
                preserved_axis=preserved,
                target_before=before[target_axis],
                target_after=after[target_axis],
                preserved_before=before[preserved],
                preserved_after=after[preserved],
            )
            interventions.append(intervention)
            rc.store.append("results", {"suite": NAME, **intervention.to_dict()})
            evidence.append((context, smap, base, flipped, intervention, after))

    metrics = isolation_metrics.summarize(interventions)
    metrics["targets"] = {
        "target_movement_min": isolation_metrics.TARGET_MOVEMENT_MIN,
        "non_target_movement_max": isolation_metrics.NON_TARGET_MOVEMENT_MAX,
        "pct_meeting_both_target": 0.75,
        "meets_pct_target": (metrics.get("pct_meeting_both") or 0) >= 0.75,
    }

    failures = []
    worst = sorted(
        (e for e in evidence if e[4].complete),
        key=lambda e: -(e[4].non_target_movement or 0),
    )
    for context, smap, base, flipped, intervention, after in worst[:5]:
        if intervention.meets_criteria:
            continue
        target = smap.axis(intervention.target_axis)
        preserved = smap.axis(intervention.preserved_axis)
        example = after["concepts"][0].text if after["concepts"] else ""
        failures.append(
            FailureCase(
                kind="isolation",
                context_id=context.id,
                product=context.product,
                target_audience=context.target_audience,
                map_summary=f"{smap.title} | target {target.name} | preserved {preserved.name}",
                selection=(
                    f"{target.pole(base.side(intervention.target_axis))} -> "
                    f"{target.pole(flipped.side(intervention.target_axis))}, holding "
                    f"{preserved.pole(base.side(intervention.preserved_axis))}"
                ),
                concept=example,
                scores=(
                    f"target moved {intervention.target_movement:.2f}, "
                    f"preserved moved {intervention.non_target_movement:.2f}"
                ),
                judge_reason=(
                    after["judgments"][0].reason if after["judgments"] else ""
                ),
            )
        )

    return SuiteResult(suite=NAME, metrics=metrics, failures=failures)
