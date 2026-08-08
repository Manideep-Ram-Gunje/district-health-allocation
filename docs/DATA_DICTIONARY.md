# Data Dictionary

Every table, column and derived quantity. Generated schema lives in `sql/`.

---

## Sources

| Key | File | Rows | Licence |
|---|---|---|---|
| `nfhs5_districts` | `nfhs5_districts.csv` | 73,319 | MIT |
| `census2011_districts` | `census2011_districts.csv` | 640 | GoI open data |
| `district_boundaries` | `india_districts_adm2.geojson` | 735 features | ODbL 1.0 |
| `state_boundaries` | `india_states_adm1.geojson` | 36 features | CC BY 2.5 IN |

Declared in `config/sources.yml` with pinned URLs. Checksums in
`data/raw/MANIFEST.json`.

**Not available:** district-level Rural Health Statistics (existing facility
counts). Recorded under `unavailable:` in `sources.yml` with what was attempted.
This is why the project measures need, not unmet need.

---

## `core.district` — 705 rows, one per NFHS-5 district

| Column | Type | Meaning |
|---|---|---|
| `district_id` | serial PK | Internal identifier |
| `nfhs_state` | text | State as spelled in NFHS-5 |
| `nfhs_district` | text | District as spelled in NFHS-5 |
| `region` | text | Zonal Council: North, Central, East, West, South, North East |
| `census_code` | integer | Census 2011 district code (1–640) |
| `census_state` | text | Matched Census state |
| `census_district` | text | Matched Census district |
| `match_tier` | text | `fuzzy`, `fuzzy_review`, `override:rename`, `override:child_of` |
| `match_score` | numeric | rapidfuzz `token_sort_ratio`, 0–100 |
| `is_apportioned` | boolean | True if this district shares a Census parent |
| `n_sharing_parent` | smallint | Number of siblings sharing the parent |
| `population_alloc` | bigint | Census population, divided equally if shared |
| `rural_share` | numeric | `Rural_Households / Households` |
| `rural_population` | bigint | `population_alloc × rural_share` — **derived** |
| `st_share` | numeric | Scheduled Tribe share of total population |
| `terrain` | text | `plains`, `hilly`, `tribal` (never `desert` — see below) |
| `catchment_norm` | integer | 5000 plains, 3000 hilly/tribal (IPHS 2022) |

**Derivations and their assumptions**

`rural_population` assumes equal mean household size rural vs urban. Rural
households are larger, so this **understates** rural population by about 1.1%
(824.2M derived vs 833.5M published) — conservative for this purpose.

`terrain` waterfall: hill state → `hilly`; else ST share ≥ 50% → `tribal`; else
`plains`. Desert is never assigned because identifying desert blocks needs
sub-district data. Both gaps under-apply the stricter 3,000 norm.

`population_alloc` divides a Census parent's population **equally** among
post-2011 children. Unbiased in aggregate, wrong district by district. 118
districts affected.

---

## `core.indicator` — 104 rows

| Column | Type | Meaning |
|---|---|---|
| `indicator_id` | smallint PK | NFHS-5 factsheet number, 1–104 |
| `indicator_key` | text | Short name; NULL if not in the index |
| `name_as_published` | text | Modal name string in the source |
| `domain` | text | `maternal`, `child`, `nutrition` |
| `higher_is_worse` | boolean | Direction |
| `in_index` | boolean | True for the 7 index members |
| `name_variants` | smallint | Distinct name strings seen; >1 means PDF noise |

Keyed on the **number**, not the name. Ten numbers carry more than one name
string from PDF extraction artefacts — including 49, which is in the index.

### The seven index indicators

| # | Key | Domain | Direction |
|---|---|---|---|
| 33 | `anc_4plus_visits` | maternal | inverted |
| 38 | `pnc_within_2_days` | maternal | inverted |
| 42 | `institutional_births` | maternal | inverted |
| 45 | `skilled_birth_attendance` | maternal | inverted |
| 49 | `child_fully_vaccinated` | child | inverted |
| 73 | `child_stunting` | nutrition | higher = worse |
| 84 | `women_anaemia` | nutrition | higher = worse |

