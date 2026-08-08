"""District Health Infrastructure Allocation — interactive allocation tool.

Everything a non-technical user can change is on the left. Every change
re-runs the real optimiser against the real database — nothing here is
precomputed or faked.

    streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.config import load_yaml                                     # noqa: E402
from src import datasource                                            # noqa: E402
from src.phase3_allocate import (check_feasible, greedy_feasible,     # noqa: E402
                                 solve_ilp)
from src.phase4_sensitivity import need_matrix, objective_gain        # noqa: E402

st.set_page_config(page_title="District Health Allocation", layout="wide",
                   initial_sidebar_state="expanded")

IND = load_yaml("indicators.yml")
ALLOC = load_yaml("allocation.yml")
INDICATORS = IND["indicators"]


# ---------------------------------------------------------------------------
# data loading (cached — the database is read once per session)
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner="Loading districts…")
def load_base():
    base, keys = datasource.load_base()
    meta_cols = ["district_id", "nfhs_state", "nfhs_district", "region", "terrain",
                 "rural_population", "catchment_norm", "is_apportioned"]
    return base[meta_cols], base[keys].to_numpy(), keys, datasource.active_source()


@st.cache_data(show_spinner="Loading sensitivity…")
def load_sensitivity():
    return datasource.load_sensitivity()


@st.cache_data(show_spinner="Loading map…")
def load_geo():
    return datasource.load_geo()


# ---------------------------------------------------------------------------
# sidebar — the controls
# ---------------------------------------------------------------------------

st.sidebar.title("Assumptions")
st.sidebar.caption("Every control re-solves the optimiser. Nothing is precomputed.")

scheme_names = list(IND["weighting_schemes"]) + ["custom…"]
picked = st.sidebar.selectbox("Weighting scheme", scheme_names, index=0,
                              help=IND["weighting_schemes"][IND["default_scheme"]]
                              ["description"].strip())

meta, P, keys, source = load_base()

if picked == "custom…":
    st.sidebar.markdown("**Indicator weights** (renormalised to sum to 1)")
    raw_w = {}
    for ind in INDICATORS:
        raw_w[ind["key"]] = st.sidebar.slider(
            ind["key"].replace("_", " "), 0.0, 1.0,
            float(IND["weighting_schemes"][IND["default_scheme"]]["weights"][ind["key"]]),
            0.01, help=ind["rationale"])
    total = sum(raw_w.values()) or 1.0
    wmap = {k: v / total for k, v in raw_w.items()}
else:
    wmap = IND["weighting_schemes"][picked]["weights"]

st.sidebar.divider()
budget = st.sidebar.slider("Sub-Centres to allocate", 5, 100, ALLOC["budget"], 1)
cap = st.sidebar.slider("Maximum per state", 1, 15,
                        ALLOC["constraints"]["max_per_state"], 1)
floor = st.sidebar.slider("Minimum per region", 0, 6,
                          ALLOC["constraints"]["min_per_region"], 1)

objective = st.sidebar.radio(
    "Objective",
    ["coverage_gain_neutral", "coverage_gain_population"],
    index=0,
    format_func=lambda s: ("Terrain-neutral (1 facility = 1 facility)"
                           if s.endswith("neutral") else
                           "Raw population coverage"),
    help="Terrain-neutral reads the IPHS norm as intended: 3,000 served in hills "
         "is equivalent to 5,000 in plains, because that is why the norm is lower. "
         "Raw population coverage favours plains by 5000/3000.")

# ---------------------------------------------------------------------------
# compute — this is the real pipeline, not a lookup
# ---------------------------------------------------------------------------

W = np.array([[wmap[k] for k in keys]])
df = meta.copy()
df["need_index"] = need_matrix(P, W)[:, 0]
df["coverage_gain"] = objective_gain(df, objective)
df["national_rank"] = df.need_index.rank(ascending=False, method="min").astype(int)

opt, status = solve_ilp(df, budget, cap, floor, time_limit=30)

st.title("District Health Infrastructure Allocation")
st.caption("NFHS-5 (2019–21) health outcomes · Census 2011 population · "
           "IPHS 2022 catchment norms · CBC integer program")
if source["kind"] == "snapshot":
    st.info(f"Running from an exported **snapshot** ({source['detail']}) rather than a "
            "live database. The optimiser is still solving for real on every change — "
            "only the underlying indicator table is a file.", icon="📦")

if status != "Optimal":
    st.error(f"**No feasible allocation exists** for these settings (solver: {status}).\n\n"
             f"With a cap of {cap} per state you cannot place {budget} facilities, or the "
             f"floor of {floor} per region cannot be met alongside the cap. "
             "This is the solver doing its job — a heuristic would have returned a "
             "plausible-looking list instead.")
    st.stop()

greedy = greedy_feasible(df, budget, cap, floor)
violations = check_feasible(opt, budget, cap, floor, df.region.unique())
naive = df.nlargest(budget, "need_index")

# ---------------------------------------------------------------------------
# headline
# ---------------------------------------------------------------------------

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Facilities", len(opt))
c2.metric("States", opt.nfhs_state.nunique())
c3.metric("Regions", f"{opt.region.nunique()} of 6")
c4.metric("Hilly / tribal", int((opt.terrain != "plains").sum()))
gap = (opt.coverage_gain.sum() - naive.coverage_gain.sum()) / naive.coverage_gain.sum()
c5.metric("vs unconstrained sort", f"{gap:+.1%}",
          help="Negative is expected and correct: the sorted list ignores the equity "
               "constraints, so it is not a better answer — it is an inadmissible one.")

if violations:
    st.error(f"Constraint violations: {violations}")

tab_alloc, tab_map, tab_cmp, tab_sens, tab_method = st.tabs(
    ["Allocation", "Map", "Versus baselines", "Confidence", "Methodology"])

# ---------------------------------------------------------------------------

with tab_alloc:
    sens = load_sensitivity()
    show = opt[["nfhs_state", "nfhs_district", "region", "terrain", "need_index",
                "national_rank", "rural_population", "is_apportioned"]].copy()
    if not sens.empty:
        centred = sens[sens.regime == "centred"][["district_id", "ilp_stability",
                                                  "classification"]]
        show = (opt[["district_id", "nfhs_state", "nfhs_district", "region", "terrain",
                     "need_index", "national_rank", "rural_population", "is_apportioned"]]
                .merge(centred, on="district_id", how="left").drop(columns="district_id"))
        st.caption("`ilp_stability` and `classification` come from the stored Phase 4 run "
                   "at the DEFAULT settings. They do not update with the sliders — "
                   "re-running 10,000 draws live would be dishonestly slow.")
    st.dataframe(show.sort_values("need_index", ascending=False),
                 use_container_width=True, hide_index=True,
                 column_config={
                     "need_index": st.column_config.ProgressColumn(
                         "Need index", min_value=0.0, max_value=1.0, format="%.3f"),
                     "ilp_stability": st.column_config.ProgressColumn(
                         "Stability", min_value=0.0, max_value=1.0, format="%.0f%%"),
                     "rural_population": st.column_config.NumberColumn(
                         "Rural population", format="%d"),
                     "is_apportioned": st.column_config.CheckboxColumn(
                         "Split district", help="Population apportioned equally from a "
                                                "Census 2011 parent district"),
                 })
    left, right = st.columns(2)
    left.markdown("**By state**")
    left.dataframe(opt.nfhs_state.value_counts().rename("facilities"),
                   use_container_width=True)
    right.markdown("**By region**")
    right.dataframe(opt.region.value_counts().rename("facilities"),
                    use_container_width=True)
    st.download_button("Download allocation (CSV)",
                       opt.to_csv(index=False).encode(), "allocation.csv", "text/csv")

# ---------------------------------------------------------------------------

with tab_map:
    gj, geo_xw = load_geo()
    if gj is None:
        st.warning("Map crosswalk not built. Run `python -m src.phase5_geo` first.")
    else:
        m = df.merge(geo_xw[["shape_id", "district_id"]], on="district_id", how="inner")
        m["selected"] = m.district_id.isin(opt.district_id)
        fig = px.choropleth(
            m, geojson=gj, locations="shape_id",
            featureidkey="properties.shapeID",
            color="need_index", color_continuous_scale="YlOrRd",
            range_color=(0, 1),
            hover_name="nfhs_district",
            hover_data={"nfhs_state": True, "terrain": True, "shape_id": False,
                        "need_index": ":.3f", "national_rank": True,
                        "rural_population": ":,", "selected": True})
        fig.update_geos(fitbounds="locations", visible=False)
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), height=620,
                          coloraxis_colorbar_title="Need")
        st.plotly_chart(fig, use_container_width=True)
        st.caption(f"{len(m)} of {len(df)} districts have a matching polygon — "
                   "see `reports/map_crosswalk_report.md`. Districts without one are "
                   "absent from the map but present in the allocation.")

# ---------------------------------------------------------------------------

with tab_cmp:
    rows = []
    for name, sel in [("optimal (ILP)", opt), ("greedy, feasible", greedy),
                      ("naive: sort by need", naive)]:
        v = check_feasible(sel, budget, cap, floor, df.region.unique())
        rows.append({"strategy": name, "coverage gain": sel.coverage_gain.sum(),
                     "states": sel.nfhs_state.nunique(),
                     "regions": sel.region.nunique(),
                     "max in one state": int(sel.nfhs_state.value_counts().max()),
                     "feasible": "yes" if not v else "NO",
                     "violations": "; ".join(v) if v else ""})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.markdown("""
