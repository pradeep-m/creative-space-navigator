"""Creative Space Navigator - local FastAPI app."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import llm
import prompts

ROOT = Path(__file__).parent
STATIC = ROOT / "static"

app = FastAPI(title="Creative Space Navigator")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

# Single-user prototype: runs live in memory and vanish on restart.
RUNS: dict[str, dict[str, Any]] = {}


def get_run(run_id: str) -> dict[str, Any]:
    run = RUNS.get(run_id)
    if run is None:
        raise HTTPException(404, "Unknown run_id. Start a new exploration.")
    return run


def clamp(value: Any) -> float:
    try:
        return max(-1.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


async def guard(coro):
    """Turn LLM failures into clean HTTP errors instead of stack traces in the UI."""
    try:
        return await coro
    except llm.MockMiss as exc:
        raise HTTPException(409, str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"{type(exc).__name__}: {exc}") from exc


class BriefIn(BaseModel):
    product: str
    audience: str


class RunIn(BaseModel):
    run_id: str


class ThemeIn(BaseModel):
    run_id: str
    theme_id: str


class Selection(BaseModel):
    map_id: str
    x_side: str  # "low" or "high"
    y_side: str


class IntersectionIn(BaseModel):
    run_id: str
    selections: list[Selection]


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/config")
async def config():
    return {"mock": llm.mock_enabled(), "model": llm.MODEL}


@app.post("/api/dimensions")
async def dimensions(body: BriefIn):
    result = await guard(prompts.propose_dimensions(body.product, body.audience))

    maps = []
    for i, m in enumerate(result["maps"]):
        maps.append({**m, "id": f"m{i}"})

    run_id = uuid.uuid4().hex[:12]
    RUNS[run_id] = {
        "product": body.product,
        "audience": body.audience,
        "maps": maps,
        "ideas": [],
        "themes": [],
    }
    return {"run_id": run_id, "maps": maps}


@app.post("/api/corpus")
async def corpus(body: RunIn):
    run = get_run(body.run_id)
    result = await guard(
        prompts.generate_corpus(run["product"], run["audience"], run["maps"])
    )

    # Ids are assigned here rather than by the model so they are guaranteed unique
    # and stable for every downstream placement call.
    ideas = [
        {"id": f"i{i + 1}", **{k: idea.get(k, "") for k in ("headline", "body", "angle")}}
        for i, idea in enumerate(result["ideas"])
    ]
    run["ideas"] = ideas
    return {"ideas": ideas}


@app.post("/api/themes")
async def themes(body: RunIn):
    run = get_run(body.run_id)
    if not run["ideas"]:
        raise HTTPException(400, "Generate the concept corpus first.")

    result = await guard(
        prompts.cluster_themes(run["product"], run["audience"], run["ideas"])
    )

    valid_ids = {idea["id"] for idea in run["ideas"]}
    grouped = []
    for i, theme in enumerate(result["themes"]):
        idea_ids = [pid for pid in theme.get("idea_ids", []) if pid in valid_ids]
        grouped.append({**theme, "id": f"t{i}", "idea_ids": idea_ids})

    run["themes"] = grouped
    return {"themes": grouped}


@app.post("/api/maps")
async def maps(body: RunIn):
    run = get_run(body.run_id)
    if not run["ideas"]:
        raise HTTPException(400, "Generate the concept corpus first.")

    results = await guard(
        asyncio.gather(
            *(
                prompts.place_on_map(run["product"], run["audience"], run["ideas"], m)
                for m in run["maps"]
            )
        )
    )

    valid_ids = {idea["id"] for idea in run["ideas"]}
    placed = []
    for m, result in zip(run["maps"], results):
        seen: set[str] = set()
        points = []
        for p in result["placements"]:
            pid = p.get("idea_id")
            if pid not in valid_ids or pid in seen:
                continue
            seen.add(pid)
            points.append({"idea_id": pid, "x": clamp(p.get("x")), "y": clamp(p.get("y"))})
        placed.append({"map_id": m["id"], "placements": points})

    run["placements"] = placed
    return {"maps": placed}


@app.post("/api/refine/theme")
async def refine_theme(body: ThemeIn):
    run = get_run(body.run_id)
    theme = next((t for t in run["themes"] if t["id"] == body.theme_id), None)
    if theme is None:
        raise HTTPException(404, "Unknown theme_id.")

    by_id = {idea["id"]: idea for idea in run["ideas"]}
    examples = [by_id[pid] for pid in theme["idea_ids"] if pid in by_id]

    result = await guard(
        prompts.refine_theme(run["product"], run["audience"], theme, examples)
    )
    return {"ideas": result["ideas"]}


@app.post("/api/refine/intersection")
async def refine_intersection(body: IntersectionIn):
    run = get_run(body.run_id)
    if not body.selections:
        raise HTTPException(400, "Select at least one quadrant.")

    maps_by_id = {m["id"]: m for m in run["maps"]}
    constraints, label_parts = [], []

    for sel in body.selections:
        m = maps_by_id.get(sel.map_id)
        if m is None:
            raise HTTPException(404, f"Unknown map_id {sel.map_id}.")
        for axis_key, side in (("x_axis", sel.x_side), ("y_axis", sel.y_side)):
            axis = m[axis_key]
            chosen = axis["high_label"] if side == "high" else axis["low_label"]
            other = axis["low_label"] if side == "high" else axis["high_label"]
            constraints.append(
                f"On the '{axis['name']}' tension, the concept must be clearly "
                f"{chosen}, not {other}."
            )
            label_parts.append(chosen)

    result = await guard(
        prompts.refine_intersection(run["product"], run["audience"], constraints)
    )
    return {
        "ideas": result["ideas"],
        "tension_note": result.get("tension_note", ""),
        "label": " x ".join(label_parts),
    }
