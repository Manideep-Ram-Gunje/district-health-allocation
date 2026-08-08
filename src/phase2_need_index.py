"""Phase 2 — build the analytics layer and report on the Need Index.

Runs sql/02_analytics.sql, then interrogates the result: index distribution,
the top of the ranking, how much the weighting scheme moves things, and the
supply-degeneracy check.

    python -m src.phase2_need_index
"""
from __future__ import annotations

import sys

import pandas as pd
from sqlalchemy import text

from src.config import DATA_PROCESSED, REPORTS, SQL_DIR, engine, load_yaml


def q(cx, sql: str, **kw) -> pd.DataFrame:
    return pd.read_sql(text(sql), cx, params=kw)


def main() -> int:
    print("=== Phase 2: analytics layer + Need Index ===")
    eng = engine()
    with eng.begin() as cx:
        cx.execute(text((SQL_DIR / "02_analytics.sql").read_text(encoding="utf-8")))
    print("  materialised views rebuilt")

    default = load_yaml("indicators.yml")["default_scheme"]

    with eng.connect() as cx:
        counts = q(cx, """
            select 'mv_indicator_score' v, count(*) n from core.mv_indicator_score
            union all select 'mv_indicator_percentile', count(*) from core.mv_indicator_percentile
            union all select 'mv_need_index', count(*) from core.mv_need_index
            union all select 'mv_district_score', count(*) from core.mv_district_score
            union all select 'mv_peer_benchmark', count(*) from core.mv_peer_benchmark
            order by 1""")
        for r in counts.itertuples():
            print(f"    {r.v:<26} {r.n:,}")

        # --- the degeneracy proof ------------------------------------------
        deg = q(cx, """select count(*) n, min(ratio_check) lo, max(ratio_check) hi
                       from core.v_supply_degeneracy where scheme = :s""", s=default)
        ok = float(deg.lo[0]) == 1.0 and float(deg.hi[0]) == 1.0
        print(f"\n  supply degeneracy check: ratio_check in "
              f"[{deg.lo[0]}, {deg.hi[0]}] across {deg.n[0]} districts "
              f"-> {'CONFIRMED: adjustment cancels exactly' if ok else 'UNEXPECTED'}")

        dist = q(cx, """select scheme, count(*) n, round(min(need_index),4) lo,
                               round(avg(need_index),4) mean, round(max(need_index),4) hi,
                               round(stddev(need_index),4) sd
                        from core.mv_district_score group by 1 order by 1""")
        print("\n  need index distribution by scheme:")
        print("   ", dist.to_string(index=False).replace("\n", "\n    "))

        top = q(cx, """
            select b.national_rank rk, s.nfhs_state, s.nfhs_district, s.terrain,
                   round(s.need_index,3) need, s.rural_population rural,
                   round(s.population_at_risk) at_risk, s.indicators_present ind
            from core.mv_district_score s
            join core.mv_peer_benchmark b using (district_id, scheme)
            where s.scheme = :s order by b.national_rank limit 15""", s=default)
        print(f"\n  top 15 by need index ({default}):")
        print("   ", top.to_string(index=False).replace("\n", "\n    "))

        # --- how much does the weighting scheme matter? --------------------
        overlap = q(cx, """
            with r as (select scheme, district_id,
                              rank() over (partition by scheme order by need_index desc) rk
                       from core.mv_district_score)
            select a.scheme sa, b.scheme sb,
                   count(*) filter (where a.rk <= 25 and b.rk <= 25) shared
            from r a join r b using (district_id)
            where a.scheme < b.scheme group by 1,2 order by 1,2""")
        print("\n  top-25 overlap between weighting schemes (of 25):")
        print("   ", overlap.to_string(index=False).replace("\n", "\n    "))

        export = q(cx, """
            select s.*, b.national_rank, b.state_rank, b.gap_to_state_mean
            from core.mv_district_score s
            join core.mv_peer_benchmark b using (district_id, scheme)
            where s.scheme = :s order by b.national_rank""", s=default)

    out = DATA_PROCESSED / "district_scores.csv"
    export.to_csv(out, index=False)
    write_report(export, dist, overlap, top, default, ok)
    print(f"\n  scores -> {out}")
    print(f"  report -> {REPORTS / 'need_index_report.md'}")
    print("\nPHASE 2 COMPLETE")
    return 0 if ok else 1


