import numpy as np
import pytest
from scipy.spatial.distance import cdist
from bestfitinterpolator.kriging_ordinary import ordinary_kriging_interpolation, _variogram
from bestfitinterpolator.kriging_universal import linear_design, detrend_linear
from bestfitinterpolator.kriging_workflow import fit_kriging_model, predict_kriging_fit


@pytest.mark.parametrize("model", ["spherical", "exponential", "gaussian"])
@pytest.mark.parametrize("degree", [0, 1])
def test_prediction_and_variance_match_independent_covariance_gls(model, degree):
    rng = np.random.default_rng(41)
    xy = rng.uniform(0, 200, (24, 2)) + [275000, 7480000]
    targets = rng.uniform(0, 200, (7, 2)) + [275000, 7480000]
    values = rng.normal(size=24)
    nugget, sill, scale = 0.4, 2.8, 100.0
    pred, var = ordinary_kriging_interpolation(*xy.T, values, *targets.T,
        nugget, sill, scale, model, return_variance=True, trend_degree=degree)
    covariance = nugget + sill - _variogram(cdist(xy, xy), scale, nugget, sill, model)
    cross = nugget + sill - _variogram(cdist(xy, targets), scale, nugget, sill, model)
    if degree:
        basis, origin, units = linear_design(xy)
        target_basis = linear_design(targets, origin, units)[0]
    else:
        basis, target_basis = np.ones((len(xy), 1)), np.ones((len(targets), 1))
    inverse_y = np.linalg.solve(covariance, values)
    inverse_basis = np.linalg.solve(covariance, basis)
    beta_covariance = np.linalg.inv(basis.T @ inverse_basis)
    beta = beta_covariance @ basis.T @ inverse_y
    reference_pred = target_basis @ beta + cross.T @ np.linalg.solve(covariance, values - basis @ beta)
    delta = target_basis.T - basis.T @ np.linalg.solve(covariance, cross)
    reference_var = nugget + sill - np.sum(cross * np.linalg.solve(covariance, cross), axis=0)
    reference_var += np.einsum("ij,jk,ki->i", delta.T, beta_covariance, delta)
    np.testing.assert_allclose(pred, reference_pred, atol=1e-9)
    np.testing.assert_allclose(var, reference_var, atol=1e-9)
    if degree == 0:
        old = ordinary_kriging_interpolation(*xy.T, values, *targets.T, nugget, sill, scale, model)
        np.testing.assert_array_equal(pred, old)


def test_universal_reproduces_plane_and_exact_data_and_local_variance():
    rng = np.random.default_rng(24)
    xy = rng.uniform(0, 10, (80, 2)) + [277000, 7480000]
    values = 12 + 2 * (xy[:, 0] - 277000) - 3 * (xy[:, 1] - 7480000)
    targets = rng.uniform(-5, 15, (11, 2)) + [277000, 7480000]
    for maximum in (None, 20):
        pred, var = ordinary_kriging_interpolation(*xy.T, values, *targets.T, 0.2, 3, 5,
            "spherical", nmax=maximum, trend_degree=1, return_variance=True)
        np.testing.assert_allclose(pred, 12 + 2 * (targets[:, 0] - 277000) - 3 * (targets[:, 1] - 7480000), atol=1e-7)
        assert np.isfinite(var).all() and (var >= 0).all()
    for degree in (0, 1):
        pred, var = ordinary_kriging_interpolation(*xy.T, values, *xy.T, 0.2, 3, 5,
            "spherical", trend_degree=degree, return_variance=True)
        np.testing.assert_allclose(pred, values, atol=1e-7)
        np.testing.assert_allclose(var, 0, atol=1e-8)


def test_reml_linear_design_and_predictions_are_coordinate_translation_invariant():
    from bestfitinterpolator.kriging_reml import ok_predict
    xy = np.random.default_rng(5).uniform(0, 20, (16, 2))
    values = 5 + xy[:, 0] * 3 + xy[:, 1] * 2
    params = dict(model="Sph", psill=2, range=10, nugget=0.5)
    before = ok_predict(xy, values, params, xy[:3] + 0.3, trend_degree=1)
    after = ok_predict(xy + [275000, 7480000], values, params, xy[:3] + [275000.3, 7480000.3], trend_degree=1)
    np.testing.assert_allclose(before[0], after[0], atol=1e-7)
    np.testing.assert_allclose(before[1], after[1], atol=1e-7)


def test_collinear_universal_locations_fail_explicitly():
    x = np.arange(10, dtype=float)
    with pytest.raises(ValueError, match="non-collinear"):
        detrend_linear(x, x * 2, np.sin(x))
    with pytest.raises(ValueError, match="non-collinear"):
        ordinary_kriging_interpolation(x, x * 2, np.sin(x), [1], [2], 0, 1, 3,
                                      "spherical", trend_degree=1)


def test_dense_collinear_neighborhood_does_not_fall_back_to_an_unbounded_global_system():
    xy = np.column_stack((np.arange(600, dtype=float), np.zeros(600)))
    xy = np.vstack((xy, [300.0, 10000.0]))
    with pytest.raises(ValueError, match="local.*collinear"):
        ordinary_kriging_interpolation(*xy.T, np.sin(xy[:, 0]), [0.5], [0.2],
            0.1, 1.0, 10.0, "spherical", trend_degree=1, return_variance=True)
