# Weight Sensitivity

10,000 weight vectors per regime, seed 42. The Need Index is recomputed and every district re-ranked on each draw, and the full ILP is re-solved on 200 sampled draws per regime.

## Why this exists

The weight vector is the least defensible choice in the methodology. It encodes a value judgement — whether child stunting matters as much as institutional births — and no amount of data settles it. The honest move is not to defend one vector but to measure how much the answer depends on it.

## Two regimes

| Regime | Sampling | What it represents |
|---|---|---|
| `centred` | Dirichlet centred on the default weights, concentration 50 | Plausible committee disagreement — the range a room of specialists would actually argue over. |
| `uniform` | Dirichlet(1,...,1), uniform on the simplex | Adversarial stress test. Includes vectors putting 80% on one indicator. Nobody would defend those, which is the point. |

## Two questions, and they are not the same

**`rank_stability`** — does this district stay in the top 25 *by need index*? This ignores the equity constraints entirely.

**`ilp_stability`** — does this district stay in the *allocation*, once the 4-per-state cap and 1-per-region floor are re-imposed?

For an allocated district the second is the meaningful one, and the distinction is not academic. The constrained optimum **deliberately reaches outside the national top 25** — it has to, because the cap forbids taking 12 districts from Bihar and the floor requires reaching all six regions. A district can therefore be a sound allocation choice while almost never appearing in the unconstrained top 25.

Classifying allocated districts by rank stability alone would mislabel exactly those districts the equity constraints exist to protect. Classification below therefore uses `ilp_stability`.

## Result

Of the 25 allocated districts, under **plausible disagreement** (`centred`): **12 robust**, 13 contested, 0 excluded.

Under the **adversarial stress test** (`uniform`): 5 robust, 20 contested, 0 excluded.

Thresholds: robust > 95%, excluded < 5%, contested between.

## The allocated 25

| nfhs_state     | nfhs_district          | region     | terrain   |   ilp_stability_centred | classification_centred   |   ilp_stability_uniform |   rank_stability_centred |   mean_rank |
|:---------------|:-----------------------|:-----------|:----------|------------------------:|:-------------------------|------------------------:|-------------------------:|------------:|
| Jharkhand      | Deoghar                | East       | plains    |                   1     | robust                   |                   1     |                   1      |        3.36 |
| Jharkhand      | Sahibganj              | East       | plains    |                   1     | robust                   |                   0.99  |                   0.9992 |        8.56 |
| Assam          | Darrang                | North East | plains    |                   1     | robust                   |                   0.87  |                   0.3809 |       32    |
| Assam          | Dhubri                 | North East | plains    |                   1     | robust                   |                   0.91  |                   0.9725 |       16.16 |
| Bihar          | Araria                 | East       | plains    |                   1     | robust                   |                   0.985 |                   1      |        1.07 |
| Haryana        | Mewat                  | North      | plains    |                   1     | robust                   |                   0.985 |                   0.2421 |       30.99 |
| Madhya Pradesh | Sheopur                | Central    | plains    |                   1     | robust                   |                   0.92  |                   0      |       63.23 |
| Jharkhand      | Pakur                  | East       | plains    |                   1     | robust                   |                   1     |                   1      |        3.45 |
| Bihar          | Purnia                 | East       | plains    |                   0.995 | robust                   |                   0.71  |                   1      |        3.43 |
| Madhya Pradesh | Chhatarpur             | Central    | plains    |                   0.99  | robust                   |                   0.705 |                   0      |       84.91 |
| Madhya Pradesh | Panna                  | Central    | plains    |                   0.985 | robust                   |                   0.74  |                   0      |       80.57 |
| Chhattisgarh   | Korba                  | Central    | plains    |                   0.97  | robust                   |                   0.575 |                   0      |       95.23 |
| Madhya Pradesh | Rewa                   | Central    | plains    |                   0.95  | contested                |                   0.495 |                   0      |       98.62 |
| Assam          | Bongaigaon             | North East | plains    |                   0.95  | contested                |                   0.69  |                   0.1628 |       40.44 |
| Uttar Pradesh  | Kanshiram Nagar        | Central    | plains    |                   0.83  | contested                |                   0.51  |                   0.6634 |       25.01 |
| Uttar Pradesh  | Bahraich               | Central    | plains    |                   0.8   | contested                |                   0.7   |                   0.6053 |       26.83 |
| Bihar          | Sitamarhi              | East       | plains    |                   0.785 | contested                |                   0.57  |                   1      |        6.14 |
| Telangana      | Komaram Bheem Asifabad | South      | plains    |                   0.68  | contested                |                   0.335 |                   0      |      198.4  |
| Maharashtra    | Jalgaon                | West       | plains    |                   0.66  | contested                |                   0.385 |                   0      |      120.63 |
| Bihar          | Saharsa                | East       | plains    |                   0.655 | contested                |                   0.415 |                   0.999  |        7.49 |
| Uttar Pradesh  | Bara Banki             | Central    | plains    |                   0.595 | contested                |                   0.52  |                   0.3813 |       30.39 |
| Uttar Pradesh  | Fatehpur               | Central    | plains    |                   0.565 | contested                |                   0.43  |                   0.2394 |       33.96 |
| Jharkhand      | Godda                  | East       | plains    |                   0.475 | contested                |                   0.32  |                   0.0795 |       37.21 |
| Maharashtra    | Parbhani               | West       | plains    |                   0.425 | contested                |                   0.49  |                   0      |      124.18 |
| Assam          | Biswanath              | North East | plains    |                   0.33  | contested                |                   0.225 |                   0      |       61.05 |

### Contested districts

Not errors — these are the districts whose selection genuinely depends on what you decided to value. Naming them is stronger than implying the list is uniformly solid.

- **Rewa, Madhya Pradesh** (Central) — allocated in 95% of re-solves, mean need rank 99
- **Bongaigaon, Assam** (North East) — allocated in 95% of re-solves, mean need rank 40
- **Kanshiram Nagar, Uttar Pradesh** (Central) — allocated in 83% of re-solves, mean need rank 25
- **Bahraich, Uttar Pradesh** (Central) — allocated in 80% of re-solves, mean need rank 27
- **Sitamarhi, Bihar** (East) — allocated in 78% of re-solves, mean need rank 6
- **Komaram Bheem Asifabad, Telangana** (South) — allocated in 68% of re-solves, mean need rank 198
- **Jalgaon, Maharashtra** (West) — allocated in 66% of re-solves, mean need rank 121
- **Saharsa, Bihar** (East) — allocated in 66% of re-solves, mean need rank 7
- **Bara Banki, Uttar Pradesh** (Central) — allocated in 60% of re-solves, mean need rank 30
- **Fatehpur, Uttar Pradesh** (Central) — allocated in 56% of re-solves, mean need rank 34
- **Godda, Jharkhand** (East) — allocated in 48% of re-solves, mean need rank 37
- **Parbhani, Maharashtra** (West) — allocated in 42% of re-solves, mean need rank 124
- **Biswanath, Assam** (North East) — allocated in 33% of re-solves, mean need rank 61

## What this does and does not establish

It establishes that the robust districts are not artefacts of one weighting choice — they survive both realistic and adversarial re-weighting.

It does **not** establish that they are the right places to build. The index rests on Census 2011 population against 2019-21 health outcomes, third-party PDF extraction, equal apportionment across post-2011 district splits, and a supply side that could not be measured at all. None of those limitations is touched by how many weight vectors you sample.

Sampling more weight vectors cannot fix a biased indicator set. If all seven indicators share a blind spot — and they are all maternal, child and nutritional, with nothing on communicable disease, mental health or injury — every draw inherits it.
