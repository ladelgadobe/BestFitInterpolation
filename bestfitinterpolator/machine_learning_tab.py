# -*- coding: utf-8 -*-
"""
machine_learning_tab.py

Logic for the Machine Learning → Covariables tab.
- Load covariate rasters from combo to list
- Optional resampling (bilinear) to a target pixel size
- Standardization (None, Z-score, -1 to 1)
- Pearson correlation matrix with the selected variable from the Data tab
- Lower triangular correlation heatmap using a red-white-blue scale centered at zero
- Export correlation matrix as CSV
- Extraction of covariate values at sampling points
- Display of extracted table in a popup window
- Clear covariate list
- Export standardized and resampled rasters back to QGIS

All code comments are in English. User-facing messages are in English.
"""

import os
import tempfile
import csv
import math
import uuid  # <- for RF raster filenames
import inspect  # <- NEW: optional progress callback support
import random

import numpy as np
import matplotlib
from matplotlib.colors import TwoSlopeNorm
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.path import Path  # <- for polygon masking
from matplotlib.patches import Polygon as MplPolygon
from osgeo import gdalconst
import pandas as pd

from qgis.PyQt.QtWidgets import (
    QVBoxLayout,
    QFileDialog,
    QMessageBox,
    QDialog,
    QTableWidget,
    QTableWidgetItem,
    QProgressDialog,
            QMenu,
            QCheckBox,
            QDialogButtonBox,
)
from qgis.PyQt.QtCore import Qt, QCoreApplication
from qgis.core import (
    QgsProject,
    QgsMapLayer,
    QgsRasterLayer,
    QgsPointXY,
    QgsCoordinateTransform,
)

from osgeo import gdal, osr

from .ml_bootstrap import ensure_ml_ready

try:
    from statistics import NormalDist
except Exception:
    NormalDist = None

# Optional ML dependency state
RF_AVAILABLE = None
RF_IMPORT_ERROR = ""

SVM_AVAILABLE = None
SVM_IMPORT_ERROR = ""


class BestFitTemporaryRasterLayer(QgsRasterLayer):
    """Raster layer wrapper used so QGIS can identify plugin temp outputs."""
    def isTemporary(self):
        return True


# Critical t-values (two-tailed, alpha=0.05)
_T_CRIT_TWO_TAILED_0_05 = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.080,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.060,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
    30: 2.042,
}
_Z_CRIT_0_05 = 1.959963984540054

# Ensure we use the Qt5 backend (generally already set by QGIS, but just in case)
matplotlib.use("Qt5Agg")


