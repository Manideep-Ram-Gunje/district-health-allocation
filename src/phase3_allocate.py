"""Phase 3 — allocate the sanctioned Sub-Centres, three ways, and compare.

Scenarios
---------
naive_top25       Sort by need index, take 25, ignore the constraints. This is
                  what "just rank them" produces. Usually infeasible.
greedy_feasible   Walk the ranking, skip anything breaching the state cap, then
                  patch empty regions. Feasible, and roughly what a competent
                  analyst builds in a spreadsheet. The honest comparator.
optimal           Integer linear program, solved to a proven optimum by CBC.

    python -m src.phase3_allocate
"""
from __future__ import annotations

import sys

import pandas as pd
import pulp
from sqlalchemy import text

from src.config import DATA_PROCESSED, REPORTS, SQL_DIR, engine, load_yaml


def load_candidates(cx, scheme: str) -> pd.DataFrame:
    return pd.read_sql(text("""
        select s.district_id, s.nfhs_state, s.nfhs_district, s.region, s.terrain,
               s.need_index, s.rural_population, s.catchment_norm, s.coverage_gain
        from core.mv_district_score s
        where s.scheme = :scheme
        order by s.need_index desc"""), cx, params={"scheme": scheme})


# --------------------------------------------------------------------------
# baselines
# --------------------------------------------------------------------------

def naive_top25(c: pd.DataFrame, budget: int, **_) -> pd.DataFrame:
    """Top N by NEED INDEX — the headline metric a human would sort on."""
    out = c.sort_values("need_index", ascending=False).head(budget).copy()
    out["pick_rank"] = range(1, len(out) + 1)
    return out


def unconstrained_bound(c: pd.DataFrame, budget: int, **_) -> pd.DataFrame:
    """Top N by the OBJECTIVE itself, constraints ignored.

    This is the true ceiling: no feasible allocation can beat it, because
    dropping every constraint and greedily taking the largest coefficients is
    exactly the unconstrained optimum of a linear objective under a cardinality
    limit. The gap between this and `optimal` is the real price of equity.
    """
    out = c.sort_values("coverage_gain", ascending=False).head(budget).copy()
    out["pick_rank"] = range(1, len(out) + 1)
    return out


def greedy_feasible(c: pd.DataFrame, budget: int, max_per_state: int,
                    min_per_region: int) -> pd.DataFrame:
    """Rank order, honour the state cap, then repair region coverage.

    Deliberately simple — this is the spreadsheet strategy, and it is meant to
    be beatable. What it cannot do is look ahead: every pick is locally best
    and permanently committed.
    """
    picked, per_state = [], {}
    for r in c.itertuples():
        if len(picked) >= budget:
            break
        if per_state.get(r.nfhs_state, 0) >= max_per_state:
            continue
        picked.append(r.district_id)
        per_state[r.nfhs_state] = per_state.get(r.nfhs_state, 0) + 1

    idx = c.set_index("district_id")
    for region in sorted(c.region.unique()):
        if sum(idx.loc[picked, "region"] == region) >= min_per_region:
            continue
        cands = c[(c.region == region) & (~c.district_id.isin(picked))]
        if cands.empty:
            continue
        add = cands.iloc[0]
        # Drop the weakest pick whose region can spare it and whose removal
        # does not push the incoming district's state over the cap.
        counts = idx.loc[picked, "region"].value_counts()
        droppable = [d for d in picked
                     if counts.get(idx.loc[d, "region"], 0) > min_per_region]
        if not droppable:
            continue
        worst = min(droppable, key=lambda d: idx.loc[d, "need_index"])
        state_n = sum(idx.loc[d, "nfhs_state"] == add.nfhs_state
                      for d in picked if d != worst)
        if state_n >= max_per_state:
            continue
        picked[picked.index(worst)] = int(add.district_id)

    out = c[c.district_id.isin(picked)].copy()
    order = {d: i + 1 for i, d in enumerate(picked)}
    out["pick_rank"] = out.district_id.map(order)
    return out.sort_values("pick_rank")


# --------------------------------------------------------------------------
# the integer program
# --------------------------------------------------------------------------

def solve_ilp(c: pd.DataFrame, budget: int, max_per_state: int,
              min_per_region: int, time_limit: int = 60) -> tuple[pd.DataFrame, str]:
    prob = pulp.LpProblem("subcentre_allocation", pulp.LpMaximize)
    ids = c.district_id.tolist()
    x = pulp.LpVariable.dicts("site", ids, cat="Binary")
    gain = dict(zip(c.district_id, c.coverage_gain))

    # objective: need-weighted population brought within IPHS catchment
    prob += pulp.lpSum(float(gain[d]) * x[d] for d in ids)

    # budget — exactly, not at most: unspent sanctioned budget is not a virtue
    prob += pulp.lpSum(x[d] for d in ids) == budget, "budget"

    for state, g in c.groupby("nfhs_state"):
        prob += pulp.lpSum(x[d] for d in g.district_id) <= max_per_state, f"cap_{state}"

    for region, g in c.groupby("region"):
        prob += pulp.lpSum(x[d] for d in g.district_id) >= min_per_region, f"floor_{region}"

    prob.solve(pulp.PULP_CBC_CMD(msg=0, timeLimit=time_limit))
    status = pulp.LpStatus[prob.status]
    chosen = [d for d in ids if x[d].value() and x[d].value() > 0.5]
    out = c[c.district_id.isin(chosen)].copy()
    out["pick_rank"] = None
    return out, status


