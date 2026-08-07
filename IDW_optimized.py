# -*- coding: utf-8 -*-
"""
IDW_optimized.py
Deterministic IDW interpolation and parameter optimization WITHOUT sklearn/scipy.

- Same public API as your original:
  * idw_interpolation(x, y, z, xi, yi, p, n) -> zi
  * optimize_idw(x, y, z, k=5) -> best_p, best_n, best_isi, final_results
    where final_results = [(p, n, mae, sae, isi), ...]
- ISI computed from normalized MAE and SAE, matching your logic.

All code comments are in English. User-facing strings in English.
"""

import numpy as np

try:
    from .array_shape_utils import (
        ensure_xy_components,
        ensure_values_1d,
    )
except Exception:  # pragma: no cover
    from array_shape_utils import (  # type: ignore
        ensure_xy_components,
        ensure_values_1d,
    )


# ----------------------------- Basic metrics ----------------------------------

def mean_absolute_error(ypred, yobs):
    """MAE."""
    ypred = np.asarray(ypred, dtype=float).ravel()
    yobs  = np.asarray(yobs,  dtype=float).ravel()
    return float(np.mean(np.abs(ypred - yobs)))


def std_error(ypred, yobs):
    """Standard deviation of errors."""
    ypred = np.asarray(ypred, dtype=float).ravel()
    yobs  = np.asarray(yobs,  dtype=float).ravel()
    return float(np.std(ypred - yobs))


def calculate_isi(mae, sae, max_abs_ae, min_sae, max_sae):
    """
    ISI = normalized_mae + normalized_sae
    - normalized_mae = mae / max_abs_ae
    - normalized_sae = (sae - min_sae) / (max_sae - min_sae)
    """
    if max_abs_ae <= 0:  # avoid division by zero
        normalized_mae = 0.0
    else:
        normalized_mae = mae / max_abs_ae

    if max_sae == min_sae:
        normalized_sae = 0.0
    else:
        normalized_sae = (sae - min_sae) / (max_sae - min_sae)

    return float(normalized_mae + normalized_sae)


# ------------------------------- IDW core -------------------------------------

def _pairwise_dist(x, y, xi, yi):
    """
    Euclidean distance between support points (x,y) and query points (xi,yi).
    Returns (M, N) matrix where M=len(xi), N=len(x)
    """
    train_xy = ensure_xy_components(x, y, "training coordinates")
    query_xy = ensure_xy_components(xi, yi, "prediction coordinates")
    x = train_xy[:, 0]
    y = train_xy[:, 1]
    xi = query_xy[:, 0]
    yi = query_xy[:, 1]

    # (M,1) and (1,N) broadcasting
    dx = xi[:, None] - x[None, :]
    dy = yi[:, None] - y[None, :]
    return np.sqrt(dx*dx + dy*dy)


def idw_interpolation(x, y, z, xi, yi, p, n):
    """
    IDW interpolation at query coordinates (xi, yi) based on (x, y, z).

    Parameters
    ----------
    x, y : arrays of shape (N,)
    z    : array  of shape (N,)
    xi, yi : arrays of shape (M,)
    p : float  - power
    n : int    - number of neighbors

    Returns
    -------
    zi : array of shape (M,)
    """
    train_xy = ensure_xy_components(x, y, "training coordinates")
    query_xy = ensure_xy_components(xi, yi, "prediction coordinates")
    z = ensure_values_1d(z, "training values")
    x = train_xy[:, 0]
    y = train_xy[:, 1]
    xi = query_xy[:, 0]
    yi = query_xy[:, 1]

    if x.size != y.size or x.size != z.size:
        raise ValueError("x, y, z must have the same length.")
    if xi.size != yi.size:
        raise ValueError("xi and yi must have the same length.")
    if x.size == 0 or xi.size == 0:
        return np.array([], dtype=float)

    # Distances (M, N)
    dist = _pairwise_dist(x, y, xi, yi)

    # Exact hits → return exact z (avoid zero division and unstable weights)
    zero_hit = dist == 0.0
    zi = np.full(xi.shape[0], np.nan, dtype=float)
    has_zero = np.any(zero_hit, axis=1)
    if np.any(has_zero):
        # pick the first zero-distance neighbor's z
        first_zero_idx = np.argmax(zero_hit[has_zero, :], axis=1)
        zi[has_zero] = z[first_zero_idx]

    # For non-exact queries, do weighted average over n nearest neighbors
    need = ~has_zero
    if np.any(need):
        dist_need = dist[need, :]                               # (m_need, N)
        # select n nearest neighbors (argpartition is faster than full sort)
        n_eff = int(max(1, min(int(n), dist_need.shape[1])))
        idx_knn = np.argpartition(dist_need, kth=n_eff-1, axis=1)[:, :n_eff]  # (m_need, n)
        row = np.arange(idx_knn.shape[0])[:, None]

        d_knn = dist_need[row, idx_knn]
        # avoid zero (we already handled exact hits above)
        d_knn[d_knn == 0.0] = 1e-12

        w = 1.0 / np.power(d_knn, float(p))                    # weights
        w_sum = np.sum(w, axis=1, keepdims=True)
        w_sum[w_sum == 0.0] = 1e-12
        w /= w_sum

        z_knn = z[idx_knn]
        zi[need] = np.sum(w * z_knn, axis=1)

    return zi


