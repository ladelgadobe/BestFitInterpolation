# -*- coding: utf-8 -*-
"""Machine Learning tab controller — Covariables / RF / SVM / RK facade.
Covariate sampling at the training points happens on the UI thread (one
block read per raster); model fits, CV and raster generation run in
workers through the method registry (button-as-cancel)."""

from __future__ import annotations

import numpy as np

from ..core.exceptions import BFIError
from ..core.types import TrainingData
from ..gis.covariates import sample_covariates_at_points
from ..gis.layer_io import extract_boundary_wkts
from ..gis.raster_io import grid_from_layer, read_raster_grid
from ..gis.temp_layers import add_result_layer, choose_raster_output_path
from ..logger import get_logger
from ..view.common import fill_metrics_table, read_cv_plan
from ..workers import CVWorker, FitWorker, InterpolationWorker
from .base import TabController

logger = get_logger(__name__)

METHOD_TAGS = {"rf": "RF", "svm": "SVM", "rk": "RK"}
METHOD_LABELS = {"rf": "Random Forest", "svm": "SVM", "rk": "Regression Kriging"}
CV_PREFIXES = {"rf": "ml_rf", "svm": "ml_svm", "rk": "rk"}


class MLCtrl(TabController):
    def wire(self):
        d = self.dialog
        self._connect(d.ml_btn_add_cov.clicked, self.add_covariate)
        self._connect(d.ml_btn_remove_cov.clicked, self.remove_selected_covariates)
        self._connect(d.ml_use_xy_check.toggled, self._on_use_xy_toggled)
        self._connect(d.ml_btn_correlation.clicked, self.compute_correlations)

        self._connect(d.ml_rf_btn_interpolate.clicked,
                      lambda _=False: self.run_interpolation("rf"))
        self._connect(d.ml_svm_btn_interpolate.clicked,
                      lambda _=False: self.run_interpolation("svm"))
        self._connect(d.rk_btn_interpolate.clicked,
                      lambda _=False: self.run_interpolation("rk"))
        self._connect(d.ml_rf_btn_cv.clicked, lambda _=False: self.run_cv("rf"))
        self._connect(d.ml_svm_btn_cv.clicked, lambda _=False: self.run_cv("svm"))
        self._connect(d.rk_btn_cv.clicked, lambda _=False: self.run_cv("rk"))
        self._connect(d.ml_rf_btn_importance.clicked,
                      lambda _=False: self.run_importance("rf"))
        self._connect(d.rk_btn_importance.clicked,
                      lambda _=False: self.run_importance("rk"))

        self._map_panels = {
            "rf": d.ml_rf_map_panel, "svm": d.ml_svm_map_panel, "rk": d.rk_map_panel,
        }
        self._val_panels = {
            "rf": d.ml_rf_val_panel, "svm": d.ml_svm_val_panel, "rk": d.rk_val_panel,
        }
        self._metrics_tables = {
            "rf": d.ml_rf_metrics_table, "svm": d.ml_svm_metrics_table,
            "rk": d.rk_metrics_table,
        }
        self._importance_panels = {
            "rf": d.ml_rf_importance_panel, "rk": d.rk_importance_panel,
        }

        self._wire_figure_buttons(d.ml_corr_panel, "ml_correlations")
        self._wire_figure_buttons(d.ml_rf_map_panel, "rf_map")
        self._wire_figure_buttons(d.ml_rf_importance_panel, "rf_importance")
        self._wire_figure_buttons(d.ml_rf_val_panel, "rf_validation")
        self._wire_figure_buttons(d.ml_svm_map_panel, "svm_map")
        self._wire_figure_buttons(d.ml_svm_val_panel, "svm_validation")
        self._wire_figure_buttons(d.rk_map_panel, "rk_map")
        self._wire_figure_buttons(d.rk_vario_panel, "rk_residual_variogram")
        self._wire_figure_buttons(d.rk_importance_panel, "rk_importance")
        self._wire_figure_buttons(d.rk_val_panel, "rk_validation")

        self._interp_handles = {
            "rf": self.handle_for(d.ml_rf_btn_interpolate),
            "svm": self.handle_for(d.ml_svm_btn_interpolate),
            "rk": self.handle_for(d.rk_btn_interpolate),
        }
        self._cv_handles = {
            "rf": self.handle_for(d.ml_rf_btn_cv),
            "svm": self.handle_for(d.ml_svm_btn_cv),
            "rk": self.handle_for(d.rk_btn_cv),
        }
        self._importance_handles = {
            "rf": self.handle_for(d.ml_rf_btn_importance),
            "rk": self.handle_for(d.rk_btn_importance),
        }

    # ---------------------------------------------------------- covariates
    def add_covariate(self):
        layer = self.dialog.ml_cov_layer_combo.currentLayer()
        if layer is None:
            self.notify_warning("Covariates", "Select a covariate raster layer first.")
            return
        name = layer.name()
        self.session.covariate_paths[name] = layer.source().split("|")[0]
        self._refresh_cov_list()
        self.notify_status("Covariates", f"Covariate added: {name}")

    def remove_selected_covariates(self):
        items = self.dialog.ml_cov_list.selectedItems()
        if not items:
            self.notify_warning("Covariates", "Select covariates in the list to remove.")
            return
        for item in items:
            self.session.covariate_paths.pop(item.text(), None)
        self._refresh_cov_list()

    def _refresh_cov_list(self):
        names = list(self.session.covariate_paths.keys())
        self.session.covariate_selection = names
        cov_list = self.dialog.ml_cov_list
        cov_list.clear()
        cov_list.addItems(names)

    def _on_use_xy_toggled(self, checked):
        self.session.use_xy_features = bool(checked)

    # --------------------------------------------------------- correlations
    def compute_correlations(self):
        # One block read per raster — cheap enough for the UI thread.
        try:
            data = self.session.require_training_data()
            paths = self.session.selected_covariate_paths()
            if not paths:
                raise BFIError("Add at least one covariate raster first.")
            cov = sample_covariates_at_points(paths, data.xy)
        except BFIError as exc:
            self.notify_warning("Correlations", str(exc))
            return
        except Exception as exc:
            logger.exception("Covariate sampling failed")
            self.notify_error("Correlations", str(exc))
            return

        columns = np.column_stack([np.asarray(data.values, dtype=float), cov])
        finite = np.isfinite(columns).all(axis=1)
        if int(finite.sum()) < 3:
            self.notify_warning(
                "Correlations",
                "Fewer than 3 sample points have values for every covariate.",
            )
            return
        matrix = np.corrcoef(columns[finite].T)
        labels = [self.session.variable_field or "target"]
        labels += list(self.session.covariate_selection)
        self.plots.correlation_matrix(self.dialog.ml_corr_panel.figure, matrix, labels)
        self.dialog.ml_corr_panel.canvas.draw_idle()

    # -------------------------------------------------------------- params
    def _rf_params(self):
        d = self.dialog
        params = {"use_xy": bool(self.session.use_xy_features)}
        if d.ml_rf_grid_search.isChecked():
            params["use_grid_search"] = True
            params["grid_params"] = {
                name: {
                    "min": int(getattr(d, f"ml_rf_grid_{name}_min").value()),
                    "max": int(getattr(d, f"ml_rf_grid_{name}_max").value()),
                    "step": int(getattr(d, f"ml_rf_grid_{name}_step").value()),
                }
                for name in ("ntree", "mtry", "nodesize")
            }
        else:
            params.update(
                ntree=int(d.ml_rf_ntree.value()),
                mtry=int(d.ml_rf_mtry.value()),
                nodesize=int(d.ml_rf_nodesize.value()),
            )
        return params

    def _svm_params(self):
        d = self.dialog
        params = {"use_xy": bool(self.session.use_xy_features)}
        if d.ml_svm_grid_search.isChecked():
            params["use_grid_search"] = True
            # log2 semantics for C/gamma are handled inside the method.
            params["grid_params"] = {
                key: {
                    "min": float(getattr(d, f"ml_svm_{name}_min").value()),
                    "max": float(getattr(d, f"ml_svm_{name}_max").value()),
                    "step": float(getattr(d, f"ml_svm_{name}_step").value()),
                }
                for key, name in (("C", "c"), ("gamma", "gamma"), ("epsilon", "epsilon"))
            }
        else:
            params.update(
                C=float(d.ml_svm_c.value()),
                gamma=float(d.ml_svm_gamma.value()),
                epsilon=float(d.ml_svm_epsilon.value()),
            )
        return params

    def _rk_params(self):
        from ..core.variogram import normalize_model_token

        params = self._rf_params()
        text = self.dialog.rk_model_combo.currentText()
        if text.strip().lower().startswith("auto"):
            params["model"] = "exponential"
        else:
            params["model"] = normalize_model_token(text)
        return params

    def _params_for(self, key):
        if key == "rf":
            return self._rf_params()
        if key == "svm":
            return self._svm_params()
        return self._rk_params()

    # --------------------------------------------------------- training data
    def _data_with_covariates(self, data: TrainingData) -> TrainingData:
        """Training data with covariates sampled at the point coordinates;
        rows with any non-finite covariate are dropped (legacy behavior)."""
        paths = self.session.selected_covariate_paths()
        if not paths:
            return data
        cov = sample_covariates_at_points(paths, data.xy)
        finite = np.isfinite(cov).all(axis=1)
        if not finite.any():
            raise BFIError(
                "No sample points have values for every covariate raster. "
                "Check that the rasters cover the point layer extent."
            )
        return TrainingData(
            xy=data.xy[finite],
            values=np.asarray(data.values, dtype=float)[finite],
            covariates=cov[finite],
            covariate_names=tuple(self.session.covariate_selection),
            crs_authid=data.crs_authid,
        )

    # -------------------------------------------------------- interpolation
    def run_interpolation(self, key):
        handle = self._interp_handles[key]
        if handle.is_running():
            return
        try:
            data = self.session.require_training_data()
            if self.session.boundary_layer is None:
                raise BFIError("Select a boundary polygon in the Data tab first.")
            params = self._params_for(key)
            data_cov = self._data_with_covariates(data)
            grid = grid_from_layer(self.session.boundary_layer, self.session.pixel_size)
            wkts, _, _ = extract_boundary_wkts(self.session.boundary_layer)
            out_path = choose_raster_output_path(
                METHOD_TAGS[key], self.session.variable_field,
                exported=self.session.export_rasters,
            )
        except BFIError as exc:
            self.notify_warning(f"{METHOD_LABELS[key]} interpolation", str(exc))
            return

        worker = InterpolationWorker(
            data_cov, key, params, grid, wkts, out_path,
            covariate_paths=self.session.selected_covariate_paths(),
        )
        handle.launch(
            worker,
            on_result=lambda result: self._on_raster_done(key, result),
            on_failed=lambda msg: self.notify_error(
                f"{METHOD_LABELS[key]} interpolation failed", msg),
            on_dep_missing=lambda msg: self.notify_warning("Missing dependency", msg),
        )

    def _on_raster_done(self, key, result):
        try:
            layer_name = f"{METHOD_TAGS[key]} ({self.session.variable_field})"
            add_result_layer(result.path, layer_name, exported=self.session.export_rasters)
        except Exception as exc:
            logger.exception("Could not add result layer")
            self.notify_error(METHOD_LABELS[key], str(exc))
            return
        try:
            arr, grid = read_raster_grid(result.path)
            panel = self._map_panels[key]
            self.plots.raster_preview(
                panel.figure, arr, grid,
                title=f"{METHOD_LABELS[key]} — {self.session.variable_field}",
            )
            panel.canvas.draw_idle()
        except Exception:
            logger.exception("Preview rendering failed")
        self.session.store_fit(key, result)
        self.notify_status(METHOD_LABELS[key], f"Raster layer created: {result.path}")

    # ------------------------------------------------------------------ CV
    def run_cv(self, key):
        handle = self._cv_handles[key]
        if handle.is_running():
            return
        try:
            data = self._data_with_covariates(self.session.require_training_data())
            params = self._params_for(key)
            plan = read_cv_plan(self.dialog, CV_PREFIXES[key], data.n)
        except BFIError as exc:
            self.notify_warning(f"{METHOD_LABELS[key]} cross-validation", str(exc))
            return

        worker = CVWorker(data, key, params, plan)
        handle.launch(
            worker,
            on_result=lambda cv: self._on_cv_done(key, cv),
            on_failed=lambda msg: self.notify_error(
                f"{METHOD_LABELS[key]} cross-validation failed", msg),
            on_dep_missing=lambda msg: self.notify_warning("Missing dependency", msg),
        )

    def _on_cv_done(self, key, cv):
        fill_metrics_table(self._metrics_tables[key], cv.metrics)
        panel = self._val_panels[key]
        self.plots.obs_vs_pred(
            panel.figure, cv.observed, cv.predicted, cv.metrics,
            title=f"{METHOD_LABELS[key]} — {cv.plan.label()}",
        )
        panel.canvas.draw_idle()
        self.session.store_cv(key, cv)
        self.notify_status(
            METHOD_LABELS[key], f"Cross-validation ({cv.plan.label()}) finished."
        )

    # ---------------------------------------------------- variable importance
    def run_importance(self, key):
        handle = self._importance_handles[key]
        if handle.is_running():
            return
        try:
            data = self._data_with_covariates(self.session.require_training_data())
            params = self._params_for(key)
        except BFIError as exc:
            self.notify_warning(f"{METHOD_LABELS[key]} importance", str(exc))
            return

        worker = FitWorker(data, key, params)
        handle.launch(
            worker,
            on_result=lambda fit: self._on_importance_done(key, fit),
            on_failed=lambda msg: self.notify_error(
                f"{METHOD_LABELS[key]} fit failed", msg),
            on_dep_missing=lambda msg: self.notify_warning("Missing dependency", msg),
        )

    def _on_importance_done(self, key, fit):
        importances = fit.diagnostics.get("importances") or {}
        if importances:
            panel = self._importance_panels[key]
            self.plots.importance_bars(
                panel.figure, list(importances.keys()), list(importances.values())
            )
            panel.canvas.draw_idle()
        else:
            self.notify_warning(
                METHOD_LABELS[key], "The fitted model reported no variable importances."
            )
        if key == "rk":
            vgm = fit.diagnostics.get("variogram")
            report = getattr(vgm, "fit_report", None) or {}
            lags = report.get("lags")
            gamma = report.get("gamma")
            if vgm is not None and lags is not None and len(lags):
                d = self.dialog
                self.plots.variogram(
                    d.rk_vario_panel.figure, lags, gamma, vgm,
                    title="RF residual semivariogram",
                )
                d.rk_vario_panel.canvas.draw_idle()
        self.notify_status(METHOD_LABELS[key], "Model fit finished.")
