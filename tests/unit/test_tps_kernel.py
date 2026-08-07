# -*- coding: utf-8 -*-
"""Behavioral tests for the TPS method (fit/predict split)."""

import numpy as np
import pytest

pytest.importorskip("scipy")

from bestfitinterpolator.core.exceptions import InvalidDataError
from bestfitinterpolator.core.methods.tps import DEFAULT_EPSILON, TPSMethod
from bestfitinterpolator.core.types import TrainingData


def _plane_data(n=25, seed=1):
    rng = np.random.default_rng(seed)
    xy = rng.uniform(0, 10, size=(n, 2))
    z = 2.0 + 0.5 * xy[:, 0] - 0.25 * xy[:, 1]
    return TrainingData(xy=xy, values=z)


def test_tps_reproduces_training_points():
    data = _plane_data()
    fit = TPSMethod().fit(data)
    pred = fit.model.predict(data.xy)
    assert pred == pytest.approx(data.values, abs=1e-6)


def test_tps_recovers_plane_at_new_points():
    data = _plane_data()
    fit = TPSMethod().fit(data)
    q = np.array([[5.0, 5.0], [2.0, 8.0]])
    expected = 2.0 + 0.5 * q[:, 0] - 0.25 * q[:, 1]
    # thin-plate RBF is not exactly affine between points; ~3% is expected
    assert fit.model.predict(q) == pytest.approx(expected, abs=0.1)


def test_default_epsilon_matches_legacy():
    fit = TPSMethod().fit(_plane_data())
    assert fit.params["epsilon"] == DEFAULT_EPSILON
    # epsilon <= 0 also falls back to the default (legacy behavior)
    fit = TPSMethod().fit(_plane_data(), params={"epsilon": -1})
    assert fit.params["epsilon"] == DEFAULT_EPSILON


def test_duplicate_coordinates_rejected_before_fit():
    xy = np.array([[0.0, 0.0], [0.0, 0.0], [1.0, 1.0], [2.0, 0.5]])
    z = np.array([1.0, 2.0, 3.0, 4.0])
    with pytest.raises(InvalidDataError):
        TPSMethod().fit(TrainingData(xy=xy, values=z))


def test_single_fit_predicts_in_chunks_consistently():
    data = _plane_data(n=40)
    fit = TPSMethod().fit(data)
    q = np.random.default_rng(2).uniform(0, 10, size=(500, 2))
    whole = fit.model.predict(q)
    chunked = fit.model.predict(q, chunk_size=37)
    assert chunked == pytest.approx(whole)
