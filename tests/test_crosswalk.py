"""Crosswalk invariants. These guard the assumptions everything downstream rests on.

    pytest -q
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.config import DATA_INTERIM, raw_path, load_yaml
from src.phase1_reconcile import directional, norm

CENSUS_2011_RURAL_POPULATION = 833_748_852   # published all-India figure


@pytest.fixture(scope="module")
def xw() -> pd.DataFrame:
    p = DATA_INTERIM / "crosswalk.csv"
    if not p.exists():
        pytest.skip("run `python -m src.phase1_reconcile` first")
    return pd.read_csv(p)


def test_every_nfhs_district_appears_once(xw):
    assert not xw.duplicated(["nfhs_state", "nfhs_district"]).any()


def test_no_unmatched_districts(xw):
    unmatched = xw[xw.census_code.isna()]
    assert len(unmatched) == 0, f"unmatched: {unmatched.nfhs_district.tolist()}"


def test_every_district_has_a_region(xw):
    """A null region would silently break the min-1-per-region ILP constraint."""
    assert xw.region.isna().sum() == 0


def test_regions_match_config(xw):
    assert set(xw.region.dropna()) == set(load_yaml("state_crosswalk.yml")["regions"])


def test_population_is_positive(xw):
    assert (xw.population_alloc > 0).all()
    assert (xw.rural_population >= 0).all()
    assert (xw.rural_population <= xw.population_alloc).all()


def test_apportionment_conserves_parent_population(xw):
    """Children of a split must sum to their parent, within rounding."""
    cen = pd.read_csv(raw_path("census2011_districts"), low_memory=False)
    parent = cen.set_index("District code")["Population"]
    got = xw.groupby("census_code")["population_alloc"].sum()
    for code, total in got.items():
        n = int((xw.census_code == code).sum())
        assert abs(total - parent[code]) <= n, f"census_code {code}: {total} vs {parent[code]}"


def test_rural_population_close_to_published_total(xw):
    """External sanity check against the published Census 2011 rural total.

    We expect to land slightly LOW: the household-share method assumes equal
    mean household size rural vs urban, and rural households are larger.
    """
    ratio = xw.rural_population.sum() / CENSUS_2011_RURAL_POPULATION
    assert 0.95 <= ratio <= 1.0, f"rural population is {ratio:.1%} of published total"


def test_directional_guard_rejects_siblings():
    """The bug this guard exists to prevent."""
    assert directional(norm("South East")) != directional(norm("North East"))
    assert directional(norm("North Garo Hills")) != directional(norm("South Garo Hills"))
    assert directional(norm("West Karbi Anglong")) != directional(norm("Karbi Anglong"))
    # ...but genuine renames must survive it
    assert directional(norm("Darjeeling")) == directional(norm("Darjiling"))
    assert directional(norm("Ahmedabad")) == directional(norm("Ahmadabad"))
    assert directional(norm("East Godavari")) == directional(norm("East Godavari"))


def test_all_seven_indicators_present_for_most_districts():
    df = pd.read_csv(raw_path("nfhs5_districts"), low_memory=False)
    df["num"] = df["Indicator"].str.extract(r"^\s*(\d+)\.").astype("Int64")
    targets = [i["id"] for i in load_yaml("indicators.yml")["indicators"]]
    s = df[df.num.isin(targets)].copy()
    s["v"] = pd.to_numeric(s["NFHS5"], errors="coerce")
    present = s.groupby(["state", "district"])["v"].count()
    floor = load_yaml("indicators.yml")["missingness"]["min_indicators_present"]
    assert (present >= floor).all(), "some districts fall below the missingness floor"
