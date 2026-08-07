# -*- coding: utf-8 -*-
"""GDAL/QGIS-tier tests for the gis/ layer: GeoTIFF round-trip, gdal-rasterize
boundary mask (polygon-hole regression on the production path), covariate
block reads, and point-layer extraction."""

import numpy as np
import pytest

pytestmark = pytest.mark.qgis

from bestfitinterpolator.core.grid import xy_to_rowcol  # noqa: E402
from bestfitinterpolator.core.types import GridSpec  # noqa: E402


@pytest.fixture
def square_grid():
    from bestfitinterpolator.gis.raster_io import grid_from_bounds

    return grid_from_bounds((0.0, 0.0, 10.0, 10.0), 1.0)


def test_write_and_read_geotiff_roundtrip(tmp_path, square_grid):
    from bestfitinterpolator.gis.raster_io import read_raster_grid, write_geotiff

    arr = np.arange(100, dtype=float).reshape(10, 10)
    arr[0, 0] = np.nan
    path = str(tmp_path / "roundtrip.tif")
    write_geotiff(arr, square_grid, path)

    back, grid = read_raster_grid(path)
    assert grid.shape == (10, 10)
    assert grid.geotransform == pytest.approx(square_grid.geotransform)
    assert np.isnan(back[0, 0])
    assert back[5, 5] == pytest.approx(55.0)


def test_write_geotiff_shape_mismatch_raises(tmp_path, square_grid):
    from bestfitinterpolator.gis.raster_io import write_geotiff

    with pytest.raises(ValueError):
        write_geotiff(np.zeros((3, 3)), square_grid, str(tmp_path / "bad.tif"))


SQUARE_WITH_HOLE_WKT = (
    "POLYGON((0 0, 10 0, 10 10, 0 10, 0 0),"
    "(4 4, 7 4, 7 7, 4 7, 4 4))"
)


def test_gdal_mask_polygon_hole_regression(square_grid):
    """Production mask path: interior ring must be EXCLUDED (legacy bug filled it)."""
    from bestfitinterpolator.gis.raster_io import build_boundary_mask

    mask = build_boundary_mask(square_grid, [SQUARE_WITH_HOLE_WKT])
    assert mask.shape == (10, 10)
    rows, cols = xy_to_rowcol(square_grid, np.array([5.5]), np.array([5.5]))
    assert not mask[rows[0], cols[0]]          # hole center excluded
    assert mask[0, 0]                          # corner cell inside
    assert int((~mask).sum()) == 9             # exactly the 3x3 hole block


def test_gdal_mask_matches_pure_python_mask(square_grid):
    from bestfitinterpolator.core.grid import polygon_mask
    from bestfitinterpolator.gis.raster_io import build_boundary_mask

    square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
    hole = [(4.0, 4.0), (7.0, 4.0), (7.0, 7.0), (4.0, 7.0), (4.0, 4.0)]
    pure = polygon_mask(square_grid, [[square, hole]])
    burned = build_boundary_mask(square_grid, [SQUARE_WITH_HOLE_WKT])
    assert (pure == burned).all()


def test_covariate_sampling_and_grid_read(tmp_path, square_grid):
    from bestfitinterpolator.gis.covariates import (
        read_covariate_grids,
        sample_covariates_at_points,
    )
    from bestfitinterpolator.gis.raster_io import write_geotiff

    # covariate = row*10 + col so values are position-checkable
    arr = (np.arange(10)[:, None] * 10 + np.arange(10)[None, :]).astype(float)
    path = str(tmp_path / "cov.tif")
    write_geotiff(arr, square_grid, path)

    pts = np.array([[0.5, 9.5], [9.5, 0.5], [50.0, 50.0]])  # last is outside
    sampled = sample_covariates_at_points([path], pts)
    assert sampled.shape == (3, 1)
    assert sampled[0, 0] == pytest.approx(0.0)     # top-left cell (row 0, col 0)
    assert sampled[1, 0] == pytest.approx(99.0)    # bottom-right cell
    assert np.isnan(sampled[2, 0])                 # out of extent

    stack = read_covariate_grids([path], square_grid)
    assert stack.shape == (10, 10, 1)
    assert np.allclose(stack[:, :, 0], arr, equal_nan=True)


def test_covariate_grid_resampled_when_misaligned(tmp_path, square_grid):
    from bestfitinterpolator.gis.covariates import read_covariate_grids
    from bestfitinterpolator.gis.raster_io import grid_from_bounds, write_geotiff

    # covariate at 2x coarser resolution over the same extent
    coarse = grid_from_bounds((0.0, 0.0, 10.0, 10.0), 2.0)
    arr = np.full((5, 5), 7.0)
    path = str(tmp_path / "coarse.tif")
    write_geotiff(arr, coarse, path)

    stack = read_covariate_grids([path], square_grid)
    assert stack.shape == (10, 10, 1)
    inner = stack[2:8, 2:8, 0]  # away from edge effects
    assert np.allclose(inner, 7.0)


def test_read_point_samples_from_memory_layer():
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsVectorLayer

    from bestfitinterpolator.core.exceptions import InvalidDataError
    from bestfitinterpolator.gis.layer_io import count_valid_samples, read_point_samples

    layer = QgsVectorLayer("Point?crs=EPSG:32722&field=zn:double&field=cov:double", "pts", "memory")
    dp = layer.dataProvider()
    rows = [(0.0, 0.0, 1.5, 10.0), (5.0, 5.0, 2.5, 20.0), (9.0, 1.0, float("nan"), 30.0)]
    for x, y, zn, cov in rows:
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
        f["zn"] = zn
        f["cov"] = cov
        dp.addFeature(f)
    layer.updateExtents()

    data = read_point_samples(layer, "zn", covariate_fields=("cov",))
    assert data.n == 2                       # NaN row dropped
    assert data.covariates.shape == (2, 1)
    assert data.covariate_names == ("cov",)
    assert data.crs_authid == "EPSG:32722"
    assert count_valid_samples(layer, "zn") == 2

    with pytest.raises(InvalidDataError):
        read_point_samples(layer, "")
