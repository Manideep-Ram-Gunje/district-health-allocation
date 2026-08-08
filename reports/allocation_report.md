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
| greedy_feasible     | equal_per_indicator |           25 |               11 |                 6 |                 91350 |                    3.1137e+07  |                       9 |                  4 |                   |
| naive_top25         | equal_per_indicator |           25 |                7 |                 3 |                101243 |                    4.42926e+07 |                       5 |                 12 |                   |
| optimal             | equal_per_indicator |           25 |                9 |                 6 |                103285 |                    3.87103e+07 |                       0 |                  4 |                   |
| unconstrained_bound | equal_per_indicator |           25 |                5 |                 4 |                109084 |                    5.14614e+07 |                       0 |                 13 |                   |

## The four scenarios, and why there are four

| Scenario | Feasible? | What it represents |
|---|---|---|
| `naive_top25` | no | Sort by the headline need index, take 25. What "just rank them" means in practice. |
| `unconstrained_bound` | no | Top 25 by the objective itself. The true ceiling — no feasible allocation can beat it. |
| `greedy_feasible` | yes | Rank order, honour the cap, patch the regions. The spreadsheet answer. |
| `optimal` | yes | The integer program, proven optimal by CBC. |

## What optimisation actually bought

- **Premium vs `greedy_feasible`: +13.07%.** Both are feasible; the ILP finds the better one. Greedy commits to each pick permanently in rank order and cannot look ahead, so it spends early picks in states where it later needs headroom, then patches regions by evicting whichever district happens to be weakest.
- **Premium vs `naive_top25`: +2.02%.** The optimal allocation beats the naive one *even though the naive one ignores every constraint*. This is the least intuitive number in the project and the most worth understanding — see below.
- **Price of equity: -5.32%** against the unconstrained ceiling. This is the honest cost of the state cap and the region floor: what you give up to get an allocation that can actually be executed.

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

| nfhs_state     | nfhs_district          | region     | terrain   |   need |   rural |   gain |
|:---------------|:-----------------------|:-----------|:----------|-------:|--------:|-------:|
| Bihar          | Araria                 | East       | plains    |  0.937 | 2634813 |   4687 |
| Jharkhand      | Deoghar                | East       | plains    |  0.919 | 1193682 |   4594 |
| Jharkhand      | Pakur                  | East       | plains    |  0.919 |  831651 |   4593 |
| Bihar          | Purnia                 | East       | plains    |  0.917 | 2914082 |   4583 |
| Bihar          | Sitamarhi              | East       | plains    |  0.903 | 3225142 |   4517 |
| Bihar          | Saharsa                | East       | plains    |  0.898 | 1747032 |   4490 |
| Jharkhand      | Sahibganj              | East       | plains    |  0.895 |  985062 |   4474 |
| Assam          | Dhubri                 | North East | plains    |  0.873 |  861612 |   4363 |
| Uttar Pradesh  | Kanshiram Nagar        | Central    | plains    |  0.846 | 1133721 |   4231 |
| Uttar Pradesh  | Bahraich               | Central    | plains    |  0.846 | 3204487 |   4229 |
| Uttar Pradesh  | Bara Banki             | Central    | plains    |  0.836 | 2900069 |   4181 |
| Assam          | Darrang                | North East | plains    |  0.836 |  863571 |   4179 |
| Haryana        | Mewat                  | North      | plains    |  0.835 |  912763 |   4176 |
| Uttar Pradesh  | Fatehpur               | Central    | plains    |  0.832 | 2311229 |   4160 |
| Jharkhand      | Godda                  | East       | plains    |  0.827 | 1243490 |   4134 |
| Assam          | Bongaigaon             | North East | plains    |  0.824 |  609844 |   4120 |
| Assam          | Biswanath              | North East | plains    |  0.796 |  848741 |   3981 |
| Madhya Pradesh | Sheopur                | Central    | plains    |  0.793 |  585080 |   3965 |
| Madhya Pradesh | Panna                  | Central    | plains    |  0.772 |  903304 |   3861 |
| Madhya Pradesh | Chhatarpur             | Central    | plains    |  0.767 | 1406664 |   3836 |
| Chhattisgarh   | Korba                  | Central    | plains    |  0.754 |  749398 |   3771 |
| Madhya Pradesh | Rewa                   | Central    | plains    |  0.751 | 2003727 |   3757 |
| Maharashtra    | Jalgaon                | West       | plains    |  0.724 | 2879118 |   3621 |
| Maharashtra    | Parbhani               | West       | plains    |  0.72  | 1261248 |   3599 |
| Telangana      | Komaram Bheem Asifabad | South      | plains    |  0.637 |  500724 |   3185 |

### Distribution

| State | Facilities |
|---|---|
| Bihar | 4 |
| Jharkhand | 4 |
| Assam | 4 |
| Uttar Pradesh | 4 |
| Madhya Pradesh | 4 |
| Maharashtra | 2 |
| Haryana | 1 |
| Chhattisgarh | 1 |
| Telangana | 1 |

| Region | Facilities |
|---|---|
| Central | 9 |
| East | 8 |
| North | 1 |
| North East | 4 |
| South | 1 |
| West | 2 |

## Caveats

1. The objective rewards need-weighted population within one facility's catchment. It does not model travel time, existing facility locations (unavailable — see README), or construction cost.
2. Because the IPHS norm is *lower* in hilly and tribal areas (3,000 vs 5,000), a facility there delivers less raw coverage gain, which mildly disadvantages those districts in the objective. They compete on need instead. The optimal allocation contains 0 non-plains districts. A defensible alternative is to divide coverage gain by the norm so a facility is worth the same everywhere; that is a policy choice, not a technical one, and it is exposed as a toggle rather than hardcoded.
3. Weights are one defensible choice among many. Phase 4 quantifies how much of this list survives 10,000 alternative weightings.
