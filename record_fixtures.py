"""Bundle the on-disk cache into fixtures/sample_run.json for MOCK=1 replay.

Run a full exploration live once, then run this script. The fixture keys are the same
cache keys llm.call() computes, so replay is exact for that brief.
"""

import json

from llm import CACHE_DIR, FIXTURE_PATH

bundle = {
    path.stem: json.loads(path.read_text())
    for path in sorted(CACHE_DIR.glob("*.json"))
    if not path.name.endswith(".meta.json")  # provenance sidecars, not replayable responses
}

FIXTURE_PATH.parent.mkdir(exist_ok=True)
FIXTURE_PATH.write_text(json.dumps(bundle, indent=2))

by_stage: dict[str, int] = {}
for key in bundle:
    by_stage[key.rsplit("-", 1)[0]] = by_stage.get(key.rsplit("-", 1)[0], 0) + 1

print(f"Wrote {len(bundle)} responses to {FIXTURE_PATH.relative_to(FIXTURE_PATH.parent.parent)}")
for stage, count in sorted(by_stage.items()):
    print(f"  {stage}: {count}")
