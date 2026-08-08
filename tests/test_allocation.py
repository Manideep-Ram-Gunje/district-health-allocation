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


def test_optimal_is_at_least_as_good_as_every_feasible_baseline(alloc):
    """The ILP must never be BEATEN by a heuristic. Matching one is fine.

    Deliberately >= and not >. Greedy sorted by the objective reaches the
    optimum on this problem — a linear objective under a cardinality limit and
    per-state caps is close to a matroid, and greedy is strong on those. An
    earlier version of this test demanded strict improvement, which only passed
    because the greedy baseline was sorted by the wrong key.
    """
    opt = scen(alloc, "optimal").coverage_gain.sum()
    for name in ("greedy_feasible", "greedy_by_need"):
        assert opt >= scen(alloc, name).coverage_gain.sum() - 1e-6, f"beaten by {name}"


def test_sorting_by_the_objective_never_loses_to_sorting_by_need(alloc):
    """Sorting by the quantity you maximise can only help.

    Deliberately >=. Under the default terrain-neutral objective, coverage gain
    is need_index x min(1, rural_pop/norm), which is need_index for all but a
    handful of districts — so the two sort keys coincide and the scenarios tie.
    Under coverage_gain_population they diverge sharply. Asserting strict
    improvement would encode an artefact of one objective choice as a law.
    """
    good = scen(alloc, "greedy_feasible").coverage_gain.sum()
    bad = scen(alloc, "greedy_by_need").coverage_gain.sum()
    assert good >= bad - 1e-9


def test_allocation_is_not_entirely_plains(alloc):
    """Guards the terrain bias that the population objective introduced.

    With coverage_gain_population, all 25 picks were plains districts although
    23% of candidates are hilly or tribal — the objective penalised hard terrain
    for being hard to serve, inverting the intent of the IPHS norm.
    """
    t = scen(alloc, "optimal").terrain
    assert (t != "plains").sum() > 0, "no hilly or tribal district was selected"


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


# ---------------------------------------------------------------------------
# The verification that decides what Phase 3 is allowed to claim.
# ---------------------------------------------------------------------------

CONFIGS = [(25, 4, 1), (25, 2, 1), (25, 1, 1), (25, 4, 3), (25, 3, 2),
           (10, 2, 1), (50, 4, 2), (25, 4, 4), (30, 2, 3)]


@pytest.fixture(scope="module")
def candidates():
    from src.phase3_allocate import load_candidates
    try:
        with engine().connect() as c:
            return load_candidates(c, load_yaml("indicators.yml")["default_scheme"],
                                   load_yaml("allocation.yml")["objective"])
    except (OperationalError, ProgrammingError):
        pytest.skip("analytics layer not built")


@pytest.mark.parametrize("budget,cap,floor", CONFIGS)
def test_greedy_is_always_feasible(candidates, budget, cap, floor):
    """A heuristic that quietly returns an infeasible answer is worse than none.

    The original region-repair did exactly ONE swap per region, so with
    min_per_region > 1 it left regions under-served and reported success. The
    inflated score then BEAT the proven optimum — which is impossible for two
    feasible solutions, and is how the bug surfaced.
    """
    from src.phase3_allocate import check_feasible, greedy_feasible
    g = greedy_feasible(candidates, budget, cap, floor)
    v = check_feasible(g, budget, cap, floor, candidates.region.unique())
    assert not v, f"greedy infeasible at ({budget},{cap},{floor}): {v}"


@pytest.mark.parametrize("budget,cap,floor", CONFIGS)
def test_ilp_is_never_beaten_by_greedy(candidates, budget, cap, floor):
    """Pins the central claim of Phase 3 across many constraint settings.

    A correctly-implemented greedy attains the ILP optimum on every feasible
    configuration tested — the objective is linear and the state caps form a
    partition matroid, which is exactly the structure greedy handles optimally.
    So the ILP is NOT claimed to find a better answer. It earns its place by
    PROVING optimality and by detecting infeasibility (budget 40 with a cap of
    1 per state is impossible, and CBC says so rather than returning a
    plausible-looking 40 districts).
    """
    from src.phase3_allocate import greedy_feasible, solve_ilp
    g = greedy_feasible(candidates, budget, cap, floor)
    o, status = solve_ilp(candidates, budget, cap, floor)
    if status != "Optimal":
        pytest.skip(f"configuration not solvable: {status}")
    assert o.coverage_gain.sum() >= g.coverage_gain.sum() - 1e-6


def test_solver_detects_a_genuinely_infeasible_configuration(candidates):
    """40 facilities at most 1 per state, across ~30 states, cannot be done."""
    from src.phase3_allocate import solve_ilp
    _, status = solve_ilp(candidates, 40, 1, 1)
    assert status != "Optimal", "solver accepted an impossible configuration"
