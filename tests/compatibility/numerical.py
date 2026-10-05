"""Small deterministic calculations shared by baseline capture and runtime tests."""
import numpy as np


def calculate():
    from bestfitinterpolator.IDW_optimized import idw_interpolation
    from bestfitinterpolator.Thin_plate_spline import tps_interpolation
    from bestfitinterpolator.kriging_ordinary import ordinary_kriging_interpolation
    from bestfitinterpolator.semivariogram_engine import SemivariogramEngine, bin_experimental_variogram
    from bestfitinterpolator.diagnostics_engine import DiagnosticsEngine, classify
    from bestfitinterpolator.RF_Interpolation import rf_interpolation
    import pandas as pd

    xy = np.array([[i * 1.7 + (j % 2) * .19, j * 2.1 + (i % 3) * .13]
                   for j in range(4) for i in range(5)], dtype=float)
    z = np.sin(xy[:, 0] / 2.) + np.cos(xy[:, 1] / 3.) + .07 * xy[:, 0]
    query = np.array([[.6, .7], [2.7, 3.3], [5.8, 2.5], [4.1, 5.9], [1.3, 4.6]])
    x, y = xy.T
    qx, qy = query.T
    ordinary = SemivariogramEngine('ok_mom')
    lags, gamma = bin_experimental_variogram(x, y, z, 8., 1.5)
    results = {
        'idw': idw_interpolation(x, y, z, qx, qy, 2., 8).tolist(),
        'tps': tps_interpolation(x, y, z, qx, qy, epsilon=.0001).tolist(),
        'lags': lags.tolist(), 'semivariance': gamma.tolist(),
        'metrics': list(ordinary._validation_metrics(np.array([1., 2., 4., 6.]), np.array([1.2, 1.8, 4.4, 5.5])).values()),
    }
    for model in ('spherical', 'exponential', 'gaussian'):
        params = ordinary._guess_initial_params(lags, gamma, 8., model)
        results['fit_' + model] = list(params)
        results['model_' + model] = ordinary._model_func(lags, model, *params).tolist()
        results['kriging_' + model] = ordinary_kriging_interpolation(x, y, z, qx, qy, .05, 1.2, 4., model).tolist()
        row = ordinary._evaluate_model_cv(model, x, y, z, 8., 1.5)
        results['cv_' + model] = [row[key] for key in ('rmse', 'mae', 'r2', 'lccc')]
    diagnostic = DiagnosticsEngine().calculate(xy, z, dict(permutations=99, seed=42, neighbors=4))
    results['moran'] = [diagnostic['global_moran'][key] for key in ('I', 'p')]
    results['local_moran'] = diagnostic['local_i'].tolist()
    results['lisa'] = diagnostic['lisa'].tolist()
    results['statistical_votes'] = diagnostic['votes'].tolist()
    frame = pd.DataFrame({'x': x, 'y': y, 'value': z})
    grid = pd.DataFrame({'x': qx, 'y': qy})
    rf = rf_interpolation(frame, grid, 'value', ['x', 'y'], False,
                          {'n_estimators': 30, 'max_depth': 4, 'min_samples_leaf': 1}, {}, n_jobs=1, random_state=20)
    model = rf['model']
    residuals = z - model.predict(frame[['x', 'y']].to_numpy())
    residual = SemivariogramEngine('residual')
    rl, rg = bin_experimental_variogram(x, y, residuals, 8., 1.5)
    fits = residual._fit_variogram_candidates(rl, rg, 8.)
    best = min(fits, key=lambda fit: fit.sse)
    residual_prediction = ordinary_kriging_interpolation(x, y, residuals, qx, qy, best.nugget, best.psill, best.range_, best.model)
    results['rk_residuals'] = residuals.tolist()
    results['rk_final'] = (model.predict(grid[['x', 'y']].to_numpy()) + residual_prediction).tolist()
    return results
