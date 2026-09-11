"""Prompts and tool schemas for each stage of the exploration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import llm

CORPUS_SIZE = 24

# Every stage dispatches through this instead of calling llm.call directly, so the eval
# harness can swap in a runner that records provenance or overrides the model, without
# any prompt text being duplicated outside this module.
Runner = Callable[..., Awaitable[dict[str, Any]]]

IDEA_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string", "description": "The ad headline, under 12 words."},
        "body": {"type": "string", "description": "One or two sentences of body copy."},
        "angle": {
            "type": "string",
            "description": (
                "A short plain-language note on the strategic idea, under 15 words. "
                "Describe the persuasive move, e.g. 'reframes price as cost per use'. "
                "Never name or restate map axes, poles or quadrants here."
            ),
        },
    },
    "required": ["headline", "body", "angle"],
}

AXIS_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Name of the tension, e.g. 'Emotional vs Rational'."},
        "low_label": {"type": "string", "description": "Short label for the -1 pole, 1-3 words."},
        "high_label": {"type": "string", "description": "Short label for the +1 pole, 1-3 words."},
    },
    "required": ["name", "low_label", "high_label"],
}


def _brief(product: str, audience: str) -> str:
    return f"Product: {product}\nTarget audience: {audience}"


def _format_ideas(ideas: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"[{idea['id']}] {idea['headline']} — {idea['body']} (angle: {idea['angle']})"
        for idea in ideas
    )


def _format_map(m: dict[str, Any]) -> str:
    x, y = m["x_axis"], m["y_axis"]
    return (
        f"Map '{m['title']}'\n"
        f"  X axis ({x['name']}): -1 = {x['low_label']}, +1 = {x['high_label']}\n"
        f"  Y axis ({y['name']}): -1 = {y['low_label']}, +1 = {y['high_label']}"
    )


async def propose_dimensions(
    product: str, audience: str, *, runner: Runner | None = None
) -> dict[str, Any]:
    system = (
        "You are a creative strategist who structures the space of possible advertising "
        "concepts. You think in terms of underlying tensions that generate real variation, "
        "not surface-level tags."
    )
    user = f"""{_brief(product, audience)}

Propose 3 semantic 2x2 maps for exploring the space of ad concepts for this brief.
Each map is a pair of axes, and each axis is a tension with two opposing poles.

Examples of the *shape* of axis we want (do not simply copy these):
- Emotional vs Rational
- Product-led vs Customer-led
- Expository vs Persuasive

Hard requirements:
1. The six axes across the three maps must be mostly orthogonal. Two axes are orthogonal
   when knowing where a concept sits on one tells you nothing about where it sits on the
   other. Do not produce two axes that are rephrasings of the same underlying tension.
2. Within a single map, the two paired axes especially must be independent, otherwise the
   concepts will collapse onto a diagonal and two quadrants will sit empty.
3. Every pole must describe a genuinely viable direction for this brief. Avoid poles that
   are obviously the "wrong" choice, since nobody will ever select them.
4. At least one map should use a tension specific to this product and audience rather than
   a generic advertising tension.

For each map give a short title, the two axes with concise pole labels, and one sentence on
why this tension matters for this particular brief."""

    return await (runner or llm.call)(
        name="dimensions",
        system=system,
        user=user,
        tool_name="propose_maps",
        tool_description="Return the proposed 2x2 creative maps.",
        input_schema={
            "type": "object",
            "properties": {
                "maps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "x_axis": AXIS_SCHEMA,
                            "y_axis": AXIS_SCHEMA,
                            "rationale": {"type": "string"},
                        },
                        "required": ["title", "x_axis", "y_axis", "rationale"],
                    },
                }
            },
            "required": ["maps"],
        },
    )


async def generate_corpus(
    product: str,
    audience: str,
    maps: list[dict[str, Any]],
    count: int | None = None,
    *,
    runner: Runner | None = None,
) -> dict[str, Any]:
    n = CORPUS_SIZE if count is None else count
    quadrant_lines = []
    for m in maps:
        x, y = m["x_axis"], m["y_axis"]
        quadrant_lines.append(
            f"- {m['title']}: {x['low_label']}/{y['low_label']}, {x['high_label']}/{y['low_label']}, "
            f"{x['low_label']}/{y['high_label']}, {x['high_label']}/{y['high_label']}"
        )

    system = (
        "You are a senior copywriter generating a deliberately wide range of ad concepts. "
        "Your job is coverage of the possibility space, not polish on a single idea."
    )
    # Default count keeps the production prompt byte-identical so existing cache keys still hit.
    if n == CORPUS_SIZE:
        user = f"""{_brief(product, audience)}

