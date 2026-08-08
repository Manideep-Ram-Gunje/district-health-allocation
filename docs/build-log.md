# Build log

A running record of what was built, what broke, and why each decision was
made. Kept during the build rather than reconstructed afterwards — the
failures below are the useful part, and most of them are load-bearing for the
methodology.

---

## Phase 0 — environment and acquisition

**Built.** Project scaffold, declarative source registry (`config/sources.yml`),
acquisition script with SHA-256 manifest and per-source shape assertions
(`src/phase0_acquire.py`), Need Index specification (`config/indicators.yml`).

**Result.** 3/3 sources downloaded and verified.

| Source | Shape | Note |
|---|---|---|
| NFHS-5 districts | 73,319 rows x 7 cols, **705 districts** | long format |
| Census 2011 districts | 640 rows x 118 cols | exact match to expected 640 |
| geoBoundaries ADM2 | 735 features | 2021 vintage, ODbL |

### Challenges

**1. The obvious NFHS-5 mirror is only half the country.**
`pratapvardhan/NFHS-5` is the most-starred and most-cited NFHS-5 CSV
repository, and its `NFHS-5-Districts.csv` contains **341 districts from 21
states** — Phase 1 of the survey only. Building on it would have silently
excluded half of India, including most of the high-need districts in the
north. Switched to `jvargh7/nfhs5_factsheets`, whose `districts.csv` is parsed
from the Phase 2 compendium and covers all states and UTs.

*Lesson: verify the row count of a dataset against what the documentation
claims the universe is, before writing a single line of analysis.*

**2. The spec's 707-district figure was approximately right but not exact.**
Actual: **705**. Chandigarh and Lakshadweep have no district factsheet in this
extract. Documented rather than fudged.

**3. District-level Rural Health Statistics does not exist in machine-readable
form.** MoHFW publishes Sub-Centre / PHC / CHC counts as state-level PDF
tables. This was checked in Phase 0 rather than discovered mid-build, and is
recorded in `config/sources.yml` under `unavailable:` with what was attempted.
Consequence: the supply side of the underservice score falls back to
state-level norms. **This is the project's principal methodological weakness**
and is stated in the README rather than buried.

**4. 115 distinct indicator name strings, but only 104 indicator numbers.**
*(After the malformed rows in challenge 5 are rescued, 10 numbers carry more
than one name string — see `reports/data_quality_report.md`.)*
The verification step flagged 115 unique values in the `Indicator` column
against an expected 104. Investigation: eight indicators have more than one
name string, differing only in whitespace and line-break artefacts from PDF
extraction — and one of them is **indicator 49, "Children age 12-23 months
fully vaccinated"**, which is in our index.

Keying the Need Index on indicator *names* would have split indicator 49 into
two partial series and silently dropped districts from the index. We key on
the leading integer instead. `name_as_published` is retained in the config for
documentation only.

*This is the single highest-value bug caught in the project, and it was caught
by a row-count assertion that took four lines to write.*

**5. Two structurally malformed rows.** Maharashtra/Raigarh has two rows where
the PDF extractor merged a section header into an indicator name
(`"Current Use of Family Planning Methods ... 20. Any method6 (%)"`). Neither
is in our indicator set. Logged, not silently dropped.

---

## Phase 1a — boundary reconciliation

**Built.** State-restricted fuzzy crosswalk with a manual override table and a
directional-token guard (`src/phase1_reconcile.py`,
`config/state_crosswalk.yml`, `config/district_overrides.csv`).

**Result.** 705/705 NFHS-5 districts matched to a Census 2011 district — 100%,
0 unmatched, 0 failed override targets.

| Tier | Districts |
|---|---|
| `fuzzy` (>= 90) | 626 |
| `override:child_of` | 69 |
| `override:rename` | 7 |
| `fuzzy_review` (80-90, flagged) | 3 |

118 districts share a Census parent with at least one sibling and have their
population apportioned.

### Challenges

**1. Matching nationally produces false positives.** There is an Aurangabad in
both Maharashtra and Bihar, a Bilaspur in both Chhattisgarh and Himachal
Pradesh, a Hamirpur in both HP and UP. So the state map had to be correct
*before* any district matching ran. `config/state_crosswalk.yml` maps each
NFHS state to a set of *candidate* Census states, which is what makes the
reorganisations expressible: Telangana searches ANDHRA PRADESH, Ladakh and
Jammu Kashmir both search JAMMU AND KASHMIR, and the merged DNH & Daman Diu UT
searches two separate 2011 UTs.

