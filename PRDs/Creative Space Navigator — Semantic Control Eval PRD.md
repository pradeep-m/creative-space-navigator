# Creative Space Navigator — Semantic Control Eval PRD

## 1. Purpose

Build an offline evaluation harness that determines whether Creative Space Navigator’s semantic structure provides a **real, measurable control surface over Claude generation**, rather than merely presenting ordinary generation behind themes, 2×2s, and repeated “Generate” actions.

The eval operates directly against the **same production prompt-building functions used by Creative Space Navigator**, but does not exercise or evaluate the UI.

The central question is:

> When a user selects regions of model-generated semantic space, does the resulting generation predictably move into those regions, preserve unrelated selected dimensions, and compose multiple dimensions successfully?

A secondary question is:

> Does structured exploration provide better systematic coverage of the creative space than asking Claude to generate a flat list of diverse concepts?

The eval is intentionally allowed to falsify the product hypothesis.

---

# 2. Claims Under Test

The eval separates five claims that should not be conflated.

### H1 — Semantic axes are meaningful

The product generates dimensions that are relevant, distinct, understandable, and useful for the supplied product × audience context.

Example:

- Pain relief ↔ Aspiration
- Rational ↔ Emotional

These should be meaningfully different dimensions rather than arbitrary or redundant labels.

### H2 — Quadrant selection steers generation

If the user selects:

- Aspiration
- Emotional

generated concepts should independently score toward both **Aspiration** and **Emotional**.

This is the basic **steering/adherence** property.

### H3 — Individual dimensions can be manipulated approximately independently

If the system changes:

- Emotional → Rational

while preserving:

- Aspirational

the output should move substantially on the first dimension while moving relatively little on the second.

This is the **isolation** property.

It is the strongest evidence that a 2×2 is actually functioning as a control surface rather than merely labeling generations after the fact.

### H4 — Controls compose across multiple 2×2s

If the user selects one quadrant from each of several 2×2s, the resulting concepts should simultaneously satisfy all selected poles.

For example:

Map A:
- Emotional
- Aspirational

Map B:
- Persona-led
- Transformation-oriented

The output should satisfy all four selected constraints.

This tests whether multidimensional composition actually works.

### H5 — Structured exploration improves systematic coverage

When given the same concept budget, deliberate quadrant exploration should cover more of the semantic space than:

> “Generate 12 diverse concepts.”

This tests whether the navigation abstraction contributes something beyond repeatedly requesting more generations.

---

# 3. Explicit Non-Goals

This eval does **not** measure:

- UI usability
- visual quality
- whether users understand the 2×2 interface
- marketing campaign performance
- CTR/CVR
- whether generated copy is objectively “good marketing”
- product-market fit
- whether users prefer the Navigator to ChatGPT
- latency or frontend performance

Founder/user sessions address some of these separately.

The automated eval is specifically about the **semantic representation and control properties of the generation pipeline**.

---

# 4. System Under Test

## 4.1 Production integration

The eval MUST use the same prompt-building functions as the actual Creative Space Navigator application.

Do not reproduce production prompts in the eval code.

The eval should expose a thin adapter around production code.

Conceptually:

```python
class NavigatorAdapter:
    def generate_maps(
        self,
        context: ProductAudienceContext
    ) -> list[SemanticMap]:
        ...

    def generate_concepts(
        self,
        context: ProductAudienceContext,
        selections: list[QuadrantSelection],
        n: int
    ) -> list[Concept]:
        ...
```

Production prompt logic remains the single source of truth.

Any future changes to production prompts should automatically alter eval behavior.

## 4.2 Generator model

Use the same Claude model currently used by the production application.

Configured via:

```text
GENERATOR_MODEL
```

The specific model ID must be persisted with every generation.

## 4.3 Judge model

Use:

```text
JUDGE_MODEL=Fable 5.1
JUDGE_TEMPERATURE=0
```

The exact configured API model identifier must be saved in result metadata.

The judge must never receive the selected quadrant when performing axis-position judgments.

---

# 5. Fixed Benchmark Dataset

Create:

```text
evals/fixtures/contexts.json
```

with ten fixed product × target-audience contexts.

Do not dynamically generate benchmark contexts during a run.

