# -*- coding: utf-8 -*-
"""Ordinary Kriging — the single implementation replacing the legacy
ok_r_integration_MoM/reml clone stack.

Two variogram-fitting strategies (MoM / REML, chosen by core.variogram.
choose_strategy) feed two prediction backends preserved from the legacy code:

* MoM   -> γ-based system, γ(0)=0 on the diagonal, LU factored once
           (legacy kriging_ordinary.ordinary_kriging_interpolation).
* REML  -> covariance-based GLS predictor with optional kriging variance
           (legacy kriging_reml.ok_predict).
"""

from __future__ import annotations

import numpy as np

from ..deps import import_scipy_linalg, import_scipy_spatial
from ..exceptions import OperationCancelled
from ..types import FitResult, TrainingData, VariogramModel
from ..variogram import (
    _cov_matrix,
    _design_matrix,
    _rho,
    choose_strategy,
    fit_variogram_mom,
    fit_variogram_reml_model,
    model_gamma,
    normalize_model_token,
)
from .base import InterpolationMethod, MethodInfo


# ------------------------- MoM (γ-based) backend ----------------------------

def _variogram_gamma0(h, a, c0, c, model_key):
    """γ(h) with γ(0)=0 — nugget applies only for h>0 (kriging-matrix rule
    from legacy kriging_ordinary._variogram)."""
    core = model_gamma(h, model_key, 0.0, c, a)  # nugget added below for h>0
    h = np.asarray(h)
    out = np.array(core, dtype=float, copy=True)
    if out.ndim == 0:
        return 0.0 if float(h) == 0.0 else (c0 + float(out))
    zero = h == 0.0
    out[~zero] = c0 + out[~zero]
    out[zero] = 0.0
    return out


def _build_system(x, y, nugget, psill, var_range, model_key):
    """Kriging matrix K ((n+1)²), LU-factored once (legacy verbatim)."""
    spatial = import_scipy_spatial()
    linalg = import_scipy_linalg()
    P = np.column_stack([x, y])
    D = spatial.distance.cdist(P, P)
    G = _variogram_gamma0(D, var_range, nugget, psill, model_key).astype(float)
    np.fill_diagonal(G, 0.0)
    np.fill_diagonal(G, G.diagonal() + 1e-12)

    n = x.size
    K = np.zeros((n + 1, n + 1), dtype=float)
    K[:n, :n] = G
    K[:n, n] = 1.0
    K[n, :n] = 1.0

    try:
        lu, piv = linalg.lu_factor(K, check_finite=False)
    except Exception:
        np.fill_diagonal(K, K.diagonal() + 1e-10)
        lu, piv = linalg.lu_factor(K, check_finite=False)
    return lu, piv


class OKModel:
    """Fitted OK predictor. Chunked evaluation with cancellation; the linear
    system is factored once at construction."""

    def __init__(self, data: TrainingData, variogram: VariogramModel):
        self.variogram = variogram
        self._x = np.asarray(data.x, dtype=float)
        self._y = np.asarray(data.y, dtype=float)
        self._z = np.asarray(data.values, dtype=float)
        if variogram.strategy == "reml":
            self._backend = "reml"
            self._lu_piv = None
        else:
            self._backend = "mom"
            self._lu_piv = _build_system(
                self._x, self._y, variogram.nugget, variogram.psill,
                variogram.range_, variogram.model,
            )

    def predict(self, xy, covariates=None, *, progress=None, should_stop=None,
                return_variance=False):
        xy = np.asarray(xy, dtype=float)
        if self._backend == "mom":
            preds = self._predict_mom(xy, progress=progress, should_stop=should_stop)
            return (preds, None) if return_variance else preds
        return self._predict_reml(
            xy, progress=progress, should_stop=should_stop, return_variance=return_variance
        )

    # -- MoM: legacy ordinary_kriging_interpolation chunk loop ---------------
    def _predict_mom(self, xy, *, progress=None, should_stop=None):
        linalg = import_scipy_linalg()
        v = self.variogram
        xp, yp = xy[:, 0], xy[:, 1]
        total = xp.size
        preds = np.empty(total, dtype=float)
        chunk = 5000 if total > 20000 else 2000
        lu, piv = self._lu_piv
        for start in range(0, total, chunk):
            if should_stop is not None and should_stop():
                raise OperationCancelled()
            end = min(total, start + chunk)
            Xblk = xp[start:end]
            Yblk = yp[start:end]
            D0 = np.hypot(self._x[None, :] - Xblk[:, None], self._y[None, :] - Yblk[:, None])
            G0 = _variogram_gamma0(D0, v.range_, v.nugget, v.psill, v.model)
            rhs = np.empty((G0.shape[0], G0.shape[1] + 1), dtype=float)
            rhs[:, :-1] = G0
            rhs[:, -1] = 1.0
            sol = linalg.lu_solve((lu, piv), rhs.T, check_finite=False).T
            preds[start:end] = sol[:, :-1] @ self._z
            if progress is not None:
                progress(end, total)
        return preds

    # -- REML: legacy kriging_reml.ok_predict ---------------------------------
    def _predict_reml(self, xy, *, progress=None, should_stop=None,
                      return_variance=False, trend_degree=0):
        if should_stop is not None and should_stop():
            raise OperationCancelled()
        v = self.variogram
        XY = np.column_stack([self._x, self._y])
        y = self._z
        XP = xy[:, :2]
        model, ps, a, ng = v.model, v.psill, v.range_, v.nugget
        X = _design_matrix(XY, trend_degree)
        Xp = _design_matrix(XP, trend_degree)
        C = _cov_matrix(XY, ps, a, ng, model)
        L = np.linalg.cholesky(C)

        def chol_solve(B):
            s = np.linalg.solve(L, B)
            return np.linalg.solve(L.T, s)

        Ci_y = chol_solve(y)
        Ci_X = chol_solve(X)
        XtCiX = X.T @ Ci_X
        XtCiX_inv = np.linalg.inv(XtCiX)
        beta = XtCiX_inv @ (X.T @ Ci_y)
        d_cross = np.sqrt(((XY[:, None, :] - XP[None, :, :]) ** 2).sum(axis=2))
        K = ps * _rho(d_cross, model, a)
        yc = y - X @ beta
        w = chol_solve(yc)
        pred = Xp @ beta + K.T @ w
        if progress is not None:
            progress(XP.shape[0], XP.shape[0])
        if not return_variance:
            return pred
        Ci_K = chol_solve(K)
        XTCiK = X.T @ Ci_K
        middle = Xp.T - XTCiK
        term_gls = np.einsum("ij,jk,ki->i", middle.T, XtCiX_inv, middle)
        kCik = np.sum(K * Ci_K, axis=0)
        var = ps - kCik + term_gls
        var = np.maximum(var, 0.0)
        return pred, var


