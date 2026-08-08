"""Weight sensitivity invariants. Skipped if Phase 4 has not been run."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sqlalchemy.exc import OperationalError, ProgrammingError

from src.config import engine, load_yaml
from src.phase4_sensitivity import need_matrix, rank_matrix

CFG = load_yaml("sensitivity.yml")


@pytest.fixture(scope="module")
def ws() -> pd.DataFrame:
    try:
        with engine().connect() as c:
            c.exec_driver_sql("select 1 from core.weight_sensitivity limit 1")
    except (OperationalError, ProgrammingError):
        pytest.skip("sensitivity not built — run `make sensitivity` first")
    with engine().connect() as c:
        return pd.read_sql("select * from core.weight_sensitivity", c)


@pytest.fixture(scope="module")
def conf() -> pd.DataFrame:
    try:
        with engine().connect() as c:
            return pd.read_sql("select * from core.v_allocation_confidence", c)
    except (OperationalError, ProgrammingError):
        pytest.skip("sensitivity not built")


def test_both_regimes_present(ws):
    assert set(ws.regime) == set(CFG["regimes"])


def test_every_scored_district_appears_in_every_regime(ws):
    counts = ws.groupby("regime").district_id.nunique()
    assert counts.nunique() == 1


def test_stabilities_are_proportions(ws):
    for col in ("rank_stability", "ilp_stability"):
        v = ws[col].dropna().astype(float)
        assert v.between(0, 1).all(), f"{col} out of [0,1]"


def test_ranks_are_within_the_district_universe(ws):
    n = ws.district_id.nunique()
    assert ws.best_rank.min() >= 1
    assert ws.worst_rank.max() <= n
    assert (ws.best_rank <= ws.worst_rank).all()


def test_percentile_band_brackets_the_mean(ws):
    assert (ws.p05_need_index <= ws.mean_need_index).all()
    assert (ws.mean_need_index <= ws.p95_need_index).all()


def test_exactly_top_n_districts_selected_per_draw_on_average(ws):
    """Sum of rank stabilities across districts must equal top_n exactly.

    Every draw puts exactly top_n districts in the top N, so the column sums to
    top_n regardless of how the draws fell. A drift here means the ranking is
    producing ties or dropping districts.
    """
    for regime, g in ws.groupby("regime"):
        total = g.rank_stability.astype(float).sum()
        assert abs(total - CFG["top_n"]) < 0.01, f"{regime}: {total}"


def test_ilp_stability_sums_to_the_budget(ws):
    budget = load_yaml("allocation.yml")["budget"]
    for regime, g in ws.groupby("regime"):
        total = g.ilp_stability.dropna().astype(float).sum()
        assert abs(total - budget) < 0.01, f"{regime}: {total}"


def test_allocated_districts_are_never_wholly_unreproducible(conf):
    """No allocated district should be excluded — that would signal an unstable optimum."""
    assert (conf.classification_centred != "excluded").all()


def test_centred_regime_is_more_stable_than_uniform(conf):
    """A tighter weight distribution must not produce LESS stable selections."""
    c = conf.ilp_stability_centred.astype(float).mean()
    u = conf.ilp_stability_uniform.astype(float).mean()
    assert c >= u, f"centred ({c:.3f}) less stable than uniform ({u:.3f})"


def test_need_matrix_renormalises_over_present_indicators():
    """A district missing an indicator is scored on the rest, not penalised."""
    P = np.array([[0.9, 0.5, np.nan], [0.9, 0.5, 0.1]])
    W = np.array([[1 / 3, 1 / 3, 1 / 3]])
    got = need_matrix(P, W)
    assert got[0, 0] == pytest.approx(0.7)          # mean of 0.9, 0.5
    assert got[1, 0] == pytest.approx(0.5)          # mean of 0.9, 0.5, 0.1


def test_rank_matrix_is_a_permutation():
    N = np.array([[0.1], [0.9], [0.5]])
    assert sorted(rank_matrix(N).ravel().tolist()) == [1, 2, 3]
    assert rank_matrix(N)[1, 0] == 1                # highest need ranks first
