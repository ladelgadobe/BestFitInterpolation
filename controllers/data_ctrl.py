# -*- coding: utf-8 -*-
"""Data tab controller: load samples into the session, run diagnostics
(CRS checks, Moran's I) and draw the sample-map preview."""

from __future__ import annotations

import numpy as np

from ..core.exceptions import BFIError
from ..core.spatial import compute_moran_index_knn
from ..gis.layer_io import extract_boundary_rings, read_point_samples
from ..logger import get_logger
from ..notify import Notifier
from .base import TabController

logger = get_logger(__name__)


class DataCtrl(TabController):
    def wire(self):
        d = self.dialog
        self._connect(d.dt_btn_load.clicked, self.load_data)
        self._connect(d.dt_pixel_size.valueChanged, self._on_pixel_size_changed)
        self._connect(d.dt_export_check.toggled, self._on_export_toggled)
        self._wire_figure_buttons(d.dt_preview_panel, "sample_map")

    # ------------------------------------------------------------------ slots
    def _on_pixel_size_changed(self, value):
        self.session.pixel_size = float(value)

    def _on_export_toggled(self, checked):
        self.session.export_rasters = bool(checked)

    def load_data(self):
        d = self.dialog
        try:
            points_layer = d.dt_points_combo.currentLayer()
            field = d.dt_variable_combo.currentField()
            polygon_layer = d.dt_polygon_combo.currentLayer()

            data = read_point_samples(points_layer, field)

            self.session.points_layer = points_layer
            self.session.variable_field = field
            self.session.boundary_layer = polygon_layer
            self.session.training_data = data
            self.session.pixel_size = float(d.dt_pixel_size.value())
            self.session.export_rasters = d.dt_export_check.isChecked()
            self.session.reset_results()

            self._update_crs_label(points_layer, polygon_layer)
            d.dt_samples_label.setText(str(data.n))
            self._update_moran(data)
            self._draw_preview(data, polygon_layer, field)
            self.notify_status("Data", f"Loaded {data.n} samples of '{field}'.")
        except BFIError as exc:
            self.notify_warning("Data", str(exc))
        except Exception as exc:
            logger.exception("Data load failed")
            self.notify_error("Data", f"{type(exc).__name__}: {exc}")

    # ------------------------------------------------------------- diagnostics
    def _update_crs_label(self, points_layer, polygon_layer):
        d = self.dialog
        try:
            crs = points_layer.crs()
            text = f"CRS: {crs.authid()} — {crs.description()}"
            warnings = []
            if crs.isGeographic():
                warnings.append(
                    "Geographic CRS detected: distance-based interpolation and "
                    "Moran's Index should be run with a projected CRS in meters."
                )
            if polygon_layer is not None and polygon_layer.crs() != crs:
                warnings.append(
                    f"Polygon CRS ({polygon_layer.crs().authid()}) differs from "
                    "the points CRS — interpolation will be blocked until they match."
                )
            if warnings:
                text += "\n⚠ " + "\n⚠ ".join(warnings)
                self.notify_status("CRS", warnings[0], level=Notifier.WARNING)
            d.dt_crs_label.setText(text)
        except Exception:
            logger.debug("CRS label update failed", exc_info=True)
            d.dt_crs_label.setText("CRS: —")

    def _update_moran(self, data):
        d = self.dialog
        result = compute_moran_index_knn(data.xy, data.values, k=8, n_permutations=199)
        if result is None or not np.isfinite(result["I"]):
            d.dt_moran_label.setText("-")
            return
        d.dt_moran_label.setText(
            f"Moran's I = {result['I']:.3f} (p = {result['p']:.3f}) — {result['pattern']}"
        )

    def _draw_preview(self, data, polygon_layer, field):
        d = self.dialog
        rings = extract_boundary_rings(polygon_layer)
        self.plots.point_map(
            d.dt_preview_panel.figure, data.xy, data.values,
            boundary_rings=rings, variable_name=field,
        )
        d.dt_preview_panel.canvas.draw_idle()
