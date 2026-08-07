# -*- coding: utf-8 -*-
"""Vector-layer extraction — the single point-layer → numpy implementation
(formerly duplicated in five controllers). Runs on the UI thread; the
returned plain-numpy TrainingData is what crosses into workers."""

from __future__ import annotations

import numpy as np

from ..core.exceptions import InvalidDataError
from ..core.types import TrainingData
from ..logger import get_logger

logger = get_logger(__name__)


def read_point_samples(layer, field_name: str, covariate_fields=()) -> TrainingData:
    """Extract finite (x, y, value[, covariates]) rows from a point layer.

    Non-point geometries, empty geometries and non-numeric / non-finite
    values are skipped (legacy behavior). Raises InvalidDataError when
    nothing valid remains.
    """
    if layer is None:
        raise InvalidDataError("No point layer selected.")
    if not field_name:
        raise InvalidDataError("No variable field selected.")

    covariate_fields = tuple(covariate_fields or ())
    xs, ys, vals = [], [], []
    covs = [[] for _ in covariate_fields]

    for feat in layer.getFeatures():
        geom = feat.geometry()
        if geom is None or geom.isEmpty():
            continue
        try:
            pt = geom.asPoint()
        except Exception:
            continue
        try:
            value = float(feat[field_name])
        except Exception:
            continue
        if not np.isfinite(value):
            continue
        row_covs = []
        ok = True
        for name in covariate_fields:
            try:
                c = float(feat[name])
            except Exception:
                ok = False
                break
            if not np.isfinite(c):
                ok = False
                break
            row_covs.append(c)
        if not ok:
            continue
        xs.append(pt.x())
        ys.append(pt.y())
        vals.append(value)
        for i, c in enumerate(row_covs):
            covs[i].append(c)

    if not vals:
        raise InvalidDataError(
            "No valid point samples found: check the layer geometry and that "
            f"'{field_name}' holds numeric values."
        )

    xy = np.column_stack([np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)])
    covariates = (
        np.column_stack([np.asarray(c, dtype=float) for c in covs])
        if covariate_fields
        else None
    )
    try:
        crs_authid = layer.crs().authid()
    except Exception:
        crs_authid = None
    return TrainingData(
        xy=xy,
        values=np.asarray(vals, dtype=float),
        covariates=covariates,
        covariate_names=covariate_fields,
        crs_authid=crs_authid,
    )


def count_valid_samples(layer, field_name: str) -> int:
    """Count finite numeric values in a point layer field (legacy verbatim)."""
    if layer is None or not field_name:
        return 0
    count = 0
    try:
        for feat in layer.getFeatures():
            try:
                value = float(feat[field_name])
            except Exception:  # nosec B112
                continue
            if value == value:
                count += 1
    except Exception:
        logger.debug("count_valid_samples failed", exc_info=True)
        return 0
    return count


def extract_boundary_wkts(polygon_layer):
    """Boundary geometries as WKT strings + extent + CRS WKT — the plain-data
    package a worker can rasterize without touching the layer."""
    if polygon_layer is None:
        raise InvalidDataError("No boundary polygon layer selected.")
    wkts = []
    for feat in polygon_layer.getFeatures():
        geom = feat.geometry()
        if geom is None or geom.isEmpty():
            continue
        wkts.append(geom.asWkt())
    if not wkts:
        raise InvalidDataError("The boundary layer contains no valid polygons.")
    extent = polygon_layer.extent()
    bounds = (extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum())
    try:
        crs_wkt = polygon_layer.crs().toWkt()
    except Exception:
        crs_wkt = ""
    return wkts, bounds, crs_wkt


def extract_boundary_rings(polygon_layer):
    """All rings as (m, 2) coordinate lists — plain data for plotting."""
    import numpy as np  # local alias for clarity; np already imported

    rings = []
    if polygon_layer is None:
        return rings
    for feat in polygon_layer.getFeatures():
        geom = feat.geometry()
        if geom is None or geom.isEmpty():
            continue
        polygons = geom.asMultiPolygon() if geom.isMultipart() else [geom.asPolygon()]
        for part in polygons:
            for ring in part:
                coords = np.array([(pt.x(), pt.y()) for pt in ring], dtype=float)
                if coords.shape[0] >= 3:
                    rings.append(coords)
    return rings


def same_layer(layer_a, layer_b) -> bool:
    """Safely compare two QGIS layers (legacy verbatim)."""
    if layer_a is None or layer_b is None:
        return False
    try:
        return layer_a.id() == layer_b.id()
    except Exception:
        return layer_a is layer_b
