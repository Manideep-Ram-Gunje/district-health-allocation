# Composite Need Index

Default weighting scheme: **`equal_per_indicator`**. 696 districts scored.

## How the index is built

1. **Direction-normalise.** Four of seven indicators are good things (institutional births, ANC visits, skilled attendance, immunisation) and three are bad things (stunting, anaemia — and note stunting and anaemia are already need-positive). Good indicators are inverted as `100 - v` so that after this step higher always means greater need.
2. **Percentile-rank within the national distribution.** Raw values are not comparable across indicators — institutional births spans roughly 20-100 while stunting spans 6-60. Averaging raw values would let the widest-spread indicator dominate by accident. Percentile ranking puts every indicator on an identical 0-1 scale so the weight vector is the only thing that determines influence.
3. **Weighted mean over present indicators.** Weights are renormalised across the indicators a district actually has, so a district missing one is scored on the six it has. No cross-district imputation is performed anywhere.

## Indicators

| # | Indicator | Domain | Direction | Weight (default) |
|---|---|---|---|---|
| 33 | `anc_4plus_visits` | maternal | inverted | 0.1429 |
| 38 | `pnc_within_2_days` | maternal | inverted | 0.1429 |
| 42 | `institutional_births` | maternal | inverted | 0.1429 |
| 45 | `skilled_birth_attendance` | maternal | inverted | 0.1429 |
| 49 | `child_fully_vaccinated` | child | inverted | 0.1429 |
| 73 | `child_stunting` | nutrition | higher = worse | 0.1429 |
| 84 | `women_anaemia` | nutrition | higher = worse | 0.1429 |

## Distribution by scheme

| scheme              |   n |     lo |   mean |     hi |     sd |
|:--------------------|----:|-------:|-------:|-------:|-------:|
| equal_per_domain    | 696 | 0.047  | 0.4993 | 0.9253 | 0.1942 |
| equal_per_indicator | 696 | 0.0334 | 0.5003 | 0.9374 | 0.2045 |
| maternal_priority   | 696 | 0.0302 | 0.5001 | 0.9376 | 0.2126 |

## Sensitivity of the top 25 to the weighting scheme

Districts shared between the top 25 of each pair of schemes:

| sa                  | sb                  |   shared |
|:--------------------|:--------------------|---------:|
| equal_per_domain    | equal_per_indicator |       18 |
| equal_per_domain    | maternal_priority   |       17 |
| equal_per_indicator | maternal_priority   |       22 |

This is a first look at the question Phase 4 answers properly with 10,000 Dirichlet-sampled weight vectors. If the schemes disagreed wildly here, the index would be an artefact of the weights rather than of the data.

## Top 15 districts

|   rk | nfhs_state   | nfhs_district   | terrain   |   need |   rural |          at_risk |   ind |
|-----:|:-------------|:----------------|:----------|-------:|--------:|-----------------:|------:|
|    1 | Bihar        | Araria          | plains    |  0.937 | 2634813 |      2.46997e+06 |     7 |
|    2 | Jharkhand    | Deoghar         | plains    |  0.919 | 1193682 |      1.09667e+06 |     7 |
|    3 | Jharkhand    | Pakur           | plains    |  0.919 |  831651 | 763934           |     7 |
|    4 | Bihar        | Purnia          | plains    |  0.917 | 2914082 |      2.67134e+06 |     7 |
|    5 | Bihar        | Sitamarhi       | plains    |  0.903 | 3225142 |      2.91328e+06 |     7 |
|    6 | Bihar        | Saharsa         | plains    |  0.898 | 1747032 |      1.56867e+06 |     7 |
|    7 | Jharkhand    | Sahibganj       | plains    |  0.895 |  985062 | 881445           |     7 |
|    8 | Bihar        | Katihar         | plains    |  0.892 | 2780441 |      2.47884e+06 |     7 |
|    9 | Bihar        | Kishanganj      | plains    |  0.891 | 1525757 |      1.3593e+06  |     7 |
|   10 | Chhattisgarh | Bastar          | tribal    |  0.881 |  602140 | 530661           |     7 |
|   11 | Bihar        | Madhepura       | plains    |  0.879 | 1907613 |      1.67607e+06 |     7 |
|   12 | Bihar        | Bhagalpur       | plains    |  0.878 | 2430204 |      2.13355e+06 |     7 |
|   13 | Bihar        | Darbhanga       | plains    |  0.877 | 3562229 |      3.12535e+06 |     7 |
|   14 | Bihar        | Purba Champaran | plains    |  0.876 | 4682980 |      4.10255e+06 |     7 |
|   15 | Bihar        | Jamui           | plains    |  0.875 | 1608173 |      1.40795e+06 |     7 |

## Finding: the supply adjustment cancels

Spec section 6.3 defines underservice as population at risk divided by existing facilities, falling back to *norm-implied* facilities where counts are unavailable. District-level facility counts are unavailable (Phase 0), so the fallback applies. Substituting it:

```
underservice = (need x rural_pop) / (rural_pop / norm)
             =  need x norm
```

The population term cancels exactly. A 'supply-adjusted' underservice score would be nothing but the need index multiplied by a terrain constant — it would carry no information about existing infrastructure at all, while looking like it did.

`core.v_supply_degeneracy` demonstrates this on the real data: `ratio_check` equals 1.0 for every district (confirmed).

**Consequence.** No supply-adjusted score is shipped. Supply enters the model only through the terrain-specific IPHS catchment norm in `coverage_gain`. This is a real limitation of the available data, and volunteering it is stronger than shipping a formula that cancels.

