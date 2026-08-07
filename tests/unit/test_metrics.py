# -*- coding: utf-8 -*-
"""Behavioral tests for core.metrics against hand-computed values."""

import numpy as np
import pytest

from bestfitinterpolator.core import metrics


OBS = np.array([1.0, 2.0, 3.0, 4.0])
PRED = np.array([1.5, 1.5, 3.5, 4.0])


def test_rmse_hand_computed():
    # errors: -0.5, 0.5, -0.5, 0.0 -> mse = 0.75/4
    assert metrics.rmse(OBS, PRED) == pytest.approx(np.sqrt(0.1875))


def test_mae_hand_computed():
    assert metrics.mae(OBS, PRED) == pytest.approx(1.5 / 4)


def test_rmse_pct_is_rmse_over_mean():
    expected = metrics.rmse(OBS, PRED) / 2.5 * 100.0
    assert metrics.rmse_pct(OBS, PRED) == pytest.approx(expected)


def test_r2_perfect_prediction_is_one():
    assert metrics.r2(OBS, OBS) == pytest.approx(1.0)


def test_pearson_r_perfect_linear():
    assert metrics.pearson_r(OBS, 2 * OBS + 1) == pytest.approx(1.0)


def test_lccc_perfect_agreement_is_one():
    assert metrics.lccc(OBS, OBS.copy()) == pytest.approx(1.0)


def test_lccc_penalizes_bias_unlike_pearson():
    shifted = OBS + 10.0
    assert metrics.pearson_r(OBS, shifted) == pytest.approx(1.0)
    assert metrics.lccc(OBS, shifted) < 0.1


def test_nan_policy_ignores_nonfinite_pairs():
    obs = np.array([1.0, 2.0, np.nan, 4.0])
    pred = np.array([1.0, 2.0, 3.0, np.nan])
    m = metrics.compute_metrics(obs, pred)
    assert m.n == 2
    assert m.rmse == pytest.approx(0.0)


def test_degenerate_single_point_gives_nan_correlations():
    assert np.isnan(metrics.r2([1.0], [1.0]))
    assert np.isnan(metrics.pearson_r([1.0], [1.0]))
    assert np.isnan(metrics.lccc([1.0], [1.0]))


def test_isi_normalization():
    # normalized_mae = 0.5, normalized_sae = 0.5 -> 1.0
    assert metrics.calculate_isi(1.0, 1.5, 2.0, 1.0, 2.0) == pytest.approx(1.0)
    # degenerate denominators fall back to zero contributions
    assert metrics.calculate_isi(1.0, 1.0, 0.0, 1.0, 1.0) == pytest.approx(0.0)