# --------------------------------------------------------------------------

def main() -> int:
    print("=== Phase 3: constrained allocation ===")
    cfg = load_yaml("allocation.yml")
    budget = cfg["budget"]
    cap = cfg["constraints"]["max_per_state"]
    floor = cfg["constraints"]["min_per_region"]
    scheme = load_yaml("indicators.yml")["default_scheme"]

    eng = engine()
    with eng.begin() as cx:
        cx.execute(text((SQL_DIR / "03_allocation.sql").read_text(encoding="utf-8")))

    with eng.connect() as cx:
        c = load_candidates(cx, scheme)
    print(f"  candidates: {len(c)} districts, scheme='{scheme}'")
    print(f"  budget={budget}, max_per_state={cap}, min_per_region={floor}")

    results = {
        "naive_top25": naive_top25(c, budget),
        "unconstrained_bound": unconstrained_bound(c, budget),
        "greedy_feasible": greedy_feasible(c, budget, cap, floor),
    }
    opt, status = solve_ilp(c, budget, cap, floor, cfg["solver"]["time_limit_seconds"])
    results["optimal"] = opt
    print(f"  CBC status: {status}")
    if status != "Optimal":
        print("  [FAIL] solver did not prove optimality")
        return 1

    rows = []
    for scenario, df in results.items():
        for r in df.itertuples():
            rows.append({"scenario": scenario, "scheme": scheme,
                         "district_id": int(r.district_id),
                         "pick_rank": int(r.pick_rank) if pd.notna(r.pick_rank) else None,
                         "need_index": float(r.need_index),
                         "coverage_gain": float(r.coverage_gain)})
    pd.DataFrame(rows).to_sql("allocation", eng, schema="core",
                              if_exists="append", index=False)

    with eng.connect() as cx:
        summary = pd.read_sql("select * from core.v_allocation_summary order by scenario", cx)
        picks = pd.read_sql(text("""
            select a.scenario, d.nfhs_state, d.nfhs_district, d.region, d.terrain,
                   round(a.need_index,3) need, d.rural_population rural,
                   round(a.coverage_gain,0) gain
            from core.allocation a join core.district d using (district_id)
            where a.scheme = :s order by a.scenario, a.need_index desc"""),
            cx, params={"s": scheme})

    print("\n  scenario comparison:")
    show = summary[["scenario", "facilities", "states_covered", "regions_covered",
                    "max_in_any_state", "total_coverage_gain", "states_over_cap"]]
    print("   ", show.to_string(index=False).replace("\n", "\n    "))

    g = {r.scenario: float(r.total_coverage_gain) for r in summary.itertuples()}
    m = {
        "premium_vs_greedy": (g["optimal"] - g["greedy_feasible"]) / g["greedy_feasible"],
        "premium_vs_naive": (g["optimal"] - g["naive_top25"]) / g["naive_top25"],
        "price_of_equity": (g["optimal"] - g["unconstrained_bound"]) / g["unconstrained_bound"],
    }
    print(f"\n  optimisation premium vs greedy_feasible   : {m['premium_vs_greedy']:+.2%}")
    print(f"  optimisation premium vs naive_top25       : {m['premium_vs_naive']:+.2%}")
    print(f"  price of equity vs unconstrained ceiling  : {m['price_of_equity']:+.2%}")

    out = DATA_PROCESSED / "allocation.csv"
    picks.to_csv(out, index=False)
    write_report(summary, picks, m, cfg, scheme, status, len(c))
    print(f"\n  picks  -> {out}")
    print(f"  report -> {REPORTS / 'allocation_report.md'}")
    print("\nPHASE 3 COMPLETE")
    return 0


