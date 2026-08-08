# User Guide

For anyone using the **dashboard**. No coding required.

**Live app:** https://district-health-allocation-pohllxwaukamsafzd5dyh7.streamlit.app/

---

## What this tool answers

A State Health Society has budget for a fixed number of new rural Sub-Centres.
This tool decides **which districts should receive them**, given district-level
health outcome data and real-world constraints — and shows how much the answer
depends on the assumptions you choose.

It is an analytical exercise on public data. **It is not a policy
recommendation.**

---

## The controls (left panel)

Every control re-runs the actual optimiser. Nothing is precomputed.

### Weighting scheme

How much each of the seven health indicators counts.

| Scheme | What it means |
|---|---|
| `equal_per_indicator` | All seven indicators count equally. The default. |
| `equal_per_domain` | Maternal, child and nutrition each count a third. |
| `maternal_priority` | Weights maternal care most heavily. |
| `custom…` | Seven sliders. Set your own; they are rescaled to sum to 1. |

There is no correct answer here — that is the point. Compare schemes and see
which districts stay.

### Sub-Centres to allocate

The budget. Default 25.

### Maximum per state

No state may receive more than this. Prevents one state absorbing the
programme. Default 4.

Ranking districts by need alone puts **12 of 25 in Bihar**, which no funding
body would approve. This is the constraint that makes optimisation necessary.

### Minimum per region

Every zonal region must receive at least this many. Default 1.

### Objective

| Option | Meaning |
|---|---|
| **Terrain-neutral** | One facility counts as one facility anywhere. Default. |
| **Raw population coverage** | Values facilities by population reached. |

This choice matters more than it looks. Under *raw population coverage* the
tool selects **25 plains districts and zero hilly or tribal ones**, because the
IPHS norm serves fewer people in difficult terrain. Terrain-neutral treats
serving 3,000 people in hills as equivalent to 5,000 in plains — which is why
the standard sets a lower norm in the first place.

Switch between them and watch 9 of the 25 districts change.

---

## The tabs

### Allocation
The chosen districts. Read two columns together:

- **Need index** — 0 to 1, higher means worse health outcomes.
- **Stability** — how often this district survives when the weights are
  re-sampled. **100% means the choice does not depend on your weighting.**
  Lower means it does.

`Split district` marks districts created after 2011, whose population is shared
with siblings — treat their population figures as approximate.

### Map
Every district shaded by need. Darker is worse. 683 of 705 districts have a
matching polygon; the rest are absent from the map but present in the table.

### Versus baselines
Compares the optimiser against simpler strategies and shows which constraints
each one breaks. The `feasible` column is the one to read.

### Confidence
Results of 10,000 re-weightings. **Robust** districts are chosen almost always;
**contested** ones depend on what you decided to value. Both regimes are shown —
a realistic one and a deliberately harsh one.

### Methodology
How a district gets its score, plus the limitations. Worth reading before
quoting any number.

---

## Try this

Set **minimum per region to 5** and **maximum per state to 1**.

The tool refuses and explains why, instead of returning a plausible-looking
list. That is the solver proving no valid answer exists — a simpler tool would
have guessed.

---

## Reading the results honestly

**Do** say: *"11 of these 25 districts are chosen under any reasonable
weighting. The other 14 depend on assumptions."*

**Do not** say: *"These are the 25 districts that need facilities most."*

The tool measures **need**, not **unmet need** — there is no data on where
facilities already exist. Population is from Census 2011 against health data
from 2019–21. Full limitations are in the Methodology tab and the README.

---

## Running it yourself

```bash
git clone git@github.com:Manideep-Ram-Gunje/district-health-allocation.git
cd district-health-allocation
make venv
make app
```

Opens at `http://localhost:8501`. Works without a database — it falls back to
the bundled data snapshot and tells you on screen when it does.
