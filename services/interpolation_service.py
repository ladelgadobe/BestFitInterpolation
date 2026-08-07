# -*- coding: utf-8 -*-
"""Raster generation: fit -> predict masked grid -> single GeoTIFF write.

The full masked array is computed in memory and written exactly once at the
end, so a cancellation can never leave a truncated raster on disk (the legacy
ML grid loop broke out on cancel and kept building from partial rows)."""

from __future__ import annotations

import numpy as np

from ..core.exceptions import InvalidDataError, OperationCancelled
from ..core.grid import values_to_raster
from ..core.methods import get_method
from ..core.types import GridSpec, RasterResult, TrainingData
from ..gis.covariates import sample_covariates_on_grid
from ..gis.raster_io import build_boundary_mask, write_geotiff
from ..logger import get_logger

logger = get_logger(__name__)


def generate_raster(
    data: TrainingData,
    method_key: str,
    params: dict,
    grid: GridSpec,
    boundary_wkts,
    out_path: str,
    *,
    covariate_paths=(),
    progress=None,
    status=None,
    should_stop=None,
) -> RasterResult:
    """Interpolate over the inside-boundary cells of ``grid`` and write a
    GeoTIFF at ``out_path``. All inputs are plain data (thread-safe)."""
    method = get_method(method_key)
    method.validate(data)

    def _say(text):
        if status is not None:
            status(text)

    def _check():
        if should_stop is not None and should_stop():
            raise OperationCancelled()

    _say("Building interpolation grid…")
    mask = build_boundary_mask(grid, boundary_wkts)
    flat_indices = np.flatnonzero(mask.ravel())
    if flat_indices.size == 0:
        raise InvalidDataError(
            "No grid cells fall inside the boundary polygon. "
            "Check the CRS and the pixel size."
        )
    _check()

    xs, ys = grid.cell_centers()
    query_xy = np.column_stack([xs[flat_indices], ys[flat_indices]])

    query_cov = None
    if covariate_paths:
        _say("Sampling covariate rasters…")
        query_cov = sample_covariates_on_grid(covariate_paths, grid, flat_indices)
        _check()

    _say(f"Fitting {method.info.label}…")
    fit = method.fit(data, params=params, should_stop=should_stop)
    _check()

    _say(f"Predicting {flat_indices.size} cells…")
    preds = fit.model.predict(
        query_xy, covariates=query_cov, progress=progress, should_stop=should_stop
    )
    _check()

    raster = values_to_raster(grid, flat_indices, preds)

    _say("Writing GeoTIFF…")
    write_geotiff(raster, grid, out_path)

    finite = preds[np.isfinite(preds)]
    stats = {
        "min": float(np.min(finite)) if finite.size else float("nan"),
        "max": float(np.max(finite)) if finite.size else float("nan"),
        "mean": float(np.mean(finite)) if finite.size else float("nan"),
        "cells": int(flat_indices.size),
    }
    return RasterResult(
        path=out_path,
        grid=grid,
        method_key=method_key,
        params=fit.params,
        stats=stats,
    )
