# -*- coding: utf-8 -*-
"""Variogram estimation and fitting — the single implementation of the
empirical binning, theoretical models, initial-parameter search (MoM fit) and
REML fit formerly duplicated across the OK controllers, the framework tab and
the regression-kriging controller.

Numerics are byte-close to the legacy code so fitted parameters are unchanged
by the restructure.
"""

from __future__ import annotations

import math

import numpy as np

from .deps import import_scipy_optimize
from .exceptions import ComputationError
from .types import VariogramModel

# ----------------------------- model tokens --------------------------------

MODEL_TOKENS = ("spherical", "exponential", "gaussian")


def normalize_model_token(txt: str) -> str:
    t = (str(txt) or "").strip().lower()
    if t.startswith(("sph", "esf")):  # Spherical/Esférico
        return "spherical"
    if t.startswith(("gau", "gaus")):
        return "gaussian"
    if t.startswith(("exp", "expon")):
        return "exponential"
    if "spher" in t:
        return "spherical"
    if "gaus" in t:
        return "gaussian"
    return "exponential"


def model_gamma(h, model: str, nugget: float, psill: float, range_: float):
    """Theoretical semivariogram γ(h) for Spherical / Exponential / Gaussian.
    Legacy _model_func semantics: nugget applies for every h (no γ(0)=0 rule —
    the kriging system enforces that separately)."""
    h = np.asarray(h, dtype=float)
    c0 = float(nugget)
    c = float(psill)
    a = max(float(range_), 1e-9)
    if model == "spherical":
        hr = np.clip(h / a, 0.0, 1.0)
        sph = c * (1.5 * hr - 0.5 * (hr ** 3))
        return np.where(h <= a, c0 + sph, c0 + c)
    elif model == "gaussian":
        return c0 + c * (1.0 - np.exp(-(h * h) / (a * a)))
    else:  # exponential
        return c0 + c * (1.0 - np.exp(-h / a))


# --------------------------- empirical variogram ---------------------------

def nearest_neighbor_dist(x, y) -> float:
    """Minimum positive nearest-neighbor distance."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    n = x.size
    if n < 2:
        return float("nan")
    scale = max(
        float(np.nanmax(np.abs(x))) if x.size else 0.0,
        float(np.nanmax(np.abs(y))) if y.size else 0.0,
        1.0,
    )
    zero_tol = np.finfo(float).eps * scale * 32.0
    dmin = np.inf
    for i in range(n):
        dx = x - x[i]
        dy = y - y[i]
        dist = np.hypot(dx, dy)
        dist[i] = np.inf
        dist = dist[np.isfinite(dist) & (dist > zero_tol)]
        if dist.size == 0:
            continue
        mi = float(np.min(dist))
        if mi < dmin:
            dmin = mi
    return dmin if np.isfinite(dmin) else float("nan")


def safe_lag_width(x, y, cutoff, lag_width, max_bins=10000) -> float:
    """Keep lag width positive while preventing pathological bin counts."""
    try:
        cutoff = float(cutoff)
    except Exception:
        cutoff = np.nan
    if not np.isfinite(cutoff) or cutoff <= 0:
        return float("nan")
    try:
        lag_width = float(lag_width)
    except Exception:
        lag_width = np.nan
    if not np.isfinite(lag_width) or lag_width <= 0:
        lag_width = float(nearest_neighbor_dist(x, y))
    if not np.isfinite(lag_width) or lag_width <= 0:
        lag_width = cutoff / 12.0
    min_width = cutoff / float(max(1, int(max_bins)))
    if lag_width < min_width:
        lag_width = min_width
    return float(lag_width)


def default_cutoff(x, y) -> float:
    """Half the maximum pairwise distance — the legacy default."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    dmax = 0.0
    for i in range(x.size - 1):
        d = np.hypot(x[i + 1 :] - x[i], y[i + 1 :] - y[i])
        if d.size:
            m = float(np.nanmax(d))
            if m > dmax:
                dmax = m
    return 0.5 * dmax


