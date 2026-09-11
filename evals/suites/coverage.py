"""Eval 6 - does deliberate navigation cover the space better than asking for variety?

Three arms on an identical concept budget:
  flat               - "generate N diverse concepts", told nothing about the maps
  structured_corpus  - production corpus generator, one evaluation map, exact budget
  structured_quadrant- one drill-down call per quadrant

The corpus arm is the mechanism the product's coverage claim actually rests on; the
quadrant arm is the PRD's literal reading. Placement fidelity separately generates the
real 24-concept, three-map corpus the main screen places.
"""

from __future__ import annotations

from evals.baselines import flat_generation
from evals.harness import RunContext, judge_axes
from evals.metrics import bootstrap
from evals.metrics import coverage as coverage_metrics
from evals.schemas import Concept, QuadrantSelection
from evals.schemas.result import FailureCase, SuiteResult
from evals.store import gather_limited

NAME = "coverage"
ARMS = ("flat", "structured_corpus", "structured_quadrant")


async def run(rc: RunContext) -> SuiteResult:
    budget = rc.profile.coverage_budget
    per_quadrant = max(1, budget // 4)
    scored: dict[str, dict[str, list[tuple[int, int]]]] = {arm: {} for arm in ARMS}
    examples: dict[str, list] = {arm: [] for arm in ARMS}

    for context in rc.contexts:
        smap = rc.maps[context.id][0]  # first map is the evaluation coordinate system
        arms_concepts: dict[str, list[Concept]] = {}

        flat = await flat_generation.generate(context, budget, run_id=rc.run_id, suite=NAME)
        rc.record_generation(flat)
        arms_concepts["flat"] = flat.concepts[:budget]

        # Only the evaluation map, and exactly the concept budget: asking the production
        # corpus to span three maps and then scoring it on one would understate coverage.
        corpus = await rc.adapter.generate_corpus(
            context, [smap], suite=NAME, count=budget, limit=budget
        )
        rc.record_generation(corpus)
        arms_concepts["structured_corpus"] = corpus.concepts[:budget]
        rc.artifacts.setdefault("coverage_corpus", {})[context.id] = corpus

        quadrant_generations = await gather_limited(
            [
                rc.adapter.generate_concepts(
                    context,
                    [smap],
                    [selection],
                    per_quadrant,
                    suite=NAME,
                    arm="structured_quadrant",
                    condition=f"{selection.x_side}{selection.y_side}",
                    rep=0,
                )
                for selection in QuadrantSelection.all_quadrants(smap.map_id)
            ]
        )
        quadrant_concepts = []
        for generation in quadrant_generations:
            rc.record_generation(generation)
            quadrant_concepts.extend(generation.concepts)
        arms_concepts["structured_quadrant"] = quadrant_concepts[:budget]

        for arm, concepts in arms_concepts.items():
            judgments = await judge_axes(rc, context, concepts, [(smap, "x"), (smap, "y")])
            by_concept: dict[str, dict[str, int]] = {}
            for judgment in judgments:
                by_concept.setdefault(judgment.concept_id, {})[judgment.axis] = judgment.score
            pairs = [
                (scores["x"], scores["y"])
                for scores in by_concept.values()
                if "x" in scores and "y" in scores
            ]
            scored[arm][context.id] = pairs
            examples[arm].append((context, smap, concepts, by_concept))

    metrics: dict[str, object] = {}
    for arm in ARMS:
        pooled = [pair for pairs in scored[arm].values() for pair in pairs]
        summary = coverage_metrics.summarize(pooled)
        # Coverage is a per-context property: pooling every context first would make four
        # quadrants look covered even if no single context ever filled more than one.
        per_context = [
            coverage_metrics.summarize(pairs)["quadrant_coverage"]
            for pairs in scored[arm].values()
            if pairs
        ]
        entropies = [
            coverage_metrics.summarize(pairs)["balanced_coverage"]
            for pairs in scored[arm].values()
            if pairs
        ]
        summary["mean_per_context_coverage"] = bootstrap.mean(
            [v for v in per_context if v is not None]
        )
        summary["mean_balanced_coverage"] = bootstrap.mean(
            [v for v in entropies if v is not None]
        )
        metrics[arm] = summary

    for structured in ("structured_corpus", "structured_quadrant"):
        difference = bootstrap.paired_difference_ci(
            {cid: [pairs] for cid, pairs in scored[structured].items() if pairs},
            {cid: [pairs] for cid, pairs in scored["flat"].items() if pairs},
            lambda groups: bootstrap.mean(
                [
                    v
                    for v in (
                        coverage_metrics.summarize(g)["quadrant_coverage"] for g in groups
                    )
                    if v is not None
                ]
            ),
            seed_parts=(NAME, structured, "vs_flat"),
        )
        metrics[f"{structured}_vs_flat"] = {
            "coverage_difference": difference["point"],
            "difference_ci": [difference["low"], difference["high"]],
        }

    return SuiteResult(suite=NAME, metrics=metrics, failures=_failures(metrics, examples))


def _failures(metrics: dict, examples: dict) -> list[FailureCase]:
    """Report the arm that covered least, and the most ambiguous concept in it."""
    failures = []
    for arm in ARMS:
        summary = metrics.get(arm, {})
        if (summary.get("mean_per_context_coverage") or 1.0) >= 0.75:
            continue
        for context, smap, concepts, by_concept in examples[arm][:2]:
            ambiguous = [
                c
                for c in concepts
                if by_concept.get(c.concept_id, {}).get("x") == 3
                or by_concept.get(c.concept_id, {}).get("y") == 3
            ]
            if not ambiguous:
                continue
            concept = ambiguous[0]
            scores = by_concept[concept.concept_id]
            failures.append(
                FailureCase(
                    kind=f"coverage_{arm}",
                    context_id=context.id,
                    product=context.product,
                    target_audience=context.target_audience,
                    map_summary=f"{smap.title} | X {smap.x_axis.name} | Y {smap.y_axis.name}",
                    selection=f"arm covered {summary.get('mean_per_context_coverage'):.0%} of quadrants",
                    concept=concept.text,
                    scores=f"x={scores.get('x')}, y={scores.get('y')} (3 = unassignable)",
                    judge_reason="Concept could not be placed in a quadrant.",
                )
            )
    return failures
