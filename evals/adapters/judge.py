"""The blind LLM judge.

Blinding is structural. None of these functions accepts a selected quadrant, a desired
pole, an expected score, an arm label or a production prompt, so no caller can leak one
into the judge even by mistake. Normalisation toward the selected pole happens in the
metrics layer, after the judge has already committed to a score.
"""

from __future__ import annotations

import uuid
from typing import Any

import llm
from evals import config, store
from evals.schemas import Axis, AxisQualityJudgment, Judgment, SemanticMap

_SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {
            "type": "integer",
            "description": "1 to 5, where 1 is the low pole and 5 is the high pole.",
        },
        "reason": {"type": "string", "description": "One or two sentences."},
    },
    "required": ["score", "reason"],
}

_NEUTRALITY = """Rules:
- Neither end of the dimension is better than the other. You are locating the concept, not
  rating it.
- A score of 3 is the correct answer for a concept that is genuinely balanced or that does
  not clearly express this dimension at all. Do not avoid 3, and do not use it to hedge a
  concept that plainly commits to one side.
- Marketing quality is irrelevant. A clumsy concept that sits clearly at one end still
  scores at that end.
- Factual correctness is irrelevant except where you need it to understand the concept.
- Score only the dimension described above. Ignore every other property the concept has.
- Do not try to work out what score was expected of you. There is no expected answer."""


def _judge_salt(*parts: str) -> str:
    return ":".join(("v" + config.EVAL_VERSION, config.JUDGE_PROMPT_VERSION, *parts))


async def _ask(name: str, system: str, user: str, tool: str, schema: dict, salt: str) -> dict:
    # temperature is passed through only if the environment set it; these models reject it.
    async with store.api_limit():
        return await llm.call(
            name=name,
            system=system,
            user=user,
            tool_name=tool,
            tool_description="Return the structured judgment.",
            input_schema=schema,
            max_tokens=4096,
            model=config.JUDGE_MODEL,
            temperature=config.JUDGE_TEMPERATURE,
            cache_salt=salt,
            cache_dir=store.cache_dir("judgments"),
            # The judge model rejects tool_choice type "tool"; structured output is its
            # equivalent guarantee that the response parses.
            output_format=True,
        )


def _score(raw: Any) -> int:
    try:
        value = int(round(float(raw)))
    except (TypeError, ValueError):
        return 3
    return max(1, min(5, value))


def _grounding(smap: SemanticMap, grounded: bool) -> str:
    if not grounded or not smap.rationale:
        return ""
    return f"""
How this dimension was defined for this brief:
"{smap.title}" - {smap.rationale}

That definition tells you what the dimension means. It is not a claim that either end is
the better choice, and it was written before this concept existed.
"""


async def score_axis(
    *,
    product: str,
    audience: str,
    concept_id: str,
    concept_text: str,
    smap: SemanticMap,
    axis: str,
    grounded: bool = True,
    repeat: int = 0,
) -> Judgment:
    """Place one concept on one axis. One axis per call.

    Scoring both axes in a single response lets the second score anchor on the first, which
    would directly contaminate the isolation measurement, so the calls are kept apart.

    `repeat` only varies the cache key, so the same judgment can be drawn a second time to
    measure judge self-consistency. It carries no information about the concept.
    """
    definition: Axis = smap.axis(axis)
    system = (
        "You are a careful annotator who locates marketing concepts on a defined semantic "
        "dimension. You are precise, you use the full 1-5 range, and you have no stake in "
        "where any concept lands."
    )
    user = f"""Product: {product}
Target audience: {audience}

Semantic dimension: {definition.name}
  1 = strongly {definition.low_label}
  2 = somewhat {definition.low_label}
  3 = balanced, ambiguous, or not clearly either
  4 = somewhat {definition.high_label}
  5 = strongly {definition.high_label}
{_grounding(smap, grounded)}
Concept:
{concept_text}

{_NEUTRALITY}"""

    result = await _ask(
        "judge_axis",
        system,
        user,
        "submit_axis_score",
        _SCORE_SCHEMA,
        _judge_salt(
            "axis",
            "grounded" if grounded else "blind",
            *((f"repeat{repeat}",) if repeat else ()),
        ),
    )
    return Judgment(
        judgment_id=f"j-{uuid.uuid4().hex[:10]}",
        concept_id=concept_id,
        map_id=smap.map_id,
        axis=axis,
        score=_score(result.get("score")),
        reason=str(result.get("reason", "")),
        grounded=grounded,
        judge_model=config.JUDGE_MODEL,
        judge_temperature=config.JUDGE_TEMPERATURE,
        judge_prompt_version=config.JUDGE_PROMPT_VERSION,
        repeat=repeat,
    )