Initial benchmark:

| ID | Product | Target audience |
|---|---|---|
| b2b_ops | Cross-team organizational update / operating-record product | Chiefs of Staff / BizOps leaders |
| budgeting | Consumer budgeting app | Young professionals building financial habits |
| running | Premium running shoe | Recreational runners |
| security | Enterprise cybersecurity platform | CISOs |
| tutoring | Online tutoring platform | Parents of school-age children |
| hotel | Luxury resort | Affluent leisure travelers |
| meal_delivery | Meal-delivery service | Busy families |
| observability | Developer observability platform | Platform / infrastructure engineers |
| dating | Dating app | Single working professionals |
| nonprofit | Charitable fundraising campaign | Prospective individual donors |

Each fixture contains:

```json
{
  "id": "b2b_ops",
  "product": "...",
  "target_audience": "...",
  "additional_context": null
}
```

These ten fixtures are version-controlled and never silently edited between benchmark runs.

---

# 6. Canonical Data Model

## SemanticMap

```json
{
  "map_id": "map_01",
  "x_axis": {
    "negative": "Pain relief",
    "positive": "Aspiration",
    "description": "..."
  },
  "y_axis": {
    "negative": "Rational",
    "positive": "Emotional",
    "description": "..."
  }
}
```

## QuadrantSelection

```json
{
  "map_id": "map_01",
  "x_pole": "positive",
  "y_pole": "positive"
}
```

A user may select only one quadrant from a given 2×2.

A generation may contain selections from several different 2×2s.

## Concept

Store at minimum:

```json
{
  "concept_id": "...",
  "text": "...",
  "generation_model": "...",
  "prompt_version": "...",
  "raw_response": "..."
}
```

---

# 7. Reproducibility

Every experiment record must contain:

```text
run_id
timestamp
git_commit
context_id
generator_model
judge_model
generator_temperature
judge_temperature
production_prompt_version/hash
random_seed
map_id(s)
selected quadrant(s)
experiment_type
baseline_type
generation repetition
```

Use deterministic random seeds for:

- selecting maps
- selecting quadrants
- choosing isolation interventions
- constructing human-calibration samples

Where the model API itself cannot guarantee deterministic generation, record all model parameters and raw outputs.

---

# 8. Eval 1 — Semantic Axis Quality

## Objective

Determine whether the Navigator is generating useful semantic controls before testing whether concepts adhere to them.

## Dataset

For every benchmark context:

1. Call the production map-generation pipeline.
2. Retain the first **3 generated 2×2 maps**.

Total:

```text
10 contexts × 3 maps = 30 semantic maps
60 individual axes
```

## Judge input

The judge receives:

- product description
- target audience
- both axes
- axis definitions

The judge does NOT receive downstream concepts.

## Judge dimensions

Score each 1–5.

### Relevance

Does this distinction meaningfully matter for this product and audience?

### Polarity

Do the two ends represent meaningfully distinguishable directions?

### Actionability

Would choosing opposite poles plausibly lead to materially different concepts?

### Axis distinctness

Do X and Y capture different semantic properties?

### Redundancy

Does this map substantially duplicate another generated map?

For redundancy:

```text
1 = highly redundant
5 = highly distinct
```

## Output schema

```json
{
  "relevance": 5,
  "polarity": 4,
  "actionability": 5,
  "axis_distinctness": 4,
  "non_redundancy": 4,
  "reason": "..."
}
```

## Predeclared target

A map is considered high quality if:

```text
relevance >= 4
polarity >= 4
actionability >= 4
axis_distinctness >= 4
```

Target:

```text
>= 80% of maps satisfy all four criteria
```

Non-redundancy is reported separately.

---

# 9. Eval 2 — Single-Map Steering / Quadrant Adherence

## Objective

Determine whether selecting a quadrant actually causes generations to occupy that region of semantic space.

## Sampling

For every benchmark context:

```text
3 semantic maps
× 2 randomly selected quadrants per map
× 3 generation repetitions
```

Total:

```text
180 Navigator generations
```

Quadrants are chosen deterministically from the run seed.

## Example

Map:

```text
X: Pain relief ←→ Aspiration
Y: Rational ←→ Emotional
```

