"""Constrained joint WLS fitting without an additional numerical dependency.

The nugget and partial sill are solved together at every candidate scale. A
bounded, iterative profile search refines the scale, so all three parameters
minimize the same weighted objective. Range always means the model scale a.
"""
from .localization import _ui
import numpy as np


def model_token(model):
    token = str(model or "").strip().lower()
    if token.startswith(("sph", "esf")):
        return "spherical"
    if token.startswith("gau"):
        return "gaussian"
    return "exponential"


def practical_range_factor(model):
    model_kind = model_token(model)
    return {"spherical": 1.0, "exponential": 3.0, "gaussian": np.sqrt(3.0)}[model_kind]


def practical_range(model, scale):
    """Conventional full-sill (spherical) or approximately 95% structured range."""
    return float(scale) * practical_range_factor(model)


RANGE_HELP = (
    "Range (a) is the model scale in layer CRS distance units, for both MoM and REML. "
    "Spherical: practical range = a (full sill). "
    "Exponential: practical range = 3a. Gaussian: practical range = sqrt(3)a. "
    "The latter two reach approximately 95% of the structured variance."
)


def range_summary(model, scale):
    return "Practical range: {:.6g} ({}; layer CRS units)".format(
        practical_range(model, scale),
        "full sill" if model_token(model) == "spherical" else "approx. 95% structured variance",
    )


def update_range_widgets(dialog, model, scale):
    for name in ("spinOKRange", "lblOKRange", "lblOKPracticalRange"):
        widget = getattr(dialog, name, None)
        if widget is not None:
            _ui(widget, 'setToolTip', RANGE_HELP)
    label = getattr(dialog, "lblOKPracticalRange", None)
    if label is not None:
        _ui(label, 'setText', range_summary(model, scale))


def fit_joint_wls(lags, gamma, cutoff, model, initial):
    """Return (nugget, psill, scale), plus reproducible fit diagnostics.

    Retain the existing distance weights 1/(1+h/median(h)); pair counts are not
    included. Profiled nonnegative linear WLS is exact for each scale. Search
    log(a) on a grid, then refine every bracketed local minimum by golden section.
    The range box is [0.01*minimum positive lag, 10*max(cutoff, maximum lag)].
    A tiny positive partial-sill floor preserves existing kriging/state contracts.
    """
    h, g = np.asarray(lags, float), np.asarray(gamma, float)
    valid = np.isfinite(h) & np.isfinite(g) & (h > 0) & (g >= 0)
    h, g = h[valid], g[valid]
    info = dict(method="joint_profile_wls", weights="1/(1+h/median(h))",
                range_parameterization="model_scale", bins=int(h.size))
    if not h.size:
        info.update(status="no_valid_bins", converged=False)
        return tuple(float(v) for v in initial), info
    order = np.argsort(h)
    h, g = h[order], g[order]
    lag_scale = float(np.median(h))
    w = 1.0 / (1.0 + h / lag_scale)
    wsum = float(w.sum())
    amplitude = float(np.max(g))
    extent = max(float(h[-1]), float(cutoff) if np.isfinite(cutoff) else 0.0)
    lower, upper = max(float(h[0]) * 0.01, 1e-12), max(extent * 10.0, float(h[0]))
    seed = float(initial[2])
    seed = float(np.clip(seed if np.isfinite(seed) and seed > 0 else lag_scale, lower, upper))
    if amplitude == 0.0:
        info.update(status="zero_semivariance", converged=False, weighted_sse=0.0)
        return (0.0, 1e-9, seed), info
    if h.size < 3 or np.unique(h).size < 3:
        # Three free parameters cannot be identified from fewer than three lags.
        info.update(status="insufficient_distinct_bins", converged=False)
        return tuple(float(v) for v in initial), info
    model_kind = model_token(model)
    scaled = g / amplitude
    mean_g = float(np.sum(w * scaled) / wsum)
    floor = 1e-12
    evaluations = [0]

    def evaluate(log_scale):
        evaluations[0] += 1
        a = float(np.exp(log_scale))
        t = h / a
        if model_kind == "spherical":
            t = np.minimum(t, 1.0)
            basis = 1.5 * t - 0.5 * t ** 3
        elif model_kind == "gaussian":
            basis = -np.expm1(-(t * t))
        else:
            basis = -np.expm1(-t)
        mean_b = float(np.sum(w * basis) / wsum)
        centered = basis - mean_b
        denom = float(np.sum(w * centered * centered))
        candidates = []
        if denom > np.finfo(float).eps * wsum:
            sill = float(np.sum(w * centered * (scaled - mean_g)) / denom)
            nugget = mean_g - sill * mean_b
            if nugget >= 0.0 and sill >= floor:
                candidates.append((nugget, sill))
        # Boundary optima complete the nonnegative two-coefficient WLS solution.
        denom0 = float(np.sum(w * basis * basis))
        sill0 = max(floor, float(np.sum(w * basis * scaled)) / max(denom0, 1e-300))
        candidates.extend(((0.0, sill0), (max(0.0, mean_g - floor * mean_b), floor)))
        scored = [(float(np.sum(w * (scaled - n - s * basis) ** 2)), n, s, a)
                  for n, s in candidates]
        return min(scored, key=lambda row: row[0])

    grid = np.unique(np.concatenate((np.linspace(np.log(lower), np.log(upper), 65), [np.log(seed)])))
    rows = [evaluate(value) for value in grid]
    best = min(rows, key=lambda row: row[0])
    ratio = (np.sqrt(5.0) - 1.0) / 2.0
    for i in range(1, len(grid) - 1):
        if not (rows[i][0] <= rows[i-1][0] and rows[i][0] <= rows[i+1][0]
                and (rows[i][0] < rows[i-1][0] or rows[i][0] < rows[i+1][0])):
            continue
        lo, hi = grid[i-1], grid[i+1]
        x1, x2 = hi - ratio * (hi-lo), lo + ratio * (hi-lo)
        r1, r2 = evaluate(x1), evaluate(x2)
        for _ in range(64):
            if hi-lo < 1e-10:
                break
            if r1[0] <= r2[0]:
                hi, x2, r2 = x2, x1, r1
                x1 = hi - ratio * (hi-lo)
                r1 = evaluate(x1)
            else:
                lo, x1, r1 = x1, x2, r2
                x2 = lo + ratio * (hi-lo)
                r2 = evaluate(x2)
        best = min((best, r1, r2), key=lambda row: row[0])
    sse, nugget, psill, scale = best
    on_bound = bool(np.isclose(scale, lower, rtol=1e-5, atol=0) or
                    np.isclose(scale, upper, rtol=1e-5, atol=0))
    info.update(status="range_bound" if on_bound else ("weak_structure" if psill <= 1e-10 else "fitted"),
                converged=True, range_on_bound=on_bound, range_bounds=(lower, upper),
                weighted_sse=float(sse * amplitude ** 2), evaluations=evaluations[0])
    return (float(nugget * amplitude), float(psill * amplitude), float(scale)), info
