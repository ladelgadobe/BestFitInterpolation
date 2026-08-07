# -*- coding: utf-8 -*-
"""Pure grid math: output-grid construction and point-in-polygon masking.

This is the headless (no GDAL) mask path used by tests and as a fallback;
the production mask in gis/raster_io.py rasterizes with GDAL. Unlike the
legacy code — which OR-ed every ring, filling polygon holes — interior rings
are subtracted here.
"""

from __future__ import annotations

import numpy as np

from .types import GridSpec


def compute_grid(xmin, ymin, xmax, ymax, pixel_size, crs_wkt="") -> GridSpec:
    """North-up grid covering the extent. Column/row counts and cell-center
    convention match the legacy _init_grid_and_mask (ceil, centers at +0.5px,
    origin at the extent's top-left)."""
    pixel_size = float(pixel_size)
    if not np.isfinite(pixel_size) or pixel_size <= 0:
        raise ValueError("Pixel size must be a positive number.")
    n_cols = int(np.ceil((xmax - xmin) / pixel_size))
    n_rows = int(np.ceil((ymax - ymin) / pixel_size))
    if n_cols < 1 or n_rows < 1:
        raise ValueError("Invalid pixel size or polygon extent is too small.")
    geotransform = (float(xmin), pixel_size, 0.0, float(ymax), 0.0, -pixel_size)
    return GridSpec(geotransform=geotransform, shape=(n_rows, n_cols), crs_wkt=crs_wkt)


def xy_to_rowcol(grid: GridSpec, x, y):
    """Vectorized inverse geotransform (north-up). Returns (rows, cols)."""
    gt = grid.geotransform
    cols = np.floor((np.asarray(x, dtype=float) - gt[0]) / gt[1]).astype(int)
    rows = np.floor((np.asarray(y, dtype=float) - gt[3]) / gt[5]).astype(int)
    return rows, cols


def polygon_mask(grid: GridSpec, polygons) -> np.ndarray:
    """Boolean (rows, cols) mask of cell centers inside the polygons.

    ``polygons`` is a sequence of parts, each part a sequence of rings, each
    ring an (m, 2) array-like of vertices; ring 0 is the exterior, further
    rings are holes. A point is inside when it falls in any part's exterior
    and in none of that part's holes — the polygon-hole fix over the legacy
    OR-all-rings behavior.
    """
    from matplotlib.path import Path  # no Qt backend involved

    xs, ys = grid.cell_centers()
    pts = np.column_stack([xs, ys])
    inside = np.zeros(pts.shape[0], dtype=bool)
    for part in polygons:
        rings = [np.asarray(r, dtype=float) for r in part if len(r) >= 3]
        if not rings:
            continue
        in_part = Path(rings[0]).contains_points(pts)
        for hole in rings[1:]:
            in_part &= ~Path(hole).contains_points(pts)
        inside |= in_part
    return inside.reshape(grid.shape)


def values_to_raster(grid: GridSpec, flat_indices, values, fill=np.nan) -> np.ndarray:
    """Scatter predicted values (aligned with ``flat_indices`` into the
    row-major flattened grid) back into a (rows, cols) array — replaces the
    legacy per-cell Python loops."""
    out = np.full(grid.n_rows * grid.n_cols, fill, dtype=float)
    out[np.asarray(flat_indices, dtype=int)] = np.asarray(values, dtype=float)
    return out.reshape(grid.shape)
