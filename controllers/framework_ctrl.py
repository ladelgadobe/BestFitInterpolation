# -*- coding: utf-8 -*-
"""Framework tab controller — diagnostics, rule-based recommendation and
multi-method comparison through the registry.

Replaces the legacy 3798-line framework_tab.py that drove the other tabs by
simulating their button clicks and scraping their figures (and reported
success even when a method's dispatch raised). Here every method runs through
FrameworkWorker/InterpolationWorker on session data only, and a failed method
is a visible "Failed" row in the results table — never a fabricated pass."""

from __future__ import annotations

import numpy as np
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QTableWidgetItem

from ..core.exceptions import BFIError
from ..core.methods import get_method
from ..core.spatial import compute_moran_index_knn
from ..core.types import TrainingData
from ..core.variogram import fit_variogram_mom
from ..gis.covariates import sample_covariates_at_points
from ..gis.layer_io import extract_boundary_wkts
from ..gis.raster_io import grid_from_layer, read_raster_grid
from ..gis.temp_layers import add_result_layer, choose_raster_output_path
from ..logger import get_logger
from ..services.framework_service import rank_by_metric
from ..view.common import read_cv_plan, tr
from ..workers import FrameworkWorker, InterpolationWorker
from .base import TabController

logger = get_logger(__name__)

#: Methods whose features include covariates / x,y (get the use_xy param).
_ML_KEYS = ("rf", "svm", "rk")

#: Legacy diagram tokens -> registry keys ("RFE" was the legacy name for RF).
_LEGACY_TOKEN_TO_KEY = {
    "IDW": "idw", "TPS": "tps", "OK": "ok",
    "SVM": "svm", "RFE": "rf", "RK": "rk",
}

_METRIC_ATTRS = ("rmse", "rmse_pct", "mae", "pearson_r", "r2", "lccc")


def _classify_sdi(sdi):
    """Legacy framework_tab._classify_sdi thresholds, verbatim."""
    if sdi < 20.0:
        return "Very Low"
    if sdi < 40.0:
        return "Low"
    if sdi < 60.0:
        return "Moderate"
    if sdi < 80.0:
        return "High"
    return "Very High"


def evaluate_framework(n, structured, sdi, has_covariates):
    """Decision tree moved from the legacy
    framework_tab.on_evaluate_methods_clicked, verbatim thresholds
    (n < 50 / < 100, SDI 40/60/80). The full diagram applies when covariates
    are loaded, the univariate diagram otherwise (the legacy mode radio +
    covariate check collapse to that). Returns (registry keys ranked by the
    diagram, human-readable decision path)."""
    n = int(n or 0)
    sdi_val = -1.0 if sdi is None else float(sdi)
    clustered = bool(structured)

    if has_covariates:
        if n < 50:
            if clustered:
                recommended = ["RK", "IDW", "TPS"]
                path = "Full: n < 100 -> n < 50 -> spatial structure -> clustered."
            else:
                recommended = ["IDW", "TPS"]
                path = "Full: n < 100 -> n < 50 -> random."
        elif n < 100:
            if clustered:
                if sdi_val >= 80:
                    recommended = ["SVM", "RFE", "RK", "OK"]
                    path = "Full: n < 100 -> n >= 50 -> clustered -> SDI >= 80%."
                else:
                    recommended = ["OK", "TPS", "IDW"]
                    path = "Full: n < 100 -> n >= 50 -> clustered -> SDI < 80%."
            else:
                if sdi_val < 60:
                    recommended = ["TPS"]
                    path = "Full: n < 100 -> n >= 50 -> random -> SDI < 60%."
                else:
                    recommended = ["SVM"]
                    path = "Full: n < 100 -> n >= 50 -> random -> SDI >= 60%."
        else:
            if clustered:
                if sdi_val < 60:
                    if sdi_val < 40:
                        recommended = ["TPS"]
                        path = "Full: n >= 100 -> clustered -> SDI < 60% -> SDI < 40%."
                    else:
                        recommended = ["TPS", "SVM"]
                        path = "Full: n >= 100 -> clustered -> SDI < 60% -> SDI >= 40%."
                elif sdi_val >= 80:
                    recommended = ["SVM", "RK", "RFE", "OK"]
                    path = "Full: n >= 100 -> clustered -> SDI >= 80%."
                else:
                    recommended = ["TPS", "RK", "RFE", "IDW", "OK"]
                    path = "Full: n >= 100 -> clustered -> 60% <= SDI < 80%."
            else:
                recommended = ["TPS", "SVM"]
                path = "Full: n >= 100 -> random -> TPS/SVM comparison."
    else:
        if n < 50:
            recommended = ["IDW", "TPS"]
            path = "Univariate: n < 100 -> n < 50."
        elif n < 100:
            if clustered:
                if sdi_val >= 80:
                    recommended = ["OK"]
                    path = "Univariate: n < 100 -> n >= 50 -> clustered -> SDI >= 80%."
                else:
                    recommended = ["OK", "TPS", "IDW"]
                    path = "Univariate: n < 100 -> n >= 50 -> clustered -> SDI < 80%."
            else:
                if sdi_val < 60:
                    recommended = ["TPS"]
                    path = "Univariate: n < 100 -> n >= 50 -> random -> SDI < 60%."
                else:
                    recommended = ["TPS", "OK"]
                    path = "Univariate: n < 100 -> n >= 50 -> random -> SDI >= 60%."
        else:
            if clustered:
                if sdi_val < 60:
                    recommended = ["TPS"]
                    path = "Univariate: n >= 100 -> clustered -> SDI < 60%."
                elif sdi_val >= 80:
                    recommended = ["TPS", "OK"]
                    path = "Univariate: n >= 100 -> clustered -> SDI >= 80%."
                else:
                    recommended = ["TPS", "IDW", "OK"]
                    path = "Univariate: n >= 100 -> clustered -> 60% <= SDI < 80%."
            else:
                recommended = ["IDW", "TPS"]
                path = "Univariate: n >= 100 -> random -> deterministic fallback."

    return [_LEGACY_TOKEN_TO_KEY[token] for token in recommended], path


