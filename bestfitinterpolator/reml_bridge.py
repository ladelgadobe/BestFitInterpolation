# -*- coding: utf-8 -*-
"""
Bridge to integrate REML OK into the existing QGIS plugin without breaking MoM OK.
Now allows using the MoM fit as initial guess (init_from_mom) to keep consistency.
"""

from __future__ import annotations

import numpy as _np
from typing import Dict, Any
from .kriging_reml import fit_variogram_reml, ok_predict, kfold_cv_ok_reml
from .semivariogram_fit import practical_range_factor


def _to_backend_result(fit_result):
    """Adapt tagged interface scale a; preserve untagged legacy backend results."""
    result = dict(fit_result)
    if result.get("range_parameterization") == "model_scale":
        result["range"] = float(result["range"]) * practical_range_factor(result["model"])
    return result


def _init_from_mom_adapter(mom_result: Dict[str, Any]) -> Dict[str, float]:
    """Translate MoM fit dict to REML init dict."""
    if mom_result is None:
        return None
    keys = {k.lower(): k for k in mom_result.keys()}
    def get(k, default=None): return mom_result.get(keys.get(k, k), default)
    return {
        "psill": float(get("psill")),
        "range": float(get("range")),
        "nugget": float(get("nugget")),
    }


def fit_ok_reml_interface(
    sample_xyz: _np.ndarray,
    model: str = "Sph",
    trend_degree: int = 0,
    init: dict | None = None,
    bounds: dict | None = None,
    nugget_fixed: float | None = None,
    random_state: int | None = 123,
    init_from_mom: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    coords = _np.asarray(sample_xyz[:, :2], float)
    values = _np.asarray(sample_xyz[:, 2], float)
    if init is None and init_from_mom is not None:
        init = _init_from_mom_adapter(init_from_mom)
    factor = practical_range_factor(model)
    if init is not None:
        init = dict(init)
        if "range" in init:
            init["range"] = float(init["range"]) * factor
    if bounds is not None:
        bounds = dict(bounds)
        if "range" in bounds:
            bounds["range"] = tuple(float(value) * factor for value in bounds["range"])
    result = fit_variogram_reml(
        coords=coords,
        values=values,
        model=model,
        init=init,
        bounds=bounds,
        trend_degree=trend_degree,
        nugget_fixed=nugget_fixed,
        random_state=random_state,
    )
    result = dict(result)
    result["practical_range"] = float(result["range"])
    result["range"] = float(result["range"]) / factor
    result["range_parameterization"] = "model_scale"
    return result


def predict_ok_reml_interface(
    fit_result: Dict[str, Any],
    sample_xyz: _np.ndarray,
    grid_xy: _np.ndarray,
    trend_degree: int = 0,
) -> tuple[_np.ndarray, _np.ndarray | None]:
    coords = _np.asarray(sample_xyz[:, :2], float)
    values = _np.asarray(sample_xyz[:, 2], float)
    pred, var = ok_predict(coords, values, _to_backend_result(fit_result), grid_xy, return_var=True, trend_degree=trend_degree)
    return pred, var


def cv_ok_reml_interface(
    sample_xyz: _np.ndarray,
    fit_result: Dict[str, Any],
    k: int = 0,
    trend_degree: int = 0,
) -> Dict[str, Any]:
    coords = _np.asarray(sample_xyz[:, :2], float)
    values = _np.asarray(sample_xyz[:, 2], float)
    return kfold_cv_ok_reml(coords, values, _to_backend_result(fit_result), k=max(int(k), 0), trend_degree=trend_degree)
