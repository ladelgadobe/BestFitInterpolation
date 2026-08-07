# -*- coding: utf-8 -*-
"""Compatibility shim — the helpers moved to core/arrays.py.

Kept only until the legacy modules that import this name are deleted by the
restructure (phase 8)."""

from .core.arrays import (  # noqa: F401
    InterpolationShapeError,
    ensure_values_1d,
    ensure_xy_2d,
    ensure_xy_components,
    finite_training_arrays,
    format_shape_error,
    split_xy,
)
