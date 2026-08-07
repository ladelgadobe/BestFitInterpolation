# -*- coding: utf-8 -*-
"""Inverse Distance Weighting — kernels moved near-verbatim from the legacy
IDW_optimized.py (pure numpy, no scipy)."""

from __future__ import annotations

import numpy as np

from ..arrays import ensure_values_1d, ensure_xy_2d
from ..cv import kfold_indices
from ..exceptions import OperationCancelled
from ..metrics import calculate_isi, mean_absolute_error, std_error
from ..types import FitResult, TrainingData
from .base import InterpolationMethod, MethodInfo

# Legacy search grids (optimize_idw), preserved verbatim.
P_VALUES = np.arange(0.5, 6.5, 0.5)   # 0.5 .. 6.0 step 0.5
N_VALUES = np.arange(4, 17, 1)        # 4 .. 16

DEFAULT_P = 2.0
DEFAULT_N = 12


def idw_predict(train_xy, z, query_xy, p, n):
    """Vectorized IDW at query points; exact hits return the sample value."""
    train_xy = ensure_xy_2d(train_xy, "training coordinates")
    query_xy = ensure_xy_2d(query_xy, "prediction coordinates")
    z = ensure_values_1d(z, "training values")
    if train_xy.shape[0] != z.size:
        raise ValueError("x, y, z must have the same length.")
    if train_xy.shape[0] == 0 or query_xy.shape[0] == 0:
        return np.array([], dtype=float)

    dx = query_xy[:, 0][:, None] - train_xy[:, 0][None, :]
    dy = query_xy[:, 1][:, None] - train_xy[:, 1][None, :]
    dist = np.sqrt(dx * dx + dy * dy)

    zero_hit = dist == 0.0
    zi = np.full(query_xy.shape[0], np.nan, dtype=float)
    has_zero = np.any(zero_hit, axis=1)
    if np.any(has_zero):
        first_zero_idx = np.argmax(zero_hit[has_zero, :], axis=1)
        zi[has_zero] = z[first_zero_idx]

    need = ~has_zero
    if np.any(need):
        dist_need = dist[need, :]
        n_eff = int(max(1, min(int(n), dist_need.shape[1])))
        idx_knn = np.argpartition(dist_need, kth=n_eff - 1, axis=1)[:, :n_eff]
        row = np.arange(idx_knn.shape[0])[:, None]

        d_knn = dist_need[row, idx_knn]
        d_knn[d_knn == 0.0] = 1e-12  # exact hits already handled above

        w = 1.0 / np.power(d_knn, float(p))
        w_sum = np.sum(w, axis=1, keepdims=True)
        w_sum[w_sum == 0.0] = 1e-12
        w /= w_sum

        zi[need] = np.sum(w * z[idx_knn], axis=1)

    return zi


def optimize_idw(train_xy, z, k=5, *, progress=None, should_stop=None):
    """Grid-search (p, n) with K-fold CV and ISI selection — legacy
    optimize_idw semantics and seeds, plus cancellation between candidates."""
    train_xy = ensure_xy_2d(train_xy, "training coordinates")
    z = ensure_values_1d(z, "training values")
    n_samples = train_xy.shape[0]
    if n_samples < 5:
        raise ValueError("Need at least 5 samples for parameter optimization.")

    kf = list(kfold_indices(n_samples, n_splits=int(max(2, k)), shuffle=True, random_state=42))
    results_tmp = []
    all_mae = []
    all_sae = []

    total = len(P_VALUES) * len(N_VALUES)
    done = 0
    for p in P_VALUES:
        for n in N_VALUES:
            if should_stop is not None and should_stop():
                raise OperationCancelled()
            mae_scores = []
            sae_scores = []
            for train_idx, test_idx in kf:
                z_pred = idw_predict(
                    train_xy[train_idx], z[train_idx], train_xy[test_idx], p, int(n)
                )
                mae_scores.append(mean_absolute_error(z_pred, z[test_idx]))
                sae_scores.append(std_error(z_pred, z[test_idx]))

            avg_mae = float(np.mean(mae_scores))
            avg_sae = float(np.mean(sae_scores))
            all_mae.append(avg_mae)
            all_sae.append(avg_sae)
            results_tmp.append((float(p), int(n), avg_mae, avg_sae))
            done += 1
            if progress is not None:
                progress(done, total)

    max_abs_ae = max(all_mae) if all_mae else 1.0
    min_sae = min(all_sae) if all_sae else 0.0
    max_sae = max(all_sae) if all_sae else 1.0

    best_p, best_n, best_isi = None, None, float("inf")
    final_results = []
    for (p, n, mae, sae) in results_tmp:
        isi = calculate_isi(mae, sae, max_abs_ae, min_sae, max_sae)
        final_results.append((p, n, mae, sae, isi))
        if isi < best_isi:
            best_p, best_n, best_isi = p, n, isi

    return float(best_p), int(best_n), float(best_isi), final_results


class IDWModel:
    def __init__(self, train_xy, values, p, n):
        self._xy = np.asarray(train_xy, dtype=float)
        self._z = np.asarray(values, dtype=float)
        self.p = float(p)
        self.n = int(n)

    def predict(self, xy, covariates=None, *, progress=None, should_stop=None,
                chunk_size=50000):
        xy = ensure_xy_2d(xy, "prediction coordinates")
        m = xy.shape[0]
        out = np.empty(m, dtype=float)
        step = int(chunk_size) if chunk_size else m
        for start in range(0, m, step):
            if should_stop is not None and should_stop():
                raise OperationCancelled()
            end = min(m, start + step)
            out[start:end] = idw_predict(self._xy, self._z, xy[start:end], self.p, self.n)
            if progress is not None:
                progress(end, m)
        return out


class IDWMethod(InterpolationMethod):
    info = MethodInfo(
        key="idw",
        label="Inverse Distance Weighting",
        min_samples=5,
        requires=(),
    )

    def fit(self, data: TrainingData, params=None, *, progress=None, should_stop=None) -> FitResult:
        self.validate(data)
        params = dict(params or {})
        diagnostics = {}
        if "p" in params and "n" in params:
            p, n = float(params["p"]), int(params["n"])
        else:
            p, n, best_isi, table = optimize_idw(
                data.xy, data.values, k=int(params.get("k", 5)),
                progress=progress, should_stop=should_stop,
            )
            diagnostics = {"best_isi": best_isi, "search_table": table}
        model = IDWModel(data.xy, data.values, p, n)
        return FitResult(model=model, params={"p": p, "n": n}, diagnostics=diagnostics)
