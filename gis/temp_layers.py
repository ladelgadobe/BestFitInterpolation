# -*- coding: utf-8 -*-
"""Output-layer helpers — the single BestFitTemporaryRasterLayer (formerly
defined in four modules) and the add-to-project flow."""

from __future__ import annotations

import os
import tempfile

from qgis.core import QgsProject, QgsRasterLayer

from ..logger import get_logger

logger = get_logger(__name__)


class BestFitTemporaryRasterLayer(QgsRasterLayer):
    """Raster layer wrapper so QGIS identifies plugin temp outputs."""

    def isTemporary(self):
        return True


def is_temporary_output_path(path) -> bool:
    """True when an output path is inside the system temp folder."""
    try:
        tmp_dir = os.path.abspath(tempfile.gettempdir())
        out_path = os.path.abspath(str(path))
        return os.path.commonpath([tmp_dir, out_path]) == tmp_dir
    except Exception:
        return False


def create_output_raster_layer(raster_path, layer_name, *, exported: bool):
    """QgsRasterLayer (or the temporary wrapper when not exported)."""
    is_temporary = (not exported) or is_temporary_output_path(raster_path)
    layer_cls = BestFitTemporaryRasterLayer if is_temporary else QgsRasterLayer
    layer = layer_cls(raster_path, layer_name, "gdal")
    if is_temporary and layer is not None:
        try:
            layer.setCustomProperty("bestfitinterpolator/output_storage", "temporary")
            layer.setCustomProperty("bestfitinterpolator/exported_to_project_folder", False)
            layer.setCustomProperty("skipMemoryLayersCheck", 0)
        except Exception:
            logger.debug("Could not tag temporary raster layer", exc_info=True)
    return layer


def add_result_layer(raster_path, layer_name, *, exported: bool):
    """Create, validate and add the output raster to the project. Returns the
    layer or raises RuntimeError on an invalid raster."""
    layer = create_output_raster_layer(raster_path, layer_name, exported=exported)
    if layer is None or not layer.isValid():
        raise RuntimeError(f"Output raster layer is not valid: {raster_path}")
    QgsProject.instance().addMapLayer(layer)
    return layer
