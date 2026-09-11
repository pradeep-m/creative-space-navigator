"""Does the main screen's own placement mean anything?

Not in the PRD, but production's primary flow does not condition generation on a quadrant
at all: it generates one unconditioned corpus and then asks Claude to place each concept on
each map. For that flow the 2x2 is post-hoc labelling, and the property that matters is
whether those coordinates agree with an independent blind judge.

Uses a production-faithful 24-concept corpus spanning every map, not the coverage suite's
smaller single-map set.
"""

from __future__ import annotations

from evals import config
from evals.harness import RunContext, judge_axes
from evals.metrics import agreement, bootstrap
from evals.schemas.result import FailureCase, SuiteResult

NAME = "placement_fidelity"


async def run(rc: RunContext) -> SuiteResult:
    budget = rc.profile.coverage_budget
    rows = []
    failures = []

    for context in rc.contexts:
        # Production-faithful corpus: all maps, default 24. This is what the main screen
        # actually places, and it is deliberately not the coverage-eval's smaller set.
        cached = (rc.artifacts.get("production_corpus") or {}).get(context.id)
        corpus = cached or await rc.adapter.generate_corpus(
            context, rc.maps[context.id], suite=NAME
        )
        if cached is None:
            rc.record_generation(corpus)
            rc.artifacts.setdefault("production_corpus", {})[context.id] = corpus

        sampler = config.rng(NAME, "corpus_sample", context.id)
        concepts = sampler.sample(corpus.concepts, min(budget, len(corpus.concepts)))

        for smap in rc.maps[context.id][: rc.profile.placement_maps_per_context]:
            placements = await rc.adapter.place_on_map(context, concepts, smap)
            judgments = await judge_axes(rc, context, concepts, [(smap, "x"), (smap, "y")])
            judged: dict[str, dict[str, int]] = {}
            for judgment in judgments:
                judged.setdefault(judgment.concept_id, {})[judgment.axis] = judgment.score

            for concept in concepts:
                scores = judged.get(concept.concept_id, {})
                placement = placements.get(concept.concept_id)
                if placement is None or "x" not in scores or "y" not in scores:
                    continue
                row = {
                    "context_id": context.id,
                    "map_id": smap.map_id,
                    "concept_id": concept.concept_id,
                    "production_x": placement[0],
                    "production_y": placement[1],
                    "judge_x": scores["x"],
                    "judge_y": scores["y"],
                }
                rows.append(row)
                rc.store.append("results", {"suite": NAME, **row})

                production_quadrant = (placement[0] > 0, placement[1] > 0)
                judge_quadrant = (scores["x"] > 3, scores["y"] > 3)
                undecided = scores["x"] == 3 or scores["y"] == 3
                if not undecided and production_quadrant != judge_quadrant and len(failures) < 5:
                    failures.append(
                        FailureCase(
                            kind="placement_fidelity",
                            context_id=context.id,
                            product=context.product,
                            target_audience=context.target_audience,
                            map_summary=f"{smap.title} | X {smap.x_axis.name} | Y {smap.y_axis.name}",
                            selection="main-flow placement, no quadrant was selected",
                            concept=concept.text,
                            scores=(
                                f"production placed ({placement[0]:+.2f}, {placement[1]:+.2f}), "
                                f"blind judge scored x={scores['x']}, y={scores['y']}"
                            ),
                            judge_reason=(
                                "Production and the blind judge put this concept in "
                                "different quadrants."
                            ),
                        )
                    )

    if not rows:
        return SuiteResult(suite=NAME, metrics={"n": 0})

    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["context_id"], []).append(row)

    def quadrant_match(items: list[dict]) -> float | None:
        decided = [
            r for r in items if r["judge_x"] != 3 and r["judge_y"] != 3
            and r["production_x"] != 0 and r["production_y"] != 0
        ]
        if not decided:
            return None
        return sum(
            (r["production_x"] > 0, r["production_y"] > 0)
            == (r["judge_x"] > 3, r["judge_y"] > 3)
            for r in decided
        ) / len(decided)

    ci = bootstrap.bootstrap_ci(
        groups, quadrant_match, seed_parts=(NAME, "quadrant_match")
    )

    metrics = {
        "n_concept_placements": len(rows),
        "spearman_x": agreement.spearman(
            [r["production_x"] for r in rows], [float(r["judge_x"]) for r in rows]
        ),
        "spearman_y": agreement.spearman(
            [r["production_y"] for r in rows], [float(r["judge_y"]) for r in rows]
        ),
        "sign_agreement_x": agreement.sign_agreement(
            [r["production_x"] for r in rows], [float(r["judge_x"]) for r in rows]
        ),
        "sign_agreement_y": agreement.sign_agreement(
            [r["production_y"] for r in rows], [float(r["judge_y"]) for r in rows]
        ),
        "quadrant_agreement": ci["point"],
        "quadrant_agreement_ci": [ci["low"], ci["high"]],
        "judge_ambiguity_rate": sum(
            r["judge_x"] == 3 or r["judge_y"] == 3 for r in rows
        ) / len(rows),
        "note": (
            "Scales differ (production is continuous -1..+1, the judge is 1-5), so this "
            "reports rank correlation and side agreement rather than point differences."
        ),
    }
    return SuiteResult(suite=NAME, metrics=metrics, failures=failures)