def write_report(export, dist, overlap, top, default, degeneracy_ok) -> None:
    ind = load_yaml("indicators.yml")
    L = ["# Composite Need Index", "",
         f"Default weighting scheme: **`{default}`**. "
         f"{len(export)} districts scored.", "",
         "## How the index is built", "",
         "1. **Direction-normalise.** Four of seven indicators are good things "
         "(institutional births, ANC visits, skilled attendance, immunisation) and three "
         "are bad things (stunting, anaemia — and note stunting and anaemia are already "
         "need-positive). Good indicators are inverted as `100 - v` so that after this "
         "step higher always means greater need.",
         "2. **Percentile-rank within the national distribution.** Raw values are not "
         "comparable across indicators — institutional births spans roughly 20-100 while "
         "stunting spans 6-60. Averaging raw values would let the widest-spread indicator "
         "dominate by accident. Percentile ranking puts every indicator on an identical "
         "0-1 scale so the weight vector is the only thing that determines influence.",
         "3. **Weighted mean over present indicators.** Weights are renormalised across "
         "the indicators a district actually has, so a district missing one is scored on "
         "the six it has. No cross-district imputation is performed anywhere.", "",
         "## Indicators", "",
         "| # | Indicator | Domain | Direction | Weight (default) |", "|---|---|---|---|---|"]
    w = ind["weighting_schemes"][default]["weights"]
    L += [f"| {i['id']} | `{i['key']}` | {i['domain']} | "
          f"{'higher = worse' if i['higher_is_worse'] else 'inverted'} "
          f"| {w[i['key']]:.4f} |" for i in ind["indicators"]]

    L += ["", "## Distribution by scheme", "", dist.to_markdown(index=False), "",
          "## Sensitivity of the top 25 to the weighting scheme", "",
          "Districts shared between the top 25 of each pair of schemes:", "",
          overlap.to_markdown(index=False), "",
          "This is a first look at the question Phase 4 answers properly with 10,000 "
          "Dirichlet-sampled weight vectors. If the schemes disagreed wildly here, the "
          "index would be an artefact of the weights rather than of the data.", "",
          "## Top 15 districts", "", top.to_markdown(index=False), "",
          "## Finding: the supply adjustment cancels", ""]
    L += [
        "Spec section 6.3 defines underservice as population at risk divided by existing "
        "facilities, falling back to *norm-implied* facilities where counts are "
        "unavailable. District-level facility counts are unavailable (Phase 0), so the "
        "fallback applies. Substituting it:", "",
        "```",
        "underservice = (need x rural_pop) / (rural_pop / norm)",
        "             =  need x norm",
        "```", "",
        "The population term cancels exactly. A 'supply-adjusted' underservice score "
        "would be nothing but the need index multiplied by a terrain constant — it "
        "would carry no information about existing infrastructure at all, while looking "
        "like it did.", "",
        f"`core.v_supply_degeneracy` demonstrates this on the real data: `ratio_check` "
        f"equals 1.0 for every district "
        f"({'confirmed' if degeneracy_ok else 'NOT CONFIRMED — investigate'}).", "",
        "**Consequence.** No supply-adjusted score is shipped. Supply enters the model "
        "only through the terrain-specific IPHS catchment norm in `coverage_gain`. "
        "This is a real limitation of the available data, and volunteering it is "
        "stronger than shipping a formula that cancels.", ""]

    (REPORTS / "need_index_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
