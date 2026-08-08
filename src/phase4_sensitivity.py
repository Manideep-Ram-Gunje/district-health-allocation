"""Phase 4 — how much of the answer is the data, and how much is the weights?

Samples weight vectors, recomputes the Need Index on every draw, and asks two
questions that are easy to confuse:

  rank stability  does this district stay in the top 25 BY NEED INDEX?
  ILP stability   does this district stay in the ALLOCATION once the equity
                  constraints are re-imposed?

For an allocated district the second is the meaningful one. The constrained
optimum deliberately reaches outside the national top 25 — it must, since the
cap forbids 12 picks from Bihar and the floor demands every region. Judging
allocated districts by rank stability alone mislabels precisely the districts
the equity constraints exist to protect.

Run under two regimes: a uniform stress test and a realistic centred one.

    python -m src.phase4_sensitivity
"""
from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd
from sqlalchemy import text

from src.config import DATA_PROCESSED, REPORTS, SQL_DIR, engine, load_yaml, weights
from src.phase3_allocate import solve_ilp


def load_percentile_matrix(cx, scheme: str):
    """Districts x indicators matrix of percentile ranks, NaN where absent."""
    long = pd.read_sql(text("""
        select p.district_id, p.indicator_key, p.need_percentile
        from core.mv_indicator_percentile p
        join core.mv_district_score s
          on s.district_id = p.district_id and s.scheme = :scheme"""),
        cx, params={"scheme": scheme})
    wide = long.pivot(index="district_id", columns="indicator_key",
                      values="need_percentile").astype(float)
    meta = pd.read_sql(text("""
        select d.district_id, d.nfhs_state, d.nfhs_district, d.region, d.terrain,
               d.rural_population, d.catchment_norm
        from core.district d
        join core.mv_district_score s using (district_id)
        where s.scheme = :scheme"""), cx, params={"scheme": scheme})
    meta = meta.set_index("district_id").loc[wide.index].reset_index()
    return meta, wide.to_numpy(), list(wide.columns)


def need_matrix(P: np.ndarray, W: np.ndarray) -> np.ndarray:
    """Need index for every district (rows) under every weight vector (cols).

    Weights are renormalised over PRESENT indicators per district, exactly as
    the SQL layer does — otherwise a district missing one indicator would be
    scored against a weight vector that no longer sums to 1.
    """
    mask = ~np.isnan(P)
    P0 = np.nan_to_num(P, nan=0.0)
    numer = P0 @ W.T
    denom = mask.astype(float) @ W.T
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(denom > 0, numer / denom, np.nan)


def rank_matrix(N: np.ndarray) -> np.ndarray:
    """Dense 1-based ranks per column; rank 1 = highest need."""
    order = np.argsort(-N, axis=0, kind="stable")
    ranks = np.empty_like(order)
    rows = np.arange(N.shape[0])[:, None]
    np.put_along_axis(ranks, order, np.broadcast_to(rows, order.shape), axis=0)
    return ranks + 1


def sample_weights(regime: dict, keys: list[str], base: dict,
                   draws: int, rng) -> np.ndarray:
    n = len(keys)
    if regime["kind"] == "dirichlet_flat":
        return rng.dirichlet(np.full(n, regime["alpha"]), size=draws)
    if regime["kind"] == "dirichlet_centred":
        w0 = np.array([base[k] for k in keys], dtype=float)
        w0 = w0 / w0.sum()
        return rng.dirichlet(w0 * regime["concentration"], size=draws)
    raise ValueError(f"unknown regime kind: {regime['kind']}")