class FrameworkCtrl(TabController):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._analysis = None

    def wire(self):
        d = self.dialog
        self._connect(d.fw_btn_analyze.clicked, self.analyze_data)
        self._connect(d.fw_btn_recommend.clicked, self.recommend_method)
        self._connect(d.fw_btn_compare.clicked, self.run_comparison)
        self._connect(d.fw_btn_interpolate.clicked, self.run_interpolation)
        self._wire_figure_buttons(d.fw_val_panel, "framework_validation")
        self._wire_figure_buttons(d.fw_map_panel, "framework_map")
        self._compare_handle = self.handle_for(d.fw_btn_compare)
        self._interp_handle = self.handle_for(d.fw_btn_interpolate)

    # ------------------------------------------------------------- analyze
    def analyze_data(self):
        """Quick diagnostics (Moran's I, MoM-variogram SDI) on the UI thread —
        cheap for typical n; each is guarded so a failure shows as "—"."""
        try:
            data = self.session.require_training_data()
        except BFIError as exc:
            self.notify_warning("Framework", str(exc))
            return
        d = self.dialog
        analysis = {"n": data.n, "moran": None, "sdi_pct": None}
        d.fw_n_label.setText(str(data.n))

        try:
            moran = compute_moran_index_knn(
                data.xy, data.values, k=8, n_permutations=199
            )
        except Exception:
            logger.exception("Moran's I computation failed")
            moran = None
        if moran is not None:
            analysis["moran"] = moran
            d.fw_moran_label.setText(
                f"I = {moran['I']:.3f}, p = {moran['p']:.3f} — {moran['pattern']}"
            )
        else:
            d.fw_moran_label.setText("—")

        try:
            vgm = fit_variogram_mom(data.x, data.y, data.values)
            total = float(vgm.nugget) + float(vgm.psill)
            if not np.isfinite(total) or total <= 0:
                raise ValueError("Degenerate variogram (nugget + psill <= 0).")
            sdi = 100.0 * float(vgm.psill) / total
            analysis["sdi_pct"] = sdi
            d.fw_sdi_label.setText(f"{sdi:.1f}% ({tr(_classify_sdi(sdi))})")
        except Exception:
            logger.exception("SDI computation failed")
            d.fw_sdi_label.setText("—")

        n_cov = len(self.session.selected_covariate_paths())
        analysis["n_covariates"] = n_cov
        d.fw_cov_label.setText(str(n_cov))

        self._analysis = analysis
        self.notify_status("Framework", "Data characteristics updated.")

    # ----------------------------------------------------------- recommend
    def recommend_method(self):
        if self._analysis is None:
            self.analyze_data()
        analysis = self._analysis
        if analysis is None:
            return  # analyze_data already warned about missing data

        n = int(analysis["n"])
        moran = analysis.get("moran")
        # Legacy _has_spatial_structure: p < 0.05, else pattern mentions cluster.
        structured = moran is not None and (
            float(moran.get("p", 1.0)) < 0.05
            or str(moran.get("pattern", "")).lower().startswith("cluster")
        )
        sdi = analysis.get("sdi_pct")
        has_covariates = int(analysis.get("n_covariates", 0)) > 0

        keys, path = evaluate_framework(n, structured, sdi, has_covariates)
        labels = [get_method(key).info.label for key in keys]

        text = tr("Recommended:") + " " + labels[0]
        if len(labels) > 1:
            text += "\n" + tr("Alternatives:") + " " + ", ".join(labels[1:])
        if keys[0] == "ok":
            # Legacy rule: REML variogram fit below 100 samples, MoM above.
            fit_mode = "REML" if n < 100 else "MoM"
            text += "\n" + tr("Variogram fit:") + f" {fit_mode}"
        d = self.dialog
        d.fw_recommendation_label.setText(text)
        d.fw_decision_view.set_state({
            "n": n,
            "moran_pattern": moran.get("pattern") if moran else None,
            "sdi_pct": sdi,
            "has_covariates": has_covariates,
            "recommended_label": labels[0],
        })
        index = d.fw_method_combo.findData(keys[0])
        if index >= 0:
            d.fw_method_combo.setCurrentIndex(index)
        self.notify_status("Framework", path)

    # ---------------------------------------------------------- covariates
    def _covariate_names(self):
        return tuple(
            name for name in self.session.covariate_selection
            if name in self.session.covariate_paths
        )

    def _data_with_covariates(self, data):
        """Training data + covariate values sampled at the points (rows with
        any non-finite covariate are dropped). No selection -> unchanged."""
        paths = self.session.selected_covariate_paths()
        if not paths:
            return data
        sampled = sample_covariates_at_points(paths, data.xy)
        mask = np.isfinite(sampled).all(axis=1)
        if not np.any(mask):
            raise BFIError(
                "No sample points have valid values in the selected "
                "covariate rasters. Check the covariate extents."
            )
        dropped = int((~mask).sum())
        if dropped:
            logger.info("Framework: dropped %d points without covariate values", dropped)
        return TrainingData(
            xy=data.xy[mask],
            values=data.values[mask],
            covariates=sampled[mask],
            covariate_names=self._covariate_names(),
            crs_authid=data.crs_authid,
        )

    # ------------------------------------------------------------- compare
    def run_comparison(self):
        if self._compare_handle.is_running():
            return
        d = self.dialog
        try:
            data = self.session.require_training_data()
            keys = []
            for i in range(d.fw_method_list.count()):
                item = d.fw_method_list.item(i)
                if item.checkState() == Qt.Checked:
                    keys.append(item.data(Qt.UserRole))
            if not keys:
                raise BFIError("Check at least one method to compare.")
            data = self._data_with_covariates(data)
            plan = read_cv_plan(d, "fw", data.n)
        except BFIError as exc:
            self.notify_warning("Framework comparison", str(exc))
            return

        params_by_method = {
            key: {"use_xy": self.session.use_xy_features}
            for key in keys if key in _ML_KEYS
        }
        worker = FrameworkWorker(data, keys, plan, params_by_method)
        self._compare_handle.launch(
            worker,
            on_result=self._on_comparison_done,
            on_failed=lambda msg: self.notify_error("Framework comparison failed", msg),
            on_dep_missing=lambda msg: self.notify_warning("Missing dependency", msg),
        )

    def _on_comparison_done(self, result):
        d = self.dialog
        ranked = rank_by_metric(result, "rmse")
        ordered = ranked + [e for e in result.entries if e.status != "ok"]

        table = d.fw_results_table
        table.setRowCount(len(ordered))
        for row, entry in enumerate(ordered):
            label = get_method(entry.method_key).info.label
            if entry.status == "ok":
                status_text = entry.cv.plan.label()
            elif entry.status == "failed":
                status_text = f"Failed: {entry.error}"
            else:  # skipped_deps / skipped_samples
                status_text = entry.error or entry.status
            cells = [label, status_text]
            if entry.status == "ok" and entry.cv is not None:
                metrics = entry.cv.metrics
                for attr in _METRIC_ATTRS:
                    value = getattr(metrics, attr, float("nan"))
                    if value is None or not np.isfinite(value):
                        cells.append("—")
                    else:
                        cells.append(f"{value:.3f}")
                self.session.store_cv(entry.method_key, entry.cv)
            else:
                cells.extend(["—"] * len(_METRIC_ATTRS))
            for col, text in enumerate(cells):
                table.setItem(row, col, QTableWidgetItem(str(text)))
        table.resizeColumnsToContents()

        if ranked:
            best = ranked[0]
            best_label = get_method(best.method_key).info.label
            self.plots.obs_vs_pred(
                d.fw_val_panel.figure, best.cv.observed, best.cv.predicted,
                best.cv.metrics,
                title=f"{best_label} — {best.cv.plan.label()}",
            )
            d.fw_val_panel.canvas.draw_idle()
            index = d.fw_method_combo.findData(best.method_key)
            if index >= 0:
                d.fw_method_combo.setCurrentIndex(index)
            self.notify_status(
                "Framework",
                f"Best: {best_label} (RMSE {best.cv.metrics.rmse:.3f})",
            )
        else:
            self.notify_warning(
                "Framework comparison",
                "No method completed successfully. See the Status column "
                "for the reason each method failed or was skipped.",
            )

    # --------------------------------------------------------- interpolate
    def run_interpolation(self):
        if self._interp_handle.is_running():
            return
        d = self.dialog
        try:
            data = self.session.require_training_data()
            if self.session.boundary_layer is None:
                raise BFIError("Select a boundary polygon in the Data tab first.")
            key = d.fw_method_combo.currentData()
            if not key:
                raise BFIError("Select a method to interpolate.")
            covariate_paths = []
            params = None
            if key in _ML_KEYS:
                data = self._data_with_covariates(data)
                covariate_paths = self.session.selected_covariate_paths()
                params = {"use_xy": self.session.use_xy_features}
            grid = grid_from_layer(self.session.boundary_layer, self.session.pixel_size)
            wkts, _, _ = extract_boundary_wkts(self.session.boundary_layer)
            out_path = choose_raster_output_path(
                key.upper(), self.session.variable_field,
                exported=self.session.export_rasters,
            )
        except BFIError as exc:
            self.notify_warning("Framework interpolation", str(exc))
            return

        worker = InterpolationWorker(
            data, key, params, grid, wkts, out_path,
            covariate_paths=covariate_paths,
        )
        self._interp_handle.launch(
            worker,
            on_result=self._on_raster_done,
            on_failed=lambda msg: self.notify_error("Framework interpolation failed", msg),
            on_dep_missing=lambda msg: self.notify_warning("Missing dependency", msg),
        )

    def _on_raster_done(self, result):
        try:
            key = result.method_key
            label = get_method(key).info.label
            layer_name = f"{key.upper()} ({self.session.variable_field})"
            add_result_layer(result.path, layer_name, exported=self.session.export_rasters)
            arr, grid = read_raster_grid(result.path)
            self.plots.raster_preview(
                self.dialog.fw_map_panel.figure, arr, grid,
                title=f"{label} — {self.session.variable_field}",
            )
            self.dialog.fw_map_panel.canvas.draw_idle()
        except Exception as exc:
            logger.exception("Framework raster post-processing failed")
            self.notify_error("Framework interpolation", str(exc))
            return
        self.session.store_fit(result.method_key, result)
        self.notify_status("Framework", f"Raster layer created: {result.path}")