**2. State name strings were not what we assumed.** First run failed loudly on
`['Dadra Nagar Haveli Daman Diu', 'Jammu Kashmir', 'NCT Delhi']` — the extract
uses no ampersands. The script exits non-zero if any NFHS state is missing
from the config rather than silently matching against an empty pool, which is
why this surfaced in one second instead of as a mystery 3% of unmatched
districts later.

**3. The dangerous failure: fuzzy matching attached new districts to their
SIBLINGS.** This is the one worth understanding. Post-2011 splits produce
names that differ from an existing district by a single directional word, and
`token_sort_ratio` scores those pairs 80-90 — comfortably inside any sane
acceptance threshold:

| NFHS district | Wrongly matched to | Score |
|---|---|---|
| Delhi `South East` | `North East` | 80 |
| `North Garo Hills` | `South Garo Hills` | 88 |
| `South West Garo Hills` | `South Garo Hills` | 86 |
| `South West Khasi Hills` | `West Khasi Hills` | 84 |
| `West Karbi Anglong` | `Karbi Anglong` | 84 |

Every one of these would have assigned a district the *wrong* population
denominator — and would have looked completely fine in the output, because a
high match score is exactly what you check for.

Fix: a **directional-token guard**. If two names disagree on their set of
directional tokens (`north/south/east/west/upper/lower/urban/rural/purba/
paschim/...`), the fuzzy match is refused regardless of score and the district
is pushed to the unmatched pile for human resolution. Raising the threshold
would not have worked — `South East` -> `North East` scores 80 while genuine
renames like `Darjeeling` -> `Darjiling` score 84.

**4. 69 genuinely new districts needed hand-mapping.** After the guard, 76
districts had no Census counterpart: Telangana 21, Gujarat 10, Chhattisgarh
10, Assam 6, Meghalaya 5, UP 4, Tripura 4, Arunachal 4, and singles elsewhere.
Each was resolved to its Census 2011 parent in
`config/district_overrides.csv`, with the creation year recorded. Every
`census_district` string was verified to exist in the Census file before being
written; a typo raises `OVERRIDE TARGET NOT FOUND` rather than failing quietly.

**5. Population apportionment is the largest remaining source of error.**
118 districts share a parent. The parent's population is divided **equally**
among children. This is unbiased in aggregate but wrong for any individual
district — Medchal-Malkajgiri and Vikarabad are not half of Rangareddy each.
Correcting it would require sub-district population data we do not have. It is
disclosed in the reconciliation report with the full list of affected
districts.

### Validation

Derived rural population summed across all 705 matched districts:
**824.2 million**, against the Census 2011 published all-India rural
population of **833.5 million** — a **1.1% shortfall**.

This is a real external check, and the direction is the one predicted in
`config/indicators.yml`: the household-share method assumes equal mean
household size in rural and urban areas, but rural households are slightly
larger, so rural population is mildly *under*-estimated. The bias is
conservative for our purpose — it understates rural need rather than inflating
it. Chandigarh and Lakshadweep being absent accounts for a negligible share.

---

## Phase 1b — schema and load

**Built.** Two-schema Postgres model (`sql/01_schema.sql`), idempotent loader
(`src/phase1_load.py`), data quality report, 18 tests.

`staging` holds verbatim source data with every column as `text` — the NFHS
source encodes missingness as `NA` and small-sample suppression as `*`, and
casting on load would destroy that distinction. `core` is typed and
constrained. Everything downstream reads only from `core`.

**Result.**

| Table | Rows |
|---|---|
| `staging.nfhs5_raw` | 73,319 |
| `core.indicator` | 104 (7 in index, 10 with unstable names) |
| `core.district` | 705 |
| `core.district_indicator` | 73,319 |
| `core.weight_scheme` | 21 (3 schemes) |

### Constraints that encode the methodology

The schema refuses to hold a contradiction rather than trusting the loader:

- `apportioned_implies_siblings` — `is_apportioned` must equal
  `n_sharing_parent > 1`. The two can never drift apart.
