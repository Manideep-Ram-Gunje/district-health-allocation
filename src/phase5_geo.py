"""Phase 5a — join map polygons to our districts, so the choropleth is honest.

The geoBoundaries ADM2 file has an EMPTY `shapeISO` on every feature, so it
carries no state. Matching 735 district names against ours nationally would
confuse the Aurangabad in Maharashtra with the one in Bihar, the Bilaspur in
Chhattisgarh with the one in Himachal, and so on — and a choropleth that
colours the wrong polygon is worse than no map, because it looks authoritative.

So state is recovered geometrically: each district polygon's representative
point is spatially joined into the ADM1 state polygons. Name matching is then
restricted within state, exactly as in Phase 1.

    python -m src.phase5_geo
"""
from __future__ import annotations

import sys

import geopandas as gpd
import pandas as pd
from rapidfuzz import fuzz, process

from src.config import DATA_INTERIM, REPORTS, engine, load_yaml, raw_path
from src.phase1_reconcile import directional, norm

ACCEPT = 82     # lower than Phase 1: map names are noisier, and a wrong colour
                # is less costly than a wrong population — but the directional
                # guard still applies, so siblings cannot be confused.


def resolve_states(districts: gpd.GeoDataFrame, states: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Attach each district polygon to the state polygon containing it."""
    states = states[["shapeName", "geometry"]].rename(columns={"shapeName": "geo_state"})
    pts = districts.copy()
    # representative_point() is guaranteed to lie INSIDE the polygon, unlike
    # centroid() which can fall outside a concave or multipart shape.
    pts["geometry"] = pts.representative_point()
    joined = gpd.sjoin(pts, states, how="left", predicate="within")
    joined = joined[~joined.index.duplicated(keep="first")]
    districts = districts.copy()
    districts["geo_state"] = joined["geo_state"]
    return districts


def main() -> int:
    print("=== Phase 5a: map polygon crosswalk ===")
    adm2 = gpd.read_file(raw_path("district_boundaries"))
    adm1 = gpd.read_file(raw_path("state_boundaries"))
    print(f"  polygons: {len(adm2)} districts, {len(adm1)} states")

    adm2 = resolve_states(adm2, adm1)
    unresolved = int(adm2.geo_state.isna().sum())
    print(f"  state resolved for {len(adm2) - unresolved}/{len(adm2)} polygons "
          f"({unresolved} unresolved)")

    with engine().connect() as cx:
        ours = pd.read_sql("""
            select district_id, nfhs_state, nfhs_district from core.district""", cx)

    # Map ADM1 state names onto NFHS state names (34 of them) by fuzzy match.
    nfhs_states = sorted(ours.nfhs_state.unique())
    nfhs_norm = {norm(s): s for s in nfhs_states}
    state_map, unmapped_states = {}, []
    for gs in sorted(adm2.geo_state.dropna().unique()):
        m = process.extractOne(norm(gs), list(nfhs_norm), scorer=fuzz.token_sort_ratio)
        if m and m[1] >= 70:
            state_map[gs] = nfhs_norm[m[0]]
        else:
            unmapped_states.append(gs)
    adm2["nfhs_state"] = adm2.geo_state.map(state_map)
    if unmapped_states:
        print(f"  [note] ADM1 states with no NFHS counterpart: {unmapped_states}")

    rows = []
    for r in adm2.itertuples():
        rec = {"shape_id": r.shapeID, "shape_name": r.shapeName,
               "geo_state": r.geo_state, "nfhs_state": r.nfhs_state,
               "district_id": pd.NA, "score": pd.NA, "note": ""}
        if pd.isna(r.nfhs_state):
            rec["note"] = "state unresolved"
            rows.append(rec)
            continue
        pool = ours[ours.nfhs_state == r.nfhs_state]
        if pool.empty:
            rec["note"] = "no NFHS districts in this state"
            rows.append(rec)
            continue
        key = norm(r.shapeName)
        cand = [norm(x) for x in pool.nfhs_district]
        m = process.extractOne(key, cand, scorer=fuzz.token_sort_ratio)
        if m and m[1] >= ACCEPT:
            hit = pool.iloc[m[2]]
            if directional(key) != directional(cand[m[2]]):
                rec["note"] = f"refused '{hit.nfhs_district}' ({m[1]:.0f}): directional mismatch"
            else:
                rec |= {"district_id": int(hit.district_id), "score": float(m[1])}
        elif m:
            rec["note"] = f"best '{pool.iloc[m[2]].nfhs_district}' scored {m[1]:.0f}"
        rows.append(rec)

    xw = pd.DataFrame(rows)

    # Enforce a 1:1 polygon <-> district mapping.
    #
    # Two polygons can match the same district when geoBoundaries splits a unit
    # we hold as one, or when a genuinely different district scores just above
    # threshold against the same name. Colouring two polygons from one district's
    # score would silently overstate that district's geographic footprint on the
    # map, so only the BEST-scoring polygon keeps the district and the runner-up
    # is released as unmatched, with the reason recorded.
    xw["score"] = pd.to_numeric(xw.score, errors="coerce")
    dropped = 0
    have = xw.dropna(subset=["district_id"])
    for did, g in have.groupby("district_id"):
        if len(g) < 2:
            continue
        keep = g.score.idxmax()
        for i in g.index:
            if i != keep:
                xw.loc[i, "note"] = (f"released: '{xw.loc[keep, 'shape_name']}' "
                                     f"matched district {int(did)} better "
                                     f"({xw.loc[keep, 'score']:.0f} vs {xw.loc[i, 'score']:.0f})")
                xw.loc[i, "district_id"] = pd.NA
                xw.loc[i, "score"] = pd.NA
                dropped += 1

    matched = int(xw.district_id.notna().sum())
    covered = xw.district_id.dropna().nunique()
    dupes = int(xw.dropna(subset=["district_id"]).duplicated("district_id").sum())
    if dropped:
        print(f"  released {dropped} duplicate polygon(s) to keep the mapping 1:1")

    out = DATA_INTERIM / "geo_crosswalk.csv"
    xw.to_csv(out, index=False)

    print(f"  polygons matched      : {matched}/{len(xw)} ({matched/len(xw):.1%})")
    print(f"  our districts covered : {covered}/{len(ours)} ({covered/len(ours):.1%})")
    print(f"  polygons sharing a district_id: {dupes}")

    unmatched_ours = set(ours.district_id) - set(xw.district_id.dropna().astype(int))
    L = ["# Map Crosswalk", "",
         "geoBoundaries ADM2 polygons matched to NFHS-5 districts.", "",
         "The ADM2 file carries an **empty `shapeISO`** on every feature, so it has no "
         "state column. Matching district names nationally would confuse same-named "
         "districts in different states, and a choropleth that colours the wrong "
         "polygon is worse than no map because it still looks authoritative.", "",
         "State is therefore recovered geometrically: each district polygon's "
         "*representative point* — guaranteed to lie inside the polygon, unlike a "
         "centroid, which can fall outside a concave or multipart shape — is spatially "
         "joined into the ADM1 state polygons. Name matching is then restricted within "
         "state, and the Phase 1 directional guard still applies.", "",
         "## Coverage", "", "| Metric | Value |", "|---|---|",
         f"| ADM2 polygons | {len(xw)} |",
         f"| State resolved by spatial join | {len(adm2) - unresolved} |",
         f"| Polygons matched to a district | {matched} ({matched/len(xw):.1%}) |",
         f"| Our districts with a polygon | {covered} of {len(ours)} ({covered/len(ours):.1%}) |",
         f"| Duplicate polygons released to keep 1:1 | {dropped} |",
         f"| Polygons sharing a district_id (must be 0) | {dupes} |", "",
         "## Districts with no polygon", "",
         "These will be absent from the choropleth. The map is an illustration; the "
         "allocation table is the deliverable, and it is unaffected.", ""]
    if unmatched_ours:
        miss = ours[ours.district_id.isin(unmatched_ours)]
        L += ["| State | District |", "|---|---|"]
        L += [f"| {r.nfhs_state} | {r.nfhs_district} |"
              for r in miss.sort_values(["nfhs_state", "nfhs_district"]).itertuples()]
    else:
        L.append("_None._")

    (REPORTS / "map_crosswalk_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"  crosswalk -> {out}")
    print(f"  report    -> {REPORTS / 'map_crosswalk_report.md'}")

    if dupes:
        print("  [FAIL] a district_id is claimed by more than one polygon")
        return 1
    if covered / len(ours) < 0.80:
        print("  [WARN] fewer than 80% of districts have a polygon")
    print("\nPHASE 5a COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
