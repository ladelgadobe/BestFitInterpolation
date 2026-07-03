# -*- coding: utf-8 -*-
"""
RF_Interpolation.py

Random Forest interpolation helpers for the BestFitInterpolator plugin.

This module replicates the logic of the original R workflow:

- Random search / grid search over (ntree, mtry, nodesize) using MAE.
- Train final RandomForest model with best hyperparameters.
- Predict over an interpolation grid using coordinates + covariates.
- Compute variable importance.

The actual loading of points, polygon, grid and covariate rasters is handled
by the plugin. Here we only work with in-memory tables (pandas DataFrames or
NumPy arrays).

All comments are in English. No user-facing GUI code here.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def _build_param_distributions(
    use_grid_search: bool,
    manual_params: Dict[str, int],
    grid_params: Dict[str, Dict[str, int]],
    n_covariates: int,
) -> Tuple[Dict[str, List[int]], bool]:
    """
    Build the hyperparameter search space.
    """
    if not use_grid_search:
        ntree = int(manual_params.get("ntree", 500))
        mtry = int(manual_params.get("mtry", max(1, n_covariates // 3)))
        nodesize = int(manual_params.get("nodesize", 5))

        mtry = max(1, min(mtry, n_covariates))
        param_dist = {
            "n_estimators": [ntree],
            "max_features": [mtry],
            "min_samples_leaf": [nodesize],
        }
        return param_dist, False

    param_dist: Dict[str, List[int]] = {}

    def _build_range(d: Dict[str, int], cap: Optional[int] = None) -> List[int]:
        """Helper to build an integer range [min, max] with given step."""
        vmin = int(d.get("min", 1))
        vmax = int(d.get("max", vmin))
        step = max(1, int(d.get("step", 1)))
        if cap is not None:
            vmax = min(vmax, cap)
        if vmax < vmin:
            vmax = vmin
        return list(range(vmin, vmax + 1, step))

    ntree_cfg = grid_params.get("ntree", {})
    mtry_cfg = grid_params.get("mtry", {})
    nodesize_cfg = grid_params.get("nodesize", {})

    ntree_range = _build_range(ntree_cfg)
    mtry_range = _build_range(mtry_cfg, cap=n_covariates)
    nodesize_range = _build_range(nodesize_cfg)

    param_dist["n_estimators"] = ntree_range
    param_dist["max_features"] = mtry_range
    param_dist["min_samples_leaf"] = nodesize_range

    total_combos = (
        len(ntree_range) * len(mtry_range) * len(nodesize_range)
    )

    return param_dist, total_combos > 1


def _tune_random_forest(
    X: np.ndarray,
    y: np.ndarray,
    use_grid_search: bool,
    manual_params: Dict[str, int],
    grid_params: Dict[str, Dict[str, int]],
    n_jobs: int = 1,
    random_state: int = 20,
    cv_folds: int = 3,
    max_iterations: int = 10,
    progress_fn: Optional[Callable[[int, int, Optional[str]], None]] = None,
) -> Tuple[Any, Dict[str, int]]:
    """
    Train a RandomForestRegressor with optional hyperparameter tuning.

    Notes
    -----
    - Single-process execution is forced for stability inside QGIS on Windows.
    - Cross-validation folds and max iterations are only used when search mode is enabled.
    """
    try:
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.model_selection import KFold, RandomizedSearchCV
    except Exception as e:
        raise ImportError(
            "Random Forest requires scikit-learn, but it could not be imported."
        ) from e

    if progress_fn is not None:
        progress_fn(0, 100, "Preparing Random Forest hyperparameter search…")

    n_covariates = X.shape[1]

    param_dist, is_search = _build_param_distributions(
        use_grid_search, manual_params, grid_params, n_covariates
    )

    if not use_grid_search or not is_search:
        if progress_fn is not None:
            progress_fn(30, 100, "Training Random Forest with manual parameters…")

        best_model = RandomForestRegressor(
            n_estimators=param_dist["n_estimators"][0],
            max_features=param_dist["max_features"][0],
            min_samples_leaf=param_dist["min_samples_leaf"][0],
            n_jobs=1,
            random_state=random_state,
        )
        best_model.fit(X, y)

        if progress_fn is not None:
            progress_fn(100, 100, "Random Forest training completed.")

        best_params = {
            "ntree": int(best_model.n_estimators),
            "mtry": int(best_model.max_features),
            "nodesize": int(best_model.min_samples_leaf),
        }
        return best_model, best_params

    base_model = RandomForestRegressor(
        n_estimators=200,
        n_jobs=1,
        random_state=random_state,
    )

    cv_folds = max(2, int(cv_folds))
    cv = KFold(n_splits=cv_folds, shuffle=True, random_state=random_state)

    total_combos = (
        len(param_dist["n_estimators"])
        * len(param_dist["max_features"])
        * len(param_dist["min_samples_leaf"])
    )
    max_iterations = max(1, int(max_iterations))
    n_iter = min(max_iterations, total_combos) if total_combos > 0 else 1

    if progress_fn is not None:
        progress_fn(
            20,
            100,
            f"Running Random Search ({n_iter} iterations, {cv_folds}-fold CV)…",
        )

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

    if progress_fn is not None:
        progress_fn(90, 100, "Finalizing Random Forest model…")

    best_model = search.best_estimator_
    best_params = {
        "ntree": int(best_model.n_estimators),
        "mtry": int(best_model.max_features),
        "nodesize": int(best_model.min_samples_leaf),
    }

    if progress_fn is not None:
        progress_fn(100, 100, "Random Forest search completed.")

    return best_model, best_params


def rf_interpolation(
    points_df: pd.DataFrame,
    grid_df: pd.DataFrame,
    target_column: str,
    covariate_columns: List[str],
    use_grid_search: bool,
    manual_params: Dict[str, int],
    grid_params: Dict[str, Dict[str, int]],
    x_col: str = "x",
    y_col: str = "y",
    n_jobs: int = 1,
    random_state: int = 20,
    cv_folds: int = 3,
    max_iterations: int = 10,
    progress_fn: Optional[Callable[[int, int, Optional[str]], None]] = None,
) -> Dict[str, object]:
    """
    Main RF interpolation function used by the plugin.
    """
    try:
        from sklearn.metrics import mean_absolute_error
    except Exception as e:
        raise ImportError(
            "Random Forest requires scikit-learn, but it could not be imported."
        ) from e

    # Force single-process execution for stability inside QGIS on Windows.
    n_jobs = 1

    if progress_fn is not None:
        progress_fn(0, 100, "Preparing Random Forest training data…")

    feature_columns = list(dict.fromkeys(covariate_columns))
    if not feature_columns:
        raise ValueError("Select at least one predictor for Random Forest interpolation.")

    cols_needed = list(dict.fromkeys([x_col, y_col] + feature_columns + [target_column]))
    train_df = points_df[cols_needed].dropna().copy()

    if train_df.empty:
        raise ValueError("No valid training rows after dropping NA in predictors/target.")

    X = train_df[feature_columns].to_numpy(dtype=float)
    y = train_df[target_column].to_numpy(dtype=float)

    model, best_params = _tune_random_forest(
        X=X,
        y=y,
        use_grid_search=use_grid_search,
        manual_params=manual_params,
        grid_params=grid_params,
        n_jobs=n_jobs,
        random_state=random_state,
        cv_folds=cv_folds,
        max_iterations=max_iterations,
        progress_fn=progress_fn,
    )

    if progress_fn is not None:
        progress_fn(92, 100, "Computing training metrics…")

    y_pred_train = model.predict(X)
    train_mae = float(mean_absolute_error(y, y_pred_train))
    train_rmse = float(np.sqrt(np.mean((y - y_pred_train) ** 2)))

    grid_cols = list(dict.fromkeys([x_col, y_col] + feature_columns))
    grid_clean = grid_df[grid_cols].dropna().copy()

    if grid_clean.empty:
        raise ValueError("No valid grid rows after dropping NA in predictors.")

    X_grid = grid_clean[feature_columns].to_numpy(dtype=float)

    if progress_fn is not None:
        progress_fn(96, 100, "Predicting Random Forest values on the interpolation grid…")

    grid_pred = model.predict(X_grid)
    grid_clean[target_column + "_pred"] = grid_pred

    merged = grid_df.copy()
    merged = pd.merge(
        merged,
        grid_clean[[x_col, y_col, target_column + "_pred"]],
        on=[x_col, y_col],
        how="left",
    )

    feature_names = feature_columns
    importances = model.feature_importances_

    importance_df = pd.DataFrame(
        {
            "Variable": feature_names,
            "Importance": importances.astype(float),
        }
    ).sort_values("Importance", ascending=False).reset_index(drop=True)

    if progress_fn is not None:
        progress_fn(100, 100, "Random Forest interpolation completed.")

    result = {
        "model": model,
        "best_params": best_params,
        "grid_with_pred": merged,
        "importance_df": importance_df,
        "train_mae": train_mae,
        "train_rmse": train_rmse,
    }

    return result
