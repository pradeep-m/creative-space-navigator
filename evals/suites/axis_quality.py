"""Eval 1 - are the generated controls meaningful before we test adherence to them?"""

from __future__ import annotations

from evals.adapters import judge
from evals.harness import RunContext
from evals.metrics import bootstrap
from evals.schemas import FailureCase
from evals.schemas.result import SuiteResult
from evals.store import gather_limited

NAME = "axis_quality"


async def run(rc: RunContext) -> SuiteResult:
    quality_tasks, redundancy_tasks = [], []
    for context in rc.contexts:
        maps = rc.maps[context.id]
        for smap in maps:
            quality_tasks.append(
                judge.score_map_quality(
                    product=context.product, audience=context.target_audience, smap=smap
                )
            )
        redundancy_tasks.append(
            judge.score_redundancy(
                product=context.product, audience=context.target_audience, maps=maps
            )
        )

    quality_results = await gather_limited(quality_tasks)
    redundancy_results = await gather_limited(redundancy_tasks)

    judgments, cursor = [], 0
    for context, redundancy in zip(rc.contexts, redundancy_results):
        maps = rc.maps[context.id]
        for index, smap in enumerate(maps):
            entry = redundancy[index] if index < len(redundancy) else None
            record = judge.build_axis_quality(
                context.id, smap, quality_results[cursor], entry
            )
            cursor += 1
            judgments.append(record)
            rc.store.append("results", {"suite": NAME, **record.to_dict()})

    groups = {
        context.id: [j for j in judgments if j.context_id == context.id]
        for context in rc.contexts
    }
    high_quality = bootstrap.bootstrap_ci(
        groups,
        lambda items: bootstrap.rate([j.high_quality for j in items]),
        seed_parts=(NAME, "high_quality"),
    )
    redundancy_scores = [j.non_redundancy for j in judgments if j.non_redundancy is not None]

    metrics = {
        "n_maps": len(judgments),
        "n_axes": 2 * len(judgments),
        "high_quality_rate": high_quality["point"],
        "high_quality_ci": [high_quality["low"], high_quality["high"]],
        "meets_target": (high_quality["point"] or 0) >= 0.80,
        "criterion_means": {
            name: sum(getattr(j, name) for j in judgments) / len(judgments)
            for name in ("relevance", "polarity", "actionability", "axis_distinctness")
        }
        if judgments
        else {},
        # Reported separately from the gating criteria, per the PRD.
        "mean_non_redundancy": (
            sum(redundancy_scores) / len(redundancy_scores) if redundancy_scores else None
        ),
        "redundant_map_rate": (
            sum(s <= 2 for s in redundancy_scores) / len(redundancy_scores)
            if redundancy_scores
            else None
        ),
    }

    failures = []
    for record in sorted(judgments, key=lambda j: min(getattr(j, n) for n in j.GATING))[:5]:
        if record.high_quality:
            continue
        context = rc.context(record.context_id)
        smap = rc.map_by_id(record.context_id, record.map_id)
        failures.append(
            FailureCase(
                kind="axis_quality",
                context_id=record.context_id,
                product=context.product,
                target_audience=context.target_audience,
                map_summary=_summary(smap),
                selection="n/a",
                concept="n/a",
                scores=", ".join(f"{n}={getattr(record, n)}" for n in record.GATING)
                + (
                    f", non_redundancy={record.non_redundancy}"
                    if record.non_redundancy is not None
                    else ""
                ),
                judge_reason=record.reason,
            )
        )

    return SuiteResult(suite=NAME, metrics=metrics, failures=failures)


def _summary(smap) -> str:
    return (
        f"{smap.title} | X {smap.x_axis.name}: {smap.x_axis.low_label} -> "
        f"{smap.x_axis.high_label} | Y {smap.y_axis.name}: {smap.y_axis.low_label} -> "
        f"{smap.y_axis.high_label}"
    )
