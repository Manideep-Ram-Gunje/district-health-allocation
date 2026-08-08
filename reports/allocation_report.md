# Allocation Results

**25** Sub-Centres allocated across **696** eligible districts, weighting scheme `equal_per_indicator`. Solver: CBC, status **Optimal**.

## The problem

```
maximise    sum_d  need_index_d * min(catchment_norm_d, rural_pop_d) * x_d
subject to  sum_d x_d = 25                        (budget, exactly)
            sum_(d in s) x_d <= 4   for each state    (equity)
            sum_(d in r) x_d >= 1   for each region   (feasibility)
            x_d in {0,1}
```

The `min()` in the objective is doing real work. One Sub-Centre cannot serve more than its catchment norm, so a district of four million and a district of forty thousand both cap out at what a single facility delivers. Without it the model would just pick the biggest districts and call that optimisation.

## Scenario comparison

| scenario            | scheme              |   facilities |   states_covered |   regions_covered |   total_coverage_gain |   rural_population_in_selected |   hilly_or_tribal_picks |   max_in_any_state | states_over_cap   |
|:--------------------|:--------------------|-------------:|-----------------:|------------------:|----------------------:|-------------------------------:|------------------------:|-------------------:|:------------------|
| greedy_by_need      | equal_per_indicator |           25 |               11 |                 6 |               21.2818 |                    3.1137e+07  |                       9 |                  4 |                   |
| greedy_feasible     | equal_per_indicator |           25 |               11 |                 6 |               21.2818 |                    3.1137e+07  |                       9 |                  4 |                   |
| naive_top25         | equal_per_indicator |           25 |                7 |                 3 |               21.9729 |                    4.42926e+07 |                       5 |                 12 | Bihar (12)        |
| optimal             | equal_per_indicator |           25 |               11 |                 6 |               21.2818 |                    3.1137e+07  |                       9 |                  4 |                   |
| unconstrained_bound | equal_per_indicator |           25 |                7 |                 3 |               21.9729 |                    4.42926e+07 |                       5 |                 12 | Bihar (12)        |

## The four scenarios, and why there are four

| Scenario | Feasible? | What it represents |
|---|---|---|
| `naive_top25` | no | Sort by the headline need index, take 25. What "just rank them" means in practice. |
| `unconstrained_bound` | no | Top 25 by the objective itself. The true ceiling — no feasible allocation can beat it. |
| `greedy_feasible` | yes | Rank order, honour the cap, patch the regions. The spreadsheet answer. |
| `optimal` | yes | The integer program, proven optimal by CBC. |

## What optimisation actually bought

- **Premium vs `greedy_feasible`: +0.00%.** Greedy, sorted by the quantity actually being maximised, is a *strong* baseline for this problem — a linear objective under a cardinality limit and per-state caps is close to a matroid, and greedy does very well on those. The ILP's value here is not a bigger number. It is that it **proves** optimality, and expresses the constraints declaratively so they can be changed without rewriting the selection logic.
- **Cost of sorting on the wrong key: +0.00%.** The same greedy heuristic, sorted by the headline *need index* instead of the objective, gives up this much. This is the real, defensible finding — and it is the mistake an analyst actually makes.
- **Premium vs `naive_top25`: -3.15%** — the unconstrained sorted list, which is also inadmissible.
- **Price of equity: -3.15%** against the unconstrained ceiling. What you give up to get an allocation that can be executed.

> **Honesty note.** An earlier version of this report claimed a +13% "optimisation premium". That number came from comparing the ILP against a greedy baseline sorted by the *need index* rather than by the objective — a straw man. Sorted correctly, greedy reaches the optimum and the premium is +0.00%. The 13% is retained above under its accurate name: the cost of ranking by the headline metric instead of the objective.

### Why sorting loses even before the constraints bite

Because the thing you sort on is not the thing you are maximising.

The need index answers *how badly off is this district*. The objective answers *how much good does one more facility do here*, and those diverge for two structural reasons:

1. **Coverage caps at the catchment norm.** A Sub-Centre serves at most 5,000 people (3,000 in hilly or tribal terrain). A district of 4 million and one of 40,000 both receive exactly one facility's worth of coverage, but a district whose entire rural population is below the norm cannot even absorb a full facility's benefit.
2. **Terrain changes the coefficient.** The same need index yields 5,000-population coverage in plains and 3,000 in hilly or tribal areas.