Selected quadrant:

```text
Aspiration + Emotional
```

Generate concepts using the actual production conditioning pipeline.

## Blinded judging

The judge receives:

- product
- audience
- generated concept
- definition of X axis
- definition of Y axis

The judge does NOT receive:

- selected quadrant
- expected scores
- production prompt
- whether this came from Navigator or baseline

Judge each axis independently.

Example:

```json
{
  "x_score": 5,
  "y_score": 4,
  "x_reason": "...",
  "y_reason": "..."
}
```

Scale:

```text
1 = strongly negative pole
2 = somewhat negative pole
3 = balanced / ambiguous
4 = somewhat positive pole
5 = strongly positive pole
```

Normalize scores internally so the selected pole is always treated as the desired direction.

## Adherence definition

A selected pole adheres if:

```text
normalized score >= 4
```

A quadrant adheres only if:

```text
both selected poles adhere
```

## Metrics

Report:

```text
X-axis adherence
Y-axis adherence
per-axis adherence
joint quadrant adherence
average normalized target score
ambiguous rate (score == 3)
```

## Predeclared target

Primary:

```text
joint quadrant adherence >= 80%
```

Secondary:

```text
per-axis adherence >= 90%
```

---

# 10. Eval 3 — Naive Natural-Language Steering Baseline

## Objective

Determine whether Navigator's internal structured conditioning improves model control beyond simply telling Claude the desired attributes in ordinary language.

For every sample from Eval 2, construct a baseline prompt containing:

- product
- audience
- the selected semantic directions

but none of the Navigator's production control prompt.

Example:

```text
Generate a marketing concept for the following product and target
audience.

The concept should be:
- aspirational rather than focused on pain relief
- emotional rather than rational

Product: ...
Target audience: ...
```

Use:

- same generator model
- equivalent output requirements
- same number of repetitions

Total:

```text
180 naive-baseline generations
```

Judge them using exactly the same blinded judging pipeline as Eval 2.

## Metrics

Compare:

```text
Navigator joint adherence
Naive-prompt joint adherence

Navigator average target score
Naive-prompt average target score
```

Calculate:

```text
absolute percentage-point difference
bootstrap 95% confidence interval
```

## Interpretation

These results intentionally support several possible conclusions.

### Navigator <80% adherence

Evidence against reliable semantic control.

### Navigator >=80%, naive approximately equal

The semantic controls work, but there is no evidence that Navigator's prompt architecture makes Claude intrinsically more controllable than straightforward prompting.

Product value would then need to come primarily from:

- representation
- discovery
- interaction
- persistent structure
- human agency

### Navigator >=80% and >=10 percentage points better than naive

Evidence that the production conditioning system itself materially improves steering.

The submission must report whichever outcome occurs.

---

# 11. Eval 4 — Axis Isolation

## Objective

Determine whether a user can manipulate one semantic dimension without unintentionally changing another.

This is the most important test of whether the 2×2 behaves like a genuine control surface.

## Example

Original:

```text
Emotional + Aspirational
```

Intervention:

```text
Rational + Aspirational
```

Only one axis changes.

## Sampling

For each benchmark context:

- choose one valid map
- create two matched interventions:
  - flip X, preserve Y
  - flip Y, preserve X
- generate 2 repetitions for each condition

Approximately:

```text
10 contexts
× 2 intervention types
× 2 conditions
× 2 repetitions
= 80 generations
```

## Measurement

Judge every concept on both semantic axes.

For each matched intervention calculate:

### Target-axis movement

```text
abs(mean score_after - mean score_before)
```

### Non-target movement

```text
abs(mean preserved_axis_after - mean preserved_axis_before)
```

## Predeclared target

Across interventions:

```text
mean target-axis movement >= 2.0 points
mean non-target-axis movement <= 0.75 points
```

Also report:

```text
% interventions meeting both conditions
```

Target:

```text
>= 75%
```

## Derived metric

Optionally report:

```text
isolation_ratio =
target_axis_movement /
max(non_target_axis_movement, 0.25)
```

This is descriptive rather than pass/fail.

---

# 12. Eval 5 — Multi-Map Composition

## Objective

