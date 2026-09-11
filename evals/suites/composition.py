"""Eval 5 - do constraints survive selecting a quadrant from several maps at once?

The scientific output is the degradation curve across 2, 4 and 6 constraints, not whether
each level clears its engineering target.
"""

from __future__ import annotations

from evals import config
from evals.baselines import naive_steering
from evals.harness import RunContext, judge_axes, outcomes_from, selected_targets
from evals.metrics import adherence, bootstrap
from evals.schemas import Concept, QuadrantSelection
from evals.schemas.result import FailureCase, SuiteResult
from evals.store import gather_limited

NAME = "composition"
LEVELS = {"two_map": 2, "three_map": 3}


async def run(rc: RunContext) -> SuiteResult:
    outcomes: dict[tuple[str, str], list[adherence.ConstraintOutcome]] = {}
    lookup: dict[str, tuple] = {}

    for level, map_count in LEVELS.items():
        for arm in ("navigator", "naive"):
            collected = []
            for context in rc.contexts:
                available = rc.maps[context.id]
                if len(available) < map_count:
                    continue
                generator = config.rng(NAME, level, context.id)
                chosen = generator.sample(available, map_count)
                selections = [
                    generator.choice(QuadrantSelection.all_quadrants(m.map_id))
                    for m in chosen
                ]

                generations = await gather_limited(
                    [
                        _generate(rc, context, chosen, selections, arm, level, rep)
                        for rep in range(rc.profile.composition_reps)
                    ]
                )
                targets = selected_targets(chosen, selections)
                for generation in generations:
                    rc.record_generation(generation)
                    judgments = await judge_axes(
                        rc, context, generation.concepts, targets
                    )
                    for concept in generation.concepts:
                        lookup[concept.concept_id] = (context, chosen, selections, concept)
                    collected.extend(
                        outcomes_from(context.id, judgments, selections)
                    )
            outcomes[(level, arm)] = collected
            for outcome in collected:
                rc.store.append(
                    "results",
                    {
                        "suite": NAME,
                        "level": level,
                        "arm": arm,
                        **outcome.__dict__,
                        "adhered": outcome.adhered,
                    },
                )

    metrics: dict[str, object] = {}
    for (level, arm), items in outcomes.items():
        summary = adherence.summarize(items)
        ci = bootstrap.bootstrap_ci(
            adherence.joint_groups_by_context(items),
            bootstrap.rate,
            seed_parts=(NAME, level, arm),
        )
        summary["full_adherence_ci"] = [ci["low"], ci["high"]]
        summary["constraints"] = LEVELS[level] * 2
        metrics[f"{level}_{arm}"] = summary

    # One-map numbers come from the steering suite so the curve starts from measured data
    # rather than a second, differently-sampled one-map experiment.
    steering = rc.artifacts.get("steering_outcomes") or {}
    curve = []
    if steering.get("navigator"):
        one_map = adherence.summarize(steering["navigator"])
        curve.append(
            {
                "composition": "1 map",
                "constraints": 2,
                "full_adherence": one_map.get("joint_adherence"),
                "mean_constraint_adherence": one_map.get("mean_constraint_adherence"),
                "target": 0.80,
            }
        )
    for level, target in (("two_map", 0.70), ("three_map", 0.60)):
        summary = metrics.get(f"{level}_navigator", {})
        curve.append(
            {
                "composition": f"{LEVELS[level]} maps",
                "constraints": LEVELS[level] * 2,
                "full_adherence": summary.get("joint_adherence"),
                "mean_constraint_adherence": summary.get("mean_constraint_adherence"),
                "target": target,
            }
        )
    metrics["degradation_curve"] = curve
    metrics["collapses_under_composition"] = _collapses(curve)

    return SuiteResult(suite=NAME, metrics=metrics, failures=_failures(outcomes, lookup))


async def _generate(rc, context, chosen, selections, arm, level, rep):
    if arm == "naive":
        return await naive_steering.generate(
            context,
            chosen,
            selections,
            rc.profile.concepts_per_generation,
            run_id=rc.run_id,
            suite=NAME,
            condition=level,
            rep=rep,
        )
    return await rc.adapter.generate_concepts(
        context,
        chosen,
        selections,
        rc.profile.concepts_per_generation,
        suite=NAME,
        arm=arm,
        condition=level,
        rep=rep,
    )


def _collapses(curve: list[dict]) -> bool | None:
    """True when adherence falls by more than half between the first and last level."""
    values = [point["full_adherence"] for point in curve if point["full_adherence"] is not None]
    if len(values) < 2 or not values[0]:
        return None
    return values[-1] < values[0] / 2


def _failures(outcomes, lookup) -> list[FailureCase]:
    failures = []
    for level in ("three_map", "two_map"):
        items = outcomes.get((level, "navigator"), [])
        partial = adherence.partial_adherence_rates(items)
        by_concept = adherence.by_concept(items)
        # A concept that satisfies some constraints and ignores others is the interesting
        # failure; one that misses everything usually means the whole generation went wrong.
        ranked = sorted(
            (cid for cid, rate in partial.items() if 0 < rate < 1),
            key=lambda cid: partial[cid],
        )
        for concept_id in ranked[:3]:
            context, chosen, selections, concept = lookup[concept_id]
            maps_by_id = {m.map_id: m for m in chosen}
            missed, met = [], []
            for outcome in by_concept[concept_id]:
                smap = maps_by_id[outcome.map_id]
                axis = smap.axis(outcome.axis)
                side = next(s for s in selections if s.map_id == outcome.map_id).side(
                    outcome.axis
                )
                (met if outcome.adhered else missed).append(
                    f"{axis.pole(side)} ({outcome.normalized}/5)"
                )
            failures.append(
                FailureCase(
                    kind=f"composition_{level}",
                    context_id=context.id,
                    product=context.product,
                    target_audience=context.target_audience,
                    map_summary=", ".join(m.title for m in chosen),
                    selection=f"met: {'; '.join(met)} | missed: {'; '.join(missed)}",
                    concept=concept.text,
                    scores=f"{partial[concept_id]:.0%} of constraints satisfied",
                    judge_reason=next(
                        (o.reason for o in by_concept[concept_id] if not o.adhered), ""
                    ),
                )
            )
    return failures
