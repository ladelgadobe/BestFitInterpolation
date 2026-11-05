"""Reviewer 1 regressions: joint fitting and consistent range conventions."""
import numpy as np
from bestfitinterpolator.semivariogram_engine import SemivariogramEngine
from bestfitinterpolator.semivariogram_fit import fit_joint_wls, practical_range, practical_range_factor
from bestfitinterpolator import reml_bridge as bridge
from bestfitinterpolator.kriging_reml import _rho, ok_predict, kfold_cv_ok_reml
from bestfitinterpolator.kriging_ordinary import ordinary_kriging_interpolation


def test_joint_fit_recovers_all_three_parameters_for_each_model():
    h = np.arange(10.0, 210.0, 10.0)
    for profile in ("ok_mom", "ok_reml", "framework", "framework_sdi"):
        engine = SemivariogramEngine(profile, use_reml=False)
        for model in ("spherical", "exponential", "gaussian"):
            for truth in ((2., 8., 50.), (0., 5., 32.), (9., 1., 70.)):
                g = engine._model_func(h, model, *truth)
                fitted = engine._guess_initial_params(h, g, 220., model)
                np.testing.assert_allclose(fitted, truth, atol=1e-6, rtol=1e-6)
                assert engine._last_mom_fit_info["converged"]
                assert engine._last_mom_fit_info["weighted_sse"] < 1e-15


def test_joint_fit_matches_independent_bounded_nonlinear_optimizer():
    from scipy.optimize import least_squares
    engine = SemivariogramEngine()
    h = np.linspace(5., 200., 35)
    for model in ("spherical", "exponential", "gaussian"):
        noise = np.random.default_rng(17).normal(0, .15, h.size)
        g = engine._model_func(h, model, 2., 8., 50.) + noise
        actual = engine._guess_initial_params(h, g, 220., model)
        weights = np.sqrt(1.0 / (1.0 + h / np.median(h)))
        residual = lambda p: weights * (engine._model_func(h, model, *p) - g)
        reference = least_squares(residual, [1., 9., 40.], bounds=([0, 1e-12, .05], [np.inf, np.inf, 2200.]),
                                  xtol=1e-12, ftol=1e-12, gtol=1e-12)
        np.testing.assert_allclose(actual, reference.x, rtol=2e-5, atol=2e-5)
        assert np.sum(residual(actual)**2) <= np.sum(reference.fun**2) + 1e-10


def test_wls_is_invariant_to_distance_and_response_units():
    h = np.arange(10., 210., 10.)
    engine = SemivariogramEngine()
    for model in ("spherical", "exponential", "gaussian"):
        g = engine._model_func(h, model, 2., 8., 50.)
        for distance_scale, variance_scale in ((1e-3, 1e6), (1000., 1e-6)):
            actual = engine._guess_initial_params(h*distance_scale, g*variance_scale, 220.*distance_scale, model)
            np.testing.assert_allclose(actual, [2.*variance_scale, 8.*variance_scale, 50.*distance_scale], rtol=2e-6, atol=1e-10)


def test_sparse_constant_invalid_and_boundary_fits_are_explicit():
    initial = (0., 1., 10.)
    for h, g, status in (([], [], "no_valid_bins"), ([1.,2.], [1.,2.], "insufficient_distinct_bins"),
                          ([1.,2.,3.], [0.,0.,0.], "zero_semivariance")):
        params, info = fit_joint_wls(h, g, 10., "exponential", initial)
        assert np.isfinite(params).all() and params[2] > 0
        assert info["status"] == status and not info["converged"]
    h = np.arange(1., 21.)
    params, info = fit_joint_wls(h, np.ones_like(h)*7., 20., "gaussian", initial)
    assert np.isfinite(params).all() and params[0] >= 0 and params[1] > 0
    assert info["status"] in ("weak_structure", "range_bound")
    params, info = fit_joint_wls(np.r_[h, np.nan, -1], np.r_[2.+h, 3., -1.], 20., "exponential", initial)
    assert info["bins"] == 20 and np.isfinite(params).all()


