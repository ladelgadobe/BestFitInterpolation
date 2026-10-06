# -*- coding: utf-8 -*-
"""Numerical contracts for the version 1.2 dense-data profile."""

from pathlib import Path
import importlib.util
import sys

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from bestfitinterpolator.grid_utils import build_inside_grid_points
from bestfitinterpolator.IDW_optimized import (
    _kfold_indices,
    calculate_isi,
    idw_interpolation,
    mean_absolute_error,
    optimize_idw,
    std_error,
)
from bestfitinterpolator.kriging_ordinary import ordinary_kriging_interpolation
from bestfitinterpolator.performance_policy import (
    DENSE_KRIGING_NMAX,
    MASSIVE_SAMPLE_THRESHOLD,
    PRODUCTIVITY_REFERENCE_SAMPLE_THRESHOLD,
    VERY_MASSIVE_SAMPLE_THRESHOLD,
    dataset_scale_label,
    dense_search_limits,
    framework_validation_subset_indices,
    is_massive_dataset,
    massive_data_capacity_note,
    ml_holdout_validation_indices,
    moran_permutation_count,
    predict_in_chunks,
    recommended_variogram_bins,
    should_hexbin_plot,
    should_rasterize_scatter,
    svm_nystroem_components,
    tuning_subset,
)
from bestfitinterpolator.spatial_diagnostics import compute_moran_index_knn
from bestfitinterpolator.Thin_plate_spline import (
    _balanced_subset_indices,
    _scale_coordinates_for_tps,
    tps_interpolation,
)
from bestfitinterpolator.variogram_utils import (
    bin_experimental_variogram,
    max_pairwise_distance,
)


def test_pairwise_diameter_is_exact_without_dense_matrix():
    rng = np.random.default_rng(4)
    xy = rng.normal(size=(80, 2))
    expected = np.max(
        np.hypot(
            xy[:, None, 0] - xy[None, :, 0],
            xy[:, None, 1] - xy[None, :, 1],
        )
    )
    assert np.isclose(max_pairwise_distance(xy[:, 0], xy[:, 1]), expected)


def test_variogram_sampling_is_bounded_and_reproducible():
    rng = np.random.default_rng(10)
    xy = rng.random((1200, 2))
    z = np.sin(xy[:, 0] * 4.0) + xy[:, 1]
    args = (xy[:, 0], xy[:, 1], z, 0.8, 0.05)
    lags1, gamma1, info1 = bin_experimental_variogram(*args, max_pairs=10000, return_info=True)
    lags2, gamma2, info2 = bin_experimental_variogram(*args, max_pairs=10000, return_info=True)
    assert info1 == info2
    assert info1["sampled"] is True
    assert info1["pairs_used"] == 10000
    assert np.array_equal(lags1, lags2)
    assert np.array_equal(gamma1, gamma2)


def test_massive_variogram_bins_are_profile_limited():
    rng = np.random.default_rng(13)
    xy = rng.random((12000, 2))
    z = np.sin(xy[:, 0] * 6.0) + np.cos(xy[:, 1] * 3.0)
    lags, gamma, info = bin_experimental_variogram(
        xy[:, 0],
        xy[:, 1],
        z,
        cutoff=0.8,
        lag_width=0.001,
        max_pairs=20000,
        return_info=True,
    )
    assert recommended_variogram_bins(xy.shape[0]) == 24
    assert info["lag_bins"] <= 24
    assert lags.size == gamma.size


def test_dense_kriging_uses_local_profile_and_returns_finite_values():
    rng = np.random.default_rng(9)
    xy = rng.random((520, 2))
    z = xy[:, 0] - 0.5 * xy[:, 1]
    query = rng.random((20, 2))
    pred = ordinary_kriging_interpolation(
        xy[:, 0], xy[:, 1], z,
        query[:, 0], query[:, 1],
        nugget=0.01, psill=1.0, var_range=0.4, model="Sph",
    )
    assert DENSE_KRIGING_NMAX < xy.shape[0]
    assert pred.shape == (query.shape[0],)
    assert np.all(np.isfinite(pred))


