# Creative Space Navigator

Explore a large space of possible ad concepts without reading dozens of near-duplicate
generations. You give a product and a target audience; the app generates one shared pool of
concepts and shows two ways of navigating it side by side.

**Version 1 (simple)** groups the pool into 4-6 named creative themes, so you compare
directions instead of individual lines of copy.

**Version 2 (structured)** projects the same pool onto three semantic 2x2 maps built from
mostly-orthogonal creative dimensions. Pick one quadrant per map to compose a combined
creative direction, then generate fresh concepts constrained to that intersection.

Both panes support drill-down, so the comparison is apples-to-apples: "more in this theme"
versus "concepts at this precise intersection".

## Run it

```bash
uv run uvicorn app:app --port 8931
```

Open http://127.0.0.1:8931.

The API key is read from `.env` (gitignored) or the `ANTHROPIC_API_KEY` environment
variable. A full run costs four waves of calls and takes roughly 45-60 seconds cold;
everything is cached to `.cache/`, so re-running the same brief is instant.

### Offline / demo mode

```bash
MOCK=1 uv run uvicorn app:app --port 8931
```

Replays `fixtures/sample_run.json` with no network calls. Two briefs are bundled; enter one
of them exactly:

- `a reusable insulated water bottle` / `commuting office workers in their 30s`
  (includes both drill-downs)
- `a meal-kit subscription for one-pan dinners` / `parents of young kids who cook on weeknights`

Any other brief returns a clear "no fixture" error rather than silently hitting the API.

To record a new fixture, do a live run of the brief you want, then:

```bash
uv run python record_fixtures.py
```

## Deploying

The app is stateless: the browser holds the run and posts the relevant slices back with
each request, so it runs on serverless without a database.

```bash
npx vercel deploy --prod
```

Set two environment variables on the deployment:

| Variable | Purpose |
| --- | --- |
| `ANTHROPIC_API_KEY` | required |
| `APP_PASSWORD` | shared password for basic auth; the gate is skipped entirely when unset |

`vercel.json` routes every path to `api/index.py` and allows 60s per invocation, which
covers the ~26s corpus call. On Vercel the disk cache moves to `/tmp` and is best-effort
only, since each instance gets its own, so expect cold runs to cost full latency.

## How it works

```
product + audience
  -> propose 3 orthogonal 2x2 maps
  -> generate 24 concepts, told to span those maps
  -> [ cluster into themes ]  +  [ place every concept on every map ]   (parallel)
```

Dimensions are derived *before* the corpus on purpose. If you generate concepts first and
map them afterwards, most of them pile into one or two quadrants and the grids are useless.
Telling the generator to cover the space up front is what keeps all four quadrants
populated.

The themes call is deliberately never shown the axes, so Version 1 stays an honest naive
baseline rather than a version of Version 2 in disguise.

Placement is LLM-judged: Claude scores each concept from -1 to 1 on each axis and the
quadrant follows from the sign. There are no embeddings involved.

## Files

| File | Role |
| --- | --- |
| `app.py` | FastAPI routes, password gate, request validation, parallel orchestration |
| `api/index.py`, `vercel.json` | Serverless entrypoint and routing |
| `llm.py` | Anthropic wrapper, forced tool-use for structured output, disk cache, mock replay |
| `prompts.py` | The six prompts and their tool schemas |
| `static/` | Single page, vanilla JS, no build step |
| `record_fixtures.py` | Bundles `.cache/` into a replayable fixture |

## Known limits

Runs live in the browser tab and are lost on refresh. No export. Access control is a
single shared password, which is enough to stop a public URL burning the API key but is
not real multi-user auth. Quadrant balance depends on the model, and a genuinely rare
combination will legitimately show few or no concepts.