def empirical_variogram(x, y, z, cutoff, lag_width):
    """Binned experimental semivariogram up to ``cutoff`` with bin size
    ``lag_width``. Returns (lags, gamma) with empty-bin rows dropped."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    z = np.asarray(z, dtype=float)
    cutoff = float(cutoff)
    lag_width = safe_lag_width(x, y, cutoff, lag_width)
    if not np.isfinite(cutoff) or cutoff <= 0 or not np.isfinite(lag_width) or lag_width <= 0:
        return np.array([], dtype=float), np.array([], dtype=float)
    nbins = max(1, int(math.floor(cutoff / lag_width)))
    if nbins > 10000:
        nbins = 10000
        lag_width = cutoff / float(nbins)
    sums = np.zeros(nbins, dtype=float)
    counts = np.zeros(nbins, dtype=int)
    dists = np.zeros(nbins, dtype=float)
    n = x.size
    for i in range(n - 1):
        xi, yi, zi = x[i], y[i], z[i]
        xj = x[i + 1 :]
        yj = y[i + 1 :]
        zj = z[i + 1 :]
        dd = np.hypot(xj - xi, yj - yi)
        mask = (dd > 0) & (dd <= cutoff)
        if not np.any(mask):
            continue
        dd = dd[mask]
        diff = zi - zj[mask]
        gj = 0.5 * (diff * diff)
        bin_idx = np.floor(dd / lag_width).astype(int)
        bin_idx[bin_idx == nbins] = nbins - 1  # clamp edge case
        np.add.at(sums, bin_idx, gj)
        np.add.at(counts, bin_idx, 1)
        np.add.at(dists, bin_idx, dd)
    valid = counts > 0
    default_centers = np.linspace(
        lag_width * 0.5, nbins * lag_width - lag_width * 0.5, nbins
    )
    lags = np.where(valid, dists / np.maximum(counts, 1), default_centers)
    gamma = np.where(valid, sums / np.maximum(counts, 1), np.nan)
    keep = ~np.isnan(gamma)
    return lags[keep], gamma[keep]


# ------------------------ MoM fit (initial-param search) --------------------

def guess_initial_params(lags, gamma, cutoff, model="exponential"):
    """MoM-style automatic fit for (nugget, psill, range): robust seeds plus a
    lightweight coarse search over range and nugget, solving the partial sill
    analytically for each candidate (legacy _guess_initial_params verbatim)."""
    lags = np.asarray(lags, dtype=float)
    gamma = np.asarray(gamma, dtype=float)
    keep = np.isfinite(lags) & np.isfinite(gamma) & (lags > 0)
    lags = lags[keep]
    gamma = gamma[keep]

    if lags.size == 0:
        return 0.0, 1.0, max(1.0, cutoff * 0.4)

    order = np.argsort(lags)
    lags = lags[order]
    gamma = gamma[order]

    # --- Base robust heuristics ---
    first_vals = gamma[: max(1, min(3, gamma.size))]
    tail_vals = gamma[-max(3, max(1, gamma.size // 3)) :]

    first_bin = float(first_vals[0]) if first_vals.size else 0.0
    first_max = float(np.nanmax(first_vals)) if first_vals.size else first_bin

    # Linear back-extrapolation using the first two bins when possible.
    nugget_intercept = first_bin
    if lags.size >= 2:
        h1, h2 = float(lags[0]), float(lags[1])
        g1, g2 = float(gamma[0]), float(gamma[1])
        if abs(h2 - h1) > 1e-12:
            slope = (g2 - g1) / (h2 - h1)
            nugget_intercept = float(g1 - slope * h1)

    nugget_floor = 0.75 * first_bin
    nugget_seed = float(max(0.0, max(max(0.0, nugget_intercept), nugget_floor, first_bin)))
    plateau_seed = float(np.nanmedian(tail_vals))
    max_seed = float(np.nanmax(gamma))
    sill_total_seed = max(plateau_seed, max_seed, first_max, nugget_seed + 1e-6)

    # Initial range seed from the first empirical crossing near the plateau
    target = 0.90 * sill_total_seed
    idx = np.where(gamma >= target)[0]
    if idx.size > 0:
        range_seed = float(lags[idx[0]])
    else:
        range_seed = float(0.60 * cutoff)
    range_seed = max(range_seed, float(np.nanmin(lags)), 1e-9)

    nugget_cap = max(0.0, min(first_max, 0.90 * sill_total_seed))
    nugget_seed = float(np.clip(nugget_seed, 0.0, nugget_cap)) if nugget_cap > 0 else 0.0
    nugget_candidates = np.array([nugget_seed], dtype=float)

    # Candidate ranges spanning from early structure to almost the cutoff.
    lag_min = max(float(np.nanmin(lags)), 1e-9)
    lag_max = max(float(np.nanmax(lags)), lag_min)
    low = max(lag_min, 0.20 * range_seed)
    high = max(low * 1.05, min(float(cutoff), max(lag_max * 1.15, range_seed * 1.8, low)))
    range_candidates = np.unique(
        np.concatenate(
            [
                np.linspace(low, high, 28),
                np.array([range_seed, 0.5 * cutoff, 0.75 * cutoff, lag_max], dtype=float),
            ]
        )
    )
    range_candidates = range_candidates[np.isfinite(range_candidates) & (range_candidates > 0)]

    # Weight the first half of the variogram so the automatic fit follows the
    # experimental points more closely near the origin.
    lag_scale = max(float(np.nanmedian(lags)), 1e-9)
    weights = 1.0 / (1.0 + (lags / lag_scale))

    best = None
    model_token = normalize_model_token(model)

    for nugget in nugget_candidates:
        yv = gamma - float(nugget)
        for rng in range_candidates:
            basis = model_gamma(lags, model_token, 0.0, 1.0, float(rng))
            denom = float(np.sum(weights * basis * basis))
            if denom <= 0:
                continue
            psill = float(np.sum(weights * basis * yv) / denom)
            psill = max(psill, 1e-9)

            pred = float(nugget) + psill * basis
            sse = float(np.sum(weights * (gamma - pred) ** 2))
            # Tiny regularization on the range only; larger nuggets are not
            # penalized because a real nugget effect can be legitimate.
            sse += 1e-6 * (rng / max(cutoff, 1e-9)) ** 2

            if (best is None) or (sse < best[0]):
                best = (sse, float(nugget), float(psill), float(rng))

    if best is None:
        return nugget_seed, max(sill_total_seed - nugget_seed, 1e-6), range_seed

    _, nugget, psill, rng = best
    return nugget, psill, rng


def fit_variogram_mom(x, y, z, *, model="exponential", cutoff=None, lag_width=None) -> VariogramModel:
    """Empirical variogram + MoM coarse-search fit, packaged."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    z = np.asarray(z, dtype=float)
    if cutoff is None or not np.isfinite(float(cutoff)) or float(cutoff) <= 0:
        cutoff = default_cutoff(x, y)
    lags, gamma = empirical_variogram(x, y, z, cutoff, lag_width)
    if lags.size == 0:
        raise ComputationError("Could not compute an experimental variogram (no valid lag bins).")
    token = normalize_model_token(model)
    nugget, psill, range_ = guess_initial_params(lags, gamma, float(cutoff), model=token)
    return VariogramModel(
        model=token,
        nugget=float(nugget),
        psill=float(psill),
        range_=float(range_),
        strategy="mom",
        fit_report={
            "lags": lags,
            "gamma": gamma,
            "cutoff": float(cutoff),
            "lag_width": None if lag_width is None else float(lag_width),
        },
    )


