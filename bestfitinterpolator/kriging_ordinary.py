# kriging_ordinary.py
# Pure-Python Ordinary Kriging using NumPy/SciPy.
# UI parameterization: nugget=c0, partial sill=c, range=a
# Models:
#   spherical:  γ(h)=c0 + c*(1.5*(h/a) - 0.5*(h/a)^3) for h<=a; else c0+c
#   exponential:γ(h)=c0 + c*(1 - exp(-h/a))
#   gaussian:   γ(h)=c0 + c*(1 - exp(-(h/a)^2))
#
# Notes:
# - We enforce γ(0)=0 in the kriging matrix (nugget NOT on the diagonal).
# - We factorize the (n+1)x(n+1) system ONCE (LU), then reuse for every prediction.

import numpy as np
from collections import OrderedDict
from scipy.spatial import cKDTree
from scipy.spatial.distance import cdist
from scipy.linalg import lu_factor, lu_solve

try:
    from .performance_policy import (
        DENSE_KRIGING_NMAX,
        DENSE_KRIGING_NMIN,
        DENSE_SAMPLE_THRESHOLD,
    )
except Exception:  # pragma: no cover - direct module loading in diagnostics
    DENSE_KRIGING_NMAX = 64
    DENSE_KRIGING_NMIN = 16
    DENSE_SAMPLE_THRESHOLD = 500

def _spherical_core(h, a, c):
    a = max(float(a), 1e-12)
    hr = np.clip(h / a, 0.0, np.inf)
    return np.where(h <= a, c * (1.5 * hr - 0.5 * (hr ** 3)), c)

def _exponential_core(h, a, c):
    a = max(float(a), 1e-12)
    return c * (1.0 - np.exp(-h / a))

def _gaussian_core(h, a, c):
    a = max(float(a), 1e-12)
    return c * (1.0 - np.exp(-(h * h) / (a * a)))

def _normalize_model(model):
    t = (str(model) or "").strip().lower()
    if t.startswith(("sph", "esf")) or "spher" in t:
        return "spherical"
    if t.startswith(("gau", "gaus")) or "gauss" in t:
        return "gaussian"
    return "exponential"

def _variogram(h, a, c0, c, model_key):
    """Return γ(h) with γ(0)=0. Nugget c0 applies only for h>0."""
    if model_key == "spherical":
        core = _spherical_core(h, a, c)
    elif model_key == "gaussian":
        core = _gaussian_core(h, a, c)
    else:
        core = _exponential_core(h, a, c)

    h = np.asarray(h)
    out = np.array(core, dtype=float, copy=True)
    if out.ndim == 0:
        return 0.0 if float(h) == 0.0 else (c0 + float(out))
    zero = (h == 0.0)
    out[~zero] = c0 + out[~zero]
    out[zero] = 0.0
    return out

def _build_system(x, y, nugget, psill, var_range, model_key):
    """Build kriging matrix K (n+1 x n+1) and return its LU factorization."""
    P = np.column_stack([x, y])
    D = cdist(P, P)
    G = _variogram(D, var_range, nugget, psill, model_key).astype(float)
    # enforce γ(0)=0 and tiny jitter on diagonal
    np.fill_diagonal(G, 0.0)
    np.fill_diagonal(G, G.diagonal() + 1e-12)

    n = x.size
    K = np.zeros((n + 1, n + 1), dtype=float)
    K[:n, :n] = G
    K[:n, n] = 1.0
    K[n, :n] = 1.0

    try:
        lu, piv = lu_factor(K, check_finite=False)
    except Exception:
        # add a bit more jitter if needed
        np.fill_diagonal(K, K.diagonal() + 1e-10)
        lu, piv = lu_factor(K, check_finite=False)
    return lu, piv

