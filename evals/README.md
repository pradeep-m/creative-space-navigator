# Semantic Control Eval

Offline harness that tests whether the Navigator's generated 2x2s are a real control
surface over Claude generation, or an organising layer over ordinary generation. It runs
against the production prompt functions and never touches the UI.

The benchmark is allowed to falsify the product hypothesis, and the report is built so a
negative result cannot be quietly presented as a positive one.

## Run it

```bash
python -m evals.run --suite all --profile smoke --estimate-only   # print the call budget
python -m evals.run --suite all --profile smoke                   # development only
python -m evals.run --suite all --profile full                    # the benchmark
```

Individual suites:

```bash
python -m evals.run --suite steering
python -m evals.run --suite axis_quality --suite isolation
```

Suites always execute in dependency order regardless of the order you pass them: steering
leaves outcomes that the composition curve and the judge ablation read, and coverage caches
the corpus that placement fidelity reuses.

A full run is roughly 680 generation calls and 5,700 judge calls before cache hits. The CLI
prints the budget and asks for confirmation above 200 calls.

## What each suite answers

| Suite | Question |
|---|---|
| `axis_quality` | Are the generated dimensions relevant, polar, actionable and distinct? |
| `steering` | Does selecting a quadrant move generation into it, and does it beat plain prompting? |
| `isolation` | Can one axis be changed without dragging the other along? |
| `composition` | Do constraints survive selecting quadrants from 2 and 3 maps at once? |
| `coverage` | Does deliberate navigation cover the space better than "give me 12 diverse ideas"? |
| `placement_fidelity` | Do the main screen's own coordinates agree with an independent blind judge? |
| `judge_ablation` | How much of the judge's signal comes from the map rationale, and how stable is it? |
| `human_calibration` | Do the automated scores agree with a human using the same rubric? |

`placement_fidelity` is not in the PRD. It exists because production's primary flow does not
condition generation on a quadrant at all: it generates one unconditioned corpus and places
each concept afterwards. For that flow the 2x2 is post-hoc labelling, and the only property
that matters is whether those coordinates are trustworthy.

## Production integration

No prompt text is duplicated here. Every generation goes through `prompts.py` via a
`runner` hook that lets the harness capture provenance and override the model, cache
partition and repetition salt without production knowing about it. `config.production_prompt_hash()`
records a hash of `prompts.py` in every run, so results can never be silently compared
across different production prompts.

Three backward-compatible additions were made to the app:

- `llm.call_with_meta()` returns provenance alongside the result; `llm.call()` is unchanged.
- `prompts.build_intersection_constraints()` holds the constraint-building logic that used
  to live inside the `/api/refine/intersection` route, so the eval conditions generation
  through exactly the text the app uses.
- Every prompt stage accepts an optional `runner`.

Existing `.cache/` entries and `fixtures/sample_run.json` still resolve: cache keys only
change when the new parameters are actually set.

## Blinding

The judge never receives the selected quadrant, the desired pole, an expected score, the
experiment condition, the Navigator-vs-baseline label or any production prompt. This is
enforced structurally — `judge.score_axis()` has no parameter capable of carrying that
information — rather than by prompt wording. Normalisation toward the selected pole happens
in `metrics/adherence.py`, after the judge has committed to a score.

Each axis is scored in its own call. Scoring both axes in one response would let the second
score anchor on the first, which would directly contaminate the isolation measurement.

The judge does receive the map's `rationale` as the axis definition, because two-word pole
labels are underdetermined on their own. The `judge_ablation` suite quantifies how much
that grounding is worth by re-scoring the same concepts without it.

## Known deviations from the PRD

1. **`JUDGE_TEMPERATURE=0` is impossible.** These models reject the `temperature`
   parameter outright. The `judge_ablation` suite measures judge self-consistency across
   two identical passes instead, which puts a floor under how much of any observed
   difference is noise.
2. **Per-axis `description` does not exist in production.** Production emits one map-level
   `rationale` covering both axes; the eval carries the production shape.
3. **Redundancy needs the whole set.** The PRD asks whether a map duplicates another while
   showing the judge one map. A separate per-context call supplies all three maps.
4. **Isolation shares one base condition** between a context's two interventions rather than
   generating a separate control for each. Same matched-pair logic, one fewer generation,
   and both interventions are measured against an identical baseline.
5. **A grounded-conditioning arm was added.** Production drops the map rationale when it
   builds constraints; this arm feeds it back in at reduced repetitions to measure what
   that omission costs.
6. **Coverage corpus uses one map and the exact concept budget.** Scoring a 24-concept,
   three-map corpus on a single map would understate coverage. Placement fidelity still
   uses the production-faithful 24-concept corpus.

## Reproducibility

`outputs/<run_id>/config.json` records the run id, git commit, production prompt hash,
both model ids, the judge prompt version, the random seed and the full sampling profile.
Every generation and judgment carries its own cache key and prompt hash, so any number in
the report traces back to the exact context, map, selection, prompt version and model.

Sampling is seeded from `EVAL_SEED` (default 20260911). Because the API cannot guarantee
deterministic generation, repetitions vary genuinely; the seed fixes which maps, quadrants
and interventions get chosen, not what the model writes.

## Caching

`cache/maps/`, `cache/generations/` and `cache/judgments/` are separate tiers. Re-running
the judge never regenerates concepts, and changing a judge prompt (bump
`JUDGE_PROMPT_VERSION` in `config.py`) invalidates only judgments. Judgment keys are
content-addressed on the concept text plus the axis definition, so a concept scored by two
suites costs one call.

## Human calibration

`--suite human_calibration` writes `calibration_export.csv`: 30 stratified rows carrying the
concept, the axis definition and a blank score column, with the condition, the arm, the
target quadrant and the automated score all withheld. Score every row 1-5 using the same
rubric, save it as `calibration_scores.csv` in the same directory, then re-run:

```bash
python -m evals.run --suite human_calibration --run-id <run_id>
```

Do not open `calibration_key.json` until you are finished; it holds the judge's scores.

Per the PRD, do not retune the judge prompt after looking at the human scores unless the
whole benchmark is rerun under a new `EVAL_VERSION`.

## Outputs

```
outputs/<run_id>/
  config.json              run metadata and the call budget
  maps.jsonl               every generated 2x2
  generations.jsonl        every generation call, its concepts and its provenance
  judgments.jsonl          every axis score with its reason
  results.jsonl            per-suite derived records
  results_by_suite.json    metrics and failure cases per suite
  summary.json             machine-readable headline metrics
  summary.csv              flat metric table
  report.md                submission table, interpretation, failures
```

Smoke results are watermarked in `report.md` and must never be used as benchmark results.