_QUALITY_SCHEMA = {
    "type": "object",
    "properties": {
        "relevance": {"type": "integer"},
        "polarity": {"type": "integer"},
        "actionability": {"type": "integer"},
        "axis_distinctness": {"type": "integer"},
        "reason": {"type": "string"},
    },
    "required": ["relevance", "polarity", "actionability", "axis_distinctness", "reason"],
}


async def score_map_quality(*, product: str, audience: str, smap: SemanticMap) -> dict:
    """Eval 1, per map. The judge never sees any downstream concept."""
    system = (
        "You are a strategy director assessing whether a proposed pair of creative "
        "dimensions is a useful way to organise advertising ideas for a specific brief."
    )
    user = f"""Product: {product}
Target audience: {audience}

Proposed 2x2 map: "{smap.title}"
  X dimension - {smap.x_axis.name}: from "{smap.x_axis.low_label}" to "{smap.x_axis.high_label}"
  Y dimension - {smap.y_axis.name}: from "{smap.y_axis.low_label}" to "{smap.y_axis.high_label}"
  Stated rationale: {smap.rationale}

Score this map 1-5 on each of the following.

relevance: Does this distinction meaningfully matter for this product and audience?
polarity: Do the two ends of each axis represent meaningfully distinguishable directions,
  with both ends being viable rather than one obviously wrong?
actionability: Would choosing opposite poles plausibly lead to materially different concepts?
axis_distinctness: Do X and Y capture different semantic properties, such that knowing a
  concept's position on one tells you little about its position on the other?

Judge the map as a tool for exploring the space. Do not reward elegant wording, and do not
penalise a map for being unglamorous if it would genuinely separate concepts."""

    return await _ask(
        "judge_map_quality", system, user, "submit_map_quality", _QUALITY_SCHEMA,
        _judge_salt("map_quality"),
    )


_REDUNDANCY_SCHEMA = {
    "type": "object",
    "properties": {
        "scores": {
            "type": "array",
            "description": "One entry per map, in the order presented.",
            "items": {
                "type": "object",
                "properties": {
                    "map_title": {"type": "string"},
                    "non_redundancy": {"type": "integer"},
                    "reason": {"type": "string"},
                },
                "required": ["map_title", "non_redundancy", "reason"],
            },
        }
    },
    "required": ["scores"],
}


async def score_redundancy(*, product: str, audience: str, maps: list[SemanticMap]) -> list[dict]:
    """Redundancy needs every map from the context in one prompt.

    The PRD asks whether a map "substantially duplicates another generated map" while
    giving the judge a single map, which cannot be answered; this call supplies the set.
    """
    blocks = "\n\n".join(
        f"""Map {i + 1}: "{m.title}"
  X - {m.x_axis.name}: "{m.x_axis.low_label}" to "{m.x_axis.high_label}"
  Y - {m.y_axis.name}: "{m.y_axis.low_label}" to "{m.y_axis.high_label}\""""
        for i, m in enumerate(maps)
    )
    system = (
        "You are a strategy director checking whether a set of proposed creative dimensions "
        "covers genuinely different ground or keeps restating one underlying tension."
    )
    user = f"""Product: {product}
Target audience: {audience}

{blocks}

For each map, score how distinct it is from the other maps shown, 1-5:
  1 = highly redundant, essentially a rewording of another map
  5 = highly distinct, captures ground no other map captures

Two maps are redundant when a concept's position on one is largely predictable from its
position on the other, even if the labels differ. Return one entry per map, in order."""

    result = await _ask(
        "judge_redundancy", system, user, "submit_redundancy", _REDUNDANCY_SCHEMA,
        _judge_salt("redundancy"),
    )
    return result.get("scores", [])


def build_axis_quality(
    context_id: str, smap: SemanticMap, quality: dict, redundancy: dict | None
) -> AxisQualityJudgment:
    return AxisQualityJudgment(
        context_id=context_id,
        map_id=smap.map_id,
        relevance=_score(quality.get("relevance")),
        polarity=_score(quality.get("polarity")),
        actionability=_score(quality.get("actionability")),
        axis_distinctness=_score(quality.get("axis_distinctness")),
        reason=str(quality.get("reason", "")),
        non_redundancy=_score(redundancy.get("non_redundancy")) if redundancy else None,
        redundancy_reason=str(redundancy.get("reason", "")) if redundancy else "",
    )
