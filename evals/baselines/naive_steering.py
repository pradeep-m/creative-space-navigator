"""Eval 3 baseline: ask for the attributes in ordinary language.

This deliberately carries none of the Navigator's control prompt — no binding-constraint
framing, no tension note, no strategist system persona. It keeps only the output shape, so
the judge sees concepts of the same form and is comparing steering rather than formatting.
"""

from __future__ import annotations

import uuid

import prompts
from evals import config
from evals.adapters.navigator import MetaRunner, _concepts
from evals.schemas import Context, Generation, QuadrantSelection, SemanticMap

SYSTEM = "You are a copywriter writing advertising concepts."


def describe_directions(
    maps: list[SemanticMap], selections: list[QuadrantSelection]
) -> list[str]:
    """Plain-language renderings of the same chosen poles the Navigator conditions on."""
    maps_by_id = {m.map_id: m for m in maps}
    lines = []
    for selection in selections:
        smap = maps_by_id[selection.map_id]
        for axis_name in ("x", "y"):
            axis = smap.axis(axis_name)
            side = selection.side(axis_name)
            chosen = axis.pole(side)
            other = axis.pole("low" if side == "high" else "high")
            lines.append(f"{chosen} rather than {other}")
    return lines


async def generate(
    context: Context,
    maps: list[SemanticMap],
    selections: list[QuadrantSelection],
    n: int,
    *,
    run_id: str,
    suite: str,
    condition: str,
    rep: int,
) -> Generation:
    directions = describe_directions(maps, selections)
    bullets = "\n".join(f"- {d}" for d in directions)
    user = f"""Generate exactly {n} marketing concepts for the following product and target
audience.

The concepts should be:
{bullets}

Product: {context.product}
Target audience: {context.target_audience}"""

    generation_id = f"{suite}-naive-{context.id}-{uuid.uuid4().hex[:8]}"
    runner = MetaRunner("generations", cache_salt=f"{suite}:naive:{condition}:rep{rep}")
    result = await runner(
        name="naive_steering",
        system=SYSTEM,
        user=user,
        tool_name="submit_concepts",
        tool_description="Return the concepts.",
        input_schema={
            "type": "object",
            "properties": {"ideas": {"type": "array", "items": prompts.IDEA_SCHEMA}},
            "required": ["ideas"],
        },
    )
    return Generation(
        generation_id=generation_id,
        run_id=run_id,
        context_id=context.id,
        suite=suite,
        arm="naive",
        condition=condition,
        rep=rep,
        selections=[s.to_dict() for s in selections],
        map_ids=[m.map_id for m in maps],
        concepts=_concepts(generation_id, result.get("ideas", []), n),
        model=runner.meta.get("model", config.GENERATOR_MODEL),
        temperature=runner.meta.get("temperature"),
        prompt_hash=runner.meta.get("prompt_hash", ""),
        production_prompt_hash=config.production_prompt_hash(),
        cache_key=runner.meta.get("cache_key", ""),
        raw_response=runner.meta.get("raw_response"),
        extra={"directions": directions},
    )
