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
from scipy.spatial.distance import cdist
from scipy.linalg import lu_factor, lu_solve

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
    progress_fn=None
):
    """
    Ordinary Kriging predictions at (x_pred, y_pred).

    Parameters
    ----------
    x, y, z : 1D arrays
    x_pred, y_pred : 1D arrays
    nugget (c0), psill (c), var_range (a), model : as in UI
    progress_fn : optional callable(int_done, int_total) to report progress

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

    # Factorize system once
    lu, piv = _build_system(x, y, c0, c, a, model_key)

    preds = np.empty(xp.size, dtype=float)
    total = xp.size
    # Compute distances to all data for all predictions in chunks to save memory
    chunk = 5000 if total > 20000 else 2000
    done = 0
    for start in range(0, total, chunk):
        end = min(total, start + chunk)
        Xblk = xp[start:end]; Yblk = yp[start:end]
        # vectorized distance block (data vs. block)
        D0 = np.hypot(x[None, :] - Xblk[:, None], y[None, :] - Yblk[:, None])  # (m, n)
        G0 = _variogram(D0, a, c0, c, model_key)                                # (m, n)
        # Solve for each row in the block
        rhs = np.empty((G0.shape[0], G0.shape[1] + 1), dtype=float)
        rhs[:, :-1] = G0
        rhs[:, -1]  = 1.0
        # lu_solve solves A x = b for each column of b; transpose to use rows
        sol = lu_solve((lu, piv), rhs.T, check_finite=False).T
        w = sol[:, :-1]
        preds[start:end] = (w @ z)

        done = end
        if progress_fn is not None:
            try:
                progress_fn(done, total)
            except Exception:  # nosec B110
                pass

    return preds
