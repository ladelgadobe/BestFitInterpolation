# -*- coding: utf-8 -*-
"""Raster IO — grid construction, boundary rasterization and GeoTIFF writing
(the single implementation of what five controllers each hand-rolled).

The boundary mask burns cells whose CENTER falls inside the polygons — the
same convention as the legacy matplotlib.path test — but GDAL honors interior
rings, fixing the legacy bug that filled polygon holes.
"""

from __future__ import annotations

import numpy as np
from osgeo import gdal, ogr, osr

from ..core.grid import compute_grid as _compute_grid_pure
from ..core.types import GridSpec
from ..logger import get_logger

logger = get_logger(__name__)


def grid_from_bounds(bounds, pixel_size, crs_wkt="") -> GridSpec:
    """GridSpec over (xmin, ymin, xmax, ymax) with the legacy cell convention."""
    xmin, ymin, xmax, ymax = bounds
    return _compute_grid_pure(xmin, ymin, xmax, ymax, pixel_size, crs_wkt=crs_wkt)


def grid_from_layer(polygon_layer, pixel_size) -> GridSpec:
    """GridSpec from a polygon layer's extent (legacy _init_grid_and_mask
    extent semantics)."""
    extent = polygon_layer.extent()
    bounds = (extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum())
    try:
        crs_wkt = polygon_layer.crs().toWkt()
    except Exception:
        crs_wkt = ""
    return grid_from_bounds(bounds, pixel_size, crs_wkt=crs_wkt)


def build_boundary_mask(grid: GridSpec, wkts) -> np.ndarray:
    """Boolean (rows, cols) inside-boundary mask via gdal.RasterizeLayer.

    ``wkts`` is the list of polygon WKT strings from
    layer_io.extract_boundary_wkts — plain data, safe across threads.
    """
    mem_ds = None
    ras_ds = None
    try:
        srs = None
        if grid.crs_wkt:
            srs = osr.SpatialReference()
            srs.ImportFromWkt(grid.crs_wkt)

        drv = ogr.GetDriverByName("MEM") or ogr.GetDriverByName("Memory")
        mem_ds = drv.CreateDataSource("boundary")
        layer = mem_ds.CreateLayer("boundary", srs=srs, geom_type=ogr.wkbMultiPolygon)
        for wkt in wkts:
            geom = ogr.CreateGeometryFromWkt(wkt)
            if geom is None:
                continue
            feature = ogr.Feature(layer.GetLayerDefn())
            feature.SetGeometry(geom)
            layer.CreateFeature(feature)
            feature = None

        ras_drv = gdal.GetDriverByName("MEM")
        ras_ds = ras_drv.Create("", grid.n_cols, grid.n_rows, 1, gdal.GDT_Byte)
        ras_ds.SetGeoTransform(grid.geotransform)
        if grid.crs_wkt:
            ras_ds.SetProjection(grid.crs_wkt)
        band = ras_ds.GetRasterBand(1)
        band.Fill(0)
        gdal.RasterizeLayer(ras_ds, [1], layer, burn_values=[1])
        mask = band.ReadAsArray().astype(bool)
        return mask
    finally:
        ras_ds = None
        mem_ds = None


def write_geotiff(array2d, grid: GridSpec, out_path, nodata_value=None) -> str:
    """Single-band Float32 GeoTIFF (LZW, tiled). Default nodata is NaN —
    the legacy convention for the plugin's interpolation outputs."""
    array2d = np.asarray(array2d, dtype=np.float32)
    rows, cols = array2d.shape
    if (rows, cols) != (grid.n_rows, grid.n_cols):
        raise ValueError(
            f"Array shape {(rows, cols)} does not match grid {grid.shape}."
        )
    driver = gdal.GetDriverByName("GTiff")
    ds = driver.Create(
        out_path, cols, rows, 1, gdal.GDT_Float32,
        options=["COMPRESS=LZW", "TILED=YES"],
    )
    if ds is None:
        raise RuntimeError("Could not create the output GeoTIFF.")
    ds.SetGeoTransform(grid.geotransform)
    if grid.crs_wkt:
        srs = osr.SpatialReference()
        srs.ImportFromWkt(grid.crs_wkt)
        ds.SetProjection(srs.ExportToWkt())

    band = ds.GetRasterBand(1)
    band.WriteArray(array2d)
    band.SetNoDataValue(float("nan") if nodata_value is None else float(nodata_value))
    band.FlushCache()
    ds.FlushCache()
    ds = None
    return out_path


def read_raster_grid(path):
    """(array float64 with nodata→NaN, GridSpec) from a single-band raster."""
    ds = gdal.Open(path)
    if ds is None:
        raise RuntimeError(f"Could not open raster: {path}")
    try:
        band = ds.GetRasterBand(1)
        arr = band.ReadAsArray().astype(float)
        nodata = band.GetNoDataValue()
        if nodata is not None and not np.isnan(nodata):
            arr[arr == nodata] = np.nan
        grid = GridSpec(
            geotransform=tuple(ds.GetGeoTransform()),
            shape=(ds.RasterYSize, ds.RasterXSize),
            crs_wkt=ds.GetProjection() or "",
        )
        return arr, grid
    finally:
        ds = None
