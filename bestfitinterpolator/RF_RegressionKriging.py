# -*- coding: utf-8 -*-
"""
RF_RegressionKriging.py

Regression Kriging controller and helpers for the BestFitInterpolator plugin.

This module keeps the RK workflow independent from the main Random Forest tab:
1. Fit the Random Forest trend first.
2. Compute and fit the residual semivariogram.
3. Interpolate the final RK surface only after the user accepts the variogram.

All comments are in English. User-facing strings can be handled by the caller/UI.
"""

from __future__ import annotations

import inspect
import math
import os
import random
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.patches import Polygon as MplPolygon

from qgis.PyQt.QtCore import Qt, QCoreApplication
from qgis.PyQt.QtWidgets import QProgressDialog, QVBoxLayout, QFileDialog, QMenu, QDialog
from qgis.core import QgsProject
import matplotlib

from .RF_Interpolation import _tune_random_forest
from .kriging_ordinary import ordinary_kriging_interpolation
from .ml_bootstrap import ensure_ml_ready


@dataclass
class VariogramFit:
    """Container for one residual variogram fit."""
    model: str
    nugget: float
    psill: float
    range_: float
    sse: float
    weak_structure: bool = False


class RegressionKrigingRFController:
    """
    Standalone controller for the Regression Kriging tab.

    The controller expects three callbacks from the host plugin:
    - points_builder() -> (points_df, target_name, covariate_names)
    - grid_builder(covariate_names) -> (grid_df, grid_meta)
    - raster_writer(grid_df, grid_meta, target_name, pred_column, layer_title) -> optional path/identifier

    The callbacks allow this module to stay independent from the rest of the
    Machine Learning tab implementation.
    """

    def __init__(
        self,
        dlg,
        iface,
        points_builder: Callable[[], Tuple[pd.DataFrame, str, List[str]]],
        grid_builder: Callable[[List[str]], Tuple[pd.DataFrame, dict]],
        raster_writer: Optional[
            Callable[[pd.DataFrame, dict, str, str, str], Optional[str]]
        ] = None,
    ):
        self.dlg = dlg
        self.iface = iface
        self.project = QgsProject.instance()

        self.points_builder = points_builder
        self.grid_builder = grid_builder
        self.raster_writer = raster_writer

        # RK state
        self._train_df: Optional[pd.DataFrame] = None
        self._target_name: Optional[str] = None
        self._covariate_names: Optional[List[str]] = None
        self._rf_model = None
        self._rf_best_params: Optional[Dict[str, int]] = None
        self._rf_fit_config = None
        self._last_interpolation_config = None
        self._train_predictions: Optional[np.ndarray] = None
        self._residuals: Optional[np.ndarray] = None
        self._importance_df: Optional[pd.DataFrame] = None
        self._variogram_lags: Optional[np.ndarray] = None
        self._variogram_gamma: Optional[np.ndarray] = None
        self._variogram_fit: Optional[VariogramFit] = None
        self._grid_meta: Optional[dict] = None
        self._grid_df: Optional[pd.DataFrame] = None
        self._grid_with_pred: Optional[pd.DataFrame] = None
        self._cv_running = False
        self._rk_running = False

        # Plot holders
        self._imp_fig = None
        self._imp_canvas = None
        self._vario_fig = None
        self._vario_canvas = None
        self._map_fig = None
        self._map_canvas = None
        self._val_fig = None
        self._val_canvas = None

        self._rk_cv_auto = None
        self._rk_cv_loocv = None
        self._rk_cv_kfold = None
        self._rk_cv_k_spin = None
        self._save_handlers = set()

        self._init_canvases()
        self._init_mode_controls()
        self._set_rk_info_icon()
        self._wire_validation_controls()
        self._wire_signals()
        self._refresh_status()

    # ------------------------------------------------------------------
    # UI wiring
    # ------------------------------------------------------------------

    def _find_widget(self, names):
        for name in names:
            w = getattr(self.dlg, name, None)
            if w is not None:
                return w
        return None

    def _clear_layout(self, container):
        if container is None:
            return None
        layout = container.layout()
        if layout is None:
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            container.setLayout(layout)
        else:
            while layout.count():
                item = layout.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.setParent(None)
        return layout

    def _shorten_label(self, value: str, max_len: int = 28) -> str:
        txt = str(value)
        return txt if len(txt) <= max_len else txt[: max_len - 3] + "..."

    def _open_large_view_for_canvas(self, source_canvas, default_prefix: str):
        try:
            dlg = QDialog(self.dlg)
            dlg.setWindowTitle(default_prefix.replace("_", " ").title())
            layout = QVBoxLayout(dlg)
            fig2 = Figure()
            canvas2 = FigureCanvas(fig2)
            layout.addWidget(canvas2)

            if source_canvas is self._vario_canvas and self._variogram_lags is not None and self._variogram_gamma is not None:
                old_fig, old_canvas = self._vario_fig, self._vario_canvas
                self._vario_fig, self._vario_canvas = fig2, canvas2
                try:
                    self._draw_variogram_plot()
                finally:
                    self._vario_fig, self._vario_canvas = old_fig, old_canvas
            elif source_canvas is self._imp_canvas and self._importance_df is not None and not self._importance_df.empty:
                old_fig, old_canvas = self._imp_fig, self._imp_canvas
                self._imp_fig, self._imp_canvas = fig2, canvas2
                try:
                    self._draw_importance_plot()
                finally:
                    self._imp_fig, self._imp_canvas = old_fig, old_canvas
            elif source_canvas is self._map_canvas and self._grid_with_pred is not None and self._grid_meta is not None:
                old_fig, old_canvas = self._map_fig, self._map_canvas
                self._map_fig, self._map_canvas = fig2, canvas2
                try:
                    pred_col = None
                    for c in self._grid_with_pred.columns:
                        if str(c).endswith('_rk_pred'):
                            pred_col = c
                            break
                    if pred_col is not None:
                        self._draw_map_plot(pred_col)
                finally:
                    self._map_fig, self._map_canvas = old_fig, old_canvas
            elif source_canvas is self._val_canvas and self._val_fig is not None:
                self._val_fig.savefig('/mnt/data/_rk_val_preview_tmp.png', dpi=200, bbox_inches='tight')
                import matplotlib.image as mpimg
                img = mpimg.imread('/mnt/data/_rk_val_preview_tmp.png')
                ax2 = fig2.add_subplot(111)
                ax2.imshow(img)
                ax2.axis('off')
                canvas2.draw_idle()
            else:
                ax2 = fig2.add_subplot(111)
                ax2.text(0.5, 0.5, 'Preview unavailable', ha='center', va='center')
                ax2.axis('off')
                canvas2.draw_idle()

            dlg.resize(1000, 800)
            dlg.exec_()
        except Exception:  # nosec B110
            pass

    def _install_canvas_menu(self, canvas, fig, default_prefix: str):
        try:
            if canvas is None or fig is None:
                return
            key = id(canvas)
            if key in self._save_handlers:
                return
            canvas.setContextMenuPolicy(Qt.CustomContextMenu)

            def _show_menu(pos):
                menu = QMenu(self.dlg)
                act_save = menu.addAction("Save graph as PNG…")
                act_zoom = menu.addAction("Open larger view…")
                act_copy = menu.addAction("Copy graph")
                chosen = menu.exec_(canvas.mapToGlobal(pos))
                if chosen == act_save:
                    suggested = f"{default_prefix}.png"
                    path, _ = QFileDialog.getSaveFileName(self.dlg, "Save graph", suggested, "PNG Images (*.png)")
                    if path:
                        fig.savefig(path, dpi=300, bbox_inches='tight')
                elif chosen == act_copy:
                    self._copy_figure_to_clipboard(fig)
                elif chosen == act_zoom:
                    self._open_large_view_for_canvas(canvas, default_prefix)

            canvas.customContextMenuRequested.connect(_show_menu)
            self._save_handlers.add(key)
        except Exception:  # nosec B110
            pass

    def _copy_figure_to_clipboard(self, fig) -> None:
        """Copy a Matplotlib figure to the system clipboard as a PNG image."""
        try:
            import io
            from qgis.PyQt.QtGui import QPixmap
            from qgis.PyQt.QtWidgets import QApplication
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=300, bbox_inches="tight")
            pixmap = QPixmap()
            pixmap.loadFromData(buf.getvalue(), "PNG")
            QApplication.clipboard().setPixmap(pixmap)
        except Exception:  # nosec B110
            pass

    def _init_canvases(self):
        imp_container = self._find_widget(["RKImportance"])
        vario_container = self._find_widget(["RKVariogram"])
        map_container = self._find_widget(["RKMap"])
        val_container = self._find_widget(["canvasRKValidation"])

        if imp_container is not None:
            layout = self._clear_layout(imp_container)
            self._imp_fig = Figure()
            self._imp_canvas = FigureCanvas(self._imp_fig)
            layout.addWidget(self._imp_canvas)
            self._install_canvas_menu(self._imp_canvas, self._imp_fig, "rk_variable_importance")

        if vario_container is not None:
            layout = self._clear_layout(vario_container)
            self._vario_fig = Figure()
            self._vario_canvas = FigureCanvas(self._vario_fig)
            layout.addWidget(self._vario_canvas)
            self._install_canvas_menu(self._vario_canvas, self._vario_fig, "rk_residual_variogram")

        if map_container is not None:
            layout = self._clear_layout(map_container)
            self._map_fig = Figure()
            self._map_canvas = FigureCanvas(self._map_fig)
            layout.addWidget(self._map_canvas)
            self._install_canvas_menu(self._map_canvas, self._map_fig, "rk_map")

        if val_container is not None:
            layout = self._clear_layout(val_container)
            self._val_fig = Figure()
            self._val_canvas = FigureCanvas(self._val_fig)
            layout.addWidget(self._val_canvas)
            self._install_canvas_menu(self._val_canvas, self._val_fig, "rk_validation")

    def _init_mode_controls(self):
        self._rk_manual_widget = getattr(self.dlg, "chkRKUseManual", None)
        self._rk_grid_widget = getattr(self.dlg, "chkRKUseGrid", None)

        if self._rk_grid_widget is not None and hasattr(self._rk_grid_widget, "toggled"):
            self._rk_grid_widget.toggled.connect(
                lambda checked: self._on_mode_changed("grid", checked)
            )
        if self._rk_manual_widget is not None and hasattr(self._rk_manual_widget, "toggled"):
            self._rk_manual_widget.toggled.connect(
                lambda checked: self._on_mode_changed("manual", checked)
            )

        try:
            if self._rk_manual_widget is not None:
                self._rk_manual_widget.setChecked(True)
            if self._rk_grid_widget is not None:
                self._rk_grid_widget.setChecked(False)
        except Exception:  # nosec B110
            pass

        self._apply_mode()

    def _wire_validation_controls(self):
        self._rk_cv_auto = getattr(self.dlg, "radRK_CV_Auto", None)
        self._rk_cv_loocv = getattr(self.dlg, "radRK_CV_LOOCV", None)
        self._rk_cv_kfold = getattr(self.dlg, "radRK_CV_KFold", None)
        self._rk_cv_k_spin = getattr(self.dlg, "spinRK_k", None)

        def _refresh():
            try:
                if self._rk_cv_k_spin is not None:
                    enabled = bool(self._rk_cv_kfold is not None and self._rk_cv_kfold.isChecked())
                    self._rk_cv_k_spin.setEnabled(enabled)
            except Exception:  # nosec B110
                pass

        for w in (self._rk_cv_auto, self._rk_cv_loocv, self._rk_cv_kfold):
            if w is not None and hasattr(w, "toggled"):
                try:
                    w.toggled.connect(_refresh)
                except Exception:  # nosec B110
                    pass
        _refresh()

    def _reset_validation_metric_labels(self):
        for name in ("valRKRMSE", "valRKRMSEpct", "valRKMAE", "valRKR2", "valRKPearsonR", "valRKLCCC"):
            widget = getattr(self.dlg, name, None)
            if widget is not None and hasattr(widget, "setText"):
                try:
                    widget.setText("--")
                except Exception:  # nosec B110
                    pass

    def clear_plots(self):
        for fig_name, canvas_name in (
            ("_vario_fig", "_vario_canvas"),
            ("_imp_fig", "_imp_canvas"),
            ("_map_fig", "_map_canvas"),
            ("_val_fig", "_val_canvas"),
        ):
            fig = getattr(self, fig_name, None)
            canvas = getattr(self, canvas_name, None)
            try:
                if fig is not None:
                    fig.clear()
                if canvas is not None:
                    canvas.draw_idle()
            except Exception:  # nosec B110
                pass
        self._reset_validation_metric_labels()

    def _wire_signals(self):
        for name, handler in [
            ("btnRKFitRF", self._on_fit_rf_clicked),
            ("btnRKFitVariogram", self._on_fit_variogram_clicked),
            ("btnRKApplyVariogram", self._on_run_rk_clicked),
            ("btnRKRun", self._on_run_rk_clicked),
            ("btnRKRunCV", self._on_run_rk_cv_clicked),
        ]:
            w = getattr(self.dlg, name, None)
            if w is not None and hasattr(w, "clicked"):
                try:
                    w.clicked.connect(handler)
                except Exception:  # nosec B110
                    pass

        cmb = getattr(self.dlg, "cmbRKModel", None)
        if cmb is not None and hasattr(cmb, "currentIndexChanged"):
            cmb.currentIndexChanged.connect(self._redraw_variogram_only)

        for name in ("spinRKNugget", "spinRKPsill", "spinRKRange"):
            w = getattr(self.dlg, name, None)
            if w is not None and hasattr(w, "valueChanged"):
                w.valueChanged.connect(self._redraw_variogram_only)

    def _on_mode_changed(self, source: str, checked: bool):
        try:
            grid_on = bool(self._rk_grid_widget.isChecked()) if self._rk_grid_widget is not None else False
            manual_on = bool(self._rk_manual_widget.isChecked()) if self._rk_manual_widget is not None else True

            if source == "grid" and checked:
                if self._rk_manual_widget is not None:
                    self._rk_manual_widget.setChecked(False)
                grid_on, manual_on = True, False
            elif source == "manual" and checked:
                if self._rk_grid_widget is not None:
                    self._rk_grid_widget.setChecked(False)
                grid_on, manual_on = False, True

            if not grid_on and not manual_on and self._rk_manual_widget is not None:
                self._rk_manual_widget.setChecked(True)
        except Exception:  # nosec B110
            pass
        self._apply_mode()

    def _apply_mode(self):
        manual_on = True
        grid_on = False
        try:
            manual_on = bool(self._rk_manual_widget.isChecked()) if self._rk_manual_widget is not None else True
            grid_on = bool(self._rk_grid_widget.isChecked()) if self._rk_grid_widget is not None else False
        except Exception:  # nosec B110
            pass

        manual_widgets = [
            "spinRK_mtry_manual",
            "spinRK_ntree_manual",
            "spinRK_nodesize_manual",
        ]
        grid_widgets = [
            "spinRK_mtry_min",
            "spinRK_mtry_max",
            "spinRK_mtry_step",
            "spinRK_ntree_min",
            "spinRK_ntree_max",
            "spinRK_ntree_step",
            "spinRK_nodesize_min",
            "spinRK_nodesize_max",
            "spinRK_nodesize_step",
            "spinRKSearchK",
            "spinRKSearchIter",
            "btnInfoRKSearchK",
            "btnInfoRKSearchIter",
        ]

        for name in manual_widgets:
            w = getattr(self.dlg, name, None)
            if w is not None and hasattr(w, "setEnabled"):
                w.setEnabled(manual_on)

        for name in grid_widgets:
            w = getattr(self.dlg, name, None)
            if w is not None and hasattr(w, "setEnabled"):
                w.setEnabled(grid_on)

    def _make_info_label(self, object_name, tooltip_text):
        """Create one passive info icon label with the shared plugin icon."""
        existing = getattr(self, object_name, None)
        if existing is not None:
            return existing
        try:
            from qgis.PyQt.QtWidgets import QLabel
            from qgis.PyQt.QtGui import QPixmap
            from qgis.PyQt.QtCore import QSize
        except Exception:
            return None

        try:
            plugin_dir = os.path.dirname(os.path.abspath(__file__))
            icon_path = os.path.join(plugin_dir, "info.png")
            if not os.path.exists(icon_path):
                return None
            label = QLabel(self.dlg)
            label.setObjectName(object_name)
            pixmap = QPixmap(icon_path)
            if not pixmap.isNull():
                label.setPixmap(pixmap.scaled(16, 16, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            label.setToolTip(tooltip_text)
            label.setWhatsThis(tooltip_text)
            label.setFixedSize(QSize(18, 18))
            label.setCursor(Qt.ArrowCursor)
            setattr(self, object_name, label)
            return label
        except Exception:
            return None

    def _hide_legacy_info_buttons(self, names):
        """Hide older per-parameter info buttons after adding one consolidated icon."""
        for name in names:
            widget = getattr(self.dlg, name, None)
            if widget is None:
                continue
            try:
                widget.setToolTip("")
                widget.setWhatsThis("")
                widget.setEnabled(False)
                widget.setVisible(False)
            except Exception:  # nosec B110
                pass

    def _clear_widget_tooltips(self, names):
        """Keep parameter explanations centralized in the consolidated info icon."""
        for name in names:
            widget = getattr(self.dlg, name, None)
            if widget is None:
                continue
            try:
                widget.setToolTip("")
                widget.setWhatsThis("")
            except Exception:  # nosec B110
                pass

    def _set_rk_info_icon(self):
        """Install one consolidated Regression Kriging info icon."""
        tooltip = (
            "Regression Kriging parameters\n\n"
            "mtry: number of predictor variables randomly considered at each Random Forest split. "
            "Lower values increase tree diversity; higher values let each split use more predictors.\n\n"
            "ntree: number of trees in the Random Forest trend. More trees usually stabilize predictions, "
            "but increase processing time.\n\n"
            "nodesize: minimum number of samples allowed in a terminal node. Smaller values can capture local detail; "
            "larger values produce smoother trees.\n\n"
            "Search folds: number of cross-validation folds used to compare candidate RF parameter sets when "
            "Grid Search is enabled.\n\n"
            "Max iterations: maximum number of candidate parameter combinations tested during the RF search. More "
            "iterations explore the search space better, but are slower.\n\n"
            "Nugget: residual semivariance at very short distances, including measurement noise or micro-scale variation.\n\n"
            "Partial sill (C1): structured residual variance explained by spatial dependence.\n\n"
            "Range: distance where the residual spatial correlation becomes negligible."
        )
        label = self._make_info_label("_rk_parameters_info_label", tooltip)
        if label is not None:
            try:
                layout = getattr(self.dlg, "horizontalLayoutRKMode", None)
                if layout is not None:
                    layout.addWidget(label)
            except Exception:  # nosec B110
                pass
        self._hide_legacy_info_buttons(["btnInfoRKSearchK", "btnInfoRKSearchIter"])
        self._clear_widget_tooltips([
            "spinRK_mtry_manual", "spinRK_ntree_manual", "spinRK_nodesize_manual",
            "spinRK_mtry_min", "spinRK_mtry_max", "spinRK_mtry_step",
            "spinRK_ntree_min", "spinRK_ntree_max", "spinRK_ntree_step",
            "spinRK_nodesize_min", "spinRK_nodesize_max", "spinRK_nodesize_step",
            "spinRKSearchK", "spinRKSearchIter",
            "spinRKNugget", "spinRKPsill", "spinRKRange",
        ])

    # ------------------------------------------------------------------
    # Status + UI helpers
    # ------------------------------------------------------------------

    def _refresh_status(self):
        status = "RF not fitted"
        if self._rf_model is not None:
            status = "RF fitted"
        if self._variogram_fit is not None:
            status = "RF + residual variogram fitted"
        if self._grid_with_pred is not None:
            status = "Regression Kriging interpolated"

        lbl = getattr(self.dlg, "valRKStatus", None)
        if lbl is not None and hasattr(lbl, "setText"):
            lbl.setText(status)

        lbl_params = getattr(self.dlg, "valRKBestParams", None)
        if lbl_params is not None and hasattr(lbl_params, "setText"):
            if (self._rf_best_params is None) or (not self._is_using_grid_search()):
                lbl_params.setText("")
            else:
                lbl_params.setText(
                    "Best RF params: "
                    f"ntree={self._rf_best_params.get('ntree')}, "
                    f"mtry={self._rf_best_params.get('mtry')}, "
                    f"nodesize={self._rf_best_params.get('nodesize')}"
                )

        lbl_res = getattr(self.dlg, "valRKResidualInfo", None)
        if lbl_res is not None and hasattr(lbl_res, "setText"):
            if self._variogram_fit is None:
                lbl_res.setText("Residual variogram not fitted")
            else:
                weak = " | weak structure" if self._variogram_fit.weak_structure else ""
                lbl_res.setText(
                    f"{self._variogram_fit.model.capitalize()} | "
                    f"SSE={self._variogram_fit.sse:.4f}{weak}"
                )

    def _set_variogram_ui(self, fit: VariogramFit):
        cmb = getattr(self.dlg, "cmbRKModel", None)
        if cmb is not None:
            for i in range(cmb.count()):
                txt = (cmb.itemText(i) or "").strip().lower()
                if txt.startswith(fit.model[:3].lower()):
                    cmb.setCurrentIndex(i)
                    break

        for name, value in [
            ("spinRKNugget", fit.nugget),
            ("spinRKPsill", fit.psill),
            ("spinRKRange", fit.range_),
        ]:
            w = getattr(self.dlg, name, None)
            if w is not None and hasattr(w, "setValue"):
                try:
                    w.setValue(float(value))
                except Exception:  # nosec B110
                    pass

    def _read_variogram_ui(self) -> VariogramFit:
        model = self._get_model_token()
        nugget = float(getattr(self.dlg, "spinRKNugget").value())
        psill = float(getattr(self.dlg, "spinRKPsill").value())
        range_ = float(getattr(self.dlg, "spinRKRange").value())
        return VariogramFit(model=model, nugget=nugget, psill=psill, range_=max(range_, 1e-9), sse=np.nan)

    def _get_model_token(self) -> str:
        cmb = getattr(self.dlg, "cmbRKModel", None)
        txt = cmb.currentText().strip().lower() if cmb is not None else "exponential"
        if txt.startswith("sph"):
            return "spherical"
        if txt.startswith("gau"):
            return "gaussian"
        return "exponential"

    def _is_using_grid_search(self) -> bool:
        try:
            return bool(self._rk_grid_widget.isChecked()) if self._rk_grid_widget is not None else False
        except Exception:
            return False

    def _get_manual_params(self) -> Dict[str, int]:
        def _read(name, default):
            w = getattr(self.dlg, name, None)
            if w is not None and hasattr(w, "value"):
                try:
                    return int(w.value())
                except Exception:  # nosec B110
                    pass
            return int(default)

        return {
            "ntree": max(1, _read("spinRK_ntree_manual", 500)),
            "mtry": max(1, _read("spinRK_mtry_manual", 3)),
            "nodesize": max(1, _read("spinRK_nodesize_manual", 5)),
        }

    def _get_grid_params(self) -> Dict[str, Dict[str, int]]:
        def _read(name, default):
            w = getattr(self.dlg, name, None)
            if w is not None and hasattr(w, "value"):
                try:
                    return int(w.value())
                except Exception:  # nosec B110
                    pass
            return int(default)

        return {
            "ntree": {
                "min": max(1, _read("spinRK_ntree_min", 200)),
                "max": max(1, _read("spinRK_ntree_max", 800)),
                "step": max(1, _read("spinRK_ntree_step", 100)),
            },
            "mtry": {
                "min": max(1, _read("spinRK_mtry_min", 1)),
                "max": max(1, _read("spinRK_mtry_max", 10)),
                "step": max(1, _read("spinRK_mtry_step", 1)),
            },
            "nodesize": {
                "min": max(1, _read("spinRK_nodesize_min", 1)),
                "max": max(1, _read("spinRK_nodesize_max", 20)),
                "step": max(1, _read("spinRK_nodesize_step", 1)),
            },
        }

    def _get_search_folds(self) -> int:
        w = getattr(self.dlg, "spinRKSearchK", None)
        return max(2, int(w.value())) if w is not None and hasattr(w, "value") else 3

    def _get_search_iterations(self) -> int:
        w = getattr(self.dlg, "spinRKSearchIter", None)
        return max(1, int(w.value())) if w is not None and hasattr(w, "value") else 10

    # ------------------------------------------------------------------
    # Core RF stage
    # ------------------------------------------------------------------

    @staticmethod
    def _unique_columns(columns):
        seen = set()
        unique = []
        for col in columns:
            if col not in seen:
                seen.add(col)
                unique.append(col)
        return unique

    def _prepare_training_data(self):
        points_df, target_name, covariate_names = self.points_builder()
        if points_df is None or target_name is None or covariate_names is None:
            raise ValueError("Training data could not be prepared.")
        self._train_df = points_df.copy()
        self._target_name = target_name
        self._covariate_names = list(covariate_names)

    def _fit_rf_stage(self, progress_fn=None):
        self._prepare_training_data()
        cols = self._unique_columns(["x", "y"] + list(self._covariate_names) + [self._target_name])
        train_df = self._train_df[cols].dropna().copy()

        X = train_df[list(self._covariate_names)].to_numpy(dtype=float)
        y = train_df[self._target_name].to_numpy(dtype=float)

        use_grid_search = self._is_using_grid_search()
        manual_params = self._get_manual_params()
        grid_params = self._get_grid_params()
        search_folds = self._get_search_folds()
        search_iterations = self._get_search_iterations()

        sig = inspect.signature(_tune_random_forest)
        kwargs = dict(
            X=X,
            y=y,
            use_grid_search=use_grid_search,
            manual_params=manual_params,
            grid_params=grid_params,
            n_jobs=1,
            random_state=20,
            cv_folds=search_folds,
            max_iterations=search_iterations,
        )
        if "progress_fn" in sig.parameters:
            kwargs["progress_fn"] = progress_fn

        model, best_params = _tune_random_forest(**kwargs)
        pred = np.asarray(model.predict(X), dtype=float)
        residuals = y - pred

        self._rf_model = model
        self._rf_best_params = best_params if use_grid_search else None
        self._rf_fit_config = {
            "resolved_params": dict(best_params or manual_params),
            "search_mode": "grid" if use_grid_search else "manual",
            "grid_params": {
                key: dict(value) for key, value in grid_params.items()
            },
            "search_folds": int(search_folds),
            "search_iterations": int(search_iterations),
        }
        self._last_interpolation_config = None
        self._train_df = train_df
        self._train_predictions = pred
        self._residuals = residuals
        self._importance_df = pd.DataFrame(
            {
                "Variable": list(self._covariate_names),
                "Importance": np.asarray(model.feature_importances_, dtype=float),
            }
        ).sort_values("Importance", ascending=False).reset_index(drop=True)

        self._variogram_fit = None
        self._grid_with_pred = None
        self._draw_importance_plot()
        self._refresh_status()

    def _on_fit_rf_clicked(self):
        if not ensure_ml_ready(parent=self.dlg, method_name="Regression Kriging"):
            return

        progress = QProgressDialog("Fitting RF parameters…", "Cancel", 0, 0, self.dlg)
        progress.setWindowTitle("Regression Kriging")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        QCoreApplication.processEvents()

        def _progress(done, total, label=None):
            if label:
                progress.setLabelText(str(label))
            if total is None or total <= 0:
                progress.setRange(0, 0)
            else:
                progress.setRange(0, int(total))
                progress.setValue(int(done))
            QCoreApplication.processEvents()
            if progress.wasCanceled():
                raise KeyboardInterrupt("Canceled by user")

        try:
            self._fit_rf_stage(progress_fn=_progress)
            if self._residuals is not None and self._train_df is not None:
                progress.setLabelText("Fitting residual semivariogram…")
                progress.setRange(0, 0)
                QCoreApplication.processEvents()
                self._fit_variogram_stage()
                self._draw_variogram_plot()
                QCoreApplication.processEvents()
        except KeyboardInterrupt:
            self.iface.messageBar().pushMessage("Regression Kriging", "Canceled by the user.", level=1)
        except Exception as e:
            self.iface.messageBar().pushMessage("Regression Kriging", f"RF fitting failed: {e}", level=2)
        finally:
            progress.close()

    # ------------------------------------------------------------------
    # Variogram stage
    # ------------------------------------------------------------------

    @staticmethod
    def _pairwise_distances(x, y):
        n = x.size
        d = np.empty(n * (n - 1) // 2, dtype=float)
        k = 0
        for i in range(n - 1):
            dx = x[i + 1:] - x[i]
            dy = y[i + 1:] - y[i]
            m = np.hypot(dx, dy)
            d[k:k + m.size] = m
            k += m.size
        return d

    @staticmethod
    def _nearest_neighbor_dist(x, y):
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        n = x.size
        if n < 2:
            return np.nan
        scale = max(float(np.nanmax(np.abs(x))) if x.size else 0.0,
                    float(np.nanmax(np.abs(y))) if y.size else 0.0,
                    1.0)
        zero_tol = np.finfo(float).eps * scale * 32.0
        dmin = np.inf
        for i in range(n):
            dx = x - x[i]
            dy = y - y[i]
            dist = np.hypot(dx, dy)
            dist[i] = np.inf
            dist = dist[np.isfinite(dist) & (dist > zero_tol)]
            if dist.size == 0:
                continue
            dmin = min(dmin, float(np.min(dist)))
        return dmin if np.isfinite(dmin) else np.nan

    def _safe_lag_width(self, x, y, cutoff, lag_width, max_bins=10000):
        try:
            cutoff = float(cutoff)
        except Exception:
            cutoff = np.nan
        if not np.isfinite(cutoff) or cutoff <= 0:
            return np.nan
        try:
            lag_width = float(lag_width)
        except Exception:
            lag_width = np.nan
        if not np.isfinite(lag_width) or lag_width <= 0:
            lag_width = float(self._nearest_neighbor_dist(x, y))
        if not np.isfinite(lag_width) or lag_width <= 0:
            lag_width = cutoff / 12.0
        min_width = cutoff / float(max(1, int(max_bins)))
        if lag_width < min_width:
            lag_width = min_width
        return float(lag_width)

    def _bin_variogram(self, x, y, z, cutoff, lag_width):
        cutoff = float(cutoff)
        lag_width = self._safe_lag_width(x, y, cutoff, lag_width)
        if not np.isfinite(cutoff) or cutoff <= 0 or not np.isfinite(lag_width) or lag_width <= 0:
            return np.array([], dtype=float), np.array([], dtype=float)
        nbins = max(1, int(math.floor(cutoff / lag_width)))
        if nbins > 10000:
            nbins = 10000
            lag_width = cutoff / float(nbins)
        sums = np.zeros(nbins, dtype=float)
        counts = np.zeros(nbins, dtype=int)
        dists = np.zeros(nbins, dtype=float)

        n = x.size
        for i in range(n - 1):
            xi, yi, zi = x[i], y[i], z[i]
            xj = x[i + 1:]
            yj = y[i + 1:]
            zj = z[i + 1:]
            dd = np.hypot(xj - xi, yj - yi)
            mask = (dd > 0) & (dd <= cutoff)
            if not np.any(mask):
                continue
            dd = dd[mask]
            gj = 0.5 * (zi - zj[mask]) ** 2
            bin_idx = np.floor(dd / lag_width).astype(int)
            bin_idx[bin_idx == nbins] = nbins - 1
            for b, dval, gval in zip(bin_idx, dd, gj):
                sums[b] += gval
                counts[b] += 1
                dists[b] += dval

        valid = counts > 0
        default_centers = np.linspace(lag_width * 0.5, nbins * lag_width - lag_width * 0.5, nbins)
        lags = np.where(valid, dists / np.maximum(counts, 1), default_centers)
        gamma = np.where(valid, sums / np.maximum(counts, 1), np.nan)
        keep = ~np.isnan(gamma)
        return lags[keep], gamma[keep]

    def _guess_initial_params(self, lags, gamma, cutoff):
        if lags.size == 0:
            return 0.0, 1.0, max(1.0, cutoff * 0.4)
        nugget = float(max(0.0, np.nanmin(gamma[: max(1, min(3, gamma.size))])))
        plateau = float(np.nanmedian(gamma[-max(3, gamma.size // 4):]))
        sill_total = float(max(np.nanmax(gamma), plateau))
        sill_total = max(sill_total, nugget + 1e-6)
        target = 0.95 * sill_total
        idx = np.where(gamma >= target)[0]
        if idx.size > 0:
            rng = float(lags[idx[0]])
        else:
            rng = float(0.5 * cutoff)
        rng = max(rng, float(lags[0]) if lags.size else 1.0)
        return nugget, sill_total - nugget, rng

    def _model_func(self, h, model, nugget, psill, rng):
        h = np.asarray(h, dtype=float)
        c0 = float(nugget)
        c = float(psill)
        a = max(float(rng), 1e-9)
        if model == "spherical":
            hr = np.clip(h / a, 0.0, 1.0)
            sph = c * (1.5 * hr - 0.5 * (hr ** 3))
            return np.where(h <= a, c0 + sph, c0 + c)
        if model == "gaussian":
            return c0 + c * (1.0 - np.exp(-(h * h) / (a * a)))
        return c0 + c * (1.0 - np.exp(-h / a))

    def _fit_variogram_candidates(self, lags, gamma, cutoff) -> List[VariogramFit]:
        nugget0, psill0, range0 = self._guess_initial_params(lags, gamma, cutoff)
        candidates = []
        nugget_grid = [max(0.0, nugget0 * f) for f in (0.0, 0.5, 1.0, 1.5)]
        psill_grid = [max(1e-9, psill0 * f) for f in (0.5, 1.0, 1.5, 2.0)]
        range_grid = [max(1e-9, range0 * f) for f in (0.5, 0.75, 1.0, 1.25, 1.5)]
        weak_structure = False
        if gamma.size >= 3:
            head = float(np.nanmean(gamma[: min(3, gamma.size)]))
            tail = float(np.nanmean(gamma[-min(3, gamma.size):]))
            weak_structure = tail <= 0 or ((tail - head) / max(abs(tail), 1e-12) < 0.10)

        for model in ("spherical", "exponential", "gaussian"):
            best_fit = None
            for nugget in nugget_grid:
                for psill in psill_grid:
                    for range_ in range_grid:
                        theo = self._model_func(lags, model, nugget, psill, range_)
                        sse = float(np.nansum((gamma - theo) ** 2))
                        fit = VariogramFit(
                            model=model,
                            nugget=float(nugget),
                            psill=float(psill),
                            range_=float(range_),
                            sse=sse,
                            weak_structure=weak_structure,
                        )
                        if best_fit is None or fit.sse < best_fit.sse:
                            best_fit = fit
            if best_fit is not None:
                candidates.append(best_fit)
        return candidates

    def _fit_variogram_stage(self):
        if self._train_df is None or self._residuals is None:
            raise ValueError("Fit the RF stage before fitting the residual variogram.")

        x = self._train_df["x"].to_numpy(dtype=float)
        y = self._train_df["y"].to_numpy(dtype=float)
        z = np.asarray(self._residuals, dtype=float)

        all_d = self._pairwise_distances(x, y)
        cutoff = 0.5 * float(np.nanmax(all_d))
        lagw = self._safe_lag_width(x, y, cutoff, self._nearest_neighbor_dist(x, y))
        lags, gamma = self._bin_variogram(x, y, z, cutoff, lagw)

        if lags.size == 0:
            lags = np.array([0.0, cutoff], dtype=float)
            gamma = np.array([0.0, np.nanvar(z)], dtype=float)
        else:
            lags = np.insert(lags, 0, 0.0)
            gamma = np.insert(gamma, 0, 0.0)

        candidates = self._fit_variogram_candidates(lags[1:], gamma[1:], cutoff)
        if not candidates:
            raise ValueError("Residual variogram fitting failed.")

        fit = sorted(candidates, key=lambda item: item.sse)[0]
        self._variogram_lags = lags
        self._variogram_gamma = gamma
        self._variogram_fit = fit
        self._set_variogram_ui(fit)
        self._draw_variogram_plot()
        self._refresh_status()

    def _on_fit_variogram_clicked(self):
        try:
            self._fit_variogram_stage()
        except Exception as e:
            self.iface.messageBar().pushMessage("Regression Kriging", f"Residual variogram fitting failed: {e}", level=2)

    def _on_apply_variogram_clicked(self):
        try:
            self._variogram_fit = self._read_variogram_ui()
            self._draw_variogram_plot()
            self._refresh_status()
        except Exception as e:
            self.iface.messageBar().pushMessage("Regression Kriging", f"Invalid variogram parameters: {e}", level=2)

    # ------------------------------------------------------------------
    # RK interpolation stage
    # ------------------------------------------------------------------

    def _run_rk_prediction(self, progress_fn=None):
        if self._rf_model is None:
            raise ValueError("Fit the RF stage first.")
        if self._variogram_lags is None or self._variogram_gamma is None:
            raise ValueError("Fit the residual variogram first.")

        self._grid_df, self._grid_meta = self.grid_builder(self._covariate_names)
        if self._grid_df is None or self._grid_meta is None:
            raise ValueError("Interpolation grid could not be prepared.")

        grid_cols = self._unique_columns(["x", "y"] + list(self._covariate_names))
        grid_clean = self._grid_df[grid_cols].dropna().copy()
        X_grid = grid_clean[list(self._covariate_names)].to_numpy(dtype=float)

        if progress_fn is not None:
            progress_fn(20, 100, "Predicting RF trend on the interpolation grid…")

        rf_pred = np.asarray(self._rf_model.predict(X_grid), dtype=float)

        if progress_fn is not None:
            progress_fn(55, 100, "Kriging RF residuals on the interpolation grid…")

        fit = self._read_variogram_ui() if self._variogram_lags is not None else self._variogram_fit
        if fit is None:
            raise ValueError("Fit the residual variogram first.")
        self._variogram_fit = fit
        residual_pred = ordinary_kriging_interpolation(
            self._train_df["x"].to_numpy(dtype=float),
            self._train_df["y"].to_numpy(dtype=float),
            np.asarray(self._residuals, dtype=float),
            grid_clean["x"].to_numpy(dtype=float),
            grid_clean["y"].to_numpy(dtype=float),
            float(fit.nugget),
            float(fit.psill),
            float(fit.range_),
            {"spherical": "Sph", "exponential": "Exp", "gaussian": "Gau"}[fit.model],
        )

        final_pred = rf_pred + np.asarray(residual_pred, dtype=float)
        pred_col = f"{self._target_name}_rk_pred"
        grid_clean[pred_col] = final_pred

        merged = self._grid_df.copy()
        merged = pd.merge(
            merged,
            grid_clean[["x", "y", pred_col]],
            on=["x", "y"],
            how="left",
        )

        self._grid_with_pred = merged

        if self.raster_writer is not None:
            out_ref = self.raster_writer(
                merged,
                self._grid_meta,
                self._target_name,
                pred_col,
                "Regression Kriging",
            )
            if out_ref is None:
                try:
                    self.iface.messageBar().pushWarning(
                        "Regression Kriging",
                        "RK interpolation was computed, but the raster could not be exported to QGIS."
                    )
                except Exception:  # nosec B110
                    pass
                return

        if self._rf_fit_config is None:
            raise ValueError("The RF configuration used by Regression Kriging is unavailable.")
        self._last_interpolation_config = {
            "train_df": self._train_df.copy(deep=True),
            "target_name": str(self._target_name),
            "feature_names": list(self._covariate_names),
            "rf_params": dict(self._rf_fit_config["resolved_params"]),
            "rf_search_mode": self._rf_fit_config["search_mode"],
            "variogram_fit": VariogramFit(
                model=str(fit.model),
                nugget=float(fit.nugget),
                psill=float(fit.psill),
                range_=float(fit.range_),
                sse=float(fit.sse),
                weak_structure=bool(fit.weak_structure),
            ),
        }

        if progress_fn is not None:
            progress_fn(100, 100, "Regression Kriging interpolation completed.")

        self._draw_map_plot(pred_col)
        self._refresh_status()

    def _on_run_rk_clicked(self):
        if not ensure_ml_ready(parent=self.dlg, method_name="Regression Kriging"):
            return

        if self._rk_running:
            return
        self._rk_running = True

        progress = QProgressDialog("Running Regression Kriging…", "Cancel", 0, 100, self.dlg)
        progress.setWindowTitle("Regression Kriging")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        QCoreApplication.processEvents()

        def _progress(done, total, label=None):
            if label:
                progress.setLabelText(str(label))
            progress.setRange(0, int(total) if total else 100)
            progress.setValue(int(done))
            QCoreApplication.processEvents()
            if progress.wasCanceled():
                raise KeyboardInterrupt("Canceled by user")

        try:
            self._run_rk_prediction(progress_fn=_progress)
        except KeyboardInterrupt:
            self.iface.messageBar().pushMessage("Regression Kriging", "Canceled by the user.", level=1)
        except Exception as e:
            self.iface.messageBar().pushMessage("Regression Kriging", f"Interpolation failed: {e}", level=2)
        finally:
            progress.close()
            self._rk_running = False

    # ------------------------------------------------------------------
    # Cross-validation
    # ------------------------------------------------------------------

    def _get_cv_mode(self):
        try:
            if self._rk_cv_loocv is not None and self._rk_cv_loocv.isChecked():
                return "loocv"
            if self._rk_cv_kfold is not None and self._rk_cv_kfold.isChecked():
                return "kfold"
        except Exception:  # nosec B110
            pass
        return "auto"

    def _decide_auto_cv(self, n):
        if n <= 100:
            return "loocv", None
        if n <= 1000:
            return "kfold", 10
        return "kfold", 5

    def _make_kfold_indices(self, n, k):
        idx = list(range(n))
        random.Random(20).shuffle(idx)  # nosec B311
        folds = []
        base, rem = divmod(n, k)
        start = 0
        for i in range(k):
            size = base + (1 if i < rem else 0)
            folds.append(idx[start:start + size])
            start += size
        return folds

    def _rmse(self, obs, pred):
        valid = np.isfinite(obs) & np.isfinite(pred)
        if valid.sum() == 0:
            return float("nan")
        d = np.asarray(obs)[valid] - np.asarray(pred)[valid]
        return float(np.sqrt(np.mean(d ** 2)))

    def _rmse_pct(self, obs, pred):
        valid = np.isfinite(obs) & np.isfinite(pred)
        if valid.sum() == 0:
            return float("nan")
        obs_v = np.asarray(obs)[valid]
        mean_obs = float(np.mean(obs_v))
        if not np.isfinite(mean_obs) or abs(mean_obs) < 1e-12:
            return float("nan")
        return float(100.0 * self._rmse(obs, pred) / abs(mean_obs))

    def _mae(self, obs, pred):
        valid = np.isfinite(obs) & np.isfinite(pred)
        if valid.sum() == 0:
            return float("nan")
        return float(np.mean(np.abs(np.asarray(obs)[valid] - np.asarray(pred)[valid])))

    def _r2(self, obs, pred):
        valid = np.isfinite(obs) & np.isfinite(pred)
        if valid.sum() < 2:
            return float("nan")
        o = np.asarray(obs)[valid]
        p = np.asarray(pred)[valid]
        ss_res = float(np.sum((o - p) ** 2))
        ss_tot = float(np.sum((o - np.mean(o)) ** 2))
        if ss_tot <= 0:
            return float("nan")
        return float(1.0 - (ss_res / ss_tot))

    def _pearson_r(self, obs, pred):
        valid = np.isfinite(obs) & np.isfinite(pred)
        if valid.sum() < 2:
            return float("nan")
        o = np.asarray(obs)[valid]
        p = np.asarray(pred)[valid]
        if np.std(o) <= 0 or np.std(p) <= 0:
            return float("nan")
        return float(np.corrcoef(o, p)[0, 1])

    def _lccc(self, obs, pred):
        valid = np.isfinite(obs) & np.isfinite(pred)
        if valid.sum() < 2:
            return float("nan")
        o = np.asarray(obs)[valid]
        p = np.asarray(pred)[valid]
        mean_o = float(np.mean(o))
        mean_p = float(np.mean(p))
        std_o = float(np.std(o))
        std_p = float(np.std(p))
        cov_op = float(np.mean((o - mean_o) * (p - mean_p)))
        denom = std_o ** 2 + std_p ** 2 + (mean_o - mean_p) ** 2
        if not np.isfinite(denom) or abs(denom) < 1e-12:
            return float("nan")
        return float((2.0 * cov_op) / denom)

    def _update_validation_metrics_ui(self, rmse, lccc, rmse_pct, r2, mae, pearson_r):
        def _set(name, value):
            w = getattr(self.dlg, name, None)
            if w is not None and hasattr(w, "setText"):
                w.setText(value)

        def _fmt(v):
            return "—" if v is None or not np.isfinite(v) else f"{v:.3f}"

        _set("valRKRMSE", _fmt(rmse))
        _set("valRKLCCC", _fmt(lccc))
        _set("valRKRMSEpct", "—" if rmse_pct is None or not np.isfinite(rmse_pct) else f"{rmse_pct:.2f}")
        _set("valRKR2", _fmt(r2))
        _set("valRKMAE", _fmt(mae))
        _set("valRKPearsonR", _fmt(pearson_r))

    def _on_run_rk_cv_clicked(self):
        config = getattr(self, "_last_interpolation_config", None)
        if not config:
            self.iface.messageBar().pushWarning(
                "Regression Kriging validation",
                "Run the complete Regression Kriging interpolation first. Validation uses its exact predictors, RF parameters, and variogram.",
            )
            return

        if not ensure_ml_ready(parent=self.dlg, method_name="Regression Kriging"):
            return

        if self._cv_running:
            return
        self._cv_running = True
        self._reset_validation_metric_labels()

        progress = QProgressDialog("Preparing RK cross-validation…", "Cancel", 0, 0, self.dlg)
        progress.setWindowTitle("Regression Kriging CV")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        QCoreApplication.processEvents()

        try:
            target_name = config["target_name"]
            feature_names = list(config["feature_names"])
            cols = self._unique_columns(["x", "y"] + feature_names + [target_name])
            train_df = config["train_df"][cols].dropna().copy()
            if len(train_df) < 5:
                raise ValueError("At least 5 valid points are required for cross-validation.")

            X_all = train_df[feature_names].to_numpy(dtype=float)
            y_all = train_df[target_name].to_numpy(dtype=float)
            xy_all = train_df[["x", "y"]].to_numpy(dtype=float)
            n = len(y_all)

            mode = self._get_cv_mode()
            k = 10
            if self._rk_cv_k_spin is not None and hasattr(self._rk_cv_k_spin, "value"):
                k = int(self._rk_cv_k_spin.value())
            if mode == "auto":
                mode, k_auto = self._decide_auto_cv(n)
                if k_auto is not None:
                    k = k_auto

            if mode == "loocv":
                folds = [[i] for i in range(n)]
                cv_desc = f"RK LOOCV (n={n})"
            else:
                k = max(2, min(int(k), n))
                folds = self._make_kfold_indices(n, k)
                cv_desc = f"RK {k}-fold CV (n={n})"

            preds = np.full(n, np.nan, dtype=float)
            resolved_rf_params = dict(config["rf_params"])
            fixed_variogram_fit = config["variogram_fit"]
            total_folds = len(folds)
            progress.setRange(0, total_folds)

            for fold_idx, test_idx_list in enumerate(folds, start=1):
                if progress.wasCanceled():
                    raise KeyboardInterrupt("Canceled by user")

                progress.setValue(fold_idx - 1)
                progress.setLabelText(f"Running {cv_desc} — fold {fold_idx}/{total_folds}…")
                QCoreApplication.processEvents()

                test_idx = np.asarray(test_idx_list, dtype=int)
                train_mask = np.ones(n, dtype=bool)
                train_mask[test_idx] = False

                X_train = X_all[train_mask]
                y_train = y_all[train_mask]
                xy_train = xy_all[train_mask]
                X_test = X_all[test_idx]
                xy_test = xy_all[test_idx]

                model, _ = _tune_random_forest(
                    X=X_train,
                    y=y_train,
                    use_grid_search=False,
                    manual_params=resolved_rf_params,
                    grid_params={},
                    n_jobs=1,
                    random_state=20,
                    cv_folds=2,
                    max_iterations=1,
                    progress_fn=None,
                )

                rf_train_pred = np.asarray(model.predict(X_train), dtype=float)
                residuals_train = y_train - rf_train_pred

                rf_test_pred = np.asarray(model.predict(X_test), dtype=float)
                residual_test_pred = ordinary_kriging_interpolation(
                    xy_train[:, 0],
                    xy_train[:, 1],
                    residuals_train,
                    xy_test[:, 0],
                    xy_test[:, 1],
                    float(fixed_variogram_fit.nugget),
                    float(fixed_variogram_fit.psill),
                    float(fixed_variogram_fit.range_),
                    {"spherical": "Sph", "exponential": "Exp", "gaussian": "Gau"}[fixed_variogram_fit.model],
                )
                preds[test_idx] = rf_test_pred + np.asarray(residual_test_pred, dtype=float)

            progress.setValue(total_folds)
            progress.setLabelText("Computing RK validation metrics…")
            QCoreApplication.processEvents()

            rmse = self._rmse(y_all, preds)
            lccc = self._lccc(y_all, preds)
            rmse_pct = self._rmse_pct(y_all, preds)
            r2 = self._r2(y_all, preds)
            mae = self._mae(y_all, preds)
            pearson_r = self._pearson_r(y_all, preds)
            self._last_rk_cv_result = {
                "observed": np.asarray(y_all, dtype=float).tolist(),
                "predicted": np.asarray(preds, dtype=float).tolist(),
                "rmse": rmse,
                "lccc": lccc,
                "rmse_pct": rmse_pct,
                "r2": r2,
                "mae": mae,
                "pearson_r": pearson_r,
            }

            self._update_validation_metrics_ui(rmse, lccc, rmse_pct, r2, mae, pearson_r)
            self._draw_validation_plot(y_all, preds, cv_desc)

        except KeyboardInterrupt:
            self.iface.messageBar().pushMessage("Regression Kriging", "Canceled by the user.", level=1)
        except Exception as e:
            self.iface.messageBar().pushMessage("Regression Kriging", f"Cross-validation failed: {e}", level=2)
        finally:
            progress.close()
            self._cv_running = False

    # ------------------------------------------------------------------
    # Plotting
    # ------------------------------------------------------------------

    def _draw_importance_plot(self):
        if self._imp_fig is None or self._imp_canvas is None or self._importance_df is None or self._importance_df.empty:
            return
        df = self._importance_df.copy().sort_values("Importance", ascending=True)
        labels = [self._shorten_label(v, 30) for v in df["Variable"]]
        values = df["Importance"].to_numpy(dtype=float)

        self._imp_fig.clear()
        ax = self._imp_fig.add_subplot(111)
        y_pos = np.arange(len(labels))
        if len(values) > 1:
            rng = float(np.max(values) - np.min(values))
            norm_vals = np.full(len(values), 0.7, dtype=float) if rng <= 0 else (values - np.min(values)) / rng
        else:
            norm_vals = np.array([0.7], dtype=float)
        colors = matplotlib.cm.viridis(norm_vals)
        ax.barh(y_pos, values, color=colors, edgecolor="black", linewidth=0.4)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, fontsize=8)
        ax.set_xlabel("Importance")
        ax.set_title("RF variable importance")
        ax.grid(axis="x", alpha=0.25)
        self._imp_fig.subplots_adjust(left=0.34, right=0.97, top=0.90, bottom=0.12)
        self._imp_canvas.draw_idle()

    def _draw_variogram_plot(self):
        if self._vario_fig is None or self._vario_canvas is None:
            return
        if self._variogram_lags is None or self._variogram_gamma is None:
            return

        fit = self._read_variogram_ui() if self._variogram_lags is not None else self._variogram_fit

        self._vario_fig.clear()
        ax = self._vario_fig.add_subplot(111)
        plot_lags = self._variogram_lags[1:] if (self._variogram_lags is not None and self._variogram_lags.size > 1) else self._variogram_lags
        plot_gamma = self._variogram_gamma[1:] if (self._variogram_gamma is not None and self._variogram_gamma.size > 1) else self._variogram_gamma
        ax.plot(plot_lags, plot_gamma, "o", color="#2f0dee", label="Experimental")
        xmax = max(float(np.nanmax(plot_lags)), float(fit.range_), 1.0)
        h = np.linspace(0.0, xmax, 200)
        ax.plot(
            h,
            self._model_func(h, fit.model, fit.nugget, fit.psill, fit.range_),
            "-",
            color="black",
            linewidth=2,
            label=f"{fit.model.capitalize()}",
        )
        ax.set_title("Residual semivariogram")
        ax.set_xlabel("Lag distance (h)")
        ax.set_ylabel("Semivariance γ(h)")
        ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.6)
        ax.legend(frameon=False, fontsize=8)
        self._vario_fig.subplots_adjust(left=0.16, right=0.97, top=0.88, bottom=0.18)
        self._vario_canvas.draw_idle()

    def _redraw_variogram_only(self, *args):
        try:
            if self._variogram_lags is not None and self._variogram_gamma is not None:
                self._draw_variogram_plot()
        except Exception:  # nosec B110
            pass

    def _draw_map_plot(self, pred_col: str):
        if self._map_fig is None or self._map_canvas is None or self._grid_with_pred is None or self._grid_meta is None:
            return

        xmin = float(self._grid_meta["xmin"])
        xmax = float(self._grid_meta["xmax"])
        ymin = float(self._grid_meta["ymin"])
        ymax = float(self._grid_meta["ymax"])
        n_cols = int(self._grid_meta["n_cols"])
        n_rows = int(self._grid_meta["n_rows"])
        pixel_size = float(self._grid_meta["pixel_size"])
        poly_layer = self._grid_meta["poly_layer"]

        raster_array = np.full((n_rows, n_cols), np.nan, dtype=np.float32)
        xs = self._grid_with_pred["x"].to_numpy(dtype=float)
        ys = self._grid_with_pred["y"].to_numpy(dtype=float)
        vals = self._grid_with_pred[pred_col].to_numpy(dtype=float)

        for x, y, v in zip(xs, ys, vals):
            col = int((x - xmin) / pixel_size)
            row = int((ymax - y) / pixel_size)
            if 0 <= col < n_cols and 0 <= row < n_rows:
                raster_array[row, col] = float(v)

        self._map_fig.clear()
        ax = self._map_fig.add_subplot(111)
        x_edges = np.linspace(xmin, xmax, n_cols + 1)
        y_edges = np.linspace(ymin, ymax, n_rows + 1)
        disp_array = np.flipud(raster_array)
        masked = np.ma.masked_invalid(disp_array)

        pm = ax.pcolormesh(x_edges, y_edges, masked, cmap="viridis", shading="auto")
        cbar = self._map_fig.colorbar(pm, ax=ax, orientation="vertical")
        cbar.set_label(self._target_name or "Prediction")

        try:
            for feat in poly_layer.getFeatures():
                geom = feat.geometry()
                if geom.isMultipart():
                    for part in geom.asMultiPolygon():
                        for ring in part:
                            ring_xy = [(pt.x(), pt.y()) for pt in ring]
                            ax.add_patch(MplPolygon(ring_xy, closed=True, edgecolor="black", facecolor="none", linewidth=1.0))
                else:
                    for ring in geom.asPolygon():
                        ring_xy = [(pt.x(), pt.y()) for pt in ring]
                        ax.add_patch(MplPolygon(ring_xy, closed=True, edgecolor="black", facecolor="none", linewidth=1.0))
        except Exception:  # nosec B110
            pass

        ax.set_title("Regression Kriging")
        ax.set_xlim(xmin, xmax)
        ax.set_ylim(ymin, ymax)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel("X")
        ax.set_ylabel("Y")
        try:
            self._map_fig.tight_layout()
        except Exception:  # nosec B110
            pass
        self._map_canvas.draw_idle()

    def _draw_validation_plot(self, obs, pred, title):
        if self._val_fig is None or self._val_canvas is None:
            return
        self._val_fig.clear()
        ax = self._val_fig.add_subplot(111)

        obs = np.asarray(obs, dtype=float)
        pred = np.asarray(pred, dtype=float)
        valid = np.isfinite(obs) & np.isfinite(pred)
        obs_valid = obs[valid]
        pred_valid = pred[valid]

        if len(obs_valid) >= 1 and len(pred_valid) >= 1:
            vmin = float(min(np.min(obs_valid), np.min(pred_valid)))
            vmax = float(max(np.max(obs_valid), np.max(pred_valid)))
        else:
            vmin, vmax = 0.0, 1.0
        if not np.isfinite(vmin) or not np.isfinite(vmax) or vmin == vmax:
            vmin, vmax = 0.0, 1.0
        pad = 0.02 * (vmax - vmin if vmax > vmin else 1.0)
        vmin -= pad
        vmax += pad

        ax.scatter(obs_valid, pred_valid, s=24, alpha=0.9, facecolors="none", edgecolors="black", label="Data")
        ax.plot([vmin, vmax], [vmin, vmax], "-", color="black", linewidth=1.0, label="1:1")
        if len(obs_valid) >= 2:
            m, b = np.polyfit(obs_valid, pred_valid, 1)
            ax.plot([vmin, vmax], [m * vmin + b, m * vmax + b], "-", color="#d62728", linewidth=1.0, label="Fit")
        ax.set_xlim(vmin, vmax)
        ax.set_ylim(vmin, vmax)
        try:
            ax.set_box_aspect(1)
        except Exception:
            ax.set_aspect("equal", adjustable="box")
        ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.6)
        ax.tick_params(axis="both", labelsize=7)
        ax.set_xlabel("Observed", fontsize=8)
        ax.set_ylabel("Predicted", fontsize=8)
        ax.set_title(title, fontsize=8)
        ax.legend(loc="best", frameon=False, fontsize=8)
        try:
            self._val_fig.tight_layout()
        except Exception:  # nosec B110
            pass
        self._val_canvas.draw_idle()