Test whether semantic constraints remain valid when users select one quadrant from several 2×2s simultaneously.

Because the production product supports this interaction, it must be evaluated separately rather than assuming single-map adherence generalizes.

## Conditions

### One-map composition

2 selected poles.

Already measured by steering eval.

### Two-map composition

Select one quadrant from each of 2 different maps.

Total semantic constraints:

```text
4
```

### Three-map composition

Select one quadrant from each of 3 maps.

Total semantic constraints:

```text
6
```

## Sampling

For every context:

```text
1 random two-map combination
1 random three-map combination
3 generation repetitions each
```

Total Navigator generations:

```text
60
```

Run matched naive natural-language baselines:

```text
60
```

## Judging

Judge each concept independently on every involved axis.

A concept has **full joint adherence** only when every selected pole scores >=4.

Also calculate partial adherence:

```text
constraints satisfied / constraints selected
```

## Metrics

Report:

| Composition | Constraints | Full adherence | Mean constraint adherence |
|---|---:|---:|---:|
| 1 map | 2 | — | — |
| 2 maps | 4 | — | — |
| 3 maps | 6 | — | — |

## Predeclared reference targets

These are engineering targets, not claims of statistical ground truth:

```text
1 map: >=80% full adherence
2 maps: >=70%
3 maps: >=60%
```

The primary scientific output is the **degradation curve**, not whether every level passes.

If performance collapses under additional maps, report that directly.

---

# 13. Eval 6 — Flat Exploration Baseline

## Objective

Test the alternative hypothesis:

> Why not just ask Claude to generate a dozen diverse ideas and let the user choose?

## Setup

Use the first generated semantic map for each benchmark context as the evaluation coordinate system.

### Flat condition

Prompt Claude:

```text
Generate 12 meaningfully diverse creative concepts for this product
and target audience. Avoid simple paraphrases and explore substantially
different directions.
```

Generate:

```text
12 concepts × 10 contexts = 120 concepts
```

### Structured condition

For the same map:

- generate 3 concepts in quadrant 1
- generate 3 in quadrant 2
- generate 3 in quadrant 3
- generate 3 in quadrant 4

Total:

```text
12 concepts × 10 contexts = 120 concepts
```

The total concept budget is therefore identical.

## Judging

Blindly score each concept on X and Y.

Assign quadrant using:

```text
score < 3 → negative
score > 3 → positive
score == 3 → ambiguous
```

Concepts with a 3 on either axis are marked ambiguous.

## Metrics

### Quadrant coverage

```text
number of quadrants containing >=1 concept / 4
```

### Balanced coverage

Compute normalized entropy over quadrant assignments:

```text
H(quadrant distribution) / log(4)
```

Range:

```text
0 = completely concentrated
1 = perfectly balanced
```

### Ambiguity rate

Percentage of concepts that cannot confidently be assigned to a quadrant.

## Interpretation

This eval does NOT establish that structured concepts are “better.”

It establishes whether deliberate navigation provides more predictable **coverage** than undirected diversity prompting.

---

# 14. Human Calibration of the LLM Judge

## Objective

Avoid relying blindly on Claude grading Claude.

## Sample size

Exactly:

```text
30 generated concepts
```

Draw using a fixed stratified sample:

```text
10 from steering
10 from isolation
5 from composition
5 from naive/flat baselines
```

The evaluator must be blind to:

- target quadrant
- experimental condition
- Navigator vs baseline
- judge model score

## Human task

For every applicable axis, manually provide a 1–5 score using exactly the same rubric as the automated judge.

Only after all 30 examples are scored should automated scores be revealed.

## Agreement metrics

Calculate:

```text
mean absolute error
exact agreement
within-one-point agreement
Spearman correlation
```

Reference targets:

```text
MAE <= 0.75
within-one-point agreement >= 85%
Spearman rho >= 0.60
```

If agreement is poor:

- automated numbers remain available;
- report the disagreement explicitly;
- do not present LLM-judge results as strongly validated measurements.

Do not retune the judge prompt after examining the human scores unless the entire benchmark is rerun and labeled as a new eval version.

---

# 15. Judge Prompt Design

All judge outputs MUST use structured JSON.

The judge should be instructed that:

