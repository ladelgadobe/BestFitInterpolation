"""Optional Universal Kriging and conditional uncertainty for both fit backends."""
from .localization import _message
from .localization import _dialog, _find_text, _new, _ui
import numpy as np
from qgis.PyQt.QtCore import Qt, QCoreApplication
from qgis.PyQt.QtWidgets import QComboBox, QLabel, QCheckBox, QHBoxLayout, QWidget, QProgressDialog, QMessageBox
from qgis.core import QgsProject
from .compat import enum_value, is_alive
from .grid_utils import build_inside_grid_points
from .kriging_universal import detrend_linear
from .kriging_workflow import fit_kriging_model, predict_kriging_fit, validate_kriging_model


UNCERTAINTY_DESCRIPTION = (
    "Conditional point-support kriging uncertainty, including estimation of the mean/trend. "
    "Variogram parameters are treated as fixed. The nugget represents variation at positive "
    "separation; observed sample locations are interpolated exactly. Measurement error is not "
    "modeled separately. This is not total uncertainty or a calibrated prediction interval.")


class GeostatisticsOptions:
    def __init__(self, *args, **kwargs):
        self._map_cache = None
        self._map_styles = {}
        self._last_map_style_key = None
        self._is_interpolating = False
        self._interpolate_btn = None
        super().__init__(*args, **kwargs)
        dlg = self.dlg
        if not hasattr(dlg, "cmbOKKrigingType"):
            panel = QWidget(dlg)
            panel.setObjectName("geostatisticsOptions21")
            row = QHBoxLayout(panel)
            row.setContentsMargins(0, 0, 0, 0)
            dlg.cmbOKKrigingType = QComboBox(panel)
            dlg.cmbOKKrigingType.setObjectName("cmbOKKrigingType")
            _ui(dlg.cmbOKKrigingType, 'addItems', ["Ordinary Kriging", "Universal Kriging (linear)"])
            row.addWidget(_new(QLabel, "Type:", panel))
            row.addWidget(dlg.cmbOKKrigingType)
            dlg.cmbOKMapOutput = QComboBox(panel)
            dlg.cmbOKMapOutput.setObjectName("cmbOKMapOutput")
            _ui(dlg.cmbOKMapOutput, 'addItems', ["Prediction", "Kriging standard deviation", "Kriging variance"])
            _ui(dlg.cmbOKMapOutput, 'setToolTip', UNCERTAINTY_DESCRIPTION)
            dlg.chkOKUncertaintyLayer = _new(QCheckBox, "Add SD layer", panel)
            dlg.chkOKUncertaintyLayer.setObjectName("chkOKUncertaintyLayer")
            dlg.chkOKUncertaintyLayer.setChecked(True)
            _ui(dlg.chkOKUncertaintyLayer, 'setToolTip', UNCERTAINTY_DESCRIPTION)
            row.addWidget(_new(QLabel, "Map:", panel))
            row.addWidget(dlg.cmbOKMapOutput)
            row.addWidget(dlg.chkOKUncertaintyLayer)
            # Only extend the existing bottom action row. Every original data,
            # model and parameter widget retains its parent, grid cell and order.
            button = dlg.btnOKInterpolate
            original_layout = button.parentWidget().layout()
            index = original_layout.indexOf(button)
            original_layout.removeWidget(button)
            original_layout.insertWidget(index, panel)
            row.addWidget(button, 1)
        self._connect(dlg.cmbOKKrigingType.currentIndexChanged, self._on_kriging_type_changed)
        self._connect(dlg.cmbOKMapOutput.currentIndexChanged, self._show_selected_map)
        self._update_trend_label()

    def trend_degree(self):
        combo = getattr(self.dlg, "cmbOKKrigingType", None)
        return 1 if combo is not None and combo.currentIndex() == 1 else 0

    def kriging_name(self):
        return "Universal Kriging" if self.trend_degree() else "Ordinary Kriging"

    def _update_trend_label(self):
        _ui(self.dlg.cmbOKKrigingType, 'setToolTip', "Linear spatial trend (X + Y); fit the residual covariance." if self.trend_degree()
                                           else "Ordinary Kriging: unknown constant mean.")

    def _on_kriging_type_changed(self, *_):
        if not self.is_dispatcher_active():
            return
        self._update_trend_label()
        window = getattr(self, "_advanced_dialog", None)
        if is_alive(window):
            window.close()
            window.deleteLater()
            self._advanced_dialog = None
        self.clear_plots()
        self._baseline_initial = self._baseline_last = self._init_params = None
        self._reml_fitted = False
        self._user_variogram_overrides = False
        self._semivariogram_stale = True
        plugin = getattr(self, "parent_plugin", None)
        if plugin is not None:
            plugin._last_ok_interpolation = None
            plugin._clear_ok_validation_outputs()
            result = getattr(plugin, "_last_interpolation_result", None)
            if result is not None and result.method in ("OK", "UK"):
                plugin._last_interpolation_result = plugin._last_interpolation_figure = None
        try:
            if self.points_layer is not None and self.z_field:
                self.calculate_and_plot_experimental(initial_load=True)
        except Exception as exc:
            _message(self.iface.messageBar().pushWarning, "Kriging", str(exc))

    def _bin_variogram(self, x, y, z, cutoff, lag_width):
        if self.trend_degree():
            z = detrend_linear(x, y, z)[0]
        return super()._bin_variogram(x, y, z, cutoff, lag_width)

    def _evaluate_model_cv(self, model_key, x, y, z, cutoff, lagw):
        if not self.trend_degree():
            return super()._evaluate_model_cv(model_key, x, y, z, cutoff, lagw)
        return validate_kriging_model(np.column_stack((x, y)), z, model_key,
            "REML" if self._use_reml else "MoM", 1, cutoff, lagw)[0]

    def _fit_reml_if_needed(self, x, y, z):
        if not self.trend_degree():
            return super()._fit_reml_if_needed(x, y, z)
        if not self._use_reml or self._reml_fitted:
            return
        fit = fit_kriging_model(np.column_stack((x, y)), z, self._get_selected_model(),
                                "REML", 1, self._cutoff, self._lag_width)
        self._init_params = tuple(fit[key] for key in ("nugget", "psill", "range"))
        self._programmatic_variogram_update = True
        try:
            for name, value in zip(("Nugget", "Psill", "Range"), self._init_params):
                getattr(self.dlg, "spinOK" + name).setValue(value)
        finally:
            self._programmatic_variogram_update = False
        self._reml_fitted = True
        self._ok_fit_method = "REML"
        self._semivariogram_stale = False
        self._update_headers(self.z_field, self._n, self._cutoff, self._lag_width)
        self._plot_with_model_if_possible()

    def _plot_with_model_if_possible(self):
        signature = (self.trend_degree(), self._get_selected_model(), *self._read_params_from_ui())
        if self._map_cache and self._map_cache.get("fit_signature") != signature:
            self._map_cache = None
            if self._krig_map_fig is not None:
                self._krig_map_fig.clear()
                self._krig_map_canvas.draw_idle()
            plugin = getattr(self, "parent_plugin", None)
            if plugin is not None:
                plugin._last_ok_interpolation = None
                plugin._clear_ok_validation_outputs()
        super()._plot_with_model_if_possible()
        if self.trend_degree() and self._krig_vario_fig is not None and self._krig_vario_fig.axes:
            self._krig_vario_fig.axes[0].set_title(
                "Residual semivariogram (REML)" if self._use_reml else "Residual semivariogram", fontsize=10)
            self._krig_vario_canvas.draw_idle()

    def _on_interpolate_clicked(self):
        if not self.is_dispatcher_active() or self._is_interpolating:
            return
        self._is_interpolating = True
        if self._interpolate_btn is not None:
            self._interpolate_btn.setEnabled(False)
        progress = None
        try:
            self._ensure_variogram_ready()
            self._sync_variogram_state_from_ui()
            self._ensure_inputs_from_ui()
            self._block_variogram_updates = True
            x, y, values = self._read_xy_z()
            if x is None:
                raise ValueError("At least five valid observations are required.")
            from .performance_policy import is_dense_dataset, dense_method_notice
            self._active_dense_notice = dense_method_notice(len(values), self.kriging_name()) if is_dense_dataset(len(values)) else ""
            polygon = self._resolve_polygon_layer()
            if polygon is None:
                raise ValueError("Select a polygon layer.")
            plugin = getattr(self, "parent_plugin", None)
            if plugin is not None and not plugin._validate_current_interpolation_coverage("Kriging"):
                return
            extent = polygon.extent()
            xmin, xmax, ymin, ymax = extent.xMinimum(), extent.xMaximum(), extent.yMinimum(), extent.yMaximum()
            pixel = self._resolve_pixel_size()
            if pixel is None or pixel <= 0:
                pixel = max(xmax - xmin, ymax - ymin) / 100.0
            cols, rows = max(1, int(np.ceil((xmax - xmin) / pixel))), max(1, int(np.ceil((ymax - ymin) / pixel)))
            targets, indices = build_inside_grid_points(
                xmin + pixel * (np.arange(cols) + 0.5), ymax - pixel * (np.arange(rows) + 0.5),
                lambda points: self._points_inside_polygon_mask(points, polygon))
            if not len(indices):
                raise ValueError("The grid does not fall within the polygon.")
            if len(indices) > 800000:
                _message(self.iface.messageBar().pushWarning, "Kriging", f"Many cells to predict ({len(indices):,}). Consider increasing the pixel size.")
            progress = _new(QProgressDialog, "Running " + self.kriging_name(), "Cancel", 0, len(targets), self.dlg)
            progress.setWindowModality(enum_value(Qt, "WindowModality", "ApplicationModal"))
            progress.setMinimumDuration(0)
            def update(done, total):
                progress.setValue(done)
                QCoreApplication.processEvents()
                if progress.wasCanceled():
                    raise InterruptedError("Interpolation cancelled")
            nugget, psill, scale = self._read_params_from_ui()
            backend = "REML" if self._use_reml else "MoM"
            fit = dict(model=self._get_selected_model(), nugget=nugget, psill=psill, range=scale,
                       trend_degree=self.trend_degree(), backend=backend, range_parameterization="model_scale")
            prediction, variance = predict_kriging_fit(np.column_stack((x, y)), values, targets, fit, True, update)
            if progress.wasCanceled():
                raise InterruptedError("Interpolation cancelled")
            maps = {}
            for name, data in (("prediction", prediction), ("variance", variance), ("std", np.sqrt(variance))):
                grid = np.full((rows, cols), np.nan)
                grid.ravel()[indices] = data
                maps[name] = grid
            # Plot the actual raster edge extent, including a partial last cell.
            self._map_cache = dict(maps=maps, bounds=(xmin, xmin + cols * pixel, ymax - rows * pixel, ymax),
                                   polygon=polygon, variable=self.z_field or "Z", kind=self.kriging_name(),
                                   fit_signature=(self.trend_degree(), fit["model"], nugget, psill, scale))
            self._maybe_export_ok_raster(maps["prediction"], xmin, xmax, ymin, ymax, pixel,
                                         polygon, self.z_field or "Z", fit["model"])
            prediction_path = getattr(self, "_last_output_path", None)
            # Always save the calculated components for preview/report. The
            # checkbox controls publication to the QGIS canvas only, as in RF/RK.
            uncertainty_paths = {}
            from osgeo import gdal
            for component, suffix, label in (("std", "sd", "Kriging standard deviation"),
                                              ("variance", "variance", "Kriging variance")):
                path = self._write_ok_raster(maps[component], xmin, xmax, ymin, ymax, pixel,
                    polygon, (self.z_field or "Z") + "_kriging_" + suffix, fit["model"])
                uncertainty_paths["kriging_" + component] = path
                dataset = gdal.Open(path, gdal.GA_Update)
                if dataset is not None:
                    for name, value in dict(BESTFIT_OUTPUT=label, BESTFIT_UNCERTAINTY=UNCERTAINTY_DESCRIPTION,
                            BESTFIT_TREND_DEGREE=self.trend_degree(),
                            BESTFIT_UNCERTAINTY_COMPONENT="kriging_" + component,
                            BESTFIT_UNCERTAINTY_DEFINITION=UNCERTAINTY_DESCRIPTION,
                            BESTFIT_PARENT_METHOD="UK" if self.trend_degree() else "OK",
                            BESTFIT_SOURCE_PREDICTION=prediction_path, BESTFIT_UNCERTAINTY_CALIBRATED="NO",
                            BESTFIT_UNITS="response_squared" if component == "variance" else "response").items():
                        dataset.SetMetadataItem(name, str(value))
                    dataset.GetRasterBand(1).SetDescription(label)
                    dataset = None
            uncertainty_path = uncertainty_paths["kriging_std"]
            canvas_outputs = []
            if self.dlg.chkOKUncertaintyLayer.isChecked():
                layer = self._create_output_raster_layer(uncertainty_path, self.kriging_name() + " SD (" + (self.z_field or "Z") + ")")
                self._mark_temporary_layer(layer, uncertainty_path)
                layer.setCustomProperty("bestfitinterpolator/uncertainty", UNCERTAINTY_DESCRIPTION)
                layer.setCustomProperty("bestfitinterpolator/output_kind", "uncertainty_component")
                layer.setCustomProperty("bestfitinterpolator/uncertainty_component", "kriging_std")
                layer.setCustomProperty("bestfitinterpolator/uncertainty_definition", UNCERTAINTY_DESCRIPTION)
                QgsProject.instance().addMapLayer(layer)
                canvas_outputs.append("kriging_std")
            self._last_output_path = prediction_path
            self._last_uncertainty_path = uncertainty_path
            self._show_selected_map()
            uncertainty_config = dict(uncertainty_path=uncertainty_path, uncertainty_definition=UNCERTAINTY_DESCRIPTION,
                uncertainty_paths=uncertainty_paths,
                uncertainty_definitions={key: UNCERTAINTY_DESCRIPTION for key in uncertainty_paths},
                uncertainty_canvas_outputs=canvas_outputs, uncertainty_calibrated=False)
            if plugin is not None:
                plugin._record_ok_interpolation(backend, self.points_layer.name(), self.z_field or "Z", polygon.name(),
                    pixel, np.column_stack((x, y, values)), fit["model"], nugget, psill, scale,
                    reml_fit=fit if backend == "REML" else None)
                plugin._last_ok_interpolation.update(trend_degree=self.trend_degree(),
                    kriging_type="UK" if self.trend_degree() else "OK", cutoff=self._cutoff, lag_width=self._lag_width,
                    **uncertainty_config,
                    model_selection="automatic" if self._is_auto_model_selection() else "fixed")
            config = dict(fit, variable=self.z_field or "Z", var_range=scale, pixel_size=pixel,
                          **uncertainty_config)
            from .interpolation_result import publish_result
            # Provenance/report always captures prediction, even when the UI displays SD.
            chosen = self.dlg.cmbOKMapOutput.currentIndex()
            self._show_selected_map(0)
            publish_result(self, "UK" if self.trend_degree() else "OK", config, self._krig_map_fig, raster_path=prediction_path)
            self._show_selected_map(chosen)
            _message(self.iface.messageBar().pushMessage, "Kriging", "Prediction and conditional uncertainty complete.", level=0)
        except InterruptedError as exc:
            _message(self.iface.messageBar().pushWarning, "Kriging", str(exc))
        except Exception as exc:
            _message(self.iface.messageBar().pushWarning, "Kriging", "Interpolation failed: " + str(exc))
        finally:
            if progress is not None:
                progress.close()
            self._block_variogram_updates = False
            self._is_interpolating = False
            if self._interpolate_btn is not None:
                self._interpolate_btn.setEnabled(True)

    def _show_selected_map(self, index=None):
        if not self.is_dispatcher_active() or not self._map_cache:
            return
        index = self.dlg.cmbOKMapOutput.currentIndex() if index is None else int(index)
        cache = self._map_cache
        if not is_alive(cache["polygon"]):
            return
        key = ("prediction", "std", "variance")[index]
        import copy
        display = getattr(self._krig_map_canvas, "_bfi_map_display", None)
        if display is not None:
            if self._last_map_style_key is not None:
                self._map_styles[self._last_map_style_key] = (copy.deepcopy(display.controls.state), display.controls._customized)
            # Prediction, SD and variance have different units/value ranges.
            # Do not apply the previous output's fixed limits to the new map.
            display.controls._customized = False
        label = cache["variable"] if index == 0 else cache["variable"] + (" — kriging SD" if index == 1 else "² — kriging variance")
        super()._plot_kriging_map(cache["maps"][key], *cache["bounds"], cache["polygon"], var_label=label)
        self._krig_map_fig._bfi_output_kind = 'prediction' if key == 'prediction' else 'kriging_' + key
        display = getattr(self._krig_map_canvas, "_bfi_map_display", None)
        if display is not None:
            saved = self._map_styles.get(key)
            if saved is None or not saved[1]:
                display.adopt_current(automatic=True)
            else:
                style, customized = saved
                controls = display.controls
                widgets = (controls.palette, controls.minimum, controls.maximum, controls.automatic, controls.scale)
                blocked = [widget.blockSignals(True) for widget in widgets]
                try:
                    palette_index = _find_text(controls.palette, style.palette, enum_value(Qt, "MatchFlag", "MatchFixedString"))
                    if palette_index >= 0: controls.palette.setCurrentIndex(palette_index)
                    controls.minimum.setValue(style.minimum); controls.maximum.setValue(style.maximum)
                    controls.automatic.setChecked(style.automatic); controls.scale.setValue(style.scale)
                    controls.minimum.setEnabled(not style.automatic); controls.maximum.setEnabled(not style.automatic)
                    controls.state = copy.deepcopy(style)
                    controls._customized = customized
                finally:
                    for widget, previous in zip(widgets, blocked): widget.blockSignals(previous)
                display.apply_current()
        self._last_map_style_key = key
        title = cache["kind"] if index == 0 else ("Kriging standard deviation" if index == 1 else "Kriging variance")
        self._krig_map_fig.axes[0].set_title(title, fontsize=10)
        self._krig_map_canvas.draw_idle()

    def _maybe_export_ok_raster(self, *args, **kwargs):
        super()._maybe_export_ok_raster(*args, **kwargs)
        path = getattr(self, "_last_output_path", None)
        if self.trend_degree() and path:
            for layer in QgsProject.instance().mapLayers().values():
                if layer.source().split("|")[0] == path:
                    layer.setName("UK " + self._get_selected_model().capitalize() + " (" + (self.z_field or "Z") + ")")

    def _krige_predict_python(self, x, y, z, grid_xy, model, nugget, psill, rng):
        fit = dict(model=model, nugget=nugget, psill=psill, range=rng, trend_degree=self.trend_degree())
        return predict_kriging_fit(np.column_stack((x, y)), z, grid_xy, fit)

    def clear_plots(self):
        self._map_cache = None
        self._last_uncertainty_path = None
        return super().clear_plots()


