# Semantic Control Eval — run `full-20260912T011614Z`

| Setting | Value |
|---|---|
| Profile | full |
| Generator | claude-sonnet-5, temperature unavailable (not sent: deprecated for this model family) |
| Judge | claude-fable-5-1, temperature unavailable (not sent: deprecated for this model family) |
| Judge prompt version | judge-v1 |
| Production prompt hash | 4582bbb1d9429580 |
| Git commit | 2fb0197dd807 |
| Random seed | 20260911 |
| Contexts | 10 |

## Submission table

| Property | Measurement | Navigator | Baseline |
|---|---|---:|---:|
| Axis quality | Maps passing semantic-quality criteria | 27% | N/A |
| Steering | Joint quadrant adherence | 85% | 76% |
| Isolation | Target / non-target movement (1-5 scale) | 3.48 / 0.38 | N/A |
| 2-map composition | All 4 constraints satisfied | — | — |
| 3-map composition | All 6 constraints satisfied | — | — |
| Coverage | Quadrants represented per context | 90% | 70% |
| Placement fidelity | Main-flow quadrant matches blind judge | 77% | N/A |
| Judge validation | Human/judge within-one agreement | — | N/A |

## What the evidence supports

- **Controls meaningful** — Generated maps fall short of the predeclared quality bar.
- **Controls steer** — Selecting a quadrant reliably moves generation into it.
- **Genuine dimensions** — Single-axis interventions move the target axis while largely preserving the other: the 2x2 behaves as a control surface, not a label.
- **Beats ordinary prompting** — The semantic controls work, but Claude follows equivalent plain-language instructions about as well. Any product advantage lies in representation, discovery and interaction rather than a superior control mechanism.

## Results

### Axis quality

27% of maps met all four gating criteria (95% CI 13–43%) against a predeclared target of 80%. Mean non-redundancy 3.37/5, reported separately.

### Single-map steering

| Metric | Navigator | Naive prompt |
|---|---:|---:|
| Joint quadrant adherence | 85% (95% CI 78–92%) | 76% (95% CI 68–83%) |
| Per-axis adherence | 93% | — |
| X-axis adherence | 88% | — |
| Y-axis adherence | 98% | — |
| Ambiguous (judge scored 3) | 2% | — |

Difference: +9.1 percentage points (95% CI 3–15%), resampling contexts rather than concepts.

**Grounded-conditioning diagnostic.** Production builds its constraints from axis names and pole labels only, dropping the map rationale. Feeding the rationale back in moved joint adherence from 84% to 85% (+0.6 pp (95% CI -3–3%)).

### Axis isolation

| Metric | Measured | Target |
|---|---:|---:|
| Target-axis movement | 3.48 | >= 2.00 |
| Non-target movement | 0.38 | <= 0.75 |
| Interventions meeting both | 80% | >= 75% |
| Median isolation ratio | 12.67 | descriptive |

### Composition degradation

| Composition | Constraints | Full adherence | Mean constraint adherence | Target |
|---|---:|---:|---:|---:|

### Coverage

| Arm | Quadrants represented | Balance (normalised entropy) |
|---|---:|---:|
| Flat diversity prompt | 70% | 0.60 |
| Structured (production corpus) | 90% | 0.86 |
| Structured (per-quadrant) | 92% | — |

### Main-flow placement fidelity

The product's primary screen does not condition generation on a quadrant: it generates one unconditioned corpus and places each concept afterwards. Those placements agreed with an independent blind judge on 77% of concepts (95% CI 68–85%), with rank correlation 0.78 on X and 0.78 on Y.

### How much the axis definition carries

Re-scoring the same concepts with the map rationale withheld moved joint adherence from 84% to 86% (mean absolute score difference 0.16). A large gap means the pole labels are underdetermined without their rationale.

### Judge stability

These models reject the `temperature` parameter, so the PRD's judge `temperature=0` could not be set and determinism cannot be requested. Asking the judge the identical question twice instead gave mean absolute difference 0.08 across 60 re-draws, with 92% exact agreement. Differences smaller than that are within judge noise.

### Judge validation