def choose_best_model_by_validation(data: TrainingData, *, cutoff=None, lag_width=None,
                                    progress=None, should_stop=None):
    """LOOCV each variogram model (spherical/exponential/gaussian) with its
    MoM fit and rank by R² then RMSE — the legacy automatic-model rule
    (_choose_best_model_by_validation). Returns ranked list of dicts."""
    from ..cv import run_cross_validation
    from ..types import CVPlan

    method = OrdinaryKrigingMethod()
    rows = []
    tokens = ("spherical", "exponential", "gaussian")
    for i, token in enumerate(tokens):
        if should_stop is not None and should_stop():
            raise OperationCancelled()
        try:
            vgm = fit_variogram_mom(
                data.x, data.y, data.values, model=token,
                cutoff=cutoff, lag_width=lag_width,
            )
            params = {
                "strategy": "MoM", "model": token,
                "nugget": vgm.nugget, "psill": vgm.psill, "range": vgm.range_,
            }
            cv = run_cross_validation(
                method, data, params, CVPlan(mode="loocv"), should_stop=should_stop
            )
            rows.append({
                "model_key": token,
                "nugget": vgm.nugget, "psill": vgm.psill, "range": vgm.range_,
                "rmse": cv.metrics.rmse, "rmse_pct": cv.metrics.rmse_pct,
                "mae": cv.metrics.mae, "r2": cv.metrics.r2,
                "pearson": cv.metrics.pearson_r, "lccc": cv.metrics.lccc,
            })
        except OperationCancelled:
            raise
        except Exception as exc:
            rows.append({"model_key": token, "error": str(exc),
                         "rmse": float("nan"), "r2": float("nan")})
        if progress is not None:
            progress(i + 1, len(tokens))

    def _rank_key(r):
        r2 = float(r.get("r2", float("nan")))
        rmse = float(r.get("rmse", float("nan")))
        return (
            -(r2 if np.isfinite(r2) else -1e300),
            rmse if np.isfinite(rmse) else 1e300,
        )

    return sorted(rows, key=_rank_key)


class OrdinaryKrigingMethod(InterpolationMethod):
    info = MethodInfo(
        key="ok",
        label="Ordinary Kriging",
        min_samples=10,
        requires=("scipy",),
        supports_variance=True,
    )

    def fit(self, data: TrainingData, params=None, *, progress=None, should_stop=None) -> FitResult:
        """params:
        - strategy: "Automatic" | "MoM" | "REML" (default Automatic)
        - model: variogram model name/token or "auto"
        - nugget/psill/range: explicit values skip fitting entirely
        - cutoff/lag_width: empirical variogram controls (MoM)
        """
        self.validate(data)
        params = dict(params or {})
        model = params.get("model", "exponential")
        token = normalize_model_token(model)

        explicit = all(k in params for k in ("nugget", "psill", "range"))
        if explicit:
            strategy = str(params.get("strategy", "MoM"))
            vgm = VariogramModel(
                model=token,
                nugget=float(params["nugget"]),
                psill=float(params["psill"]),
                range_=float(params["range"]),
                strategy="reml" if strategy.strip().upper() == "REML" else "mom",
                fit_report={"source": "user"},
            )
            decision_reason = "User-provided variogram parameters"
        else:
            decision = choose_strategy(data.n, params.get("strategy", "Automatic"))
            decision_reason = decision.reason
            if decision.mode == "REML":
                # Legacy flow: seed REML with the MoM fit so the nugget stays
                # anchored (see kriging_reml bounds logic).
                try:
                    mom = fit_variogram_mom(
                        data.x, data.y, data.values, model=token,
                        cutoff=params.get("cutoff"), lag_width=params.get("lag_width"),
                    )
                    init = {"nugget": mom.nugget, "psill": mom.psill, "range": mom.range_}
                except Exception:
                    init = None
                vgm = fit_variogram_reml_model(
                    data.x, data.y, data.values, model=token, init=init
                )
            else:
                vgm = fit_variogram_mom(
                    data.x, data.y, data.values, model=token,
                    cutoff=params.get("cutoff"), lag_width=params.get("lag_width"),
                )
        if should_stop is not None and should_stop():
            raise OperationCancelled()

        model_obj = OKModel(data, vgm)
        resolved = {
            "strategy": vgm.strategy,
            "model": vgm.model,
            "nugget": vgm.nugget,
            "psill": vgm.psill,
            "range": vgm.range_,
        }
        return FitResult(
            model=model_obj,
            params=resolved,
            diagnostics={"variogram": vgm, "strategy_reason": decision_reason},
        )
