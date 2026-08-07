# -*- coding: utf-8 -*-
"""Behavioral tests for the IDW method."""

import numpy as np
import pytest

from bestfitinterpolator.core.exceptions import InsufficientSamples, OperationCancelled
from bestfitinterpolator.core.methods.idw import IDWMethod, idw_predict, optimize_idw
from bestfitinterpolator.core.types import CVPlan, TrainingData


XY = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [1.0, 1.0], [0.5, 0.2]])
Z = np.array([1.0, 2.0, 3.0, 4.0, 2.0])


def _data(xy=XY, z=Z):
    return TrainingData(xy=np.asarray(xy, float), values=np.asarray(z, float))


def test_exact_hit_returns_sample_value():
    zi = idw_predict(XY, Z, np.array([[1.0, 0.0]]), p=2.0, n=4)
    assert zi[0] == pytest.approx(2.0)


def test_hand_computed_two_neighbors():
    # query (0.5, 0.0): distances to (0,0) and (1,0) both 0.5, others farther
    zi = idw_predict(XY[:2], Z[:2], np.array([[0.5, 0.0]]), p=2.0, n=2)
    assert zi[0] == pytest.approx(1.5)


def test_prediction_within_data_range():
    rng = np.random.default_rng(3)
    xy = rng.uniform(0, 10, size=(40, 2))
    z = rng.uniform(5, 9, size=40)
    q = rng.uniform(0, 10, size=(100, 2))
    zi = idw_predict(xy, z, q, p=2.0, n=8)
    assert np.all(zi >= 5.0 - 1e-9) and np.all(zi <= 9.0 + 1e-9)


def test_high_power_approaches_nearest_neighbor():
    q = np.array([[0.9, 0.05]])   # nearest sample is (1, 0) -> z=2
    zi = idw_predict(XY, Z, q, p=50.0, n=5)
    assert zi[0] == pytest.approx(2.0, abs=1e-3)


def test_optimize_idw_picks_from_legacy_grid():
    rng = np.random.default_rng(11)
    xy = rng.uniform(0, 100, size=(30, 2))
    z = xy[:, 0] * 0.1 + rng.normal(0, 0.1, 30)
    p, n, isi, table = optimize_idw(xy, z, k=5)
    assert 0.5 <= p <= 6.0
    assert 4 <= n <= 16
    assert len(table) == 12 * 13
    assert np.isfinite(isi)


def test_optimize_requires_five_samples():
    with pytest.raises(ValueError):
        optimize_idw(XY[:4], Z[:4])


def test_fit_with_explicit_params_skips_search():
    fit = IDWMethod().fit(_data(), params={"p": 2.0, "n": 4})
    assert fit.params == {"p": 2.0, "n": 4}
    assert fit.diagnostics == {}
    pred = fit.model.predict(np.array([[0.0, 0.0]]))
    assert pred[0] == pytest.approx(1.0)


def test_fit_validates_min_samples():
    with pytest.raises(InsufficientSamples):
        IDWMethod().fit(_data(XY[:3], Z[:3]))


def test_predict_cancellation():
    fit = IDWMethod().fit(_data(), params={"p": 2.0, "n": 4})
    with pytest.raises(OperationCancelled):
        fit.model.predict(np.zeros((10, 2)), should_stop=lambda: True)


def test_cross_validate_returns_full_prediction_vector():
    rng = np.random.default_rng(5)
    xy = rng.uniform(0, 50, size=(25, 2))
    z = xy[:, 1] * 0.2 + rng.normal(0, 0.05, 25)
    cv = IDWMethod().cross_validate(
        TrainingData(xy=xy, values=z), {"p": 2.0, "n": 6}, CVPlan(mode="loocv")
    )
    assert cv.observed.shape == (25,)
    assert np.all(np.isfinite(cv.predicted))
    assert cv.metrics.n == 25
    assert cv.metrics.r2 > 0.5
