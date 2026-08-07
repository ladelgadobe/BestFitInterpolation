# -*- coding: utf-8 -*-
"""Regression Kriging: Random Forest trend + Ordinary Kriging of the RF
residuals (legacy RF_RegressionKriging compute path: tune RF -> residuals ->
MoM residual variogram -> γ-based OK on residuals -> trend + kriged residual)."""

from __future__ import annotations

import numpy as np

from ..exceptions import OperationCancelled
from ..types import FitResult, TrainingData, VariogramModel
from ..variogram import fit_variogram_mom, normalize_model_token
from .base import InterpolationMethod, MethodInfo
from .kriging_ok import OKModel
from .rf import RANDOM_STATE, RFModel, build_features, tune_random_forest


class RKModel:
    def __init__(self, rf_model: RFModel, residual_ok: OKModel):
        self.rf_model = rf_model
        self.residual_ok = residual_ok

    def predict(self, xy, covariates=None, *, progress=None, should_stop=None):
        trend = self.rf_model.predict(
            xy, covariates=covariates, should_stop=should_stop
        )
        residual = self.residual_ok.predict(
            np.asarray(xy, dtype=float), progress=progress, should_stop=should_stop
        )
        return trend + np.asarray(residual, dtype=float)


class RegressionKrigingMethod(InterpolationMethod):
    info = MethodInfo(
        key="rk",
        label="Regression Kriging (RF)",
        min_samples=10,
        requires=("scipy", "scikit-learn"),
        supports_covariates=True,
        needs_covariates=False,
    )

    def fit(self, data: TrainingData, params=None, *, progress=None, should_stop=None) -> FitResult:
        self.validate(data)
        params = dict(params or {})
        use_xy = bool(params.get("use_xy", True))
        X = build_features(data.xy, data.covariates, use_xy=use_xy)
        y = np.asarray(data.values, dtype=float)

        # 1. RF trend
        estimator, best_rf = tune_random_forest(
            X,
            y,
            use_grid_search=bool(params.get("use_grid_search", False)),
            manual_params=params.get("manual_params") or {
                k: params[k] for k in ("ntree", "mtry", "nodesize") if k in params
            },
            grid_params=params.get("grid_params") or {},
            random_state=int(params.get("random_state", RANDOM_STATE)),
            cv_folds=int(params.get("cv_folds", 3)),
            max_iterations=int(params.get("max_iterations", 10)),
            progress=progress,
            should_stop=should_stop,
        )
        rf_model = RFModel(estimator, use_xy)
        residuals = y - np.asarray(estimator.predict(X), dtype=float)

        if should_stop is not None and should_stop():
            raise OperationCancelled()

        # 2. Residual variogram (MoM) — explicit params skip fitting
        token = normalize_model_token(params.get("model", "exponential"))
        if all(k in params for k in ("nugget", "psill", "range")):
            vgm = VariogramModel(
                model=token,
                nugget=float(params["nugget"]),
                psill=float(params["psill"]),
                range_=float(params["range"]),
                strategy="mom",
                fit_report={"source": "user"},
            )
        else:
            vgm = fit_variogram_mom(
                data.x, data.y, residuals, model=token,
                cutoff=params.get("cutoff"), lag_width=params.get("lag_width"),
            )

        # 3. OK on the residuals (γ-based MoM backend)
        residual_data = TrainingData(xy=data.xy, values=residuals)
        residual_ok = OKModel(residual_data, vgm)

        resolved = dict(best_rf)
        resolved.update(
            use_xy=use_xy,
            use_grid_search=False,
            manual_params=dict(best_rf),
            model=vgm.model,
            nugget=vgm.nugget,
            psill=vgm.psill,
            range=vgm.range_,
        )
        feature_names = (("x", "y") if use_xy else ()) + tuple(data.covariate_names)
        importances = np.asarray(estimator.feature_importances_, dtype=float)
        return FitResult(
            model=RKModel(rf_model, residual_ok),
            params=resolved,
            diagnostics={
                "variogram": vgm,
                "residuals": residuals,
                "importances": dict(zip(feature_names, importances.tolist())),
            },
        )
