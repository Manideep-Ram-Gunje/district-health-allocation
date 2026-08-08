# Architecture

Technical reference. For a gentler introduction see
[`resources/Codebase_Guide.pdf`](../resources/Codebase_Guide.pdf).

---

## Design principles

**The database is the analytics engine.** The Need Index is computed in SQL, not
pandas. Python orchestrates, downloads, optimises and reports; the scoring logic
lives in materialised views that can be selected from and defended line by line.

**Configuration is data.** Indicators, weights, budget, constraints and IPHS
norms live in `config/*.yml` and are loaded into `core.param` so SQL reads the
same values Python does. No methodology number is hardcoded twice.

**Constraints encode the methodology.** The schema refuses contradictions: an
indicator cannot enter the index without a direction and a domain; a split flag
cannot disagree with its sibling count; a terrain cannot disagree with its
catchment norm.

**Fail loudly.** `core.get_param()` raises on a missing key rather than
returning NULL, because NULL propagates silently — a constraint-violation view
once reported *no violations* for an allocation with 12 facilities in one state.

**Everything is reproducible.** Sources are pinned and checksummed; the RNG seed
is fixed; `make pipeline` rebuilds from raw data. Nothing in `reports/` or
`data/processed/` is authored by hand.

---

## Data flow

```
config/sources.yml
      │  phase0_acquire.py — download, SHA-256, shape assertions
      ▼
data/raw/ ──────────────────────────────────────────────┐
      │  phase1_reconcile.py — state-restricted fuzzy    │
      │  match + directional guard + override table      │
      ▼                                                  │
data/interim/crosswalk.csv                               │
      │  phase1_load.py — schema, staging, core, params  │
      ▼                                                  │
PostgreSQL ── staging (verbatim) ── core (typed)         │
      │  02_analytics.sql — need index chain             │
      ▼                                                  │
core.mv_district_score                                   │
      │  phase3_allocate.py — CBC integer program        │
      ├──────────────► core.allocation                   │
      │  phase4_sensitivity.py — 10k draws, 400 solves   │
      ├──────────────► core.weight_sensitivity           │
      │  phase7_residual.py — sklearn, out-of-fold       │
      ├──────────────► data/processed/residuals.csv      │
      │  phase5_geo.py — spatial join ◄──────────────────┘
      ▼
data/interim/geo_crosswalk.csv
      │  snapshot.py — parquet + trimmed geojson
      ▼
data/processed/snapshot/ ──► app/streamlit_app.py (via src/datasource.py)
```

---

## Database schema

Two schemas, deliberately separated.

### `staging` — verbatim

Every column is `text`. The NFHS source encodes missing as `NA` and
small-sample suppression as `*`; casting on load would destroy the distinction
permanently.

| Table | Rows | Contents |
|---|---|---|
| `nfhs5_raw` | 73,319 | NFHS-5 long format, exactly as downloaded |
| `census2011_raw` | 640 | Selected Census 2011 columns |

### `core` — typed and constrained

| Table | Rows | Purpose |
|---|---|---|
| `indicator` | 104 | Factsheet catalogue; `in_index` marks the 7 used |
| `district` | 705 | One row per NFHS district with Census lineage |
| `district_indicator` | 73,319 | The fact table |
| `weight_scheme` | 21 | Named weight vectors from config |
| `param` | 7 | Scalar methodology parameters |
| `allocation` | 125 | Selected districts per scenario |
| `weight_sensitivity` | 1,392 | Phase 4 output, per district per regime |
| `load_audit` | — | Which file, which checksum, how many rows |

### Key constraints

| Constraint | Prevents |
|---|---|
| `apportioned_implies_siblings` | Split flag drifting from sibling count |
| `rural_not_exceeding_total` | Rural population above total |
| `index_members_fully_specified` | Half-configured indicator entering the index |
| `catchment_matches_terrain` | Terrain and norm disagreeing |
| `indicator_id BETWEEN 1 AND 104` | A bad regex parse reaching the table |

