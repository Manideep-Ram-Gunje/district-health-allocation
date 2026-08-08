"""Phase 1a — reconcile NFHS-5 (2019-21) districts against Census 2011 districts.

The two vintages disagree. Districts were renamed (Bangalore -> Bengaluru
Urban), split (Bardhaman -> Purba + Paschim), and whole states were created
(Telangana in 2014, Ladakh in 2019) after the 2011 enumeration. There is no
official crosswalk published in machine-readable form, so we build one and
report its quality honestly rather than asserting it worked.

Resolution is a three-tier waterfall, and every district lands in exactly one
tier:

  1. override   - manual entry in config/district_overrides.csv (always wins)
  2. fuzzy      - rapidfuzz match within candidate Census states, >= threshold
  3. unmatched  - reported, and excluded from allocation

Where several NFHS districts resolve to one Census district (a post-2011
split), Census population is apportioned EQUALLY among the children and the
rows are flagged. Equal apportionment is wrong in detail but unbiased in
aggregate, and it is stated rather than hidden.

    python -m src.phase1_reconcile
"""
from __future__ import annotations

import re
import sys
import unicodedata

import pandas as pd
from rapidfuzz import fuzz, process

from src.config import DATA_INTERIM, REPORTS, load_yaml, raw_path, CONFIG_DIR

ACCEPT = 90      # >= this: accepted as a match
REVIEW = 80      # >= this but < ACCEPT: accepted but flagged for eyeballing

_NOISE = re.compile(r"\b(district|dist|zila|zilla|pargana|division)\b")
_NONAL = re.compile(r"[^a-z0-9 ]")
_WS = re.compile(r"\s+")

# Directional / qualifier tokens. Two district names that agree on everything
# EXCEPT one of these are almost never the same place — they are siblings
# produced by a split. token_sort_ratio scores such pairs 80-90, which is high
# enough to be accepted and completely wrong: it silently attaches a new
# district to its sibling's population instead of its parent's.
#
# Observed casualties before this guard existed:
#   Delhi "South East"      -> "North East"       (80)
#   "North Garo Hills"      -> "South Garo Hills" (88)
#   "South West Garo Hills" -> "South Garo Hills" (86)
#   "South West Khasi Hills"-> "West Khasi Hills" (84)
#
# So: if the directional token SETS differ, the fuzzy match is refused
# regardless of score, and the district is sent to the unmatched pile where a
# human has to resolve it in config/district_overrides.csv.
_DIRECTIONAL = frozenset({
    "north", "south", "east", "west", "central",
    "upper", "lower", "urban", "rural", "metropolitan", "new",
    "purba", "paschim", "uttar", "dakshin", "poorvi", "pashchim",
})


def directional(s: str) -> frozenset:
    return frozenset(s.split()) & _DIRECTIONAL


def norm(s: str) -> str:
    """Aggressive but reversible-in-spirit normalisation for name matching."""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("&", " and ").replace("-", " ").replace(".", " ")
    s = _NOISE.sub(" ", s)
    s = _NONAL.sub(" ", s)
    return _WS.sub(" ", s).strip()


def load_inputs():
    nfhs = pd.read_csv(raw_path("nfhs5_districts"), low_memory=False)
    nfhs = nfhs[["state", "district"]].drop_duplicates().reset_index(drop=True)

    cen = pd.read_csv(raw_path("census2011_districts"), low_memory=False)
    cen = cen.rename(columns={
        "District code": "census_code", "State name": "census_state",
        "District name": "census_district", "Population": "population",
        "Rural_Households": "rural_hh", "Urban_Households": "urban_hh",
        "Households": "total_hh",
    })[["census_code", "census_state", "census_district",
        "population", "rural_hh", "urban_hh", "total_hh"]]
    cen["norm"] = cen["census_district"].map(norm)
    return nfhs, cen


def load_overrides() -> dict:
    ov = pd.read_csv(CONFIG_DIR / "district_overrides.csv", comment="#")
    return {(r.nfhs_state, r.nfhs_district): r for r in ov.itertuples()}