def run_regime(name, regime, meta, P, keys, base, cfg, acfg, allocated, rng):
    draws, top_n = cfg["draws"], cfg["top_n"]
    W = sample_weights(regime, keys, base, draws, rng)

    t0 = time.time()
    N = need_matrix(P, W)
    ranks = rank_matrix(N)
    in_top = ranks <= top_n
    print(f"    {draws:,} draws recomputed in {time.time() - t0:.1f}s")

    res = pd.DataFrame({
        "district_id": meta.district_id,
        "regime": name,
        "draws": draws,
        "times_in_top_n": in_top.sum(axis=1),
        "mean_need_index": N.mean(axis=1),
        "p05_need_index": np.percentile(N, 5, axis=1),
        "p95_need_index": np.percentile(N, 95, axis=1),
        "mean_rank": ranks.mean(axis=1),
        "best_rank": ranks.min(axis=1),
        "worst_rank": ranks.max(axis=1),
    })
    res["rank_stability"] = res.times_in_top_n / draws

    # --- the harder test: re-solve the ILP under sampled weights ------------
    runs = int(cfg.get("ilp_runs", 0))
    budget = acfg["budget"]
    cap, floor = acfg["constraints"]["max_per_state"], acfg["constraints"]["min_per_region"]
    counter = pd.Series(0, index=meta.district_id)
    t0 = time.time()
    idx = rng.choice(draws, size=min(runs, draws), replace=False)
    base_df = meta.copy()
    solved = 0
    for dr in idx:
        base_df["need_index"] = N[:, dr]
        base_df["coverage_gain"] = base_df.need_index * np.minimum(
            base_df.catchment_norm, base_df.rural_population)
        picked, status = solve_ilp(base_df, budget, cap, floor, time_limit=30)
        if status == "Optimal":
            counter.loc[picked.district_id] += 1
            solved += 1
    print(f"    {solved} ILP re-solves in {time.time() - t0:.0f}s")

    res["ilp_runs"] = solved
    res["times_allocated"] = res.district_id.map(counter).fillna(0).astype(int)
    res["ilp_stability"] = res.times_allocated / max(solved, 1)

    # Classification uses ILP stability — the operationally meaningful measure.
    hi, lo = cfg["thresholds"]["robust"], cfg["thresholds"]["excluded"]
    s = res.ilp_stability
    res["classification"] = np.select([s > hi, s < lo], ["robust", "excluded"],
                                      default="contested")
    return res


def main() -> int:
    print("=== Phase 4: weight sensitivity ===")
    cfg = load_yaml("sensitivity.yml")
    acfg = load_yaml("allocation.yml")
    scheme = load_yaml("indicators.yml")["default_scheme"]

    eng = engine()
    with eng.begin() as cx:
        cx.execute(text((SQL_DIR / "04_sensitivity.sql").read_text(encoding="utf-8")))
    with eng.connect() as cx:
        meta, P, keys = load_percentile_matrix(cx, scheme)
        allocated = set(pd.read_sql(
            "select district_id from core.allocation where scenario='optimal'",
            cx).district_id)

    print(f"  districts={P.shape[0]}, indicators={P.shape[1]}, allocated={len(allocated)}")
    base = weights(scheme)
    rng = np.random.default_rng(cfg["seed"])

    frames = []
    for name, regime in cfg["regimes"].items():
        print(f"\n  regime '{name}' ({regime['kind']}):")
        frames.append(run_regime(name, regime, meta, P, keys, base, cfg,
                                 acfg, allocated, rng))
    res = pd.concat(frames, ignore_index=True)
    res.to_sql("weight_sensitivity", eng, schema="core", if_exists="append", index=False)

    with eng.connect() as cx:
        conf = pd.read_sql(
            "select * from core.v_allocation_confidence "
            "order by ilp_stability_centred desc nulls last", cx)

    print("\n  of the 25 allocated districts:")
    for regime, col in (("centred", "classification_centred"),
                        ("uniform", "classification_uniform")):
        c = conf[col].value_counts()
        print(f"    {regime:<9} robust={int(c.get('robust',0)):>2}  "
              f"contested={int(c.get('contested',0)):>2}  "
              f"excluded={int(c.get('excluded',0)):>2}")

    out = DATA_PROCESSED / "weight_sensitivity.csv"
    res.merge(meta, on="district_id").to_csv(out, index=False)
    write_report(res, conf, cfg)
    print(f"\n  detail -> {out}")
    print(f"  report -> {REPORTS / 'sensitivity_report.md'}")
    print("\nPHASE 4 COMPLETE")
    return 0