def test_small_kriging_default_matches_explicit_global_solution():
    rng = np.random.default_rng(14)
    xy = rng.random((40, 2))
    z = np.cos(xy[:, 0]) + xy[:, 1]
    query = rng.random((12, 2))
    kwargs = dict(nugget=0.02, psill=0.8, var_range=0.5, model="Exp")
    automatic = ordinary_kriging_interpolation(
        xy[:, 0], xy[:, 1], z, query[:, 0], query[:, 1], **kwargs
    )
    explicit = ordinary_kriging_interpolation(
        xy[:, 0], xy[:, 1], z, query[:, 0], query[:, 1],
        nmax=xy.shape[0], **kwargs
    )
    assert np.allclose(automatic, explicit, rtol=1e-12, atol=1e-12)


def test_grid_blocks_keep_flat_raster_indices():
    x = np.arange(5, dtype=float)
    y = np.arange(4, dtype=float)
    points, indices = build_inside_grid_points(
        x, y, lambda pts: (pts[:, 0] >= 2) & (pts[:, 1] <= 2), row_block=2
    )
    assert points.shape == (9, 2)
    assert np.array_equal(indices, np.array([2, 3, 4, 7, 8, 9, 12, 13, 14]))


def test_ml_dense_bounds_subset_and_chunked_predictions():
    folds, iterations, changed = dense_search_limits(501, 10, 20)
    assert (folds, iterations, changed) == (3, 8, True)
    X = np.arange(9000, dtype=float).reshape(3000, 3)
    y = np.arange(3000, dtype=float)
    Xs, ys, sampled = tuning_subset(X, y, max_samples=500, random_state=20)
    assert sampled is True
    assert Xs.shape == (500, 3)
    assert ys.shape == (500,)

    class Model:
        def predict(self, values):
            return values[:, 0] + values[:, 1]

    pred = predict_in_chunks(Model(), X[:103], chunk_size=17)
    assert np.array_equal(pred, X[:103, 0] + X[:103, 1])


def test_productivity_scale_is_massive_above_10000_samples():
    assert MASSIVE_SAMPLE_THRESHOLD == 10000
    assert PRODUCTIVITY_REFERENCE_SAMPLE_THRESHOLD == 100000
    assert VERY_MASSIVE_SAMPLE_THRESHOLD > PRODUCTIVITY_REFERENCE_SAMPLE_THRESHOLD
    assert dataset_scale_label(500) == "normal"
    assert dataset_scale_label(501) == "dense"
    assert dataset_scale_label(10000) == "dense"
    assert dataset_scale_label(99000) == "massive"
    assert is_massive_dataset(99000) is True
    assert svm_nystroem_components(99000) == 128
    assert should_rasterize_scatter(99000) is True
    assert should_hexbin_plot(99000) is True

    x = np.linspace(0.0, 1.0, 99000)
    y = np.mod(np.arange(99000, dtype=float), 997.0)
    holdout_idx = ml_holdout_validation_indices(x.size)
    validation_idx, validation_sampled = framework_validation_subset_indices(
        x,
        y,
        sample_count=x.size,
    )
    assert holdout_idx.size == 10000
    assert validation_sampled is True
    assert validation_idx.size == 10000
    assert "no fixed sample-count stop" in massive_data_capacity_note(99000)


def test_moran_uses_all_valid_samples_for_large_knn_statistic():
    rng = np.random.default_rng(62)
    coords = rng.random((12000, 2))
    values = coords[:, 0] - coords[:, 1]
    result = compute_moran_index_knn(
        coords,
        values,
        k=8,
        n_permutations=19,
        random_seed=20,
    )
    assert result["n"] == coords.shape[0]
    assert result["k"] == 8
    assert result["permutations"] == 19
    assert np.isfinite(result["I"])


def test_moran_keeps_full_data_and_bounds_only_permutation_count():
    assert moran_permutation_count(500, 199) == 199
    assert moran_permutation_count(99000, 199) == 49
    assert moran_permutation_count(300000, 199) == 19


