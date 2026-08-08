"""Residual model invariants. Skipped if Phase 7 has not been run."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.config import DATA_PROCESSED


@pytest.fixture(scope="module")
def res() -> pd.DataFrame:
    p = DATA_PROCESSED / "residuals.csv"
    if not p.exists():
        pytest.skip("run `make residual` first")
    return pd.read_csv(p)


def test_every_scored_district_has_a_residual(res):
    assert len(res) > 600
    assert res.residual.notna().all()


def test_residual_is_actual_minus_predicted(res):
    assert np.allclose(res.residual, res.need_index - res.predicted_need, atol=1e-9)


def test_residuals_are_approximately_centred(res):
    """Out-of-fold residuals should have near-zero mean. A large bias would mean
    the model is systematically over- or under-predicting, which invalidates
    reading any individual residual as a signal."""
    assert abs(res.residual.mean()) < 0.05


def test_predictions_stay_in_the_index_range(res):
    """The need index is a weighted mean of percentiles, so it lives in [0, 1].
    A prediction outside that range would be extrapolating past what the target
    can physically be."""
    assert res.predicted_need.between(-0.05, 1.05).all()


def test_features_are_shares(res):
    """Every predictor is a ratio, so district size cannot leak in as a proxy
    for health outcomes."""
    feats = ["literacy_rate", "female_literacy_rate", "sc_share", "st_share",
             "electrified_hh", "latrine_hh", "tapwater_hh", "lpg_hh",
             "agri_worker_share", "worker_share", "rural_hh_share"]
    for f in feats:
        assert res[f].between(0, 1).all(), f"{f} is not a share"


def test_model_explains_something_but_not_everything(res):
    """Guards both failure modes.

    R^2 near 0 would mean the socioeconomic frame is useless. R^2 near 1 would
    mean health outcomes are fully determined by material conditions — leaving
    no room for a health-system signal, and making the residual meaningless.
    The interesting regime is the middle.
    """
    ss_res = ((res.need_index - res.predicted_need) ** 2).sum()
    ss_tot = ((res.need_index - res.need_index.mean()) ** 2).sum()
    r2 = 1 - ss_res / ss_tot
    assert 0.3 < r2 < 0.9, f"out-of-fold R^2 = {r2:.3f} is outside the useful range"
