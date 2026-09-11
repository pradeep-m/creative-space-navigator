"""Run configuration: models, sampling profiles, seeds, paths.

Importing this module also loads .env via llm, so ANTHROPIC_API_KEY and any model
overrides are available to everything downstream.
"""

from __future__ import annotations

import hashlib
import os
import random
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import llm

ROOT = Path(__file__).parent
CACHE_ROOT = Path(os.environ.get("EVAL_CACHE_DIR") or ROOT / "cache")
OUTPUT_ROOT = Path(os.environ.get("EVAL_OUTPUT_DIR") or ROOT / "outputs")
FIXTURES_PATH = ROOT / "fixtures" / "contexts.json"

# Bump when a change should invalidate cached judgments; it is folded into judge cache keys.
EVAL_VERSION = "1"
JUDGE_PROMPT_VERSION = "judge-v1"

GENERATOR_MODEL = os.environ.get("GENERATOR_MODEL") or llm.MODEL
JUDGE_MODEL = os.environ.get("JUDGE_MODEL") or "claude-fable-5-1"

# These models reject `temperature` outright ("deprecated for this model"), so the PRD's
# JUDGE_TEMPERATURE=0 cannot be honoured and judge determinism cannot be requested. Left
# settable in case a later model restores it; when None, nothing is sent. The judge
# self-consistency check in the judge_ablation suite measures the resulting noise instead.
TEMPERATURE_NOTE = "not sent: deprecated for this model family"


def _optional_float(name: str) -> float | None:
    raw = os.environ.get(name)
    return float(raw) if raw else None


GENERATOR_TEMPERATURE = _optional_float("GENERATOR_TEMPERATURE")
JUDGE_TEMPERATURE = _optional_float("JUDGE_TEMPERATURE")

RANDOM_SEED = int(os.environ.get("EVAL_SEED", "20260911"))

MAX_CONCURRENCY = int(os.environ.get("EVAL_CONCURRENCY", "8"))

ALL_SUITES = [
    "axis_quality",
    "steering",
    "isolation",
    "composition",
    "coverage",
    "placement_fidelity",
    "judge_ablation",
]


@dataclass(frozen=True)
class Profile:
    """Everything that controls how much gets sampled."""

    name: str
    contexts: int
    maps_per_context: int
    quadrants_per_map: int
    steering_reps: int
    isolation_reps: int
    composition_reps: int
    concepts_per_generation: int
    coverage_budget: int  # must divide by 4 so the structured arm fills each quadrant
    ablation_concepts: int
    grounded_arm_reps: int
    placement_maps_per_context: int
    calibration_sample: int


FULL = Profile(
    name="full",
    contexts=10,
    maps_per_context=3,
    quadrants_per_map=2,
    steering_reps=3,
    isolation_reps=2,
    composition_reps=3,
    concepts_per_generation=3,
    coverage_budget=12,
    ablation_concepts=180,
    grounded_arm_reps=1,
    placement_maps_per_context=1,
    calibration_sample=30,
)

SMOKE = Profile(
    name="smoke",
    contexts=2,
    maps_per_context=3,  # one API call returns all three, so this costs nothing extra
    quadrants_per_map=1,
    steering_reps=1,
    isolation_reps=1,
    composition_reps=1,
    concepts_per_generation=2,
    coverage_budget=4,
    ablation_concepts=4,
    grounded_arm_reps=1,
    placement_maps_per_context=1,
    calibration_sample=4,
)

PROFILES = {p.name: p for p in (FULL, SMOKE)}


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT.parent,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def production_prompt_hash() -> str:
    """Hash of the production prompt module.

    Any edit to prompts.py changes this, so a benchmark run can never be silently compared
    against results produced by different production prompts.
    """
    source = (ROOT.parent / "prompts.py").read_bytes()
    return hashlib.sha256(source).hexdigest()[:16]


def derive_seed(*parts: object) -> int:
    payload = ":".join(str(p) for p in (RANDOM_SEED, *parts))
    return int(hashlib.sha256(payload.encode()).hexdigest()[:12], 16)


def rng(*parts: object) -> random.Random:
    """Deterministic generator keyed by whatever identifies the sampling decision."""
    return random.Random(derive_seed(*parts))


def run_metadata(run_id: str, profile: Profile, suites: list[str]) -> dict[str, object]:
    return {
        "run_id": run_id,
        "eval_version": EVAL_VERSION,
        "git_commit": git_commit(),
        "production_prompt_hash": production_prompt_hash(),
        "generator_model": GENERATOR_MODEL,
        "generator_temperature": GENERATOR_TEMPERATURE or TEMPERATURE_NOTE,
        "judge_model": JUDGE_MODEL,
        "judge_temperature": JUDGE_TEMPERATURE or TEMPERATURE_NOTE,
        "judge_prompt_version": JUDGE_PROMPT_VERSION,
        "random_seed": RANDOM_SEED,
        "profile": asdict(profile),
        "suites": suites,
    }