- neither pole is intrinsically superior;
- score 3 is appropriate for ambiguous or genuinely balanced concepts;
- marketing quality is irrelevant;
- factual correctness is irrelevant unless needed to interpret the concept;
- it should score only the semantic property requested;
- it should not infer the intended answer;
- scores should reflect the concept itself, not whether the judge personally likes it.

Example output:

```json
{
  "axis_scores": [
    {
      "axis_id": "x",
      "score": 4,
      "reason": "The concept emphasizes..."
    },
    {
      "axis_id": "y",
      "score": 2,
      "reason": "The framing relies primarily on..."
    }
  ]
}
```

Reasons are retained for failure analysis but not included in primary quantitative metrics.

---

# 16. Blinding Requirements

The judging layer must not receive:

```text
selected quadrant
desired pole
expected score
experiment type
Navigator vs baseline label
production prompt
```

It receives only:

```text
product
target audience
concept
semantic axis definitions
```

This requirement should be enforced at the code/API boundary rather than relying on prompt wording.

---

# 17. Caching

Every API result must be cached.

Directory structure:

```text
evals/
  cache/
    maps/
    generations/
    judgments/
```

Cache keys should include:

```text
model
prompt hash
generation parameters
eval version
```

Running the judge again must not regenerate concepts.

Changing judge prompts must not regenerate generator outputs.

---

# 18. Suggested Repository Structure

```text
evals/
  README.md

  config.py

  fixtures/
    contexts.json

  adapters/
    navigator.py
    generator.py
    judge.py

  baselines/
    naive_steering.py
    flat_generation.py

  suites/
    axis_quality.py
    steering.py
    isolation.py
    composition.py
    coverage.py
    human_calibration.py

  schemas/
    context.py
    semantic_map.py
    generation.py
    judgment.py
    result.py

  metrics/
    adherence.py
    isolation.py
    coverage.py
    agreement.py
    bootstrap.py

  reporting/
    aggregate.py
    markdown.py

  cache/

  outputs/
```

---

# 19. CLI

Support running the entire benchmark:

```bash
python -m evals.run --suite all --profile full
```

Individual suites:

```bash
python -m evals.run --suite axis_quality
python -m evals.run --suite steering
python -m evals.run --suite isolation
python -m evals.run --suite composition
python -m evals.run --suite coverage
```

Add:

```bash
python -m evals.run --suite all --profile smoke
```

Smoke profile should use:

```text
2 contexts
1 map/context
1 sampled condition
1 generation/condition
```

for development only.

Smoke results must never be included in the final benchmark report.

---

# 20. Output Artifacts

Every full benchmark run produces:

```text
outputs/<run_id>/
    config.json
    maps.jsonl
    generations.jsonl
    judgments.jsonl
    results.jsonl
    summary.json
    summary.csv
    report.md
```

## summary.json

Contains machine-readable metrics.

Example:

```json
{
  "axis_quality": {
    "high_quality_rate": 0.87
  },
  "steering": {
    "x_adherence": 0.93,
    "y_adherence": 0.91,
    "joint_adherence": 0.86
  },
  "naive_baseline": {
    "joint_adherence": 0.74
  },
  "isolation": {
    "target_movement": 2.5,
    "non_target_movement": 0.55
  },
  "composition": {
    "one_map": 0.86,
    "two_maps": 0.73,
    "three_maps": 0.58
  },
  "coverage": {
    "navigator_coverage": 1.0,
    "flat_coverage": 0.7
  }
}
```

Values above are examples only.

---

# 21. Statistical Reporting

For key proportions and differences, calculate bootstrap 95% confidence intervals.

Required:

```text
single-map joint adherence
Navigator-vs-naive adherence difference
2-map composition adherence
3-map composition adherence
flat-vs-structured coverage difference
```

Use benchmark context as the highest-level resampling unit where practical so hundreds of generations from one context do not masquerade as hundreds of independent product domains.

Do not report conventional p-values unless there is a clear reason.

The benchmark is too small for claims of universal statistical validity.

---

# 22. Failure Analysis

The report must not contain only aggregate scores.

Automatically identify and include examples from:

### Steering failure

Target quadrant missed.

### Isolation failure