---

## `core.district_indicator` — 73,319 rows

| Column | Type | Meaning |
|---|---|---|
| `district_id` | integer FK | |
| `indicator_id` | smallint FK | |
| `value_nfhs5` | numeric | NFHS-5 value; NULL = absent **or** suppressed |
| `value_nfhs4` | numeric | NFHS-4 value, for reference |
| `flag_nfhs5` | text | Distinguishes absent from small-sample suppressed |

---

## Derived metrics

| Metric | Definition | Range |
|---|---|---|
| `need_value` | Direction-normalised indicator value | 0–100 |
| `need_percentile` | National percentile rank of `need_value` | 0–1 |
| `need_index` | Weighted mean of percentiles over present indicators | 0–1 |
| `weight_covered` | Sum of weights present; <1 means partial data | 0–1 |
| `population_at_risk` | `need_index × rural_population` | people |
| `required_facilities` | `ceil(rural_population / catchment_norm)` | count |
| `coverage_gain_population` | `need × min(catchment_norm, rural_pop)` | people |
| `coverage_gain_neutral` | `need × min(1, rural_pop / catchment_norm)` | 0–1 |

`coverage_gain_neutral` is the default objective. The `min()` in
`coverage_gain_population` binds for only 2 of 696 districts, so it reduces to
`need × 5000` or `need × 3000` — a 67% handicap for difficult terrain.

---

## `core.allocation`

| Column | Meaning |
|---|---|
| `scenario` | `optimal`, `greedy_feasible`, `greedy_by_need`, `naive_top25`, `unconstrained_bound` |
| `district_id` | Selected district |
| `pick_rank` | Selection order for heuristics; NULL for the ILP |
| `need_index`, `coverage_gain` | Values at selection time |

Only winners are stored. Absence means not selected.

---

## `core.weight_sensitivity`

| Column | Meaning |
|---|---|
| `regime` | `centred` (plausible) or `uniform` (adversarial) |
| `rank_stability` | Share of draws in the top 25 **by need index** |
| `ilp_stability` | Share of re-solves where **actually allocated** |
| `mean_rank`, `best_rank`, `worst_rank` | Rank across draws |
| `p05_need_index`, `p95_need_index` | Need index band |
| `classification` | `robust` >95%, `contested` 5–95%, `excluded` <5% |

Classification uses `ilp_stability`. Judging an allocated district by rank
stability alone mislabels the districts the equity constraints exist to protect,
because the constrained optimum deliberately reaches outside the national top 25.

---

## `data/processed/residuals.csv`

| Column | Meaning |
|---|---|
| `need_index` | Actual |
| `predicted_need` | **Out-of-fold** prediction from Census socioeconomics |
| `residual` | `need_index − predicted_need` |
| `residual_z` | Standardised residual |
| `allocated` | Whether the district is in the optimal 25 |

Predictors (all shares, so district size cannot leak in): `literacy_rate`,
`female_literacy_rate`, `sc_share`, `st_share`, `electrified_hh`, `latrine_hh`,
`tapwater_hh`, `lpg_hh`, `agri_worker_share`, `worker_share`, `rural_hh_share`.

Positive residual = worse health than material conditions predict.

---

## `core.param`

| Key | Source |
|---|---|
| `min_indicators_present` | `config/indicators.yml` |
| `tribal_st_share_threshold` | `config/iphs_norms.yml` |
| `catchment_plains`, `catchment_hilly` | `config/iphs_norms.yml` |
| `budget`, `max_per_state`, `min_per_region` | `config/allocation.yml` |

Read via `core.get_param()`, which **raises** on a missing key.

---

## Scope exclusions

**9 districts are unscoreable** — Mumbai, Mumbai Suburban, Chennai, Kolkata,
Hyderabad, Delhi Central, New Delhi, Mahe, Yanam. All have zero rural
population; a rural Sub-Centre cannot be sited where there is no rural
population. 705 districts → 696 scored. A test pins that the excluded set
contains only zero-rural districts.

**22 districts have no map polygon** and are absent from the choropleth but
present in every table. See `reports/map_crosswalk_report.md`.
