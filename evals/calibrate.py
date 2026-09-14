"""Local scoring UI for the human-calibration sample.

    python -m evals.calibrate --run-id <run_id>

Serves a one-item-at-a-time page with the same fields the judge sees, writes
`calibration_scores.csv` as you go, and never opens `calibration_key.json`.
"""

from __future__ import annotations

import argparse
import csv
import webbrowser
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from evals import config
from evals.suites.human_calibration import COLUMNS, EXPORT_FILE, SCORES_FILE

STATIC = Path(__file__).parent / "static" / "calibrate.html"

app = FastAPI(title="Human calibration")
app.state.run_id = None


def _run_dir(run_id: str | None = None) -> Path:
    chosen = run_id or app.state.run_id or latest_run()
    if not chosen:
        raise HTTPException(
            404,
            f"No run with {EXPORT_FILE} found under {config.OUTPUT_ROOT}. "
            "Generate one with: python -m evals.run --suite human_calibration",
        )
    path = config.OUTPUT_ROOT / chosen
    if not (path / EXPORT_FILE).exists():
        raise HTTPException(404, f"{path / EXPORT_FILE} is missing.")
    app.state.run_id = chosen
    return path


def available_runs() -> list[str]:
    root = config.OUTPUT_ROOT
    if not root.exists():
        return []
    runs = [p.name for p in root.iterdir() if p.is_dir() and (p / EXPORT_FILE).exists()]
    return sorted(runs, key=lambda name: (root / name).stat().st_mtime, reverse=True)


def latest_run() -> str | None:
    runs = available_runs()
    return runs[0] if runs else None


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [{key: row.get(key, "") or "" for key in COLUMNS} for row in csv.DictReader(handle)]


def load_items(run_dir: Path) -> list[dict[str, str]]:
    items = _read_csv(run_dir / EXPORT_FILE)
    if not items:
        raise HTTPException(404, f"{run_dir / EXPORT_FILE} has no rows.")
    by_id = {row["item_id"]: row["your_score_1_to_5"].strip() for row in _read_csv(run_dir / SCORES_FILE)}
    for item in items:
        item["your_score_1_to_5"] = by_id.get(item["item_id"], item["your_score_1_to_5"].strip())
    return items


def save_items(run_dir: Path, items: list[dict[str, str]]) -> None:
    with (run_dir / SCORES_FILE).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: item.get(key, "") for key in COLUMNS} for item in items)


def _state(run_dir: Path) -> dict:
    items = load_items(run_dir)
    scored = sum(1 for item in items if item["your_score_1_to_5"])
    return {
        "run_id": run_dir.name,
        "scores_path": str(run_dir / SCORES_FILE),
        "scored": scored,
        "total": len(items),
        "items": items,
    }


class ScoreBody(BaseModel):
    item_id: str
    score: int | None = Field(default=None, ge=1, le=5)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC)


@app.get("/api/state")
def api_state() -> dict:
    return _state(_run_dir())


@app.post("/api/score")
def api_score(body: ScoreBody) -> dict:
    run_dir = _run_dir()
    items = load_items(run_dir)
    for item in items:
        if item["item_id"] == body.item_id:
            item["your_score_1_to_5"] = "" if body.score is None else str(body.score)
            save_items(run_dir, items)
            return _state(run_dir)
    raise HTTPException(404, f"Unknown item_id {body.item_id!r}.")


def main() -> int:
    parser = argparse.ArgumentParser(prog="evals.calibrate")
    parser.add_argument("--run-id", default=None, help="Output directory that already has calibration_export.csv.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    run_id = args.run_id or latest_run()
    if not run_id:
        print(
            f"No run with {EXPORT_FILE} found under {config.OUTPUT_ROOT}.\n"
            "Generate one with: python -m evals.run --suite human_calibration"
        )
        return 2

    export = config.OUTPUT_ROOT / run_id / EXPORT_FILE
    if not export.exists():
        print(f"Missing {export}")
        return 2

    app.state.run_id = run_id
    url = f"http://{args.host}:{args.port}"
    print(f"Human calibration for {run_id}")
    print(f"  {url}")
    print(f"  scores → {config.OUTPUT_ROOT / run_id / SCORES_FILE}")
    print("  Do not open calibration_key.json until every item is scored.")
    if not args.no_browser:
        webbrowser.open(url)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