# ------------------------------ KFold (light) ---------------------------------

def _kfold_indices(n_samples, n_splits=5, shuffle=True, random_state=42):
    """
    Lightweight replacement for sklearn.model_selection.KFold.
    Yields (train_idx, test_idx) for each fold.
    """
    n_splits = int(max(2, min(n_splits, n_samples)))
    idx = np.arange(n_samples)
    if shuffle:
        rng = np.random.default_rng(int(random_state))
        rng.shuffle(idx)

    fold_sizes = np.full(n_splits, n_samples // n_splits, dtype=int)
    fold_sizes[: n_samples % n_splits] += 1

    current = 0
    for fold_size in fold_sizes:
        start, stop = current, current + fold_size
        test_idx = idx[start:stop]
        train_idx = np.concatenate([idx[:start], idx[stop:]])
        current = stop
        yield train_idx, test_idx


# ----------------------------- Parameter search --------------------------------

def optimize_idw(x, y, z, k=5):
    """
    Grid-search for (p, n) using K-fold CV (MAE & SAE) and ISI selection.

    Parameters
    ----------
    x, y, z : arrays of shape (N,)
    k : int  (CV folds)

    Returns
    -------
    best_p : float
    best_n : int
    best_isi : float
    final_results : list of tuples (p, n, mae, sae, isi)
    """
    train_xy = ensure_xy_components(x, y, "training coordinates")
    z = ensure_values_1d(z, "training values")
    x = train_xy[:, 0]
    y = train_xy[:, 1]
    n_samples = x.size
    if not (n_samples == y.size == z.size):
        raise ValueError("x, y, z must have the same length.")
    if n_samples < 5:
        raise ValueError("Need at least 5 samples for parameter optimization.")

    # Search grids (same ranges you had)
    p_values = np.arange(0.5, 6.5, 0.5)   # 0.5 .. 6.0 step 0.5
    n_values = np.arange(4, 17, 1)        # 4 .. 16

    kf = list(_kfold_indices(n_samples, n_splits=int(max(2, k)), shuffle=True, random_state=42))
    results_tmp = []
    all_mae = []
    all_sae = []

    # Evaluate each (p, n)
    for p in p_values:
        for n in n_values:
            mae_scores = []
            sae_scores = []
            for train_idx, test_idx in kf:
                x_tr, y_tr, z_tr = x[train_idx], y[train_idx], z[train_idx]
                x_te, y_te, z_te = x[test_idx],  y[test_idx],  z[test_idx]

                z_pred = idw_interpolation(x_tr, y_tr, z_tr, x_te, y_te, p, int(n))
                mae_scores.append(mean_absolute_error(z_pred, z_te))
                sae_scores.append(std_error(z_pred, z_te))

            avg_mae = float(np.mean(mae_scores))
            avg_sae = float(np.mean(sae_scores))
            all_mae.append(avg_mae)
            all_sae.append(avg_sae)
            results_tmp.append((float(p), int(n), avg_mae, avg_sae))

    # Normalize & compute ISI
    max_abs_ae = max(all_mae) if all_mae else 1.0
    min_sae    = min(all_sae) if all_sae else 0.0
    max_sae    = max(all_sae) if all_sae else 1.0

    best_p, best_n, best_isi = None, None, float('inf')
    final_results = []

    for (p, n, mae, sae) in results_tmp:
        isi = calculate_isi(mae, sae, max_abs_ae, min_sae, max_sae)
        final_results.append((p, n, mae, sae, isi))
        if isi < best_isi:
            best_p, best_n, best_isi = p, n, isi

    return float(best_p), int(best_n), float(best_isi), final_results
