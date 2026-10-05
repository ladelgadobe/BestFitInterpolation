
import numpy as np
from scipy.interpolate import Rbf

try:
    from scipy.interpolate import RBFInterpolator
except Exception:  # pragma: no cover - older SciPy bundled with QGIS
    RBFInterpolator = None

try:
    from .performance_policy import (
        DENSE_SAMPLE_THRESHOLD,
        DENSE_TPS_NEIGHBORS,
        MASSIVE_TPS_NEIGHBORS,
        MASSIVE_PREDICTION_CHUNK,
        is_massive_dataset,
    )
except Exception:  # pragma: no cover
    DENSE_SAMPLE_THRESHOLD = 500
    DENSE_TPS_NEIGHBORS = 64
    MASSIVE_TPS_NEIGHBORS = 32
    MASSIVE_PREDICTION_CHUNK = 5000

    def is_massive_dataset(sample_count):
        return int(sample_count) > 10000

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


def _as_1d_array(a):
    """Return input as a contiguous 1D float64 numpy array."""
    return np.asarray(a, dtype=float).ravel()


def _balanced_subset_indices(x, y, max_points=500):
    """Select representative coordinates with deterministic farthest-first sampling."""
    coords = np.column_stack((np.asarray(x, dtype=float), np.asarray(y, dtype=float)))
    n = coords.shape[0]
    max_points = max(1, min(int(max_points), n))
    if n <= max_points:
        return np.arange(n, dtype=int)

    center = np.nanmean(coords, axis=0)
    selected = np.empty(max_points, dtype=int)
    selected[0] = int(np.nanargmin(np.sum((coords - center) ** 2, axis=1)))
    min_dist2 = np.sum((coords - coords[selected[0]]) ** 2, axis=1)
    min_dist2[selected[0]] = -1.0

    for pos in range(1, max_points):
        idx = int(np.nanargmax(min_dist2))
        selected[pos] = idx
        dist2 = np.sum((coords - coords[idx]) ** 2, axis=1)
        min_dist2 = np.minimum(min_dist2, dist2)
        min_dist2[selected[:pos + 1]] = -1.0
    return np.sort(selected)


def _scale_coordinates_for_tps(x, y, xi, yi):
    """Scale coordinates to improve TPS conditioning on projected CRS values."""
    x = np.asarray(x, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    xi = np.asarray(xi, dtype=float).ravel()
    yi = np.asarray(yi, dtype=float).ravel()
    x_center = float(np.nanmean(x))
    y_center = float(np.nanmean(y))
    x_span = float(np.nanmax(x) - np.nanmin(x)) if x.size else 0.0
    y_span = float(np.nanmax(y) - np.nanmin(y)) if y.size else 0.0
    scale = max(x_span, y_span, 1.0)
    return (
        (x - x_center) / scale,
        (y - y_center) / scale,
        (xi - x_center) / scale,
        (yi - y_center) / scale,
    )


def tps_interpolation(
    x,
    y,
    z,
    xi,
    yi,
    epsilon=None,
    chunk_size=50000,
    progress_fn=None,
    dense_threshold=DENSE_SAMPLE_THRESHOLD,
    dense_neighbors=DENSE_TPS_NEIGHBORS,
):
    """
    Evaluate Thin Plate Spline (TPS) at query points.

    Parameters
    ----------
    x, y : array-like, shape (n_samples,)
        Training coordinates.
    z : array-like, shape (n_samples,)
        Training values.
    xi, yi : array-like, shape (n_queries,)
        Query coordinates where TPS will be evaluated.
    epsilon : float or None, optional
        RBF scale parameter. If None or <= 0, defaults to 1e-4.
    chunk_size : int, optional
        Number of query points to evaluate per batch to limit memory usage.

    Returns
    -------
    zi : np.ndarray, shape (n_queries,)
        Interpolated values at (xi, yi).

    Notes
    -----
    - Matches the original TPS script: Rbf(function='thin_plate', epsilon=epsilon).
    - If xi/yi are huge, chunked evaluation avoids large temporary arrays.
    """
    # Coerce inputs through shared helpers so single query points stay (1, 2).
    train_xy = ensure_xy_components(x, y, "training coordinates")
    query_xy = ensure_xy_components(xi, yi, "prediction coordinates")
    z = ensure_values_1d(z, "training values")
    x = train_xy[:, 0]
    y = train_xy[:, 1]
    xi = query_xy[:, 0]
    yi = query_xy[:, 1]

    if x.size != y.size or x.size != z.size:
        raise ValueError("Training arrays x, y, z must have the same length.")
    if xi.size != yi.size:
        raise ValueError("Query arrays xi, yi must have the same length.")
    if x.size > 1:
        xy = np.column_stack([x, y])
        if np.unique(xy, axis=0).shape[0] < xy.shape[0]:
            raise ValueError(
                "TPS training data contains duplicate coordinates. "
                "Keep one sample per coordinate before interpolation."
            )
    x_fit, y_fit, xi_fit, yi_fit = _scale_coordinates_for_tps(x, y, xi, yi)

    # Default epsilon
    if epsilon is None or float(epsilon) <= 0.0:
        epsilon = 1e-4  # default requested

    use_dense = x.size > int(dense_threshold)
    use_local = use_dense and RBFInterpolator is not None
    if use_local:
        # SciPy's neighbor-aware TPS keeps all observations available while
        # solving only a local system for each query point.
        neighbor_limit = MASSIVE_TPS_NEIGHBORS if is_massive_dataset(x.size) else dense_neighbors
        neighbors = max(3, min(int(neighbor_limit), x.size))
        rbf = RBFInterpolator(
            np.column_stack((x_fit, y_fit)),
            z,
            kernel="thin_plate_spline",
            neighbors=neighbors,
            smoothing=0.0,
        )
        max_chunk = MASSIVE_PREDICTION_CHUNK if is_massive_dataset(x.size) else 10000
        chunk_size = min(max(1, int(chunk_size or max_chunk)), max_chunk)
    elif use_dense:
        # Older QGIS SciPy builds may not provide RBFInterpolator. Keep dense
        # TPS bounded by fitting a deterministic representative subset.
        keep = _balanced_subset_indices(x, y, max_points=int(dense_threshold))
        rbf = Rbf(x_fit[keep], y_fit[keep], z[keep], function='thin_plate', epsilon=float(epsilon))
        max_chunk = MASSIVE_PREDICTION_CHUNK if is_massive_dataset(x.size) else 10000
        chunk_size = min(max(1, int(chunk_size or max_chunk)), max_chunk)
    else:
        # Legacy path retained unchanged for small datasets.
        rbf = Rbf(x_fit, y_fit, z, function='thin_plate', epsilon=float(epsilon))

    # Chunked prediction
    m = xi.size
    zi = np.empty(m, dtype=float)
    if chunk_size is None or chunk_size <= 0:
        chunk_size = m

    for start in range(0, m, chunk_size):
        end = min(m, start + chunk_size)
        if use_local:
            pred = rbf(np.column_stack((xi_fit[start:end], yi_fit[start:end])))
        else:
            pred = rbf(xi_fit[start:end], yi_fit[start:end])
        zi[start:end] = np.asarray(pred, dtype=float).ravel()
        if progress_fn is not None:
            progress_fn(end, m)

    return zi