**What optimisation buys, honestly.** A correctly implemented greedy usually *matches*
the ILP here — the objective is linear and the per-state caps form a partition matroid,
which is the structure greedy handles optimally. The ILP earns its place by

1. **proving** the answer cannot be beaten,
2. **detecting infeasibility** instead of returning a plausible-looking list, and
3. expressing constraints declaratively, so changing one is a line of config rather
   than a rewrite of the selection logic.

Try setting *minimum per region* to 5 with a *maximum per state* of 1 and watch the
solver refuse rather than improvise.
""")

# ---------------------------------------------------------------------------

with tab_sens:
    sens = load_sensitivity()
    if sens.empty:
        st.warning("Run `make sensitivity` to populate this tab.")
    else:
        st.markdown("From the stored Phase 4 run: 10,000 Dirichlet weight vectors per "
                    "regime, with the full ILP re-solved on 200 of them.")
        for regime in sorted(sens.regime.unique()):
            g = sens[sens.regime == regime]
            sel = g[g.district_id.isin(opt.district_id)]
            counts = sel.classification.value_counts()
            st.write(f"**{regime}** — of the currently selected {len(sel)}: "
                     f"{int(counts.get('robust', 0))} robust, "
                     f"{int(counts.get('contested', 0))} contested, "
                     f"{int(counts.get('excluded', 0))} excluded")
        merged = (opt[["district_id", "nfhs_state", "nfhs_district"]]
                  .merge(sens[sens.regime == "centred"], on="district_id", how="left"))
        fig = px.bar(merged.sort_values("ilp_stability", ascending=True),
                     x="ilp_stability", y="nfhs_district", orientation="h",
                     color="classification", height=700,
                     labels={"ilp_stability": "Share of re-solves selecting this district"})
        st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------------

with tab_method:
    st.markdown(f"""
