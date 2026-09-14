# Semantic Control Eval — run `full-20260912T011614Z`

| Setting | Value |
|---|---|
| Profile | full |
| Generator | claude-sonnet-5, temperature unavailable (not sent: deprecated for this model family) |
| Judge | claude-fable-5-1, temperature unavailable (not sent: deprecated for this model family) |
| Judge prompt version | judge-v1 |
| Production prompt hash | 4582bbb1d9429580 |
| Git commit | e2f704245acf |
| Random seed | 20260911 |
| Contexts | 10 |

## Submission table

| Property | Measurement | Navigator | Baseline |
|---|---|---:|---:|
| Axis quality | Maps passing semantic-quality criteria | — | N/A |
| Steering | Joint quadrant adherence | — | — |
| Isolation | Target / non-target movement (1-5 scale) | — | N/A |
| 2-map composition | All 4 constraints satisfied | — | — |
| 3-map composition | All 6 constraints satisfied | — | — |
| Coverage | Quadrants represented per context | — | — |
| Placement fidelity | Main-flow quadrant matches blind judge | — | N/A |
| Judge validation | Human/judge within-one agreement | 87% | N/A |

## What the evidence supports


## Results

### Axis quality

— of maps met all four gating criteria against a predeclared target of 80%. Mean non-redundancy —/5, reported separately.

### Single-map steering

| Metric | Navigator | Naive prompt |
|---|---:|---:|
| Joint quadrant adherence | — | — |
| Per-axis adherence | — | — |
| X-axis adherence | — | — |
| Y-axis adherence | — | — |
| Ambiguous (judge scored 3) | — | — |

### Axis isolation

| Metric | Measured | Target |
|---|---:|---:|
| Target-axis movement | — | >= 2.00 |
| Non-target movement | — | <= 0.75 |
| Interventions meeting both | — | >= 75% |
| Median isolation ratio | — | descriptive |

### Composition degradation

| Composition | Constraints | Full adherence | Mean constraint adherence | Target |
|---|---:|---:|---:|---:|

### Coverage

| Arm | Quadrants represented | Balance (normalised entropy) |
|---|---:|---:|
| Flat diversity prompt | — | — |
| Structured (production corpus) | — | — |
| Structured (per-quadrant) | — | — |

### Judge validation

| Metric | Measured | Target |
|---|---:|---:|
| Mean absolute error | 0.47 | <= 0.75 |
| Within-one agreement | 87% | >= 85% |
| Exact agreement | 73% | — |
| Spearman rho | 0.81 | >= 0.60 |

## Failure analysis

No failures met the reporting criteria in this run.

---

Every figure above is populated from measured results. The benchmark is small: ten product domains resampled at the context level, so intervals are wide and no claim of universal statistical validity is intended.
