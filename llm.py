"""Async Anthropic wrapper with forced tool-use for structured output, plus a disk cache."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic, Timeout

ROOT = Path(__file__).parent
FIXTURE_PATH = ROOT / "fixtures" / "sample_run.json"


def _default_cache_dir() -> Path:
    # Serverless filesystems are read-only apart from /tmp, and that /tmp is per-instance,
    # so the cache degrades to a best-effort warm-instance optimisation there.
    if os.environ.get("VERCEL"):
        return Path("/tmp/csn-cache")
    return ROOT / ".cache"


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


# Before CACHE_DIR and MODEL, so both can be overridden from .env and not just real env vars.
load_env()

CACHE_DIR = Path(os.environ.get("CACHE_DIR") or _default_cache_dir())

MODEL = os.environ.get("GENERATOR_MODEL") or "claude-sonnet-5"

_client: AsyncAnthropic | None = None


def client() -> AsyncAnthropic:
    global _client
    if _client is None:
        # Default SDK read timeout is 600s × 2 retries ≈ 30 minutes of silence.
        # Judge and 3-concept generations finish in seconds; 120s is already generous.
        _client = AsyncAnthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"],
            timeout=Timeout(connect=10.0, read=120.0, write=120.0, pool=30.0),
            max_retries=2,
        )
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


def _strict(schema: Any) -> Any:
    """Recursively forbid extra properties, which json_schema output config requires."""
    if not isinstance(schema, dict):
        return schema
    out = dict(schema)
    if isinstance(out.get("properties"), dict):
        out["properties"] = {k: _strict(v) for k, v in out["properties"].items()}
    if "items" in out:
        out["items"] = _strict(out["items"])
    if out.get("type") == "object":
        out["additionalProperties"] = False
    return out


def _extract(response: Any, output_format: bool) -> tuple[dict[str, Any] | None, str]:
    if output_format:
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        if not text:
            return None, "model returned no text block"
        try:
            return json.loads(text), ""
        except json.JSONDecodeError as exc:
            return None, f"response was not valid JSON: {exc}"
    result = next((b.input for b in response.content if b.type == "tool_use"), None)
    if result is None:
        return None, "model returned no tool_use block"
    return result, ""


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


def cache_key(
    name: str,
    system: str,
    user: str,
    schema: dict[str, Any],
    model: str | None = None,
    temperature: float | None = None,
    cache_salt: str = "",
) -> str:
    """Content-addressed key for one call.

    temperature and cache_salt are only folded in when set, so keys recorded before those
    parameters existed still resolve.
    """
    payload: dict[str, Any] = {
        "name": name,
        "model": model or MODEL,
        "system": system,
        "user": user,
        "schema": schema,
    }
    if temperature is not None:
        payload["temperature"] = temperature
    if cache_salt:
        payload["cache_salt"] = cache_salt
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return f"{name}-{digest[:16]}"


async def call(**kwargs: Any) -> dict[str, Any]:
    """Run one Claude call whose answer is forced through a tool schema.

    Forcing tool_choice means the model must return an object matching input_schema,
    which is far more reliable than parsing JSON out of prose.
    """
    result, _ = await call_with_meta(**kwargs)
    return result


async def call_with_meta(
    *,
    name: str,
    system: str,
    user: str,
    tool_name: str,
    tool_description: str,
    input_schema: dict[str, Any],
    max_tokens: int = 8000,
    model: str | None = None,
    temperature: float | None = None,
    cache_salt: str = "",
    cache_dir: Path | None = None,
    output_format: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """As call(), but also returns provenance the eval harness needs to record.

    model, temperature and cache_salt all default to the app's behaviour. cache_salt exists
    so repeated sampling of an identical prompt does not collapse onto one cached response.

    output_format switches from forced tool use to a json_schema output config, for models
    that reject tool_choice type "tool". The app never sets it.
    """
    model = model or MODEL
    key = cache_key(name, system, user, input_schema, model, temperature, cache_salt)
    prompt_hash = hashlib.sha256(f"{system}\n{user}".encode()).hexdigest()[:16]
    meta: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "cache_key": key,
        "prompt_hash": prompt_hash,
        "cached": False,
        "raw_response": None,
        "usage": None,
    }

    if mock_enabled():
        hit = fixtures().get(key)
        if hit is None:
            raise MockMiss(
                f"No fixture for {key}. Run once without MOCK=1 to record it, "
                f"then regenerate fixtures with `python record_fixtures.py`."
            )
        return hit, {**meta, "cached": True}

    directory = cache_dir or CACHE_DIR
    cache_file = directory / f"{key}.json"
    meta_file = directory / f"{key}.meta.json"
    try:
        if cache_file.exists():
            cached_meta = json.loads(meta_file.read_text()) if meta_file.exists() else {}
            return json.loads(cache_file.read_text()), {**meta, **cached_meta, "cached": True}
    except OSError:
        pass

    nudge = (
        "\n\nIMPORTANT: return a real JSON object matching the schema. Array fields must "
        "be actual arrays of objects, never a string containing JSON."
    )

    extra: dict[str, Any] = {} if temperature is None else {"temperature": temperature}
    if output_format:
        extra["output_config"] = {
            "format": {"type": "json_schema", "schema": _strict(input_schema)}
        }
    else:
        extra["tools"] = [
            {
                "name": tool_name,
                "description": tool_description,
                "input_schema": input_schema,
            }
        ]
        extra["tool_choice"] = {"type": "tool", "name": tool_name}

    last_error = ""
    # httpx read timeout resets whenever any byte arrives, so a trickle of thinking
    # tokens can hold a slot forever. This wall-clock cap cannot be reset that way.
    wall_clock = float(os.environ.get("ANTHROPIC_CALL_TIMEOUT", "120"))
    for attempt in range(2):
        try:
            response = await asyncio.wait_for(
                client().messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user + (nudge if attempt else "")}],
                    **extra,
                ),
                timeout=wall_clock,
            )
        except asyncio.TimeoutError:
            last_error = f"request exceeded {wall_clock:.0f}s wall-clock timeout"
            continue

        result, last_error = _extract(response, output_format)
        if result is None:
            continue

        result = _coerce(result, input_schema)
        if not _valid(result, input_schema):
            last_error = f"response did not match schema (keys: {sorted(result)})"
            continue

        meta["raw_response"] = [block.model_dump(mode="json") for block in response.content]
        meta["usage"] = response.usage.model_dump(mode="json")
        meta["stop_reason"] = response.stop_reason

        # Only cache once the shape is known good, so a bad response can't poison the run.
        # Meta goes in a sidecar to keep the primary file format unchanged for MOCK replay.
        try:
            directory.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(result, indent=2))
            meta_file.write_text(json.dumps(meta, indent=2))
        except OSError:
            pass  # read-only filesystem: caching is an optimisation, not a requirement
        return result, meta

    raise RuntimeError(f"{name}: {last_error}")
