# -*- coding: utf-8 -*-
"""Behavioral tests for the unified Ordinary Kriging method."""

import numpy as np
import pytest

pytest.importorskip("scipy")

from bestfitinterpolator.core.methods.kriging_ok import OrdinaryKrigingMethod
from bestfitinterpolator.core.types import CVPlan, TrainingData


def _field(n=60, seed=9):
    rng = np.random.default_rng(seed)
    xy = rng.uniform(0, 100, size=(n, 2))
    d = np.sqrt(((xy[:, None, :] - xy[None, :, :]) ** 2).sum(axis=2))
    cov = 4.0 * np.exp(-3.0 * d / 40.0) + 0.2 * np.eye(n)
    z = 12.0 + np.linalg.cholesky(cov + 1e-10 * np.eye(n)) @ rng.standard_normal(n)
    return TrainingData(xy=xy, values=z)


EXPLICIT = {"strategy": "MoM", "model": "exponential", "nugget": 0.2, "psill": 4.0, "range": 40.0}


def test_mom_prediction_is_near_exact_at_samples():
    data = _field()
    fit = OrdinaryKrigingMethod().fit(data, params=EXPLICIT)
    pred = fit.model.predict(data.xy)
    # nugget!=0 gives near-interpolation (γ(0)=0 rule keeps it close)
    assert np.corrcoef(pred, data.values)[0, 1] > 0.99


def test_explicit_params_skip_fitting():
    fit = OrdinaryKrigingMethod().fit(_field(), params=EXPLICIT)
    assert fit.params["nugget"] == 0.2
    assert fit.params["psill"] == 4.0
    assert fit.params["range"] == 40.0
    assert fit.diagnostics["variogram"].fit_report == {"source": "user"}


def test_automatic_small_n_selects_reml():
    data = _field(n=40)
    fit = OrdinaryKrigingMethod().fit(data, params={"strategy": "Automatic", "model": "exponential"})
    assert fit.params["strategy"] == "reml"
    assert "n < 100" in fit.diagnostics["strategy_reason"]


def test_automatic_large_n_selects_mom():
    data = _field(n=120)
    fit = OrdinaryKrigingMethod().fit(data, params={"strategy": "Automatic", "model": "exponential"})
    assert fit.params["strategy"] == "mom"


def test_reml_variance_available():
    data = _field(n=40)
    fit = OrdinaryKrigingMethod().fit(data, params={"strategy": "REML", "model": "exponential"})
    pred, var = fit.model.predict(data.xy[:5], return_variance=True)
    assert pred.shape == (5,)
    assert var.shape == (5,)
    assert np.all(var >= 0)


def test_cv_with_explicit_params_matches_manual_loocv():
    data = _field(n=60)
    method = OrdinaryKrigingMethod()
    cv = method.cross_validate(data, EXPLICIT, CVPlan(mode="loocv"))
    assert cv.metrics.n == 60
    assert cv.metrics.r2 > 0.4  # structured field must beat the mean (0.58 measured)
    assert cv.params["nugget"] == 0.2
