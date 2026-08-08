# District Health Infrastructure Allocation System

**Where should a State Health Society build its next 25 rural Sub-Centres, and
how much better is an optimised answer than a sorted list?**

An end-to-end analytics system over Indian public health data: it ingests three
public datasets, reconciles a decade of district boundary changes, builds a
documented composite need index in SQL, solves a budget-constrained integer
program, and tests how much of the answer survives 10,000 alternative
weightings.

> This is a portfolio project built on public data. **It is not a policy
> recommendation** and should never be presented as one. Its principal
> limitations are listed in [Limitations](#limitations), not buried at the end.

---

## The headline result

25 Sub-Centres allocated across **696 eligible districts**:

| | |
|---|---|
| States receiving facilities | 11 |
| Regions covered | 6 of 6 |
| Terrain mix | 16 plains, 5 hilly, 4 tribal |
| Robust under plausible re-weighting | **11 of 25** |
| Contested | 14 of 25 |
| Excluded | 0 |

The list is led by Araria, Purnia and Sitamarhi in Bihar's Seemanchal region and
Pakur, Sahibganj and Deoghar in Jharkhand's Santhal Pargana — among the most
deprived districts in India. The index found them from seven survey indicators
with no geographic input and no tuning.

**The honest framing is not "these are the 25 correct districts."** It is: *11
of 25 survive any plausible re-weighting, 14 depend on what you decided to
value, and here is exactly which is which.*

---

## Three findings worth reading

### 1. The supply adjustment cancels algebraically

The specification defines underservice as population at risk ÷ existing
facilities, falling back to *norm-implied* facilities where counts are
unavailable. District-level facility counts are not published in machine
readable form, so the fallback applies. Substituting it:

```
underservice = (need × rural_pop) / (rural_pop / norm) = need × norm
```

The population term cancels **exactly**. A "supply-adjusted" score would be the
need index times a terrain constant — carrying zero information about existing
infrastructure while appearing to account for it, and ranking districts almost
identically to raw need so the error would never look suspicious.

`core.v_supply_degeneracy` proves this on the real data (`ratio_check` = 1.0 for
all 696 districts) and a test enforces it. No supply-adjusted score is shipped.

### 2. Optimisation did not beat sorting — and that is the finding

An earlier version of this project claimed a **+13% optimisation premium**. It
was wrong. The premium was measured against a greedy baseline sorted by the
*need index* while the objective being maximised was *coverage gain* — a straw
man. Sorted by the objective it is supposed to maximise, greedy reaches the ILP
optimum exactly, selecting the identical 25 districts.

Verified across 11 constraint configurations (`tests/test_allocation.py`): a
correct greedy attains the optimum in every feasible one. That is a property of
the problem, not a failure of the solver — the objective is linear and the
per-state caps form a **partition matroid**, exactly the structure greedy
handles optimally.

So what does the ILP buy?

1. **A proof.** Greedy gives an answer; the ILP certifies it cannot be beaten.
   Without it you would not know — and at `min_per_region ≥ 2` our greedy was
   silently returning *infeasible* answers that scored higher than the optimum.
2. **Infeasibility detection.** 40 facilities at one per state across ~30 states
   is impossible. CBC says so. A heuristic returns a plausible-looking list.
3. **Declarative constraints.** Changing the cap is one line of config; the
   greedy repair logic had to be rewritten to handle a floor above 1.
4. **Robustness to change.** The moment constraints couple districts — adjacency,
   travel time, shared staffing — the matroid structure is gone and greedy loses
   its guarantee. The ILP formulation does not change.

### 3. The first objective was quietly discriminatory

The initial objective, `need × min(catchment_norm, rural_population)`, produced
an allocation containing **zero hilly and zero tribal districts** — though 23%
of candidates are non-plains.

The `min()` binds for only **2 of 696** districts, so the objective collapsed to
`need × 5000` in plains and `need × 3000` in hills: a hilly district needed a
67% higher need index merely to compete. This **inverts the purpose of the IPHS
standard**, which sets a lower norm *because* those areas are harder to reach.

The default is now terrain-neutral — one facility counts as one facility
wherever it stands. Both objectives are computed and the choice is explicit in
config, because it is a policy judgement, not a technical one. It moves 9 of the
25 districts.

---

### 4. Some districts are far sicker than their poverty explains

The Need Index says *how bad* outcomes are. It cannot separate a district that
is unhealthy **because it is poor** from one that is unhealthy **beyond what its
poverty explains** — and a new facility plausibly helps the second far more.

So the index is modelled from Census socioeconomic variables (literacy,
electrification, sanitation, piped water, cooking fuel, caste composition,
workforce structure) and the **residuals** are the object of interest.
Out-of-fold **R² = 0.657** (random forest, 5-fold; ridge gives 0.537).

A high R² would *not* be a good result here — it would mean health outcomes are
fully determined by material conditions, leaving no room for a health-system
signal. The useful quantity is what the model cannot explain.

| District | State | Actual need | Predicted | Residual |
|---|---|---|---|---|
| Kamrup Metropolitan | Assam | 0.622 | 0.171 | **+0.451** |
| Mewat | Haryana | 0.835 | 0.461 | +0.374 |
| Jalgaon | Maharashtra | 0.724 | 0.380 | +0.345 |
| Deoghar | Jharkhand | 0.919 | 0.584 | +0.335 |
| Patna | Bihar | 0.810 | 0.536 | +0.274 |

Kamrup Metropolitan is Guwahati — a state capital with a relatively strong
socioeconomic profile and health outcomes far below it. Mewat is a documented
outlier in Indian public health despite sitting an hour from Delhi. Patna is
another state capital. These are not the districts a need ranking alone
surfaces, and that is the point.

The residual is **not** used to drive the allocation. It is a second lens;
folding it into the objective without a causal argument would be indefensible.

## Quick start

Requires Python 3.10+ and PostgreSQL 15+. **Live demo:** https://district-health-allocation-pohllxwaukamsafzd5dyh7.streamlit.app/

```bash
# 1 — environment
python3 -m venv .venv && .venv/bin/pip install -r requirements-pipeline.txt
cp .env.example .env

# 2 — database (native install)
sudo apt install -y postgresql postgresql-client
sudo systemctl enable --now postgresql
make db-create

#    ...or with Docker instead
#    make db-up          # publishes on 5433; set PGPORT=5433 in .env

# 3 — everything
make pipeline           # acquire → reconcile → load → index → allocate → sensitivity → residual → geo → snapshot
make test               # 82 tests
make app                # http://localhost:8501
```

`make help` lists every target.

### Running without a database

The app falls back to an exported snapshot (`data/processed/snapshot/`) when no
Postgres is reachable, and **says so on screen**. This is what makes cloud
deployment and a fresh clone work. The database remains the source of truth;
regenerate the snapshot with `make snapshot`.

---

## How a district gets its score

1. **Direction-normalise.** Four of the seven indicators are good things
   (institutional births, ANC visits, skilled attendance, immunisation) and
   three are bad (stunting, anaemia). Good ones become `100 − v` so that higher
   always means greater need.
2. **Percentile-rank within the national distribution.** Raw values are not
   comparable — institutional births spans roughly 20–100 while stunting spans
   6–60. Averaging them directly would let the widest-spread indicator dominate
   *by accident*, while the weight vector claimed they were equal. Ranking puts
   all seven on an identical 0–1 scale, so the weights are the only thing that
   determines influence — which is also what makes the sensitivity analysis
   meaningful.
3. **Weighted mean over present indicators**, with weights renormalised across
   the indicators a district actually has. **No cross-district imputation
   anywhere.** An imputed need score driving a real budget allocation is not
   defensible.

### The indicators

| # | Indicator | Domain | Direction |
|---|---|---|---|
| 33 | Mothers with 4+ antenatal care visits | maternal | inverted |
| 38 | Mothers receiving postnatal care within 2 days | maternal | inverted |
| 42 | Institutional births | maternal | inverted |
| 45 | Births attended by skilled health personnel | maternal | inverted |
| 49 | Children 12–23 months fully vaccinated | child | inverted |
| 73 | Children under 5 stunted | nutrition | higher = worse |
| 84 | Women 15–49 anaemic | nutrition | higher = worse |

Indicators are keyed on their **factsheet number**, not their name. Ten
indicator numbers carry more than one name string in the source because of PDF
extraction artefacts — including number 49, which is in the index. Keying on
names would have split that series in two and silently dropped districts.

### The optimisation

```
maximise    Σ  need_index_d × min(1, rural_pop_d / catchment_norm_d) × x_d
subject to  Σ x_d = 25                        budget, exactly
            Σ_(d ∈ state)  x_d ≤ 4            equity
            Σ_(d ∈ region) x_d ≥ 1            political feasibility
            x_d ∈ {0,1}
```

Solved by CBC via PuLP to a proven optimum.

---

## Data sources

| Source | Provides | Licence |
|---|---|---|
| [NFHS-5 district factsheets](https://github.com/jvargh7/nfhs5_factsheets) (2019–21) | 705 districts × 104 indicators | MIT |
| [Census of India 2011](https://github.com/nishusharma1608/India-Census-2011-Analysis) | District population, rural/urban households, ST population | GoI open data |
| [geoBoundaries ADM2](https://www.geoboundaries.org/) | District polygons | ODbL 1.0 |
| [geoBoundaries ADM1](https://www.geoboundaries.org/) | State polygons | CC BY 2.5 IN |

Every source is declared in `config/sources.yml` with a pinned URL, and
`src/phase0_acquire.py` records a SHA-256 manifest and asserts the shape of each
file before anything downstream runs.

**One source was rejected.** `pratapvardhan/NFHS-5` is the most-cited NFHS-5 CSV
mirror, but contains only **341 districts from 21 states** — Phase 1 of the
survey. Building on it would have silently excluded half of India.

---

## Boundary reconciliation

NFHS-5 uses 2019–21 district boundaries; Census 2011 predates Telangana, the
J&K reorganisation and dozens of district splits. **705 of 705 districts are
matched**, via:

- **State-restricted matching.** There is an Aurangabad in both Maharashtra and
  Bihar, a Bilaspur in both Chhattisgarh and Himachal. Matching nationally
  produces confident, wrong answers.
- **A directional-token guard.** Post-2011 districts differ from an existing
  district by one directional word, and `token_sort_ratio` scores those pairs
  80–90 — inside any sane threshold. Delhi's `South East` matched `North East`
  at 80; `North Garo Hills` matched `South Garo Hills` at 88. Each would have
  assigned a district its **sibling's** population and looked perfect. Raising
  the threshold does not help: the bad match scores 80 while the genuine rename
  `Darjeeling → Darjiling` scores 84. So a match is refused outright when
  directional tokens disagree.
- **A hand-built override table** (`config/district_overrides.csv`) resolving 76
  post-2011 districts to their Census parents, with creation years recorded.

### Validation

Total population across all 705 districts reconciles to Census 2011 to within
**7 people**:

```
loaded                    1,209,735,047
Census 2011 all-India     1,210,854,977
gap                           1,119,930
Chandigarh + Lakshadweep      1,119,923   ← the two UTs with no NFHS factsheet
unexplained residual                  7   ← apportionment rounding
```

---

## Repository layout

```
config/       sources, indicators, crosswalk, overrides, IPHS norms, allocation, sensitivity
sql/          01 schema · 02 analytics · 03 allocation · 04 sensitivity
src/          config, datasource, snapshot + one module per phase
app/          streamlit_app.py
tests/        82 tests across 8 files
reports/      seven generated reports — reconciliation, quality, index, allocation, sensitivity, map, residual
docs/         build-log.md — every phase, every failure, and why each decision was made
resources/    report PDF, slide deck, memo, and Codebase_Guide.pdf — start there
data/         raw (checksummed) · interim · processed · snapshot (committed)
```

`docs/build-log.md` is the most useful file here. It records what broke during
the build and what replaced it, written as it happened rather than reconstructed
afterwards.

---

## Limitations

Stated up front, because volunteering them is stronger than being caught by
them.

1. **No supply data.** District-level Sub-Centre counts are not published in
   machine readable form. This measures **need, not unmet need** — see finding 1.
   This is the project's single largest methodological weakness.
2. **Census 2011 against 2019–21 outcomes.** A decade apart. Population is not
   projected forward, because a defensible district-level growth assumption does
   not exist.
3. **Rural population is derived, not enumerated.** Computed from rural
   household share, which assumes equal mean household size in rural and urban
   areas. Rural households are larger, so rural population is understated by
   about 1.1% (824.2M derived vs 833.5M published) — conservative for our
   purpose.
4. **118 districts share a Census parent.** Population is apportioned equally
   among post-2011 siblings: unbiased in aggregate, wrong district by district.
5. **Third-party PDF extraction.** The NFHS data was parsed from published PDFs
   by a third party who documents possible errors.
6. **Seven maternal, child and nutritional indicators.** Nothing on communicable
   disease, mental health or injury. Sampling more weight vectors cannot fix a
   blind spot shared by every indicator.
7. **Terrain is assigned per district.** IPHS applies it per facility, and
   *desert* is never assigned because identifying desert blocks needs
   sub-district data. Both errors under-apply the stricter 3,000 norm.
8. **The objective ignores geography.** No travel time, no existing facility
   locations, no construction cost.

---

## Deployment

The app runs from the committed snapshot, so no database is required.

```bash
# local, reachable on the lab network
.venv/bin/streamlit run app/streamlit_app.py --server.address 0.0.0.0
```

For a public URL via Streamlit Community Cloud, see
[`docs/DEPLOY.md`](docs/DEPLOY.md). Use `requirements-app.txt` — it omits the
geospatial stack, which is the usual cause of a failed cloud build.

---

## Tech stack

PostgreSQL 16 · Python 3.12 · pandas · rapidfuzz · PuLP (CBC) · geopandas ·
plotly · Streamlit · SQLAlchemy · pytest

## Licence and attribution

Code released under the MIT Licence. Data licences are recorded per source in
`config/sources.yml` and must be honoured separately.

Authors: _(add names)_