- `rural_not_exceeding_total` — rural population cannot exceed total.
- `index_members_fully_specified` — any indicator marked `in_index` must have
  a key, a domain and a direction. An indicator cannot enter the Need Index
  half-configured.
- `indicator_id BETWEEN 1 AND 104` — catches a bad regex parse at insert time.

### Challenges

**1. `libpq` silently overrode the connection URL.** Testing against a
throwaway Postgres, connections kept landing on the wrong port despite
`DATABASE_URL` being set explicitly. Cause: the URL omitted the port, and
libpq fills any parameter the URL omits from the `PG*` environment variables —
which `.env` had already populated via `load_dotenv`. The override is silent
and there is no warning. Documented in `.env.example`: if you set
`DATABASE_URL`, spell the port out.

**2. `pytest` and `python -m pytest` do not agree on `sys.path`.** The `-m`
form prepends the current directory, the console script does not, so
`from src.config import ...` resolved under one and raised
`ModuleNotFoundError` under the other. Fixed properly in `pyproject.toml` with
`pythonpath = ["."]` rather than by telling people which command to type.

**3. Two malformed rows were rescued rather than dropped.** The Maharashtra/
Raigarh rows where the PDF extractor merged a section header into the
indicator name are recovered with a secondary regex. This is why the count of
indicators with unstable names rises from 8 (raw) to 10 (loaded) — the two
rescued strings become extra name variants for indicators 20 and 98. Neither
is in the index.

### Validation — population conservation

The strongest check in the project so far. Total population summed across all
705 loaded districts:

```
loaded                    1,209,735,047
Census 2011 all-India     1,210,854,977
gap                           1,119,930
Chandigarh + Lakshadweep      1,119,923   <- the two UTs with no NFHS factsheet
unexplained residual                  7   <- apportionment rounding
```

Population is conserved to seven people across 118 apportioned districts. If
the split logic were double-counting or dropping population, this number would
be in the millions. It is asserted in `tests/test_load.py` so it cannot
regress silently.

---

## Phase 2 — SQL analytics layer and the Composite Need Index

**Built.** A chain of materialised views (`sql/02_analytics.sql`), the Phase 2
driver (`src/phase2_need_index.py`), IPHS terrain classification, 10 more
tests. 696 districts scored under 3 weighting schemes.

The index is deliberately built as a *chain* rather than one query, so every
intermediate stage can be selected from and defended:

```
mv_indicator_score       direction-normalised raw values
mv_indicator_percentile  percentile rank in the national distribution
mv_need_index            weighted composite, per scheme
mv_district_score        need + population + IPHS coverage terms
mv_peer_benchmark        district vs its state and region
v_supply_degeneracy      executable proof of a methodological finding
```

### Why percentile-rank rather than z-score or min-max

Raw indicator values are not comparable. Institutional births spans roughly
20-100; stunting spans 6-60. Averaging raw values silently lets the
widest-spread indicator dominate — the weight vector would say the indicators
are equal while the arithmetic disagreed. Percentile ranking puts all seven on
an identical 0-1 scale, so the weights are the *only* thing determining
influence. That is also what makes the Phase 4 sensitivity analysis meaningful:
perturbing the weights perturbs exactly one thing.

### Challenges

**1. `percent_rank()` returns double precision, and Postgres has no
two-argument `round()` for doubles.** The build failed with
`function round(double precision, integer) does not exist`. The lazy fix is to
cast at each call site. The right fix is to cast once, at the source, so the
whole downstream chain is exact decimal arithmetic — which also makes the need
index bit-for-bit reproducible across machines rather than subject to binary
floating-point drift.

**2. Terrain had to be derived, not assumed.** IPHS sets the Sub-Centre
catchment at 5,000 in plains and 3,000 in hilly, tribal *or desert* areas —
the spec quoted "hilly and tribal" and dropped desert, which was caught by
checking the published standard (IPHS 2022 Volume IV) rather than quoting from
memory. Hill states come from a config list; tribal status is computed from
**Census ST population share >= 50%**, a measured quantity rather than a guess.
Result: 543 plains, 118 hilly, 44 tribal. The tribal set is face-valid — The
Dangs 94.7% ST, Alirajpur 89.0%, Jhabua 87.0%.

