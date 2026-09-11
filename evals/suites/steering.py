"""Evals 2 and 3 - single-map quadrant adherence, against the naive-prompt baseline.

Also runs the grounded-conditioning arm: production drops the map rationale when it builds
constraints, so this measures what feeding it back in would buy.
"""

from __future__ import annotations

from dataclasses import dataclass

from evals.baselines import naive_steering
from evals.harness import RunContext, judge_axes, outcomes_from, sample_quadrants
from evals.metrics import adherence, bootstrap
from evals.schemas import Concept, Context, Generation, QuadrantSelection, SemanticMap
from evals.schemas.result import FailureCase, SuiteResult
from evals.store import gather_limited

NAME = "steering"
ARMS = ("navigator", "naive", "navigator_grounded")


@dataclass
class Sample:
    context: Context
    smap: SemanticMap
    selection: QuadrantSelection
    rep: int

    @property
    def condition(self) -> str:
        return f"{self.smap.map_id}:{self.selection.x_side}{self.selection.y_side}"


def plan(rc: RunContext) -> list[Sample]:
    samples = []
    for context in rc.contexts:
        for smap in rc.maps[context.id]:
            for selection in sample_quadrants(
                context.id, smap, rc.profile.quadrants_per_map
            ):
                for rep in range(rc.profile.steering_reps):
                    samples.append(Sample(context, smap, selection, rep))
    return samples


async def _generate(rc: RunContext, sample: Sample, arm: str) -> Generation:
    if arm == "naive":
        return await naive_steering.generate(
            sample.context,
            [sample.smap],
            [sample.selection],
            rc.profile.concepts_per_generation,
            run_id=rc.run_id,
            suite=NAME,
            condition=sample.condition,
            rep=sample.rep,
        )
    return await rc.adapter.generate_concepts(
        sample.context,
        [sample.smap],
        [sample.selection],
        rc.profile.concepts_per_generation,
        suite=NAME,
        arm=arm,
        condition=sample.condition,
        rep=sample.rep,
        include_rationale=arm == "navigator_grounded",
    )


async def run(rc: RunContext) -> SuiteResult:
    samples = plan(rc)
    # The grounded arm is a diagnostic, so it runs at reduced repetitions and is compared
    # only against the matching subset of the main Navigator arm.
    arm_samples = {
        "navigator": samples,
        "naive": samples,
        "navigator_grounded": [s for s in samples if s.rep < rc.profile.grounded_arm_reps],
    }

    outcomes: dict[str, list[adherence.ConstraintOutcome]] = {}
    concept_lookup: dict[str, tuple[Sample, Concept]] = {}

    for arm in ARMS:
        chosen = arm_samples[arm]
        if not chosen:
            continue
        generations = await gather_limited([_generate(rc, s, arm) for s in chosen])

        judge_tasks = []
        for sample, generation in zip(chosen, generations):
            rc.record_generation(generation)
            for concept in generation.concepts:
                concept_lookup[concept.concept_id] = (sample, concept)
            judge_tasks.append(
                judge_axes(
                    rc,
                    sample.context,
                    generation.concepts,
                    [(sample.smap, "x"), (sample.smap, "y")],
                )
            )
        judged = await gather_limited(judge_tasks)

        arm_outcomes = []
        for sample, judgments in zip(chosen, judged):
            arm_outcomes.extend(
                outcomes_from(sample.context.id, judgments, [sample.selection])
            )
        outcomes[arm] = arm_outcomes
        for outcome in arm_outcomes:
            rc.store.append(
                "results",
                {"suite": NAME, "arm": arm, **outcome.__dict__, "adhered": outcome.adhered},
            )

    rc.artifacts["steering_outcomes"] = outcomes
    rc.artifacts["steering_concepts"] = concept_lookup

    metrics = {arm: adherence.summarize(items) for arm, items in outcomes.items()}
    for arm, items in outcomes.items():
        ci = bootstrap.bootstrap_ci(
            adherence.joint_groups_by_context(items),
            bootstrap.rate,
            seed_parts=(NAME, arm, "joint"),
        )
        metrics[arm]["joint_adherence_ci"] = [ci["low"], ci["high"]]

    if "navigator" in outcomes and "naive" in outcomes:
        difference = bootstrap.paired_difference_ci(
            adherence.joint_groups_by_context(outcomes["navigator"]),
            adherence.joint_groups_by_context(outcomes["naive"]),
            bootstrap.rate,
            seed_parts=(NAME, "nav_vs_naive"),
        )
        metrics["navigator_vs_naive"] = {
            "joint_adherence_difference": difference["point"],
            "difference_ci": [difference["low"], difference["high"]],
            "difference_pp": (difference["point"] or 0) * 100,
            "navigator_materially_better": (difference["point"] or 0) >= 0.10,
        }

    if "navigator_grounded" in outcomes:
        matched = [
            o
            for o in outcomes.get("navigator", [])
            if concept_lookup[o.concept_id][0].rep < rc.profile.grounded_arm_reps
        ]
        difference = bootstrap.paired_difference_ci(
            adherence.joint_groups_by_context(outcomes["navigator_grounded"]),
            adherence.joint_groups_by_context(matched),
            bootstrap.rate,
            seed_parts=(NAME, "grounded"),
        )
        metrics["grounded_conditioning"] = {
            "note": (
                "Production builds constraints from axis names and pole labels only; this "
                "arm adds the map rationale the app currently drops."
            ),
            "matched_navigator_joint_adherence": adherence.summarize(matched).get(
                "joint_adherence"
            ),
            "grounded_joint_adherence": metrics["navigator_grounded"].get("joint_adherence"),
            "difference": difference["point"],
            "difference_ci": [difference["low"], difference["high"]],
        }

    metrics["targets"] = {
        "joint_adherence_target": 0.80,
        "per_axis_adherence_target": 0.90,
        "navigator_meets_joint": (
            metrics.get("navigator", {}).get("joint_adherence") or 0
        )
        >= 0.80,
        "navigator_meets_per_axis": (
            metrics.get("navigator", {}).get("per_axis_adherence") or 0
        )
        >= 0.90,
    }

    return SuiteResult(
        suite=NAME,
        metrics=metrics,
        failures=_failures(rc, outcomes, concept_lookup),
    )


def _failures(
    rc: RunContext,
    outcomes: dict[str, list[adherence.ConstraintOutcome]],
    lookup: dict[str, tuple[Sample, Concept]],
) -> list[FailureCase]:
    failures = []
    for outcome in sorted(outcomes.get("navigator", []), key=lambda o: o.normalized)[:5]:
        if outcome.adhered:
            continue
        sample, concept = lookup[outcome.concept_id]
        smap = sample.smap
        axis = smap.axis(outcome.axis)
        side = sample.selection.side(outcome.axis)
        failures.append(
            FailureCase(
                kind="steering",
                context_id=outcome.context_id,
                product=sample.context.product,
                target_audience=sample.context.target_audience,
                map_summary=f"{smap.title} | {axis.name}",
                selection=(
                    f"wanted {axis.pole(side)} on {axis.name}, "
                    f"{smap.axis('y' if outcome.axis == 'x' else 'x').pole(sample.selection.side('y' if outcome.axis == 'x' else 'x'))} "
                    f"on the other axis"
                ),
                concept=concept.text,
                scores=f"raw={outcome.raw_score}, toward selected pole={outcome.normalized}/5",
                judge_reason=outcome.reason,
            )
        )
    return failures
