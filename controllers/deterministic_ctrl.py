# -*- coding: utf-8 -*-
"""Deterministic tab controller — IDW (optimized/manual) and TPS through the
method registry, all compute in workers (button-as-cancel)."""

from __future__ import annotations

from ..core.exceptions import BFIError
from ..gis.layer_io import extract_boundary_wkts
from ..gis.raster_io import grid_from_layer
from ..gis.temp_layers import add_result_layer, choose_raster_output_path
from ..logger import get_logger
from ..view.common import fill_metrics_table, read_cv_plan
from ..workers import CVWorker, InterpolationWorker
from .base import TabController

logger = get_logger(__name__)

METHOD_TAGS = {"idw": "IDW", "tps": "TPS"}


class DeterministicCtrl(TabController):
    def wire(self):
        d = self.dialog
        # Legacy semantics: the three options behave as an exclusive group.
        self._connect(d.det_chk_optimize.toggled, self._on_optimize_toggled)
        self._connect(d.det_rad_manual.toggled, self._on_manual_toggled)
        self._connect(d.det_chk_tps.toggled, self._on_tps_toggled)
        self._connect(d.det_btn_interpolate.clicked, self.run_interpolation)
        self._connect(d.det_btn_cv.clicked, self.run_cv)
        self._wire_figure_buttons(d.det_interp_panel, "deterministic_map")
        self._wire_figure_buttons(d.det_val_panel, "deterministic_validation")
        d.det_rad_manual.setChecked(True)
        self._interp_handle = self.handle_for(d.det_btn_interpolate)
        self._cv_handle = self.handle_for(d.det_btn_cv)

    # ---------------------------------------------------------- exclusivity
    def _on_optimize_toggled(self, checked):
        if checked:
            self.dialog.det_rad_manual.setChecked(False)
            self.dialog.det_chk_tps.setChecked(False)
        self._sync_idw_spins()

    def _on_manual_toggled(self, checked):
        if checked:
            self.dialog.det_chk_optimize.setChecked(False)
            self.dialog.det_chk_tps.setChecked(False)
        self._sync_idw_spins()

    def _on_tps_toggled(self, checked):
        if checked:
            self.dialog.det_chk_optimize.setChecked(False)
            self.dialog.det_rad_manual.setChecked(False)
        self._sync_idw_spins()

    def _sync_idw_spins(self):
        manual = self.dialog.det_rad_manual.isChecked()
        self.dialog.det_spin_power.setEnabled(manual)
        self.dialog.det_spin_neighbors.setEnabled(manual)

    # ------------------------------------------------------------- params
    def _method_and_params(self):
        d = self.dialog
        if d.det_chk_tps.isChecked():
            return "tps", {}
        if d.det_chk_optimize.isChecked():
            return "idw", None      # None -> auto-tune (p, n) search
        return "idw", {
            "p": float(d.det_spin_power.value()),
            "n": int(d.det_spin_neighbors.value()),
        }

    # ---------------------------------------------------------------- runs
    def run_interpolation(self):
        if self._interp_handle.is_running():
            return
        d = self.dialog
        try:
            data = self.session.require_training_data()
            if self.session.boundary_layer is None:
                raise BFIError("Select a boundary polygon in the Data tab first.")
            self._check_crs()
            method_key, params = self._method_and_params()
            grid = grid_from_layer(self.session.boundary_layer, self.session.pixel_size)
            wkts, _, _ = extract_boundary_wkts(self.session.boundary_layer)
            out_path = choose_raster_output_path(
                METHOD_TAGS[method_key], self.session.variable_field,
                exported=self.session.export_rasters,
            )
        except BFIError as exc:
            self.notify_warning("Interpolation", str(exc))
            return

        worker = InterpolationWorker(data, method_key, params, grid, wkts, out_path)
        self._interp_handle.launch(
            worker,
            on_result=self._on_raster_done,
            on_failed=lambda msg: self.notify_error("Interpolation failed", msg),
            on_dep_missing=lambda msg: self.notify_warning("Missing dependency", msg),
        )

    def _on_raster_done(self, result):
        try:
            layer_name = f"{METHOD_TAGS[result.method_key]} ({self.session.variable_field})"
            add_result_layer(result.path, layer_name, exported=self.session.export_rasters)
        except Exception as exc:
            logger.exception("Could not add result layer")
            self.notify_error("Interpolation", str(exc))
            return
        try:
            from ..gis.raster_io import read_raster_grid

            arr, grid = read_raster_grid(result.path)
            self.plots.raster_preview(
                self.dialog.det_interp_panel.figure, arr, grid,
                title=f"{METHOD_TAGS[result.method_key]} — {self.session.variable_field}",
            )
            self.dialog.det_interp_panel.canvas.draw_idle()
        except Exception:
            logger.exception("Preview rendering failed")
        self.session.store_fit(result.method_key, result)
        self.notify_status("Interpolation", f"Raster layer created: {result.path}")

    def run_cv(self):
        if self._cv_handle.is_running():
            return
        try:
            data = self.session.require_training_data()
            method_key, params = self._method_and_params()
            plan = read_cv_plan(self.dialog, "det", data.n)
        except BFIError as exc:
            self.notify_warning("Cross-validation", str(exc))
            return

        worker = CVWorker(data, method_key, params, plan)
        self._cv_handle.launch(
            worker,
            on_result=lambda cv: self._on_cv_done(method_key, cv),
            on_failed=lambda msg: self.notify_error("Cross-validation failed", msg),
            on_dep_missing=lambda msg: self.notify_warning("Missing dependency", msg),
        )

    def _on_cv_done(self, method_key, cv):
        d = self.dialog
        fill_metrics_table(d.det_metrics_table, cv.metrics)
        self.plots.obs_vs_pred(
            d.det_val_panel.figure, cv.observed, cv.predicted, cv.metrics,
            title=f"{METHOD_TAGS[method_key]} — {cv.plan.label()}",
        )
        d.det_val_panel.canvas.draw_idle()
        self.session.store_cv(method_key, cv)
        self.notify_status("Cross-validation", f"{METHOD_TAGS[method_key]} {cv.plan.label()} finished.")

    # ------------------------------------------------------------- checks
    def _check_crs(self):
        points = self.session.points_layer
        boundary = self.session.boundary_layer
        if points is not None and boundary is not None:
            try:
                if points.crs() != boundary.crs():
                    raise BFIError(
                        "Points and polygon layers use different CRS. "
                        "Reproject one of them before interpolating."
                    )
            except BFIError:
                raise
            except Exception:
                logger.debug("CRS comparison failed", exc_info=True)
