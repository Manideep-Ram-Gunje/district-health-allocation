# Recommendation Memo

**To:** State Health Society — Infrastructure Planning
**Subject:** Allocation of 25 sanctioned rural Sub-Centres
**Status:** Analytical exercise on public data. Not a policy recommendation.

---

## Recommendation

Allocate the 25 sanctioned Sub-Centres across **11 states and all 6 zonal
regions**, weighted toward districts in the lowest decile of maternal, child and
nutritional health outcomes. The full list is attached; the eleven districts
below are recommended **without qualification**, because they are selected under
every plausible weighting of the underlying indicators.

| District | State | Region | Terrain | Need index |
|---|---|---|---|---|
| Araria | Bihar | East | plains | 0.937 |
| Deoghar | Jharkhand | East | plains | 0.919 |
| Pakur | Jharkhand | East | plains | 0.919 |
| Purnia | Bihar | East | plains | 0.917 |
| Sahibganj | Jharkhand | East | plains | 0.895 |
| Bastar | Chhattisgarh | Central | tribal | 0.881 |
| Dhubri | Assam | North East | plains | 0.873 |
| West Jaintia Hills | Meghalaya | North East | hilly | 0.867 |
| Unakoti | Tripura | North East | hilly | 0.867 |
| North Garo Hills | Meghalaya | North East | hilly | 0.860 |
| Mewat | Haryana | North | plains | 0.835 |

The remaining 14 districts are **contested**: they are defensible selections,
but their inclusion depends on how the seven health indicators are weighted
relative to one another. They should be treated as a shortlist for judgement,
not as a settled answer.

## Basis

Each of 696 eligible rural districts was scored on seven NFHS-5 (2019–21)
indicators spanning maternal care, child immunisation and nutrition. Indicators
were direction-normalised, converted to national percentile ranks so that no
single indicator could dominate through having a wider spread, and combined
under a documented weight vector.

The allocation was then solved as an integer program maximising need-weighted
coverage, subject to a maximum of 4 facilities per state and a minimum of 1 per
region.

## Why the constraints matter

Ranking districts by need and taking the top 25 places **12 of them in Bihar**
and reaches only **3 of 6 regions**. That allocation is not merely politically
difficult; it would not survive review. The constrained allocation gives up
**3.15%** of theoretical coverage to reach every region with no state taking
more than four facilities.

That 3.15% is the measurable price of an executable programme.

## Confidence

The weighting of the seven indicators is a value judgement, not a finding. To
test how much the answer depends on it, the index was recomputed under 10,000
alternative weight vectors and the full allocation re-solved 200 times.

- **11 of 25 districts are robust** — selected in over 95% of runs under
  plausible disagreement about the weights.
- **14 are contested** — selected between 5% and 95% of the time.
- **0 are excluded**, meaning the optimiser never selects a district that
  cannot be re-selected when the weights move.

Under an adversarial stress test — weightings so lopsided no committee would
propose them — only 2 remain robust. Both figures are reported.

## What this analysis cannot tell you

**It measures need, not unmet need.** District-level counts of existing
Sub-Centres are not published in machine readable form. Substituting the
norm-implied supply that the methodology allows makes the adjustment cancel
algebraically, leaving a score that appears to account for existing
infrastructure but does not. No supply-adjusted figure is therefore quoted.

Population comes from Census 2011 against health outcomes from 2019–21 — a
decade apart, with no projection. 118 districts created after 2011 share a
parent district's population, divided equally among siblings.

Before acting on any district in this list, its existing facility count should
be verified from state records.

---

*Full methodology, assumptions and failure analysis: `README.md` and
`docs/build-log.md`. Every figure here regenerates with `make pipeline`.*