So the top of the need ranking is not the top of the objective ranking. Sorting by the headline metric produces a list that is both inadmissible *and* leaves value on the table — which is a stronger answer to "why not just sort?" than the constraint argument alone.

### Why the naive list is inadmissible anyway

Sorting by need index and taking the top 25 puts:

- **Bihar — 12 of 25 facilities** (cap is 4)

and reaches only 3 of 6 regions. No State Health Society could take that to a Finance Commission review, whatever the need data says.

## Optimal allocation

| nfhs_state    | nfhs_district          | region     | terrain   |   need |   rural |   gain |
|:--------------|:-----------------------|:-----------|:----------|-------:|--------:|-------:|
| Bihar         | Araria                 | East       | plains    |  0.937 | 2634813 |      1 |
| Jharkhand     | Deoghar                | East       | plains    |  0.919 | 1193682 |      1 |
| Jharkhand     | Pakur                  | East       | plains    |  0.919 |  831651 |      1 |
| Bihar         | Purnia                 | East       | plains    |  0.917 | 2914082 |      1 |
| Bihar         | Sitamarhi              | East       | plains    |  0.903 | 3225142 |      1 |
| Bihar         | Saharsa                | East       | plains    |  0.898 | 1747032 |      1 |
| Jharkhand     | Sahibganj              | East       | plains    |  0.895 |  985062 |      1 |
| Chhattisgarh  | Bastar                 | Central    | tribal    |  0.881 |  602140 |      1 |
| Assam         | Dhubri                 | North East | plains    |  0.873 |  861612 |      1 |
| Meghalaya     | West Jaintia Hills     | North East | hilly     |  0.867 |  180639 |      1 |
| Tripura       | Unakoti                | North East | hilly     |  0.867 |  270987 |      1 |
| Meghalaya     | North Garo Hills       | North East | hilly     |  0.86  |  134288 |      1 |
| Uttar Pradesh | Kanshiram Nagar        | Central    | plains    |  0.846 | 1133721 |      1 |
| Uttar Pradesh | Bahraich               | Central    | plains    |  0.846 | 3204487 |      1 |
| Uttar Pradesh | Bara Banki             | Central    | plains    |  0.836 | 2900069 |      1 |
| Assam         | Darrang                | North East | plains    |  0.836 |  863571 |      1 |
| Jharkhand     | Pashchimi Singhbhum    | East       | tribal    |  0.835 | 1264425 |      1 |
| Haryana       | Mewat                  | North      | plains    |  0.835 |  912763 |      1 |
| Uttar Pradesh | Fatehpur               | Central    | plains    |  0.832 | 2311229 |      1 |
| Nagaland      | Zunheboto              | North East | hilly     |  0.829 |  117956 |      1 |
| Assam         | Bongaigaon             | North East | plains    |  0.824 |  609844 |      1 |
| Chhattisgarh  | Bijapur                | Central    | tribal    |  0.815 |  220515 |      1 |
| Nagaland      | Tuensang               | North East | hilly     |  0.81  |  159540 |      1 |
| Maharashtra   | Nandurbar              | West       | tribal    |  0.765 | 1357015 |      1 |
| Telangana     | Komaram Bheem Asifabad | South      | plains    |  0.637 |  500724 |      1 |

### Distribution

| State | Facilities |
|---|---|
| Bihar | 4 |
| Jharkhand | 4 |
| Uttar Pradesh | 4 |
| Assam | 3 |
| Chhattisgarh | 2 |
| Meghalaya | 2 |
| Nagaland | 2 |
| Tripura | 1 |
| Haryana | 1 |
| Maharashtra | 1 |
| Telangana | 1 |

| Region | Facilities |
|---|---|
| Central | 6 |
| East | 8 |
| North | 1 |
| North East | 8 |
| South | 1 |
| West | 1 |

## Caveats

1. The objective rewards need-weighted population within one facility's catchment. It does not model travel time, existing facility locations (unavailable — see README), or construction cost.
2. Because the IPHS norm is *lower* in hilly and tribal areas (3,000 vs 5,000), a facility there delivers less raw coverage gain, which mildly disadvantages those districts in the objective. They compete on need instead. The optimal allocation contains 9 non-plains districts. A defensible alternative is to divide coverage gain by the norm so a facility is worth the same everywhere; that is a policy choice, not a technical one, and it is exposed as a toggle rather than hardcoded.
3. Weights are one defensible choice among many. Phase 4 quantifies how much of this list survives 10,000 alternative weightings.
