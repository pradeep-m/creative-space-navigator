"""report.md: aggregates, the degradation curve, interpretation, and real failures."""

from __future__ import annotations

from evals.reporting.aggregate import num, pct, submission_rows
from evals.schemas.result import SuiteResult


def _table(headers: list[str], rows: list[list[str]], align: list[str] | None = None) -> str:
    align = align or ["---"] * len(headers)
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(align) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def _model(name: str, temperature) -> str:
    if isinstance(temperature, (int, float)):
        return f"{name}, temperature {temperature}"
    return f"{name}, temperature unavailable ({temperature})"


def _ci(bounds) -> str:
    if not bounds or bounds[0] is None or bounds[1] is None:
        return ""
    return f" (95% CI {bounds[0] * 100:.0f}–{bounds[1] * 100:.0f}%)"


def render(summary: dict, results: dict[str, SuiteResult]) -> str:
    run = summary["run"]
    parts: list[str] = []

    parts.append(f"# Semantic Control Eval — run `{run['run_id']}`\n")
    parts.append(
        _table(
            ["Setting", "Value"],
            [
                ["Profile", str(run["profile"]["name"])],
                ["Generator", _model(run["generator_model"], run["generator_temperature"])],
                ["Judge", _model(run["judge_model"], run["judge_temperature"])],
                ["Judge prompt version", run["judge_prompt_version"]],
                ["Production prompt hash", run["production_prompt_hash"]],
                ["Git commit", run["git_commit"][:12]],
                ["Random seed", str(run["random_seed"])],
                ["Contexts", str(run["profile"]["contexts"])],
            ],
        )
    )

    if run["profile"]["name"] == "smoke":
        parts.append(
            "\n> **Smoke run.** Sample sizes are development-only and these numbers must "
            "not be used as benchmark results.\n"
        )

    parts.append("\n## Submission table\n")
    parts.append(
        _table(
            ["Property", "Measurement", "Navigator", "Baseline"],
            submission_rows(summary),
            ["---", "---", "---:", "---:"],
        )
    )

    parts.append("\n## What the evidence supports\n")
    for key, answer in summary["interpretation"].items():
        if key.startswith("_") or answer is None:
            continue
        label = key.split("_", 1)[1].replace("_", " ")
        parts.append(f"- **{label.capitalize()}** — {answer}")

    parts.append("\n## Results\n")
    parts.append("### Axis quality\n")
    axis = summary["axis_quality"]
    parts.append(
        f"{pct(axis.get('high_quality_rate'))} of maps met all four gating criteria"
        f"{_ci(axis.get('high_quality_ci'))} against a predeclared target of 80%. "
        f"Mean non-redundancy {num(axis.get('mean_non_redundancy'))}/5, reported separately."
    )

    parts.append("\n### Single-map steering\n")
    steering, naive = summary["steering"], summary["naive_baseline"]
    parts.append(
        _table(
            ["Metric", "Navigator", "Naive prompt"],
            [
                [
                    "Joint quadrant adherence",
                    pct(steering.get("joint_adherence")) + _ci(steering.get("joint_adherence_ci")),
                    pct(naive.get("joint_adherence")) + _ci(naive.get("joint_adherence_ci")),
                ],
                ["Per-axis adherence", pct(steering.get("per_axis_adherence")), "—"],
                ["X-axis adherence", pct(steering.get("x_adherence")), "—"],
                ["Y-axis adherence", pct(steering.get("y_adherence")), "—"],
                ["Ambiguous (judge scored 3)", pct(steering.get("ambiguous_rate")), "—"],
            ],
            ["---", "---:", "---:"],
        )
    )
    if naive.get("difference") is not None:
        parts.append(
            f"\nDifference: {naive['difference'] * 100:+.1f} percentage points"
            f"{_ci(naive.get('difference_ci'))}, resampling contexts rather than concepts."
        )

    grounded = summary.get("grounded_conditioning") or {}
    if grounded.get("difference") is not None:
        parts.append(
            f"\n**Grounded-conditioning diagnostic.** Production builds its constraints from "
            f"axis names and pole labels only, dropping the map rationale. Feeding the "
            f"rationale back in moved joint adherence from "
            f"{pct(grounded.get('matched_navigator_joint_adherence'))} to "
            f"{pct(grounded.get('grounded_joint_adherence'))} "
            f"({grounded['difference'] * 100:+.1f} pp{_ci(grounded.get('difference_ci'))})."
        )

    parts.append("\n### Axis isolation\n")
    isolation = summary["isolation"]
    parts.append(
        _table(
            ["Metric", "Measured", "Target"],
            [
                ["Target-axis movement", num(isolation.get("target_movement")), ">= 2.00"],
                ["Non-target movement", num(isolation.get("non_target_movement")), "<= 0.75"],
                ["Interventions meeting both", pct(isolation.get("pct_meeting_both")), ">= 75%"],
                [
                    "Median isolation ratio",
                    num(isolation.get("median_isolation_ratio")),
                    "descriptive",
                ],
            ],
            ["---", "---:", "---:"],
        )
    )

    parts.append("\n### Composition degradation\n")
    curve_rows = [
        [
            point["composition"],
            str(point["constraints"]),
            pct(point.get("full_adherence")),
            pct(point.get("mean_constraint_adherence")),
            pct(point.get("target")),
        ]
        for point in summary["composition"].get("degradation_curve", [])
    ]
    parts.append(
        _table(
            ["Composition", "Constraints", "Full adherence", "Mean constraint adherence", "Target"],
            curve_rows,
            ["---", "---:", "---:", "---:", "---:"],
        )
    )

    parts.append("\n### Coverage\n")
    coverage = summary["coverage"]
    parts.append(
        _table(
            ["Arm", "Quadrants represented", "Balance (normalised entropy)"],
            [
                ["Flat diversity prompt", pct(coverage.get("flat_coverage")), num(coverage.get("flat_balance"))],
                [
                    "Structured (production corpus)",
                    pct(coverage.get("structured_corpus_coverage")),
                    num(coverage.get("structured_corpus_balance")),
                ],
                [
                    "Structured (per-quadrant)",
                    pct(coverage.get("structured_quadrant_coverage")),
                    "—",
                ],
            ],
            ["---", "---:", "---:"],
        )
    )

    placement = summary.get("placement_fidelity") or {}
    if placement.get("quadrant_agreement") is not None:
        parts.append("\n### Main-flow placement fidelity\n")
        parts.append(
            f"The product's primary screen does not condition generation on a quadrant: it "
            f"generates one unconditioned corpus and places each concept afterwards. Those "
            f"placements agreed with an independent blind judge on "
            f"{pct(placement.get('quadrant_agreement'))} of concepts"
            f"{_ci(placement.get('quadrant_agreement_ci'))}, with rank correlation "
            f"{num(placement.get('spearman_x'))} on X and {num(placement.get('spearman_y'))} on Y."
        )

    ablation = summary.get("judge_ablation") or {}
    if ablation.get("blind_joint_adherence") is not None:
        agreement = ablation.get("score_agreement") or {}
        parts.append("\n### How much the axis definition carries\n")
        parts.append(
            f"Re-scoring the same concepts with the map rationale withheld moved joint "
            f"adherence from {pct(ablation.get('grounded_joint_adherence'))} to "
            f"{pct(ablation.get('blind_joint_adherence'))} "
            f"(mean absolute score difference {num(agreement.get('mean_absolute_error'))}). "
            f"A large gap means the pole labels are underdetermined without their rationale."
        )

    consistency = (summary.get("judge_ablation") or {}).get("self_consistency") or {}
    if consistency.get("n"):
        parts.append("\n### Judge stability\n")
        parts.append(
            f"These models reject the `temperature` parameter, so the PRD's judge "
            f"`temperature=0` could not be set and determinism cannot be requested. Asking "
            f"the judge the identical question twice instead gave mean absolute difference "
            f"{num(consistency.get('mean_absolute_error'))} across {consistency['n']} "
            f"re-draws, with {pct(consistency.get('exact_agreement'))} exact agreement. "
            f"Differences smaller than that are within judge noise."
        )

    calibration = summary.get("human_calibration") or {}
    parts.append("\n### Judge validation\n")
    if calibration.get("n"):
        parts.append(
            _table(
                ["Metric", "Measured", "Target"],
                [
                    ["Mean absolute error", num(calibration.get("mean_absolute_error")), "<= 0.75"],
                    ["Within-one agreement", pct(calibration.get("within_one_agreement")), ">= 85%"],
                    ["Exact agreement", pct(calibration.get("exact_agreement")), "—"],
                    ["Spearman rho", num(calibration.get("spearman_rho")), ">= 0.60"],
                ],
                ["---", "---:", "---:"],
            )
        )
        if not calibration.get("meets_targets"):
            parts.append(
                "\nAgreement is below at least one predeclared target. Automated numbers "
                "above remain available but should not be presented as strongly validated."
            )
    else:
        parts.append(
            "Not yet performed. `calibration_export.csv` holds the blind sample; automated "
            "results in this report are unvalidated against human scoring until it is filled in."
        )

    parts.append("\n## Failure analysis\n")
    failures = [f for result in results.values() for f in result.failures]
    if not failures:
        parts.append("No failures met the reporting criteria in this run.")
    for failure in failures[:12]:
        parts.append(f"\n**{failure.kind}** — `{failure.context_id}`\n")
        parts.append(f"- Product: {failure.product}")
        parts.append(f"- Audience: {failure.target_audience}")
        parts.append(f"- Map: {failure.map_summary}")
        parts.append(f"- Selection: {failure.selection}")
        parts.append(f"- Concept: {failure.concept}".replace("\n", " "))
        parts.append(f"- Scores: {failure.scores}")
        parts.append(f"- Judge: {failure.judge_reason}")

    parts.append(
        "\n---\n\nEvery figure above is populated from measured results. The benchmark is "
        "small: ten product domains resampled at the context level, so intervals are wide "
        "and no claim of universal statistical validity is intended."
    )
    return "\n".join(parts) + "\n"
