# -*- coding: utf-8 -*-
"""Behavioral tests for core.grid — including the polygon-hole regression:
the legacy mask OR-ed every ring, so interior rings (holes) were filled."""

import numpy as np
import pytest

from bestfitinterpolator.core.grid import (
    compute_grid,
    polygon_mask,
    values_to_raster,
    xy_to_rowcol,
)


def test_compute_grid_dimensions_match_legacy_ceil():
    grid = compute_grid(0, 0, 10, 5, pixel_size=1.0)
    assert grid.shape == (5, 10)
    grid = compute_grid(0, 0, 10.2, 5.2, pixel_size=1.0)  # ceil
    assert grid.shape == (6, 11)


def test_compute_grid_rejects_bad_pixel_size():
    with pytest.raises(ValueError):
        compute_grid(0, 0, 10, 10, pixel_size=0)
    with pytest.raises(ValueError):
        compute_grid(0, 0, 0, 0, pixel_size=1.0)  # empty extent -> zero cols/rows


def test_cell_centers_follow_legacy_convention():
    grid = compute_grid(0, 0, 4, 2, pixel_size=1.0)
    xs, ys = grid.cell_centers()
    assert xs[:4].tolist() == [0.5, 1.5, 2.5, 3.5]     # xmin + px*(c+0.5)
    assert ys[0] == pytest.approx(1.5)                  # ymax - px*(r+0.5)
    assert ys[-1] == pytest.approx(0.5)


def test_xy_to_rowcol_roundtrip():
    grid = compute_grid(100, 200, 110, 210, pixel_size=1.0)
    xs, ys = grid.cell_centers()
    rows, cols = xy_to_rowcol(grid, xs, ys)
    flat = rows * grid.n_cols + cols
    assert flat.tolist() == list(range(grid.n_rows * grid.n_cols))


SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
HOLE = [(4.0, 4.0), (7.0, 4.0), (7.0, 7.0), (4.0, 7.0), (4.0, 4.0)]


def test_polygon_mask_square():
    grid = compute_grid(0, 0, 10, 10, pixel_size=1.0)
    mask = polygon_mask(grid, [[SQUARE]])
    assert mask.shape == (10, 10)
    assert mask.all()


def test_polygon_hole_regression_cells_in_hole_are_masked_out():
    grid = compute_grid(0, 0, 10, 10, pixel_size=1.0)
    mask = polygon_mask(grid, [[SQUARE, HOLE]])
    # center of the hole (5.5, 5.5) -> row 4, col 5 must be OUTSIDE
    rows, cols = xy_to_rowcol(grid, np.array([5.5]), np.array([5.5]))
    assert not mask[rows[0], cols[0]]
    # a corner cell stays inside
    assert mask[0, 0]
    # exactly the 3x3 block of hole-interior centers is excluded
    assert int((~mask).sum()) == 9


def test_polygon_mask_multipart():
    left = [(0.0, 0.0), (3.0, 0.0), (3.0, 3.0), (0.0, 3.0), (0.0, 0.0)]
    right = [(7.0, 7.0), (10.0, 7.0), (10.0, 10.0), (7.0, 10.0), (7.0, 7.0)]
    grid = compute_grid(0, 0, 10, 10, pixel_size=1.0)
    mask = polygon_mask(grid, [[left], [right]])
    assert int(mask.sum()) == 18


def test_values_to_raster_scatter():
    grid = compute_grid(0, 0, 3, 2, pixel_size=1.0)
    out = values_to_raster(grid, [0, 4], [7.0, 9.0])
    assert out.shape == (2, 3)
    assert out[0, 0] == 7.0
    assert out[1, 1] == 9.0
    assert np.isnan(out).sum() == 4
