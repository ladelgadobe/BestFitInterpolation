# -*- coding: utf-8 -*-
"""
SVM_Interpolation.py

Support Vector Machine interpolation helpers for the BestFitInterpolator plugin.
All code comments are in English. User-facing messages are handled by the caller.
"""

from itertools import product
import math
import random

import numpy as np
import pandas as pd

from sklearn.base import clone
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import KFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR


def _safe_progress(progress_fn, done, total, label=None):
    """Call the optional progress callback safely."""
    if progress_fn is None:
        return
    try:
        progress_fn(done, total, label)
    except TypeError:
        progress_fn(done, total)


def _float_seq(min_value, max_value, step_value, *, log2=False, include_zero=False):
    """Create a numeric sequence for parameter search."""
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
        if log2:
            values.append(float(2.0 ** current))
        else:
            values.append(float(current))
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
    """Build discrete SVM parameter grids from the UI ranges."""
    c_values = _float_seq(
        grid_params["C"]["min"],
        grid_params["C"]["max"],
        grid_params["C"]["step"],
        log2=True,
    )
    gamma_values = _float_seq(
        grid_params["gamma"]["min"],
        grid_params["gamma"]["max"],
        grid_params["gamma"]["step"],
        log2=True,
    )
    epsilon_values = _float_seq(
        grid_params["epsilon"]["min"],
        grid_params["epsilon"]["max"],
        grid_params["epsilon"]["step"],
        log2=False,
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
    """Create a scaler + SVR pipeline with radial kernel."""
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


def _cv_rmse_for_params(X, y, params, cv_folds=3, random_state=20):
    """Evaluate one SVM parameter combination with K-fold CV."""
    n = len(y)
    if n < 3:
        model = _make_pipeline(params)
        model.fit(X, y)
        pred = model.predict(X)
        rmse = float(math.sqrt(mean_squared_error(y, pred)))
        return rmse

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



def _prepare_feature_matrices(points_df, grid_df, target_column, covariate_columns, x_col="x", y_col="y"):
    """Build training and prediction matrices from point and grid DataFrames."""
    feature_columns = list(dict.fromkeys(covariate_columns))
    if not feature_columns:
        raise ValueError("Select at least one predictor for SVM interpolation.")
    train_columns = list(dict.fromkeys([x_col, y_col, target_column] + feature_columns))
    predict_columns = list(dict.fromkeys([x_col, y_col] + feature_columns))

    train_df = points_df[train_columns].copy()
    train_df = train_df.replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)

    pred_df = grid_df[predict_columns].copy()
    pred_df = pred_df.replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)

    if train_df.empty:
        raise ValueError("No valid training rows are available for SVM interpolation.")
    if pred_df.empty:
        raise ValueError("No valid grid rows are available for SVM interpolation.")

    X_train = train_df[feature_columns].to_numpy(dtype=float)
    y_train = train_df[target_column].to_numpy(dtype=float)
    X_pred = pred_df[feature_columns].to_numpy(dtype=float)

    return train_df, pred_df, X_train, y_train, X_pred



def _sample_param_candidates(all_candidates, max_iterations=12, random_state=20):
    """Reduce the number of evaluated parameter combinations to keep QGIS responsive."""
    if not all_candidates:
        return [{"C": 1.0, "gamma": 0.1, "epsilon": 0.1}]

    max_iterations = max(1, int(max_iterations))
    if len(all_candidates) <= max_iterations:
        return list(all_candidates)

    rng = random.Random(int(random_state))
    sampled = list(all_candidates)
    rng.shuffle(sampled)
    return sampled[:max_iterations]