Generate exactly {CORPUS_SIZE} distinct ad concepts.

These concepts will be plotted onto the following 2x2 maps, so the set must spread across
the whole space. Every quadrant listed below needs at least two concepts that clearly
belong in it:

{chr(10).join(quadrant_lines)}

Rules:
- Maximise genuine diversity. If two concepts could be swapped without a reader noticing,
  one of them is wasted.
- Vary the strategic angle, not just the wording. Different promises, different objections
  handled, different moments of use, different emotional registers.
- Some concepts should be deliberately extreme on one axis. Do not hedge everything to the
  middle, or the maps will be useless.
- Keep every concept plausible enough to actually run.
- The maps above are scaffolding for your own coverage. Never mention the axes, poles or
  quadrant names in the headline, body or angle. A reader of the output should not be able
  to tell that these maps exist."""
    else:
        per_quadrant = max(1, n // (4 * max(len(maps), 1)))
        user = f"""{_brief(product, audience)}

Generate exactly {n} distinct ad concepts.

These concepts will be plotted onto the following 2x2 maps, so the set must spread across
the whole space. Every quadrant listed below needs at least {per_quadrant} concepts that clearly
belong in it:

{chr(10).join(quadrant_lines)}

Rules:
- Maximise genuine diversity. If two concepts could be swapped without a reader noticing,
  one of them is wasted.
- Vary the strategic angle, not just the wording. Different promises, different objections
  handled, different moments of use, different emotional registers.
- Some concepts should be deliberately extreme on one axis. Do not hedge everything to the
  middle, or the maps will be useless.
- Keep every concept plausible enough to actually run.
- The maps above are scaffolding for your own coverage. Never mention the axes, poles or
  quadrant names in the headline, body or angle. A reader of the output should not be able
  to tell that these maps exist."""

    return await (runner or llm.call)(
        name="corpus",
        system=system,
        user=user,
        tool_name="submit_concepts",
        tool_description="Return the full set of ad concepts.",
        input_schema={
            "type": "object",
            "properties": {"ideas": {"type": "array", "items": IDEA_SCHEMA}},
            "required": ["ideas"],
        },
    )


async def cluster_themes(
    product: str,
    audience: str,
    ideas: list[dict[str, Any]],
    *,
    runner: Runner | None = None,
) -> dict[str, Any]:
    """Deliberately not told about the axes, so this stays an honest naive baseline."""
    system = (
        "You are a creative director reviewing a batch of ad concepts and organising them "
        "into a handful of distinct creative directions a client could choose between."
    )
    user = f"""{_brief(product, audience)}

Here are {len(ideas)} ad concepts:

{_format_ideas(ideas)}

Group them into 4 to 6 distinct creative themes.

Rules:
- Every concept must be assigned to exactly one theme.
- Themes must be genuinely different directions, not severity gradings of one direction.
- Name each theme the way a strategist would present it to a client: evocative but concrete.
- The description should say what the theme claims and who it is for, in one sentence."""

    return await (runner or llm.call)(
        name="themes",
        system=system,
        user=user,
        tool_name="submit_themes",
        tool_description="Return the thematic grouping of the concepts.",
        input_schema={
            "type": "object",
            "properties": {
                "themes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "idea_ids": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["name", "description", "idea_ids"],
                    },
                }
            },
            "required": ["themes"],
        },
    )


async def place_on_map(
    product: str,
    audience: str,
    ideas: list[dict[str, Any]],
    m: dict[str, Any],
    *,
    runner: Runner | None = None,
) -> dict[str, Any]:
    system = (
        "You are an analyst placing creative concepts onto a semantic map. You are precise "
        "and you use the full range of the scale."
    )
    user = f"""{_brief(product, audience)}

{_format_map(m)}

Place every one of these {len(ideas)} concepts on that map:

{_format_ideas(ideas)}

For each concept give an x and a y score between -1 and 1.

