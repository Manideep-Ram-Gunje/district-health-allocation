"""Need Index invariants. Skipped if the analytics layer has not been built.

    python -m pytest
"""
from __future__ import annotations

import pandas as pd
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

from src.config import engine, load_yaml

DEFAULT = load_yaml("indicators.yml")["default_scheme"]


@pytest.fixture(scope="module")
def cx():
    try:
        with engine().connect() as c:
            c.exec_driver_sql("select 1 from core.mv_district_score limit 1")
    except (OperationalError, ProgrammingError):
        pytest.skip("analytics layer not built — run `make analytics` first")
    with engine().connect() as c:
        yield c


def q(cx, sql, **kw) -> pd.DataFrame:
    return pd.read_sql(text(sql), cx, params=kw)


def test_need_index_is_a_unit_interval(cx):
    r = q(cx, "select min(need_index) lo, max(need_index) hi from core.mv_district_score")
    assert 0.0 <= float(r.lo[0]) and float(r.hi[0]) <= 1.0


def test_direction_normalisation_inverts_only_good_indicators(cx):
    """need_value = raw for bad indicators, 100 - raw for good ones."""
    bad = q(cx, """select count(*) n from core.mv_indicator_score
                   where higher_is_worse and need_value <> raw_value""").n[0]
    good = q(cx, """select count(*) n from core.mv_indicator_score
                    where not higher_is_worse and need_value <> 100 - raw_value""").n[0]
    assert bad == 0 and good == 0


def test_percentiles_span_the_full_range_for_every_indicator(cx):
    r = q(cx, """select indicator_key, min(need_percentile) lo, max(need_percentile) hi
                 from core.mv_indicator_percentile group by 1""")
    assert len(r) == 7
    assert (r.lo.astype(float) == 0.0).all(), "percent_rank should start at exactly 0"
    assert (r.hi.astype(float) == 1.0).all(), "percent_rank should end at exactly 1"


def test_weights_are_renormalised_not_dropped(cx):
    """A district missing an indicator is scored on the rest, never zeroed."""
    r = q(cx, """select min(weight_covered) lo, max(weight_covered) hi
                 from core.mv_need_index where scheme = :s""", s=DEFAULT)
    assert 0 < float(r.lo[0]) <= 1.0 and abs(float(r.hi[0]) - 1.0) < 1e-6


def test_only_zero_rural_districts_are_excluded(cx):
    """The scored set must differ from all districts by exactly the urban ones.

    Rural Sub-Centres cannot be sited in a district with no rural population,
    so Mumbai, Chennai, Kolkata and friends are correctly out of scope.
    """
    missing = q(cx, """select d.rural_population from core.district d
                       where d.district_id not in
                         (select district_id from core.mv_district_score where scheme = :s)""",
                s=DEFAULT)
    assert (missing.rural_population == 0).all(), "a district with rural population was dropped"


def test_supply_adjustment_provably_cancels(cx):
    """The methodological finding, asserted so it cannot silently stop being true."""
    r = q(cx, """select min(ratio_check) lo, max(ratio_check) hi, count(*) n
                 from core.v_supply_degeneracy where scheme = :s""", s=DEFAULT)
    assert float(r.lo[0]) == 1.0 and float(r.hi[0]) == 1.0 and int(r.n[0]) > 0


def test_coverage_gain_never_exceeds_one_facility_catchment(cx):
    """A single Sub-Centre cannot serve more than its catchment norm."""
    n = q(cx, """select count(*) n from core.mv_district_score
                 where coverage_gain_population > catchment_norm""").n[0]
    assert n == 0


def test_neutral_objective_is_a_facility_equivalent(cx):
    """The terrain-neutral objective is bounded by 1: one facility, one unit."""
    n = q(cx, """select count(*) n from core.mv_district_score
                 where coverage_gain_neutral > 1.0""").n[0]
    assert n == 0


def test_the_catchment_cap_almost_never_binds(cx):
    """Documents WHY the two objectives differ so much.

    Only a handful of districts have rural population below the catchment norm,
    so coverage_gain_population reduces to need x a terrain constant — giving
    plains districts a 5000/3000 advantage. This test pins the fact rather than
    leaving it as a footnote.
    """
    r = q(cx, """select count(*) filter (where rural_population < catchment_norm) binds,
                        count(*) total from core.mv_district_score
                 where scheme = :s""", s=DEFAULT)
    assert int(r.binds[0]) < 0.02 * int(r.total[0])


def test_population_at_risk_bounded_by_rural_population(cx):
    n = q(cx, """select count(*) n from core.mv_district_score
                 where population_at_risk > rural_population""").n[0]
    assert n == 0


def test_every_scheme_scores_the_same_districts(cx):
    r = q(cx, "select scheme, count(*) n from core.mv_district_score group by 1")
    assert r.n.nunique() == 1, "schemes disagree on which districts are scorable"


def test_national_ranks_are_dense_and_complete(cx):
    r = q(cx, """select count(*) n, min(national_rank) lo, max(national_rank) hi
                 from core.mv_peer_benchmark where scheme = :s""", s=DEFAULT)
    assert int(r.lo[0]) == 1 and int(r.hi[0]) <= int(r.n[0])
