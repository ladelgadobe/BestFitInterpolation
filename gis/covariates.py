# -*- coding: utf-8 -*-
"""Covariate raster access — block reads replacing the legacy per-grid-cell
``provider.sample()`` loop (millions of provider round-trips plus a
processEvents() pump per cell, the single worst hotspot in the old code).

Workers pass raster *paths*; each function opens its own GDAL dataset handle
(thread-safe) and reads whole arrays once.
"""

from __future__ import annotations

import numpy as np
from osgeo import gdal

from ..core.types import GridSpec


def _open(path):
    ds = gdal.Open(path)
    if ds is None:
        raise RuntimeError(f"Could not open covariate raster: {path}")
    return ds


def _read_band_nan(ds):
    band = ds.GetRasterBand(1)
    arr = band.ReadAsArray().astype(float)
    nodata = band.GetNoDataValue()
    if nodata is not None and not np.isnan(nodata):
        arr[arr == nodata] = np.nan
    return arr


def sample_covariates_at_points(raster_paths, xy) -> np.ndarray:
    """(n, k) covariate values at point coordinates. One ReadAsArray per
    raster; vectorized inverse geotransform; out-of-extent points get NaN."""
    xy = np.asarray(xy, dtype=float)
    n = xy.shape[0]
    out = np.full((n, len(raster_paths)), np.nan, dtype=float)
    for k, path in enumerate(raster_paths):
        ds = _open(path)
        try:
            gt = ds.GetGeoTransform()
            arr = _read_band_nan(ds)
            cols = np.floor((xy[:, 0] - gt[0]) / gt[1]).astype(int)
            rows = np.floor((xy[:, 1] - gt[3]) / gt[5]).astype(int)
            valid = (rows >= 0) & (rows < arr.shape[0]) & (cols >= 0) & (cols < arr.shape[1])
            out[valid, k] = arr[rows[valid], cols[valid]]
        finally:
            ds = None
    return out


def read_covariate_grids(raster_paths, grid: GridSpec) -> np.ndarray:
    """(rows, cols, k) covariate stack aligned to the output grid. Rasters on
    a different grid are resampled (bilinear) with an in-memory gdal.Warp."""
    rows, cols = grid.n_rows, grid.n_cols
    out = np.full((rows, cols, len(raster_paths)), np.nan, dtype=float)
    gt = grid.geotransform
    bounds = (
        gt[0],                      # xmin
        gt[3] + gt[5] * rows,       # ymin
        gt[0] + gt[1] * cols,       # xmax
        gt[3],                      # ymax
    )
    for k, path in enumerate(raster_paths):
        ds = _open(path)
        try:
            same_grid = (
                np.allclose(ds.GetGeoTransform(), gt)
                and ds.RasterYSize == rows
                and ds.RasterXSize == cols
            )
            if not same_grid:
                warp_opts = gdal.WarpOptions(
                    format="MEM",
                    outputBounds=bounds,
                    xRes=abs(gt[1]),
                    yRes=abs(gt[5]),
                    dstSRS=grid.crs_wkt or None,
                    resampleAlg="bilinear",
                )
                warped = gdal.Warp("", ds, options=warp_opts)
                if warped is None:
                    raise RuntimeError(f"Could not align covariate raster: {path}")
                ds = None
                ds = warped
            arr = _read_band_nan(ds)
            # Warp output can be off by a row/col on edge-snapping extents.
            r = min(rows, arr.shape[0])
            c = min(cols, arr.shape[1])
            out[:r, :c, k] = arr[:r, :c]
        finally:
            ds = None
    return out


def sample_covariates_on_grid(raster_paths, grid: GridSpec, flat_indices) -> np.ndarray:
    """(m, k) covariates at the given row-major flattened grid indices."""
    stack = read_covariate_grids(raster_paths, grid)
    flat = stack.reshape(-1, stack.shape[2])
    return flat[np.asarray(flat_indices, dtype=int)]
