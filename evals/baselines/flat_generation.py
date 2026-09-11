"""Eval 6 baseline: undirected diversity prompting.

The alternative hypothesis is that you can skip navigation entirely and just ask for a
dozen different ideas. This arm gets the same concept budget as the structured arms and is
told nothing about the maps.
"""

from __future__ import annotations

import prompts
from evals import config
from evals.adapters.navigator import MetaRunner, _concepts
from evals.schemas import Context, Generation

SYSTEM = "You are a copywriter writing advertising concepts."


async def generate(
    context: Context, budget: int, *, run_id: str, suite: str = "coverage"
) -> Generation:
    user = f"""Product: {context.product}
Target audience: {context.target_audience}

Generate {budget} meaningfully diverse creative concepts for this product and target
audience. Avoid simple paraphrases and explore substantially different directions."""

    generation_id = f"{suite}-flat-{context.id}"
    runner = MetaRunner("generations", cache_salt=f"{suite}:flat")
    result = await runner(
        name="flat_generation",
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
        arm="flat",
        condition="flat",
        rep=0,
        concepts=_concepts(generation_id, result.get("ideas", []), budget),
        model=runner.meta.get("model", config.GENERATOR_MODEL),
        temperature=runner.meta.get("temperature"),
        prompt_hash=runner.meta.get("prompt_hash", ""),
        production_prompt_hash=config.production_prompt_hash(),
        cache_key=runner.meta.get("cache_key", ""),
        raw_response=runner.meta.get("raw_response"),
    )
