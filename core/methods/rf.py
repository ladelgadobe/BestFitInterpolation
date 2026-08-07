# -*- coding: utf-8 -*-
"""Random Forest interpolation — tuning logic moved from the legacy
RF_Interpolation.py; DataFrames and the float-keyed pd.merge are gone
(features stay positionally aligned numpy end to end)."""

from __future__ import annotations

import numpy as np

from ..deps import import_sklearn
from ..exceptions import InvalidDataError, OperationCancelled
from ..types import FitResult, TrainingData
from .base import InterpolationMethod, MethodInfo

RANDOM_STATE = 20  # legacy seed


def build_features(xy, covariates, use_xy=True):
    """Positional feature matrix: optional (x, y) columns ⊕ covariates."""
    parts = []
    if use_xy:
        parts.append(np.asarray(xy, dtype=float))
    if covariates is not None and np.size(covariates):
        cov = np.asarray(covariates, dtype=float)
        if cov.ndim == 1:
            cov = cov[:, None]
        parts.append(cov)
    if not parts:
        raise InvalidDataError("Select at least one predictor (x/y or covariates).")
    return np.column_stack(parts)


def _build_param_distributions(use_grid_search, manual_params, grid_params, n_features):
    """Hyperparameter search space (legacy verbatim; mtry capped at the
    feature count)."""
    if not use_grid_search:
        ntree = int(manual_params.get("ntree", 500))
        mtry = int(manual_params.get("mtry", max(1, n_features // 3)))
        nodesize = int(manual_params.get("nodesize", 5))
        mtry = max(1, min(mtry, n_features))
        return {
            "n_estimators": [ntree],
            "max_features": [mtry],
            "min_samples_leaf": [nodesize],
        }, False

    def _build_range(d, cap=None):
        vmin = int(d.get("min", 1))
        vmax = int(d.get("max", vmin))
        step = max(1, int(d.get("step", 1)))
        if cap is not None:
            vmax = min(vmax, cap)
        if vmax < vmin:
            vmax = vmin
        return list(range(vmin, vmax + 1, step))

    param_dist = {
        "n_estimators": _build_range(grid_params.get("ntree", {})),
        "max_features": _build_range(grid_params.get("mtry", {}), cap=n_features),
        "min_samples_leaf": _build_range(grid_params.get("nodesize", {})),
    }
    total = (
        len(param_dist["n_estimators"])
        * len(param_dist["max_features"])
        * len(param_dist["min_samples_leaf"])
    )
    return param_dist, total > 1


def tune_random_forest(
    X,
    y,
    *,
    use_grid_search=False,
    manual_params=None,
    grid_params=None,
    random_state=RANDOM_STATE,
    cv_folds=3,
    max_iterations=10,
    progress=None,
    should_stop=None,
):
    """Legacy _tune_random_forest: manual fit or RandomizedSearchCV over
    (ntree, mtry, nodesize) scored by MAE; single-process for QGIS stability."""
    import_sklearn()
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.model_selection import KFold, RandomizedSearchCV

    manual_params = manual_params or {}
    grid_params = grid_params or {}
    n_features = X.shape[1]
    param_dist, is_search = _build_param_distributions(
        use_grid_search, manual_params, grid_params, n_features
    )

    if should_stop is not None and should_stop():
        raise OperationCancelled()

    if not use_grid_search or not is_search:
        if progress is not None:
            progress(30, 100)
        model = RandomForestRegressor(
            n_estimators=param_dist["n_estimators"][0],
            max_features=param_dist["max_features"][0],
            min_samples_leaf=param_dist["min_samples_leaf"][0],
            n_jobs=1,
            random_state=random_state,
        )
        model.fit(X, y)
        if progress is not None:
            progress(100, 100)
        return model, {
            "ntree": int(model.n_estimators),
            "mtry": int(model.max_features),
            "nodesize": int(model.min_samples_leaf),
        }

    base_model = RandomForestRegressor(n_estimators=200, n_jobs=1, random_state=random_state)
    cv_folds = max(2, int(cv_folds))
    cv = KFold(n_splits=cv_folds, shuffle=True, random_state=random_state)
    total_combos = (
        len(param_dist["n_estimators"])
        * len(param_dist["max_features"])
        * len(param_dist["min_samples_leaf"])
    )
    n_iter = min(max(1, int(max_iterations)), total_combos) if total_combos > 0 else 1

    if progress is not None:
        progress(20, 100)
    search = RandomizedSearchCV(
        estimator=base_model,
        param_distributions=param_dist,
        n_iter=n_iter,
        scoring="neg_mean_absolute_error",
        cv=cv,
        n_jobs=1,
        pre_dispatch=1,
        random_state=random_state,
        refit=True,
        verbose=0,
    )
    search.fit(X, y)
    if progress is not None:
        progress(100, 100)
    model = search.best_estimator_
    return model, {
        "ntree": int(model.n_estimators),
        "mtry": int(model.max_features),
        "nodesize": int(model.min_samples_leaf),
    }


class RFModel:
    def __init__(self, estimator, use_xy):
        self.estimator = estimator
        self.use_xy = bool(use_xy)

    @property
    def feature_importances_(self):
        return self.estimator.feature_importances_

    def predict(self, xy, covariates=None, *, progress=None, should_stop=None):
        if should_stop is not None and should_stop():
            raise OperationCancelled()
        X = build_features(xy, covariates, use_xy=self.use_xy)
        out = np.asarray(self.estimator.predict(X), dtype=float)
        if progress is not None:
            progress(len(out), len(out))
        return out


class RandomForestMethod(InterpolationMethod):
    info = MethodInfo(
        key="rf",
        label="Random Forest",
        min_samples=5,
        requires=("scipy", "scikit-learn"),
        supports_covariates=True,
        needs_covariates=False,   # can run on x,y alone (legacy allows it)
    )

    def fit(self, data: TrainingData, params=None, *, progress=None, should_stop=None) -> FitResult:
        self.validate(data)
        params = dict(params or {})
        use_xy = bool(params.get("use_xy", True))
        X = build_features(data.xy, data.covariates, use_xy=use_xy)
        y = np.asarray(data.values, dtype=float)

        estimator, best = tune_random_forest(
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

        feature_names = (("x", "y") if use_xy else ()) + tuple(data.covariate_names)
        importances = np.asarray(estimator.feature_importances_, dtype=float)
        resolved = dict(best)
        resolved["use_xy"] = use_xy
        # Manual params must survive into CV folds without re-search.
        resolved["use_grid_search"] = False
        resolved["manual_params"] = dict(best)
        return FitResult(
            model=RFModel(estimator, use_xy),
            params=resolved,
            diagnostics={
                "importances": dict(zip(feature_names, importances.tolist())),
            },
        )