def test_tps_dense_fallback_stays_bounded_without_local_interpolator():
    import bestfitinterpolator.Thin_plate_spline as tps_module

    rng = np.random.default_rng(31)
    xy = rng.random((80, 2))
    z = np.sin(xy[:, 0] * 3.0) + xy[:, 1]
    query = rng.random((9, 2))
    keep = _balanced_subset_indices(xy[:, 0], xy[:, 1], max_points=20)
    assert keep.shape == (20,)

    original = tps_module.RBFInterpolator
    try:
        tps_module.RBFInterpolator = None
        pred = tps_interpolation(
            xy[:, 0], xy[:, 1], z,
            query[:, 0], query[:, 1],
            dense_threshold=20,
        )
    finally:
        tps_module.RBFInterpolator = original
    assert pred.shape == (query.shape[0],)
    assert np.all(np.isfinite(pred))


def test_tps_scales_projected_coordinates_before_interpolation():
    rng = np.random.default_rng(45)
    x = 500000.0 + rng.random(90) * 2500.0
    y = 7400000.0 + rng.random(90) * 2500.0
    z = np.sin((x - x.min()) / 500.0) + np.cos((y - y.min()) / 600.0)
    xi = np.linspace(float(x.min()), float(x.max()), 18)
    yi = np.linspace(float(y.min()), float(y.max()), 18)

    x_fit, y_fit, xi_fit, yi_fit = _scale_coordinates_for_tps(x, y, xi, yi)
    assert max(np.ptp(x_fit), np.ptp(y_fit)) <= 2.0
    assert max(np.ptp(xi_fit), np.ptp(yi_fit)) <= 2.0

    pred = tps_interpolation(x, y, z, xi, yi, dense_threshold=5000)
    assert pred.shape == (xi.shape[0],)
    assert np.all(np.isfinite(pred))


def test_idw_optimization_matches_small_reference_grid():
    rng = np.random.default_rng(44)
    xy = rng.random((18, 2))
    z = xy[:, 0] + 0.25 * xy[:, 1]
    best_p, best_n, best_isi, final_results = optimize_idw(xy[:, 0], xy[:, 1], z, k=4)

    p_values = np.arange(0.5, 6.5, 0.5)
    n_values = np.arange(4, 17, 1)
    folds = list(_kfold_indices(z.size, n_splits=4, shuffle=True, random_state=42))
    tmp = []
    all_mae, all_sae = [], []
    for p in p_values:
        for n in n_values:
            maes, saes = [], []
            for train_idx, test_idx in folds:
                pred = idw_interpolation(
                    xy[train_idx, 0], xy[train_idx, 1], z[train_idx],
                    xy[test_idx, 0], xy[test_idx, 1],
                    p=float(p), n=int(n),
                )
                maes.append(mean_absolute_error(pred, z[test_idx]))
                saes.append(std_error(pred, z[test_idx]))
            mae = float(np.mean(maes))
            sae = float(np.mean(saes))
            tmp.append((float(p), int(n), mae, sae))
            all_mae.append(mae)
            all_sae.append(sae)

    max_abs_ae = max(all_mae)
    min_sae = min(all_sae)
    max_sae = max(all_sae)
    reference = []
    for p, n, mae, sae in tmp:
        reference.append((p, n, mae, sae, calculate_isi(mae, sae, max_abs_ae, min_sae, max_sae)))
    ref_best = min(reference, key=lambda row: row[4])

    assert (best_p, best_n) == (ref_best[0], ref_best[1])
    assert np.isclose(best_isi, ref_best[4])
    assert np.allclose(np.asarray(final_results), np.asarray(reference))


def test_framework_observed_predicted_plots_share_limits():
    source = (ROOT / "framework_tab.py").read_text(encoding="utf-8")
    assert "def _common_observed_predicted_limits" in source
    assert "np.concatenate(values)" in source
    assert source.count("self._common_observed_predicted_limits") >= 2