Desert is never assigned, and ST share is computed on total rather than rural
population. Both errors under-apply the 3,000 norm, i.e. both are conservative.
Documented in `config/iphs_norms.yml`.

**3. Nine districts are correctly unscoreable.** 705 districts, 696 scored. The
nine dropped are Mumbai, Mumbai Suburban, Chennai, Kolkata, Hyderabad, Delhi
Central, New Delhi, Mahe and Yanam — every one has *zero* rural population. A
rural Sub-Centre cannot be sited where there is no rural population, so this is
the scope boundary in the spec asserting itself, not a data failure. A test
pins it: the excluded set must contain only zero-rural districts.

### The main finding: the supply adjustment cancels

Spec section 6.3 defines underservice as population at risk divided by existing
facilities, falling back to *norm-implied* facilities where counts are
unavailable. Counts are unavailable (Phase 0). Substituting the fallback:

```
underservice = (need x rural_pop) / (rural_pop / norm)
             =  need x norm
```

The population term cancels **exactly**. A supply-adjusted underservice score
would be the need index times a terrain constant — carrying zero information
about existing infrastructure while appearing to account for it. It would also
rank districts almost identically to the raw need index, so the error would
never show up as a suspicious-looking output.

`core.v_supply_degeneracy` proves this on the real data rather than asserting
it: `ratio_check` is 1.0 for all 696 districts, and a test enforces it.

**Consequence.** No supply-adjusted score is shipped. Supply enters only
through the terrain-specific catchment norm in `coverage_gain`. Volunteering
this is stronger than shipping a formula that cancels.

### Face validity