def write_report(summary, picks, m, cfg, scheme, status, n_cand) -> None:
    budget = cfg["budget"]
    cap = cfg["constraints"]["max_per_state"]
    floor = cfg["constraints"]["min_per_region"]
    naive = picks[picks.scenario == "naive_top25"]
    opt = picks[picks.scenario == "optimal"]
    naive_states = naive.nfhs_state.value_counts()
    over = naive_states[naive_states > cap]

    L = ["# Allocation Results", "",
         f"**{budget}** Sub-Centres allocated across **{n_cand}** eligible districts, "
         f"weighting scheme `{scheme}`. Solver: CBC, status **{status}**.", "",
         "## The problem", "",
         "```",
         "maximise    sum_d  need_index_d * min(catchment_norm_d, rural_pop_d) * x_d",
         "subject to  sum_d x_d = 25                        (budget, exactly)",
         f"            sum_(d in s) x_d <= {cap}   for each state    (equity)",
         f"            sum_(d in r) x_d >= {floor}   for each region   (feasibility)",
         "            x_d in {0,1}",
         "```", "",
         "The `min()` in the objective is doing real work. One Sub-Centre cannot serve "
         "more than its catchment norm, so a district of four million and a district of "
         "forty thousand both cap out at what a single facility delivers. Without it the "
         "model would just pick the biggest districts and call that optimisation.", "",
         "## Scenario comparison", "", summary.to_markdown(index=False), "",
         "## The four scenarios, and why there are four", "",
         "| Scenario | Feasible? | What it represents |", "|---|---|---|",
         "| `naive_top25` | no | Sort by the headline need index, take 25. What "
         "\"just rank them\" means in practice. |",
         "| `unconstrained_bound` | no | Top 25 by the objective itself. The true "
         "ceiling — no feasible allocation can beat it. |",
         "| `greedy_feasible` | yes | Rank order, honour the cap, patch the regions. "
         "The spreadsheet answer. |",
         "| `optimal` | yes | The integer program, proven optimal by CBC. |", "",
         "## What optimisation actually bought", ""]

    L += [f"- **Premium vs `greedy_feasible`: {m['premium_vs_greedy']:+.2%}.** Both are "
          "feasible; the ILP finds the better one. Greedy commits to each pick "
          "permanently in rank order and cannot look ahead, so it spends early picks in "
          "states where it later needs headroom, then patches regions by evicting "
          "whichever district happens to be weakest.",
          f"- **Premium vs `naive_top25`: {m['premium_vs_naive']:+.2%}.** The optimal "
          "allocation beats the naive one *even though the naive one ignores every "
          "constraint*. This is the least intuitive number in the project and the most "
          "worth understanding — see below.",
          f"- **Price of equity: {m['price_of_equity']:+.2%}** against the unconstrained "
          "ceiling. This is the honest cost of the state cap and the region floor: what "
          "you give up to get an allocation that can actually be executed.", ""]

    L += ["### Why sorting loses even before the constraints bite", "",
          "Because the thing you sort on is not the thing you are maximising.", "",
          "The need index answers *how badly off is this district*. The objective "
          "answers *how much good does one more facility do here*, and those diverge "
          "for two structural reasons:", "",
          "1. **Coverage caps at the catchment norm.** A Sub-Centre serves at most "
          "5,000 people (3,000 in hilly or tribal terrain). A district of 4 million and "
          "one of 40,000 both receive exactly one facility's worth of coverage, but a "
          "district whose entire rural population is below the norm cannot even absorb "
          "a full facility's benefit.",
          "2. **Terrain changes the coefficient.** The same need index yields "
          "5,000-population coverage in plains and 3,000 in hilly or tribal areas.", "",
          "So the top of the need ranking is not the top of the objective ranking. "
          "Sorting by the headline metric produces a list that is both inadmissible "
          "*and* leaves value on the table — which is a stronger answer to \"why not "
          "just sort?\" than the constraint argument alone.", ""]

    if len(over):
        L += ["### Why the naive list is inadmissible anyway", "",
              f"Sorting by need index and taking the top {budget} puts:", ""]
        L += [f"- **{s} — {n} of {budget} facilities** (cap is {cap})"
              for s, n in over.items()]
        L += ["", f"and reaches only {naive.region.nunique()} of 6 regions. No State "
                  "Health Society could take that to a Finance Commission review, "
                  "whatever the need data says.", ""]

    L += ["## Optimal allocation", "",
          opt[["nfhs_state", "nfhs_district", "region", "terrain", "need", "rural", "gain"]]
             .to_markdown(index=False), "",
          "### Distribution", "",
          "| State | Facilities |", "|---|---|"]
    L += [f"| {s} | {n} |" for s, n in opt.nfhs_state.value_counts().items()]
    L += ["", "| Region | Facilities |", "|---|---|"]
    L += [f"| {r} | {n} |" for r, n in opt.region.value_counts().sort_index().items()]

    L += ["", "## Caveats", "",
          "1. The objective rewards need-weighted population within one facility's "
          "catchment. It does not model travel time, existing facility locations "
          "(unavailable — see README), or construction cost.",
          "2. Because the IPHS norm is *lower* in hilly and tribal areas (3,000 vs "
          "5,000), a facility there delivers less raw coverage gain, which mildly "
          "disadvantages those districts in the objective. They compete on need instead. "
          f"The optimal allocation contains "
          f"{int((opt.terrain != 'plains').sum())} non-plains districts. A defensible "
          "alternative is to divide coverage gain by the norm so a facility is worth "
          "the same everywhere; that is a policy choice, not a technical one, and it is "
          "exposed as a toggle rather than hardcoded.",
          "3. Weights are one defensible choice among many. Phase 4 quantifies how much "
          "of this list survives 10,000 alternative weightings."]

    (REPORTS / "allocation_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