def run_universal_validation(plugin, state):
    from .kriging_workflow import automatic_test_folds
    sample = np.asarray(state["sample_xyz"], float)
    mode = getattr(plugin, "_cv_mode_ok", plugin.CV_AUTO)
    if mode == plugin.CV_AUTO:
        folds = automatic_test_folds(len(sample))
    elif mode == plugin.CV_LOOCV:
        folds = [np.array([i], int) for i in range(len(sample))]
    else:
        k = min(len(sample), max(2, int(plugin.spin_k_ok.value())))
        folds = plugin._make_kfold_indices(len(sample), k)
    progress = _new(QProgressDialog, "Validating Universal Kriging (training-fold refit)", "Cancel", 0, 0, plugin.dlg)
    progress.setMinimumDuration(0)
    progress.setWindowModality(enum_value(Qt, "WindowModality", "WindowModal"))
    def cancelled():
        QCoreApplication.processEvents()
        return progress.wasCanceled()
    try:
        metrics, prediction = validate_kriging_model(sample[:, :2], sample[:, 2], state["model"],
            state["backend"], 1, state.get("cutoff"), state.get("lag_width"), folds, cancelled)
        plugin._clear_ok_validation_outputs()
        plugin._ensure_canvases_attached()
        if plugin.ok_cv_fig is None or plugin.ok_cv_canvas is None:
            plugin._attach_ok_cv_canvas()
        for suffix, key in (("RMSE", "rmse"), ("RMSEpct", "rmse_pct"), ("MAE", "mae"),
                            ("R2", "r2"), ("PearsonR", "pearson"), ("LCCC", "lccc")):
            label = getattr(plugin.dlg, "valOK" + suffix, None)
            if label is not None:
                value = metrics[key]
                _ui(label, 'setText', (f"{value:.2f}%" if key == "rmse_pct" else f"{value:.3f}") if np.isfinite(value) else "—")
        description = f"UK {len(folds)}-fold validation — training-fold refit"
        plugin._plot_validation_scatter(sample[:, 2], prediction, fig=plugin.ok_cv_fig,
            canvas=plugin.ok_cv_canvas, title=description)
        plugin._last_ok_cv_result = dict(metrics, observed=sample[:, 2].tolist(), predicted=prediction.tolist(),
                                         validation_strategy="training_fold_refit", cv_desc=description)
    except Exception as exc:
        _dialog(QMessageBox.warning, plugin.dlg, "Universal Kriging validation", str(exc))
    finally:
        progress.close()
