# -*- coding: utf-8 -*-
"""Behavioral tests for core.variogram: empirical binning, model curves,
MoM/REML fitting on synthetic fields, and the strategy chooser."""

import numpy as np
import pytest

from bestfitinterpolator.core import variogram as vg
from bestfitinterpolator.core.exceptions import DependencyMissing


def _gaussian_field(n=120, range_=30.0, psill=4.0, nugget=0.5, seed=7):
    """Sample a stationary GRF with an exponential covariance so the fitted
    variogram parameters can be compared against the generating truth."""
    rng = np.random.default_rng(seed)
    xy = rng.uniform(0, 100, size=(n, 2))
    d = np.sqrt(((xy[:, None, :] - xy[None, :, :]) ** 2).sum(axis=2))
    cov = psill * np.exp(-3.0 * d / range_) + nugget * np.eye(n)
    L = np.linalg.cholesky(cov + 1e-10 * np.eye(n))
    z = 10.0 + L @ rng.standard_normal(n)
    return xy[:, 0], xy[:, 1], z


def test_normalize_model_token():
    assert vg.normalize_model_token("Spherical") == "spherical"
    assert vg.normalize_model_token("Esférico") == "spherical"
    assert vg.normalize_model_token("gauss") == "gaussian"
    assert vg.normalize_model_token("Exponential") == "exponential"
    assert vg.normalize_model_token("") == "exponential"
    assert vg.normalize_model_token(None) == "exponential"


def test_model_gamma_shapes_and_limits():
    h = np.array([0.0, 5.0, 10.0, 50.0])
    for model in ("spherical", "exponential", "gaussian"):
        g = vg.model_gamma(h, model, nugget=1.0, psill=3.0, range_=10.0)
        assert g.shape == h.shape
        assert g[0] == pytest.approx(1.0)          # nugget at h=0 (curve, not kriging matrix)
        assert np.all(np.diff(g) >= -1e-9)          # monotone non-decreasing
    # spherical reaches the full sill exactly at the range
    g_sph = vg.model_gamma(np.array([10.0, 50.0]), "spherical", 1.0, 3.0, 10.0)
    assert g_sph[0] == pytest.approx(4.0)
    assert g_sph[1] == pytest.approx(4.0)


def test_empirical_variogram_two_points():
    # single pair at distance 10 with dz=2 -> gamma = 0.5*4 = 2
    lags, gamma = vg.empirical_variogram(
        np.array([0.0, 10.0]), np.array([0.0, 0.0]), np.array([1.0, 3.0]),
        cutoff=20.0, lag_width=5.0,
    )
    assert lags.tolist() == [10.0]
    assert gamma.tolist() == [2.0]


def test_empirical_variogram_increases_for_correlated_field():
    x, y, z = _gaussian_field()
    cutoff = vg.default_cutoff(x, y)
    lags, gamma = vg.empirical_variogram(x, y, z, cutoff, None)
    assert lags.size >= 5
    # semivariance near the origin must be well below the tail plateau
    assert gamma[0] < np.median(gamma[-3:])


def test_fit_variogram_mom_recovers_synthetic_parameters():
    x, y, z = _gaussian_field()
    model = vg.fit_variogram_mom(x, y, z, model="exponential")
    assert model.strategy == "mom"
    assert model.model == "exponential"
    # generous tolerances: MoM on one 120-point realization is noisy
    assert 0.0 <= model.nugget < 3.0
    assert 1.0 < model.psill < 12.0
    assert 5.0 < model.range_ < 100.0
    assert model.fit_report["lags"].size > 0


def test_fit_variogram_reml_close_to_mom_on_same_field():
    pytest.importorskip("scipy")
    x, y, z = _gaussian_field()
    mom = vg.fit_variogram_mom(x, y, z, model="exponential")
    reml = vg.fit_variogram_reml_model(x, y, z, model="exponential")
    assert reml.strategy == "reml"
    # same order of magnitude for total sill — parity guard for the clone merge
    assert reml.sill == pytest.approx(mom.sill, rel=2.0)
    assert reml.fit_report["converged"]


def test_choose_strategy_rules_verbatim():
    d = vg.choose_strategy(50, "Automatic", reml_ok=True)
    assert d.mode == "REML"
    assert vg.choose_strategy(100, "Automatic", reml_ok=True).mode == "MoM"
    assert vg.choose_strategy(50, "Automatic", reml_ok=False).mode == "MoM"
    assert vg.choose_strategy(499, "REML", reml_ok=True).mode == "REML"
    d = vg.choose_strategy(500, "REML", reml_ok=True)
    assert d.mode == "MoM" and "500" in d.reason
    d = vg.choose_strategy(50, "REML", reml_ok=False)
    assert d.mode == "MoM" and "unavailable" in d.reason
    assert vg.choose_strategy(10, "MoM", reml_ok=True).mode == "MoM"


def test_safe_lag_width_guards():
    x = np.array([0.0, 1.0, 5.0])
    y = np.zeros(3)
    assert np.isnan(vg.safe_lag_width(x, y, cutoff=-1, lag_width=1))
    # invalid width falls back to nearest-neighbor distance (=1.0)
    assert vg.safe_lag_width(x, y, cutoff=10.0, lag_width=0) == pytest.approx(1.0)
    # width floor prevents pathological bin counts
    assert vg.safe_lag_width(x, y, 10.0, 1e-9, max_bins=10) == pytest.approx(1.0)
