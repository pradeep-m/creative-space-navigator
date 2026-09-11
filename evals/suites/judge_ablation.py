"""How much of the judge's signal comes from the map rationale?

Re-scores steering concepts with the rationale withheld, leaving only axis name and pole
labels. A large gap means the two-word labels are underdetermined on their own, which bears
on H1: an axis whose meaning collapses without its paragraph is a weak control dimension.

No new generations - this re-judges concepts that already exist.
"""

from __future__ import annotations

from evals import config
from evals.harness import RunContext, judge_axes
from evals.metrics import adherence, agreement
from evals.metrics.adherence import ConstraintOutcome, normalize
from evals.schemas.result import SuiteResult
from evals.store import gather_limited

NAME = "judge_ablation"


async def run(rc: RunContext) -> SuiteResult:
    outcomes = (rc.artifacts.get("steering_outcomes") or {}).get("navigator")
    lookup = rc.artifacts.get("steering_concepts") or {}
    if not outcomes:
        return SuiteResult(
            suite=NAME,
            metrics={"skipped": "requires the steering suite to have run first"},
        )

    concept_ids = sorted({o.concept_id for o in outcomes})
    sampler = config.rng(NAME, "sample")
    sampled = sampler.sample(
        concept_ids, min(rc.profile.ablation_concepts, len(concept_ids))
    )

    tasks = []
    for concept_id in sampled:
        sample, concept = lookup[concept_id]
        tasks.append(
            judge_axes(
                rc,
                sample.context,
                [concept],
                [(sample.smap, "x"), (sample.smap, "y")],
                grounded=False,
            )
        )
    results = await gather_limited(tasks)

    blind: list[ConstraintOutcome] = []
    for concept_id, judgments in zip(sampled, results):
        sample, _ = lookup[concept_id]
        for judgment in judgments:
            blind.append(
                ConstraintOutcome(
                    context_id=sample.context.id,
                    concept_id=judgment.concept_id,
                    map_id=judgment.map_id,
                    axis=judgment.axis,
                    raw_score=judgment.score,
                    normalized=normalize(
                        judgment.score, sample.selection.side(judgment.axis)
                    ),
                    reason=judgment.reason,
                )
            )

    sampled_set = set(sampled)
    grounded = [o for o in outcomes if o.concept_id in sampled_set]

    keyed = {(o.concept_id, o.axis): o for o in grounded}
    paired = [(keyed[(o.concept_id, o.axis)], o) for o in blind if (o.concept_id, o.axis) in keyed]

    grounded_summary = adherence.summarize([g for g, _ in paired])
    blind_summary = adherence.summarize([b for _, b in paired])

    metrics = {
        "n_concepts": len(sampled),
        "n_paired_scores": len(paired),
        "grounded_joint_adherence": grounded_summary.get("joint_adherence"),
        "blind_joint_adherence": blind_summary.get("joint_adherence"),
        "adherence_difference": (
            (grounded_summary.get("joint_adherence") or 0)
            - (blind_summary.get("joint_adherence") or 0)
        ),
        "score_agreement": agreement.summarize(
            [float(g.raw_score) for g, _ in paired], [float(b.raw_score) for _, b in paired]
        ),
        "grounded_ambiguous_rate": grounded_summary.get("ambiguous_rate"),
        "blind_ambiguous_rate": blind_summary.get("ambiguous_rate"),
        "self_consistency": await _self_consistency(rc, lookup, sampled[:30]),
        "note": (
            "Grounded judging supplies the map rationale as the axis definition; blind "
            "judging supplies only the axis name and pole labels. All headline metrics "
            "elsewhere in this benchmark use grounded judging."
        ),
    }
    rc.store.append("results", {"suite": NAME, **{k: v for k, v in metrics.items()}})
    return SuiteResult(suite=NAME, metrics=metrics)


async def _self_consistency(rc: RunContext, lookup: dict, concept_ids: list[str]) -> dict:
    """How stable is the judge when asked the identical question twice?

    The PRD assumes JUDGE_TEMPERATURE=0, but these models reject the temperature parameter,
    so determinism cannot be requested. Measuring the spread is the honest substitute: it
    puts a floor under how much of any difference elsewhere is just judge noise.
    """
    if not concept_ids:
        return {}

    # Primary judgments only: the second pass is written to the same log and is excluded
    # by its repeat marker, otherwise it would be compared against itself.
    first = {
        (j["concept_id"], j["axis"]): j["score"]
        for j in rc.store.read_jsonl("judgments")
        if j.get("grounded") and not j.get("repeat")
    }

    tasks = []
    for concept_id in concept_ids:
        sample, concept = lookup[concept_id]
        tasks.append(
            judge_axes(
                rc,
                sample.context,
                [concept],
                [(sample.smap, "x"), (sample.smap, "y")],
                repeat=1,
            )
        )
    second_pass = await gather_limited(tasks)
    pairs = [
        (first[(j.concept_id, j.axis)], j.score)
        for judgments in second_pass
        for j in judgments
        if (j.concept_id, j.axis) in first
    ]
    if not pairs:
        return {}

    summary = agreement.summarize([float(a) for a, _ in pairs], [float(b) for _, b in pairs])
    return {
        **summary,
        "note": (
            "Two independent passes of the same judge on the same question. Differences "
            "smaller than this are within judge noise."
        ),
    }
