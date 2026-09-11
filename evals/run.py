"""CLI entry point.

    python -m evals.run --suite all --profile full
    python -m evals.run --suite steering
    python -m evals.run --suite all --profile smoke
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone

from evals import config
from evals.adapters.navigator import NavigatorAdapter
from evals.harness import RunContext, build_maps
from evals.reporting import aggregate, markdown
from evals.schemas import load_contexts
from evals.schemas.result import SuiteResult
from evals.store import RunStore
from evals.suites import (
    axis_quality,
    composition,
    coverage,
    human_calibration,
    isolation,
    judge_ablation,
    placement_fidelity,
    steering,
)

# Order is a dependency order, not a preference: steering leaves outcomes the composition
# curve and the ablation read, and coverage caches the corpus placement_fidelity reuses.
SUITES = {
    "axis_quality": axis_quality,
    "steering": steering,
    "isolation": isolation,
    "composition": composition,
    "coverage": coverage,
    "placement_fidelity": placement_fidelity,
    "judge_ablation": judge_ablation,
    "human_calibration": human_calibration,
}

NEEDS_MAPS = set(SUITES) - {"human_calibration"}


def estimate(profile: config.Profile, suites: list[str]) -> dict[str, int]:
    """Rough upper bound on API calls, before cache hits."""
    n = profile.concepts_per_generation
    contexts = profile.contexts
    maps = profile.maps_per_context
    generations = judgments = contexts  # one map-generation call per context

    if "axis_quality" in suites:
        judgments += contexts * maps + contexts

    if "steering" in suites:
        samples = contexts * maps * profile.quadrants_per_map * profile.steering_reps
        grounded = contexts * maps * profile.quadrants_per_map * profile.grounded_arm_reps
        generations += samples * 2 + grounded
        judgments += (samples * 2 + grounded) * n * 2

    if "isolation" in suites:
        conditions = contexts * 3 * profile.isolation_reps
        generations += conditions
        judgments += conditions * n * 2

    if "composition" in suites:
        for map_count in (2, 3):
            calls = contexts * profile.composition_reps * 2
            generations += calls
            judgments += calls * n * map_count * 2

    if "coverage" in suites:
        generations += contexts * (1 + 1 + 4)
        judgments += contexts * profile.coverage_budget * 3 * 2

    if "placement_fidelity" in suites:
        generations += contexts * profile.placement_maps_per_context
        judgments += contexts * profile.coverage_budget * 2

    if "judge_ablation" in suites:
        judgments += min(profile.ablation_concepts, contexts * maps) * 2

    return {"generation_calls": generations, "judge_calls": judgments}


async def execute(args: argparse.Namespace) -> int:
    suites = list(SUITES) if "all" in args.suite else args.suite
    unknown = [s for s in suites if s not in SUITES]
    if unknown:
        print(f"Unknown suite(s): {', '.join(unknown)}", file=sys.stderr)
        return 2
    suites.sort(key=lambda s: list(SUITES).index(s))

    profile = config.PROFILES[args.profile]
    contexts = load_contexts(config.FIXTURES_PATH, profile.contexts)

    budget = estimate(profile, suites)
    total = budget["generation_calls"] + budget["judge_calls"]
    print(
        f"Profile '{profile.name}': {len(contexts)} contexts, suites "
        f"{', '.join(suites)}\n"
        f"Upper bound before cache hits: {budget['generation_calls']} generation calls + "
        f"{budget['judge_calls']} judge calls = {total} API calls."
    )
    if args.estimate_only:
        return 0
    if not args.yes and total > 200:
        if input("Proceed? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Aborted.")
            return 1

    run_id = args.run_id or (
        f"{profile.name}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    store = RunStore(run_id)
    metadata = config.run_metadata(run_id, profile, suites)
    store.write_json("config.json", {**metadata, "estimated_calls": budget})

    rc = RunContext(
        run_id=run_id,
        profile=profile,
        store=store,
        adapter=NavigatorAdapter(run_id),
        contexts=contexts,
    )

    if set(suites) & NEEDS_MAPS:
        print("Generating semantic maps...")
        rc.maps = await build_maps(rc)

    results: dict[str, SuiteResult] = {}
    for name in suites:
        print(f"Running {name}...")
        try:
            results[name] = await SUITES[name].run(rc)
        except Exception as exc:  # one bad suite should not discard the rest of the run
            print(f"  {name} failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            results[name] = SuiteResult(suite=name, metrics={"error": f"{type(exc).__name__}: {exc}"})

    summary = aggregate.build_summary(results, metadata)
    store.write_json("summary.json", summary)
    store.write_text("summary.csv", aggregate.build_csv(summary))
    store.write_text("report.md", markdown.render(summary, results))
    store.write_json("results_by_suite.json", {k: v.to_dict() for k, v in results.items()})
    store.close()

    print(f"\nWrote {store.dir}")
    for artifact in sorted(p.name for p in store.dir.iterdir()):
        print(f"  {artifact}")
    if profile.name == "smoke":
        print("\nSmoke profile: development only, not benchmark results.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="evals.run")
    parser.add_argument(
        "--suite", action="append", default=None, help="Suite name, or 'all'. Repeatable."
    )
    parser.add_argument("--profile", choices=sorted(config.PROFILES), default="full")
    parser.add_argument("--run-id", default=None, help="Reuse an existing output directory.")
    parser.add_argument("--yes", action="store_true", help="Skip the cost confirmation.")
    parser.add_argument("--estimate-only", action="store_true", help="Print the call budget and exit.")
    args = parser.parse_args()
    args.suite = args.suite or ["all"]
    return asyncio.run(execute(args))


if __name__ == "__main__":
    raise SystemExit(main())
