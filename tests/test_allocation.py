"""Allocation invariants. Skipped if Phase 3 has not been run.

The constraint tests matter most: an ILP that silently returns an infeasible
answer looks exactly like one that worked.
"""
from __future__ import annotations

import pandas as pd
import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

from src.config import engine, load_yaml

CFG = load_yaml("allocation.yml")
BUDGET = CFG["budget"]
CAP = CFG["constraints"]["max_per_state"]
FLOOR = CFG["constraints"]["min_per_region"]


@pytest.fixture(scope="module")
def alloc() -> pd.DataFrame:
    try:
        with engine().connect() as c:
            c.exec_driver_sql("select 1 from core.allocation limit 1")
    except (OperationalError, ProgrammingError):
        pytest.skip("allocation not built — run `make allocate` first")
    with engine().connect() as c:
        return pd.read_sql(text("""
            select a.scenario, a.district_id, a.need_index, a.coverage_gain,
                   d.nfhs_state, d.region, d.terrain
            from core.allocation a join core.district d using (district_id)"""), c)


def scen(alloc, name) -> pd.DataFrame:
    return alloc[alloc.scenario == name]


def test_every_scenario_spends_the_whole_budget(alloc):
    for name, g in alloc.groupby("scenario"):
        assert len(g) == BUDGET, f"{name} selected {len(g)}, expected {BUDGET}"


def test_optimal_respects_the_state_cap(alloc):
    worst = scen(alloc, "optimal").nfhs_state.value_counts().max()
    assert worst <= CAP, f"optimal puts {worst} facilities in one state, cap is {CAP}"


def test_optimal_respects_the_region_floor(alloc):
    counts = scen(alloc, "optimal").region.value_counts()
    assert len(counts) == 6, f"optimal reaches only {len(counts)} of 6 regions"
    assert counts.min() >= FLOOR


def test_greedy_baseline_is_also_feasible(alloc):
    """If greedy were infeasible the premium would be measured against nonsense."""
    g = scen(alloc, "greedy_feasible")
    assert g.nfhs_state.value_counts().max() <= CAP
    assert g.region.nunique() == 6


def test_optimal_beats_the_feasible_baseline(alloc):
    opt = scen(alloc, "optimal").coverage_gain.sum()
    greedy = scen(alloc, "greedy_feasible").coverage_gain.sum()
    assert opt > greedy, "the ILP failed to beat a greedy heuristic"


def test_optimal_never_exceeds_the_unconstrained_ceiling(alloc):
    """Adding constraints cannot increase the optimum. If it does, the model is wrong."""
    opt = scen(alloc, "optimal").coverage_gain.sum()
    ceiling = scen(alloc, "unconstrained_bound").coverage_gain.sum()
    assert opt <= ceiling + 1e-6, "constrained solution beat the unconstrained bound"


def test_naive_ranking_is_genuinely_infeasible(alloc):
    """Pins the finding: sorting by need index breaches the equity constraints.

    If this ever fails it means the constraints stopped binding, and the whole
    optimisation argument would need restating rather than quietly assuming.
    """
    n = scen(alloc, "naive_top25")
    assert n.nfhs_state.value_counts().max() > CAP or n.region.nunique() < 6


def test_no_district_selected_twice_within_a_scenario(alloc):
    assert not alloc.duplicated(["scenario", "district_id"]).any()


def test_all_selected_districts_are_scorable(alloc):
    with engine().connect() as c:
        ok = set(pd.read_sql("select district_id from core.mv_district_score", c).district_id)
    assert set(alloc.district_id) <= ok
