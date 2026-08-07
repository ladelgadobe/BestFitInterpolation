# -*- coding: utf-8 -*-
"""Spatial diagnostics — global Moran's I with KNN weights (moved verbatim
from the legacy Data tab; seeds and thresholds preserved)."""

from __future__ import annotations

import math

import numpy as np


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(float(x) / math.sqrt(2.0)))


def compute_moran_index_knn(xy, values, k=8, n_permutations=199, random_seed=20):
    """Global Moran's I using row-standardized KNN weights and a permutation
    z-score. Returns dict(I, z, p, pattern, k, n) or None when n < 3."""
    coords = np.asarray(xy, dtype=float)
    values = np.asarray(values, dtype=float)

    mask = np.isfinite(coords).all(axis=1) & np.isfinite(values)
    coords = coords[mask]
    values = values[mask]

    n = values.size
    if n < 3:
        return None

    k = max(1, min(int(k), n - 1))

    diff_x = coords[:, 0][:, None] - coords[:, 0][None, :]
    diff_y = coords[:, 1][:, None] - coords[:, 1][None, :]
    dist2 = diff_x * diff_x + diff_y * diff_y
    np.fill_diagonal(dist2, np.inf)
    neighbor_idx = np.argpartition(dist2, kth=k - 1, axis=1)[:, :k]

    x_dev = values - float(np.mean(values))
    den = float(np.sum(x_dev ** 2))
    if den <= 0:
        return {"I": 0.0, "z": 0.0, "p": 1.0, "pattern": "Random", "k": k, "n": n}

    neighbor_mean = np.mean(x_dev[neighbor_idx], axis=1)
    observed_i = float(np.sum(x_dev * neighbor_mean) / den)

    rng = np.random.default_rng(random_seed)
    sim_i = np.empty(int(max(19, n_permutations)), dtype=float)
    for b in range(sim_i.size):
        perm = rng.permutation(x_dev)
        perm_neighbor_mean = np.mean(perm[neighbor_idx], axis=1)
        sim_i[b] = float(np.sum(perm * perm_neighbor_mean) / den)

    sim_mean = float(np.mean(sim_i))
    sim_std = float(np.std(sim_i, ddof=1)) if sim_i.size > 1 else 0.0
    if sim_std > 0:
        z_score = float((observed_i - sim_mean) / sim_std)
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

    return {"I": observed_i, "z": z_score, "p": p_value, "pattern": pattern, "k": k, "n": n}