class MachineLearningTabController:
    """
    Controller for the Machine Learning tab (covariates + RF interpolation).
    """

    def __init__(self, dlg, iface):
        # Main plugin dialog and QGIS iface
        self.dlg = dlg
        self.iface = iface

        # QGIS project instance
        self.project = QgsProject.instance()

        # Mapping from covariate name (list item text) to QgsRasterLayer
        self.covariate_layers = {}

        # Storage for the latest correlation matrix and variable names
        self._last_corr_matrix = None
        self._last_corr_names = None
        self._last_sample_count = None

        # Matplotlib figure & canvas for the correlation plot
        self._corr_fig = None
        self._corr_canvas = None
        self._corr_ax = None

        # Matplotlib figures & canvases for RF previews
        self._rf_map_fig = None
        self._rf_map_canvas = None
        self._rf_map_ax = None
        self._rf_imp_fig = None
        self._rf_imp_canvas = None
        self._rf_imp_ax = None
        self._rf_val_fig = None
        self._rf_val_canvas = None
        self._rf_val_ax = None
        self._rf_last_map_payload = None
        self._rf_last_importance_df = None
        self._last_rf_interpolation_config = None
        self._last_svm_interpolation_config = None

        self._rf_cv_auto = None
        self._rf_cv_loocv = None
        self._rf_cv_kfold = None
        self._rf_cv_k_spin = None

        # Temporary directory for resampled/standardized rasters
        self._tmp_dir = tempfile.mkdtemp(prefix="bestfit_ml_cov_")

        # Storage for extracted covariate table
        self._extracted_headers = None
        self._extracted_rows = None

        # Flag to control whether extraction should standardize covariate values
        self._standardization_for_extraction = False
        self._active_covariate_selection = None

        # Init UI-related stuff
        self._init_raster_combo()
        self._init_corr_plot_canvas()
        self._init_rf_plot_canvases()
        self._init_rf_validation_canvas()
        self._connect_signals()

        # Pixel-size sync flags
        self._target_pixel_initialized = False
        # Initialize pixel display from Data tab and set default target once
        try:
            self._sync_pixel_size_from_data(set_target_default=True)
        except Exception:
            pass

        # --- RF controls (grid search vs manual) ---
        self._rf_grid_widget = None
        self._rf_manual_widget = None
        self._rf_manual_container = None
        self._rf_grid_container = None
        self._init_rf_mode_controls()
        self._set_rf_info_icons()

        # --- SVM controls ---
        self._svm_map_fig = None
        self._svm_map_canvas = None
        self._svm_map_ax = None
        self._svm_last_map_payload = None
        self._svm_val_fig = None
        self._svm_val_canvas = None
        self._svm_val_ax = None
        self._svm_manual_widget = None
        self._svm_grid_widget = None
        self._init_svm_plot_canvases()
        self._init_svm_mode_controls()
        self._set_svm_ui_decimals()
        self._set_svm_info_icons()
        try:
            self._connect_svm_signals()
        except Exception:
            pass

        # React to changes in Data tab pixel size by updating the display only
        try:
            if hasattr(self.dlg, "spinPixelSize") and hasattr(
                self.dlg.spinPixelSize, "valueChanged"
            ):
                self.dlg.spinPixelSize.valueChanged.connect(
                    lambda v: self._sync_pixel_size_from_data(
                        set_target_default=False
                    )
                )
        except Exception:
            pass

        # RF: connect interpolation button and any RF-specific controls
        try:
            self._connect_rf_signals()
            self._wire_rf_cv_controls()
        except Exception:
            # We do not want RF wiring to break the whole tab in case of a UI mismatch
            pass

    # -------------------------------------------------------------------------
    # UI wiring
    # -------------------------------------------------------------------------

    def _init_raster_combo(self):
        """Populate the covariate raster combo with raster layers from the project."""
        combo = self.dlg.cmbMLRaster
        combo.clear()

        for layer in self.project.mapLayers().values():
            if isinstance(layer, QgsRasterLayer):
                combo.addItem(layer.name(), layer.id())

    def refresh_raster_combo(self):
        """Public helper to refresh raster combo if project layers change."""
        self._init_raster_combo()

    def _get_data_pixel_size(self, default=0.01) -> float:
        """Return pixel size from the Data tab spin box, or a default value."""
        try:
            if hasattr(self.dlg, "spinPixelSize") and hasattr(
                self.dlg.spinPixelSize, "value"
            ):
                return float(self.dlg.spinPixelSize.value())
        except Exception:
            pass
        return float(default)

    def _sync_pixel_size_from_data(self, set_target_default: bool = False):
        """
        Update px_import label to reflect Data tab pixel size and optionally seed
        the target pixel size spin box.
        - set_target_default=True will set spinTargetPixelSize only once
          (first call) so user can override later.
        """
        px = self._get_data_pixel_size()
        # Update display label (no decimals)
        try:
            if hasattr(self.dlg, "px_import") and hasattr(
                self.dlg.px_import, "setText"
            ):
                self.dlg.px_import.setText(f"{px:.0f}")
        except Exception:
            pass
        # Seed target pixel size only once as default, still editable
        if set_target_default and not self._target_pixel_initialized:
            try:
                if hasattr(self.dlg, "spinTargetPixelSize") and hasattr(
                    self.dlg.spinTargetPixelSize, "setValue"
                ):
                    self.dlg.spinTargetPixelSize.setValue(px)
                    self._target_pixel_initialized = True
            except Exception:
                pass

    def _connect_signals(self):
        """Connect signals from the Machine Learning → Covariables tab."""
        # Load / remove / clear covariates
        self.dlg.btnMLLoadRaster.clicked.connect(self._on_add_covariate)
        self.dlg.btnRemoveCovariates.clicked.connect(
            self._on_remove_selected_covariates
        )
        if hasattr(self.dlg, "btnClear"):
            self.dlg.btnClear.clicked.connect(self._on_clear_covariates)

        # Processing
        self.dlg.btnResampleCovariates.clicked.connect(
            self._on_resample_covariates
        )
        self.dlg.btnApplyStandardization.clicked.connect(
            self._on_apply_standardization_clicked
        )

        # Correlations
        self.dlg.btnComputeCorrelations.clicked.connect(
            self._on_compute_correlations_clicked
        )
        if hasattr(self.dlg, "btnExportCorrCSV"):
            self.dlg.btnExportCorrCSV.clicked.connect(
                self._on_export_correlations_csv
            )

        # Extraction buttons
        if hasattr(self.dlg, "BtnExtract"):
            self.dlg.BtnExtract.clicked.connect(
                self._on_extract_covariates_clicked
            )
        if hasattr(self.dlg, "BtnExtracted"):
            self.dlg.BtnExtracted.clicked.connect(
                self._on_show_extracted_table_clicked
            )

    def _init_corr_plot_canvas(self):
        """
        Create a matplotlib FigureCanvas inside the CorPlot placeholder widget.

        We do NOT create an Axes or draw anything here, so the area stays blank
        until the user clicks "Compute correlations".
        """
        container = self.dlg.CorPlot

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

        self._corr_fig = Figure()
        self._corr_canvas = FigureCanvas(self._corr_fig)
        self._corr_ax = None
        layout.addWidget(self._corr_canvas)

        # Install right-click menu (save PNG / zoom)
        self._install_corr_canvas_menu()

    def _init_rf_validation_canvas(self):
        """Create the matplotlib canvas used for RF cross-validation."""
        container = getattr(self.dlg, "canvasRFValidation", None)
        if container is None:
            container = getattr(self.dlg, "CV_RF_widget", None)
        if container is None:
            return

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

        self._rf_val_fig = Figure()
        self._rf_val_canvas = FigureCanvas(self._rf_val_fig)
        self._rf_val_ax = None
        layout.addWidget(self._rf_val_canvas)

    def _wire_rf_cv_controls(self):
        """Wire RF validation controls and connect the CV button."""
        self._rf_cv_auto = getattr(self.dlg, "radRF_CV_Auto", None)
        self._rf_cv_loocv = getattr(self.dlg, "radRF_CV_LOOCV", None)
        self._rf_cv_kfold = getattr(self.dlg, "radRF_CV_KFold", None)
        self._rf_cv_k_spin = getattr(self.dlg, "spinRF_k", None)

        def _refresh():
            try:
                if self._rf_cv_k_spin is not None:
                    enabled = bool(self._rf_cv_kfold is not None and self._rf_cv_kfold.isChecked())
                    self._rf_cv_k_spin.setEnabled(enabled)
            except Exception:
                pass

        for w in (self._rf_cv_auto, self._rf_cv_loocv, self._rf_cv_kfold):
            if w is not None and hasattr(w, "toggled"):
                try:
                    w.toggled.connect(_refresh)
                except Exception:
                    pass
        _refresh()

        run_btn = getattr(self.dlg, "btnRFRunCV", None)
        if run_btn is not None and hasattr(run_btn, "clicked"):
            try:
                run_btn.clicked.disconnect()
            except Exception:
                pass
            run_btn.clicked.connect(self._on_run_rf_cross_validation)

    def _rf_get_cv_mode(self):
        """Return RF CV mode as 'auto', 'loocv', or 'kfold'."""
        try:
            if self._rf_cv_loocv is not None and self._rf_cv_loocv.isChecked():
                return "loocv"
            if self._rf_cv_kfold is not None and self._rf_cv_kfold.isChecked():
                return "kfold"
        except Exception:
            pass
        return "auto"

    def _rf_decide_auto_cv(self, n):
        """Match the auto CV policy used in the deterministic/geostatistical tabs."""
        if n <= 100:
            return "loocv", None
        elif n <= 1000:
            return "kfold", 10
        return "kfold", 5

    def _rf_make_kfold_indices(self, n, k):
        """Create K random folds using the same simple policy as the other tabs."""
        idx = list(range(n))
        random.Random(20).shuffle(idx)
        folds = []
        base, rem = divmod(n, k)
        start = 0
        for i in range(k):
            size = base + (1 if i < rem else 0)
            folds.append(idx[start:start + size])
            start += size
        return folds

    def _rf_rmse(self, obs, pred):
        valid = np.isfinite(obs) & np.isfinite(pred)
        if valid.sum() == 0:
            return float("nan")
        d = np.asarray(obs)[valid] - np.asarray(pred)[valid]
        return float(np.sqrt(np.mean(d ** 2)))

    def _rf_rmse_pct(self, obs, pred):
        valid = np.isfinite(obs) & np.isfinite(pred)
        if valid.sum() == 0:
            return float("nan")
        obs_v = np.asarray(obs)[valid]
        mean_obs = float(np.mean(obs_v))
        if not np.isfinite(mean_obs) or abs(mean_obs) < 1e-12:
            return float("nan")
        return float(100.0 * self._rf_rmse(obs, pred) / abs(mean_obs))

    def _rf_mae(self, obs, pred):
        valid = np.isfinite(obs) & np.isfinite(pred)
        if valid.sum() == 0:
            return float("nan")
        return float(np.mean(np.abs(np.asarray(obs)[valid] - np.asarray(pred)[valid])))

    def _rf_r2(self, obs, pred):
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

    def _rf_pearson_r(self, obs, pred):
        valid = np.isfinite(obs) & np.isfinite(pred)
        if valid.sum() < 2:
            return float("nan")
        o = np.asarray(obs)[valid]
        p = np.asarray(pred)[valid]
        if np.std(o) <= 0 or np.std(p) <= 0:
            return float("nan")
        return float(np.corrcoef(o, p)[0, 1])

    def _rf_lccc(self, obs, pred):
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

    def _update_rf_validation_metrics_ui(self, rmse, lccc, rmse_pct, r2, mae, pearson_r):
        """Update RF validation metric labels when they exist in the UI."""
        def _set(name, value):
            w = getattr(self.dlg, name, None)
            if w is not None and hasattr(w, "setText"):
                w.setText(value)

        def _fmt(v):
            return "—" if v is None or not np.isfinite(v) else f"{v:.3f}"

        _set("valRFRMSE", _fmt(rmse))
        _set("valRFLCCC", _fmt(lccc))
        _set("valRFRMSEpct", "—" if rmse_pct is None or not np.isfinite(rmse_pct) else f"{rmse_pct:.2f}")
        _set("valRFR2", _fmt(r2))
        _set("valRFMAE", _fmt(mae))
        _set("valRFPearsonR", _fmt(pearson_r))

    def _plot_rf_validation_scatter(self, obs, pred, title="Observed vs Predicted (RF CV)"):
        """Plot RF CV observed vs predicted using the same visual style as other tabs."""
        if self._rf_val_fig is None or self._rf_val_canvas is None:
            self._init_rf_validation_canvas()
        if self._rf_val_fig is None or self._rf_val_canvas is None:
            return

        fig = self._rf_val_fig
        canvas = self._rf_val_canvas
        fig.clear()
        ax = fig.add_subplot(111)

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

        if len(obs_valid) < 2:
            ax.scatter(obs_valid, pred_valid, s=20, alpha=0.9, facecolors='none', edgecolors='black')
            ax.set_title(f"{title} (not enough data for fit)", fontsize=8)
        else:
            ax.scatter(obs_valid, pred_valid, s=24, alpha=0.9, facecolors='none', edgecolors='black', label='Data')
            ax.plot([vmin, vmax], [vmin, vmax], '-', color='black', linewidth=1.0, label='1:1')
            m, b = np.polyfit(obs_valid, pred_valid, 1)
            ax.plot([vmin, vmax], [m * vmin + b, m * vmax + b], '-', color='#d62728', linewidth=1.0, label='Fit')
            ax.set_title(title, fontsize=8)
            ax.legend(loc='best', frameon=False, fontsize=8)

        ax.set_xlim(vmin, vmax)
        ax.set_ylim(vmin, vmax)
        try:
            ax.set_box_aspect(1)
        except Exception:
            ax.set_aspect('equal', adjustable='box')
        ax.grid(True, linestyle='--', linewidth=0.5, alpha=0.6)
        ax.tick_params(axis='both', labelsize=7)
        ax.set_xlabel("Observed", fontsize=8)
        ax.set_ylabel("Predicted", fontsize=8)
        try:
            fig.tight_layout()
        except Exception:
            pass
        canvas.draw_idle()
        self._rf_val_ax = ax

    def _reset_metric_labels(self, names):
        """Reset metric labels if the corresponding UI widgets exist."""
        for name in names:
            widget = getattr(self.dlg, name, None)
            if widget is not None and hasattr(widget, "setText"):
                try:
                    widget.setText("--")
                except Exception:
                    pass

    def clear_plots(self):
        """Clear Machine Learning plots and cached plot payloads."""
        plot_items = [
            ("_corr_fig", "_corr_canvas", "_corr_ax"),
            ("_rf_map_fig", "_rf_map_canvas", "_rf_map_ax"),
            ("_rf_imp_fig", "_rf_imp_canvas", "_rf_imp_ax"),
            ("_rf_val_fig", "_rf_val_canvas", "_rf_val_ax"),
            ("_svm_map_fig", "_svm_map_canvas", "_svm_map_ax"),
            ("_svm_val_fig", "_svm_val_canvas", "_svm_val_ax"),
        ]
        for fig_name, canvas_name, ax_name in plot_items:
            fig = getattr(self, fig_name, None)
            canvas = getattr(self, canvas_name, None)
            if fig is not None:
                try:
                    fig.clear()
                except Exception:
                    pass
            if canvas is not None:
                try:
                    canvas.draw_idle()
                except Exception:
                    pass
            try:
                setattr(self, ax_name, None)
            except Exception:
                pass

        self._last_corr_matrix = None
        self._last_corr_names = None
        self._last_sample_count = None
        self._rf_last_map_payload = None
        self._rf_last_importance_df = None
        self._svm_last_map_payload = None

        self._reset_metric_labels([
            "valRFRMSE",
            "valRFLCCC",
            "valRFRMSEpct",
            "valRFR2",
            "valRFMAE",
            "valRFPearsonR",
            "valRFTrainMAE",
            "valRFTrainRMSE",
            "valRFBestNtree",
            "valRFBestMtry",
            "valRFBestNodesize",
            "valSVMRMSE",
            "valSVMLCCC",
            "valSVMRMSEpct",
            "valSVMR2",
            "valSVMMAE",
            "valSVMPearsonR",
        ])

    def reset_for_data_change(self):
        """Reset ML covariates and outputs when the selected dataset changes."""
        try:
            self._on_clear_covariates()
        except Exception:
            pass

        self.clear_plots()
        self._extracted_headers = None
        self._extracted_rows = None
        self._standardization_for_extraction = False

        try:
            self.refresh_raster_combo()
        except Exception:
            pass
        try:
            self._sync_pixel_size_from_data(set_target_default=False)
        except Exception:
            pass

    def _find_first_existing_widget(self, candidate_names):
        """Return the first existing dialog widget from a list of candidate names."""
        for name in candidate_names:
            w = getattr(self.dlg, name, None)
            if w is not None:
                return w
        return None

    def _clear_layout_widgets(self, container):
        """Remove existing child widgets from a container layout and return the layout."""
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

    def _init_rf_plot_canvases(self):
        """
        Create matplotlib canvases for the RF map preview and RF importance plot.
        The method tries several widget names so the code remains robust against
        small UI naming differences.
        """
        map_container = self._find_first_existing_widget(
            [
                "RFMap",
                "rfMap",
                "widgetRFMap",
                "frameRFMap",
                "plotRFMap",
                "RF_map",
                "canvasRFInterpolation",
            ]
        )
        imp_container = self._find_first_existing_widget(
            [
                "RFImportance",
                "RFImportancePlot",
                "rfImportance",
                "widgetRFImportance",
                "frameRFImportance",
                "plotRFImportance",
                "canvasRFImportance",
            ]
        )

        if map_container is not None:
            map_layout = self._clear_layout_widgets(map_container)
            self._rf_map_fig = Figure()
            self._rf_map_canvas = FigureCanvas(self._rf_map_fig)
            self._rf_map_ax = None
            map_layout.addWidget(self._rf_map_canvas)
            self._install_plot_canvas_menu(
                self._rf_map_canvas,
                lambda: self._rf_map_fig if self._rf_last_map_payload is not None else None,
                "rf_interpolation",
                "RF interpolation — zoom view",
                self._redraw_rf_map_into,
            )

        if imp_container is not None:
            imp_layout = self._clear_layout_widgets(imp_container)
            self._rf_imp_fig = Figure()
            self._rf_imp_canvas = FigureCanvas(self._rf_imp_fig)
            self._rf_imp_ax = None
            imp_layout.addWidget(self._rf_imp_canvas)
            self._install_plot_canvas_menu(
                self._rf_imp_canvas,
                lambda: self._rf_imp_fig if self._rf_last_importance_df is not None else None,
                "rf_importance",
                "RF variable importance — zoom view",
                self._redraw_rf_importance_into,
            )

    @staticmethod
    def _apply_basic_map_formatter(ax):
        """Apply the same lightweight axis formatting style used across the plugin."""
        try:
            from matplotlib.ticker import MaxNLocator
            ax.xaxis.set_major_locator(MaxNLocator(nbins=6))
            ax.yaxis.set_major_locator(MaxNLocator(nbins=6))
        except Exception:
            pass
        ax.tick_params(axis="both", labelsize=8)
        ax.set_xlabel("X")
        ax.set_ylabel("Y")

    def _draw_rf_interpolation_preview(self, grid_df, grid_meta, target_column, fig=None, canvas=None):
        """Draw RF interpolation preview into the RF map widget using viridis."""
        if fig is None:
            fig = self._rf_map_fig
        if canvas is None:
            canvas = self._rf_map_canvas
        if fig is None or canvas is None:
            return
        if fig is self._rf_map_fig:
            self._rf_last_map_payload = {
                "grid_df": grid_df.copy(),
                "grid_meta": dict(grid_meta),
                "target_column": target_column,
            }

        xmin = float(grid_meta["xmin"])
        xmax = float(grid_meta["xmax"])
        ymin = float(grid_meta["ymin"])
        ymax = float(grid_meta["ymax"])
        n_cols = int(grid_meta["n_cols"])
        n_rows = int(grid_meta["n_rows"])
        pixel_size = float(grid_meta["pixel_size"])
        poly_layer = grid_meta["poly_layer"]

        value_col = f"{target_column}_pred"
        if value_col not in grid_df.columns:
            return

        raster_array = np.full((n_rows, n_cols), np.nan, dtype=np.float32)
        xs = grid_df["x"].to_numpy(dtype=float)
        ys = grid_df["y"].to_numpy(dtype=float)
        vals = grid_df[value_col].to_numpy(dtype=float)

        for x, y, v in zip(xs, ys, vals):
            col = int((x - xmin) / pixel_size)
            row = int((ymax - y) / pixel_size)
            if 0 <= col < n_cols and 0 <= row < n_rows:
                raster_array[row, col] = float(v)

        fig.clear()
        ax = fig.add_subplot(111)
        ax.set_title(f"RF interpolation ({target_column})")

        x_edges = np.linspace(xmin, xmax, n_cols + 1)
        y_edges = np.linspace(ymin, ymax, n_rows + 1)
        disp_array = np.flipud(raster_array)
        masked = np.ma.masked_invalid(disp_array)

        pm = ax.pcolormesh(
            x_edges,
            y_edges,
            masked,
            cmap="viridis",
            shading="auto",
        )
        cbar = fig.colorbar(pm, ax=ax, orientation="vertical")
        cbar.set_label(target_column)

        try:
            for feat in poly_layer.getFeatures():
                geom = feat.geometry()
                if geom.isMultipart():
                    for part in geom.asMultiPolygon():
                        for ring in part:
                            ring_xy = [(pt.x(), pt.y()) for pt in ring]
                            patch = MplPolygon(
                                ring_xy,
                                closed=True,
                                edgecolor="black",
                                facecolor="none",
                                linewidth=1.0,
                            )
                            ax.add_patch(patch)
                else:
                    for ring in geom.asPolygon():
                        ring_xy = [(pt.x(), pt.y()) for pt in ring]
                        patch = MplPolygon(
                            ring_xy,
                            closed=True,
                            edgecolor="black",
                            facecolor="none",
                            linewidth=1.0,
                        )
                        ax.add_patch(patch)
        except Exception:
            pass

        ax.set_xlim(xmin, xmax)
        ax.set_ylim(ymin, ymax)
        ax.set_aspect("equal", adjustable="box")
        self._apply_basic_map_formatter(ax)

        fig.tight_layout()
        canvas.draw()
        if fig is self._rf_map_fig:
            self._rf_map_ax = ax

    def _draw_rf_importance_plot(self, importance_df, fig=None, canvas=None):
        """Draw RF variable importance as a horizontal bar chart using viridis."""
        if fig is None:
            fig = self._rf_imp_fig
        if canvas is None:
            canvas = self._rf_imp_canvas
        if fig is None or canvas is None:
            return
        if fig is self._rf_imp_fig:
            self._rf_last_importance_df = None if importance_df is None else importance_df.copy()
        if importance_df is None or importance_df.empty:
            return
        if "Variable" not in importance_df.columns or "Importance" not in importance_df.columns:
            return

        df = importance_df.copy()
        df = df.sort_values("Importance", ascending=True).reset_index(drop=True)
        labels = [self._shorten_var_name(str(v), max_len=32) for v in df["Variable"]]
        values = df["Importance"].to_numpy(dtype=float)

        fig.clear()
        ax = fig.add_subplot(111)

        if len(values) > 1:
            rng = float(np.max(values) - np.min(values))
            if rng <= 0:
                norm_vals = np.full(len(values), 0.7, dtype=float)
            else:
                norm_vals = (values - np.min(values)) / rng
        else:
            norm_vals = np.array([0.7], dtype=float)

        colors = matplotlib.cm.viridis(norm_vals)
        y_pos = np.arange(len(labels))
        ax.barh(y_pos, values, color=colors, edgecolor="black", linewidth=0.4)
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, fontsize=9)
        ax.set_xlabel("Importance")
        ax.set_title("RF variable importance")
        ax.grid(axis="x", alpha=0.25)

        fig.tight_layout()
        canvas.draw()
        if fig is self._rf_imp_fig:
            self._rf_imp_ax = ax

    def _install_plot_canvas_menu(self, canvas, get_figure_fn, save_prefix, zoom_title, redraw_fn):
        """Add right-click context menu with save/zoom to a generic matplotlib canvas."""
        if canvas is None:
            return
        try:
            if not hasattr(self, "_plot_canvas_menu_bound"):
                self._plot_canvas_menu_bound = set()
            key = id(canvas)
            if key in self._plot_canvas_menu_bound:
                return
            canvas.setContextMenuPolicy(Qt.CustomContextMenu)
        except Exception:
            return

        def _show_menu(pos):
            fig = get_figure_fn() if callable(get_figure_fn) else None
            if fig is None:
                menu = QMenu(self.dlg)
                act_none = menu.addAction("No graph to save")
                act_none.setEnabled(False)
                menu.exec_(canvas.mapToGlobal(pos))
                return

            menu = QMenu(self.dlg)
            act_save = menu.addAction("Save graph as PNG…")
            act_zoom = menu.addAction("Open larger view…")
            act_copy = menu.addAction("Copy graph")
            chosen = menu.exec_(canvas.mapToGlobal(pos))

            if chosen == act_copy:
                self._copy_figure_to_clipboard(fig)
            elif chosen == act_save:
                suggested = os.path.join(tempfile.gettempdir(), f"{save_prefix}.png")
                path, _ = QFileDialog.getSaveFileName(
                    self.dlg,
                    "Save graph",
                    suggested,
                    "PNG Images (*.png)",
                )
                if path:
                    try:
                        fig.savefig(path, dpi=300, bbox_inches="tight")
                        QMessageBox.information(self.dlg, "Saved", f"Graph saved to:\n{path}")
                    except Exception as e:
                        QMessageBox.warning(self.dlg, "Save error", f"Could not save PNG:\n{e}")
            elif chosen == act_zoom:
                try:
                    dlg = QDialog(self.dlg)
                    dlg.setWindowTitle(zoom_title)
                    fig2 = Figure()
                    canvas2 = FigureCanvas(fig2)
                    layout = QVBoxLayout(dlg)
                    layout.addWidget(canvas2)
                    redraw_fn(fig2, canvas2)
                    dlg.resize(900, 700)
                    dlg.exec_()
                except Exception as e:
                    QMessageBox.warning(self.dlg, "Zoom error", f"Could not open larger view:\n{e}")

        canvas.customContextMenuRequested.connect(_show_menu)
        self._plot_canvas_menu_bound.add(id(canvas))

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
            QMessageBox.information(self.dlg, "Copied", "Graph copied to clipboard.")
        except Exception as e:
            QMessageBox.warning(self.dlg, "Copy error", f"Could not copy graph:\n{e}")

    def _redraw_rf_map_into(self, fig, canvas):
        payload = self._rf_last_map_payload
        if not payload:
            return
        self._draw_rf_interpolation_preview(payload["grid_df"], payload["grid_meta"], payload["target_column"], fig=fig, canvas=canvas)

    def _redraw_rf_importance_into(self, fig, canvas):
        if self._rf_last_importance_df is None:
            return
        self._draw_rf_importance_plot(self._rf_last_importance_df, fig=fig, canvas=canvas)

    def _redraw_svm_map_into(self, fig, canvas):
        payload = self._svm_last_map_payload
        if not payload:
            return
        self._draw_svm_interpolation_preview(payload["grid_df"], payload["grid_meta"], payload["target_column"], fig=fig, canvas=canvas)

    def _install_corr_canvas_menu(self):
        """Add right-click context menu on the correlation canvas."""
        if self._corr_canvas is None:
            return
        self._corr_canvas.setContextMenuPolicy(Qt.CustomContextMenu)
        self._corr_canvas.customContextMenuRequested.connect(
            self._on_corr_canvas_context_menu
        )

    def _on_corr_canvas_context_menu(self, pos):
        """Context menu with 'Save graph...' and 'Open larger view...'."""
        if self._last_corr_matrix is None or self._last_corr_names is None:
            # Nothing drawn yet – just tell the user
            menu = QMenu(self.dlg)
            act_none = menu.addAction("No graph to save")
            act_none.setEnabled(False)
            menu.exec_(self._corr_canvas.mapToGlobal(pos))
            return

        menu = QMenu(self.dlg)
        act_save = menu.addAction("Save graph as PNG…")
        act_zoom = menu.addAction("Open larger view…")
        act_copy = menu.addAction("Copy graph")
        chosen = menu.exec_(self._corr_canvas.mapToGlobal(pos))

        if chosen == act_copy:
            self._copy_figure_to_clipboard(self._corr_fig)
        elif chosen == act_save:
            suggested = os.path.join(
                tempfile.gettempdir(), "covariates_correlation.png"
            )
            path, _ = QFileDialog.getSaveFileName(
                self.dlg,
                "Save graph",
                suggested,
                "PNG Images (*.png)",
            )
            if path:
                try:
                    self._corr_fig.savefig(path, dpi=300, bbox_inches="tight")
                    QMessageBox.information(
                        self.dlg, "Saved", f"Graph saved to:\n{path}"
                    )
                except Exception as e:
                    QMessageBox.warning(
                        self.dlg,
                        "Save error",
                        f"Could not save PNG:\n{e}",
                    )
        elif chosen == act_zoom:
            self._show_zoom_corr_dialog()

    def _show_zoom_corr_dialog(self):
        """Open the correlation plot in a larger dialog window."""
        if (
            self._last_corr_matrix is None
            or self._last_corr_names is None
            or self._last_sample_count is None
        ):
            return

        dlg = QDialog(self.dlg)
        dlg.setWindowTitle("Pearson correlation — zoom view")

        fig = Figure()
        canvas = FigureCanvas(fig)
        layout = QVBoxLayout(dlg)
        layout.addWidget(canvas)

        self._draw_corr_plot(
            self._last_corr_matrix,
            self._last_corr_names,
            self._last_sample_count,
            fig,
            canvas,
        )

        dlg.resize(900, 700)
        dlg.exec_()

    # -------------------------------------------------------------------------
    # Covariate list management
    # -------------------------------------------------------------------------

    def _on_add_covariate(self):
        """Add the selected raster from the combo to the covariate list."""
        combo = self.dlg.cmbMLRaster
        list_widget = self.dlg.listCovariates

        if combo.currentIndex() < 0:
            self._show_info_message(
                "No raster selected",
                "Please select a raster layer to add as covariate.",
            )
            return

        raster_name = combo.currentText()
        raster_id = combo.currentData()

        existing_names = [
            list_widget.item(i).text() for i in range(list_widget.count())
        ]
        if raster_name in existing_names:
            self._show_info_message(
                "Already loaded",
                f"Raster '{raster_name}' is already in the covariates list.",
            )
            return

        layer = self.project.mapLayer(raster_id)
        if not isinstance(layer, QgsRasterLayer):
            self._show_warning_message(
                "Invalid layer",
                "Selected layer is not a raster or is no longer available.",
            )
            return

        self.covariate_layers[raster_name] = layer
        list_widget.addItem(raster_name)

    def _on_remove_selected_covariates(self):
        """Remove selected covariates from the list and mapping."""
        list_widget = self.dlg.listCovariates
        selected_items = list_widget.selectedItems()
        if not selected_items:
            return

        for item in selected_items:
            name = item.text()
            row = list_widget.row(item)
            list_widget.takeItem(row)
            if name in self.covariate_layers:
                del self.covariate_layers[name]

    def _on_clear_covariates(self):
        """Clear all loaded covariates from the list and internal mapping."""
        try:
            self.dlg.listCovariates.clear()
        except Exception:
            pass
        self.covariate_layers.clear()
        self._last_corr_matrix = None
        self._last_corr_names = None
        self._extracted_headers = None
        self._extracted_rows = None
        try:
            self.dlg.labelResamplingInfo.setText("")
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Resampling logic
    # -------------------------------------------------------------------------

    def _on_resample_covariates(self):
        """
        Resample all loaded covariate rasters to the chosen pixel size (bilinear).
        Creates temporary rasters, updates the internal mapping to them,
        and updates the names in the covariate list so the user sees
        which version is being used.
        """
        list_widget = self.dlg.listCovariates
        label_info = self.dlg.labelResamplingInfo
        target_pixel_size = float(self.dlg.spinTargetPixelSize.value())

        if list_widget.count() == 0:
            self._show_info_message(
                "No covariates",
                "Please load at least one covariate raster before resampling.",
            )
            return

        if target_pixel_size <= 0:
            self._show_warning_message(
                "Invalid pixel size",
                "Target pixel size must be greater than zero.",
            )
            return

        total = list_widget.count()
        progress = QProgressDialog(
            "Resampling covariates...", "Cancel", 0, total, self.dlg
        )
        progress.setWindowTitle("Resampling")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        resampled_count = 0

        for i in range(total):
            if progress.wasCanceled():
                break

            progress.setValue(i)
            QCoreApplication.processEvents()

            old_name = list_widget.item(i).text()
            layer = self.covariate_layers.get(old_name)
            if not isinstance(layer, QgsRasterLayer):
                continue

            src_path = layer.source()
            if not os.path.exists(src_path):
                continue

            base_name = os.path.splitext(os.path.basename(src_path))[0]
            out_name = f"{base_name}_resampled_{target_pixel_size:.0f}"
            out_path = os.path.join(self._ensure_output_dir_for_rf(), f"{out_name}.tif")

            try:
                warp_options = gdal.WarpOptions(
                    xRes=target_pixel_size,
                    yRes=target_pixel_size,
                    resampleAlg="bilinear",
                )
                result = gdal.Warp(out_path, src_path, options=warp_options)
                if result is None:
                    continue
                result = None
            except Exception:
                continue

            resampled_layer = self._create_output_raster_layer(out_path, out_name)
            if not resampled_layer.isValid():
                continue

            self._mark_temporary_layer(resampled_layer, out_path)
            self.project.addMapLayer(resampled_layer)

            # Update mapping and visible name
            new_name = out_name
            self.covariate_layers.pop(old_name, None)
            self.covariate_layers[new_name] = resampled_layer
            list_widget.item(i).setText(new_name)

            resampled_count += 1

        progress.setValue(total)

        if resampled_count > 0:
            label_info.setText(
                f"Resampled {resampled_count} covariate(s) to {target_pixel_size:.2f} pixel size (bilinear)."
            )
        else:
            label_info.setText(
                "Resampling failed or no valid covariates were found."
            )

    # -------------------------------------------------------------------------
    # Standardization
    # -------------------------------------------------------------------------

    def _on_apply_standardization_clicked(self):
        """
        Standardize all current covariate rasters, create new rasters, and
        replace the entries in the 'Loaded covariates' list by the processed
        versions. Extraction will read from whatever is shown in that list.
        """
        method = self._get_standardization_method()
        if method == "none":
            self._show_info_message(
                "Standardization",
                "No standardization applied because the selected method is 'None'.",
            )
            self._standardization_for_extraction = False
            return

        self._standardization_for_extraction = True

        list_widget = self.dlg.listCovariates
        if list_widget.count() == 0:
            self._show_warning_message(
                "No covariates",
                "Please load at least one covariate raster before standardizing.",
            )
            return

        standardized_count = 0
        total = list_widget.count()

        progress = QProgressDialog(
            "Standardizing covariates...", "Cancel", 0, total, self.dlg
        )
        progress.setWindowTitle("Standardization")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        for i in range(total):
            if progress.wasCanceled():
                break

            progress.setValue(i)
            QCoreApplication.processEvents()

            old_name = list_widget.item(i).text()
            layer = self.covariate_layers.get(old_name)
            if not isinstance(layer, QgsRasterLayer):
                continue

            src_path = layer.source()
            if not os.path.exists(src_path):
                continue

            ds = gdal.Open(src_path, gdal.GA_ReadOnly)
            if ds is None:
                continue

            band = ds.GetRasterBand(1)
            arr = band.ReadAsArray().astype("float64")

            # Detect source NoData value
            src_nodata = band.GetNoDataValue()

            # Valid-mask: ignore NaN/inf and NoData
            if src_nodata is None or (isinstance(src_nodata, float) and math.isnan(src_nodata)):
                valid = np.isfinite(arr)
            else:
                valid = np.isfinite(arr) & (arr != src_nodata)

            if not np.any(valid):
                ds = None
                continue

            vals = arr[valid]
            vals_min = float(np.nanmin(vals))
            vals_max = float(np.nanmax(vals))
            vals_mean = float(np.nanmean(vals))
            vals_std = float(np.nanstd(vals, ddof=1)) if vals.size > 1 else 0.0

            std_arr = np.full_like(arr, np.nan, dtype="float64")

            if method == "zscore":
                # Avoid division by near-zero std
                if vals_std > 1e-12:
                    std_arr[valid] = (arr[valid] - vals_mean) / vals_std
                else:
                    std_arr[valid] = 0.0

            elif method == "minus_one_to_one":
                if (vals_max - vals_min) > 1e-12:
                    std_arr[valid] = (
                        2.0 * (arr[valid] - vals_min) / (vals_max - vals_min) - 1.0
                    )
                else:
                    std_arr[valid] = 0.0
            else:
                ds = None
                continue

            # Output NoData
            if src_nodata is not None and np.isfinite(src_nodata):
                out_nodata = float(src_nodata)
            else:
                out_nodata = -9999.0

            std_arr[~valid] = out_nodata

            base_name = os.path.splitext(os.path.basename(src_path))[0]
            method_tag = "zscore" if method == "zscore" else "m1to1"
            out_name = f"{base_name}_standardized_{method_tag}"
            out_path = os.path.join(self._ensure_output_dir_for_rf(), f"{out_name}.tif")

            driver = gdal.GetDriverByName("GTiff")
            out_ds = driver.Create(
                out_path,
                ds.RasterXSize,
                ds.RasterYSize,
                1,
                gdalconst.GDT_Float32,
            )
            if out_ds is None:
                ds = None
                continue

            out_ds.SetGeoTransform(ds.GetGeoTransform())
            out_ds.SetProjection(ds.GetProjection())

            out_band = out_ds.GetRasterBand(1)
            out_band.WriteArray(std_arr.astype(np.float32))
            out_band.SetNoDataValue(out_nodata)

            # Compute and set statistics so QGIS shows correct min/max
            valid_mask = np.isfinite(std_arr) & (std_arr != out_nodata)
            valid_vals = std_arr[valid_mask]
            if valid_vals.size > 0:
                stat_min = float(np.nanmin(valid_vals))
                stat_max = float(np.nanmax(valid_vals))
                stat_mean = float(np.nanmean(valid_vals))
                stat_std = (
                    float(np.nanstd(valid_vals, ddof=1))
                    if valid_vals.size > 1
                    else 0.0
                )
                try:
                    out_band.SetStatistics(
                        stat_min, stat_max, stat_mean, stat_std
                    )
                except Exception:
                    pass

            out_band.FlushCache()
            out_ds.FlushCache()
            out_ds = None
            ds = None

            std_layer = self._create_output_raster_layer(out_path, out_name)
            if not std_layer.isValid():
                continue

            self._mark_temporary_layer(std_layer, out_path)
            self.project.addMapLayer(std_layer)

            # Update mapping and visible name so extraction uses the processed raster
            new_name = out_name
            self.covariate_layers.pop(old_name, None)
            self.covariate_layers[new_name] = std_layer
            list_widget.item(i).setText(new_name)

            standardized_count += 1

        progress.setValue(total)

        if standardized_count > 0:
            self._show_info_message(
                "Standardization",
                f"Standardized {standardized_count} covariate raster(s) and added them to the project.\n"
                "Extraction will use the processed rasters currently listed as 'Loaded covariates'.",
            )
        else:
            self._show_warning_message(
                "Standardization",
                "Standardization failed or no valid covariate rasters were found.",
            )

    def _get_standardization_method(self):
        """Return the selected standardization method as a canonical string."""
        text = self.dlg.cmbStandardizeMethod.currentText().strip().lower()
        if "z" in text:
            return "zscore"
        if "-1" in text:
            return "minus_one_to_one"
        return "none"

    def _standardize_data_matrix(self, data_matrix, method):
        """
        Apply the selected standardization to the columns of data_matrix.
        Used for correlation and extraction (point-based), not for rasters.
        """
        if method == "none":
            return data_matrix.copy()

        data = data_matrix.astype(float).copy()
        n_vars = data.shape[1]

        for j in range(n_vars):
            col = data[:, j]
            valid = ~np.isnan(col)
            if not np.any(valid):
                continue

            col_valid = np.asarray(col[valid], dtype=float)
            col_min = float(np.min(col_valid))
            col_max = float(np.max(col_valid))
            col_mean = float(np.mean(col_valid))
            col_std = float(np.std(col_valid, ddof=1)) if col_valid.size > 1 else 0.0

            if method == "zscore":
                if col_std > 0:
                    col_stdized = (col - col_mean) / col_std
                else:
                    col_stdized = np.zeros_like(col)
                data[:, j] = col_stdized
            elif method == "minus_one_to_one":
                if col_max > col_min:
                    col_scaled = (
                        2.0 * (col - col_min) / (col_max - col_min) - 1.0
                    )
                else:
                    col_scaled = np.zeros_like(col)
                data[:, j] = col_scaled

        return data

    # -------------------------------------------------------------------------
    # Correlation computation and plotting
    # -------------------------------------------------------------------------

    def _on_compute_correlations_clicked(self):
        """
        Compute Pearson correlation matrix between:
        [target variable from Data tab] + [all loaded covariates],
        using the sample points and raster values at those points.
        """
        points_layer = self._get_selected_points_layer()
        if points_layer is None:
            self._show_warning_message(
                "No points layer",
                "Please select a valid points layer in the Data tab.",
            )
            return

        attr_name = self.dlg.cmbVariable.currentText().strip()
        if not attr_name:
            self._show_warning_message(
                "No variable", "Please select a variable in the Data tab."
            )
            return

        attr_index = points_layer.fields().indexOf(attr_name)
        if attr_index < 0:
            self._show_warning_message(
                "Invalid variable",
                "Selected variable not found in the points layer.",
            )
            return

        list_widget = self.dlg.listCovariates
        cov_names = [list_widget.item(i).text() for i in range(list_widget.count())]

        if not cov_names:
            self._show_warning_message(
                "No covariates",
                "Please load at least one covariate raster to compute correlations.",
            )
            return

        raster_layers = [
            self.covariate_layers.get(name) for name in cov_names
        ]
        raster_layers = [
            rl for rl in raster_layers if isinstance(rl, QgsRasterLayer)
        ]
        if not raster_layers:
            self._show_warning_message(
                "No valid rasters",
                "Loaded covariates are not valid raster layers.",
            )
            return

        raster_crs = raster_layers[0].crs()
        point_crs = points_layer.crs()

        if (
            raster_crs.isValid()
            and point_crs.isValid()
            and raster_crs != point_crs
        ):
            transform = QgsCoordinateTransform(
                point_crs, raster_crs, self.project
            )
        else:
            transform = None

        data_rows = []

        for feat in points_layer.getFeatures():
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue

            try:
                pt = geom.asPoint()
            except Exception:
                multi = geom.asMultiPoint()
                if not multi:
                    continue
                pt = multi[0]

            if transform is not None:
                try:
                    pt = transform.transform(pt)
                except Exception:
                    continue

            val = feat[attr_index]
            if val is None:
                continue

            try:
                y_value = float(val)
            except Exception:
                continue

            row = [y_value]
            missing = False

            for rlayer in raster_layers:
                provider = rlayer.dataProvider()
                sample_point = QgsPointXY(pt.x(), pt.y())
                sample_val, res = provider.sample(sample_point, 1)
                if (
                    not res
                    or sample_val is None
                    or math.isnan(sample_val)
                ):
                    missing = True
                    break
                row.append(float(sample_val))

            if not missing:
                data_rows.append(row)

        if len(data_rows) < 3:
            self._show_warning_message(
                "Insufficient data",
                "Not enough valid samples were found to compute correlations.",
            )
            return

        data_matrix = np.array(data_rows)
        sample_count = data_matrix.shape[0]

        method = self._get_standardization_method()
        data_std = self._standardize_data_matrix(data_matrix, method)

        try:
            corr_matrix = np.corrcoef(data_std, rowvar=False)
        except Exception as e:
            self._show_warning_message(
                "Correlation error",
                f"Could not compute correlation matrix:\n{e}",
            )
            return

        var_names = [attr_name] + cov_names
        self._last_corr_matrix = corr_matrix
        self._last_corr_names = var_names
        self._last_sample_count = sample_count

        self._update_corr_plot(corr_matrix, var_names, sample_count)

    def _shorten_var_name(self, name: str, max_len: int = 30) -> str:
        """
        Shorten very long variable names for plotting and add flags:
        - (S) for standardized
        - (R) for resampled
        - (SR) for resampled + standardized
        """
        low = name.lower()

        has_std = (
            "_standardized" in low
            or "_zscore" in low
            or "_m1to1" in low
        )
        has_res = "_resampled" in low

        if has_std and has_res:
            flag = " (SR)"
        elif has_std:
            flag = " (S)"
        elif has_res:
            flag = " (R)"
        else:
            flag = ""

        # Remove processing suffixes from the base name
        base = name
        for token in ["_resampled", "_standardized", "_zscore", "_m1to1"]:
            idx = base.lower().find(token)
            if idx > 0:
                base = base[:idx]
                break

        base = base.strip("_- ")

        # Reserve space for the flag when truncating
        max_base_len = max_len - len(flag)
        if max_base_len < 5:
            max_base_len = 5

        if len(base) > max_base_len:
            base = base[: max_base_len - 3] + "..."

        return base + flag

    def _update_corr_plot(self, corr_matrix, var_names, sample_count):
        """Draw correlation matrix into the main canvas."""
        if self._corr_fig is None or self._corr_canvas is None:
            return
        self._draw_corr_plot(
            corr_matrix, var_names, sample_count, self._corr_fig, self._corr_canvas
        )

    def _draw_corr_plot(self, corr_matrix, var_names, sample_count, fig, canvas):
        """
        Core plotting routine used both by the main canvas and the zoom dialog.
        """
        fig.clf()
        ax = fig.add_subplot(111)

        mask = np.triu(np.ones_like(corr_matrix, dtype=bool), k=1)
        matrix_to_plot = np.ma.array(corr_matrix, mask=mask)

        norm = TwoSlopeNorm(vmin=-1.0, vcenter=0.0, vmax=1.0)
        im = ax.imshow(matrix_to_plot, cmap="RdBu", norm=norm)

        n_vars = len(var_names)
        display_names = [self._shorten_var_name(n) for n in var_names]

        ax.set_xticks(range(n_vars))
        ax.set_yticks(range(n_vars))
        ax.set_xticklabels(display_names, rotation=45, ha="right", fontsize=9)
        ax.set_yticklabels(display_names, fontsize=9)

        cbar = fig.colorbar(
            im,
            ax=ax,
            fraction=0.046,
            pad=0.04,
            label="Pearson r",
        )
        cbar.ax.yaxis.label.set_size(9)

        sig_mask = self._compute_significance_mask(
            corr_matrix, sample_count
        )

        for i in range(n_vars):
            for j in range(n_vars):
                if j > i:
                    continue
                value = corr_matrix[i, j]
                if np.isnan(value):
                    continue
                star = "*" if sig_mask[i, j] else ""
                text = f"{value:.2f}{star}"
                ax.text(
                    j,
                    i,
                    text,
                    ha="center",
                    va="center",
                    fontsize=8,
                )

        ax.set_title("Pearson correlation", fontsize=10)
        fig.tight_layout()
        canvas.draw()

        # keep reference to main axes if this is the main figure
        if fig is self._corr_fig:
            self._corr_ax = ax

    def _compute_significance_mask(
        self, corr_matrix, sample_count, alpha=0.05
    ):
        """Return boolean matrix marking correlations significant at the given alpha."""
        if sample_count is None or sample_count <= 2:
            return np.zeros_like(corr_matrix, dtype=bool)
        df = sample_count - 2
        tcrit = self._t_critical_value(df, alpha)
        if tcrit is None:
            return np.zeros_like(corr_matrix, dtype=bool)
        rcrit = math.sqrt((tcrit ** 2) / (tcrit ** 2 + df))
        mask = np.abs(corr_matrix) >= rcrit
        np.fill_diagonal(mask, False)
        return mask

    def _t_critical_value(self, df: int, alpha: float = 0.05):
        """Return the two-tailed critical t value for the requested df."""
        if df <= 0:
            return None
        if df in _T_CRIT_TWO_TAILED_0_05:
            return _T_CRIT_TWO_TAILED_0_05[df]
        if NormalDist is not None:
            return NormalDist().inv_cdf(1 - alpha / 2.0)
        return _Z_CRIT_0_05

    # -------------------------------------------------------------------------
    # RF mode: grid search vs manual (UI only)
    # -------------------------------------------------------------------------

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
            label.setScaledContents(False)
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
            except Exception:
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
            except Exception:
                pass


    def _set_rf_info_icons(self):
        """Install one consolidated RF info icon."""
        tooltip = (
            "Random Forest parameters\n\n"
            "mtry: number of predictor variables randomly considered at each tree split. "
            "Lower values increase tree diversity; higher values let each split use more predictors.\n\n"
            "ntree: number of trees in the forest. More trees usually make predictions more stable, "
            "but increase processing time.\n\n"
            "nodesize: minimum number of samples allowed in a terminal node. Smaller values can capture "
            "more local detail; larger values produce smoother, more generalized trees.\n\n"
            "Search folds: number of cross-validation folds used to compare candidate RF parameter sets "
            "when Grid Search is enabled.\n\n"
            "Max iterations: maximum number of candidate parameter combinations tested during the search. "
            "More iterations explore the search space better, but are slower."
        )
        label = self._make_info_label("_rf_parameters_info_label", tooltip)
        if label is not None:
            try:
                layout = getattr(self.dlg, "groupRFParams", None).layout()
                layout.addWidget(label, 1, 4, Qt.AlignRight | Qt.AlignVCenter)
            except Exception:
                pass
        self._hide_legacy_info_buttons(["btnInfoRFSearchK", "btnInfoRFSearchIter"])
        self._clear_widget_tooltips([
            "spinRF_mtry_manual", "spinRF_ntree_manual", "spinRF_nodesize_manual",
            "spinRF_mtry_min", "spinRF_mtry_max", "spinRF_mtry_step",
            "spinRF_ntree_min", "spinRF_ntree_max", "spinRF_ntree_step",
            "spinRF_nodesize_min", "spinRF_nodesize_max", "spinRF_nodesize_step",
            "spinRFSearchK", "spinRFSearchIter",
        ])

    def _init_rf_mode_controls(self):
        """
        Wire RF controls for:
        - chkRFUseManual  (QRadioButton)
        - chkRFUseGrid    (QRadioButton)

        And groupboxes:
        - grpRFManual     (manual parameters)
        - grpRFGrid       (grid search parameters)
        """

        # 1) Main widgets
        self._rf_manual_widget = getattr(self.dlg, "chkRFUseManual", None)
        self._rf_grid_widget = getattr(self.dlg, "chkRFUseGrid", None)

        # 2) Parameter containers for each mode
        self._rf_manual_container = None
        for name in ["grpRFManual", "gbRFManual", "frameRFManual"]:
            w = getattr(self.dlg, name, None)
            if w is not None:
                self._rf_manual_container = w
                break

        self._rf_grid_container = None
        for name in ["grpRFGrid", "gbRFGrid", "frameRFGrid"]:
            w = getattr(self.dlg, name, None)
            if w is not None:
                self._rf_grid_container = w
                break

        # 3) Connect toggles
        if self._rf_grid_widget is not None and hasattr(self._rf_grid_widget, "toggled"):
            self._rf_grid_widget.toggled.connect(
                lambda checked: self._on_rf_mode_changed(source="grid", checked=checked)
            )

        if self._rf_manual_widget is not None and hasattr(self._rf_manual_widget, "toggled"):
            self._rf_manual_widget.toggled.connect(
                lambda checked: self._on_rf_mode_changed(source="manual", checked=checked)
            )

        # 4) Initial state: Manual ON, Grid OFF
        try:
            if self._rf_manual_widget is not None and hasattr(self._rf_manual_widget, "setChecked"):
                self._rf_manual_widget.setChecked(True)
            if self._rf_grid_widget is not None and hasattr(self._rf_grid_widget, "setChecked"):
                self._rf_grid_widget.setChecked(False)
        except Exception:
            pass

        self._apply_rf_mode()

    def _on_rf_mode_changed(self, source: str, checked: bool):
        """
        Exclusivity logic:
        - If Grid is activated → Manual off.
        - If Manual is activated → Grid off.
        - If for some reason both are off → force Manual on.
        """
        try:
            grid_on = bool(
                self._rf_grid_widget.isChecked()
                if self._rf_grid_widget is not None and hasattr(self._rf_grid_widget, "isChecked")
                else False
            )
            manual_on = bool(
                self._rf_manual_widget.isChecked()
                if self._rf_manual_widget is not None and hasattr(self._rf_manual_widget, "isChecked")
                else False
            )

            if source == "grid" and self._rf_grid_widget is not None:
                if checked:
                    # Grid ON → Manual OFF
                    if self._rf_manual_widget is not None and hasattr(self._rf_manual_widget, "setChecked"):
                        self._rf_manual_widget.setChecked(False)
                    grid_on = True
                    manual_on = False
                else:
                    # Grid OFF: if Manual is also OFF, force Manual ON
                    if not manual_on and self._rf_manual_widget is not None and hasattr(
                        self._rf_manual_widget, "setChecked"
                    ):
                        self._rf_manual_widget.setChecked(True)
                        manual_on = True

            elif source == "manual" and self._rf_manual_widget is not None:
                if checked:
                    # Manual ON → Grid OFF
                    if self._rf_grid_widget is not None and hasattr(self._rf_grid_widget, "setChecked"):
                        self._rf_grid_widget.setChecked(False)
                    manual_on = True
                    grid_on = False
                else:
                    # Manual OFF: if Grid is also OFF, force Grid ON
                    if not grid_on and self._rf_grid_widget is not None and hasattr(
                        self._rf_grid_widget, "setChecked"
                    ):
                        self._rf_grid_widget.setChecked(True)
                        grid_on = True

            self._apply_rf_mode()
        except Exception:
            # Do not let RF mode toggle crash the tab
            pass

    # -------------------- NEW: Robust widget enable/disable -------------------

    def _set_enabled_for_prefix(self, prefix: str, enabled: bool, suffix_any=None):
        """
        Enable/disable widgets on the dialog by attribute name prefix.
        Optionally restrict to those whose name ends with any suffix in suffix_any.
        """
        try:
            suf = tuple(suffix_any) if suffix_any else None
            for attr in dir(self.dlg):
                if attr.startswith("_"):
                    continue
                if not attr.startswith(prefix):
                    continue
                if suf is not None and (not attr.endswith(suf)):
                    continue
                w = getattr(self.dlg, attr, None)
                if w is not None and hasattr(w, "setEnabled"):
                    try:
                        w.setEnabled(bool(enabled))
                    except Exception:
                        pass
        except Exception:
            pass

    def _apply_rf_mode(self):
        """
        Enable/disable RF widgets according to selected mode.

        Manual mode:
        - Enable manual parameter widgets.
        - Disable grid search widgets and search tuning widgets.

        Grid mode:
        - Disable manual parameter widgets.
        - Enable grid search widgets and search tuning widgets.
        """
        try:
            manual_on = bool(
                self._rf_manual_widget.isChecked()
                if self._rf_manual_widget is not None and hasattr(self._rf_manual_widget, "isChecked")
                else True
            )
            grid_on = bool(
                self._rf_grid_widget.isChecked()
                if self._rf_grid_widget is not None and hasattr(self._rf_grid_widget, "isChecked")
                else False
            )

            if not manual_on and not grid_on:
                manual_on = True
                grid_on = False

            manual_widget_names = [
                "spinRF_mtry_manual",
                "spinRF_ntree_manual",
                "spinRF_nodesize_manual",
                "spinRFManualMtry",
                "spinRFManualNtree",
                "spinRFManualNodesize",
                "spinRFMtry",
                "spinRFNtree",
                "spinRFNodesize",
                "spnRFMtry",
                "spnRFNtree",
                "spnRFNodesize",
            ]

            grid_widget_names = [
                "spinRF_mtry_min",
                "spinRF_mtry_max",
                "spinRF_mtry_step",
                "spinRF_ntree_min",
                "spinRF_ntree_max",
                "spinRF_ntree_step",
                "spinRF_nodesize_min",
                "spinRF_nodesize_max",
                "spinRF_nodesize_step",
                "spinRFGridMtryMin",
                "spinRFGridMtryMax",
                "spinRFGridMtryStep",
                "spinRFGridNtreeMin",
                "spinRFGridNtreeMax",
                "spinRFGridNtreeStep",
                "spinRFGridNodeMin",
                "spinRFGridNodeMax",
                "spinRFGridNodeStep",
            ]

            search_only_widget_names = [
                "spinRFSearchK",
                "spinRFSearchIter",
                "labelRFSearchK",
                "labelRFSearchIter",
                "btnInfoRFSearchK",
                "btnInfoRFSearchIter",
            ]

            for name in manual_widget_names:
                w = getattr(self.dlg, name, None)
                if w is not None and hasattr(w, "setEnabled"):
                    try:
                        w.setEnabled(manual_on)
                    except Exception:
                        pass

            for name in grid_widget_names:
                w = getattr(self.dlg, name, None)
                if w is not None and hasattr(w, "setEnabled"):
                    try:
                        w.setEnabled(grid_on)
                    except Exception:
                        pass

            for name in search_only_widget_names:
                w = getattr(self.dlg, name, None)
                if w is not None and hasattr(w, "setEnabled"):
                    try:
                        w.setEnabled(grid_on)
                    except Exception:
                        pass

        except Exception:
            pass
    def _connect_rf_signals(self):
        """
        Connect RF interpolation button to the RF routine.

        We try the actual UI button name first and then some fallbacks.
        """
        rf_button = getattr(self.dlg, "btnRFRun", None)

        if rf_button is None:
            for name in ["btnRFInterpolate", "btnRFRunInterpolation", "btnRFRunRF", "btnRunRandomForest"]:
                b = getattr(self.dlg, name, None)
                if b is not None and hasattr(b, "clicked"):
                    rf_button = b
                    break

        if rf_button is None:
            try:
                for attr in dir(self.dlg):
                    if attr.startswith("_"):
                        continue
                    obj = getattr(self.dlg, attr, None)
                    if obj is None or not hasattr(obj, "clicked") or not hasattr(obj, "text"):
                        continue
                    try:
                        txt = (obj.text() or "").strip().lower()
                    except Exception:
                        txt = ""
                    if not txt:
                        continue
                    if ("run" in txt and "forest" in txt) or ("run" in txt and "rf" in txt):
                        rf_button = obj
                        break
            except Exception:
                pass

        if rf_button is not None and hasattr(rf_button, "clicked"):
            try:
                rf_button.clicked.disconnect()
            except Exception:
                pass
            rf_button.clicked.connect(self._on_run_rf_interpolation)

    def _import_rf_interpolation(self, show_message=False):
        global RF_AVAILABLE, RF_IMPORT_ERROR

        try:
            from .RF_Interpolation import rf_interpolation as rf_func
            RF_AVAILABLE = True
            RF_IMPORT_ERROR = ""
            return rf_func
        except Exception as e:
            RF_AVAILABLE = False
            RF_IMPORT_ERROR = str(e)

            if show_message:
                self._show_warning_message(
                    "Missing dependency",
                    "Random Forest is unavailable because the bundled dependency "
                    "could not be loaded.\n\n"
                    f"Details:\n{RF_IMPORT_ERROR}"
                )
            return None

    def _is_rf_using_grid_search(self) -> bool:
        """Return True if the RF mode is currently set to Grid search."""
        try:
            if self._rf_grid_widget is not None and hasattr(self._rf_grid_widget, "isChecked"):
                return bool(self._rf_grid_widget.isChecked())
        except Exception:
            pass
        return False

    def _get_rf_manual_params(self):
        """
        Read manual RF hyperparameters from UI.
        """
        def _read_int_widget(names, default_value):
            for name in names:
                w = getattr(self.dlg, name, None)
                if w is not None and hasattr(w, "value"):
                    try:
                        return int(w.value())
                    except Exception:
                        pass
            return int(default_value)

        ntree = _read_int_widget(
            ["spinRF_ntree_manual", "spinRFManualNtree", "spinRFNtree", "spnRFNtree"], 500
        )
        mtry = _read_int_widget(
            ["spinRF_mtry_manual", "spinRFManualMtry", "spinRFMtry", "spnRFMtry"], 3
        )
        nodesize = _read_int_widget(
            ["spinRF_nodesize_manual", "spinRFManualNodesize", "spinRFNodesize", "spnRFNodesize"], 5
        )

        manual_params = {
            "ntree": max(1, ntree),
            "mtry": max(1, mtry),
            "nodesize": max(1, nodesize),
        }
        return manual_params
    def _get_rf_grid_params(self):
        """
        Read grid search ranges from UI.
        """
        def _read_int_widget(names, default_value):
            for name in names:
                w = getattr(self.dlg, name, None)
                if w is not None and hasattr(w, "value"):
                    try:
                        return int(w.value())
                    except Exception:
                        pass
            return int(default_value)

        ntree_min = _read_int_widget(["spinRF_ntree_min", "spinRFGridNtreeMin"], 200)
        ntree_max = _read_int_widget(["spinRF_ntree_max", "spinRFGridNtreeMax"], 800)
        ntree_step = _read_int_widget(["spinRF_ntree_step", "spinRFGridNtreeStep"], 100)

        mtry_min = _read_int_widget(["spinRF_mtry_min", "spinRFGridMtryMin"], 1)
        mtry_max = _read_int_widget(["spinRF_mtry_max", "spinRFGridMtryMax"], 10)
        mtry_step = _read_int_widget(["spinRF_mtry_step", "spinRFGridMtryStep"], 1)

        node_min = _read_int_widget(["spinRF_nodesize_min", "spinRFGridNodeMin"], 1)
        node_max = _read_int_widget(["spinRF_nodesize_max", "spinRFGridNodeMax"], 20)
        node_step = _read_int_widget(["spinRF_nodesize_step", "spinRFGridNodeStep"], 1)

        grid_params = {
            "ntree": {
                "min": max(1, ntree_min),
                "max": max(ntree_min, ntree_max),
                "step": max(1, ntree_step),
            },
            "mtry": {
                "min": max(1, mtry_min),
                "max": max(mtry_min, mtry_max),
                "step": max(1, mtry_step),
            },
            "nodesize": {
                "min": max(1, node_min),
                "max": max(node_min, node_max),
                "step": max(1, node_step),
            },
        }
        return grid_params

    def _get_rf_search_folds(self) -> int:
        """
        Return the number of folds used for RF hyperparameter search.
        This parameter is only used when grid search is enabled.
        """
        for name in ["spinRFSearchK", "spinRFKFolds", "spinRF_k"]:
            w = getattr(self.dlg, name, None)
            if w is not None and hasattr(w, "value"):
                try:
                    return max(2, int(w.value()))
                except Exception:
                    pass
        return 3

    def _get_rf_search_iterations(self) -> int:
        """
        Return the maximum number of random-search iterations.
        This parameter is only used when grid search is enabled.
        """
        for name in ["spinRFSearchIter", "spinRFMaxIter", "spinRFIterations"]:
            w = getattr(self.dlg, name, None)
            if w is not None and hasattr(w, "value"):
                try:
                    return max(1, int(w.value()))
                except Exception:
                    pass
        return 10
    def _ensure_output_dir_for_rf(self):
        """
        Return the raster output directory for RF/SVM.
        """
        if not self._should_export_raster():
            return tempfile.gettempdir()
        proj = QgsProject.instance()
        proj_path = proj.fileName()
        if proj_path and os.path.isfile(proj_path):
            base_dir = os.path.dirname(proj_path)
            out_dir = os.path.join(base_dir, "BestFitInterpolation")
            os.makedirs(out_dir, exist_ok=True)
            return out_dir
        # If project is not saved, fallback to temp dir
        return tempfile.gettempdir()

    def _should_export_raster(self):
        chk = getattr(self.dlg, "chkExportRaster", None)
        if chk is None:
            return True
        try:
            return bool(chk.isChecked())
        except Exception:
            return True

    def _is_temporary_output_path(self, path):
        try:
            tmp_dir = os.path.abspath(tempfile.gettempdir())
            out_path = os.path.abspath(str(path))
            return os.path.commonpath([tmp_dir, out_path]) == tmp_dir
        except Exception:
            return False

    def _mark_temporary_layer(self, layer, raster_path=None):
        is_temporary = (not self._should_export_raster()) or self._is_temporary_output_path(raster_path)
        if layer is None or not is_temporary:
            return
        try:
            layer.setCustomProperty("bestfitinterpolator/output_storage", "temporary")
            layer.setCustomProperty("bestfitinterpolator/exported_to_project_folder", False)
            layer.setCustomProperty("skipMemoryLayersCheck", 0)
        except Exception:
            pass

    def _create_output_raster_layer(self, raster_path, layer_name):
        is_temporary = (not self._should_export_raster()) or self._is_temporary_output_path(raster_path)
        layer_cls = BestFitTemporaryRasterLayer if is_temporary else QgsRasterLayer
        layer = layer_cls(raster_path, layer_name, "gdal")
        if is_temporary:
            if not hasattr(self, "_temporary_output_layers"):
                self._temporary_output_layers = []
            self._temporary_output_layers.append(layer)
        return layer
        for method_name in ("setIsTemporary", "setTemporary"):
            method = getattr(layer, method_name, None)
            if callable(method):
                try:
                    method(True)
                except Exception:
                    pass
        try:
            flag_enum = getattr(QgsMapLayer, "LayerFlag", None)
            flag = getattr(flag_enum, "Temporary", None) if flag_enum is not None else None
            if flag is None:
                flag = getattr(QgsMapLayer, "Temporary", None)
            if flag is not None and hasattr(layer, "setFlags") and hasattr(layer, "flags"):
                layer.setFlags(layer.flags() | flag)
        except Exception:
            pass

    @staticmethod
    def _unique_columns(columns):
        seen = set()
        unique = []
        for col in columns:
            if col not in seen:
                seen.add(col)
                unique.append(col)
        return unique

    def _prompt_covariate_selection(self, cov_names, title="Select covariates"):
        """Ask which loaded covariates should be used by multivariate methods."""
        cov_names = [str(name) for name in (cov_names or []) if str(name).strip()]
        option_names = self._unique_columns(["x", "y"] + cov_names)

        previous = getattr(self, "_active_covariate_selection", None)
        previous = [name for name in (previous or option_names) if name in option_names]
        if not previous:
            previous = list(option_names)

        dlg = QDialog(self.dlg)
        dlg.setWindowTitle(title)
        layout = QVBoxLayout(dlg)
        checks = []
        for name in option_names:
            chk = QCheckBox(name)
            chk.setChecked(name in previous)
            layout.addWidget(chk)
            checks.append(chk)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec_() != QDialog.Accepted:
            return None
        selected = [chk.text() for chk in checks if chk.isChecked()]
        if not selected:
            self._show_warning_message("No predictors selected", "Select at least one predictor.")
            return None
        self._active_covariate_selection = list(selected)
        return selected

    def _build_points_dataframe_for_rf(self):
        """
        Build a DataFrame with:
        [x, y, target_variable, covariates...]

        Uses:
        - Points layer + variable from Data tab.
        - Covariates from the ML covariate list (raster sampling at point locations).
        """
        points_layer = self._get_selected_points_layer()
        if points_layer is None:
            self._show_warning_message(
                "No points layer",
                "Please select a valid points layer in the Data tab.",
            )
            return None, None, None

        attr_name = self.dlg.cmbVariable.currentText().strip()
        if not attr_name:
            self._show_warning_message(
                "No variable",
                "Please select a variable in the Data tab.",
            )
            return None, None, None

        attr_index = points_layer.fields().indexOf(attr_name)
        if attr_index < 0:
            self._show_warning_message(
                "Invalid variable",
                "Selected variable not found in the points layer.",
            )
            return None, None, None

        list_widget = self.dlg.listCovariates
        available_cov_names = [list_widget.item(i).text() for i in range(list_widget.count())]
        feature_names = self._prompt_covariate_selection(available_cov_names)
        if feature_names is None:
            return None, None, None
        cov_names = [name for name in feature_names if name not in ("x", "y")]

        raster_layers = [
            self.covariate_layers.get(name) for name in cov_names
        ]
        raster_layers = [
            rl for rl in raster_layers if isinstance(rl, QgsRasterLayer)
        ]
        if cov_names and not raster_layers:
            self._show_warning_message(
                "No valid rasters",
                "Loaded covariates are not valid raster layers.",
            )
            return None, None, None

        # CRS sync between points and rasters
        point_crs = points_layer.crs()
        raster_crs = raster_layers[0].crs() if raster_layers else None
        if raster_crs is not None and raster_crs.isValid() and point_crs.isValid() and raster_crs != point_crs:
            transform = QgsCoordinateTransform(point_crs, raster_crs, self.project)
        else:
            transform = None

        rows = []

        for feat in points_layer.getFeatures():
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue

            try:
                pt = geom.asPoint()
            except Exception:
                multi = geom.asMultiPoint()
                if not multi:
                    continue
                pt = multi[0]

            # Original coordinates (for x/y)
            orig_pt = pt

            sample_pt = pt
            if transform is not None:
                try:
                    sample_pt = transform.transform(pt)
                except Exception:
                    continue

            val = feat[attr_index]
            if val is None:
                continue

            try:
                target_val = float(val)
            except Exception:
                continue

            cov_values = []
            missing = False

            for rlayer in raster_layers:
                provider = rlayer.dataProvider()
                sample_point = QgsPointXY(sample_pt.x(), sample_pt.y())
                sample_val, res = provider.sample(sample_point, 1)
                if (not res) or (sample_val is None) or math.isnan(sample_val):
                    missing = True
                    break
                cov_values.append(float(sample_val))

            if missing:
                continue

            rows.append([orig_pt.x(), orig_pt.y(), target_val] + cov_values)

        if not rows:
            self._show_warning_message(
                "No training data",
                "No valid points were found with covariate values for RF training.",
            )
            return None, None, None

        headers = ["x", "y", attr_name] + cov_names
        points_df = pd.DataFrame(rows, columns=headers)
        return points_df, attr_name, feature_names

    def _get_selected_polygon_layer(self):
        """Return the polygon layer selected in the Data tab (for grid generation)."""
        combo = getattr(self.dlg, "cmbPolygonLayer", None)
        if combo is None or combo.currentIndex() < 0:
            return None

        layer_id = combo.currentData()
        layer = None
        if layer_id:
            layer = self.project.mapLayer(layer_id)

        if layer is None:
            name = combo.currentText()
            for lyr in self.project.mapLayers().values():
                if lyr.name() == name:
                    layer = lyr
                    break

        return layer

    def _build_grid_dataframe_for_rf(
        self,
        cov_names,
        context_name="RF",
        progress_title="RF interpolation",
        progress_label="Building RF interpolation grid...",
    ):
        """
        Build a grid DataFrame for RF interpolation.

        - Uses polygon extent and Data tab pixel size.
        - Builds a regular grid of cell centers.
        - Keeps only grid points inside the polygon.
        - Samples covariate rasters at each grid point.
        """
        poly_layer = self._get_selected_polygon_layer()
        if poly_layer is None:
            self._show_warning_message(
                "No polygon layer",
                f"Please select a polygon layer in the Data tab before {context_name} interpolation.",
            )
            return None, None

        pixel_size = self._get_data_pixel_size(default=0.01)
        extent = poly_layer.extent()
        xmin, ymin, xmax, ymax = extent.toRectF().getCoords()

        # Number of columns/rows
        n_cols = int(np.ceil((xmax - xmin) / pixel_size))
        n_rows = int(np.ceil((ymax - ymin) / pixel_size))
        if n_cols < 1 or n_rows < 1:
            self._show_warning_message(
                "Invalid grid",
                "Polygon extent and pixel size produced an invalid grid.",
            )
            return None, None

        # Build grid centers in polygon CRS
        x_coords = xmin + pixel_size * (np.arange(n_cols) + 0.5)
        y_coords = ymax - pixel_size * (np.arange(n_rows) + 0.5)
        grid_points = np.array(
            [(x_coords[c], y_coords[r]) for r in range(n_rows) for c in range(n_cols)]
        )

        # Build polygon mask using matplotlib Path
        combined_mask = np.zeros(grid_points.shape[0], dtype=bool)
        for feature in poly_layer.getFeatures():
            geom = feature.geometry()
            if geom.isMultipart():
                for part in geom.asMultiPolygon():
                    for ring in part:
                        ring_coords = [(pt.x(), pt.y()) for pt in ring]
                        ring_path = Path(ring_coords)
                        mask_i = ring_path.contains_points(grid_points)
                        combined_mask = np.logical_or(combined_mask, mask_i)
            else:
                for ring in geom.asPolygon():
                    ring_coords = [(pt.x(), pt.y()) for pt in ring]
                    ring_path = Path(ring_coords)
                    mask_i = ring_path.contains_points(grid_points)
                    combined_mask = np.logical_or(combined_mask, mask_i)

        inside_indices = np.where(combined_mask)[0]
        if inside_indices.size == 0:
            self._show_warning_message(
                "Empty grid",
                f"No grid cells fall inside the polygon for {context_name} interpolation.",
            )
            return None, None

        feature_names = list(cov_names or [])
        raster_cov_names = [name for name in feature_names if name not in ("x", "y")]

        # Prepare raster layers
        raster_layers = [self.covariate_layers.get(name) for name in raster_cov_names]
        raster_layers = [rl for rl in raster_layers if isinstance(rl, QgsRasterLayer)]
        if raster_cov_names and not raster_layers:
            self._show_warning_message(
                "No valid rasters",
                "Loaded covariates are not valid raster layers.",
            )
            return None, None

        # CRS transform from polygon to raster CRS (use first raster as reference)
        poly_crs = poly_layer.crs()
        raster_crs = raster_layers[0].crs() if raster_layers else None
        if raster_crs is not None and raster_crs.isValid() and poly_crs.isValid() and raster_crs != poly_crs:
            transform = QgsCoordinateTransform(poly_crs, raster_crs, self.project)
        else:
            transform = None

        rows = []
        total_inside = int(inside_indices.size)

        progress = QProgressDialog(
            "Building RF interpolation grid…", "Cancel", 0, total_inside, self.dlg
        )
        progress.setWindowTitle(progress_title)
        progress.setLabelText(progress_label)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        for idx_i, gi in enumerate(inside_indices, start=1):
            if progress.wasCanceled():
                break
            x, y = grid_points[gi]

            sample_pt = QgsPointXY(x, y)
            if transform is not None:
                try:
                    sample_pt = transform.transform(sample_pt)
                except Exception:
                    progress.setValue(idx_i)
                    QCoreApplication.processEvents()
                    continue

            cov_values = []
            missing = False

            for rlayer in raster_layers:
                provider = rlayer.dataProvider()
                sample_val, res = provider.sample(sample_pt, 1)
                if (not res) or (sample_val is None) or math.isnan(sample_val):
                    missing = True
                    break
                cov_values.append(float(sample_val))

            if not missing:
                rows.append([x, y] + cov_values)

            progress.setValue(idx_i)
            QCoreApplication.processEvents()

        progress.close()

        if not rows:
            self._show_warning_message(
                "No grid cells",
                "No valid grid cells were found with complete covariate data.",
            )
            return None, None

        headers = ["x", "y"] + raster_cov_names
        grid_df = pd.DataFrame(rows, columns=headers)

        # Return also a small metadata dict needed to build the output raster
        grid_meta = {
            "xmin": float(xmin),
            "ymin": float(ymin),
            "xmax": float(xmax),
            "ymax": float(ymax),
            "n_cols": int(n_cols),
            "n_rows": int(n_rows),
            "pixel_size": float(pixel_size),
            "poly_layer": poly_layer,
        }
        return grid_df, grid_meta

    def _write_rf_raster_from_grid_df(self, grid_df, grid_meta, target_column):
        """
        Convert RF grid predictions to a GeoTIFF and add it as a QGIS layer.
        """
        xmin = grid_meta["xmin"]
        ymin = grid_meta["ymin"]
        xmax = grid_meta["xmax"]
        ymax = grid_meta["ymax"]
        n_cols = grid_meta["n_cols"]
        n_rows = grid_meta["n_rows"]
        pixel_size = grid_meta["pixel_size"]
        poly_layer = grid_meta["poly_layer"]

        # Prepare a full grid array filled with NaN
        raster_array = np.full((n_rows, n_cols), np.nan, dtype=np.float32)

        # Map each grid_df row (x,y) to col/row indices
        xs = grid_df["x"].to_numpy(dtype=float)
        ys = grid_df["y"].to_numpy(dtype=float)
        preds = grid_df[f"{target_column}_pred"].to_numpy(dtype=float)

        for x, y, v in zip(xs, ys, preds):
            # Column index: from left
            col = int((x - xmin) / pixel_size)
            # Row index: from top (ymax downwards)
            row = int((ymax - y) / pixel_size)
            if 0 <= col < n_cols and 0 <= row < n_rows:
                raster_array[row, col] = float(v)

        # Create output path
        out_dir = self._ensure_output_dir_for_rf()
        safe_var = "".join(ch if ch.isalnum() else "_" for ch in target_column)
        base_name = f"RF_{safe_var}_{uuid.uuid4().hex[:6]}.tif"
        out_path = os.path.join(out_dir, base_name)

        # GeoTIFF writing
        driver = gdal.GetDriverByName("GTiff")
        ds = driver.Create(out_path, n_cols, n_rows, 1, gdal.GDT_Float32)
        if ds is None:
            self._show_warning_message(
                "RF raster error",
                "Could not create GeoTIFF for RF interpolation.",
            )
            return None

        geotransform = (xmin, pixel_size, 0.0, ymax, 0.0, -pixel_size)
        ds.SetGeoTransform(geotransform)

        srs = osr.SpatialReference()
        srs.ImportFromWkt(poly_layer.crs().toWkt())
        ds.SetProjection(srs.ExportToWkt())

        nodata_value = -9999.0
        raster_array_to_write = np.where(np.isfinite(raster_array), raster_array, nodata_value)

        band = ds.GetRasterBand(1)
        band.WriteArray(raster_array_to_write)
        band.SetNoDataValue(nodata_value)
        band.FlushCache()
        ds.FlushCache()
        ds = None

        # Add to QGIS
        layer_name = f"RF Interpolation ({target_column})"
        raster_layer = self._create_output_raster_layer(out_path, layer_name)
        if not raster_layer.isValid():
            self._show_warning_message(
                "RF raster error",
                "RF raster was written but could not be loaded as a QGIS layer.",
            )
            return None

        self._mark_temporary_layer(raster_layer, out_path)
        QgsProject.instance().addMapLayer(raster_layer)
        self.iface.messageBar().pushMessage(
            "RF interpolation",
            f"RF raster created: {out_path}",
            level=0,
        )
        return out_path

    def _update_rf_metrics_ui(self, train_mae, train_rmse, best_params):
        """
        Optionally update RF-specific metric labels if they exist.
        Also copy best parameters to the manual widgets so the user can reuse them.
        """
        def _set_text_if_exists(name, value_str):
            w = getattr(self.dlg, name, None)
            if w is not None and hasattr(w, "setText"):
                try:
                    w.setText(value_str)
                except Exception:
                    pass

        def _set_spin_value_if_exists(names, value):
            for name in names:
                w = getattr(self.dlg, name, None)
                if w is not None and hasattr(w, "setValue"):
                    try:
                        w.setValue(int(value))
                        return
                    except Exception:
                        pass

        if train_mae is not None:
            _set_text_if_exists("valRFTrainMAE", f"{train_mae:.3f}")
        if train_rmse is not None:
            _set_text_if_exists("valRFTrainRMSE", f"{train_rmse:.3f}")

        if best_params is not None:
            _set_text_if_exists("valRFBestNtree", str(best_params.get("ntree", "")))
            _set_text_if_exists("valRFBestMtry", str(best_params.get("mtry", "")))
            _set_text_if_exists("valRFBestNodesize", str(best_params.get("nodesize", "")))

            _set_spin_value_if_exists(
                ["spinRF_ntree_manual", "spinRFManualNtree", "spinRFNtree", "spnRFNtree"],
                best_params.get("ntree", 500),
            )
            _set_spin_value_if_exists(
                ["spinRF_mtry_manual", "spinRFManualMtry", "spinRFMtry", "spnRFMtry"],
                best_params.get("mtry", 3),
            )
            _set_spin_value_if_exists(
                ["spinRF_nodesize_manual", "spinRFManualNodesize", "spinRFNodesize", "spnRFNodesize"],
                best_params.get("nodesize", 5),
            )

        self._apply_rf_mode()
    def _on_run_rf_interpolation(self):
        """
        Entry point for the RF "Interpolate" button.

        - Builds training DataFrame (points_df) with x, y, target, covariates.
        - Builds interpolation grid (grid_df) with x, y, covariates.
        - Runs RF training + (optional) hyperparameter search.
        - Predicts over grid and writes a GeoTIFF.
        """
        if not ensure_ml_ready(parent=self.dlg, method_name="Random Forest"):
            return

        rf_interpolation = self._import_rf_interpolation(show_message=True)
        if rf_interpolation is None:
            return

        progress = QProgressDialog(
            "Preparing data…",
            "Cancel",
            0,
            0,
            self.dlg,
        )
        progress.setWindowTitle("Random Forest")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setRange(0, 0)
        progress.show()
        QCoreApplication.processEvents()

        try:
            progress.setLabelText("Preparing training data…")
            QCoreApplication.processEvents()

            points_df, target_name, cov_names = self._build_points_dataframe_for_rf()
            if points_df is None or target_name is None or cov_names is None:
                progress.close()
                return
            if progress.wasCanceled():
                progress.close()
                return

            progress.setLabelText("Preparing interpolation grid…")
            QCoreApplication.processEvents()

            grid_df, grid_meta = self._build_grid_dataframe_for_rf(cov_names)
            if grid_df is None or grid_meta is None:
                progress.close()
                return
            if progress.wasCanceled():
                progress.close()
                return

            use_grid_search = self._is_rf_using_grid_search()
            manual_params = self._get_rf_manual_params()
            grid_params = self._get_rf_grid_params()
            search_folds = self._get_rf_search_folds()
            search_iterations = self._get_rf_search_iterations()

            def _safe_set_progress(done, total, label=None):
                try:
                    if label:
                        progress.setLabelText(str(label))
                    if total is None or total <= 0:
                        progress.setRange(0, 0)
                    else:
                        progress.setRange(0, int(total))
                        progress.setValue(int(done))
                    QCoreApplication.processEvents()
                except Exception:
                    pass
                if progress.wasCanceled():
                    raise KeyboardInterrupt("Canceled by user")

            sig = None
            try:
                sig = inspect.signature(rf_interpolation)
            except Exception:
                sig = None

            kwargs = dict(
                points_df=points_df,
                grid_df=grid_df,
                target_column=target_name,
                covariate_columns=cov_names,
                use_grid_search=use_grid_search,
                manual_params=manual_params,
                grid_params=grid_params,
                x_col="x",
                y_col="y",
                n_jobs=1,
                random_state=20,
            )

            if sig is not None:
                if "cv_folds" in sig.parameters:
                    kwargs["cv_folds"] = search_folds
                if "max_iterations" in sig.parameters:
                    kwargs["max_iterations"] = search_iterations

            cb_param = None
            if sig is not None:
                for cand in ("progress_fn", "progress_callback", "callback", "progress"):
                    if cand in sig.parameters:
                        cb_param = cand
                        break

            if cb_param is not None:
                kwargs[cb_param] = _safe_set_progress
                _safe_set_progress(0, 100, "Hyperparameter optimization…")
            else:
                progress.setRange(0, 0)
                progress.setLabelText("Hyperparameter optimization…")
                QCoreApplication.processEvents()

            try:
                result = rf_interpolation(**kwargs)
            except KeyboardInterrupt:
                progress.close()
                self.iface.messageBar().pushMessage(
                    "RF interpolation", "Canceled by the user.", level=1
                )
                return

            progress.setLabelText("Writing RF raster…")
            progress.setRange(0, 0)
            QCoreApplication.processEvents()

        except Exception as e:
            progress.close()
            self._show_warning_message(
                "RF error",
                f"Random Forest interpolation failed:\n{e}",
            )
            return

        progress.close()

        if result is None or "grid_with_pred" not in result:
            self._show_warning_message(
                "RF error",
                "Random Forest interpolation did not return a valid result.",
            )
            return

        grid_with_pred = result["grid_with_pred"]
        best_params = result.get("best_params", None)
        train_mae = result.get("train_mae", None)
        train_rmse = result.get("train_rmse", None)
        importance_df = result.get("importance_df", None)

        out_path = self._write_rf_raster_from_grid_df(
            grid_with_pred, grid_meta, target_name
        )
        if out_path is None:
            return

        resolved_params = dict(best_params or manual_params)
        self._last_rf_interpolation_config = {
            "points_df": points_df.copy(deep=True),
            "target_name": str(target_name),
            "feature_names": list(cov_names),
            "resolved_params": resolved_params,
            "search_mode": "grid" if use_grid_search else "manual",
            "grid_params": {
                key: dict(value) for key, value in grid_params.items()
            },
            "search_folds": int(search_folds),
            "search_iterations": int(search_iterations),
        }

        self._update_rf_metrics_ui(train_mae, train_rmse, best_params)

        try:
            self._draw_rf_interpolation_preview(
                grid_with_pred,
                grid_meta,
                target_name,
            )
        except Exception:
            pass

        try:
            self._draw_rf_importance_plot(importance_df)
        except Exception:
            pass

        msg = f"RF interpolation finished."
        if best_params is not None:
            msg += f" Best: ntree={best_params.get('ntree')}, mtry={best_params.get('mtry')}, nodesize={best_params.get('nodesize')}."
        if (train_mae is not None) and (train_rmse is not None):
            msg += f" Train MAE={train_mae:.3f}, RMSE={train_rmse:.3f}."
        self.iface.messageBar().pushMessage(
            "RF interpolation",
            msg,
            level=0,
        )
    def _on_run_rf_cross_validation(self):
        """Run RF cross-validation using the same CV policy used in the other tabs."""
        config = getattr(self, "_last_rf_interpolation_config", None)
        if not config:
            self._show_warning_message(
                "RF validation",
                "Run Random Forest interpolation first. Validation uses the exact predictors and final parameters from that interpolation.",
            )
            return

        if not ensure_ml_ready(parent=self.dlg, method_name="Random Forest"):
            return

        self._reset_metric_labels([
            "valRFRMSE", "valRFRMSEpct", "valRFMAE",
            "valRFR2", "valRFPearsonR", "valRFLCCC",
        ])
        try:
            from .RF_Interpolation import _tune_random_forest
        except Exception as e:
            self._show_warning_message("RF validation error", f"Random Forest validation is unavailable.\n{e}")
            return

        progress = QProgressDialog("Preparing RF cross-validation…", "Cancel", 0, 0, self.dlg)
        progress.setWindowTitle("RF cross-validation")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setRange(0, 0)
        progress.show()
        QCoreApplication.processEvents()

        try:
            progress.setLabelText("Preparing training data…")
            QCoreApplication.processEvents()
            points_df = config["points_df"].copy(deep=True)
            target_name = config["target_name"]
            cov_names = list(config["feature_names"])

            feature_cols = list(cov_names)
            cols = self._unique_columns(["x", "y"] + feature_cols + [target_name])
            train_df = points_df[cols].dropna().copy()
            if len(train_df) < 5:
                progress.close()
                self._show_warning_message(
                    "RF validation error",
                    "At least 5 valid data points are required for cross-validation.",
                )
                return

            X_all = train_df[feature_cols].to_numpy(dtype=float)
            y_all = train_df[target_name].to_numpy(dtype=float)
            n = len(y_all)

            mode = self._rf_get_cv_mode()
            k = 10
            if self._rf_cv_k_spin is not None and hasattr(self._rf_cv_k_spin, "value"):
                try:
                    k = int(self._rf_cv_k_spin.value())
                except Exception:
                    k = 10
            if mode == "auto":
                mode, k_auto = self._rf_decide_auto_cv(n)
                if k_auto is not None:
                    k = k_auto

            if mode == "loocv":
                folds = [[i] for i in range(n)]
                cv_desc = f"RF LOOCV (n={n})"
            else:
                k = max(2, min(int(k), n))
                folds = self._rf_make_kfold_indices(n, k)
                cv_desc = f"RF {k}-fold CV (n={n})"

            preds = np.full(n, np.nan, dtype=float)
            resolved_params = dict(config["resolved_params"])

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
                if train_mask.sum() < 2:
                    continue

                X_train = X_all[train_mask]
                y_train = y_all[train_mask]
                X_test = X_all[test_idx]

                model, _ = _tune_random_forest(
                    X=X_train,
                    y=y_train,
                    use_grid_search=False,
                    manual_params=resolved_params,
                    grid_params={},
                    n_jobs=1,
                    random_state=20,
                    cv_folds=2,
                    max_iterations=1,
                    progress_fn=None,
                )
                preds[test_idx] = np.asarray(model.predict(X_test), dtype=float)

            progress.setValue(total_folds)
            progress.setLabelText("Computing RF validation metrics…")
            QCoreApplication.processEvents()

            rmse = self._rf_rmse(y_all, preds)
            lccc = self._rf_lccc(y_all, preds)
            rmse_pct = self._rf_rmse_pct(y_all, preds)
            r2 = self._rf_r2(y_all, preds)
            mae = self._rf_mae(y_all, preds)
            pearson_r = self._rf_pearson_r(y_all, preds)
            self._last_rf_cv_result = {
                "observed": np.asarray(y_all, dtype=float).tolist(),
                "predicted": np.asarray(preds, dtype=float).tolist(),
                "rmse": rmse,
                "lccc": lccc,
                "rmse_pct": rmse_pct,
                "r2": r2,
                "mae": mae,
                "pearson_r": pearson_r,
            }

            self._update_rf_validation_metrics_ui(rmse, lccc, rmse_pct, r2, mae, pearson_r)
            self._plot_rf_validation_scatter(y_all, preds, title=f"{cv_desc} — Observed vs Predicted")

        except KeyboardInterrupt:
            progress.close()
            self.iface.messageBar().pushMessage("RF validation", "Canceled by the user.", level=1)
            return
        except Exception as e:
            progress.close()
            self._show_warning_message("RF validation error", f"Random Forest validation failed:\n{e}")
            return

        progress.close()
        self.iface.messageBar().pushMessage(
            "RF validation",
            f"{cv_desc} finished. RMSE={rmse:.3f}, RMSE%={(rmse_pct if np.isfinite(rmse_pct) else float('nan')):.2f}%, "
            f"MAE={mae:.3f}, R²={(r2 if np.isfinite(r2) else float('nan')):.3f}, "
            f"Pearson r={(pearson_r if np.isfinite(pearson_r) else float('nan')):.3f}, "
            f"LCCC={(lccc if np.isfinite(lccc) else float('nan')):.3f}",
            level=0,
        )

    def _on_extract_covariates_clicked(self):
        """
        Extract covariate values at sampling points.

        Uses the rasters currently listed as 'Loaded covariates' (which may be
        original, resampled, standardized, or both).
        """
        points_layer = self._get_selected_points_layer()
        if points_layer is None:
            self._show_warning_message(
                "No points layer",
                "Please select a valid points layer in the Data tab.",
            )
            return

        attr_name = self.dlg.cmbVariable.currentText().strip()
        if not attr_name:
            self._show_warning_message(
                "No variable", "Please select a variable in the Data tab."
            )
            return

        attr_index = points_layer.fields().indexOf(attr_name)
        if attr_index < 0:
            self._show_warning_message(
                "Invalid variable",
                "Selected variable not found in the points layer.",
            )
            return

        list_widget = self.dlg.listCovariates
        cov_names = [list_widget.item(i).text() for i in range(list_widget.count())]

        if not cov_names:
            self._show_warning_message(
                "No covariates",
                "Please load at least one covariate raster before extracting values.",
            )
            return

        raster_layers = [
            self.covariate_layers.get(name) for name in cov_names
        ]
        raster_layers = [
            rl for rl in raster_layers if isinstance(rl, QgsRasterLayer)
        ]
        if not raster_layers:
            self._show_warning_message(
                "No valid rasters",
                "Loaded covariates are not valid raster layers.",
            )
            return

        raster_crs = raster_layers[0].crs()
        point_crs = points_layer.crs()

        if (
            raster_crs.isValid()
            and point_crs.isValid()
            and raster_crs != point_crs
        ):
            transform = QgsCoordinateTransform(
                point_crs, raster_crs, self.project
            )
        else:
            transform = None

        rows = []

        for feat in points_layer.getFeatures():
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue

            try:
                pt = geom.asPoint()
            except Exception:
                multi = geom.asMultiPoint()
                if not multi:
                    continue
                pt = multi[0]

            try:
                orig_pt = geom.asPoint()
            except Exception:
                multi = geom.asMultiPoint()
                if not multi:
                    continue
                orig_pt = multi[0]

            x_coord = orig_pt.x()
            y_coord = orig_pt.y()

            sample_pt = pt
            if transform is not None:
                try:
                    sample_pt = transform.transform(pt)
                except Exception:
                    continue

            val = feat[attr_index]
            if val is None:
                continue

            try:
                y_value = float(val)
            except Exception:
                continue

            cov_values = []
            missing = False

            for rlayer in raster_layers:
                provider = rlayer.dataProvider()
                sample_point = QgsPointXY(sample_pt.x(), sample_pt.y())
                sample_val, res = provider.sample(sample_point, 1)
                if (
                    not res
                    or sample_val is None
                    or math.isnan(sample_val)
                ):
                    missing = True
                    break
                cov_values.append(float(sample_val))

            if missing:
                continue

            rows.append([x_coord, y_coord, y_value] + cov_values)

        if not rows:
            self._show_warning_message(
                "No extractions",
                "No valid samples were found to extract covariate values.",
            )
            return

        # Optional: standardize covariates in memory (columns from index 3 onward)
        method = self._get_standardization_method()
        if self._standardization_for_extraction and method != "none":
            cov_matrix = np.array([r[3:] for r in rows], dtype=float)
            cov_std = self._standardize_data_matrix(cov_matrix, method)
            for i in range(len(rows)):
                rows[i][3:] = list(cov_std[i, :])

        headers = ["x", "y", attr_name] + cov_names
        self._extracted_headers = headers
        self._extracted_rows = rows

        self._show_info_message(
            "Extraction complete",
            f"Extracted covariate values for {len(rows)} point(s). "
            "Use 'View extracted table' to inspect the results.",
        )

    def _on_show_extracted_table_clicked(self):
        """Show a popup window with the extracted table."""
        if not self._extracted_headers or not self._extracted_rows:
            self._show_info_message(
                "No data",
                "No extracted data is available. Please run the extraction first.",
            )
            return

        dialog = QDialog(self.dlg)
        dialog.setWindowTitle("Extracted covariate values")

        table = QTableWidget(dialog)
        table.setRowCount(len(self._extracted_rows))
        table.setColumnCount(len(self._extracted_headers))
        table.setHorizontalHeaderLabels(self._extracted_headers)

        for i, row in enumerate(self._extracted_rows):
            for j, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                table.setItem(i, j, item)

        layout = QVBoxLayout(dialog)
        layout.addWidget(table)
        dialog.setLayout(layout)
        dialog.resize(900, 600)
        dialog.exec_()

    # -------------------------------------------------------------------------
    # Export CSV
    # -------------------------------------------------------------------------

    def _on_export_correlations_csv(self):
        """Export the last computed correlation matrix to a CSV file."""
        if self._last_corr_matrix is None or self._last_corr_names is None:
            self._show_info_message(
                "No correlations",
                "Please compute the correlation matrix before exporting.",
            )
            return

        corr = self._last_corr_matrix
        names = self._last_corr_names

        out_path, _ = QFileDialog.getSaveFileName(
            self.dlg,
            "Save correlation matrix as CSV",
            "",
            "CSV files (*.csv);;All files (*.*)",
        )
        if not out_path:
            return

        try:
            with open(out_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["variable"] + names)
                for i, name in enumerate(names):
                    row_values = [
                        f"{corr[i, j]:.6f}"
                        if not np.isnan(corr[i, j])
                        else ""
                        for j in range(len(names))
                    ]
                    writer.writerow([name] + row_values)
        except Exception as e:
            self._show_warning_message(
                "Export error", f"Could not write CSV file:\n{e}"
            )
            return

        self._show_info_message(
            "Export complete", f"Correlation matrix saved to:\n{out_path}"
        )

    # -------------------------------------------------------------------------
    # SVM interpolation (minimal controller, independent from RF)
    # -------------------------------------------------------------------------

    def _init_svm_plot_canvases(self):
        """Create matplotlib canvases for SVM interpolation and validation."""
        map_container = self._find_first_existing_widget([
            "canvasSVMInterpolation", "SVMMap", "widgetSVMMap", "frameSVMMap"
        ])
        val_container = self._find_first_existing_widget([
            "canvasSVMValidation", "SVMValidation", "widgetSVMValidation"
        ])

        if map_container is not None:
            map_layout = self._clear_layout_widgets(map_container)
            self._svm_map_fig = Figure()
            self._svm_map_canvas = FigureCanvas(self._svm_map_fig)
            self._svm_map_ax = None
            map_layout.addWidget(self._svm_map_canvas)
            self._install_plot_canvas_menu(
                self._svm_map_canvas,
                lambda: self._svm_map_fig if self._svm_last_map_payload is not None else None,
                "svm_interpolation",
                "SVM interpolation — zoom view",
                self._redraw_svm_map_into,
            )

        if val_container is not None:
            val_layout = self._clear_layout_widgets(val_container)
            self._svm_val_fig = Figure()
            self._svm_val_canvas = FigureCanvas(self._svm_val_fig)
            self._svm_val_ax = None
            val_layout.addWidget(self._svm_val_canvas)

    def _set_svm_ui_decimals(self):
        """Force all SVM double spin boxes to use two decimals."""
        svm_double_names = [
            "spinSVM_C_manual", "spinSVM_gamma_manual", "spinSVM_epsilon_manual",
            "spinSVM_C_min", "spinSVM_C_max", "spinSVM_C_step",
            "spinSVM_gamma_min", "spinSVM_gamma_max", "spinSVM_gamma_step",
            "spinSVM_epsilon_min", "spinSVM_epsilon_max", "spinSVM_epsilon_step",
        ]
        for name in svm_double_names:
            w = getattr(self.dlg, name, None)
            if w is not None and hasattr(w, "setDecimals"):
                try:
                    w.setDecimals(2)
                    if hasattr(w, "setSingleStep"):
                        w.setSingleStep(0.01)
                except Exception:
                    pass

    def _set_svm_info_icons(self):
        """Install one consolidated SVM info icon."""
        tooltip = (
            "Support Vector Machine parameters\n\n"
            "C: penalty for prediction errors. Higher values force the model to fit training data more strictly; "
            "lower values allow a smoother and more tolerant fit.\n\n"
            "gamma: influence radius of each sample in the RBF kernel. Higher values create more local and complex "
            "responses; lower values create smoother and broader responses.\n\n"
            "epsilon: insensitive margin around the regression function. Errors smaller than epsilon are ignored "
            "during training. Smaller values fit data more tightly; larger values smooth the model.\n\n"
            "Search folds: number of cross-validation folds used to compare candidate SVM parameter sets when "
            "Grid Search is enabled.\n\n"
            "Max iterations: maximum number of candidate parameter combinations tested during the search. More "
            "iterations explore the search space better, but increase processing time."
        )
        label = self._make_info_label("_svm_parameters_info_label", tooltip)
        if label is not None:
            try:
                layout = getattr(self.dlg, "horizontalLayoutSVMMode", None)
                if layout is not None:
                    layout.addStretch(1)
                    layout.addWidget(label)
            except Exception:
                pass
        self._hide_legacy_info_buttons([
            "btnInfoSVMCManual", "btnInfoSVMGammaManual", "btnInfoSVMEpsilonManual",
            "btnInfoSVMC", "btnInfoSVMGamma", "btnInfoSVMEpsilon",
            "btnInfoSVMSearchK", "btnInfoSVMSearchIter",
        ])
        self._clear_widget_tooltips([
            "spinSVM_C_manual", "spinSVM_gamma_manual", "spinSVM_epsilon_manual",
            "spinSVM_C_min", "spinSVM_C_max", "spinSVM_C_step",
            "spinSVM_gamma_min", "spinSVM_gamma_max", "spinSVM_gamma_step",
            "spinSVM_epsilon_min", "spinSVM_epsilon_max", "spinSVM_epsilon_step",
            "spinSVMSearchK", "spinSVMSearchIter",
        ])

    def _init_svm_mode_controls(self):
        """Wire SVM manual/grid search controls and apply initial state."""
        self._svm_manual_widget = getattr(self.dlg, "chkSVMUseManual", None)
        self._svm_grid_widget = getattr(self.dlg, "chkSVMUseGrid", None)

        if self._svm_manual_widget is not None:
            if hasattr(self._svm_manual_widget, "toggled"):
                self._svm_manual_widget.toggled.connect(
                    lambda checked: self._on_svm_mode_changed("manual", checked)
                )
            if hasattr(self._svm_manual_widget, "clicked"):
                self._svm_manual_widget.clicked.connect(
                    lambda checked=False: self._on_svm_mode_changed("manual", True)
                )
        if self._svm_grid_widget is not None:
            if hasattr(self._svm_grid_widget, "toggled"):
                self._svm_grid_widget.toggled.connect(
                    lambda checked: self._on_svm_mode_changed("grid", checked)
                )
            if hasattr(self._svm_grid_widget, "clicked"):
                self._svm_grid_widget.clicked.connect(
                    lambda checked=False: self._on_svm_mode_changed("grid", True)
                )

        try:
            if self._svm_manual_widget is not None and hasattr(self._svm_manual_widget, "setChecked"):
                self._svm_manual_widget.setChecked(True)
            if self._svm_grid_widget is not None and hasattr(self._svm_grid_widget, "setChecked"):
                self._svm_grid_widget.setChecked(False)
        except Exception:
            pass
        self._apply_svm_mode()

    def _on_svm_mode_changed(self, source, checked):
        """Keep SVM mode buttons mutually exclusive and refresh the UI."""
        try:
            if source == "manual" and checked:
                if self._svm_manual_widget is not None:
                    self._svm_manual_widget.blockSignals(True)
                    self._svm_manual_widget.setChecked(True)
                    self._svm_manual_widget.blockSignals(False)
                if self._svm_grid_widget is not None:
                    self._svm_grid_widget.blockSignals(True)
                    self._svm_grid_widget.setChecked(False)
                    self._svm_grid_widget.blockSignals(False)
            elif source == "grid" and checked:
                if self._svm_grid_widget is not None:
                    self._svm_grid_widget.blockSignals(True)
                    self._svm_grid_widget.setChecked(True)
                    self._svm_grid_widget.blockSignals(False)
                if self._svm_manual_widget is not None:
                    self._svm_manual_widget.blockSignals(True)
                    self._svm_manual_widget.setChecked(False)
                    self._svm_manual_widget.blockSignals(False)
        except Exception:
            pass
        self._apply_svm_mode(source=source if checked else None)

    def _apply_svm_mode(self, source=None):
        """Enable or disable SVM widgets according to selected mode."""
        manual_on = False
        grid_on = False
        try:
            manual_on = bool(self._svm_manual_widget.isChecked()) if self._svm_manual_widget is not None else False
            grid_on = bool(self._svm_grid_widget.isChecked()) if self._svm_grid_widget is not None else False
        except Exception:
            pass

        if source == "manual":
            manual_on, grid_on = True, False
        elif source == "grid":
            manual_on, grid_on = False, True
        elif manual_on and grid_on:
            grid_on = False
        elif not manual_on and not grid_on:
            manual_on = True

        try:
            if self._svm_manual_widget is not None:
                self._svm_manual_widget.blockSignals(True)
                self._svm_manual_widget.setChecked(manual_on)
                self._svm_manual_widget.blockSignals(False)
            if self._svm_grid_widget is not None:
                self._svm_grid_widget.blockSignals(True)
                self._svm_grid_widget.setChecked(grid_on)
                self._svm_grid_widget.blockSignals(False)
        except Exception:
            pass

        manual_names = [
            "grpSVMManual",
            "spinSVM_C_manual", "spinSVM_gamma_manual", "spinSVM_epsilon_manual",
            "labelSVM_C_manual", "labelSVM_gamma_manual", "labelSVM_epsilon_manual",
            "btnInfoSVMCManual", "btnInfoSVMGammaManual", "btnInfoSVMEpsilonManual",
        ]
        grid_names = [
            "grpSVMGrid",
            "labelSVMGridParameter", "labelSVMGridMin", "labelSVMGridMax", "labelSVMGridStep",
            "labelSVM_C", "labelSVM_gamma", "labelSVM_epsilon",
            "labelSVMSearchK", "labelSVMSearchIter",
            "spinSVM_C_min", "spinSVM_C_max", "spinSVM_C_step",
            "spinSVM_gamma_min", "spinSVM_gamma_max", "spinSVM_gamma_step",
            "spinSVM_epsilon_min", "spinSVM_epsilon_max", "spinSVM_epsilon_step",
            "spinSVMSearchK", "spinSVMSearchIter",
            "btnInfoSVMC", "btnInfoSVMGamma", "btnInfoSVMEpsilon",
            "btnInfoSVMSearchK", "btnInfoSVMSearchIter",
        ]
        for name in manual_names:
            w = getattr(self.dlg, name, None)
            if w is not None and hasattr(w, "setEnabled"):
                try:
                    w.setEnabled(bool(manual_on))
                except Exception:
                    pass
        for name in grid_names:
            w = getattr(self.dlg, name, None)
            if w is not None and hasattr(w, "setEnabled"):
                try:
                    w.setEnabled(bool(grid_on))
                except Exception:
                    pass
        for container_name in ("grpSVMManual", "grpSVMGrid"):
            container = getattr(self.dlg, container_name, None)
            if container is not None:
                try:
                    container.updateGeometry()
                    container.update()
                    container.repaint()
                except Exception:
                    pass

    def _connect_svm_signals(self):
        """Connect SVM interpolation and validation buttons."""
        btn = getattr(self.dlg, "btnSVMRun", None)
        if btn is None:
            for name in ["btnRunSVM", "btnSVMInterpolate", "btnSVMRunInterpolation"]:
                candidate = getattr(self.dlg, name, None)
                if candidate is not None and hasattr(candidate, "clicked"):
                    btn = candidate
                    break
        if btn is not None and hasattr(btn, "clicked"):
            try:
                btn.clicked.disconnect()
            except Exception:
                pass
            btn.clicked.connect(self._on_run_svm_interpolation)

        cv_btn = getattr(self.dlg, "btnSVMRunCV", None)
        if cv_btn is not None and hasattr(cv_btn, "clicked"):
            try:
                cv_btn.clicked.disconnect()
            except Exception:
                pass
            cv_btn.clicked.connect(self._on_run_svm_cross_validation)

        self._svm_cv_auto = getattr(self.dlg, "radSVM_CV_Auto", None)
        self._svm_cv_loocv = getattr(self.dlg, "radSVM_CV_LOOCV", None)
        self._svm_cv_kfold = getattr(self.dlg, "radSVM_CV_KFold", None)
        self._svm_cv_k_spin = getattr(self.dlg, "spinSVM_k", None)

        def _refresh_cv():
            try:
                if self._svm_cv_k_spin is not None:
                    enabled = bool(self._svm_cv_kfold is not None and self._svm_cv_kfold.isChecked())
                    self._svm_cv_k_spin.setEnabled(enabled)
            except Exception:
                pass

        for w in (self._svm_cv_auto, self._svm_cv_loocv, self._svm_cv_kfold):
            if w is not None:
                try:
                    w.toggled.connect(_refresh_cv)
                except Exception:
                    pass
                try:
                    w.clicked.connect(_refresh_cv)
                except Exception:
                    pass
        _refresh_cv()

    def _import_svm_interpolation(self, show_message=False):
        global SVM_AVAILABLE, SVM_IMPORT_ERROR
        try:
            from .SVM_Interpolation import svm_interpolation as svm_func
            SVM_AVAILABLE = True
            SVM_IMPORT_ERROR = ""
            return svm_func
        except Exception as e:
            SVM_AVAILABLE = False
            SVM_IMPORT_ERROR = str(e)
            if show_message:
                self._show_warning_message(
                    "Missing dependency",
                    "SVM is unavailable because the bundled dependency could not be loaded.\n\n"
                    f"Details:\n{SVM_IMPORT_ERROR}",
                )
            return None

    def _is_svm_using_grid_search(self):
        try:
            if self._svm_grid_widget is not None and hasattr(self._svm_grid_widget, "isChecked"):
                return bool(self._svm_grid_widget.isChecked())
        except Exception:
            pass
        return False

    def _get_svm_manual_params(self):
        def _read_float(name, default):
            w = getattr(self.dlg, name, None)
            if w is not None and hasattr(w, "value"):
                try:
                    return round(float(w.value()), 2)
                except Exception:
                    pass
            return float(default)
        return {
            "C": max(0.01, _read_float("spinSVM_C_manual", 1.0)),
            "gamma": max(0.01, _read_float("spinSVM_gamma_manual", 0.1)),
            "epsilon": max(0.0, _read_float("spinSVM_epsilon_manual", 0.1)),
        }

    def _get_svm_grid_params(self):
        def _read_float(name, default):
            w = getattr(self.dlg, name, None)
            if w is not None and hasattr(w, "value"):
                try:
                    return round(float(w.value()), 2)
                except Exception:
                    pass
            return float(default)
        return {
            "C": {
                "min": max(0.01, _read_float("spinSVM_C_min", 0.1)),
                "max": max(0.01, _read_float("spinSVM_C_max", 10.0)),
                "step": max(0.01, _read_float("spinSVM_C_step", 0.5)),
            },
            "gamma": {
                "min": max(0.01, _read_float("spinSVM_gamma_min", 0.01)),
                "max": max(0.01, _read_float("spinSVM_gamma_max", 1.0)),
                "step": max(0.01, _read_float("spinSVM_gamma_step", 0.1)),
            },
            "epsilon": {
                "min": max(0.0, _read_float("spinSVM_epsilon_min", 0.0)),
                "max": max(0.0, _read_float("spinSVM_epsilon_max", 1.0)),
                "step": max(0.01, _read_float("spinSVM_epsilon_step", 0.1)),
            },
        }

    def _get_svm_search_folds(self):
        w = getattr(self.dlg, "spinSVMSearchK", None)
        if w is not None and hasattr(w, "value"):
            try:
                return max(2, int(w.value()))
            except Exception:
                pass
        return 3

    def _get_svm_search_iterations(self):
        w = getattr(self.dlg, "spinSVMSearchIter", None)
        if w is not None and hasattr(w, "value"):
            try:
                return max(1, int(w.value()))
            except Exception:
                pass
        return 12

    def _write_svm_raster_from_grid_df(self, grid_df, grid_meta, target_column):
        """Convert SVM grid predictions to a GeoTIFF and add it as a QGIS layer."""
        xmin = grid_meta["xmin"]
        ymin = grid_meta["ymin"]
        xmax = grid_meta["xmax"]
        ymax = grid_meta["ymax"]
        n_cols = grid_meta["n_cols"]
        n_rows = grid_meta["n_rows"]
        pixel_size = grid_meta["pixel_size"]
        poly_layer = grid_meta["poly_layer"]

        raster_array = np.full((n_rows, n_cols), np.nan, dtype=np.float32)
        xs = grid_df["x"].to_numpy(dtype=float)
        ys = grid_df["y"].to_numpy(dtype=float)
        preds = grid_df[f"{target_column}_pred"].to_numpy(dtype=float)

        for x, y, v in zip(xs, ys, preds):
            col = int((x - xmin) / pixel_size)
            row = int((ymax - y) / pixel_size)
            if 0 <= col < n_cols and 0 <= row < n_rows:
                raster_array[row, col] = float(v)

        out_dir = self._ensure_output_dir_for_rf()
        safe_var = "".join(ch if ch.isalnum() else "_" for ch in target_column)
        base_name = f"SVM_{safe_var}_{uuid.uuid4().hex[:6]}.tif"
        out_path = os.path.join(out_dir, base_name)

        driver = gdal.GetDriverByName("GTiff")
        ds = driver.Create(out_path, n_cols, n_rows, 1, gdal.GDT_Float32)
        if ds is None:
            self._show_warning_message("SVM raster error", "Could not create GeoTIFF for SVM interpolation.")
            return None

        geotransform = (xmin, pixel_size, 0.0, ymax, 0.0, -pixel_size)
        ds.SetGeoTransform(geotransform)
        srs = osr.SpatialReference()
        srs.ImportFromWkt(poly_layer.crs().toWkt())
        ds.SetProjection(srs.ExportToWkt())

        nodata_value = -9999.0
        raster_array_to_write = np.where(np.isfinite(raster_array), raster_array, nodata_value)
        band = ds.GetRasterBand(1)
        band.WriteArray(raster_array_to_write)
        band.SetNoDataValue(nodata_value)
        band.FlushCache()
        ds.FlushCache()
        ds = None

        layer_name = f"SVM Interpolation ({target_column})"
        raster_layer = self._create_output_raster_layer(out_path, layer_name)
        if not raster_layer.isValid():
            self._show_warning_message("SVM raster error", "SVM raster was written but could not be loaded as a QGIS layer.")
            return None
        self._mark_temporary_layer(raster_layer, out_path)
        QgsProject.instance().addMapLayer(raster_layer)
        self.iface.messageBar().pushMessage("SVM interpolation", f"SVM raster created: {out_path}", level=0)
        return out_path

    def _draw_svm_interpolation_preview(self, grid_df, grid_meta, target_column, fig=None, canvas=None):
        """Draw SVM interpolation preview into the SVM map widget using viridis."""
        if fig is None:
            fig = self._svm_map_fig
        if canvas is None:
            canvas = self._svm_map_canvas
        if fig is None or canvas is None:
            return
        if fig is self._svm_map_fig:
            self._svm_last_map_payload = {
                "grid_df": grid_df.copy(),
                "grid_meta": dict(grid_meta),
                "target_column": target_column,
            }
        xmin = float(grid_meta["xmin"])
        xmax = float(grid_meta["xmax"])
        ymin = float(grid_meta["ymin"])
        ymax = float(grid_meta["ymax"])
        n_cols = int(grid_meta["n_cols"])
        n_rows = int(grid_meta["n_rows"])
        pixel_size = float(grid_meta["pixel_size"])
        poly_layer = grid_meta["poly_layer"]

        value_col = f"{target_column}_pred"
        if value_col not in grid_df.columns:
            return

        raster_array = np.full((n_rows, n_cols), np.nan, dtype=np.float32)
        xs = grid_df["x"].to_numpy(dtype=float)
        ys = grid_df["y"].to_numpy(dtype=float)
        vals = grid_df[value_col].to_numpy(dtype=float)
        for x, y, v in zip(xs, ys, vals):
            col = int((x - xmin) / pixel_size)
            row = int((ymax - y) / pixel_size)
            if 0 <= col < n_cols and 0 <= row < n_rows:
                raster_array[row, col] = float(v)

        fig.clear()
        ax = fig.add_subplot(111)
        ax.set_title(f"SVM interpolation ({target_column})")
        x_edges = np.linspace(xmin, xmax, n_cols + 1)
        y_edges = np.linspace(ymin, ymax, n_rows + 1)
        disp_array = np.flipud(raster_array)
        masked = np.ma.masked_invalid(disp_array)
        pm = ax.pcolormesh(x_edges, y_edges, masked, cmap="viridis", shading="auto")
        cbar = fig.colorbar(pm, ax=ax, orientation="vertical")
        cbar.set_label(target_column)
        try:
            for feat in poly_layer.getFeatures():
                geom = feat.geometry()
                if geom.isMultipart():
                    for part in geom.asMultiPolygon():
                        for ring in part:
                            ring_xy = [(pt.x(), pt.y()) for pt in ring]
                            patch = MplPolygon(ring_xy, closed=True, edgecolor="black", facecolor="none", linewidth=1.0)
                            ax.add_patch(patch)
                else:
                    for ring in geom.asPolygon():
                        ring_xy = [(pt.x(), pt.y()) for pt in ring]
                        patch = MplPolygon(ring_xy, closed=True, edgecolor="black", facecolor="none", linewidth=1.0)
                        ax.add_patch(patch)
        except Exception:
            pass
        ax.set_xlim(xmin, xmax)
        ax.set_ylim(ymin, ymax)
        ax.set_aspect("equal", adjustable="box")
        self._apply_basic_map_formatter(ax)
        fig.tight_layout()
        canvas.draw()
        if fig is self._svm_map_fig:
            self._svm_map_ax = ax

    def _on_run_svm_interpolation(self):
        """Entry point for the SVM interpolation button."""
        if not ensure_ml_ready(parent=self.dlg, method_name="Support Vector Machine"):
            return

        svm_interpolation = self._import_svm_interpolation(show_message=True)
        if svm_interpolation is None:
            return

        progress = QProgressDialog("Preparing data…", "Cancel", 0, 0, self.dlg)
        progress.setWindowTitle("SVM")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setRange(0, 0)
        progress.show()
        QCoreApplication.processEvents()

        try:
            progress.setLabelText("Preparing training data…")
            QCoreApplication.processEvents()
            points_df, target_name, cov_names = self._build_points_dataframe_for_rf()
            if points_df is None or target_name is None or cov_names is None:
                progress.close()
                return

            progress.setLabelText("Preparing interpolation grid…")
            QCoreApplication.processEvents()
            grid_df, grid_meta = self._build_grid_dataframe_for_rf(
                cov_names,
                context_name="SVM",
                progress_title="SVM interpolation",
                progress_label="Building SVM interpolation grid...",
            )
            if grid_df is None or grid_meta is None:
                progress.close()
                return

            use_grid_search = self._is_svm_using_grid_search()
            manual_params = self._get_svm_manual_params()
            grid_params = self._get_svm_grid_params()
            search_folds = self._get_svm_search_folds()
            search_iterations = self._get_svm_search_iterations()

            def _safe_set_progress(done, total, label=None):
                try:
                    if label:
                        progress.setLabelText(str(label))
                    if total is None or total <= 0:
                        progress.setRange(0, 0)
                    else:
                        progress.setRange(0, int(total))
                        progress.setValue(int(done))
                    QCoreApplication.processEvents()
                except Exception:
                    pass
                if progress.wasCanceled():
                    raise KeyboardInterrupt("Canceled by user")

            kwargs = dict(
                points_df=points_df,
                grid_df=grid_df,
                target_column=target_name,
                covariate_columns=cov_names,
                use_grid_search=use_grid_search,
                manual_params=manual_params,
                grid_params=grid_params,
                x_col="x",
                y_col="y",
                cv_folds=search_folds,
                max_iterations=search_iterations,
                n_jobs=1,
                random_state=20,
                progress_fn=_safe_set_progress,
            )
            result = svm_interpolation(**kwargs)

            progress.setLabelText("Writing SVM raster…")
            progress.setRange(0, 0)
            QCoreApplication.processEvents()
        except KeyboardInterrupt:
            progress.close()
            self.iface.messageBar().pushMessage("SVM interpolation", "Canceled by the user.", level=1)
            return
        except Exception as e:
            progress.close()
            self._show_warning_message("SVM error", f"SVM interpolation failed:\n{e}")
            return

        progress.close()

        if result is None or "grid_with_pred" not in result:
            self._show_warning_message("SVM error", "SVM interpolation did not return a valid result.")
            return

        grid_with_pred = result["grid_with_pred"]
        best_params = result.get("best_params", None)
        train_mae = result.get("train_mae", None)
        train_rmse = result.get("train_rmse", None)
        out_path = self._write_svm_raster_from_grid_df(grid_with_pred, grid_meta, target_name)
        if out_path is None:
            return

        resolved_params = dict(best_params or manual_params)
        self._last_svm_interpolation_config = {
            "points_df": points_df.copy(deep=True),
            "target_name": str(target_name),
            "feature_names": list(cov_names),
            "resolved_params": resolved_params,
            "search_mode": "grid" if use_grid_search else "manual",
            "grid_params": {
                key: dict(value) for key, value in grid_params.items()
            },
            "search_folds": int(search_folds),
            "search_iterations": int(search_iterations),
        }

        try:
            self._draw_svm_interpolation_preview(grid_with_pred, grid_meta, target_name)
        except Exception:
            pass

        msg = "SVM interpolation finished."
        if best_params is not None:
            msg += (
                f" Best: C={best_params.get('C', 0):.2f},"
                f" gamma={best_params.get('gamma', 0):.2f},"
                f" epsilon={best_params.get('epsilon', 0):.2f}."
            )
        if (train_mae is not None) and (train_rmse is not None):
            msg += f" Train MAE={train_mae:.2f}, RMSE={train_rmse:.2f}."
        self.iface.messageBar().pushMessage("SVM interpolation", msg, level=0)

    def _svm_get_cv_mode(self):
        try:
            if getattr(self, "_svm_cv_loocv", None) is not None and self._svm_cv_loocv.isChecked():
                return "loocv"
            if getattr(self, "_svm_cv_kfold", None) is not None and self._svm_cv_kfold.isChecked():
                return "kfold"
        except Exception:
            pass
        return "auto"

    def _svm_decide_auto_cv(self, n):
        if n <= 100:
            return "loocv", None
        if n <= 1000:
            return "kfold", 10
        return "kfold", 5

    def _svm_make_kfold_indices(self, n, k):
        idx = list(range(n))
        random.Random(20).shuffle(idx)
        folds = []
        base, rem = divmod(n, k)
        start = 0
        for i in range(k):
            size = base + (1 if i < rem else 0)
            folds.append(idx[start:start + size])
            start += size
        return folds

    def _update_svm_validation_metrics_ui(self, rmse, lccc, rmse_pct, r2, mae, pearson_r):
        def _set(name, value):
            w = getattr(self.dlg, name, None)
            if w is not None and hasattr(w, "setText"):
                w.setText(value)
        def _fmt(v):
            return "—" if v is None or not np.isfinite(v) else f"{v:.3f}"
        _set("valSVMRMSE", _fmt(rmse))
        _set("valSVMLCCC", _fmt(lccc))
        _set("valSVMRMSEpct", "—" if rmse_pct is None or not np.isfinite(rmse_pct) else f"{rmse_pct:.2f}")
        _set("valSVMR2", _fmt(r2))
        _set("valSVMMAE", _fmt(mae))
        _set("valSVMPearsonR", _fmt(pearson_r))

    def _plot_svm_validation_scatter(self, obs, pred, title="Observed vs Predicted (SVM CV)"):
        if self._svm_val_fig is None or self._svm_val_canvas is None:
            self._init_svm_plot_canvases()
        if self._svm_val_fig is None or self._svm_val_canvas is None:
            return
        fig = self._svm_val_fig
        canvas = self._svm_val_canvas
        fig.clear()
        ax = fig.add_subplot(111)
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
        if len(obs_valid) < 2:
            ax.scatter(obs_valid, pred_valid, s=20, alpha=0.9, facecolors='none', edgecolors='black')
            ax.set_title(f"{title} (not enough data for fit)", fontsize=8)
        else:
            ax.scatter(obs_valid, pred_valid, s=24, alpha=0.9, facecolors='none', edgecolors='black', label='Data')
            ax.plot([vmin, vmax], [vmin, vmax], '-', color='black', linewidth=1.0, label='1:1')
            m, b = np.polyfit(obs_valid, pred_valid, 1)
            ax.plot([vmin, vmax], [m * vmin + b, m * vmax + b], '-', color='#d62728', linewidth=1.0, label='Fit')
            ax.set_title(title, fontsize=8)
            ax.legend(loc='best', frameon=False, fontsize=8)
        ax.set_xlim(vmin, vmax)
        ax.set_ylim(vmin, vmax)
        try:
            ax.set_box_aspect(1)
        except Exception:
            ax.set_aspect('equal', adjustable='box')
        ax.grid(True, linestyle='--', linewidth=0.5, alpha=0.6)
        ax.tick_params(axis='both', labelsize=7)
        ax.set_xlabel("Observed", fontsize=8)
        ax.set_ylabel("Predicted", fontsize=8)
        try:
            fig.tight_layout()
        except Exception:
            pass
        canvas.draw_idle()
        self._svm_val_ax = ax

    def _on_run_svm_cross_validation(self):
        config = getattr(self, "_last_svm_interpolation_config", None)
        if not config:
            self._show_warning_message(
                "SVM validation",
                "Run SVM interpolation first. Validation uses the exact predictors and final parameters from that interpolation.",
            )
            return

        if not ensure_ml_ready(parent=self.dlg, method_name="Support Vector Machine"):
            return

        self._reset_metric_labels([
            "valSVMRMSE", "valSVMRMSEpct", "valSVMMAE",
            "valSVMR2", "valSVMPearsonR", "valSVMLCCC",
        ])
        try:
            from sklearn.svm import SVR
        except Exception as e:
            self._show_warning_message("SVM validation error", f"SVM validation is unavailable.\n{e}")
            return

        progress = QProgressDialog("Preparing SVM cross-validation…", "Cancel", 0, 0, self.dlg)
        progress.setWindowTitle("SVM cross-validation")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setRange(0, 0)
        progress.show()
        QCoreApplication.processEvents()
        try:
            points_df = config["points_df"].copy(deep=True)
            target_name = config["target_name"]
            cov_names = list(config["feature_names"])
            feature_cols = list(cov_names)
            cols = self._unique_columns(["x", "y"] + feature_cols + [target_name])
            train_df = points_df[cols].dropna().copy()
            if len(train_df) < 5:
                progress.close()
                self._show_warning_message("SVM validation error", "At least 5 valid data points are required for cross-validation.")
                return
            X_all = train_df[feature_cols].to_numpy(dtype=float)
            y_all = train_df[target_name].to_numpy(dtype=float)
            n = len(y_all)
            mode = self._svm_get_cv_mode()
            k = 10
            if getattr(self, "_svm_cv_k_spin", None) is not None and hasattr(self._svm_cv_k_spin, "value"):
                try:
                    k = int(self._svm_cv_k_spin.value())
                except Exception:
                    k = 10
            if mode == "auto":
                mode, k_auto = self._svm_decide_auto_cv(n)
                if k_auto is not None:
                    k = k_auto
            if mode == "loocv":
                folds = [[i] for i in range(n)]
                cv_desc = f"SVM LOOCV (n={n})"
            else:
                k = max(2, min(int(k), n))
                folds = self._svm_make_kfold_indices(n, k)
                cv_desc = f"SVM {k}-fold CV (n={n})"
            preds = np.full(n, np.nan, dtype=float)
            total_folds = len(folds)
            progress.setRange(0, total_folds)

            params = dict(config["resolved_params"])
            param_space = [(
                float(params["C"]),
                float(params["gamma"]),
                float(params["epsilon"]),
            )]

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
                X_test = X_all[test_idx]
                best_rmse = None
                best_model = None
                for C, gamma, epsilon in param_space:
                    try:
                        model = SVR(kernel="rbf", C=max(C, 1e-9), gamma=max(gamma, 1e-9), epsilon=max(epsilon, 1e-9))
                        model.fit(X_train, y_train)
                        pred_train = np.asarray(model.predict(X_train), dtype=float)
                        rmse_train = self._rf_rmse(y_train, pred_train)
                        if best_rmse is None or rmse_train < best_rmse:
                            best_rmse = rmse_train
                            best_model = model
                    except Exception:
                        continue
                if best_model is None:
                    continue
                try:
                    preds[test_idx] = np.asarray(best_model.predict(X_test), dtype=float)
                except Exception:
                    continue
            progress.setValue(total_folds)
            rmse = self._rf_rmse(y_all, preds)
            lccc = self._rf_lccc(y_all, preds)
            rmse_pct = self._rf_rmse_pct(y_all, preds)
            r2 = self._rf_r2(y_all, preds)
            mae = self._rf_mae(y_all, preds)
            pearson_r = self._rf_pearson_r(y_all, preds)
            self._last_svm_cv_result = {
                "observed": np.asarray(y_all, dtype=float).tolist(),
                "predicted": np.asarray(preds, dtype=float).tolist(),
                "rmse": rmse,
                "lccc": lccc,
                "rmse_pct": rmse_pct,
                "r2": r2,
                "mae": mae,
                "pearson_r": pearson_r,
            }
            self._update_svm_validation_metrics_ui(rmse, lccc, rmse_pct, r2, mae, pearson_r)
            self._plot_svm_validation_scatter(y_all, preds, cv_desc)
        except KeyboardInterrupt:
            self.iface.messageBar().pushMessage("SVM validation", "Canceled by the user.", level=1)
        except Exception as e:
            self._show_warning_message("SVM validation error", f"SVM cross-validation failed:\n{e}")
        finally:
            progress.close()

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _get_selected_points_layer(self):
        """Return the currently selected points layer from the Data tab combo."""
        combo = self.dlg.cmbPointsLayer
        if combo.currentIndex() < 0:
            return None

        layer_id = combo.currentData()
        layer = None
        if layer_id:
            layer = self.project.mapLayer(layer_id)

        if layer is None:
            name = combo.currentText()
            for lyr in self.project.mapLayers().values():
                if lyr.name() == name:
                    layer = lyr
                    break

        return layer

    def _show_info_message(self, title, text):
        """Show an information message box."""
        QMessageBox.information(self.dlg, title, text)

    def _show_warning_message(self, title, text):
        """Show a warning message box."""
        QMessageBox.warning(self.dlg, title, text)
