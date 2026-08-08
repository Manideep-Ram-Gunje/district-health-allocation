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
