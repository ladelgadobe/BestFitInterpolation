"""Linear universal kriging, using the same exact-data convention as ordinary.

The nugget contributes at positive separation, gamma(0)=0. Variance refers to
the sampled variable at point support, conditional on fixed covariance and drift
basis. It includes drift coefficient estimation, not variogram-parameter error.
"""
from collections import OrderedDict
import numpy as np
from scipy.linalg import lu_factor, lu_solve
from scipy.spatial import cKDTree
from scipy.spatial.distance import cdist
from .kriging_ordinary import _variogram, _normalize_model
from .performance_policy import DENSE_KRIGING_NMAX, DENSE_KRIGING_NMIN, DENSE_SAMPLE_THRESHOLD


def linear_design(coords, origin=None, scale=None):
    coords = np.asarray(coords, float)
    origin = coords.mean(axis=0) if origin is None else np.asarray(origin, float)
    scale = np.maximum(np.std(coords, axis=0), 1.0) if scale is None else np.asarray(scale, float)
    return np.column_stack((np.ones(len(coords)), (coords - origin) / scale)), origin, scale


def detrend_linear(x, y, z):
    matrix, origin, scale = linear_design(np.column_stack((x, y)))
    if np.linalg.matrix_rank(matrix) < 3:
        raise ValueError("Universal Kriging needs non-collinear locations to estimate a linear spatial trend.")
    beta = np.linalg.lstsq(matrix, np.asarray(z, float), rcond=None)[0]
    return np.asarray(z, float) - matrix @ beta, beta, origin, scale


def universal_kriging_interpolation(x, y, z, x_pred, y_pred, nugget, psill, var_range,
                                  model, progress_fn=None, nmax=None,
                                  nmin=DENSE_KRIGING_NMIN, dense_threshold=DENSE_SAMPLE_THRESHOLD,
                                  return_variance=False, trend_degree=1):
    if int(trend_degree) != 1:
        raise ValueError("This version supports a linear Universal Kriging trend (degree 1).")
    xy = np.column_stack((x, y)).astype(float)
    query = np.column_stack((x_pred, y_pred)).astype(float)
    values = np.asarray(z, float).ravel()
    if len(xy) != len(values) or len(values) < 4:
        raise ValueError("Universal Kriging requires at least four valid observations.")
    if not (np.isfinite(xy).all() and np.isfinite(query).all() and np.isfinite(values).all()):
        raise ValueError("Kriging coordinates and values must be finite.")
    design, origin, scale = linear_design(xy)
    if np.linalg.matrix_rank(design) < 3:
        raise ValueError("Universal Kriging needs non-collinear sample locations.")
    target_design, _, _ = linear_design(query, origin, scale)
    token = _normalize_model(model)
    k = len(values) if nmax is None and len(values) <= dense_threshold else (DENSE_KRIGING_NMAX if nmax is None else int(nmax))
    k = min(len(values), max(4, int(nmin), k))
    tree = cKDTree(xy) if k < len(values) else None
    cache = OrderedDict()
    prediction = np.empty(len(query), float)
    variance = np.empty(len(query), float) if return_variance else None
    for start in range(0, len(query), 1024):
        stop = min(start + 1024, len(query))
        if tree is None:
            sets = np.arange(len(values), dtype=int)[None, :]
            inverse = np.zeros(stop - start, dtype=int)
        else:
            _, neighbors = tree.query(query[start:stop], k=k)
            sets, inverse = np.unique(np.sort(neighbors, axis=1), axis=0, return_inverse=True)
        for group, subset in enumerate(sets):
            rows = start + np.flatnonzero(inverse == group)
            # A local neighborhood may be collinear even when the full design is
            # estimable. Use the global set explicitly in that exceptional case.
            if np.linalg.matrix_rank(design[subset]) < 3:
                if len(values) <= dense_threshold:
                    subset = np.arange(len(values), dtype=int)
                else:
                    for expanded in (min(len(values), k * 2), min(len(values), k * 4), min(len(values), 512)):
                        _, expanded_indices = tree.query(query[rows[0]], k=expanded)
                        subset = np.sort(np.atleast_1d(expanded_indices))
                        if np.linalg.matrix_rank(design[subset]) == 3:
                            break
                    if np.linalg.matrix_rank(design[subset]) < 3:
                        raise ValueError("The local Universal Kriging neighborhood is collinear. A two-dimensional sampling pattern is required.")
            key = tuple(subset)
            cached = cache.get(key)
            if cached is None:
                gamma = _variogram(cdist(xy[subset], xy[subset]), var_range, nugget, psill, token)
                np.fill_diagonal(gamma, 1e-12)
                basis = design[subset]
                system = np.block([[gamma, basis], [basis.T, np.zeros((3, 3))]])
                cached = lu_factor(system, check_finite=False)
                cache[key] = cached
                if len(cache) > 256:
                    cache.popitem(last=False)
            else:
                cache.move_to_end(key)
            gamma0 = _variogram(cdist(query[rows], xy[subset]), var_range, nugget, psill, token)
            rhs = np.column_stack((gamma0, target_design[rows]))
            solution = lu_solve(cached, rhs.T, check_finite=False).T
            prediction[rows] = solution[:, :len(subset)] @ values[subset]
            if return_variance:
                variance[rows] = np.maximum(np.sum(solution * rhs, axis=1), 0.0)
        if progress_fn:
            progress_fn(stop, len(query))
    if not np.isfinite(prediction).all() or (return_variance and not np.isfinite(variance).all()):
        raise ValueError("Kriging system is singular; check duplicate locations and model parameters.")
    return (prediction, variance) if return_variance else prediction