Target dimension changes, but preserved dimension changes substantially too.

### Composition failure

Generation satisfies some selected axes while ignoring others.

### Axis-quality failure

Generated map is irrelevant, redundant, or semantically incoherent.

### Baseline win

Naive prompting performs as well as or better than Navigator.

Each failure should include:

```text
product/audience
semantic map
selection
generated concept
judge scores
brief judge rationale
```

At least three representative failure cases should appear in `report.md`.

---

# 23. Result Interpretation Framework

The benchmark should not output a binary:

```text
NAVIGATOR WORKS
```

Instead, the report should answer four separate questions.

## A. Are the generated controls meaningful?

Use axis-quality results.

## B. Can the controls steer Claude?

Use single-map adherence.

## C. Are they genuine dimensions rather than labels?

Use isolation.

## D. Does the structured representation add anything over ordinary prompting?

Use:

- naive steering comparison
- flat-generation coverage comparison

## E. Does multidimensional composition work?

Use the composition degradation curve.

---

# 24. Predeclared Interpretation Matrix

### Strong evidence for semantic control

Expected pattern:

```text
axis quality strong
single-map adherence >=80%
target-axis isolation >=2 points
non-target movement <=0.75
```

### Semantic control works, but prompt architecture adds little

Expected pattern:

```text
Navigator adherence strong
naive direct prompting roughly equally strong
```

Conclusion:

> Structured navigation may provide human-facing discovery and agency, but there is insufficient evidence that its internal prompt representation makes the model more steerable than ordinary prompting.

### Visualization / organization without reliable control

Expected pattern:

```text
axis quality good
adherence weak
or isolation weak
```

Conclusion:

> Generated maps may organize concepts intelligibly, but should not be described as a reliable semantic control surface.

### Multi-map composition unsupported

Expected pattern:

```text
1-map strong
2/3-map performance deteriorates sharply
```

Conclusion:

> Single-map semantic steering works, but explicit multidimensional composition is not sufficiently reliable.

This is an acceptable and useful negative finding.

---

# 25. Final Submission Table

The eval harness should automatically produce a compact table suitable for the Anthropic take-home write-up.

Example structure:

| Property | Measurement | Navigator | Baseline |
|---|---|---:|---:|
| Axis quality | Maps passing semantic-quality criteria | — | N/A |
| Steering | Joint quadrant adherence | — | — |
| Isolation | Target / non-target movement | — / — | N/A |
| 2-map composition | All 4 constraints satisfied | — | — |
| 3-map composition | All 6 constraints satisfied | — | — |
| Coverage | Quadrants represented | — | — |
| Judge validation | Human/judge within-1 agreement | — | N/A |

Do not hard-code claims such as “Navigator wins.”

Populate the table directly from measured results.

---

# 26. Acceptance Criteria for the Eval Harness

The implementation is complete when:

1. It imports the actual production prompt-building functions.
2. The full ten-context fixture is checked in.
3. All five model-behavior evals run end-to-end.
4. Both baselines run end-to-end.
5. All judgments are blinded.
6. Model outputs and judgments are cached separately.
7. Every result can be traced back to its exact context, map, selection, prompt version, and model.
8. Metrics are generated automatically.
9. Thirty examples can be exported for blind human scoring.
10. Human-vs-judge agreement is calculated once scores are provided.
11. `report.md` contains aggregate results plus representative failures.
12. A full run is reproducible from a single CLI command.

---

# 27. What We Should Be Able to Say After Running It

The eval exists to let the evidence determine which of these statements is justified.

Potential strong conclusion:

> Creative Space Navigator's generated semantic dimensions behave as meaningful control variables: selecting regions predictably steers Claude, single-axis interventions largely preserve unrelated dimensions, and deliberate navigation covers more of the output space than flat generation.

Potential narrower conclusion:

> The semantic organization is useful for human navigation, but Claude follows equivalent plain-language instructions equally well. The product's advantage appears to be interaction and cognition rather than a superior model-control mechanism.

Potential negative conclusion:

> The axes organize outputs visually, but they are not sufficiently isolated or composable to justify treating the 2×2s as a semantic control surface.

All three are valid outcomes.

The benchmark should make it impossible to quietly transform the third result into the first.