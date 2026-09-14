"""Creative Space Navigator - FastAPI app.

Stateless by design: the browser holds the run and passes the pieces it needs back with
each request. That costs a few KB per call and buys deployability onto serverless, where
an in-memory run store would break the moment two requests hit different instances.
"""

from __future__ import annotations

import asyncio
import base64
import os
import secrets
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import llm
import prompts

ROOT = Path(__file__).parent
STATIC = ROOT / "static"

APP_PASSWORD = os.environ.get("APP_PASSWORD", "")

app = FastAPI(title="Creative Space Navigator")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def password_gate(request: Request, call_next):
    """Shared-password basic auth, so a public demo URL can't burn the API key.

    Disabled entirely when APP_PASSWORD is unset, which is the local dev case.
    """
    if not APP_PASSWORD:
        return await call_next(request)

    header = request.headers.get("authorization", "")
    if header.startswith("Basic "):
        try:
            decoded = base64.b64decode(header[6:]).decode()
        except (ValueError, UnicodeDecodeError):
            decoded = ""
        _, _, supplied = decoded.partition(":")
        if secrets.compare_digest(supplied, APP_PASSWORD):
            return await call_next(request)

    return Response(
        status_code=401,
        content="Authentication required.",
        headers={"WWW-Authenticate": 'Basic realm="Creative Space Navigator"'},
    )


# ---------------------------------------------------------------- payload models

MAX_IDEAS = 60


class Axis(BaseModel):
    name: str = Field(max_length=120)
    low_label: str = Field(max_length=60)
    high_label: str = Field(max_length=60)


class Map(BaseModel):
    id: str = Field(max_length=16)
    title: str = Field(max_length=120)
    x_axis: Axis
    y_axis: Axis
    rationale: str = Field(default="", max_length=2000)


class Idea(BaseModel):
    id: str = Field(max_length=16)
    headline: str = Field(max_length=300)
    body: str = Field(default="", max_length=1000)
    angle: str = Field(default="", max_length=300)


class Theme(BaseModel):
    id: str = Field(max_length=16)
    name: str = Field(max_length=200)
    description: str = Field(default="", max_length=1000)
    idea_ids: list[str] = Field(default_factory=list, max_length=MAX_IDEAS)


class Brief(BaseModel):
    product: str = Field(min_length=1, max_length=300)
    audience: str = Field(min_length=1, max_length=300)


class CorpusIn(Brief):
    maps: list[Map] = Field(max_length=6)


class ThemesIn(Brief):
    ideas: list[Idea] = Field(max_length=MAX_IDEAS)


class MapsIn(Brief):
    ideas: list[Idea] = Field(max_length=MAX_IDEAS)
    maps: list[Map] = Field(max_length=6)


class RefineThemeIn(Brief):
    theme: Theme
    examples: list[Idea] = Field(default_factory=list, max_length=MAX_IDEAS)


class Selection(BaseModel):
    map_id: str = Field(max_length=16)
    x_side: str = Field(pattern="^(low|high)$")
    y_side: str = Field(pattern="^(low|high)$")


class IntersectionIn(Brief):
    maps: list[Map] = Field(max_length=6)
    selections: list[Selection] = Field(min_length=1, max_length=6)
    prior_headlines: list[str] = Field(default_factory=list, max_length=MAX_IDEAS)


# ---------------------------------------------------------------- helpers


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


# ---------------------------------------------------------------- routes


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/config")
async def config():
    return {"mock": llm.mock_enabled(), "model": llm.MODEL}


@app.post("/api/dimensions")
async def dimensions(body: Brief):
    result = await guard(prompts.propose_dimensions(body.product, body.audience))
    maps = [{**m, "id": f"m{i}"} for i, m in enumerate(result["maps"])]
    return {"maps": maps}


@app.post("/api/corpus")
async def corpus(body: CorpusIn):
    maps = [m.model_dump() for m in body.maps]
    result = await guard(prompts.generate_corpus(body.product, body.audience, maps))

    # Ids are assigned here rather than by the model so they are unique and stable
    # for every downstream placement call.
    ideas = [
        {"id": f"i{i + 1}", **{k: idea.get(k, "") for k in ("headline", "body", "angle")}}
        for i, idea in enumerate(result["ideas"][:MAX_IDEAS])
    ]
    return {"ideas": ideas}


@app.post("/api/themes")
async def themes(body: ThemesIn):
    ideas = [i.model_dump() for i in body.ideas]
    if not ideas:
        raise HTTPException(400, "No concepts supplied.")

    result = await guard(prompts.cluster_themes(body.product, body.audience, ideas))

    valid_ids = {i["id"] for i in ideas}
    grouped = [
        {
            **theme,
            "id": f"t{n}",
            "idea_ids": [pid for pid in theme.get("idea_ids", []) if pid in valid_ids],
        }
        for n, theme in enumerate(result["themes"])
    ]
    return {"themes": grouped}


@app.post("/api/maps")
async def maps(body: MapsIn):
    ideas = [i.model_dump() for i in body.ideas]
    map_dicts = [m.model_dump() for m in body.maps]
    if not ideas:
        raise HTTPException(400, "No concepts supplied.")

    results = await guard(
        asyncio.gather(
            *(
                prompts.place_on_map(body.product, body.audience, ideas, m)
                for m in map_dicts
            )
        )
    )

    valid_ids = {i["id"] for i in ideas}
    placed = []
    for m, result in zip(map_dicts, results):
        seen: set[str] = set()
        points = []
        for p in result["placements"]:
            pid = p.get("idea_id")
            if pid not in valid_ids or pid in seen:
                continue
            seen.add(pid)
            points.append({"idea_id": pid, "x": clamp(p.get("x")), "y": clamp(p.get("y"))})
        placed.append({"map_id": m["id"], "placements": points})

    return {"maps": placed}


@app.post("/api/refine/theme")
async def refine_theme(body: RefineThemeIn):
    result = await guard(
        prompts.refine_theme(
            body.product,
            body.audience,
            body.theme.model_dump(),
            [i.model_dump() for i in body.examples],
        )
    )
    return {"ideas": result["ideas"]}


@app.post("/api/refine/intersection")
async def refine_intersection(body: IntersectionIn):
    try:
        constraints, label_parts = prompts.build_intersection_constraints(
            [m.model_dump() for m in body.maps],
            [s.model_dump() for s in body.selections],
        )
    except KeyError as exc:
        raise HTTPException(404, f"Unknown map_id {exc.args[0]}.") from exc

    # MOCK replay is keyed on the exact prompt, so skip priors there and reuse the
    # recorded fixture. Live runs pass them so a second generate is actually new.
    priors = [] if llm.mock_enabled() else [h for h in body.prior_headlines if h.strip()]
    result = await guard(
        prompts.refine_intersection(
            body.product, body.audience, constraints, prior_headlines=priors
        )
    )
    return {
        "ideas": result["ideas"],
        "tension_note": result.get("tension_note", ""),
        "label": " x ".join(label_parts),
    }
