# -*- coding: utf-8 -*-
"""Geostatistics tab controller — the single OK controller replacing the
legacy MoM/REML clone pair and their dispatcher. Strategy (Automatic/MoM/
REML) is a fit parameter routed through the registry."""

from __future__ import annotations

import numpy as np

from ..core.exceptions import BFIError
from ..gis.layer_io import extract_boundary_wkts
from ..gis.raster_io import grid_from_layer, read_raster_grid
from ..gis.temp_layers import add_result_layer, choose_raster_output_path
from ..logger import get_logger
from ..view.common import fill_metrics_table, read_cv_plan, tr
from ..workers import CVWorker, FitWorker, InterpolationWorker, ModelValidationWorker
from .base import TabController

logger = get_logger(__name__)

_MODEL_TEXTS = {"spherical": "Sph", "exponential": "Exp", "gaussian": "Gau"}


class GeostatCtrl(TabController):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._auto_model = "exponential"
        self._model_validation_rows = None

    def wire(self):
        d = self.dialog
        self._connect(d.ok_btn_calculate.clicked, self.calculate_variogram)
        self._connect(d.ok_btn_reset.clicked, self.reset_variogram)
        self._connect(d.ok_btn_interpolate.clicked, self.run_interpolation)
        self._connect(d.ok_btn_cv.clicked, self.run_cv)
        self._connect(d.ok_btn_model_validation.clicked, self.show_model_validation)
        self._connect(d.ok_spin_nugget.valueChanged, self._update_sdi_label)
        self._connect(d.ok_spin_psill.valueChanged, self._update_sdi_label)
        self._wire_figure_buttons(d.ok_vario_panel, "kriging_variogram")
        self._wire_figure_buttons(d.ok_map_panel, "kriging_map")
        self._wire_figure_buttons(d.ok_val_panel, "kriging_validation")
        self._fit_handle = self.handle_for(d.ok_btn_calculate)
        self._interp_handle = self.handle_for(d.ok_btn_interpolate)
        self._cv_handle = self.handle_for(d.ok_btn_cv)
        self._validation_handle = self.handle_for(d.ok_btn_model_validation)

    # ------------------------------------------------------------ helpers
    def _selected_model_token(self):
        text = self.dialog.ok_model_combo.currentText()
        if text.strip().lower().startswith("auto"):
            return self._auto_model
        from ..core.variogram import normalize_model_token

        return normalize_model_token(text)

    def _strategy(self):
        return self.dialog.ok_fit_method_combo.currentText() or "Automatic"

    def _explicit_params(self):
        d = self.dialog
        nugget = float(d.ok_spin_nugget.value())
        psill = float(d.ok_spin_psill.value())
        range_ = float(d.ok_spin_range.value())
        if psill <= 0 or range_ <= 0:
            raise BFIError(
                "Fit the semivariogram first (Calculate…) or enter positive "
                "partial sill and range values."
            )
        return {
            "strategy": self._strategy(),
            "model": self._selected_model_token(),
            "nugget": nugget,
            "psill": psill,
            "range": range_,
        }

    def _fit_params(self):
        d = self.dialog
        params = {
            "strategy": self._strategy(),
            "model": self._selected_model_token(),
        }
        cutoff = float(d.ok_spin_cutoff.value())
        lag = float(d.ok_spin_lag.value())
        if cutoff > 0:
            params["cutoff"] = cutoff
        if lag > 0:
            params["lag_width"] = lag
        return params

    def _update_sdi_label(self, *_):
        d = self.dialog
        try:
            nugget = float(d.ok_spin_nugget.value())
            psill = float(d.ok_spin_psill.value())
            total = nugget + psill
            if not np.isfinite(total) or total <= 0:
                d.ok_sdi_label.setText("—")
                return
            sdi = 100.0 * psill / total
            if sdi < 20.0:
                cls = "Very Low"
            elif sdi < 40.0:
                cls = "Low"
            elif sdi < 60.0:
                cls = "Moderate"
            elif sdi < 80.0:
                cls = "High"
            else:
                cls = "Very High"
            d.ok_sdi_label.setText(f"{sdi:.1f}% ({cls})")
        except Exception:
            d.ok_sdi_label.setText("—")

    # ---------------------------------------------------------- variogram
    def calculate_variogram(self):
        if self._fit_handle.is_running():
            return
        try:
            data = self.session.require_training_data()
        except BFIError as exc:
            self.notify_warning("Kriging", str(exc))
            return
        self.dialog.ok_samples_label.setText(str(data.n))
        self.dialog.ok_z_label.setText(self.session.variable_field or "—")

        worker = FitWorker(data, "ok", self._fit_params())
        self._fit_handle.launch(
            worker,
            on_result=self._on_variogram_fitted,
            on_failed=lambda msg: self.notify_error("Variogram fit failed", msg),
            on_dep_missing=lambda msg: self.notify_warning("Missing dependency", msg),
        )

    def _on_variogram_fitted(self, fit):
        d = self.dialog
        vgm = fit.diagnostics.get("variogram")
        reason = fit.diagnostics.get("strategy_reason", "")
        if vgm is None:
            self.notify_error("Kriging", "Fit produced no variogram.")
            return
        d.ok_spin_nugget.setValue(vgm.nugget)
        d.ok_spin_psill.setValue(vgm.psill)
        d.ok_spin_range.setValue(vgm.range_)
        d.ok_fit_label.setText(f"{vgm.strategy.upper()} — {reason}")
        self._auto_model = vgm.model
        self._update_sdi_label()

        report = vgm.fit_report or {}
        lags = report.get("lags")
        gamma = report.get("gamma")
        if report.get("cutoff") and d.ok_spin_cutoff.value() <= 0:
            d.ok_spin_cutoff.setValue(float(report["cutoff"]))
        if lags is not None and len(lags):
            self.plots.variogram(d.ok_vario_panel.figure, lags, gamma, vgm,
                                 title=tr("Experimental semivariogram"))
        else:
            # REML has no experimental variogram (legacy behavior) — show the
            # model curve alone over a nominal distance span.
            span = np.linspace(0, vgm.range_ * 1.5 or 1.0, 2)
            self.plots.variogram(d.ok_vario_panel.figure, span[:0], span[:0], vgm,
                                 title=tr("REML fitted model"))
        d.ok_vario_panel.canvas.draw_idle()
        self.session.store_fit("ok", fit)
        if reason:
            self.notify_status("Kriging", reason)

    def reset_variogram(self):
        d = self.dialog
        for spin in (d.ok_spin_cutoff, d.ok_spin_lag, d.ok_spin_nugget,
                     d.ok_spin_psill, d.ok_spin_range):
            spin.setValue(0.0)
        d.ok_fit_label.setText("—")
        self.calculate_variogram()

    def show_model_validation(self):
        if self._validation_handle.is_running():
            return
        try:
            data = self.session.require_training_data()
        except BFIError as exc:
            self.notify_warning("Kriging model validation", str(exc))
            return
        cutoff = float(self.dialog.ok_spin_cutoff.value()) or None
        lag = float(self.dialog.ok_spin_lag.value()) or None
        worker = ModelValidationWorker(data, cutoff, lag)
        self._validation_handle.launch(
            worker,
            on_result=self._on_model_validation_done,
            on_failed=lambda msg: self.notify_error("Model validation failed", msg),
            on_dep_missing=lambda msg: self.notify_warning("Missing dependency", msg),
        )

    def _on_model_validation_done(self, rows):
        self._model_validation_rows = rows
        best = rows[0] if rows else None
        if best and not best.get("error"):
            self._auto_model = str(best["model_key"])
        lines = []
        for r in rows:
            name = _MODEL_TEXTS.get(r["model_key"], r["model_key"])
            if r.get("error"):
                lines.append(f"{name}: failed ({r['error']})")
            else:
                lines.append(
                    f"{name}: R²={r['r2']:.3f}  RMSE={r['rmse']:.3f}  "
                    f"LCCC={r['lccc']:.3f}"
                )
        best_name = _MODEL_TEXTS.get(self._auto_model, self._auto_model)
        self.notifier.info(
            self.dialog, tr("Kriging model validation"),
            tr("LOOCV comparison (best first):") + "\n\n" + "\n".join(lines)
            + f"\n\n{tr('Best automatic model:')} {best_name}",
        )

    # -------------------------------------------------------- interpolation
    def run_interpolation(self):
        if self._interp_handle.is_running():
            return
        try:
            data = self.session.require_training_data()
            if self.session.boundary_layer is None:
                raise BFIError("Select a boundary polygon in the Data tab first.")
            params = self._explicit_params()
            grid = grid_from_layer(self.session.boundary_layer, self.session.pixel_size)
            wkts, _, _ = extract_boundary_wkts(self.session.boundary_layer)
            out_path = choose_raster_output_path(
                "OK", self.session.variable_field, exported=self.session.export_rasters
            )
        except BFIError as exc:
            self.notify_warning("Kriging", str(exc))
            return

        worker = InterpolationWorker(data, "ok", params, grid, wkts, out_path)
        self._interp_handle.launch(
            worker,
            on_result=self._on_raster_done,
            on_failed=lambda msg: self.notify_error("Kriging failed", msg),
            on_dep_missing=lambda msg: self.notify_warning("Missing dependency", msg),
        )

    def _on_raster_done(self, result):
        try:
            layer_name = f"OK ({self.session.variable_field})"
            add_result_layer(result.path, layer_name, exported=self.session.export_rasters)
            arr, grid = read_raster_grid(result.path)
            self.plots.raster_preview(
                self.dialog.ok_map_panel.figure, arr, grid,
                title=f"Ordinary Kriging — {self.session.variable_field}",
            )
            self.dialog.ok_map_panel.canvas.draw_idle()
        except Exception as exc:
            logger.exception("OK raster post-processing failed")
            self.notify_error("Kriging", str(exc))
            return
        self.notify_status("Kriging", f"Raster layer created: {result.path}")

    # ------------------------------------------------------------------ CV
    def run_cv(self):
        if self._cv_handle.is_running():
            return
        try:
            data = self.session.require_training_data()
            params = self._explicit_params()
            plan = read_cv_plan(self.dialog, "ok", data.n)
        except BFIError as exc:
            self.notify_warning("Kriging cross-validation", str(exc))
            return

        worker = CVWorker(data, "ok", params, plan)
        self._cv_handle.launch(
            worker,
            on_result=self._on_cv_done,
            on_failed=lambda msg: self.notify_error("Cross-validation failed", msg),
            on_dep_missing=lambda msg: self.notify_warning("Missing dependency", msg),
        )

    def _on_cv_done(self, cv):
        d = self.dialog
        fill_metrics_table(d.ok_metrics_table, cv.metrics)
        self.plots.obs_vs_pred(
            d.ok_val_panel.figure, cv.observed, cv.predicted, cv.metrics,
            title=f"Ordinary Kriging — {cv.plan.label()}",
        )
        d.ok_val_panel.canvas.draw_idle()
        self.session.store_cv("ok", cv)
        self.notify_status("Kriging", f"Cross-validation ({cv.plan.label()}) finished.")
