# -*- coding: utf-8 -*-
"""Shared limits for responsive processing of dense sample datasets.

The 1.2 policy intentionally keeps the legacy algorithms unchanged up to the
dense-data threshold.  Above it, expensive searches and local spatial systems
are bounded while final machine-learning fits still use every valid sample.
"""

import numpy as np

DENSE_SAMPLE_THRESHOLD = 500
MASSIVE_SAMPLE_THRESHOLD = 10000
COMPUTATIONAL_WARNING_THRESHOLD = 50000
PRODUCTIVITY_REFERENCE_SAMPLE_THRESHOLD = 100000
VERY_MASSIVE_SAMPLE_THRESHOLD = 250000
FRAMEWORK_DENSE_SEARCH_FOLDS = 3
FRAMEWORK_DENSE_SEARCH_ITERATIONS = 8
DENSE_TUNING_MAX_SAMPLES = 2000
FRAMEWORK_VALIDATION_SUBSET_THRESHOLD = MASSIVE_SAMPLE_THRESHOLD
FRAMEWORK_VALIDATION_MAX_SAMPLES = 10000
PLOT_MAX_SAMPLES = 10000
PLOT_RASTERIZED_SCATTER_THRESHOLD = 10000
PLOT_HEXBIN_THRESHOLD = 50000
PLOT_HEXBIN_GRIDSIZE = 180
DENSE_KRIGING_NMAX = 64
DENSE_KRIGING_NMIN = 16
DENSE_TPS_NEIGHBORS = 64
MASSIVE_TPS_NEIGHBORS = 32
DENSE_VARIOGRAM_MAX_PAIRS = 250000
DENSE_PREDICTION_CHUNK = 25000
MASSIVE_PREDICTION_CHUNK = 5000
DENSE_SVM_APPROX_THRESHOLD = DENSE_SAMPLE_THRESHOLD
DENSE_SVM_NYSTROEM_COMPONENTS = 256
MASSIVE_SVM_NYSTROEM_COMPONENTS = 128
MASSIVE_RF_MAX_TREES = 300
MASSIVE_RF_MIN_LEAF = 5
ML_MASSIVE_HOLDOUT_FRACTION = 0.2
ML_MASSIVE_HOLDOUT_MAX_TEST = 10000
MORAN_DENSE_PERMUTATIONS = 199
MORAN_MASSIVE_PERMUTATIONS = 49
MORAN_VERY_MASSIVE_PERMUTATIONS = 19


def is_dense_dataset(sample_count):
    """Return whether the sample count uses the dense-data profile."""
    return int(sample_count) > DENSE_SAMPLE_THRESHOLD


def is_massive_dataset(sample_count):
    """Return whether the sample count uses the massive productivity-data profile."""
    return int(sample_count) > MASSIVE_SAMPLE_THRESHOLD


def dataset_scale_label(sample_count):
    """Return the runtime profile label for user-facing disclosures."""
    n = int(sample_count)
    if n > MASSIVE_SAMPLE_THRESHOLD:
        return "massive"
    if n > DENSE_SAMPLE_THRESHOLD:
        return "dense"
    return "normal"


def moran_permutation_count(sample_count, requested=199):
    """Keep Moran's I exact while bounding permutation cost for massive data."""
    n = int(sample_count)
    req = max(0, int(requested))
    if n > VERY_MASSIVE_SAMPLE_THRESHOLD:
        return min(req, MORAN_VERY_MASSIVE_PERMUTATIONS)
    if n > MASSIVE_SAMPLE_THRESHOLD:
        return min(req, MORAN_MASSIVE_PERMUTATIONS)
    if n > DENSE_SAMPLE_THRESHOLD:
        return min(req, MORAN_DENSE_PERMUTATIONS)
    return req


