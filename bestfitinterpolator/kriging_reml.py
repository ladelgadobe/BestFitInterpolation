# -*- coding: utf-8 -*-
"""
REML-based variogram fitting and Ordinary Kriging prediction.
All comments are in English (as requested).

This module mirrors geoR::likfit(..., method = "REML") logic at a high level:
- Parametric covariance models (Spherical, Exponential, Gaussian)
- No experimental variogram is required; we fit by maximizing the restricted log-likelihood
- Optional trend via design matrix X (default intercept-only => Ordinary Kriging)
- Robust linear algebra using Cholesky; small jitter added for numerical stability
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass

try:
    from scipy.optimize import minimize
    _HAS_SCIPY = True
except Exception:
    _HAS_SCIPY = False


# ----------------------------
# Helpers
# ----------------------------

@dataclass
class VariogramParams:
    model: str
    psill: float
    range: float
    nugget: float
    beta: np.ndarray


def _ensure_2d_coords(coords: np.ndarray) -> np.ndarray:
    c = np.asarray(coords, dtype=float)
    if c.ndim != 2 or c.shape[1] not in (2, 3):
        raise ValueError("coords must be (n,2) or (n,3)")
    return c[:, :2]


def _design_matrix(coords: np.ndarray, degree: int) -> np.ndarray:
    x = coords[:, 0]
    y = coords[:, 1]
    if degree <= 0:
        return np.ones((coords.shape[0], 1))
    cols = [np.ones_like(x), x, y]
    if degree >= 2:
        cols += [x * x, x * y, y * y]
    return np.vstack(cols).T


# ----------------------------
# Covariance models
# ----------------------------

def _pairwise_distances(coords: np.ndarray) -> np.ndarray:
    X = coords
    diffs = X[:, None, :] - X[None, :, :]
    return np.sqrt((diffs ** 2).sum(axis=2))


def _rho(h: np.ndarray, model: str, a: float) -> np.ndarray:
    h = np.asarray(h, dtype=float)
    model = model.lower()
    a = max(float(a), 1e-12)
    r = np.zeros_like(h)
    if model in ("sph", "spherical"):
        t = np.clip(h / a, 0.0, 1.0)
        r = 1.0 - 1.5 * t + 0.5 * (t ** 3)
        r[h > a] = 0.0
    elif model in ("exp", "exponential"):
        lam = a / 3.0
        r = np.exp(-h / lam)
    elif model in ("gau", "gaussian"):
        lam = a / np.sqrt(3.0)
        r = np.exp(-(h / lam) ** 2)
    else:
        raise ValueError(f"Unsupported model: {model}")
    return r


def _cov_matrix(coords: np.ndarray, psill: float, a: float, nugget: float, model: str, jitter: float = 1e-9) -> np.ndarray:
    d = _pairwise_distances(coords)
    R = _rho(d, model, a)
    C = psill * R
    n = coords.shape[0]
    C[np.arange(n), np.arange(n)] += nugget + jitter
    return C


# ----------------------------
# Restricted log-likelihood
# ----------------------------

def _restricted_loglik(theta: np.ndarray, coords: np.ndarray, y: np.ndarray, X: np.ndarray, model: str) -> float:
    log_psill, log_a, log_nugget = theta
    psill, a, nugget = np.exp(log_psill), np.exp(log_a), np.exp(log_nugget)
    C = _cov_matrix(coords, psill, a, nugget, model)
    try:
        L = np.linalg.cholesky(C)
    except np.linalg.LinAlgError:
        return 1e20

    def chol_solve(B: np.ndarray) -> np.ndarray:
        v = np.linalg.solve(L, B)
        return np.linalg.solve(L.T, v)

    n, p = y.size, X.shape[1]
    Ci_y = chol_solve(y)
    Ci_X = chol_solve(X)
    XtCiX = X.T @ Ci_X
    try:
        XtCiX_inv = np.linalg.inv(XtCiX)
    except np.linalg.LinAlgError:
        return 1e19

    beta = XtCiX_inv @ (X.T @ Ci_y)
    r = y - X @ beta
    Ci_r = chol_solve(r)

    logdetC = 2.0 * np.sum(np.log(np.diag(L)))
    L2 = np.linalg.cholesky(XtCiX)
    logdetXtCiX = 2.0 * np.sum(np.log(np.diag(L2)))
    nll = 0.5 * (logdetC + logdetXtCiX + r.T @ Ci_r)
    return float(nll)


# ----------------------------
# Fitting
# ----------------------------

def fit_variogram_reml(
    coords: np.ndarray,
    values: np.ndarray,
    model: str = "Sph",
    init: dict | None = None,
    bounds: dict | None = None,
    trend_degree: int = 0,
    nugget_fixed: float | None = None,
    anisotropy: dict | None = None,
    random_state: int | None = None,
) -> dict:
    rng = np.random.default_rng(random_state)
    XY = _ensure_2d_coords(coords)
    y = np.asarray(values, dtype=float).ravel()
    X = _design_matrix(XY, trend_degree)
    y_var = np.var(y, ddof=1) if len(y) > 1 else 1.0
    dmat = _pairwise_distances(XY)
    max_d = np.percentile(dmat, 95)
    default_bounds = {
        "psill": (y_var * 1e-6, y_var * 100.0),
        "range": (max_d * 0.05, max_d * 3.0),
        "nugget": (y_var * 1e-6, y_var * 10.0),
    }

    if init is None:
        init = {
            "psill": y_var * 0.7,
            "range": max_d * 0.6,
            "nugget": y_var * 0.3,
        }

    # Keep REML anchored to the MoM nugget when an initial guess is provided.
    # The previous lower bound was nearly zero (y_var * 1e-6), which allowed
    # the optimizer to collapse the nugget to ~0 even when the MoM fit showed
    # a meaningful nugget effect. Here we preserve flexibility, but prevent
    # unrealistic collapse by using a lower bound based on the initial nugget.
    init_psill = max(float(init.get("psill", y_var * 0.7)), y_var * 1e-9)
    init_range = max(float(init.get("range", max_d * 0.6)), max(max_d * 1e-9, 1e-9))
    init_nugget = max(float(init.get("nugget", y_var * 0.3)), 0.0)

    user_bounds = bounds or {}

    nugget_lb_default = y_var * 1e-6
    if init_nugget > 0.0:
        nugget_lb_default = max(
            nugget_lb_default,
            min(init_nugget * 0.25, init_nugget)
        )

    psill_bounds = user_bounds.get("psill", default_bounds["psill"])
    range_bounds = user_bounds.get("range", default_bounds["range"])
    nugget_bounds = user_bounds.get("nugget", (nugget_lb_default, default_bounds["nugget"][1]))

    # Sanity clamp user/derived bounds
    psill_bounds = (max(psill_bounds[0], y_var * 1e-12), max(psill_bounds[1], max(psill_bounds[0] * 1.01, y_var * 1e-11)))
    range_bounds = (max(range_bounds[0], 1e-12), max(range_bounds[1], range_bounds[0] * 1.01))
    nugget_bounds = (max(nugget_bounds[0], 0.0), max(nugget_bounds[1], max(nugget_bounds[0] * 1.01, 1e-12)))

    # Keep initial values inside the feasible box
    init_psill = min(max(init_psill, psill_bounds[0]), psill_bounds[1])
    init_range = min(max(init_range, range_bounds[0]), range_bounds[1])
    init_nugget = min(max(init_nugget, nugget_bounds[0]), nugget_bounds[1])

    def pack(psill, a, nug): return np.log([psill, a, nug])

    if nugget_fixed is not None:
        def obj_free(theta_free):
            theta = np.array([theta_free[0], theta_free[1], np.log(nugget_fixed)])
            return _restricted_loglik(theta, XY, y, X, model)

        x0 = np.log([init_psill, init_range])
        bnds = [(np.log(psill_bounds[0]), np.log(psill_bounds[1])),
                (np.log(range_bounds[0]), np.log(range_bounds[1]))]
        res = minimize(obj_free, x0=x0, method="L-BFGS-B", bounds=bnds)
        ps, a, ng = np.exp(res.x[0]), np.exp(res.x[1]), nugget_fixed
        converged, niter, reml_val = res.success, res.nit, -res.fun
    else:
        x0 = pack(init_psill, init_range, init_nugget)
        bnds = [(np.log(psill_bounds[0]), np.log(psill_bounds[1])),
                (np.log(range_bounds[0]), np.log(range_bounds[1])),
                (np.log(max(nugget_bounds[0], 1e-15)), np.log(nugget_bounds[1]))]
        res = minimize(_restricted_loglik, x0=x0, args=(XY, y, X, model),
                       method="L-BFGS-B", bounds=bnds)
        ps, a, ng = np.exp(res.x)
        converged, niter, reml_val = res.success, res.nit, -res.fun

    C = _cov_matrix(XY, ps, a, ng, model)
    L = np.linalg.cholesky(C)
    def chol_solve(B): v = np.linalg.solve(L, B); return np.linalg.solve(L.T, v)
    Ci_X = chol_solve(X)
    XtCiX = X.T @ Ci_X
    beta = np.linalg.inv(XtCiX) @ (X.T @ chol_solve(y))
    return {"model": model, "psill": ps, "range": a, "nugget": ng,
            "beta": beta, "reml_value": reml_val, "converged": converged, "niter": niter}


# ----------------------------
# Prediction
# ----------------------------

def ok_predict(coords, values, params, pred_coords, return_var=True, trend_degree=0):
    XY = _ensure_2d_coords(coords)
    y = np.asarray(values, float).ravel()
    XP = _ensure_2d_coords(pred_coords)
    model, ps, a, ng = params["model"], params["psill"], params["range"], params["nugget"]
    X, Xp = _design_matrix(XY, trend_degree), _design_matrix(XP, trend_degree)
    C = _cov_matrix(XY, ps, a, ng, model)
    L = np.linalg.cholesky(C)
    def chol_solve(B): v = np.linalg.solve(L, B); return np.linalg.solve(L.T, v)
    Ci = lambda B: chol_solve(B)
    Ci_y, Ci_X = Ci(y), Ci(X)
    XtCiX = X.T @ Ci_X
    XtCiX_inv = np.linalg.inv(XtCiX)
    beta = XtCiX_inv @ (X.T @ Ci_y)
    d_cross = np.sqrt(((XY[:, None, :] - XP[None, :, :]) ** 2).sum(axis=2))
    K = ps * _rho(d_cross, model, a)
    yc = y - X @ beta
    w = Ci(yc)
    pred = Xp @ beta + K.T @ w
    if not return_var:
        return pred, None
    Ci_K = Ci(K)
    XTCi = X.T @ Ci
    XTCiK = XTCi(K)
    middle = Xp.T - XTCiK
    term_gls = np.einsum("ij,jk,ki->i", middle.T, XtCiX_inv, middle)
    kCik = np.sum(K * Ci_K, axis=0)
    var = ps - kCik + term_gls
    var = np.maximum(var, 0.0)
    return pred, var


# ----------------------------
# Cross-validation
# ----------------------------

def _metrics(y, yhat):
    y, yhat = np.asarray(y, float), np.asarray(yhat, float)
    resid = yhat - y
    mae = np.mean(np.abs(resid))
    rmse = np.sqrt(np.mean(resid ** 2))
    ybar = np.mean(y)
    r2 = 1 - np.sum((y - yhat) ** 2) / np.sum((y - ybar) ** 2)
    s_y, s_yhat = np.std(y), np.std(yhat)
    cov = np.mean((y - ybar) * (yhat - np.mean(yhat)))
    ccc = (2 * cov) / (s_y ** 2 + s_yhat ** 2 + (ybar - np.mean(yhat)) ** 2 + 1e-12)
    rmse_pct = (rmse / (np.mean(np.abs(y)) + 1e-12)) * 100
    return mae, rmse, r2, ccc, rmse_pct


def kfold_cv_ok_reml(coords, values, params, k=10, trend_degree=0):
    XY = _ensure_2d_coords(coords)
    y = np.asarray(values, float).ravel()
    n = len(y)
    if k <= 1 or k >= n:
        idx = np.arange(n)
        yhat = np.zeros(n, float)
        for i in range(n):
            mask = idx != i
            pred, _ = ok_predict(XY[mask], y[mask], params, XY[[i]], return_var=False, trend_degree=trend_degree)
            yhat[i] = pred[0]
    else:
        rng = np.random.default_rng(123)
        perm = rng.permutation(n)
        folds = np.array_split(perm, k)
        yhat = np.zeros(n, float)
        for fold in folds:
            train = np.setdiff1d(np.arange(n), fold)
            pred, _ = ok_predict(XY[train], y[train], params, XY[fold], return_var=False, trend_degree=trend_degree)
            yhat[fold] = pred
    mae, rmse, r2, ccc, rmse_pct = _metrics(y, yhat)
    return {"rmse": rmse, "mae": mae, "r2": r2, "ccc": ccc,
            "rmse_pct": rmse_pct, "y_true": y, "y_pred": yhat}
