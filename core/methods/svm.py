# -*- coding: utf-8 -*-
"""Support Vector Machine interpolation — tuning logic moved from the legacy
SVM_Interpolation.py. sklearn imports are lazy (the legacy module imported
sklearn at module top level, which broke plugin load without it)."""

from __future__ import annotations

import math
import random
from itertools import product

import numpy as np

from ..deps import import_sklearn
from ..exceptions import OperationCancelled
from ..types import FitResult, TrainingData
from .base import InterpolationMethod, MethodInfo
from .rf import build_features

RANDOM_STATE = 20  # legacy seed


def _float_seq(min_value, max_value, step_value, *, log2=False, include_zero=False):
    """Numeric sequence for parameter search (legacy verbatim)."""
    min_value = float(min_value)
    max_value = float(max_value)
    step_value = float(step_value)

    if step_value <= 0:
        step_value = 1.0
    if max_value < min_value:
        max_value = min_value

    values = []
    current = min_value
    guard = 0
    while current <= max_value + 1e-12 and guard < 10000:
        values.append(float(2.0 ** current) if log2 else float(current))
        current += step_value
        guard += 1

    if include_zero and 0.0 not in values:
        values = [0.0] + values

    cleaned = []
    seen = set()
    for val in values:
        if not np.isfinite(val):
            continue
        key = round(float(val), 12)
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(float(val))
    return cleaned


def _build_param_grid(grid_params):
    c_values = _float_seq(
        grid_params["C"]["min"], grid_params["C"]["max"], grid_params["C"]["step"], log2=True
    )
    gamma_values = _float_seq(
        grid_params["gamma"]["min"], grid_params["gamma"]["max"], grid_params["gamma"]["step"],
        log2=True,
    )
    epsilon_values = _float_seq(
        grid_params["epsilon"]["min"], grid_params["epsilon"]["max"],
        grid_params["epsilon"]["step"], log2=False,
        include_zero=(float(grid_params["epsilon"]["min"]) <= 0.0),
    )

    if not c_values:
        c_values = [1.0]
    if not gamma_values:
        gamma_values = [0.1]
    if not epsilon_values:
        epsilon_values = [0.1]

    return [
        {"C": float(c), "gamma": float(g), "epsilon": float(e)}
        for c, g, e in product(c_values, gamma_values, epsilon_values)
    ]


def _make_pipeline(params):
    """Scaler + radial-kernel SVR pipeline (legacy verbatim)."""
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVR

    return Pipeline(
        steps=[
            ("scaler", StandardScaler()),
            (
                "svr",
                SVR(
                    kernel="rbf",
                    C=float(params["C"]),
                    gamma=float(params["gamma"]),
                    epsilon=float(params["epsilon"]),
                ),
            ),
        ]
    )


def _cv_rmse_for_params(X, y, params, cv_folds=3, random_state=RANDOM_STATE):
    from sklearn.metrics import mean_squared_error
    from sklearn.model_selection import KFold

    n = len(y)
    if n < 3:
        model = _make_pipeline(params)
        model.fit(X, y)
        pred = model.predict(X)
        return float(math.sqrt(mean_squared_error(y, pred)))

    folds = max(2, min(int(cv_folds), n))
    splitter = KFold(n_splits=folds, shuffle=True, random_state=random_state)

    rmses = []
    for train_idx, test_idx in splitter.split(X):
        model = _make_pipeline(params)
        model.fit(X[train_idx], y[train_idx])
        pred = model.predict(X[test_idx])
        rmse = float(math.sqrt(mean_squared_error(y[test_idx], pred)))
        if np.isfinite(rmse):
            rmses.append(rmse)

    if not rmses:
        return float("inf")
    return float(np.mean(rmses))


def _sample_param_candidates(all_candidates, max_iterations=12, random_state=RANDOM_STATE):
    """Cap the evaluated combinations (legacy verbatim)."""
    if not all_candidates:
        return [{"C": 1.0, "gamma": 0.1, "epsilon": 0.1}]

    max_iterations = max(1, int(max_iterations))
    if len(all_candidates) <= max_iterations:
        return list(all_candidates)

    rng = random.Random(int(random_state))  # nosec B311
    sampled = list(all_candidates)
    rng.shuffle(sampled)
    return sampled[:max_iterations]


def tune_svm(
    X,
    y,
    *,
    use_grid_search=True,
    manual_params=None,
    grid_params=None,
    cv_folds=3,
    max_iterations=12,
    random_state=RANDOM_STATE,
    progress=None,
    should_stop=None,
):
    import_sklearn()

    if not use_grid_search:
        params = {
            "C": float((manual_params or {}).get("C", 1.0)),
            "gamma": float((manual_params or {}).get("gamma", 0.1)),
            "epsilon": float((manual_params or {}).get("epsilon", 0.1)),
        }
        model = _make_pipeline(params)
        model.fit(X, y)
        return model, params

    all_candidates = _build_param_grid(grid_params or {})
    candidates = _sample_param_candidates(
        all_candidates, max_iterations=max_iterations, random_state=random_state
    )

    best_params = None
    best_rmse = float("inf")
    total = len(candidates)
    for idx, params in enumerate(candidates, start=1):
        if should_stop is not None and should_stop():
            raise OperationCancelled()
        rmse = _cv_rmse_for_params(X, y, params, cv_folds=cv_folds, random_state=random_state)
        if rmse < best_rmse:
            best_rmse = rmse
            best_params = dict(params)
        if progress is not None:
            progress(idx, total)

    if best_params is None:
        best_params = {"C": 1.0, "gamma": 0.1, "epsilon": 0.1}

    model = _make_pipeline(best_params)
    model.fit(X, y)
    return model, best_params


class SVMModel:
    def __init__(self, pipeline, use_xy):
        self.pipeline = pipeline
        self.use_xy = bool(use_xy)

    def predict(self, xy, covariates=None, *, progress=None, should_stop=None):
        if should_stop is not None and should_stop():
            raise OperationCancelled()
        X = build_features(xy, covariates, use_xy=self.use_xy)
        out = np.asarray(self.pipeline.predict(X), dtype=float)
        if progress is not None:
            progress(len(out), len(out))
        return out


class SVMMethod(InterpolationMethod):
    info = MethodInfo(
        key="svm",
        label="Support Vector Machine",
        min_samples=5,
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

        default_grid = params.get("grid_params") or {}
        model, best = tune_svm(
            X,
            y,
            use_grid_search=bool(params.get("use_grid_search", False)),
            manual_params=params.get("manual_params") or {
                k: params[k] for k in ("C", "gamma", "epsilon") if k in params
            },
            grid_params=default_grid,
            cv_folds=int(params.get("cv_folds", 3)),
            max_iterations=int(params.get("max_iterations", 12)),
            random_state=int(params.get("random_state", RANDOM_STATE)),
            progress=progress,
            should_stop=should_stop,
        )

        resolved = dict(best)
        resolved["use_xy"] = use_xy
        resolved["use_grid_search"] = False
        resolved["manual_params"] = dict(best)
        return FitResult(model=SVMModel(model, use_xy), params=resolved)