# --------------------------------- REML ------------------------------------
# Mirrors geoR::likfit(..., method="REML") at a high level; moved from the
# legacy kriging_reml.py with scipy access routed through core.deps.

def _design_matrix(coords: np.ndarray, degree: int) -> np.ndarray:
    x = coords[:, 0]
    y = coords[:, 1]
    if degree <= 0:
        return np.ones((coords.shape[0], 1))
    cols = [np.ones_like(x), x, y]
    if degree >= 2:
        cols += [x * x, x * y, y * y]
    return np.vstack(cols).T


def _pairwise_distances(coords: np.ndarray) -> np.ndarray:
    X = coords
    diffs = X[:, None, :] - X[None, :, :]
    return np.sqrt((diffs ** 2).sum(axis=2))


def _rho(h: np.ndarray, model: str, a: float) -> np.ndarray:
    """Correlation function matching geoR parameterization."""
    h = np.asarray(h, dtype=float)
    model = model.lower()
    a = max(float(a), 1e-12)
    if model in ("sph", "spherical"):
        t = np.clip(h / a, 0.0, 1.0)
        r = 1.0 - 1.5 * t + 0.5 * (t ** 3)
        r = np.asarray(r)
        r[h > a] = 0.0
    elif model in ("exp", "exponential"):
        lam = a / 3.0
        r = np.exp(-h / lam)
    elif model in ("gau", "gaussian"):
        lam = a / np.sqrt(3.0)
        r = np.exp(-((h / lam) ** 2))
    else:
        raise ValueError(f"Unsupported model: {model}")
    return r