### How a district gets its score

1. **Direction-normalise.** Four indicators are good things, three are bad things.
   Good ones become `100 - v` so higher always means greater need.
2. **Percentile-rank nationally.** Institutional births spans ~20–100; stunting spans
   6–60. Averaging raw values would let the widest-spread indicator dominate while the
   weights claimed otherwise. Ranking puts all seven on one scale, so the weights are
   the only thing that matters.
3. **Weighted mean over present indicators**, weights renormalised. No district is ever
   imputed from another.

### Objective

`{objective}` — see the sidebar toggle. The choice moves roughly 9 of 25 districts and
decides whether hilly and tribal districts appear at all.

### What this is not

A portfolio project on public data. **Not a policy recommendation.** The largest
weaknesses, stated rather than buried:

- **No supply data.** District-level facility counts are not published in machine
  readable form, so this measures *need*, not *unmet need*. Substituting norm-implied
  supply makes the adjustment cancel algebraically — `core.v_supply_degeneracy` proves
  it on the real data.
- **Census 2011 against 2019–21 outcomes.** A decade apart, with no projection.
- **118 districts share a Census parent** after post-2011 splits; their population is
  apportioned equally, which is unbiased in aggregate and wrong district by district.
- **Seven maternal, child and nutritional indicators.** Nothing on communicable
  disease, mental health or injury. No amount of weight sampling fixes a shared blind
  spot.
""")