Not yet performed. `calibration_export.csv` holds the blind sample; automated results in this report are unvalidated against human scoring until it is filled in.

## Failure analysis


**axis_quality** — `running`

- Product: A premium running shoe with a carbon plate and a high-rebound foam midsole
- Audience: Recreational runners training for their first half marathon
- Map: Motivation Style | X Emotional vs Rational: Emotional -> Rational | Y Identity vs Achievement: Identity-driven -> Achievement-driven
- Selection: n/a
- Concept: n/a
- Scores: relevance=4, polarity=4, actionability=3, axis_distinctness=2, non_redundancy=3
- Judge: Both tensions are pertinent to first-half-marathon runners: the 'am I a runner yet' identity question and the concrete finish-line goal are real levers, and a carbon-plate shoe supports both a spec-driven and a feeling-driven sell. Each axis has two viable ends. But the axes are heavily correlated: identity-driven stories are almost inherently emotional (the rationale itself describes the emotional pole as 'how the shoe makes them feel about themselves', which is identity), while achievement-driven stories default to rational proof points like pace, energy return and PRs. The off-diagonal cells (rational identity, emotional achievement) exist but are thin, so in practice the map collapses toward a single emotional-identity vs rational-achievement diagonal. Actionability is moderate: the Y axis genuinely changes the narrative centre, but the X axis is more a tonal register than a concept generator.

**axis_quality** — `observability`

- Product: A developer observability platform unifying logs, metrics and distributed traces with per-service cost attribution
- Audience: Platform and infrastructure engineers who own production reliability
- Map: Tone of Address | X Emotional vs Rational: Emotional -> Rational | Y Playful vs Serious: Playful -> Serious
- Selection: n/a
- Concept: n/a
- Scores: relevance=3, polarity=4, actionability=3, axis_distinctness=2, non_redundancy=3
- Judge: Both axes are legitimate tone variables and each pole is viable for this audience (3am-dread emotion vs architecture logic; gallows humor vs technical gravity), so polarity is sound. But the map is a generic tone grid that never touches what this product actually does (unified telemetry, per-service cost attribution), so it organises executions more than ideas—choosing poles yields different registers for possibly the same core concept. The bigger flaw is overlap: Playful is almost inherently Emotional and Serious skews Rational, leaving the Playful/Rational quadrant thin and making position on one axis a strong predictor of the other. Two of the four quadrants do most of the work, so it functions closer to a single spectrum than a true 2x2.

**axis_quality** — `b2b_ops`

