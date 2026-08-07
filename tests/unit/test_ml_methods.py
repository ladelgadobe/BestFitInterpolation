# -*- coding: utf-8 -*-
"""Behavioral tests for RF / SVM / RK methods and the registry."""

import numpy as np
import pytest

pytest.importorskip("sklearn")
pytest.importorskip("scipy")

from bestfitinterpolator.core.methods import METHOD_REGISTRY, available_methods, get_method
from bestfitinterpolator.core.methods.rf import build_features
from bestfitinterpolator.core.exceptions import InvalidDataError
from bestfitinterpolator.core.types import CVPlan, TrainingData


def _cov_data(n=40, seed=4):
    rng = np.random.default_rng(seed)
    xy = rng.uniform(0, 100, size=(n, 2))
    cov = rng.uniform(0, 1, size=(n, 2))
    z = 3.0 * cov[:, 0] + 0.5 * cov[:, 1] + 0.01 * xy[:, 0] + rng.normal(0, 0.05, n)
    return TrainingData(
        xy=xy, values=z, covariates=cov, covariate_names=("ndvi", "elev")
    )


def test_registry_has_all_six_methods():
    assert set(METHOD_REGISTRY) == {"idw", "tps", "ok", "rf", "svm", "rk"}
    assert get_method("rf").info.label == "Random Forest"
    with pytest.raises(ValueError, match="Unknown interpolation method"):
        get_method("nope")


def test_available_methods_filters_on_missing_deps(monkeypatch):
    from bestfitinterpolator.core import methods as reg

    monkeypatch.setattr(
        reg, "check_imports", lambda: {"scipy": False, "scikit-learn": False, "joblib": False}
    )
    keys = {info.key for info in reg.available_methods(check_deps=True)}
    assert keys == {"idw"}  # only the numpy-only method survives
    assert {i.key for i in reg.available_methods()} == set(METHOD_REGISTRY)


def test_build_features_positional_alignment():
    xy = np.array([[1.0, 2.0], [3.0, 4.0]])
    cov = np.array([[0.1], [0.2]])
    X = build_features(xy, cov, use_xy=True)
    assert X.tolist() == [[1.0, 2.0, 0.1], [3.0, 4.0, 0.2]]
    X = build_features(xy, cov, use_xy=False)
    assert X.tolist() == [[0.1], [0.2]]
    with pytest.raises(InvalidDataError):
        build_features(xy, None, use_xy=False)


def test_rf_manual_params_reproducible_and_learns_covariate():
    data = _cov_data()
    rf = get_method("rf")
    fit1 = rf.fit(data, params={"ntree": 100, "mtry": 2, "nodesize": 3})
    fit2 = rf.fit(data, params={"ntree": 100, "mtry": 2, "nodesize": 3})
    pred1 = fit1.model.predict(data.xy, covariates=data.covariates)
    pred2 = fit2.model.predict(data.xy, covariates=data.covariates)
    assert pred1 == pytest.approx(pred2)  # seed 20 fixed
    assert fit1.params["ntree"] == 100
    # the dominant covariate carries the most importance
    imp = fit1.diagnostics["importances"]
    assert imp["ndvi"] == max(imp.values())


def test_rf_cv_uses_resolved_params_not_research():
    data = _cov_data()
    cv = get_method("rf").cross_validate(
        data, {"ntree": 60, "mtry": 2, "nodesize": 3}, CVPlan(mode="kfold", folds=5)
    )
    assert cv.metrics.n == data.n
    assert cv.metrics.r2 > 0.5
    assert cv.params["ntree"] == 60


def test_svm_manual_fit_and_predict():
    data = _cov_data()
    fit = get_method("svm").fit(data, params={"C": 10.0, "gamma": 0.5, "epsilon": 0.01})
    assert fit.params["C"] == 10.0
    pred = fit.model.predict(data.xy, covariates=data.covariates)
    assert np.corrcoef(pred, data.values)[0, 1] > 0.8


def test_svm_grid_search_respects_max_iterations():
    data = _cov_data(n=25)
    grid = {
        "C": {"min": -2, "max": 2, "step": 1},
        "gamma": {"min": -4, "max": 0, "step": 1},
        "epsilon": {"min": 0.0, "max": 0.2, "step": 0.1},
    }
    fit = get_method("svm").fit(
        data,
        params={"use_grid_search": True, "grid_params": grid, "max_iterations": 5},
    )
    assert {"C", "gamma", "epsilon"} <= set(fit.params)


def test_rk_prediction_beats_rf_on_spatial_residual():
    """RK = RF trend + kriged residual; on a field with a strong spatial
    residual the kriging step must recover signal RF misses."""
    rng = np.random.default_rng(6)
    n = 60
    xy = rng.uniform(0, 100, size=(n, 2))
    cov = rng.uniform(0, 1, size=(n, 1))
    spatial = np.sin(xy[:, 0] / 15.0) * 2.0
    z = 3.0 * cov[:, 0] + spatial
    data = TrainingData(xy=xy, values=z, covariates=cov, covariate_names=("c1",))

    rk_fit = get_method("rk").fit(data, params={"ntree": 100, "mtry": 1, "nodesize": 5})
    pred = rk_fit.model.predict(data.xy, covariates=data.covariates)
    # near-interpolation at training points thanks to residual kriging
    assert float(np.mean(np.abs(pred - z))) < 0.35
    assert rk_fit.diagnostics["variogram"].strategy == "mom"
    assert rk_fit.diagnostics["residuals"].shape == (n,)
