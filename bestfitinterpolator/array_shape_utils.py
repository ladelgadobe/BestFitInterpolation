# -*- coding: utf-8 -*-
"""
array_shape_utils.py

Small NumPy shape helpers shared by interpolation and validation code.
All code comments are in English.
"""

from __future__ import annotations

from typing import Any, Tuple
import numpy as np


class InterpolationShapeError(ValueError):
    """Raised when interpolation inputs cannot be converted to safe shapes."""


def ensure_xy_2d(xy: Any, name: str = "coordinates") -> np.ndarray:
    """Ensure coordinates are a 2D array with shape (n_points, 2)."""
    xy = np.asarray(xy, dtype=float)

    if xy.ndim == 1:
        if xy.size == 2:
            xy = xy.reshape(1, 2)
        else:
            raise InterpolationShapeError(
                f"{name} must have shape (n_points, 2). Got shape {xy.shape}."
            )

    if xy.ndim != 2 or xy.shape[1] != 2:
        raise InterpolationShapeError(
            f"{name} must have shape (n_points, 2). Got shape {xy.shape}."
        )

    return xy


def ensure_values_1d(values: Any, name: str = "values") -> np.ndarray:
    """Ensure target values are a non-empty 1D numeric array."""
    values = np.asarray(values, dtype=float).ravel()

    if values.size == 0:
        raise InterpolationShapeError(f"{name} is empty.")

    return values


def ensure_xy_components(x: Any, y: Any, name: str = "coordinates") -> np.ndarray:
    """Build a safe (n_points, 2) coordinate array from x and y components."""
    x_arr = np.asarray(x, dtype=float).ravel()
    y_arr = np.asarray(y, dtype=float).ravel()
    if x_arr.size != y_arr.size:
        raise InterpolationShapeError(
            f"{name} x and y must have the same length. Got {x_arr.size} and {y_arr.size}."
        )
    if x_arr.size == 0:
        raise InterpolationShapeError(f"{name} is empty.")
    return ensure_xy_2d(np.column_stack([x_arr, y_arr]), name)


def split_xy(xy: Any, name: str = "coordinates") -> Tuple[np.ndarray, np.ndarray]:
    """Return x and y 1D arrays from a safe coordinate matrix."""
    xy = ensure_xy_2d(xy, name)
    return xy[:, 0], xy[:, 1]


def finite_training_arrays(x: Any, y: Any, values: Any) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return finite x, y, values arrays after shared shape validation."""
    xy = ensure_xy_components(x, y, "training coordinates")
    values_1d = ensure_values_1d(values, "training values")
    if xy.shape[0] != values_1d.size:
        raise InterpolationShapeError(
            "training coordinates and values must have the same length. "
            f"Got {xy.shape[0]} coordinates and {values_1d.size} values."
        )
    mask = np.isfinite(xy[:, 0]) & np.isfinite(xy[:, 1]) & np.isfinite(values_1d)
    xy = xy[mask]
    values_1d = values_1d[mask]
    if values_1d.size == 0:
        raise InterpolationShapeError("training values are empty after filtering invalid rows.")
    return xy[:, 0], xy[:, 1], values_1d


def format_shape_error(exc: Exception, train_xy: Any = None, query_xy: Any = None, values: Any = None) -> str:
    """Build a clear user-facing shape error message."""
    def _shape(value: Any) -> str:
        try:
            return str(np.asarray(value).shape)
        except Exception:
            return "unknown"

    details = []
    if train_xy is not None:
        details.append(f"training coordinates shape = {_shape(train_xy)}")
    if query_xy is not None:
        details.append(f"prediction coordinates shape = {_shape(query_xy)}")
    if values is not None:
        details.append(f"training values shape = {_shape(values)}")
    detail_text = "; ".join(details) if details else str(exc)
    return (
        "Interpolation failed because the input coordinates were not correctly shaped.\n"
        "Please check that the layer contains valid point geometries and numeric target values.\n"
        f"Details: {detail_text}"
    )