- Product: A cross-team organizational update and operating-record product that keeps a searchable history of what every team decided, shipped and changed
- Audience: Chiefs of Staff and BizOps leaders at companies of 200-2000 people
- Map: Narrative Style | X Expository vs Persuasive: Explains the system -> Argues a point of view | Y Product-led vs Customer-led: Shows the product -> Shows the customer's world
- Selection: n/a
- Concept: n/a
- Scores: relevance=3, polarity=4, actionability=4, axis_distinctness=3, non_redundancy=5
- Judge: Both axes are legitimate craft choices for a B2B ops tool, but they are generic format dimensions that don't engage the specifics of institutional memory, cross-team visibility, or the Chief of Staff's role, so the map organises execution more than it explores what to say to this buyer. Polarity is sound: demo-style explanation and thesis-driven argument are both viable, as are tool-hero and people-hero framings. Opposite corners would yield genuinely different work (a mechanics walkthrough vs a manifesto set inside a BizOps leader's week). The main weakness is correlation between axes: 'explains the system' naturally leans product-led and 'argues a point of view' naturally leans customer-led, so two quadrants (expository/customer-led, persuasive/product-led) are thinner and positions partly predict each other.

**axis_quality** — `b2b_ops`

- Product: A cross-team organizational update and operating-record product that keeps a searchable history of what every team decided, shipped and changed
- Audience: Chiefs of Staff and BizOps leaders at companies of 200-2000 people
- Map: Operating Record Value | X Forward-looking vs Backward-looking: Prevents future misalignment -> Resolves past disputes | Y Visible Control vs Ambient Trust: Active dashboard, always watching -> Quiet system of record, rarely opened
- Selection: n/a
- Concept: n/a
- Scores: relevance=4, polarity=4, actionability=4, axis_distinctness=3, non_redundancy=4
- Judge: The X axis hits a genuine positioning fork for a system-of-record product: sell it as proactive coordination that stops drift or as the arbiter of 'who decided what' after the fact. Both are credible pains for Chiefs of Staff, though the backward-looking pole is a somewhat narrower, more defensive frame. The Y axis (active dashboard vs quiet infrastructure) is also a real choice and both ends are viable for this audience. Opposite quadrants would produce clearly different work: a forward-looking command-centre concept versus a 'the receipts are there when you need them' concept. The weakness is independence: backward-looking dispute resolution naturally pairs with 'rarely opened', and forward-looking prevention naturally pairs with active monitoring, so the off-diagonal quadrants (ambient prevention, actively-watched historical audit) are plausible but require more work to populate. Knowing X gives a moderate hint about Y.

**axis_quality** — `budgeting`

- Product: A consumer budgeting app that categorises spending automatically and nudges users toward savings goals
- Audience: Young professionals in their twenties building financial habits for the first time
- Map: Tone of Voice | X Emotional vs Rational appeal: Rational -> Emotional | Y Playful vs Serious register: Serious -> Playful
- Selection: n/a
- Concept: n/a
- Scores: relevance=4, polarity=4, actionability=3, axis_distinctness=3, non_redundancy=3
- Judge: Tone genuinely matters for a category where twenty-somethings often feel anxiety or shame about money, so whether an ad leads with feeling or logic and treats money lightly or gravely are real strategic choices; both ends of each axis are viable in fintech (serious-trust vs Monzo-style levity, data-led vs aspirational). However, these are execution registers rather than idea territories, so opposite poles yield different treatments more reliably than different concepts, and the axes lean on each other in practice: playful work tends toward emotional and serious toward rational, with the off-diagonal quadrants (witty-rational, heartfelt-serious) possible but less naturally populated.

**steering** — `hotel`

- Product: A luxury island resort with private villas, a spa and a reef-diving programme
- Audience: Affluent leisure travellers booking a once-a-year trip
- Map: Solitude vs Sensation | Social Framing
- Selection: wanted Shared Indulgence on Social Framing, Quiet Stillness on the other axis
- Concept: Two loungers. One horizon. No words needed. Share a private villa terrace with the person who matters most, where the only sound is the tide. This is a trip built for togetherness that never asks you to fill the silence.
- Scores: raw=1, toward selected pole=1/5
- Judge: The concept is built entirely around vanishing from the world with one partner on a private terrace in silence, which is exactly the 'vanish with a partner/family' pole of the definition; the togetherness is intimate and hidden, not a story-worthy spectacle to relive or share.

**steering** — `hotel`

- Product: A luxury island resort with private villas, a spa and a reef-diving programme
- Audience: Affluent leisure travellers booking a once-a-year trip
- Map: Solitude vs Sensation | Social Framing
- Selection: wanted Shared Indulgence on Social Framing, Quiet Stillness on the other axis
- Concept: Two chairs. One reef. All the silence you need. Share a private villa built for two, where the loudest sound is your partner turning a page beside you. The reef waits quietly offshore, for whenever you're ready to drift into it together.
- Scores: raw=1, toward selected pole=1/5
- Judge: The concept is explicitly about vanishing with a partner into silence and a private villa built for two; even the reef is framed as quiet and private ('drift into it together'), with no story-worthy spectacle or shareable sensation. It sits firmly at the Private Escape pole.

**steering** — `hotel`

- Product: A luxury island resort with private villas, a spa and a reef-diving programme
- Audience: Affluent leisure travellers booking a once-a-year trip
- Map: Solitude vs Sensation | Social Framing
- Selection: wanted Shared Indulgence on Social Framing, Quiet Stillness on the other axis
- Concept: A villa for two. A stillness only shared quiet can hold. Wake slowly, side by side, to nothing but the tide. The spa, the reef, the whole island moves at the pace of two people who no longer need to fill the silence.
- Scores: raw=1, toward selected pole=1/5
- Judge: The concept is built entirely around a couple vanishing into stillness and silence in a private villa, with no story-worthy spectacle or sharing with others; 'shared quiet' refers to the intimate pair, which sits squarely in the Private Escape pole.

**steering** — `b2b_ops`

- Product: A cross-team organizational update and operating-record product that keeps a searchable history of what every team decided, shipped and changed
- Audience: Chiefs of Staff and BizOps leaders at companies of 200-2000 people
- Map: Narrative Style | Expository vs Persuasive
- Selection: wanted Explains the system on Expository vs Persuasive, Shows the customer's world on the other axis
- Concept: Every Monday, someone asks 'wait, why did we decide that?' Across a 400-person company, three teams are usually mid-argument about a decision that was already made months ago. The record just doesn't exist anywhere anyone can find it.
- Scores: raw=4, toward selected pole=2/5
- Judge: The concept never demonstrates or explains how the product works; instead it builds a case through a problem-agitation narrative about teams re-arguing settled decisions, with people rather than the tool as the focus. It argues a point of view, though it stops short of an explicit hard-sell claim, so it sits at somewhat persuasive rather than strongly.

**steering** — `b2b_ops`

- Product: A cross-team organizational update and operating-record product that keeps a searchable history of what every team decided, shipped and changed
- Audience: Chiefs of Staff and BizOps leaders at companies of 200-2000 people
- Map: Narrative Style | Expository vs Persuasive
- Selection: wanted Explains the system on Expository vs Persuasive, Shows the customer's world on the other axis
- Concept: A new VP's first two weeks look the same everywhere Slack archaeology, a dozen pings to 'can someone catch me up', a doc that was last touched in Q1. That's how context actually gets transferred at most 500-2000 person companies today.
- Scores: raw=4, toward selected pole=2/5
- Judge: The concept never explains how the product works; instead it asserts a diagnosis of the status quo ('look the same everywhere', 'that's how context actually gets transferred') to build a case that the current way is broken. It argues a point of view through rhetorical scene-setting rather than demonstrating mechanics, though it stops short of an explicit hard-sell argument.

**isolation** — `tutoring`

- Product: An online tutoring platform matching students with vetted subject tutors for live weekly sessions
- Audience: Parents of school-age children who are worried about falling grades
- Map: Emotional Register | target Parent-Focused vs Child-Focused | preserved Anxiety vs Aspiration
- Selection: Child's Growth & Confidence -> Parent's Peace of Mind, holding Hope for Achievement
- Concept: Picture report card day without the dread. Weekly sessions with a vetted tutor mean you walk into every parent-teacher meeting knowing exactly where things stand — and liking what you hear. Book your family's tutor today and start expecting good news.
- Scores: target moved 4.00, preserved moved 2.00
- Judge: The concept opens by invoking parental dread and frames the payoff as relief from worry (anxiety end), but then pivots to painting a positive future of 'liking what you hear' and 'expecting good news' (aspiration end). It genuinely straddles both registers rather than committing to one.

**isolation** — `b2b_ops`

- Product: A cross-team organizational update and operating-record product that keeps a searchable history of what every team decided, shipped and changed
- Audience: Chiefs of Staff and BizOps leaders at companies of 200-2000 people
- Map: Operating Record Value | target Forward-looking vs Backward-looking | preserved Visible Control vs Ambient Trust
- Selection: Prevents future misalignment -> Resolves past disputes, holding Active dashboard, always watching
- Concept: Every 'That's not what we decided' — settled in one click. Pull up the exact decision, the date, the owner, and the thread that changed it. Your dashboard is always open, so the receipts are always ready.
- Scores: target moved 3.83, preserved moved 1.17
- Judge: The concept is built entirely around settling 'That's not what we decided' disputes after the fact by pulling up receipts—the exact decision, date, owner, and change thread—which is squarely the arbiter/resolves-past-disputes pole with no proactive drift-prevention framing.

---

Every figure above is populated from measured results. The benchmark is small: ten product domains resampled at the context level, so intervals are wide and no claim of universal statistical validity is intended.
