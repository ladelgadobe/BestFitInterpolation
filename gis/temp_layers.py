# -*- coding: utf-8 -*-
"""Output-layer helpers — the single BestFitTemporaryRasterLayer (formerly
defined in four modules) and the add-to-project flow."""

from __future__ import annotations

import os
import tempfile

from qgis.core import QgsProject, QgsRasterLayer

from ..logger import get_logger

logger = get_logger(__name__)


def ensure_output_dir() -> str:
    """BestFitInterpolation folder inside the project directory, or '' when
    the project is unsaved (legacy behavior: fall back to temp)."""
    proj_path = QgsProject.instance().fileName()
    if not proj_path:
        return ""
    out_dir = os.path.join(os.path.dirname(proj_path), "BestFitInterpolation")
    os.makedirs(out_dir, exist_ok=True)
    return out_dir


def choose_raster_output_path(method_tag, variable_name, *, exported: bool) -> str:
    """<method>_<variable>_<uuid6>.tif in the project output folder (when
    exporting and the project is saved) else the system temp dir."""
    import uuid

    base_name = f"{method_tag}_{variable_name}_{uuid.uuid4().hex[:6]}.tif"
    if exported:
        out_dir = ensure_output_dir()
        if out_dir:
            return os.path.join(out_dir, base_name)
    return os.path.join(tempfile.gettempdir(), base_name)


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