def _cov_matrix(coords, psill, a, nugget, model, jitter=1e-9) -> np.ndarray:
    d = _pairwise_distances(coords)
    R = _rho(d, model, a)
    C = psill * R
    n = coords.shape[0]
    C[np.arange(n), np.arange(n)] += nugget + jitter
    return C


def _restricted_loglik(theta, coords, y, X, model) -> float:
    log_psill, log_a, log_nugget = theta
    psill, a, nugget = np.exp(log_psill), np.exp(log_a), np.exp(log_nugget)
    C = _cov_matrix(coords, psill, a, nugget, model)
    try:
        L = np.linalg.cholesky(C)
    except np.linalg.LinAlgError:
        return 1e20

    def chol_solve(B):
        v = np.linalg.solve(L, B)
        return np.linalg.solve(L.T, v)

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


def fit_variogram_reml(
    coords,
    values,
    model: str = "Sph",
    init: dict | None = None,
    bounds: dict | None = None,
    trend_degree: int = 0,
    nugget_fixed: float | None = None,
) -> dict:
    """REML fit; returns the legacy dict shape (model/psill/range/nugget/beta/
    reml_value/converged/niter). Raises DependencyMissing without scipy."""
    optimize = import_scipy_optimize()
    minimize = optimize.minimize

    XY = np.asarray(coords, dtype=float)[:, :2]
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

    # Keep REML anchored to the MoM nugget when an initial guess is provided:
    # a nearly-zero lower bound let the optimizer collapse the nugget even when
    # the MoM fit showed a meaningful nugget effect.
    init_psill = max(float(init.get("psill", y_var * 0.7)), y_var * 1e-9)
    init_range = max(float(init.get("range", max_d * 0.6)), max(max_d * 1e-9, 1e-9))
    init_nugget = max(float(init.get("nugget", y_var * 0.3)), 0.0)

    user_bounds = bounds or {}

    nugget_lb_default = y_var * 1e-6
    if init_nugget > 0.0:
        nugget_lb_default = max(nugget_lb_default, min(init_nugget * 0.25, init_nugget))

    psill_bounds = user_bounds.get("psill", default_bounds["psill"])
    range_bounds = user_bounds.get("range", default_bounds["range"])
    nugget_bounds = user_bounds.get("nugget", (nugget_lb_default, default_bounds["nugget"][1]))

    # Sanity clamp user/derived bounds
    psill_bounds = (
        max(psill_bounds[0], y_var * 1e-12),
        max(psill_bounds[1], max(psill_bounds[0] * 1.01, y_var * 1e-11)),
    )
    range_bounds = (max(range_bounds[0], 1e-12), max(range_bounds[1], range_bounds[0] * 1.01))
    nugget_bounds = (
        max(nugget_bounds[0], 0.0),
        max(nugget_bounds[1], max(nugget_bounds[0] * 1.01, 1e-12)),
    )

    # Keep initial values inside the feasible box
    init_psill = min(max(init_psill, psill_bounds[0]), psill_bounds[1])
    init_range = min(max(init_range, range_bounds[0]), range_bounds[1])
    init_nugget = min(max(init_nugget, nugget_bounds[0]), nugget_bounds[1])

    if nugget_fixed is not None:

        def obj_free(theta_free):
            theta = np.array([theta_free[0], theta_free[1], np.log(nugget_fixed)])
            return _restricted_loglik(theta, XY, y, X, model)

        x0 = np.log([init_psill, init_range])
        bnds = [
            (np.log(psill_bounds[0]), np.log(psill_bounds[1])),
            (np.log(range_bounds[0]), np.log(range_bounds[1])),
        ]
        res = minimize(obj_free, x0=x0, method="L-BFGS-B", bounds=bnds)
        ps, a, ng = np.exp(res.x[0]), np.exp(res.x[1]), nugget_fixed
        converged, niter, reml_val = res.success, res.nit, -res.fun
    else:
        x0 = np.log([init_psill, init_range, init_nugget])
        bnds = [
            (np.log(psill_bounds[0]), np.log(psill_bounds[1])),
            (np.log(range_bounds[0]), np.log(range_bounds[1])),
            (np.log(max(nugget_bounds[0], 1e-15)), np.log(nugget_bounds[1])),
        ]
        res = minimize(
            _restricted_loglik, x0=x0, args=(XY, y, X, model), method="L-BFGS-B", bounds=bnds
        )
        ps, a, ng = np.exp(res.x)
        converged, niter, reml_val = res.success, res.nit, -res.fun

    C = _cov_matrix(XY, ps, a, ng, model)
    L = np.linalg.cholesky(C)

    def chol_solve(B):
        v = np.linalg.solve(L, B)
        return np.linalg.solve(L.T, v)

    Ci_X = chol_solve(X)
    XtCiX = X.T @ Ci_X
    beta = np.linalg.inv(XtCiX) @ (X.T @ chol_solve(y))
    return {
        "model": model,
        "psill": ps,
        "range": a,
        "nugget": ng,
        "beta": beta,
        "reml_value": reml_val,
        "converged": converged,
        "niter": niter,
    }