def _tune_svm(
    X,
    y,
    *,
    use_grid_search=True,
    manual_params=None,
    grid_params=None,
    cv_folds=3,
    max_iterations=12,
    random_state=20,
    progress_fn=None,
):
    """Tune SVM hyperparameters and return the fitted model and best parameters."""
    if not use_grid_search:
        params = {
            "C": float(manual_params.get("C", 1.0)),
            "gamma": float(manual_params.get("gamma", 0.1)),
            "epsilon": float(manual_params.get("epsilon", 0.1)),
        }
        _safe_progress(progress_fn, 1, 1, "Fitting manual SVM model…")
        model = _make_pipeline(params)
        model.fit(X, y)
        return model, params

    all_candidates = _build_param_grid(grid_params or {})
    candidates = _sample_param_candidates(
        all_candidates,
        max_iterations=max_iterations,
        random_state=random_state,
    )

    best_params = None
    best_rmse = float("inf")

    total = len(candidates)
    for idx, params in enumerate(candidates, start=1):
        _safe_progress(progress_fn, idx - 1, total, f"SVM tuning {idx}/{total}…")
        rmse = _cv_rmse_for_params(
            X,
            y,
            params,
            cv_folds=cv_folds,
            random_state=random_state,
        )
        if rmse < best_rmse:
            best_rmse = rmse
            best_params = dict(params)

    if best_params is None:
        best_params = {"C": 1.0, "gamma": 0.1, "epsilon": 0.1}

    _safe_progress(progress_fn, total, total, "Fitting best SVM model…")
    model = _make_pipeline(best_params)
    model.fit(X, y)
    return model, best_params



def svm_interpolation(
    *,
    points_df,
    grid_df,
    target_column,
    covariate_columns,
    use_grid_search=True,
    manual_params=None,
    grid_params=None,
    x_col="x",
    y_col="y",
    cv_folds=3,
    max_iterations=12,
    random_state=20,
    n_jobs=1,
    progress_fn=None,
):
    """
    Fit an SVM interpolation model and predict over the interpolation grid.

    Parameters
    ----------
    points_df : pandas.DataFrame
        Training data with x, y, target column, and covariates.
    grid_df : pandas.DataFrame
        Prediction grid with x, y, and covariates.
    target_column : str
        Target variable name.
    covariate_columns : list[str]
        Covariate names.
    use_grid_search : bool, default True
        Whether to optimize hyperparameters.
    manual_params : dict, optional
        Manual values for C, gamma, and epsilon.
    grid_params : dict, optional
        Search ranges for C, gamma, and epsilon.
    x_col, y_col : str
        Coordinate column names.
    cv_folds : int, default 3
        Number of folds used during tuning.
    max_iterations : int, default 12
        Maximum number of parameter combinations evaluated.
    random_state : int, default 20
        Seed used for reproducibility.
    n_jobs : int, default 1
        Kept for interface compatibility. The implementation runs on one core.
    progress_fn : callable, optional
        Callback used by the plugin to keep the UI responsive.
    """
    del n_jobs

    train_df, pred_df, X_train, y_train, X_pred = _prepare_feature_matrices(
        points_df,
        grid_df,
        target_column,
        covariate_columns,
        x_col=x_col,
        y_col=y_col,
    )

    model, best_params = _tune_svm(
        X_train,
        y_train,
        use_grid_search=use_grid_search,
        manual_params=manual_params or {},
        grid_params=grid_params or {},
        cv_folds=cv_folds,
        max_iterations=max_iterations,
        random_state=random_state,
        progress_fn=progress_fn,
    )

    _safe_progress(progress_fn, 0, 0, "Predicting SVM interpolation grid…")
    pred_train = model.predict(X_train)
    pred_grid = model.predict(X_pred)

    train_mae = float(mean_absolute_error(y_train, pred_train))
    train_rmse = float(math.sqrt(mean_squared_error(y_train, pred_train)))

    grid_with_pred = pred_df.copy()
    grid_with_pred[f"{target_column}_pred"] = np.asarray(pred_grid, dtype=float)

    return {
        "model": model,
        "best_params": best_params,
        "train_mae": train_mae,
        "train_rmse": train_rmse,
        "grid_with_pred": grid_with_pred,
        "train_df": train_df,
    }
