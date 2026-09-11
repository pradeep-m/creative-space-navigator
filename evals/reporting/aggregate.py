"""Turn suite results into summary.json, summary.csv and the submission table."""

from __future__ import annotations

import csv
import io

from evals.schemas.result import SuiteResult


def _get(results: dict[str, SuiteResult], suite: str, *path, default=None):
    node: object = results.get(suite).metrics if results.get(suite) else None
    for key in path:
        if not isinstance(node, dict):
            return default
        node = node.get(key)
    return default if node is None else node


def build_summary(results: dict[str, SuiteResult], metadata: dict) -> dict:
    summary: dict[str, object] = {"run": metadata}

    summary["axis_quality"] = {
        "high_quality_rate": _get(results, "axis_quality", "high_quality_rate"),
        "high_quality_ci": _get(results, "axis_quality", "high_quality_ci"),
        "mean_non_redundancy": _get(results, "axis_quality", "mean_non_redundancy"),
        "meets_target": _get(results, "axis_quality", "meets_target"),
    }
    summary["steering"] = {
        "x_adherence": _get(results, "steering", "navigator", "x_adherence"),
        "y_adherence": _get(results, "steering", "navigator", "y_adherence"),
        "per_axis_adherence": _get(results, "steering", "navigator", "per_axis_adherence"),
        "joint_adherence": _get(results, "steering", "navigator", "joint_adherence"),
        "joint_adherence_ci": _get(results, "steering", "navigator", "joint_adherence_ci"),
        "ambiguous_rate": _get(results, "steering", "navigator", "ambiguous_rate"),
    }
    summary["naive_baseline"] = {
        "joint_adherence": _get(results, "steering", "naive", "joint_adherence"),
        "joint_adherence_ci": _get(results, "steering", "naive", "joint_adherence_ci"),
        "difference": _get(results, "steering", "navigator_vs_naive", "joint_adherence_difference"),
        "difference_ci": _get(results, "steering", "navigator_vs_naive", "difference_ci"),
    }
    summary["grounded_conditioning"] = _get(results, "steering", "grounded_conditioning", default={})
    summary["isolation"] = {
        "target_movement": _get(results, "isolation", "target_movement"),
        "non_target_movement": _get(results, "isolation", "non_target_movement"),
        "pct_meeting_both": _get(results, "isolation", "pct_meeting_both"),
        "median_isolation_ratio": _get(results, "isolation", "median_isolation_ratio"),
    }
    summary["composition"] = {
        "one_map": _get(results, "steering", "navigator", "joint_adherence"),
        "two_maps": _get(results, "composition", "two_map_navigator", "joint_adherence"),
        "three_maps": _get(results, "composition", "three_map_navigator", "joint_adherence"),
        "two_maps_naive": _get(results, "composition", "two_map_naive", "joint_adherence"),
        "three_maps_naive": _get(results, "composition", "three_map_naive", "joint_adherence"),
        "degradation_curve": _get(results, "composition", "degradation_curve", default=[]),
    }
    summary["coverage"] = {
        "flat_coverage": _get(results, "coverage", "flat", "mean_per_context_coverage"),
        "structured_corpus_coverage": _get(
            results, "coverage", "structured_corpus", "mean_per_context_coverage"
        ),
        "structured_quadrant_coverage": _get(
            results, "coverage", "structured_quadrant", "mean_per_context_coverage"
        ),
        "flat_balance": _get(results, "coverage", "flat", "mean_balanced_coverage"),
        "structured_corpus_balance": _get(
            results, "coverage", "structured_corpus", "mean_balanced_coverage"
        ),
    }
    summary["placement_fidelity"] = _get(results, "placement_fidelity", default={})
    summary["judge_ablation"] = _get(results, "judge_ablation", default={})
    summary["human_calibration"] = _get(results, "human_calibration", "agreement", default={})
    summary["interpretation"] = interpret(summary)
    return summary


