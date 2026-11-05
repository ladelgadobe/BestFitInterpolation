"""Fitting and fold-local validation for new geostatistical options."""
import numpy as np
from .kriging_ordinary import ordinary_kriging_interpolation
from .kriging_universal import detrend_linear
from .semivariogram_fit import model_token
from .variogram_utils import bin_experimental_variogram, max_pairwise_distance, nearest_neighbor_distance
from .validation_policy import decide_automatic_cv


def fit_kriging_model(xy, values, model="spherical", backend="MoM", trend_degree=0,
                      cutoff=None, lag=None):
    from .semivariogram_engine import SemivariogramEngine
    xy, values = np.asarray(xy, float), np.asarray(values, float)
    residual = detrend_linear(xy[:, 0], xy[:, 1], values)[0] if trend_degree else values
    cutoff = float(cutoff or max_pairwise_distance(xy[:, 0], xy[:, 1]) / 2.0)
    cutoff = max(cutoff, 1e-9)
    lag = float(lag or max(nearest_neighbor_distance(xy[:, 0], xy[:, 1]), cutoff / 12.0))
    token = model_token(model)
    lags, gamma = bin_experimental_variogram(xy[:, 0], xy[:, 1], residual, cutoff, lag)
    engine = SemivariogramEngine("ok_mom")
    params = engine._guess_initial_params(lags, gamma, cutoff, token)
    fit = dict(model=token, nugget=params[0], psill=params[1], range=params[2],
               range_parameterization="model_scale", trend_degree=int(trend_degree),
               backend=backend, cutoff=cutoff, lag=lag)
    if backend == "REML":
        from .reml_bridge import fit_ok_reml_interface
        result = fit_ok_reml_interface(np.column_stack((xy, values)), model=token,
            trend_degree=int(trend_degree), init_from_mom=dict(zip(("nugget", "psill", "range"), params)))
        fit.update(result)
    return fit


def predict_kriging_fit(xy, values, targets, fit, return_variance=False, progress_fn=None):
    return ordinary_kriging_interpolation(
        xy[:, 0], xy[:, 1], values, targets[:, 0], targets[:, 1],
        fit["nugget"], fit["psill"], fit["range"], fit["model"],
        trend_degree=fit.get("trend_degree", 0), return_variance=return_variance,
        progress_fn=progress_fn)


def automatic_test_folds(n, seed=20):
    mode, k = decide_automatic_cv(n)
    if mode == "loocv":
        return [np.array([i], int) for i in range(n)]
    indices = np.random.default_rng(seed).permutation(n)
    return [part for part in np.array_split(indices, k) if len(part)]


def validate_kriging_model(xy, values, model, backend="MoM", trend_degree=0,
                           cutoff=None, lag=None, folds=None, cancelled=lambda: False):
    xy, values = np.asarray(xy, float), np.asarray(values, float)
    prediction = np.full(len(values), np.nan)
    for test in (automatic_test_folds(len(values)) if folds is None else folds):
        if cancelled():
            raise InterruptedError("Validation cancelled")
        train = np.ones(len(values), bool)
        train[test] = False
        fit = fit_kriging_model(xy[train], values[train], model, backend, trend_degree, cutoff, lag)
        prediction[test] = predict_kriging_fit(xy[train], values[train], xy[test], fit)
    from .semivariogram_engine import SemivariogramEngine
    metrics = SemivariogramEngine("ok_mom")._validation_metrics(values, prediction)
    fit = fit_kriging_model(xy, values, model, backend, trend_degree, cutoff, lag)
    metrics.update(model=str(model).capitalize(), model_key=model_token(model),
        nugget=fit["nugget"], psill=fit["psill"], range=fit["range"],
        fitted_params=tuple(fit[key] for key in ("nugget", "psill", "range")),
        selection="training-fold refit", validation_n=len(values), trend_degree=trend_degree)
    return metrics, prediction
