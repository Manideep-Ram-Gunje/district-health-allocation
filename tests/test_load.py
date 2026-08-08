"""Database invariants. Skipped automatically if Postgres is not reachable.

    python -m pytest
"""
from __future__ import annotations

import pandas as pd
import pytest
from sqlalchemy.exc import OperationalError

from src.config import engine, load_yaml

CENSUS_2011_TOTAL_POPULATION = 1_210_854_977
CENSUS_2011_RURAL_POPULATION = 833_748_852
# Chandigarh + Lakshadweep have no NFHS-5 district factsheet in this extract.
ABSENT_UT_POPULATION = 1_055_450 + 64_473


@pytest.fixture(scope="module")
def cx():
    try:
        eng = engine()
        with eng.connect() as c:
            c.exec_driver_sql("select 1")
    except OperationalError:
        pytest.skip("postgres not reachable — run `make db-create && make load` first")
    with engine().connect() as c:
        yield c


def q(cx, sql: str) -> pd.DataFrame:
    return pd.read_sql(sql, cx)


def test_district_count(cx):
    assert q(cx, "select count(*) n from core.district").n[0] == 705


def test_indicator_catalogue_complete(cx):
    r = q(cx, "select count(*) n, sum(in_index::int) k from core.indicator")
    assert r.n[0] == 104 and r.k[0] == 7


def test_no_orphan_facts(cx):
    n = q(cx, """select count(*) n from core.district_indicator di
                 left join core.district d using (district_id)
                 where d.district_id is null""").n[0]
    assert n == 0


def test_every_weight_scheme_sums_to_one(cx):
    r = q(cx, "select scheme, sum(weight) s from core.weight_scheme group by 1")
    assert not r.empty
    for row in r.itertuples():
        assert abs(float(row.s) - 1.0) < 1e-6, f"{row.scheme} sums to {row.s}"


def test_weight_schemes_cover_exactly_the_index_indicators(cx):
    keys = set(q(cx, "select indicator_key k from core.indicator where in_index").k)
    for scheme in load_yaml("indicators.yml")["weighting_schemes"]:
        got = set(q(cx, f"select indicator_key k from core.weight_scheme "
                        f"where scheme = '{scheme}'").k)
        assert got == keys, f"{scheme} covers {got ^ keys} incorrectly"


def test_population_reconciles_to_census_total(cx):
    """Apportionment must conserve population.

    Expected total = Census 2011 all-India minus the two UTs with no NFHS
    factsheet. Any larger gap means apportionment is losing or duplicating
    people, which would silently distort every allocation downstream.
    """
    total = int(q(cx, "select sum(population_alloc) s from core.district").s[0])
    expected = CENSUS_2011_TOTAL_POPULATION - ABSENT_UT_POPULATION
    assert abs(total - expected) < 1000, f"{total:,} vs expected {expected:,}"


def test_rural_population_slightly_below_published(cx):
    rural = int(q(cx, "select sum(rural_population) s from core.district").s[0])
    ratio = rural / CENSUS_2011_RURAL_POPULATION
    assert 0.95 <= ratio <= 1.0, f"rural is {ratio:.2%} of published"


def test_all_six_regions_populated(cx):
    r = q(cx, "select region, count(*) n from core.district group by 1")
    assert len(r) == 6 and (r.n > 0).all()


def test_index_indicator_values_are_percentages(cx):
    """All seven index indicators are percentages, so values must sit in [0, 100]."""
    bad = q(cx, """select i.indicator_key, count(*) n
                   from core.district_indicator di
                   join core.indicator i using (indicator_id)
                   where i.in_index and di.value_nfhs5 is not null
                     and (di.value_nfhs5 < 0 or di.value_nfhs5 > 100)
                   group by 1""")
    assert bad.empty, f"out-of-range values: {bad.to_dict('records')}"