def fit_variogram_reml_model(x, y, z, *, model="exponential", init=None) -> VariogramModel:
    """REML fit packaged as a VariogramModel (γ-parameterization compatible
    with model_gamma / the OK kriging system)."""
    token = normalize_model_token(model)
    coords = np.column_stack([np.asarray(x, dtype=float), np.asarray(y, dtype=float)])
    res = fit_variogram_reml(coords, z, model=token, init=init)
    return VariogramModel(
        model=token,
        nugget=float(res["nugget"]),
        psill=float(res["psill"]),
        range_=float(res["range"]),
        strategy="reml",
        fit_report={
            "reml_value": float(res["reml_value"]),
            "converged": bool(res["converged"]),
            "niter": int(res["niter"]),
        },
    )


# --------------------------- strategy selection -----------------------------

AUTOMATIC_REML_THRESHOLD = 100
MANUAL_REML_LIMIT = 500


class StrategyDecision:
    """Selected kriging variogram-fitting strategy plus the reason string the
    UI surfaces (legacy OKStrategyDecision semantics)."""

    def __init__(self, mode: str, sample_count: int, reason: str):
        self.mode = mode                    # "MoM" | "REML"
        self.sample_count = int(sample_count)
        self.reason = reason

    def __repr__(self):
        return f"StrategyDecision(mode={self.mode!r}, n={self.sample_count}, reason={self.reason!r})"


def reml_available() -> bool:
    try:
        import_scipy_optimize()
        return True
    except Exception:
        return False


def choose_strategy(sample_count: int, requested_mode: str = "Automatic",
                    reml_ok: bool | None = None) -> StrategyDecision:
    """Legacy OKStrategySelector.choose rules, verbatim:
    - explicit MoM -> MoM
    - explicit REML -> REML only if available and n < 500, else MoM + reason
    - Automatic -> REML if available and n < 100, else MoM."""
    n = int(sample_count or 0)
    available = reml_available() if reml_ok is None else bool(reml_ok)
    requested = str(requested_mode or "Automatic").strip().upper()
    if requested == "MOM":
        return StrategyDecision("MoM", n, "User selected MoM")
    if requested == "REML":
        if not available:
            return StrategyDecision(
                "MoM", n, "REML requested but backend is unavailable; using MoM"
            )
        if n >= MANUAL_REML_LIMIT:
            return StrategyDecision(
                "MoM", n, f"REML requested but n >= {MANUAL_REML_LIMIT}; using MoM"
            )
        return StrategyDecision("REML", n, f"User selected REML and n < {MANUAL_REML_LIMIT}")
    if available and n < AUTOMATIC_REML_THRESHOLD:
        return StrategyDecision("REML", n, f"REML available and n < {AUTOMATIC_REML_THRESHOLD}")
    return StrategyDecision(
        "MoM",
        n,
        (
            "Using MoM because REML is unavailable"
            if not available
            else f"Using MoM because n >= {AUTOMATIC_REML_THRESHOLD}"
        ),
    )
