"""Thin adapter over the production pipeline.

Every prompt string used here comes from prompts.py. Nothing in this module reproduces
production prompt text, so a change to production prompts changes eval behaviour
automatically, and config.production_prompt_hash() records which version ran.
"""

from __future__ import annotations

import uuid
from typing import Any

import llm
import prompts
from evals import config, store
from evals.schemas import Concept, Context, Generation, QuadrantSelection, SemanticMap


class MetaRunner:
    """Dispatch target handed to production prompt functions.

    Captures provenance and applies eval-only overrides (model, temperature, cache
    partition, repetition salt) without the production code knowing about any of it.
    """

    def __init__(self, cache_kind: str, *, cache_salt: str = "", temperature: float | None = None):
        self.overrides = {
            "model": config.GENERATOR_MODEL,
            "temperature": temperature if temperature is not None else config.GENERATOR_TEMPERATURE,
            "cache_salt": cache_salt,
            "cache_dir": store.cache_dir(cache_kind),
        }
        self.meta: dict[str, Any] = {}

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        async with store.api_limit():
            result, meta = await llm.call_with_meta(**kwargs, **self.overrides)
        self.meta = meta
        return result


def _concepts(generation_id: str, raw: list[dict], limit: int | None = None) -> list[Concept]:
    items = raw[:limit] if limit else raw
    return [
        Concept(
            concept_id=f"{generation_id}-c{i}",
            generation_id=generation_id,
            headline=str(item.get("headline", "")).strip(),
            body=str(item.get("body", "")).strip(),
            angle=str(item.get("angle", "")).strip(),
        )
        for i, item in enumerate(items)
        if str(item.get("headline", "")).strip() or str(item.get("body", "")).strip()
    ]


class NavigatorAdapter:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id

    async def generate_maps(self, context: Context, limit: int) -> list[SemanticMap]:
        runner = MetaRunner("maps")
        result = await prompts.propose_dimensions(
            context.product, context.target_audience, runner=runner
        )
        # Production assigns ids positionally in the route; mirror that exactly.
        return [
            SemanticMap.from_production(context.id, f"m{i}", raw)
            for i, raw in enumerate(result["maps"][:limit])
        ]

    async def generate_concepts(
        self,
        context: Context,
        maps: list[SemanticMap],
        selections: list[QuadrantSelection],
        n: int,
        *,
        suite: str,
        arm: str,
        condition: str,
        rep: int,
        include_rationale: bool = False,
    ) -> Generation:
        """The only quadrant-conditioned generator in production: the drill-down."""
        constraints, label_parts = prompts.build_intersection_constraints(
            [m.to_prompt_dict() for m in maps],
            [s.to_dict() for s in selections],
            include_rationale=include_rationale,
        )
        generation_id = f"{suite}-{arm}-{context.id}-{uuid.uuid4().hex[:8]}"
        runner = MetaRunner("generations", cache_salt=f"{suite}:{arm}:{condition}:rep{rep}")
        result = await prompts.refine_intersection(
            context.product,
            context.target_audience,
            constraints,
            count=n,
            runner=runner,
        )
        return self._generation(
            generation_id,
            context,
            suite,
            arm,
            condition,
            rep,
            runner,
            _concepts(generation_id, result.get("ideas", []), n),
            selections=[s.to_dict() for s in selections],
            map_ids=[m.map_id for m in maps],
            extra={
                "constraints": constraints,
                "label": " x ".join(label_parts),
                "tension_note": result.get("tension_note", ""),
                "include_rationale": include_rationale,
            },
        )

    async def generate_corpus(
        self,
        context: Context,
        maps: list[SemanticMap],
        *,
        suite: str,
        limit: int | None = None,
        count: int | None = None,
    ) -> Generation:
        """The main-flow generator: one unconditioned batch told to span the maps."""
        generation_id = f"{suite}-corpus-{context.id}"
        runner = MetaRunner(
            "generations",
            cache_salt=f"{suite}:corpus:{count if count is not None else 'default'}",
        )
        result = await prompts.generate_corpus(
            context.product,
            context.target_audience,
            [m.to_prompt_dict() for m in maps],
            count=count,
            runner=runner,
        )
        return self._generation(
            generation_id,
            context,
            suite,
            "structured_corpus",
            "corpus",
            0,
            runner,
            _concepts(generation_id, result.get("ideas", []), limit),
            map_ids=[m.map_id for m in maps],
        )

    async def place_on_map(
        self, context: Context, concepts: list[Concept], smap: SemanticMap
    ) -> dict[str, tuple[float, float]]:
        """Production's own -1..+1 placement, used only by the placement-fidelity suite."""
        runner = MetaRunner("judgments", cache_salt="placement")
        ideas = [
            {"id": c.concept_id, "headline": c.headline, "body": c.body, "angle": c.angle}
            for c in concepts
        ]
        result = await prompts.place_on_map(
            context.product,
            context.target_audience,
            ideas,
            smap.to_prompt_dict(),
            runner=runner,
        )
        placements: dict[str, tuple[float, float]] = {}
        for entry in result.get("placements", []):
            concept_id = entry.get("idea_id")
            if concept_id is None:
                continue
            placements[concept_id] = (_clamp(entry.get("x")), _clamp(entry.get("y")))
        return placements

    def _generation(
        self,
        generation_id: str,
        context: Context,
        suite: str,
        arm: str,
        condition: str,
        rep: int,
        runner: MetaRunner,
        concepts: list[Concept],
        *,
        selections: list[dict] | None = None,
        map_ids: list[str] | None = None,
        extra: dict | None = None,
    ) -> Generation:
        return Generation(
            generation_id=generation_id,
            run_id=self.run_id,
            context_id=context.id,
            suite=suite,
            arm=arm,
            condition=condition,
            rep=rep,
            selections=selections or [],
            map_ids=map_ids or [],
            concepts=concepts,
            model=runner.meta.get("model", config.GENERATOR_MODEL),
            temperature=runner.meta.get("temperature"),
            prompt_hash=runner.meta.get("prompt_hash", ""),
            production_prompt_hash=config.production_prompt_hash(),
            cache_key=runner.meta.get("cache_key", ""),
            raw_response=runner.meta.get("raw_response"),
            extra=extra or {},
        )


def _clamp(value: Any) -> float:
    try:
        return max(-1.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0