def reconcile() -> pd.DataFrame:
    nfhs, cen = load_inputs()
    xw = load_yaml("state_crosswalk.yml")
    state_map, overrides = xw["states"], load_overrides()
    region_of = {s: reg for reg, states in xw["regions"].items() for s in states}

    unknown_states = sorted(set(nfhs.state) - set(state_map))
    if unknown_states:
        print(f"  [FAIL] NFHS states absent from config/state_crosswalk.yml: {unknown_states}")
        sys.exit(1)

    rows = []
    for r in nfhs.itertuples():
        rec = {"nfhs_state": r.state, "nfhs_district": r.district,
               "region": region_of.get(r.state), "census_code": pd.NA,
               "census_state": pd.NA, "census_district": pd.NA,
               "match_score": pd.NA, "tier": "unmatched", "note": ""}

        ov = overrides.get((r.state, r.district))
        if ov is not None and ov.rule != "exclude":
            hit = cen[(cen.census_state == ov.census_state)
                      & (cen.census_district.map(norm) == norm(ov.census_district))]
            if len(hit):
                h = hit.iloc[0]
                rec |= {"census_code": h.census_code, "census_state": h.census_state,
                        "census_district": h.census_district, "match_score": 100.0,
                        "tier": f"override:{ov.rule}", "note": ov.note}
                rows.append(rec)
                continue
            rec["note"] = f"OVERRIDE TARGET NOT FOUND: {ov.census_state}/{ov.census_district}"
        elif ov is not None:
            rec |= {"tier": "excluded", "note": ov.note}
            rows.append(rec)
            continue

        pool = cen[cen.census_state.isin(state_map[r.state])]
        if len(pool):
            key = norm(r.district)
            m = process.extractOne(key, pool["norm"].tolist(), scorer=fuzz.token_sort_ratio)
            if m and m[1] >= REVIEW:
                h = pool.iloc[m[2]]
                if directional(key) != directional(h["norm"]):
                    rec["note"] = (f"REFUSED '{h.census_district}' (scored {m[1]:.0f}): "
                                   f"directional tokens differ "
                                   f"{sorted(directional(key)) or '[]'} vs "
                                   f"{sorted(directional(h['norm'])) or '[]'} — "
                                   "likely a sibling, not the parent")
                else:
                    rec |= {"census_code": h.census_code, "census_state": h.census_state,
                            "census_district": h.census_district, "match_score": float(m[1]),
                            "tier": "fuzzy" if m[1] >= ACCEPT else "fuzzy_review"}
            elif m:
                rec["note"] = f"best candidate '{pool.iloc[m[2]].census_district}' scored {m[1]:.0f} (< {REVIEW})"
        rows.append(rec)

    df = pd.DataFrame(rows)

    # --- post-2011 splits: several NFHS districts -> one Census district -----
    matched = df["census_code"].notna()
    share = df[matched].groupby("census_code")["nfhs_district"].transform("size")
    df.loc[matched, "n_sharing_parent"] = share
    df["is_apportioned"] = df.get("n_sharing_parent", pd.Series(dtype=float)).gt(1).fillna(False)

    cen_idx = load_inputs()[1].set_index("census_code")
    for col in ("population", "rural_hh", "total_hh"):
        df[col] = df["census_code"].map(cen_idx[col])
    df["n_sharing_parent"] = df["n_sharing_parent"].fillna(0).astype(int)

    # Equal apportionment across children of a split parent.
    sh = df["n_sharing_parent"].where(df["n_sharing_parent"] > 0, 1)
    df["population_alloc"] = (df["population"] / sh).round().astype("Int64")

    # Rural population via household share (see config/indicators.yml).
    hh_share = (df["rural_hh"] / df["total_hh"]).clip(0, 1)
    df["rural_share"] = hh_share.round(4)
    df["rural_population"] = (df["population_alloc"] * hh_share).round().astype("Int64")
    return df