def dense_search_limits(sample_count, requested_folds, requested_iterations):
    """Bound ML tuning while keeping the final fit on all valid rows."""
    folds = max(2, int(requested_folds))
    iterations = max(1, int(requested_iterations))
    if not is_dense_dataset(sample_count):
        return folds, iterations, False
    bounded_folds = min(folds, FRAMEWORK_DENSE_SEARCH_FOLDS)
    bounded_iterations = min(iterations, FRAMEWORK_DENSE_SEARCH_ITERATIONS)
    changed = bounded_folds != folds or bounded_iterations != iterations
    return bounded_folds, bounded_iterations, changed


def framework_search_limits(sample_count, requested_folds, requested_iterations):
    """Backward-compatible alias for callers introduced early in version 1.2."""
    return dense_search_limits(sample_count, requested_folds, requested_iterations)


def tuning_subset(X, y, max_samples=DENSE_TUNING_MAX_SAMPLES, random_state=20):
    """Return a reproducible search subset; final model fitting remains external."""
    X = np.asarray(X)
    y = np.asarray(y)
    if X.shape[0] != y.shape[0]:
        raise ValueError("X and y must contain the same number of rows.")
    limit = max(2, int(max_samples))
    if X.shape[0] <= limit:
        return X, y, False
    rng = np.random.default_rng(int(random_state))
    selected = np.sort(rng.choice(X.shape[0], size=limit, replace=False))
    return X[selected], y[selected], True