def interpret(summary: dict) -> dict[str, object]:
    """Answer sections 23 and 24 from measured values, without collapsing to a verdict."""
    steering = summary["steering"].get("joint_adherence")
    naive = summary["naive_baseline"].get("joint_adherence")
    difference = summary["naive_baseline"].get("difference")
    isolation = summary["isolation"]
    axis_quality = summary["axis_quality"].get("high_quality_rate")

    answers = {
        "A_controls_meaningful": _verdict(
            axis_quality,
            0.80,
            "Generated maps meet the predeclared quality bar.",
            "Generated maps fall short of the predeclared quality bar.",
        ),
        "B_controls_steer": _verdict(
            steering,
            0.80,
            "Selecting a quadrant reliably moves generation into it.",
            "Quadrant selection does not reliably steer generation.",
        ),
        "C_genuine_dimensions": None,
        "D_beats_ordinary_prompting": None,
        "E_composition_works": None,
    }

    target, non_target = isolation.get("target_movement"), isolation.get("non_target_movement")
    if target is not None and non_target is not None:
        isolated = target >= 2.0 and non_target <= 0.75
        answers["C_genuine_dimensions"] = (
            "Single-axis interventions move the target axis while largely preserving the "
            "other: the 2x2 behaves as a control surface, not a label."
            if isolated
            else "Single-axis interventions do not cleanly separate the two axes, so the "
            "2x2 should not be described as a reliable control surface."
        )

    if difference is not None:
        if difference >= 0.10:
            answers["D_beats_ordinary_prompting"] = (
                "The production conditioning system materially improves steering over "
                "plain-language prompting."
            )
        elif steering is not None and steering >= 0.80:
            answers["D_beats_ordinary_prompting"] = (
                "The semantic controls work, but Claude follows equivalent plain-language "
                "instructions about as well. Any product advantage lies in representation, "
                "discovery and interaction rather than a superior control mechanism."
            )
        else:
            answers["D_beats_ordinary_prompting"] = (
                "Neither the Navigator nor plain prompting reaches the adherence bar."
            )

    curve = summary["composition"].get("degradation_curve") or []
    values = [p["full_adherence"] for p in curve if p.get("full_adherence") is not None]
    if len(values) >= 2 and values[0]:
        answers["E_composition_works"] = (
            "Multi-map composition degrades sharply; single-map steering works but explicit "
            "multidimensional composition is not sufficiently reliable."
            if values[-1] < values[0] / 2
            else "Constraints largely survive composition across multiple maps."
        )

    if naive is not None:
        answers["_naive_comparison_reported"] = True
    return answers


def _verdict(value, threshold, yes, no):
    if value is None:
        return None
    return yes if value >= threshold else no


def build_csv(summary: dict) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["section", "metric", "value"])
    for section, payload in summary.items():
        if section in ("run", "interpretation") or not isinstance(payload, dict):
            continue
        for metric, value in payload.items():
            if isinstance(value, (list, dict)):
                continue
            writer.writerow([section, metric, value])
    return buffer.getvalue()


def submission_rows(summary: dict) -> list[list[str]]:
    """The compact table for the write-up. Populated only from measured values."""
    isolation = summary["isolation"]
    movement = "—"
    if isolation.get("target_movement") is not None:
        movement = (
            f"{isolation['target_movement']:.2f} / {isolation['non_target_movement']:.2f}"
        )
    calibration = summary.get("human_calibration") or {}

    return [
        [
            "Axis quality",
            "Maps passing semantic-quality criteria",
            pct(summary["axis_quality"].get("high_quality_rate")),
            "N/A",
        ],
        [
            "Steering",
            "Joint quadrant adherence",
            pct(summary["steering"].get("joint_adherence")),
            pct(summary["naive_baseline"].get("joint_adherence")),
        ],
        ["Isolation", "Target / non-target movement (1-5 scale)", movement, "N/A"],
        [
            "2-map composition",
            "All 4 constraints satisfied",
            pct(summary["composition"].get("two_maps")),
            pct(summary["composition"].get("two_maps_naive")),
        ],
        [
            "3-map composition",
            "All 6 constraints satisfied",
            pct(summary["composition"].get("three_maps")),
            pct(summary["composition"].get("three_maps_naive")),
        ],
        [
            "Coverage",
            "Quadrants represented per context",
            pct(summary["coverage"].get("structured_corpus_coverage")),
            pct(summary["coverage"].get("flat_coverage")),
        ],
        [
            "Placement fidelity",
            "Main-flow quadrant matches blind judge",
            pct((summary.get("placement_fidelity") or {}).get("quadrant_agreement")),
            "N/A",
        ],
        [
            "Judge validation",
            "Human/judge within-one agreement",
            pct(calibration.get("within_one_agreement")),
            "N/A",
        ],
    ]


def pct(value) -> str:
    return "—" if value is None else f"{value * 100:.0f}%"


def num(value, digits: int = 2) -> str:
    return "—" if value is None else f"{value:.{digits}f}"
