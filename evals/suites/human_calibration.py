"""Section 14 - blind human scoring of a stratified sample, then agreement with the judge.

Two phases. Export writes a CSV carrying the concept, the axis definition and nothing else:
no condition, no arm, no target quadrant, no automated score. Import reads the filled-in
scores back and computes agreement.

The automated score for each exported row lives in calibration_key.json, which the person
doing the scoring must not open until every row is filled in.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from evals import config
from evals.harness import RunContext
from evals.metrics import agreement
from evals.schemas.result import SuiteResult

NAME = "human_calibration"

EXPORT_FILE = "calibration_export.csv"
KEY_FILE = "calibration_key.json"
SCORES_FILE = "calibration_scores.csv"

# Stratification weights from the PRD: steering, isolation, composition, baselines.
STRATA = {
    "steering": 10,
    "isolation": 10,
    "composition": 5,
    "baseline": 5,
}

COLUMNS = [
    "item_id",
    "product",
    "target_audience",
    "dimension",
    "score_1_means",
    "score_5_means",
    "dimension_definition",
    "concept",
    "your_score_1_to_5",
]


def _strata_for(record: dict) -> str:
    if record.get("arm") in ("naive", "flat"):
        return "baseline"
    suite = record.get("suite", "")
    return suite if suite in STRATA else "baseline"


async def run(rc: RunContext) -> SuiteResult:
    generations = rc.store.read_jsonl("generations")
    judgments = [j for j in rc.store.read_jsonl("judgments") if j.get("grounded")]
    maps = {(m["context_id"], m["map_id"]): m for m in rc.store.read_jsonl("maps")}

    if not judgments:
        return SuiteResult(suite=NAME, metrics={"skipped": "no judgments in this run"})

    concepts, origin = {}, {}
    for generation in generations:
        for concept in generation.get("concepts", []):
            concepts[concept["concept_id"]] = concept
            origin[concept["concept_id"]] = generation

    candidates = []
    for judgment in judgments:
        generation = origin.get(judgment["concept_id"])
        concept = concepts.get(judgment["concept_id"])
        if not generation or not concept:
            continue
        key = (generation["context_id"], judgment["map_id"])
        if key not in maps:
            continue
        candidates.append((_strata_for(generation), judgment, generation, concept, maps[key]))

    sampler = config.rng(NAME, "sample")
    total = rc.profile.calibration_sample
    scale = total / sum(STRATA.values())

    selected = []
    for stratum, weight in STRATA.items():
        pool = [c for c in candidates if c[0] == stratum]
        take = max(1, round(weight * scale)) if pool else 0
        sampler.shuffle(pool)
        selected.extend(pool[:take])
    sampler.shuffle(selected)  # so ordering cannot hint at the stratum
    selected = selected[:total]

    rows, key = [], {}
    for index, (stratum, judgment, generation, concept, smap) in enumerate(selected):
        item_id = f"item_{index + 1:03d}"
        axis = smap["x_axis"] if judgment["axis"] == "x" else smap["y_axis"]
        context = rc.context(generation["context_id"])
        rows.append(
            {
                "item_id": item_id,
                "product": context.product,
                "target_audience": context.target_audience,
                "dimension": axis["name"],
                "score_1_means": axis["low_label"],
                "score_5_means": axis["high_label"],
                "dimension_definition": smap.get("rationale", ""),
                "concept": concept["text"],
                "your_score_1_to_5": "",
            }
        )
        key[item_id] = {
            "judgment_id": judgment["judgment_id"],
            "concept_id": judgment["concept_id"],
            "map_id": judgment["map_id"],
            "axis": judgment["axis"],
            "judge_score": judgment["score"],
            "stratum": stratum,
        }

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    rc.store.write_text(EXPORT_FILE, buffer.getvalue())
    rc.store.write_json(KEY_FILE, key)

    metrics: dict[str, object] = {
        "exported": len(rows),
        "export_path": str(rc.store.dir / EXPORT_FILE),
        "strata": {s: sum(1 for v in key.values() if v["stratum"] == s) for s in STRATA},
        "instructions": (
            f"Score every row from 1 to 5 using the same rubric as the judge: "
            f"`python -m evals.calibrate --run-id {rc.run_id}`. "
            f"That writes {SCORES_FILE}. Then re-run "
            f"`python -m evals.run --suite human_calibration --run-id {rc.run_id}`. "
            f"You can also fill {EXPORT_FILE} by hand. Do not open {KEY_FILE} until you "
            f"are finished."
        ),
    }

    scores_path = rc.store.dir / SCORES_FILE
    if scores_path.exists():
        metrics.update(_agreement(scores_path, key))
    else:
        metrics["status"] = "awaiting human scores"

    rc.store.append("results", {"suite": NAME, **metrics})
    return SuiteResult(suite=NAME, metrics=metrics)


def _agreement(scores_path: Path, key: dict) -> dict[str, object]:
    human, judge_scores, skipped = [], [], 0
    with scores_path.open() as handle:
        for row in csv.DictReader(handle):
            entry = key.get(row.get("item_id", ""))
            raw = (row.get("your_score_1_to_5") or "").strip()
            if entry is None or not raw:
                skipped += 1
                continue
            try:
                value = float(raw)
            except ValueError:
                skipped += 1
                continue
            human.append(value)
            judge_scores.append(float(entry["judge_score"]))

    summary = agreement.summarize(human, judge_scores)
    return {
        "status": "scored",
        "unscored_rows": skipped,
        "agreement": summary,
        "interpretation": (
            "Judge results are validated against human scoring at the stated targets."
            if summary.get("meets_targets")
            else "Agreement is below at least one predeclared target; automated numbers "
            "are reported but should not be presented as strongly validated."
        ),
    }