The top of the ranking was not tuned toward any expected answer, and it lands
on exactly the districts an Indian public health researcher would name: Araria,
Purnia, Sitamarhi, Katihar and Kishanganj (Bihar's Seemanchal region), and
Pakur, Sahibganj and Deoghar (Jharkhand's Santhal Pargana). These are among the
most deprived districts in the country. The index found them from seven NFHS
indicators without being told anything about geography.

### First look at weight sensitivity

Top-25 overlap between weighting schemes, out of 25:

| Scheme A | Scheme B | Shared |
|---|---|---|
| `equal_per_domain` | `equal_per_indicator` | 18 |
| `equal_per_domain` | `maternal_priority` | 17 |
| `equal_per_indicator` | `maternal_priority` | 22 |

Substantial but not total agreement — which is the honest answer, and sets up
Phase 4 to quantify it properly across 10,000 sampled weight vectors.

---

## Phase 3 — constrained allocation

**Built.** Integer linear program in PuLP solved by CBC, three comparison
baselines, results table and comparison view (`sql/03_allocation.sql`),
`src/phase3_allocate.py`, 10 more tests.

```
maximise    sum_d  need_index_d * min(catchment_norm_d, rural_pop_d) * x_d
subject to  sum_d x_d = 25                     budget, exactly
            sum_(d in state) x_d <= 4          equity
            sum_(d in region) x_d >= 1         political feasibility
            x_d in {0,1}
```

CBC returns **Optimal** — a proven optimum, not a good-enough answer.

### Results

| Scenario | Feasible | States | Regions | Max in one state | Coverage gain |
|---|---|---|---|---|---|
| `unconstrained_bound` | no | 5 | 4 | 13 | 109,084 |
| `optimal` | **yes** | 9 | 6 | 4 | **103,285** |
| `naive_top25` | no | 7 | 3 | 12 | 101,243 |
| `greedy_feasible` | yes | 11 | 6 | 4 | 91,350 |

- **Optimisation premium vs `greedy_feasible`: +13.07%**
- **Optimisation premium vs `naive_top25`: +2.02%**
- **Price of equity vs the unconstrained ceiling: −5.32%**

### The result I did not expect

The optimal allocation beats the naive top-25 **even though the naive list
ignores every constraint**. My first draft of the report had the narrative
written the other way round — assuming the constrained answer must score lower
and framing the gap as the cost of equity. The data said otherwise, so the
explanation had to be rebuilt rather than the number explained away.

The cause: *the thing you sort on is not the thing you are maximising.* The
need index answers "how badly off is this district". The objective answers "how
much good does one more facility do here". They diverge because coverage gain
caps at the catchment norm — a district of 4 million and one of 40,000 both get
one facility's worth of benefit, and a district whose entire rural population
is below the norm cannot absorb even that. Terrain shifts the coefficient too
(5,000 in plains, 3,000 in hilly or tribal).

So sorting by the headline metric produces a list that is both inadmissible
**and** leaves value on the table. That is a stronger answer to "why not just
sort?" than the constraint argument on its own.

Adding `unconstrained_bound` — top 25 by the objective itself, constraints
dropped — completes the decomposition. It is the true ceiling, so the −5.32%
gap to the optimum is the genuine price of equity, measured against something
achievable-in-principle rather than against a list nobody could execute.

The binding constraint is the state cap: unconstrained, Bihar takes 13 of 25
and Uttar Pradesh 6, reaching only 4 of 6 regions.

### Challenges

**1. `tabulate` was an undeclared dependency.** Phase 2 completed every
computation, wrote its CSV, then crashed writing the markdown report —
`pandas.to_markdown()` requires `tabulate`, which was present in the
development environment and absent from `requirements.txt`. An optional
dependency of a package you *do* declare fails only at the moment of use, and
here that moment was after all the real work had succeeded.

Rather than just adding the line, `tests/test_dependencies.py` now enforces the
invariant: every third-party module the code imports must appear in
`requirements.txt`, and known implicit dependencies (`to_markdown` ->
`tabulate`, `read_parquet` -> `pyarrow`) must too.

**2. That guard was wrong twice before it was right** — worth recording,
because both failures are instructive:

- It scanned *itself* and reported `openpyxl` as missing, because its own
  lookup table contains the literal strings `read_excel` and `openpyxl`.
- Its regex matched SQL inside triple-quoted strings: `from core.district d
  join ...` looked like an import of a module named `core`, and `from r a join
  r b` like one named `r`.

Fixed by excluding the file from its own scan and by parsing the **AST**
instead of pattern-matching source text. A regex over code is a guess about
syntax; `ast.walk` knows what an import actually is.

---

## Phase 4 — weight sensitivity

**Built.** Dirichlet sampling under two regimes, vectorised index recomputation,
ILP re-solves, results table and confidence view (`sql/04_sensitivity.sql`),
`src/phase4_sensitivity.py`, 12 more tests.

### Result

Of the 25 allocated districts:

| Regime | Robust | Contested | Excluded |
|---|---|---|---|
| `centred` — plausible committee disagreement | **12** | 13 | 0 |
| `uniform` — adversarial stress test | 5 | 20 | 0 |

**Zero excluded under either regime** is the reassuring number: the optimiser
never selects a district that could not be re-selected when the weights move.

### Challenges

**1. A silent NULL nearly shipped a false clean bill of health.** Running the
pipeline on a second machine, `states_over_cap` reported `None` for *every*
scenario — including the naive allocation that puts 12 of 25 facilities in
Bihar. The database had been rebuilt without reloading `core.param`, so
`(SELECT value FROM core.param WHERE key = 'max_per_state')` returned NULL,
`n > NULL` evaluated to NULL, and the constraint-violation view reported
nothing rather than failing.

This is the most dangerous failure mode in the project so far: **the output
looked correct**. A missing parameter should be a broken build, not an empty
result set. All parameter reads now go through `core.get_param()`, which
raises. The bare-subquery pattern is gone from every view.

**2. The first classification was measuring the wrong thing.** The initial run
labelled 9 of the 25 allocated districts as "excluded" — apparently claiming
the optimiser had chosen districts that almost never belong in the top 25.

It had, and correctly. Rank stability asks *"is this district in the national
top 25 by need index?"*, but the ILP chooses under a 4-per-state cap and a
1-per-region floor, so it **must** reach outside that list — the cap forbids
taking 12 districts from Bihar and the floor demands every region be served. A
district can be an entirely sound allocation choice while rarely appearing in
the unconstrained ranking.

Judging allocated districts by rank stability alone mislabels precisely those
districts the equity constraints exist to protect. Classification now uses
`ilp_stability` — the share of re-solved ILPs in which the district is actually
allocated — and both measures are stored so the difference is inspectable.

**3. Uniform Dirichlet is a stress test, not a sensitivity analysis.**
`alpha = 1` is uniform over the simplex, so a single draw can put 80% of the
weight on one indicator. No committee would defend that. Reporting only this
regime overstates fragility: it answers "what if the weights were chosen
adversarially?" rather than "what if reasonable people disagreed?"

Both regimes now run. `centred` samples Dirichlet around the default vector
with concentration 50 — realistic disagreement. `uniform` remains as the
adversarial bound. The two numbers together (12 robust vs 5) are more
informative than either alone, and quoting the harsher one alongside the
realistic one is more credible than quoting only the flattering one.

### Interpretation

The right framing for a defence is not "these are the 25 correct districts".
It is: **12 of 25 survive any plausible re-weighting, 13 depend on what you
decided to value, and here is exactly which is which.** The contested list is
the useful deliverable — it tells a State Health Society where the argument
actually is.

What sensitivity analysis cannot do: sampling more weight vectors cannot fix a
biased indicator set. All seven indicators are maternal, child and nutritional.
There is nothing on communicable disease, mental health or injury, so every
draw inherits that blind spot.

---

## Critical review — attacking our own results

Before building the app, the three headline claims were attacked deliberately.
Two of them did not survive. This section records what broke and what replaced
it, because the corrected versions are the defensible ones.

### Claim 1 — "optimisation premium of +13%" — WITHDRAWN

The premium was measured against a greedy baseline sorted by the **need
index**, while the objective being maximised was **coverage gain**. Sorting a
baseline by the wrong key and then reporting the difference as the value of
optimisation is a straw man.

Sorted by the objective it is supposed to maximise, greedy scored **exactly the
ILP optimum** — 103,285 versus 103,285, selecting the identical district set.
The real premium was **0.00%**.

### Claim 2 — "the model allocates on need" — FALSIFIED, THEN FIXED

The optimal 25 contained **zero hilly and zero tribal districts**, although
23.3% of candidates are non-plains.

Cause: `coverage_gain = need × min(catchment_norm, rural_population)`, and the
`min()` binds for only **2 of 696 districts**. So the objective collapsed to
`need × 5000` in plains and `need × 3000` in hilly or tribal terrain — a hilly
district needed a 67% higher need index merely to compete.

This **inverts the purpose of the IPHS standard**. The norm is lower in hills
*because* reaching 3,000 people there takes what reaching 5,000 takes in
plains. Our objective punished hard terrain for being hard to serve.

Fix: a second objective, `coverage_gain_neutral = need × min(1, rural_pop /
norm)` — one facility counts as one facility wherever it stands. Now the
default. Both are computed in SQL and the choice is explicit in
`config/allocation.yml`, because it is a policy judgement a State Health
Society is entitled to make differently. Effect: 9 of the 25 districts change,
and the allocation becomes **16 plains, 5 hilly, 4 tribal**.

### Claim 3 — "greedy is a fair baseline" — BROKEN, THEN FIXED

Sweeping across constraint settings produced an impossible result: at
`min_per_region >= 2`, greedy scored **higher** than the proven optimum
(21.197 vs 20.442). A feasible heuristic cannot beat a proven optimum, so one
of them was wrong.

Greedy was. Its region-repair step performed exactly **one swap per region**,
so a region needing 3 facilities with 0 selected was "repaired" to 1 and the
result reported as feasible. The infeasible allocation kept districts it should
have surrendered, which is why it scored higher.

The repair now loops until every region meets the floor, and `check_feasible()`
validates every scenario before any comparison is made. Phase 3 exits non-zero
if a scenario claiming feasibility violates a constraint.

### What Phase 3 is now allowed to claim

Verified across 11 constraint configurations (`tests/test_allocation.py`):

| budget | cap | floor | greedy | ILP | identical set |
|---|---|---|---|---|---|
| 25 | 4 | 1 | 21.282 | 21.282 | yes |
| 25 | 2 | 1 | 20.614 | 20.614 | yes |
| 25 | 1 | 1 | 18.901 | 18.901 | yes |
| 25 | 4 | 3 | 20.442 | 20.442 | yes |
| 25 | 3 | 2 | 20.788 | 20.788 | yes |
| 10 | 2 | 1 | 8.550 | 8.550 | yes |
| 50 | 4 | 2 | 40.023 | 40.023 | yes |
| 60 | 2 | 1 | 40.605 | 40.605 | yes |
| 25 | 4 | 4 | 19.778 | 19.778 | yes |
| 30 | 2 | 3 | 23.938 | 23.938 | yes |
| 40 | 1 | 1 | — | **infeasible** | — |

**A correctly implemented greedy attains the ILP optimum in every feasible
configuration tested.** That is not a failure of the ILP — it is a property of
the problem. The objective is linear, the per-state caps form a partition
matroid, and greedy is optimal on exactly that structure.

So the honest answer to *"what did optimisation buy you over sorting?"* is:

1. **A proof.** Greedy gives an answer; the ILP certifies it cannot be beaten.
   Without the ILP you would not know that greedy was optimal — and at
   `min_per_region >= 2` our greedy was silently wrong.
2. **Infeasibility detection.** 40 facilities at one per state across ~30
   states is impossible. CBC says so. Greedy returns a plausible-looking list.
3. **Declarative constraints.** Changing the cap is one line; the greedy repair
   logic had to be rewritten to handle a floor above 1.
4. **Robustness to change.** The moment constraints couple districts —
   adjacency, travel time, shared staffing — the matroid structure is gone and
   greedy loses its guarantee. The ILP formulation does not change.

Claiming a fabricated premium would have been easier and would not have
survived the first competent interviewer. This version invites the question.

---

## Phase 5 — map, app, and making it deployable

**Built.** Polygon crosswalk (`src/phase5_geo.py`), Streamlit application
(`app/streamlit_app.py`), a data-access layer (`src/datasource.py`) and a
snapshot exporter (`src/snapshot.py`).

### Challenges

**1. The map file has no state column.** geoBoundaries ADM2 carries an **empty
`shapeISO` on every one of its 735 features**. Matching district names
nationally would confuse the Aurangabad in Maharashtra with the one in Bihar —
and a choropleth that colours the wrong district is worse than no map, because
it still looks authoritative.

State is recovered geometrically instead: the ADM1 state layer is acquired, and
each district polygon's **representative point** is spatially joined into it.
`representative_point()` rather than `centroid()` deliberately — a centroid can
fall outside a concave or multipart shape, which for coastal and island
districts silently assigns the wrong state. Name matching is then restricted
within state, with the Phase 1 directional guard still applying. Result: 93.1%
of polygons matched, 96.9% of districts covered.

**2. Two polygons claimed the same district.** The 1:1 guard caught it and the
run failed rather than shipping. Only the best-scoring polygon now keeps a
district; the runner-up is released with the reason recorded. Colouring two
polygons from one district's score would have overstated its footprint on the
map.

**3. The app could not be deployed.** It read live Postgres, which no cloud
host has. Rather than maintain two apps, `src/datasource.py` tries Postgres
first and falls back to an exported snapshot — parquet tables plus a geojson
trimmed from 8 MB to about 2 MB by keeping only matched polygons and
simplifying the geometry.

The app **displays which source answered**. A dashboard that silently serves
stale files while looking live is precisely the thing that destroys trust in an
analysis, and the fix costs one line.

`requirements-app.txt` exists for the same reason: the deployed app never
imports geopandas, fiona or psycopg2, so dropping them removes the GDAL system
dependency that is the usual cause of a failed cloud build.

---

## Phase 6 — documentation and deliverables

**Built.** `README.md`, `docs/DEPLOY.md`, `reports/recommendation_memo.md`,
`docs/Project_Report.pdf` (10 pages, recruiter-facing) and
`docs/Project_Deck.pptx` (12 slides).

### Challenges

**1. ReportLab does not wrap text in table cells.** Long strings ran straight
off the page edge — invisible in the code, obvious in the render. Every cell is
now wrapped in a `Paragraph`, which is the only flowable that reflows to the
column width. Caught by rendering the PDF to images and *looking* at it, which
is the only reliable check.

**2. Three near-blank pages** from manual page breaks that fired after short
sections. Removed the manual breaks and let content flow, keeping
`KeepTogether` only where a block genuinely must not split. 13 pages became 10,
with no widows.

**3. A table drawn twice.** In the deck, a header rectangle was drawn over a
table and then the table redrawn on top, leaving white header text on a white
fill — invisible. Fixed by styling the header cells directly instead of
painting a shape behind them.

All three were caught by rendering to images and inspecting them. None would
have been caught by reading the generating code, which is the point.
