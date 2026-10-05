# -*- coding: utf-8 -*-
"""Memory-bounded regular-grid construction helpers."""

from __future__ import annotations

import numpy as np


def build_inside_grid_points(x_coords, y_coords, mask_fn, row_block=128):
    """Return inside centers and flat raster indices without a full-grid matrix."""
    x_coords = np.asarray(x_coords, dtype=float).ravel()
    y_coords = np.asarray(y_coords, dtype=float).ravel()
    n_cols = x_coords.size
    point_parts = []
    index_parts = []
    for row_start in range(0, y_coords.size, max(1, int(row_block))):
        row_end = min(y_coords.size, row_start + max(1, int(row_block)))
        xx, yy = np.meshgrid(x_coords, y_coords[row_start:row_end])
        points = np.column_stack((xx.ravel(), yy.ravel()))
        mask = np.asarray(mask_fn(points), dtype=bool).ravel()
        if mask.size != points.shape[0]:
            raise ValueError("Polygon mask size does not match the grid block.")
        local = np.flatnonzero(mask)
        if local.size:
            point_parts.append(points[local])
            index_parts.append(row_start * n_cols + local)
    if not point_parts:
        return np.empty((0, 2), dtype=float), np.array([], dtype=np.int64)
    return np.vstack(point_parts), np.concatenate(index_parts).astype(np.int64, copy=False)