def test_practical_range_matches_each_implemented_covariance():
    for model in ("spherical", "exponential", "gaussian"):
        scale = 17.
        practical = practical_range(model, scale)
        assert practical == scale * practical_range_factor(model)
        h = np.linspace(.1, 100., 40)
        shown = SemivariogramEngine()._model_func(h, model, .2, 1.3, scale)
        backend = .2 + 1.3 * (1. - _rho(h, model, practical))
        np.testing.assert_allclose(shown, backend, rtol=1e-13, atol=1e-13)
        fraction = (SemivariogramEngine()._model_func([practical], model, .2, 1.3, scale)[0] - .2) / 1.3
        np.testing.assert_allclose(fraction, 1. if model == "spherical" else 1.-np.exp(-3.))


def test_reml_bridge_converts_inputs_bounds_outputs_and_preserves_caller_dicts():
    original = bridge.fit_variogram_reml
    try:
        for model in ("Sph", "Exp", "Gau"):
            captured = {}
            def fake_fit(**kwargs):
                captured.update(kwargs)
                return dict(model=model, range=kwargs["init"]["range"], psill=8., nugget=2.)
            bridge.fit_variogram_reml = fake_fit
            seed = dict(nugget=2., psill=8., range=50.)
            bounds = dict(range=(1., 100.))
            fit = bridge.fit_ok_reml_interface(np.array([[0.,0.,1.],[1.,1.,2.]]), model=model, init_from_mom=seed, bounds=bounds)
            factor = practical_range_factor(model)
            assert captured["init"]["range"] == 50.*factor
            assert captured["bounds"]["range"] == (factor, 100.*factor)
            assert fit["range"] == 50. and fit["range_parameterization"] == "model_scale"
            assert seed["range"] == 50. and bounds["range"] == (1.,100.)
            assert bridge._to_backend_result(fit)["range"] == 50.*factor
            legacy = dict(model=model, range=77.)
            assert bridge._to_backend_result(legacy)["range"] == 77.
    finally:
        bridge.fit_variogram_reml = original


def test_reml_prediction_validation_and_ordinary_solver_share_the_same_scale():
    rng = np.random.default_rng(4)
    xy = rng.uniform(0., 20., (14,2))
    z = np.sin(xy[:,0]/5.) + .1*xy[:,1]
    xyz = np.column_stack((xy,z))
    query = np.array([[1.,3.],[7.,11.],[15.,6.]])
    for model in ("spherical", "exponential", "gaussian"):
        fit = dict(model=model, nugget=.2, psill=1.3, range=8., range_parameterization="model_scale")
        expected_backend = dict(fit, range=practical_range(model, 8.))
        prediction, variance = bridge.predict_ok_reml_interface(fit, xyz, query)
        expected, expected_variance = ok_predict(xy, z, expected_backend, query, return_var=True)
        ordinary = ordinary_kriging_interpolation(xy[:,0],xy[:,1],z,query[:,0],query[:,1],.2,1.3,8.,model)
        np.testing.assert_allclose(prediction, expected, rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose(variance, expected_variance, rtol=1e-12, atol=1e-12)
        np.testing.assert_allclose(prediction, ordinary, rtol=1e-7, atol=1e-7)
        cv = bridge.cv_ok_reml_interface(xyz, fit)
        expected_cv = kfold_cv_ok_reml(xy,z,expected_backend,k=0)
        np.testing.assert_allclose(cv["y_pred"],expected_cv["y_pred"],rtol=1e-12,atol=1e-12)


def test_reml_validation_reports_the_parameters_actually_validated():
    rng = np.random.default_rng(17)
    xy = rng.uniform(0., 12., (8,2))
    z = np.sin(xy[:,0]/3.) + .15*xy[:,1]
    engine = SemivariogramEngine("ok_reml")
    for model in ("spherical", "exponential", "gaussian"):
        row = engine._evaluate_model_cv(model,xy[:,0],xy[:,1],z,10.,2.)
        assert row["selection"] == "reml_cv"
        np.testing.assert_array_equal(row["fitted_params"], [row[k] for k in ("nugget","psill","range")])