def ordinary_kriging_interpolation(
    x, y, z, x_pred, y_pred,
    nugget, psill, var_range, model,
    progress_fn=None,
    nmax=None,
    nmin=DENSE_KRIGING_NMIN,
    dense_threshold=DENSE_SAMPLE_THRESHOLD,
):
    """
    Ordinary Kriging predictions at (x_pred, y_pred).

    Parameters
    ----------
    x, y, z : 1D arrays
    x_pred, y_pred : 1D arrays
    nugget (c0), psill (c), var_range (a), model : as in UI
    progress_fn : optional callable(int_done, int_total) to report progress
    nmax : int or None
        Moving-neighborhood size. None preserves global kriging up to 500
        samples and automatically uses 64 neighbors above that threshold.

    Returns
    -------
    preds : 1D ndarray
    """
    x = np.asarray(x, dtype=float); y = np.asarray(y, dtype=float); z = np.asarray(z, dtype=float)
    xp = np.asarray(x_pred, dtype=float); yp = np.asarray(y_pred, dtype=float)

    if x.size != y.size or x.size != z.size:
        raise ValueError("x, y, z must have the same length.")
    if xp.size != yp.size:
        raise ValueError("x_pred and y_pred must have the same length.")
    if x.size < 2:
        raise ValueError("At least two points are required for kriging.")

    model_key = _normalize_model(model)
    a = float(var_range); c0 = float(nugget); c = float(psill)

    preds = np.empty(xp.size, dtype=float)
    total = xp.size
    requested_nmax = None if nmax is None else int(nmax)
    if requested_nmax is None:
        requested_nmax = DENSE_KRIGING_NMAX if x.size > int(dense_threshold) else x.size
    local_k = max(2, min(x.size, max(int(nmin), requested_nmax)))
    use_local = local_k < x.size

    if not use_local:
        # Legacy global solve: one factorization reused for every prediction.
        lu, piv = _build_system(x, y, c0, c, a, model_key)
        bytes_per_query = max(x.size * 40, 1)
        chunk = max(1, min(total, (64 * 1024 * 1024) // bytes_per_query))
        for start in range(0, total, chunk):
            end = min(total, start + chunk)
            Xblk = xp[start:end]
            Yblk = yp[start:end]
            D0 = np.hypot(x[None, :] - Xblk[:, None], y[None, :] - Yblk[:, None])
            G0 = _variogram(D0, a, c0, c, model_key)
            rhs = np.empty((G0.shape[0], G0.shape[1] + 1), dtype=float)
            rhs[:, :-1] = G0
            rhs[:, -1] = 1.0
            sol = lu_solve((lu, piv), rhs.T, check_finite=False).T
            preds[start:end] = sol[:, :-1] @ z
            if progress_fn is not None:
                progress_fn(end, total)
        return preds

    # Dense path: exact k-nearest moving neighborhoods, grouped and cached so
    # adjacent raster cells sharing a neighborhood reuse the same factorization.
    train_xy = np.column_stack((x, y))
    tree = cKDTree(train_xy)
    cache = OrderedDict()
    max_cached_systems = 256
    query_chunk = 2048
    for start in range(0, total, query_chunk):
        end = min(total, start + query_chunk)
        query_xy = np.column_stack((xp[start:end], yp[start:end]))
        try:
            _, neighbors = tree.query(query_xy, k=local_k, workers=1)
        except TypeError:  # older QGIS SciPy
            _, neighbors = tree.query(query_xy, k=local_k)
        neighbors = np.asarray(neighbors, dtype=np.int64)
        if neighbors.ndim == 1:
            neighbors = neighbors[:, None]
        # Sorting only canonicalizes the set; the kriging equations are order invariant.
        canonical = np.sort(neighbors, axis=1)
        unique_sets, inverse = np.unique(canonical, axis=0, return_inverse=True)
        block_pred = np.empty(end - start, dtype=float)

        for group_id, subset in enumerate(unique_sets):
            rows = np.flatnonzero(inverse == group_id)
            key = tuple(int(v) for v in subset)
            cached = cache.get(key)
            if cached is None:
                sx = x[subset]
                sy = y[subset]
                sz = z[subset]
                lu, piv = _build_system(sx, sy, c0, c, a, model_key)
                cached = (lu, piv, sx, sy, sz)
                cache[key] = cached
                if len(cache) > max_cached_systems:
                    cache.popitem(last=False)
            else:
                cache.move_to_end(key)
            lu, piv, sx, sy, sz = cached
            qx = query_xy[rows, 0]
            qy = query_xy[rows, 1]
            distances = np.hypot(sx[None, :] - qx[:, None], sy[None, :] - qy[:, None])
            gamma0 = _variogram(distances, a, c0, c, model_key)
            rhs = np.empty((rows.size, local_k + 1), dtype=float)
            rhs[:, :-1] = gamma0
            rhs[:, -1] = 1.0
            sol = lu_solve((lu, piv), rhs.T, check_finite=False).T
            block_pred[rows] = sol[:, :-1] @ sz

        preds[start:end] = block_pred
        if progress_fn is not None:
            progress_fn(end, total)

    return preds