def write_report(res, conf, cfg) -> None:
    hi, lo = cfg["thresholds"]["robust"], cfg["thresholds"]["excluded"]
    cc = conf.classification_centred.value_counts()
    cu = conf.classification_uniform.value_counts()
    n_rob_c, n_con_c = int(cc.get("robust", 0)), int(cc.get("contested", 0))

    L = ["# Weight Sensitivity", "",
         f"{cfg['draws']:,} weight vectors per regime, seed {cfg['seed']}. The Need "
         f"Index is recomputed and every district re-ranked on each draw, and the full "
         f"ILP is re-solved on {cfg['ilp_runs']} sampled draws per regime.", "",
         "## Why this exists", "",
         "The weight vector is the least defensible choice in the methodology. It "
         "encodes a value judgement — whether child stunting matters as much as "
         "institutional births — and no amount of data settles it. The honest move is "
         "not to defend one vector but to measure how much the answer depends on it.", "",
         "## Two regimes", "",
         "| Regime | Sampling | What it represents |", "|---|---|---|",
         "| `centred` | Dirichlet centred on the default weights, concentration 50 | "
         "Plausible committee disagreement — the range a room of specialists would "
         "actually argue over. |",
         "| `uniform` | Dirichlet(1,...,1), uniform on the simplex | Adversarial stress "
         "test. Includes vectors putting 80% on one indicator. Nobody would defend "
         "those, which is the point. |", "",
         "## Two questions, and they are not the same", "",
         "**`rank_stability`** — does this district stay in the top 25 *by need index*? "
         "This ignores the equity constraints entirely.", "",
         "**`ilp_stability`** — does this district stay in the *allocation*, once the "
         "4-per-state cap and 1-per-region floor are re-imposed?", "",
         "For an allocated district the second is the meaningful one, and the "
         "distinction is not academic. The constrained optimum **deliberately reaches "
         "outside the national top 25** — it has to, because the cap forbids taking 12 "
         "districts from Bihar and the floor requires reaching all six regions. A "
         "district can therefore be a sound allocation choice while almost never "
         "appearing in the unconstrained top 25.", "",
         "Classifying allocated districts by rank stability alone would mislabel "
         "exactly those districts the equity constraints exist to protect. "
         "Classification below therefore uses `ilp_stability`.", "",
         "## Result", "",
         f"Of the 25 allocated districts, under **plausible disagreement** "
         f"(`centred`): **{n_rob_c} robust**, {n_con_c} contested, "
         f"{int(cc.get('excluded', 0))} excluded.", "",
         f"Under the **adversarial stress test** (`uniform`): "
         f"{int(cu.get('robust', 0))} robust, {int(cu.get('contested', 0))} contested, "
         f"{int(cu.get('excluded', 0))} excluded.", "",
         f"Thresholds: robust > {hi:.0%}, excluded < {lo:.0%}, contested between.", "",
         "## The allocated 25", "",
         conf[["nfhs_state", "nfhs_district", "region", "terrain",
               "ilp_stability_centred", "classification_centred",
               "ilp_stability_uniform", "rank_stability_centred",
               "mean_rank"]].to_markdown(index=False), ""]

    contested = conf[conf.classification_centred == "contested"]
    if len(contested):
        L += ["### Contested districts", "",
              "Not errors — these are the districts whose selection genuinely depends "
              "on what you decided to value. Naming them is stronger than implying the "
              "list is uniformly solid.", ""]
        for r in contested.itertuples():
            L.append(f"- **{r.nfhs_district}, {r.nfhs_state}** "
                     f"({r.region}) — allocated in {r.ilp_stability_centred:.0%} of "
                     f"re-solves, mean need rank {r.mean_rank:.0f}")
        L.append("")

    L += ["## What this does and does not establish", "",
          "It establishes that the robust districts are not artefacts of one weighting "
          "choice — they survive both realistic and adversarial re-weighting.", "",
          "It does **not** establish that they are the right places to build. The index "
          "rests on Census 2011 population against 2019-21 health outcomes, third-party "
          "PDF extraction, equal apportionment across post-2011 district splits, and a "
          "supply side that could not be measured at all. None of those limitations is "
          "touched by how many weight vectors you sample.", "",
          "Sampling more weight vectors cannot fix a biased indicator set. If all seven "
          "indicators share a blind spot — and they are all maternal, child and "
          "nutritional, with nothing on communicable disease, mental health or injury — "
          "every draw inherits it."]

    (REPORTS / "sensitivity_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
