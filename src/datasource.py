"""Single data-access layer: Postgres when available, snapshot files otherwise.

The app must run in two very different places:

  * a lab machine with the full Postgres pipeline behind it, and
  * a cloud deployment or a fresh clone, with no database at all.

Rather than maintain two apps, everything goes through here. Postgres is tried
first and is always preferred; the snapshot is a fallback, never a substitute
for the pipeline. `active_source()` reports which one answered, and the app
displays it — a dashboard that silently serves stale files while looking live
is exactly the kind of thing that destroys trust in an analysis.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.config import DATA_INTERIM, DATA_PROCESSED, engine, raw_path

SNAP = DATA_PROCESSED / "snapshot"
_SOURCE = {"kind": "unknown", "detail": ""}


def active_source() -> dict:
    return dict(_SOURCE)


def _snapshot_available() -> bool:
    return (SNAP / "districts.parquet").exists()


def _try_db(query_fn):
    try:
        with engine().connect() as cx:
            out = query_fn(cx)
        _SOURCE.update(kind="postgres", detail="live database")
        return out
    except Exception:                                        # noqa: BLE001
        return None


def load_base() -> tuple[pd.DataFrame, list[str]]:
    """District metadata plus the indicator percentile matrix."""
    def q(cx):
        pct = pd.read_sql("""
            select p.district_id, p.indicator_key, p.need_percentile
            from core.mv_indicator_percentile p
            where p.district_id in (select district_id from core.mv_district_score)""", cx)
        meta = pd.read_sql("""
            select distinct d.district_id, d.nfhs_state, d.nfhs_district, d.region,
                   d.terrain, d.rural_population, d.catchment_norm, d.is_apportioned
            from core.district d
            join core.mv_district_score s using (district_id)""", cx)
        wide = pct.pivot(index="district_id", columns="indicator_key",
                         values="need_percentile").astype(float)
        return meta.set_index("district_id").join(wide, how="inner").reset_index()

    got = _try_db(q)
    if got is None:
        if not _snapshot_available():
            raise RuntimeError(
                "No data source. Either start Postgres and run `make pipeline`, "
                "or generate a snapshot with `make snapshot`.")
        got = pd.read_parquet(SNAP / "districts.parquet")
        man = json.loads((SNAP / "manifest.json").read_text())
        _SOURCE.update(kind="snapshot", detail=f"exported {man['exported_utc']}")

    meta_cols = ["district_id", "nfhs_state", "nfhs_district", "region", "terrain",
                 "rural_population", "catchment_norm", "is_apportioned"]
    keys = [c for c in got.columns if c not in meta_cols]
    return got, sorted(keys)


def load_sensitivity() -> pd.DataFrame:
    got = _try_db(lambda cx: pd.read_sql("""
        select district_id, regime, ilp_stability, rank_stability, classification
        from core.weight_sensitivity""", cx))
    if got is not None:
        return got
    p = SNAP / "sensitivity.parquet"
    return pd.read_parquet(p) if p.exists() else pd.DataFrame()


def load_geo():
    """(geojson dict, crosswalk) — snapshot geometry preferred: it is far smaller."""
    snap_gj = SNAP / "districts.geojson"
    if snap_gj.exists():
        with open(snap_gj, "r", encoding="utf-8") as fh:
            gj = json.load(fh)
        xw = pd.DataFrame([{"shape_id": f["properties"]["shapeID"],
                            "district_id": int(f["properties"]["district_id"])}
                           for f in gj["features"]])
        return gj, xw

    xw_path = DATA_INTERIM / "geo_crosswalk.csv"
    raw = Path(raw_path("district_boundaries"))
    if not xw_path.exists() or not raw.exists():
        return None, None
    xw = pd.read_csv(xw_path).dropna(subset=["district_id"])
    xw["district_id"] = xw.district_id.astype(int)
    with open(raw, "r", encoding="utf-8") as fh:
        gj = json.load(fh)
    return gj, xw[["shape_id", "district_id"]]
