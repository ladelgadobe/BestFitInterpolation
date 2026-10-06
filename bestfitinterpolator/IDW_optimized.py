# -*- coding: utf-8 -*-
"""
IDW_optimized.py
Deterministic IDW interpolation and parameter optimization.

- Same public API as your original:
  * idw_interpolation(x, y, z, xi, yi, p, n) -> zi
  * optimize_idw(x, y, z, k=5) -> best_p, best_n, best_isi, final_results
    where final_results = [(p, n, mae, sae, isi), ...]
- ISI computed from normalized MAE and SAE, matching your logic.

All code comments are in English. User-facing strings in English.
"""

import numpy as np

try:
    from scipy.spatial import cKDTree
except Exception:  # pragma: no cover - SciPy should exist in QGIS, fallback remains
    cKDTree = None

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


def _prediction_chunk_size(n_train, n_queries, max_memory_mb=64):
    """Return a query block size that bounds IDW temporary matrices."""
    if n_queries <= 0:
        return 1
    # Distance, exact-hit mask, neighbor indices/values, and weights coexist.
    bytes_per_query = max(int(n_train) * 40, 1)
    target_bytes = max(int(max_memory_mb), 1) * 1024 * 1024
    return max(1, min(int(n_queries), target_bytes // bytes_per_query))


def _query_tree(tree, query_xy, n_neighbors):
    try:
        distances, indices = tree.query(query_xy, k=int(n_neighbors), workers=1)
    except TypeError:  # older SciPy bundled with some QGIS builds
        distances, indices = tree.query(query_xy, k=int(n_neighbors))
    distances = np.asarray(distances, dtype=float)
    indices = np.asarray(indices, dtype=int)
    if distances.ndim == 1:
        distances = distances[:, None]
        indices = indices[:, None]
    return distances, indices


def idw_interpolation(
    x,
    y,
    z,
    xi,
    yi,
    p,
    n,
    chunk_size=None,
    progress_fn=None,
):
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

    zi = np.full(xi.shape[0], np.nan, dtype=float)
    n_eff = int(max(1, min(int(n), x.size)))
    tree = None
    if cKDTree is not None:
        try:
            tree = cKDTree(np.column_stack((x, y)))
        except Exception:
            tree = None
    if chunk_size is None or int(chunk_size) <= 0:
        chunk_size = 25000 if tree is not None else _prediction_chunk_size(x.size, xi.size)
    else:
        chunk_size = max(1, int(chunk_size))

    for start in range(0, xi.size, chunk_size):
        end = min(xi.size, start + chunk_size)
        block_values = np.full(end - start, np.nan, dtype=float)
        if tree is not None:
            dist, idx_knn = _query_tree(tree, np.column_stack((xi[start:end], yi[start:end])), n_eff)
            zero_hit = dist == 0.0
            has_zero = np.any(zero_hit, axis=1)
            if np.any(has_zero):
                first_zero_idx = np.argmax(zero_hit[has_zero, :], axis=1)
                block_values[has_zero] = z[idx_knn[has_zero, first_zero_idx]]

            need = ~has_zero
            if np.any(need):
                d_knn = np.maximum(dist[need, :], 1e-12)
                z_knn = z[idx_knn[need, :]]
                weights = 1.0 / np.power(d_knn, float(p))
                weight_sum = np.sum(weights, axis=1, keepdims=True)
                weight_sum[weight_sum == 0.0] = 1e-12
                weights /= weight_sum
                block_values[need] = np.sum(weights * z_knn, axis=1)

            zi[start:end] = block_values
            if progress_fn is not None:
                try:
                    progress_fn(end, xi.size)
                except Exception:  # nosec B110
                    pass
            continue

        dist = _pairwise_dist(x, y, xi[start:end], yi[start:end])

        # Exact hits return the first coincident sample value.
        zero_hit = dist == 0.0
        block_values = np.full(end - start, np.nan, dtype=float)
        has_zero = np.any(zero_hit, axis=1)
        if np.any(has_zero):
            first_zero_idx = np.argmax(zero_hit[has_zero, :], axis=1)
            block_values[has_zero] = z[first_zero_idx]

        need = ~has_zero
        if np.any(need):
            dist_need = dist[need, :]
            idx_knn = np.argpartition(
                dist_need,
                kth=n_eff - 1,
                axis=1,
            )[:, :n_eff]
            row = np.arange(idx_knn.shape[0])[:, None]
            d_knn = dist_need[row, idx_knn]
            d_knn[d_knn == 0.0] = 1e-12

            weights = 1.0 / np.power(d_knn, float(p))
            weight_sum = np.sum(weights, axis=1, keepdims=True)
            weight_sum[weight_sum == 0.0] = 1e-12
            weights /= weight_sum
            block_values[need] = np.sum(weights * z[idx_knn], axis=1)

        zi[start:end] = block_values
        if progress_fn is not None:
            try:
                progress_fn(end, xi.size)
            except Exception:  # nosec B110
                pass

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

def optimize_idw(x, y, z, k=5, progress_fn=None):
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
    scores = {
        (float(p), int(n)): ([], [])
        for p in p_values
        for n in n_values
    }

    # Distances and nearest neighbors are independent of p. Compute them once
    # per fold instead of repeating the O(n^2) work for all 156 combinations.
    for fold_no, (train_idx, test_idx) in enumerate(kf, start=1):
        x_tr, y_tr, z_tr = x[train_idx], y[train_idx], z[train_idx]
        x_te, y_te, z_te = x[test_idx], y[test_idx], z[test_idx]
        fold_neighbors = int(min(np.max(n_values), x_tr.size))
        nearest_d = np.empty((test_idx.size, fold_neighbors), dtype=float)
        nearest_z = np.empty((test_idx.size, fold_neighbors), dtype=float)
        exact_values = np.full(test_idx.size, np.nan, dtype=float)

        tree = None
        if cKDTree is not None:
            try:
                tree = cKDTree(np.column_stack((x_tr, y_tr)))
            except Exception:
                tree = None
        if tree is not None:
            nearest_d, idx = _query_tree(
                tree,
                np.column_stack((x_te, y_te)),
                fold_neighbors,
            )
            nearest_z = z_tr[idx]
            zero_hit = nearest_d == 0.0
            has_zero = np.any(zero_hit, axis=1)
            if np.any(has_zero):
                first_zero = np.argmax(zero_hit[has_zero], axis=1)
                exact_values[np.flatnonzero(has_zero)] = z_tr[idx[has_zero, first_zero]]
        else:
            block = _prediction_chunk_size(x_tr.size, test_idx.size)
            for start in range(0, test_idx.size, block):
                end = min(test_idx.size, start + block)
                dist = _pairwise_dist(x_tr, y_tr, x_te[start:end], y_te[start:end])
                zero_hit = dist == 0.0
                has_zero = np.any(zero_hit, axis=1)
                if np.any(has_zero):
                    first_zero = np.argmax(zero_hit[has_zero], axis=1)
                    exact_values[start + np.flatnonzero(has_zero)] = z_tr[first_zero]
                idx = np.argpartition(dist, kth=fold_neighbors - 1, axis=1)[:, :fold_neighbors]
                row = np.arange(idx.shape[0])[:, None]
                selected_d = dist[row, idx]
                order = np.argsort(selected_d, axis=1)
                idx = idx[row, order]
                nearest_d[start:end] = dist[row, idx]
                nearest_z[start:end] = z_tr[idx]

        safe_d = np.maximum(nearest_d, 1e-12)
        exact_mask = np.isfinite(exact_values)
        for p in p_values:
            weights = 1.0 / np.power(safe_d, float(p))
            cumulative_w = np.cumsum(weights, axis=1)
            cumulative_wz = np.cumsum(weights * nearest_z, axis=1)
            for n in n_values:
                n_eff = min(int(n), fold_neighbors)
                pred = cumulative_wz[:, n_eff - 1] / np.maximum(cumulative_w[:, n_eff - 1], 1e-12)
                if np.any(exact_mask):
                    pred = pred.copy()
                    pred[exact_mask] = exact_values[exact_mask]
                mae_list, sae_list = scores[(float(p), int(n))]
                mae_list.append(mean_absolute_error(pred, z_te))
                sae_list.append(std_error(pred, z_te))

        if progress_fn is not None:
            progress_fn(fold_no, len(kf))

    results_tmp = []
    all_mae = []
    all_sae = []
    for p in p_values:
        for n in n_values:
            mae_scores, sae_scores = scores[(float(p), int(n))]
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