Rules:
- Use the full range. Scores bunched near zero make the map unreadable.
- Avoid exactly 0 on either axis; commit to a side.
- Judge each concept independently on each axis. Do not let a concept's x score drag its
  y score along with it.
- Return one entry for every concept id listed above, using those exact ids."""

    return await (runner or llm.call)(
        name="placement",
        system=system,
        user=user,
        tool_name="submit_placements",
        tool_description="Return the coordinates for every concept on this map.",
        input_schema={
            "type": "object",
            "properties": {
                "placements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "idea_id": {"type": "string"},
                            "x": {"type": "number"},
                            "y": {"type": "number"},
                        },
                        "required": ["idea_id", "x", "y"],
                    },
                }
            },
            "required": ["placements"],
        },
    )


async def refine_theme(
    product: str,
    audience: str,
    theme: dict[str, Any],
    examples: list[dict[str, Any]],
    count: int = 6,
    *,
    runner: Runner | None = None,
) -> dict[str, Any]:
    system = (
        "You are a senior copywriter developing one chosen creative direction in more depth."
    )
    user = f"""{_brief(product, audience)}

The chosen creative direction is "{theme['name']}": {theme['description']}

Concepts already in this direction:

{_format_ideas(examples)}

Write {count} new concepts in this same direction.

Rules:
- Stay unmistakably inside this direction.
- Do not restate the concepts above. Find angles the existing set has missed.
- Vary the execution: some short and blunt, some warmer, some with a specific concrete detail."""

    return await (runner or llm.call)(
        name="refine_theme",
        system=system,
        user=user,
        tool_name="submit_concepts",
        tool_description="Return the new concepts.",
        input_schema={
            "type": "object",
            "properties": {"ideas": {"type": "array", "items": IDEA_SCHEMA}},
            "required": ["ideas"],
        },
    )


def build_intersection_constraints(
    maps: list[dict[str, Any]],
    selections: list[dict[str, Any]],
    include_rationale: bool = False,
) -> tuple[list[str], list[str]]:
    """Turn selected quadrants into the binding constraint lines and a display label.

    Lives here rather than in the route so the eval harness conditions generation through
    exactly the same text the app does. include_rationale is off in production: the app
    passes only axis names and pole labels, which is what the eval measures by default.

    Raises KeyError if a selection names a map that was not supplied.
    """
    maps_by_id = {m["id"]: m for m in maps}
    constraints: list[str] = []
    label_parts: list[str] = []

    for sel in selections:
        m = maps_by_id[sel["map_id"]]
        for axis, side in (
            (m["x_axis"], sel["x_side"]),
            (m["y_axis"], sel["y_side"]),
        ):
            chosen = axis["high_label"] if side == "high" else axis["low_label"]
            other = axis["low_label"] if side == "high" else axis["high_label"]
            constraints.append(
                f"On the '{axis['name']}' tension, the concept must be clearly "
                f"{chosen}, not {other}."
            )
            label_parts.append(chosen)
        if include_rationale and m.get("rationale"):
            constraints.append(f"Context for the '{m['title']}' tensions: {m['rationale']}")

    return constraints, label_parts


async def refine_intersection(
    product: str,
    audience: str,
    constraints: list[str],
    count: int = 6,
    *,
    runner: Runner | None = None,
) -> dict[str, Any]:
    system = (
        "You are a senior copywriter working inside a tightly specified creative brief. "
        "You treat the constraints as binding."
    )
    bullets = "\n".join(f"- {c}" for c in constraints)
    user = f"""{_brief(product, audience)}

Write {count} new ad concepts that satisfy ALL of the following constraints at once:

{bullets}

Rules:
- Every constraint is binding. A concept that satisfies only some of them is a failure.
- Within those constraints, make the {count} concepts as different from each other as possible.
- If two of the constraints are in genuine tension, say so in `tension_note` and explain how
  you resolved it. Do not quietly water both down into something generic. If they sit together
  comfortably, leave `tension_note` empty."""

    return await (runner or llm.call)(
        name="refine_intersection",
        system=system,
        user=user,
        tool_name="submit_concepts",
        tool_description="Return the constrained concepts.",
        input_schema={
            "type": "object",
            "properties": {
                "ideas": {"type": "array", "items": IDEA_SCHEMA},
                "tension_note": {"type": "string"},
            },
            "required": ["ideas"],
        },
    )
