# -*- coding: utf-8 -*-
"""QGIS-tier tests for interpolation_service.generate_raster — end-to-end
fit->predict->mask->write, plus the no-partial-file-on-cancel guarantee."""

import os

import numpy as np
import pytest

pytestmark = pytest.mark.qgis

from bestfitinterpolator.core.exceptions import InvalidDataError, OperationCancelled  # noqa: E402
from bestfitinterpolator.core.types import TrainingData  # noqa: E402


SQUARE_WKT = "POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))"
HOLE_WKT = (
    "POLYGON((0 0, 10 0, 10 10, 0 10, 0 0),(4 4, 7 4, 7 7, 4 7, 4 4))"
)


def _data(n=25, seed=8):
    rng = np.random.default_rng(seed)
    xy = rng.uniform(0, 10, size=(n, 2))
    z = 5.0 + 0.3 * xy[:, 0] + rng.normal(0, 0.05, n)
    return TrainingData(xy=xy, values=z)


def _grid():
    from bestfitinterpolator.gis.raster_io import grid_from_bounds

    return grid_from_bounds((0.0, 0.0, 10.0, 10.0), 1.0)


def test_generate_idw_raster_end_to_end(tmp_path):
    from bestfitinterpolator.gis.raster_io import read_raster_grid
    from bestfitinterpolator.services.interpolation_service import generate_raster

    out = str(tmp_path / "idw.tif")
    result = generate_raster(
        _data(), "idw", {"p": 2.0, "n": 6}, _grid(), [SQUARE_WKT], out
    )
    assert os.path.isfile(out)
    assert result.stats["cells"] == 100
    arr, grid = read_raster_grid(out)
    assert grid.shape == (10, 10)
    finite = arr[np.isfinite(arr)]
    assert finite.size == 100
    assert result.stats["min"] <= finite.mean() <= result.stats["max"]


def test_generate_raster_respects_polygon_hole(tmp_path):
    from bestfitinterpolator.gis.raster_io import read_raster_grid
    from bestfitinterpolator.services.interpolation_service import generate_raster

    out = str(tmp_path / "hole.tif")
    result = generate_raster(
        _data(), "idw", {"p": 2.0, "n": 6}, _grid(), [HOLE_WKT], out
    )
    assert result.stats["cells"] == 91
    arr, _ = read_raster_grid(out)
    assert np.isnan(arr[4, 5])          # hole center row/col
    assert np.isfinite(arr[0, 0])


def test_cancel_before_write_leaves_no_file(tmp_path):
    from bestfitinterpolator.services.interpolation_service import generate_raster

    out = str(tmp_path / "cancelled.tif")
    calls = {"n": 0}

    def stop_after_fit():
        calls["n"] += 1
        return calls["n"] > 2  # allow mask + first checks, cancel before write

    with pytest.raises(OperationCancelled):
        generate_raster(
            _data(), "idw", {"p": 2.0, "n": 6}, _grid(), [SQUARE_WKT], out,
            should_stop=stop_after_fit,
        )
    assert not os.path.exists(out)      # truncated-raster regression


def test_no_overlap_raises_invalid_data(tmp_path):
    from bestfitinterpolator.gis.raster_io import grid_from_bounds
    from bestfitinterpolator.services.interpolation_service import generate_raster

    far_grid = grid_from_bounds((1000.0, 1000.0, 1010.0, 1010.0), 1.0)
    with pytest.raises(InvalidDataError, match="No grid cells"):
        generate_raster(
            _data(), "idw", {"p": 2.0, "n": 6}, far_grid, [SQUARE_WKT],
            str(tmp_path / "never.tif"),
        )
