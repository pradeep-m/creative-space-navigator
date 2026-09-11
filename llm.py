"""Async Anthropic wrapper with forced tool-use for structured output, plus a disk cache."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic

ROOT = Path(__file__).parent
CACHE_DIR = ROOT / ".cache"
FIXTURE_PATH = ROOT / "fixtures" / "sample_run.json"

MODEL = "claude-sonnet-5"


class MockMiss(Exception):
    """Raised when MOCK=1 is set but the fixture has no entry for this call."""


def load_env() -> None:
    """Minimal .env loader so we don't need python-dotenv. Real env vars win."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


load_env()

_client: AsyncAnthropic | None = None


def client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def mock_enabled() -> bool:
    return os.environ.get("MOCK") == "1"


_fixtures: dict[str, Any] | None = None


def fixtures() -> dict[str, Any]:
    global _fixtures
    if _fixtures is None:
        if FIXTURE_PATH.exists():
            _fixtures = json.loads(FIXTURE_PATH.read_text())
        else:
            _fixtures = {}
    return _fixtures


def _coerce(result: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    """Repair the occasional tool-use response that serialises a field as a JSON string.

    Seen in practice as {"ideas": "{\\"ideas\\": [...]}"} - the whole payload stringified
    and stuffed back under one key.
    """
    out = dict(result)
    for key, spec in schema.get("properties", {}).items():
        value = out.get(key)
        if not isinstance(value, str) or spec.get("type") not in ("array", "object"):
            continue
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and key in parsed:
            out.update(parsed)  # double-wrapped: lift the inner payload out
        else:
            out[key] = parsed
    return out


def _valid(result: dict[str, Any], schema: dict[str, Any]) -> bool:
    props = schema.get("properties", {})
    for key in schema.get("required", []):
        if key not in result:
            return False
    for key, spec in props.items():
        if key not in result:
            continue
        expected = spec.get("type")
        if expected == "array" and not isinstance(result[key], list):
            return False
        if expected == "object" and not isinstance(result[key], dict):
            return False
    return True


def cache_key(name: str, system: str, user: str, schema: dict[str, Any]) -> str:
    payload = json.dumps(
        {"name": name, "model": MODEL, "system": system, "user": user, "schema": schema},
        sort_keys=True,
    )
    return f"{name}-{hashlib.sha256(payload.encode()).hexdigest()[:16]}"


async def call(
    *,
    name: str,
    system: str,
    user: str,
    tool_name: str,
    tool_description: str,
    input_schema: dict[str, Any],
    max_tokens: int = 8000,
) -> dict[str, Any]:
    """Run one Claude call whose answer is forced through a tool schema.

    Forcing tool_choice means the model must return an object matching input_schema,
    which is far more reliable than parsing JSON out of prose.
    """
    key = cache_key(name, system, user, input_schema)

    if mock_enabled():
        hit = fixtures().get(key)
        if hit is None:
            raise MockMiss(
                f"No fixture for {key}. Run once without MOCK=1 to record it, "
                f"then regenerate fixtures with `python record_fixtures.py`."
            )
        return hit

    cache_file = CACHE_DIR / f"{key}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    nudge = (
        "\n\nIMPORTANT: pass the tool input as a real JSON object. Array fields must be "
        "actual arrays of objects, never a string containing JSON."
    )

    last_error = ""
    for attempt in range(2):
        response = await client().messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user + (nudge if attempt else "")}],
            tools=[
                {
                    "name": tool_name,
                    "description": tool_description,
                    "input_schema": input_schema,
                }
            ],
            tool_choice={"type": "tool", "name": tool_name},
        )

        result = next(
            (block.input for block in response.content if block.type == "tool_use"), None
        )
        if result is None:
            last_error = "model returned no tool_use block"
            continue

        result = _coerce(result, input_schema)
        if not _valid(result, input_schema):
            last_error = f"response did not match schema (keys: {sorted(result)})"
            continue

        # Only cache once the shape is known good, so a bad response can't poison the run.
        CACHE_DIR.mkdir(exist_ok=True)
        cache_file.write_text(json.dumps(result, indent=2))
        return result

    raise RuntimeError(f"{name}: {last_error}")
