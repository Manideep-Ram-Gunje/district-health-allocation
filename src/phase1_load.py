"""Phase 1b — build the schema, load staging and core, emit the data quality report.

Idempotent: drops and rebuilds both schemas from data/raw + the Phase 1a
crosswalk. Nothing in the database is authored by hand.

    python -m src.phase1_reconcile     # must run first — produces the crosswalk
    python -m src.phase1_load
"""
from __future__ import annotations

import json
import re
import sys

import pandas as pd
from sqlalchemy import text

from src.config import (DATA_INTERIM, MANIFEST, REPORTS, SQL_DIR, engine,
                        load_yaml, raw_path)

NUM_RE = re.compile(r"^\s*(\d+)\.")


def parse_indicator_numbers(df: pd.DataFrame) -> pd.DataFrame:
    """Extract the leading factsheet number. See docs/build-log.md Phase 0 #4."""
    df = df.copy()
    df["indicator_id"] = df["Indicator"].str.extract(NUM_RE)[0]
    # Two rows in Maharashtra/Raigarh have a section header merged into the
    # indicator name by the PDF extractor, so the number is not leading.
    # Rescue them with a looser pattern rather than dropping silently.
    loose = df["indicator_id"].isna()
    if loose.any():
        df.loc[loose, "indicator_id"] = (
            df.loc[loose, "Indicator"].str.extract(r"(?:^|\s)(\d{1,3})\.\s*[A-Z]")[0])
    df["indicator_id"] = pd.to_numeric(df["indicator_id"], errors="coerce").astype("Int64")
    return df


