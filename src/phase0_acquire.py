"""Phase 0 — download every declared source, checksum it, and verify its shape.

Nothing downstream runs until this passes. Usage:

    python -m src.phase0_acquire            # download missing, verify all
    python -m src.phase0_acquire --force    # re-download everything
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from datetime import datetime, timezone

import pandas as pd

from src.config import DATA_RAW, MANIFEST, sources

UA = {"User-Agent": "district-health-allocation/1.0 (portfolio project)"}
OK, BAD = "  [ok]  ", "  [FAIL]"


def download(url: str, dest, force: bool = False) -> bool:
    """Return True if a fresh download happened."""
    if dest.exists() and not force:
        print(f"  cached  {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
        return False
    print(f"  fetching {dest.name} ...", flush=True)
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=180) as r, open(dest, "wb") as fh:
        fh.write(r.read())
    print(f"  saved   {dest.name} ({dest.stat().st_size / 1e6:.1f} MB)")
    return True


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _check(label: str, passed: bool, detail: str, failures: list) -> None:
    print(f"{OK if passed else BAD} {label}: {detail}")
    if not passed:
        failures.append(f"{label}: {detail}")


def verify_csv(path, rules: dict, failures: list) -> dict:
    df = pd.read_csv(path, low_memory=False)
    stats = {"rows": len(df), "cols": len(df.columns)}
    print(f"  shape: {len(df):,} rows x {len(df.columns)} columns")

    missing = [c for c in rules.get("required_columns", []) if c not in df.columns]
    _check("required columns", not missing,
           "all present" if not missing else f"MISSING {missing}", failures)

    if "min_rows" in rules:
        _check("row count", len(df) >= rules["min_rows"],
               f"{len(df):,} (need >= {rules['min_rows']:,})", failures)
    if "exact_rows" in rules:
        _check("row count", len(df) == rules["exact_rows"],
               f"{len(df):,} (need exactly {rules['exact_rows']:,})", failures)

    if "min_distinct_districts" in rules:
        n = df.groupby(["state", "district"]).ngroups
        stats["distinct_districts"] = n
        _check("distinct districts", n >= rules["min_distinct_districts"],
               f"{n:,} (need >= {rules['min_distinct_districts']:,})", failures)
    if "min_distinct_indicators" in rules:
        n = df["Indicator"].nunique()
        stats["distinct_indicators"] = n
        _check("distinct indicators", n >= rules["min_distinct_indicators"],
               f"{n:,} (need >= {rules['min_distinct_indicators']:,})", failures)
    return stats


def verify_geojson(path, rules: dict, failures: list) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        gj = json.load(fh)
    feats = gj.get("features", [])
    stats = {"features": len(feats)}
    print(f"  features: {len(feats):,}")
    _check("feature count", len(feats) >= rules.get("min_features", 0),
           f"{len(feats):,} (need >= {rules.get('min_features', 0):,})", failures)
    props = set(feats[0]["properties"].keys()) if feats else set()
    missing = [p for p in rules.get("required_properties", []) if p not in props]
    _check("required properties", not missing,
           "all present" if not missing else f"MISSING {missing}", failures)
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-download even if cached")
    args = ap.parse_args()

    manifest, failures = {}, []
    for key, spec in sources().items():
        print(f"\n=== {key} ===")
        print(f"  {spec['description'].strip().splitlines()[0]}")
        dest = DATA_RAW / spec["filename"]
        try:
            download(spec["url"], dest, force=args.force)
        except Exception as exc:                      # noqa: BLE001
            print(f"{BAD} download failed: {exc}")
            failures.append(f"{key}: download failed ({exc})")
            continue

        rules = spec.get("verify", {})
        stats = (verify_csv if spec["format"] == "csv" else verify_geojson)(dest, rules, failures)

        digest = sha256(dest)
        print(f"  sha256: {digest[:16]}...")
        manifest[key] = {
            "filename": spec["filename"],
            "url": spec["url"],
            "sha256": digest,
            "bytes": dest.stat().st_size,
            "licence": spec.get("licence"),
            "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            **stats,
        }

    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nmanifest -> {MANIFEST.relative_to(MANIFEST.parents[2])}")

    print("\n" + "=" * 62)
    if failures:
        print(f"PHASE 0 FAILED — {len(failures)} check(s) did not pass:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("PHASE 0 PASSED — all sources downloaded and verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
