
import numpy as np
from scipy.interpolate import Rbf

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


def tps_interpolation(x, y, z, xi, yi, epsilon=None, chunk_size=50000):
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

    # Default epsilon
    if epsilon is None or float(epsilon) <= 0.0:
        epsilon = 1e-4  # default requested

    # Fit RBF TPS once, matching the original standalone Python script.
    rbf = Rbf(x, y, z, function='thin_plate', epsilon=float(epsilon))

    # Chunked prediction
    m = xi.size
    zi = np.empty(m, dtype=float)
    if chunk_size is None or chunk_size <= 0:
        chunk_size = m

    for start in range(0, m, chunk_size):
        end = min(m, start + chunk_size)
        pred = rbf(xi[start:end], yi[start:end])
        zi[start:end] = np.asarray(pred, dtype=float).ravel()

    return zi
