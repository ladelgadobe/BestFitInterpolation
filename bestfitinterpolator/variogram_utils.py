# -*- coding: utf-8 -*-
"""Memory-bounded spatial distance and experimental variogram helpers."""

from __future__ import annotations

import math
import numpy as np

from .performance_policy import DENSE_VARIOGRAM_MAX_PAIRS, recommended_variogram_bins


def max_pairwise_distance(x, y):
    """Return the exact planar diameter without allocating an n-by-n matrix."""
    coords = np.column_stack((np.asarray(x, dtype=float), np.asarray(y, dtype=float)))
    coords = coords[np.all(np.isfinite(coords), axis=1)]
    if coords.shape[0] < 2:
        return 0.0
    try:
        from scipy.spatial import ConvexHull
        from scipy.spatial.distance import pdist

        if coords.shape[0] > 2:
            coords = coords[ConvexHull(coords).vertices]
        if coords.shape[0] < 2:
            return 0.0
        return float(np.max(pdist(coords)))
    except Exception:
        best = 0.0
        target_bytes = 32 * 1024 * 1024
        bytes_per_pair = 24
        block = max(1, min(1024, target_bytes // max(bytes_per_pair * coords.shape[0], 1)))
        for start in range(0, coords.shape[0], block):
            part = coords[start:start + block]
            dist2 = np.sum((part[:, None, :] - coords[None, :, :]) ** 2, axis=2)
            best = max(best, float(np.sqrt(np.max(dist2))))
        return best


def nearest_neighbor_distance(x, y):
    """Return the smallest positive nearest-neighbor distance."""
    coords = np.column_stack((np.asarray(x, dtype=float), np.asarray(y, dtype=float)))
    coords = coords[np.all(np.isfinite(coords), axis=1)]
    if coords.shape[0] < 2:
        return float("nan")
    scale = max(float(np.max(np.abs(coords))), 1.0)
    zero_tol = np.finfo(float).eps * scale * 32.0
    try:
        from scipy.spatial import cKDTree

        tree = cKDTree(coords)
        try:
            distances, _ = tree.query(coords, k=2, workers=1)
        except TypeError:  # older QGIS SciPy
            distances, _ = tree.query(coords, k=2)
        positive = distances[:, 1]
        positive = positive[np.isfinite(positive) & (positive > zero_tol)]
        return float(np.min(positive)) if positive.size else float("nan")
    except Exception:
        best = np.inf
        for i in range(coords.shape[0]):
            d = np.hypot(coords[:, 0] - coords[i, 0], coords[:, 1] - coords[i, 1])
            d = d[np.isfinite(d) & (d > zero_tol)]
            if d.size:
                best = min(best, float(np.min(d)))
        return best if np.isfinite(best) else float("nan")


def safe_lag_width(x, y, cutoff, lag_width, max_bins=10000):
    """Normalize lag width while retaining the existing UI behavior."""
    cutoff = float(cutoff)
    if not np.isfinite(cutoff) or cutoff <= 0:
        return float("nan")
    sample_count = int(np.asarray(x).ravel().size)
    recommended_bins = int(recommended_variogram_bins(sample_count))
    try:
        requested_bins = int(max_bins)
    except Exception:
        requested_bins = recommended_bins
    if requested_bins >= 10000:
        requested_bins = recommended_bins
    else:
        requested_bins = min(max(1, requested_bins), recommended_bins)
    try:
        width = float(lag_width)
    except Exception:
        width = float("nan")
    if not np.isfinite(width) or width <= 0:
        width = nearest_neighbor_distance(x, y)
    if not np.isfinite(width) or width <= 0:
        width = cutoff / 12.0
    return float(max(width, cutoff / float(max(1, requested_bins))))


def _condensed_indices_to_pairs(indices, n):
    """Map SciPy condensed-distance indices to upper-triangle row/column pairs."""
    k = np.asarray(indices, dtype=np.int64)
    i = n - 2 - np.floor(
        np.sqrt(-8.0 * k + 4.0 * n * (n - 1) - 7.0) / 2.0 - 0.5
    ).astype(np.int64)
    before = n * i - (i * (i + 1)) // 2
    j = k - before + i + 1
    return i, j


def _sample_pairs(n, max_pairs, random_state):
    total = n * (n - 1) // 2
    if total <= max_pairs:
        return None, total
    rng = np.random.default_rng(int(random_state))
    selected = rng.choice(total, size=int(max_pairs), replace=False)
    return _condensed_indices_to_pairs(selected, n), total


def bin_experimental_variogram(
    x,
    y,
    z,
    cutoff,
    lag_width,
    max_pairs=DENSE_VARIOGRAM_MAX_PAIRS,
    random_state=12345,
    return_info=False,
):
    """Bin semivariances with exact small-n and bounded reproducible dense-n paths."""
    x = np.asarray(x, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    z = np.asarray(z, dtype=float).ravel()
    if not (x.size == y.size == z.size):
        raise ValueError("x, y and z must have the same length.")
    cutoff = float(cutoff)
    width = safe_lag_width(x, y, cutoff, lag_width)
    if not np.isfinite(cutoff) or cutoff <= 0 or not np.isfinite(width) or width <= 0:
        empty = (np.array([], dtype=float), np.array([], dtype=float))
        return (*empty, {"sampled": False, "pairs_used": 0, "pairs_total": 0}) if return_info else empty

    max_bins = int(recommended_variogram_bins(x.size))
    nbins = max(1, min(max_bins, int(math.floor(cutoff / width))))
    if nbins >= max_bins:
        width = cutoff / float(nbins)
    sums = np.zeros(nbins, dtype=float)
    counts = np.zeros(nbins, dtype=np.int64)
    dist_sums = np.zeros(nbins, dtype=float)

    sampled_pairs, pairs_total = _sample_pairs(x.size, int(max_pairs), random_state)
    if sampled_pairs is None:
        for i in range(x.size - 1):
            dd = np.hypot(x[i + 1:] - x[i], y[i + 1:] - y[i])
            gamma = 0.5 * (z[i] - z[i + 1:]) ** 2
            mask = np.isfinite(dd) & np.isfinite(gamma) & (dd > 0) & (dd <= cutoff)
            if not np.any(mask):
                continue
            dd = dd[mask]
            gamma = gamma[mask]
            bins = np.minimum(np.floor(dd / width).astype(np.int64), nbins - 1)
            sums += np.bincount(bins, weights=gamma, minlength=nbins)[:nbins]
            counts += np.bincount(bins, minlength=nbins)[:nbins]
            dist_sums += np.bincount(bins, weights=dd, minlength=nbins)[:nbins]
        pairs_used = pairs_total
        sampled = False
    else:
        i, j = sampled_pairs
        dd = np.hypot(x[j] - x[i], y[j] - y[i])
        gamma = 0.5 * (z[i] - z[j]) ** 2
        mask = np.isfinite(dd) & np.isfinite(gamma) & (dd > 0) & (dd <= cutoff)
        dd = dd[mask]
        gamma = gamma[mask]
        bins = np.minimum(np.floor(dd / width).astype(np.int64), nbins - 1)
        sums += np.bincount(bins, weights=gamma, minlength=nbins)[:nbins]
        counts += np.bincount(bins, minlength=nbins)[:nbins]
        dist_sums += np.bincount(bins, weights=dd, minlength=nbins)[:nbins]
        pairs_used = int(i.size)
        sampled = True

    valid = counts > 0
    lags = dist_sums[valid] / counts[valid]
    gamma = sums[valid] / counts[valid]
    info = {
        "sampled": sampled,
        "pairs_used": pairs_used,
        "pairs_total": int(pairs_total),
        "max_pairs": int(max_pairs),
        "lag_bins": int(nbins),
        "lag_width": float(width),
    }
    return (lags, gamma, info) if return_info else (lags, gamma)