def representative_sample_indices(
    x,
    y,
    max_samples=FRAMEWORK_VALIDATION_MAX_SAMPLES,
    random_state=20,
):
    """Return spatially representative indices without an O(n²) selection step."""
    x = np.asarray(x, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    if x.shape[0] != y.shape[0]:
        raise ValueError("x and y must contain the same number of rows.")

    n = int(x.shape[0])
    limit = max(1, int(max_samples))
    if n <= limit:
        return np.arange(n, dtype=int), False

    finite_mask = np.isfinite(x) & np.isfinite(y)
    finite_idx = np.flatnonzero(finite_mask)
    if finite_idx.size <= limit:
        return finite_idx.astype(int), finite_idx.size != n

    xf = x[finite_idx]
    yf = y[finite_idx]
    xmin = float(np.nanmin(xf))
    xmax = float(np.nanmax(xf))
    ymin = float(np.nanmin(yf))
    ymax = float(np.nanmax(yf))
    rng = np.random.default_rng(int(random_state))

    if not np.isfinite([xmin, xmax, ymin, ymax]).all() or xmax <= xmin or ymax <= ymin:
        selected = np.sort(rng.choice(finite_idx, size=limit, replace=False))
        return selected.astype(int), True

    n_bins = max(1, int(np.ceil(np.sqrt(limit))))
    xi = np.floor((xf - xmin) / max(xmax - xmin, 1e-12) * n_bins).astype(int)
    yi = np.floor((yf - ymin) / max(ymax - ymin, 1e-12) * n_bins).astype(int)
    xi = np.clip(xi, 0, n_bins - 1)
    yi = np.clip(yi, 0, n_bins - 1)
    cells = xi * n_bins + yi

    order = rng.permutation(finite_idx.size)
    shuffled_cells = cells[order]
    _, first_positions = np.unique(shuffled_cells, return_index=True)
    selected = finite_idx[order[np.sort(first_positions)]]

    if selected.size > limit:
        selected = rng.choice(selected, size=limit, replace=False)
    elif selected.size < limit:
        remaining = np.setdiff1d(finite_idx, selected, assume_unique=False)
        extra_count = min(limit - selected.size, remaining.size)
        if extra_count > 0:
            extra = rng.choice(remaining, size=extra_count, replace=False)
            selected = np.concatenate([selected, extra])

    return np.sort(selected).astype(int), True


def framework_validation_subset_indices(x, y, sample_count=None, random_state=20):
    """Return indices used by Framework validation for massive data."""
    n = int(sample_count if sample_count is not None else len(np.asarray(x).ravel()))
    if n <= FRAMEWORK_VALIDATION_SUBSET_THRESHOLD:
        return np.arange(n, dtype=int), False
    return representative_sample_indices(
        x,
        y,
        max_samples=FRAMEWORK_VALIDATION_MAX_SAMPLES,
        random_state=random_state,
    )


def plotting_sample_indices(x, y, sample_count=None, random_state=20):
    """Return representative indices for drawing large point clouds only."""
    n = int(sample_count if sample_count is not None else len(np.asarray(x).ravel()))
    if n <= PLOT_MAX_SAMPLES:
        return np.arange(n, dtype=int), False
    return representative_sample_indices(
        x,
        y,
        max_samples=PLOT_MAX_SAMPLES,
        random_state=random_state,
    )


def recommended_variogram_bins(sample_count):
    """Return a legible maximum lag count for the current data profile."""
    n = int(sample_count)
    if n > MASSIVE_SAMPLE_THRESHOLD:
        return 24
    if n > DENSE_SAMPLE_THRESHOLD:
        return 36
    return 10000


def should_hexbin_plot(sample_count):
    """Return whether point plots should use a density-style hexbin view."""
    return int(sample_count) > PLOT_HEXBIN_THRESHOLD


def should_rasterize_scatter(sample_count):
    """Return whether Matplotlib scatter markers should be rasterized."""
    return int(sample_count) > PLOT_RASTERIZED_SCATTER_THRESHOLD


def ml_holdout_validation_indices(
    sample_count,
    fraction=ML_MASSIVE_HOLDOUT_FRACTION,
    max_test=ML_MASSIVE_HOLDOUT_MAX_TEST,
    random_state=20,
):
    """Return reproducible hold-out validation indices for massive ML datasets."""
    n = int(sample_count)
    if n <= MASSIVE_SAMPLE_THRESHOLD:
        return None
    if n < 5:
        return None
    test_size = int(round(float(fraction) * n))
    test_size = min(int(max_test), max(1000, test_size))
    test_size = max(1, min(test_size, n - 2))
    rng = np.random.default_rng(int(random_state))
    return np.sort(rng.choice(n, size=test_size, replace=False)).astype(int)


def svm_nystroem_components(sample_count):
    """Bound approximate SVM feature expansion for very large productivity datasets."""
    if is_massive_dataset(sample_count):
        return MASSIVE_SVM_NYSTROEM_COMPONENTS
    return DENSE_SVM_NYSTROEM_COMPONENTS


def predict_in_chunks(model, X, chunk_size=DENSE_PREDICTION_CHUNK, progress_fn=None, label=None):
    """Predict without materializing another full-size model input/output copy."""
    X = np.asarray(X)
    total = int(X.shape[0])
    if total == 0:
        return np.array([], dtype=float)
    block = max(1, int(chunk_size))
    result = np.empty(total, dtype=float)
    for start in range(0, total, block):
        end = min(total, start + block)
        result[start:end] = np.asarray(model.predict(X[start:end]), dtype=float).ravel()
        if progress_fn is not None:
            try:
                progress_fn(end, total, label)
            except TypeError:
                progress_fn(end, total)
    return result


def dense_method_notice(sample_count, method_name="interpolation"):
    """Return a concise profile disclosure for metadata and optional UI text."""
    scale = dataset_scale_label(sample_count)
    return f"{method_name}: {scale} data profile ({int(sample_count):,} valid samples)."


def massive_data_capacity_note(sample_count=None):
    """Return a non-modal note for manuals and Data-tab profile disclosures."""
    suffix = ""
    if sample_count is not None:
        suffix = f" Current selection: {int(sample_count):,} valid samples."
    return (
        "Massive mode has no fixed sample-count stop and includes productivity "
        f"datasets around {PRODUCTIVITY_REFERENCE_SAMPLE_THRESHOLD:,}+ samples. "
        "Practical runtime still depends on sample count, raster grid cells, "
        "covariates, and the selected method."
        f"{suffix}"
    )


def dense_framework_notice(sample_count, folds, iterations):
    """Return a concise Framework data-profile disclosure."""
    scale = dataset_scale_label(sample_count)
    return (
        f"Framework data profile: {scale} ({int(sample_count):,} valid samples). "
        "See the Data tab profile info and manual for details."
    )