def write_report(df: pd.DataFrame) -> None:
    n = len(df)
    tiers = df["tier"].value_counts()
    matched = int(df["census_code"].notna().sum())
    appt = int(df["is_apportioned"].sum())
    unmatched = df[df.tier == "unmatched"]
    review = df[df.tier == "fuzzy_review"].sort_values("match_score")

    L = ["# Reconciliation Report", "",
         "NFHS-5 (2019-21) districts matched to Census 2011 districts.", "",
         "## Coverage", "",
         f"| Metric | Value |", "|---|---|",
         f"| NFHS-5 districts | {n} |",
         f"| Matched to a Census district | {matched} ({matched/n:.1%}) |",
         f"| Unmatched (excluded from allocation) | {n - matched} ({(n-matched)/n:.1%}) |",
         f"| Sharing a parent (post-2011 split) | {appt} |", "",
         "## Resolution tier", "", "| Tier | Districts |", "|---|---|"]
    L += [f"| `{k}` | {v} |" for k, v in tiers.items()]
    L += ["", f"Thresholds: accept >= {ACCEPT}, flag for review >= {REVIEW}, "
              f"reject below {REVIEW}. Scorer: `rapidfuzz.fuzz.token_sort_ratio` "
              "over state-restricted candidate pools.", ""]

    L += ["## Population apportionment", "",
          f"{appt} NFHS districts resolve to a Census parent shared with at least one "
          "sibling — these are post-2011 splits. Parent population is divided EQUALLY "
          "among children. This is unbiased in aggregate but wrong for any individual "
          "district, and it is the single largest source of error in the population "
          "denominator. Districts affected:", ""]
    if appt:
        t = (df[df.is_apportioned]
             .sort_values(["census_state", "census_district", "nfhs_district"])
             [["nfhs_state", "nfhs_district", "census_district", "n_sharing_parent",
               "population_alloc"]])
        L += ["| NFHS state | NFHS district | Census parent | Siblings | Apportioned pop |",
              "|---|---|---|---|---|"]
        L += [f"| {r.nfhs_state} | {r.nfhs_district} | {r.census_district} | "
              f"{r.n_sharing_parent} | {r.population_alloc:,} |" for r in t.itertuples()]
    L.append("")

    L += ["## Unmatched districts", "",
          "No Census 2011 counterpart scored above threshold. These carry no "
          "population denominator and are therefore excluded from the allocation. "
          "Each is a candidate for a `child_of` row in `config/district_overrides.csv`.", ""]
    if len(unmatched):
        L += ["| NFHS state | NFHS district | Diagnostic |", "|---|---|---|"]
        L += [f"| {r.nfhs_state} | {r.nfhs_district} | {r.note or 'no candidate in state pool'} |"
              for r in unmatched.itertuples()]
    else:
        L.append("_None._")
    L.append("")

    L += ["## Low-confidence matches (accepted, flagged)", "",
          f"Scored between {REVIEW} and {ACCEPT}. Accepted, but these are the rows to "
          "read manually before trusting the result.", ""]
    if len(review):
        L += ["| NFHS district | Census district | Score |", "|---|---|---|"]
        L += [f"| {r.nfhs_state} / {r.nfhs_district} | {r.census_state} / {r.census_district} "
              f"| {r.match_score:.0f} |" for r in review.itertuples()]
    else:
        L.append("_None._")

    (REPORTS / "reconciliation_report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main() -> int:
    print("=== Phase 1a: boundary reconciliation ===")
    df = reconcile()
    out = DATA_INTERIM / "crosswalk.csv"
    df.to_csv(out, index=False)
    write_report(df)

    n, matched = len(df), int(df["census_code"].notna().sum())
    print(f"\n  NFHS-5 districts      : {n}")
    print(f"  matched               : {matched} ({matched/n:.1%})")
    print(f"  unmatched             : {n - matched}")
    print(f"  apportioned (splits)  : {int(df['is_apportioned'].sum())}")
    print("\n  tier breakdown:")
    for k, v in df["tier"].value_counts().items():
        print(f"    {k:<22} {v}")
    print(f"\n  crosswalk -> {out}")
    print(f"  report    -> {REPORTS / 'reconciliation_report.md'}")
    if matched / n < 0.85:
        print("\n  [WARN] match rate below 85% — add overrides before proceeding.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