def build_indicator_catalogue(nfhs: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    cfg = {i["id"]: i for i in load_yaml("indicators.yml")["indicators"]}
    ok = nfhs[nfhs.indicator_id.notna() & nfhs.indicator_id.between(1, 104)]
    variants = ok.groupby("indicator_id")["Indicator"].nunique()
    names = ok.groupby("indicator_id")["Indicator"].agg(lambda s: s.mode().iat[0])

    cat = pd.DataFrame({"indicator_id": names.index.astype(int),
                        "name_as_published": names.values,
                        "name_variants": variants.reindex(names.index).values})
    cat["indicator_key"] = cat.indicator_id.map(lambda i: cfg[i]["key"] if i in cfg else None)
    cat["domain"] = cat.indicator_id.map(lambda i: cfg[i]["domain"] if i in cfg else None)
    cat["higher_is_worse"] = cat.indicator_id.map(
        lambda i: cfg[i]["higher_is_worse"] if i in cfg else None).astype("object")
    cat["in_index"] = cat.indicator_id.isin(cfg)
    return cat, int(nfhs.indicator_id.isna().sum())


def main() -> int:
    print("=== Phase 1b: schema + load ===")
    xw_path = DATA_INTERIM / "crosswalk.csv"
    if not xw_path.exists():
        print("  [FAIL] crosswalk.csv missing — run `python -m src.phase1_reconcile` first")
        return 1

    eng = engine()
    with eng.begin() as cx:
        cx.execute(text((SQL_DIR / "01_schema.sql").read_text(encoding="utf-8")))
    print("  schema rebuilt (staging, core)")

    # --- staging ------------------------------------------------------------
    nfhs = pd.read_csv(raw_path("nfhs5_districts"), low_memory=False)
    nfhs.rename(columns={"Indicator": "indicator_text", "NFHS5": "nfhs5", "NFHS4": "nfhs4",
                         "Flag_NFHS5": "flag_nfhs5", "Flag_NFHS4": "flag_nfhs4"}
                ).to_sql("nfhs5_raw", eng, schema="staging", if_exists="append", index=False)

    cen = pd.read_csv(raw_path("census2011_districts"), low_memory=False).rename(columns={
        "District code": "census_code", "State name": "census_state",
        "District name": "census_district", "Population": "population",
        "Rural_Households": "rural_hh", "Urban_Households": "urban_hh",
        "Households": "total_hh"})
    cen[["census_code", "census_state", "census_district", "population",
         "rural_hh", "urban_hh", "total_hh"]].to_sql(
        "census2011_raw", eng, schema="staging", if_exists="append", index=False)
    print(f"  staging.nfhs5_raw       {len(nfhs):,}")
    print(f"  staging.census2011_raw  {len(cen):,}")

    # --- core.indicator -----------------------------------------------------
    nfhs = parse_indicator_numbers(nfhs.rename(columns={"indicator_text": "Indicator"}))
    cat, unparsed = build_indicator_catalogue(nfhs)
    cat.to_sql("indicator", eng, schema="core", if_exists="append", index=False)
    print(f"  core.indicator          {len(cat):,}  (in_index={int(cat.in_index.sum())}, "
          f"multi-name={int((cat.name_variants > 1).sum())}, unparsed rows={unparsed})")

    # --- core.district ------------------------------------------------------
    xw = pd.read_csv(xw_path)
    cols = ["nfhs_state", "nfhs_district", "region", "census_code", "census_state",
            "census_district", "match_score", "is_apportioned", "n_sharing_parent",
            "population_alloc", "rural_share", "rural_population"]
    d = xw.rename(columns={"tier": "match_tier"})[["match_tier"] + cols].copy()
    d["n_sharing_parent"] = d.n_sharing_parent.replace(0, 1)
    d["is_apportioned"] = d.n_sharing_parent > 1
    d.to_sql("district", eng, schema="core", if_exists="append", index=False)
    print(f"  core.district           {len(d):,}")

    # --- core.district_indicator -------------------------------------------
    with eng.connect() as cx:
        ids = pd.read_sql("select district_id, nfhs_state, nfhs_district from core.district", cx)
    fact = (nfhs.rename(columns={"state": "nfhs_state", "district": "nfhs_district"})
                .merge(ids, on=["nfhs_state", "nfhs_district"], how="inner"))
    fact = fact[fact.indicator_id.notna() & fact.indicator_id.between(1, 104)]
    fact["value_nfhs5"] = pd.to_numeric(fact["NFHS5"], errors="coerce")
    fact["value_nfhs4"] = pd.to_numeric(fact["NFHS4"], errors="coerce")
    fact = (fact[["district_id", "indicator_id", "value_nfhs5", "value_nfhs4", "Flag_NFHS5"]]
            .rename(columns={"Flag_NFHS5": "flag_nfhs5"})
            .drop_duplicates(["district_id", "indicator_id"]))
    fact.to_sql("district_indicator", eng, schema="core", if_exists="append",
                index=False, chunksize=10000)
    print(f"  core.district_indicator {len(fact):,}")

    # --- core.weight_scheme -------------------------------------------------
    schemes = load_yaml("indicators.yml")["weighting_schemes"]
    w = pd.DataFrame([{"scheme": s, "indicator_key": k, "weight": v}
                      for s, spec in schemes.items() for k, v in spec["weights"].items()])
    w.to_sql("weight_scheme", eng, schema="core", if_exists="append", index=False)
    print(f"  core.weight_scheme      {len(w):,}  ({w.scheme.nunique()} schemes)")

    # --- audit --------------------------------------------------------------
    if MANIFEST.exists():
        man = json.loads(MANIFEST.read_text())
        rows = {"nfhs5_districts": len(nfhs), "census2011_districts": len(cen)}
        pd.DataFrame([{"source_key": k, "filename": v["filename"], "sha256": v["sha256"],
                       "rows_loaded": rows.get(k)} for k, v in man.items()]
                     ).to_sql("load_audit", eng, schema="core", if_exists="append", index=False)

    write_quality_report(eng, cat, xw, unparsed)
    print(f"\n  report -> {REPORTS / 'data_quality_report.md'}")
    print("\nPHASE 1 COMPLETE")
    return 0


def write_quality_report(eng, cat: pd.DataFrame, xw: pd.DataFrame, unparsed: int) -> None:
    cfg = load_yaml("indicators.yml")
    floor = cfg["missingness"]["min_indicators_present"]
    with eng.connect() as cx:
        cover = pd.read_sql("""
            select i.indicator_id, i.indicator_key, i.domain, i.higher_is_worse,
                   count(di.value_nfhs5)                       as present,
                   count(*) - count(di.value_nfhs5)            as missing,
                   min(di.value_nfhs5) as min_v, max(di.value_nfhs5) as max_v,
                   round(avg(di.value_nfhs5), 1) as mean_v
            from core.indicator i
            join core.district_indicator di using (indicator_id)
            where i.in_index
            group by 1,2,3,4 order by 1""", cx)
        per_dist = pd.read_sql("""
            select d.nfhs_state, d.nfhs_district, count(di.value_nfhs5) as n_present
            from core.district d
            join core.district_indicator di on di.district_id = d.district_id
            join core.indicator i on i.indicator_id = di.indicator_id and i.in_index
            group by 1,2""", cx)
        totals = pd.read_sql("""
            select (select count(*) from core.district)            as districts,
                   (select count(*) from core.indicator)           as indicators,
                   (select count(*) from core.district_indicator)  as facts,
                   (select sum(rural_population) from core.district) as rural_pop""", cx)

    below = per_dist[per_dist.n_present < floor]
    L = ["# Data Quality Report", "",
         "Generated by `src/phase1_load.py` against the loaded database.", "",
         "## Volumes", "", "| Table | Rows |", "|---|---|",
         f"| `core.district` | {totals.districts[0]:,} |",
         f"| `core.indicator` | {totals.indicators[0]:,} |",
         f"| `core.district_indicator` | {totals.facts[0]:,} |",
         f"| Derived rural population | {int(totals.rural_pop[0]):,} |", "",
         "## Index indicator coverage", "",
         "`missing` counts districts with no NFHS-5 value — either genuinely absent or "
         "suppressed for small sample size. We never impute across districts.", "",
         "| # | Indicator | Domain | Higher = worse | Present | Missing | Min | Mean | Max |",
         "|---|---|---|---|---|---|---|---|---|"]
    L += [f"| {r.indicator_id} | `{r.indicator_key}` | {r.domain} | {r.higher_is_worse} "
          f"| {r.present} | {r.missing} | {r.min_v} | {r.mean_v} | {r.max_v} |"
          for r in cover.itertuples()]

    L += ["", "## Missingness floor", "",
          f"Districts must have at least **{floor} of 7** index indicators present to be "
          f"scored. Districts below the floor: **{len(below)}**."]
    if len(below):
        L += ["", "| District | Present |", "|---|---|"]
        L += [f"| {r.nfhs_state} / {r.nfhs_district} | {r.n_present} |" for r in below.itertuples()]
    else:
        L.append("\nNo district falls below the floor, so the rule never binds on this "
                 "dataset. It is retained because it should not be silently absent.")

    multi = cat[cat.name_variants > 1]
    L += ["", "## Indicator name instability", "",
          f"**{len(multi)}** of {len(cat)} indicator numbers have more than one name string "
          "in the source, from PDF extraction artefacts. This is why the pipeline keys on "
          "the factsheet number rather than the name.", ""]
    if len(multi):
        L += ["| # | Variants | In index | Name (modal) |", "|---|---|---|---|"]
        L += [f"| {r.indicator_id} | {r.name_variants} | {'**yes**' if r.in_index else 'no'} "
              f"| {r.name_as_published[:70]} |" for r in multi.itertuples()]
    L += ["", f"Rows whose indicator number could not be parsed at all: **{unparsed}**.", ""]

    tiers = xw["tier"].value_counts()
    L += ["## Crosswalk provenance", "", "| Tier | Districts |", "|---|---|"]
    L += [f"| `{k}` | {v} |" for k, v in tiers.items()]
    L += ["", f"Districts sharing a Census parent (population apportioned equally): "
              f"**{int(xw.is_apportioned.sum())}**. See `reports/reconciliation_report.md`.", "",
          "## Known limitations carried forward", "",
          "1. Census 2011 population against 2019-21 health outcomes — a decade apart. Not projected forward.",
          "2. Rural population derived from household shares, not enumerated directly. Understates rural population by roughly 1%.",
          "3. Equal apportionment across post-2011 splits is wrong district-by-district, unbiased in aggregate.",
          "4. No district-level facility counts exist in machine-readable form; the supply side falls back to state norms."]

    (REPORTS / "data_quality_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
