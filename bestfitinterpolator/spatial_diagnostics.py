# -*- coding: utf-8 -*-
"""UI-independent spatial diagnostics used by Data and Framework workflows."""

from __future__ import annotations

import math

import numpy as np


def _normal_cdf(value):
    """Return the standard normal cumulative probability."""
    return 0.5 * (1.0 + math.erf(float(value) / math.sqrt(2.0)))


def _knn_indices(coords, k, block_memory_mb=32):
    """Return KNN row indices without allocating a full ``n x n`` matrix."""
    coords = np.asarray(coords, dtype=float)
    n = int(coords.shape[0])
    k = max(1, min(int(k), n - 1))

    try:
        from scipy.spatial import cKDTree

        tree = cKDTree(coords)
        result_cols = int(k + 1)
        bytes_per_query = result_cols * (
            np.dtype(float).itemsize + np.dtype(np.intp).itemsize
        )
        target_bytes = max(int(block_memory_mb), 1) * 1024 * 1024
        query_block = max(1, min(n, target_bytes // max(bytes_per_query, 1)))
        neighbors = np.empty((n, k), dtype=np.int32)
        for start in range(0, n, query_block):
            end = min(n, start + query_block)
            try:
                _, candidates = tree.query(coords[start:end], k=result_cols, workers=1)
            except TypeError:
                # ``workers`` is unavailable in older SciPy builds shipped with
                # some supported QGIS versions.
                _, candidates = tree.query(coords[start:end], k=result_cols)
            candidates = np.asarray(candidates, dtype=np.int64)
            if candidates.ndim == 1:
                candidates = candidates[:, None]

            for local_row, row in enumerate(range(start, end)):
                without_self = candidates[local_row][candidates[local_row] != row]
                if without_self.size < k:
                    raise ValueError("KNN query did not return enough non-self neighbors.")
                neighbors[row] = without_self[:k].astype(np.int32, copy=False)
        return neighbors
    except (ImportError, ValueError):
        # NumPy fallback for environments where SciPy is unavailable. The
        # distance calculation is blockwise, so peak memory stays bounded.
        # Coordinate deltas, squared distances, and temporary arrays coexist.
        bytes_per_row = max(n * np.dtype(float).itemsize * 4, 1)
        target_bytes = max(int(block_memory_mb), 1) * 1024 * 1024
        block_size = max(1, min(n, target_bytes // bytes_per_row))
        neighbors = np.empty((n, k), dtype=np.int32)

        for start in range(0, n, block_size):
            end = min(n, start + block_size)
            delta = coords[start:end, None, :] - coords[None, :, :]
            dist2 = np.einsum("ijk,ijk->ij", delta, delta)
            local_rows = np.arange(end - start)
            global_rows = np.arange(start, end)
            dist2[local_rows, global_rows] = np.inf
            neighbors[start:end] = np.argpartition(
                dist2,
                kth=k - 1,
                axis=1,
            )[:, :k]

        return neighbors


def compute_moran_index_knn(
    coordinates,
    values,
    k=8,
    n_permutations=199,
    random_seed=20,
):
    """Compute global Moran's I with row-standardized binary KNN weights.

    The statistical definition and defaults match the legacy implementation.
    Only neighbor discovery changes: a spatial tree replaces the dense
    pairwise distance matrices that could exhaust QGIS memory.
    """
    coords = np.asarray(coordinates, dtype=float)
    values = np.asarray(values, dtype=float).ravel()
    if coords.ndim != 2 or coords.shape[1] != 2:
        raise ValueError("coordinates must have shape (n, 2).")
    if coords.shape[0] != values.size:
        raise ValueError("coordinates and values must contain the same number of rows.")

    mask = np.isfinite(coords).all(axis=1) & np.isfinite(values)
    coords = coords[mask]
    values = values[mask]

    n = int(values.size)
    if n < 3:
        return None

    k = max(1, min(int(k), n - 1))
    neighbor_idx = _knn_indices(coords, k).astype(np.intp, copy=False)

    x_dev = values - float(np.mean(values))
    denominator = float(np.sum(x_dev ** 2))
    if denominator <= 0:
        return {
            "I": 0.0,
            "z": 0.0,
            "p": 1.0,
            "pattern": "Random",
            "k": k,
            "n": n,
            "permutations": 0,
        }

    inv_k = 1.0 / float(k)
    neighbor_sum = np.add.reduce(x_dev[neighbor_idx], axis=1)
    observed_i = float(np.sum(x_dev * neighbor_sum) * inv_k / denominator)

    rng = np.random.default_rng(random_seed)
    permutation_count = int(max(19, n_permutations))
    simulations = np.empty(permutation_count, dtype=float)
    for index in range(simulations.size):
        permuted = rng.permutation(x_dev)
        permuted_neighbor_sum = np.add.reduce(permuted[neighbor_idx], axis=1)
        simulations[index] = float(
            np.sum(permuted * permuted_neighbor_sum) * inv_k / denominator
        )

    simulation_mean = float(np.mean(simulations))
    simulation_std = (
        float(np.std(simulations, ddof=1)) if simulations.size > 1 else 0.0
    )
    if simulation_std > 0:
        z_score = float((observed_i - simulation_mean) / simulation_std)
        p_value = float(2.0 * (1.0 - _normal_cdf(abs(z_score))))
    else:
        z_score = 0.0
        p_value = 1.0

    if z_score > 1.96:
        pattern = "Clustered"
    elif z_score < -1.96:
        pattern = "Dispersed"
    else:
        pattern = "Random"

    return {
        "I": observed_i,
        "z": z_score,
        "p": p_value,
        "pattern": pattern,
        "k": k,
        "n": n,
        "permutations": permutation_count,
    }