### Materialised views (`sql/02_analytics.sql`)

Built as a chain so every stage is separately inspectable.

| View | What it adds |
|---|---|
| `mv_indicator_score` | Direction normalisation — higher always means worse |
| `mv_indicator_percentile` | National percentile rank, cast to `numeric` |
| `mv_need_index` | Weighted mean, weights renormalised over present indicators |
| `mv_district_score` | Both objectives, population at risk, required facilities |
| `mv_peer_benchmark` | National and state rank, gap to state mean |
| `v_supply_degeneracy` | Executable proof that supply adjustment cancels |

`percent_rank()` returns double precision and is cast to `numeric` once, at the
source. This is deliberate: Postgres has no two-argument `round()` for doubles,
and casting once makes the whole chain exact decimal arithmetic and
bit-for-bit reproducible.

---

## The optimisation

```
maximise    Σ  need_d × min(1, rural_pop_d / catchment_norm_d) × x_d
subject to  Σ x_d = budget                        exactly, not at most
            Σ_(d ∈ state)  x_d ≤ max_per_state
            Σ_(d ∈ region) x_d ≥ min_per_region
            x_d ∈ {0,1}
```

Solved by CBC via PuLP with `mip_gap = 0` — a proven optimum, not a
good-enough answer.

**Verified property:** a correct greedy attains this optimum in all 10 feasible
configurations tested (`tests/test_allocation.py`). The objective is linear and
the per-state caps form a partition matroid, which is exactly the structure
greedy handles optimally. The ILP is therefore *not* claimed to find a better
answer — it proves optimality, detects infeasibility, and expresses constraints
declaratively.

---

## Module reference

| Module | Responsibility |
|---|---|
| `config.py` | Paths, YAML loading, database URL. Import this, never hardcode |
| `datasource.py` | Postgres if reachable, snapshot otherwise; reports which |
| `snapshot.py` | Exports parquet + simplified geojson for deployment |
| `phase0_acquire.py` | Download, checksum, assert shape |
| `phase1_reconcile.py` | District crosswalk, directional guard, `norm()` |
| `phase1_load.py` | Schema build, staging + core load, terrain classification |
| `phase2_need_index.py` | Runs the analytics SQL, reports the index |
| `phase3_allocate.py` | ILP, three baselines, `check_feasible()` |
| `phase4_sensitivity.py` | Dirichlet sampling, `need_matrix()`, re-solves |
| `phase5_geo.py` | Polygon crosswalk via spatial join |
| `phase7_residual.py` | Socioeconomic model, out-of-fold residuals |

Each phase module exposes `main() -> int`, returning 0 on success and non-zero
on a check failure, so `make` halts the pipeline on error.

---

## Test strategy

82 tests in 8 files. Every test's docstring explains **why it exists**, usually
naming the bug it caught.

| File | Guards |
|---|---|
| `test_crosswalk.py` | Match completeness, population conservation, directional guard |
| `test_load.py` | Row counts, orphan facts, weight sums, Census reconciliation |
| `test_need_index.py` | Index bounds, direction normalisation, percentile span |
| `test_allocation.py` | Constraint satisfaction across 11 configurations |
| `test_sensitivity.py` | Stability sums, regime ordering, matrix maths |
| `test_residual.py` | Residual centring, feature ranges, R² in useful range |
| `test_dependencies.py` | Every import declared; deployment file stays lean |

Database-backed tests skip cleanly when Postgres is unavailable, so a fresh
clone can run the suite before setting anything up.

---

## Deployment

The app runs from `data/processed/snapshot/` when no database is reachable and
displays a banner saying so. This is what makes cloud deployment possible.

`requirements.txt` (root) is the **deployment** set — Streamlit Cloud installs
that filename and offers no way to point elsewhere. `requirements-pipeline.txt`
adds geopandas, psycopg2, scikit-learn and pytest. A test enforces that the
geospatial stack never leaks into the root file, because it drags in GDAL and
breaks the cloud build.

See [`DEPLOY.md`](DEPLOY.md).
