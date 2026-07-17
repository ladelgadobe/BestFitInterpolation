# -*- coding: utf-8 -*-
"""
framework_tab.py

Standalone controller for the Framework tab of BestFitInterpolator.
This module is intentionally isolated from the rest of the plugin so it can be
integrated gradually without affecting the currently working tabs.

All code comments are in English.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from pathlib import Path
import glob
import html
import math
import os
import tempfile
import numpy as np

try:
    from qgis.PyQt.QtCore import QObject, Qt, QCoreApplication
    from qgis.PyQt.QtGui import QIcon, QPixmap, QTextDocument
    from qgis.PyQt.QtPrintSupport import QPrinter
    from qgis.PyQt.QtWidgets import (
        QFileDialog,
        QCheckBox,
        QComboBox,
        QDialog,
        QDoubleSpinBox,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QListWidgetItem,
        QListWidget,
        QMessageBox,
        QPlainTextEdit,
        QProgressDialog,
        QPushButton,
        QMenu,
        QSizePolicy,
        QSplitter,
        QTableWidget,
        QTableWidgetItem,
        QHeaderView,
        QVBoxLayout,
        QWidget,
    )
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    from qgis.core import QgsProject, QgsRasterLayer
except Exception:  # pragma: no cover
    from PyQt5.QtCore import QObject, Qt, QCoreApplication
    from PyQt5.QtGui import QIcon, QPixmap, QTextDocument
    from PyQt5.QtPrintSupport import QPrinter
    from PyQt5.QtWidgets import (
        QFileDialog,
        QCheckBox,
        QComboBox,
        QDialog,
        QDoubleSpinBox,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QListWidgetItem,
        QListWidget,
        QMessageBox,
        QPlainTextEdit,
        QProgressDialog,
        QPushButton,
        QMenu,
        QSizePolicy,
        QSplitter,
        QTableWidget,
        QTableWidgetItem,
        QHeaderView,
        QVBoxLayout,
        QWidget,
    )
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    from qgis.core import QgsProject, QgsRasterLayer

try:
    from .framework_sdi_dialog import FrameworkSDIDialog
except Exception:  # pragma: no cover
    try:
        from framework_sdi_dialog import FrameworkSDIDialog  # type: ignore
    except Exception:
        FrameworkSDIDialog = None

try:
    from .framework_decision_tree_view import FrameworkDecisionTreeView
except Exception:  # pragma: no cover
    try:
        from framework_decision_tree_view import FrameworkDecisionTreeView  # type: ignore
    except Exception:
        FrameworkDecisionTreeView = None

try:
    from .array_shape_utils import (
        ensure_xy_2d,
        ensure_values_1d,
        finite_training_arrays,
        format_shape_error,
    )
except Exception:  # pragma: no cover
    try:
        from array_shape_utils import (  # type: ignore
            ensure_xy_2d,
            ensure_values_1d,
            finite_training_arrays,
            format_shape_error,
        )
    except Exception:
        ensure_xy_2d = ensure_values_1d = finite_training_arrays = format_shape_error = None

try:
    from .IDW_optimized import idw_interpolation, optimize_idw
    from .Thin_plate_spline import tps_interpolation
    from .kriging_ordinary import ordinary_kriging_interpolation
except Exception:  # pragma: no cover
    try:
        from IDW_optimized import idw_interpolation, optimize_idw  # type: ignore
        from Thin_plate_spline import tps_interpolation  # type: ignore
        from kriging_ordinary import ordinary_kriging_interpolation  # type: ignore
    except Exception:
        idw_interpolation = optimize_idw = tps_interpolation = ordinary_kriging_interpolation = None

try:
    from .kriging_reml import _HAS_SCIPY as _HAS_REML
    from .reml_bridge import fit_ok_reml_interface, cv_ok_reml_interface
except Exception:  # pragma: no cover
    try:
        from kriging_reml import _HAS_SCIPY as _HAS_REML  # type: ignore
        from reml_bridge import fit_ok_reml_interface, cv_ok_reml_interface  # type: ignore
    except Exception:
        _HAS_REML = False
        fit_ok_reml_interface = None
        cv_ok_reml_interface = None


ARTICLE_TITLE = "Performance of interpolation methods in digital soil mapping: the influence of data characteristics"
ARTICLE_AUTHORS = (
    "Laura Delgado Bejarano, Agda Loureiro Gonçalves Oliveira, João Vitor Fiolo Pozzuto, "
    "Dario Castañeda Sánchez & Lucas Rios do Amaral"
)
ARTICLE_DOI_URL = "https://doi.org/10.1007/s11119-025-10311-8"
ARTICLE_LINK_URL = "https://link.springer.com/article/10.1007/s11119-025-10311-8"
ARTICLE_CITATION = (
    "Delgado Bejarano, L., Loureiro Gonçalves Oliveira, A., Fiolo Pozzuto, J. V., "
    "Castañeda Sánchez, D., & Rios do Amaral, L. (2026). "
    "Performance of interpolation methods in digital soil mapping: the influence of data characteristics. "
    "Precision Agriculture, 27(1), 10."
)


@dataclass
class FrameworkDataState:
    """Shared state for the Framework tab.

    This object stores only high-level information so the tab can be wired to
    the existing plugin step by step.
    """

    variable_name: str = ""
    pixel_size: Optional[float] = None
    sample_count: Optional[int] = None
    moran_i: Optional[float] = None
    moran_p_value: Optional[float] = None
    spatial_pattern: str = "Not evaluated"
    sdi_value: Optional[float] = None
    sdi_status: str = "Not calculated"
    framework_mode: str = "Univariate"
    decision_summary: str = "Run diagnostics to classify the dataset in the framework."
    suggested_methods: List[str] = field(default_factory=list)
    eligible_methods: List[str] = field(default_factory=list)
    validated_methods: List[str] = field(default_factory=list)
    selected_winner: str = ""
    covariates: List[str] = field(default_factory=list)
    validation_results: List[Dict[str, Any]] = field(default_factory=list)
    ok_model_validation_results: List[Dict[str, Any]] = field(default_factory=list)


class FrameworkTabController(QObject):
    """Controller for the new Framework tab.

    The goal is to keep all Framework-specific behavior in a separate file.
    Existing tabs can continue to work untouched while this controller is wired
    progressively from the main plugin class.
    """

    METHOD_CHECKBOXES = {
        "TPS": "chkFrameworkTPS",
        "IDW": "chkFrameworkIDW",
        "OK": "chkFrameworkOK",
        "SVM": "chkFrameworkSVM",
        "RFE": "chkFrameworkRFE",
        "RK": "chkFrameworkRK",
    }
    REML_SAMPLE_LIMIT = 100
    MANUAL_REML_SAMPLE_LIMIT = 500

    def __init__(self, dialog: QWidget, plugin: Optional[Any] = None) -> None:
        super().__init__(dialog)
        self.dlg = dialog
        self.plugin = plugin
        self.state = FrameworkDataState()
        self._bind_widgets()
        self._connect_signals()
        self._initialize_ui()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------
    def _bind_widgets(self) -> None:
        """Bind frequently used widgets safely.

        Missing widgets are tolerated so the controller can evolve without
        crashing the whole plugin.
        """

        self.txt_variable = self._get("lblFrameworkVariableValue")
        self.txt_pixel = self._get("lblFrameworkPixelValue")
        self.txt_samples = self._get("lblFrameworkSamplesValue")
        self.txt_moran = self._get("lblFrameworkMoranValue")
        self.txt_pvalue = self._get("lblFrameworkPValueValue")
        self.txt_pattern = self._get("lblFrameworkPatternValue")
        self.txt_sdi = self._get("lblFrameworkSDIValue")
        self.txt_sdi_status = self._get("lblFrameworkSDIStatusValue")

        self.btn_calculate_sdi = self._get("btnFrameworkCalculateSDI")
        self.btn_open_sdi_window = self._get("btnFrameworkOpenSDIWindow")
        self.btn_info = self._get("btnFrameworkHeaderInfo") or self._get("btnFrameworkInfo")
        self.lbl_info_text = self._get("lblFrameworkInfoText")
        self.frame_point_map = self._get("frameFrameworkPointMap")
        self.frame_variogram = self._get("frameFrameworkVariogramPreview")
        self.lbl_point_placeholder = self._get("lblFrameworkPointMapPlaceholder")
        self.lbl_variogram_placeholder = self._get("lblFrameworkVariogramPlaceholder")
        self.frame_decision_figure = self._get("frameFrameworkFigure")
        self.lbl_decision_figure_placeholder = self._get("lblFrameworkFigurePlaceholder")
        self.framework_subtabs = self._get("frameworkSubTabs")

        self.rad_univariate = self._get("radFrameworkUnivariate")
        self.rad_full = self._get("radFrameworkFull")
        self.txt_decision_summary = self._get("txtFrameworkDecisionSummary")
        self.lbl_eligibility_preview = self._get("lblFrameworkEligibilityPreview")
        self.btn_evaluate_methods = self._get("btnFrameworkEvaluateMethods")
        self.btn_go_to_validation = self._get("btnFrameworkGoToValidation")

        self.list_covariates = self._get("listFrameworkCovariates")
        self.btn_reuse_covariates = self._get("btnFrameworkReuseCovariates")
        self.btn_load_covariates = self._get("btnFrameworkLoadCovariates")
        self.btn_remove_covariate = self._get("btnFrameworkRemoveCovariate")
        self.btn_clear_covariates = self._get("btnFrameworkClearCovariates")
        self.cmb_standardization = self._get("cmbFrameworkStandardization")
        self.spin_cov_pixel = self._get("spinFrameworkCovPixelSize")
        self.btn_compute_correlation = self._get("btnFrameworkComputeCorrelation")

        self.btn_select_suggested = self._get("btnFrameworkSelectSuggested")
        self.btn_run_validation = self._get("btnFrameworkRunValidation")
        self.table_validation = self._get("tableFrameworkValidation")
        self.cmb_validation_plot_type = self._get("cmbFrameworkValidationPlotType")
        self.cmb_validation_method = self._get("cmbFrameworkValidationMethod")
        self.lbl_validation_summary = self._get("lblFrameworkValidationSummary")
        self.btn_validation_graph = self._get("btnFrameworkGraph")
        self.lbl_validation_method = self._get("lblFrameworkValidationMethod")
        self.frame_validation_plot = self._get("frameFrameworkValidationPlot")
        self.lbl_validation_plot_placeholder = self._get("lblFrameworkValidationPlotPlaceholder")

        self.cmb_final_method = self._get("cmbFrameworkFinalMethod")
        self.chk_use_best = self._get("chkFrameworkUseBestMethod")
        self.btn_run_interpolation = self._get("btnFrameworkRunInterpolation")
        self.frame_interpolation_map = self._get("frameFrameworkInterpolationMap")
        self.lbl_interpolation_map_placeholder = self._get("lblFrameworkInterpolationMapPlaceholder")
        self.txt_summary_mode = self._get("txtFrameworkSummaryMode")
        self.lbl_summary_winner_title = self._get("lblFrameworkSummaryWinnerTitle")
        if self.lbl_summary_winner_title and hasattr(self.lbl_summary_winner_title, "setText"):
            self.lbl_summary_winner_title.setText("Selected")
        self.txt_summary_winner = self._get("txtFrameworkSummaryWinner")
        self.txt_summary_diagnostics = self._get("txtFrameworkSummaryDiagnostics")
        self.txt_summary_methods = self._get("txtFrameworkSummaryMethods")
        self.btn_preview_report = self._get("btnFrameworkPreviewReport")
        self.btn_export_pdf = self._get("btnFrameworkExportPDF")
        self.chk_report_decision_tree = self._get("chkFrameworkReportDecisionTree")

    def _connect_signals(self) -> None:
        """Connect UI signals to standalone handlers."""

        if self.btn_calculate_sdi:
            self.btn_calculate_sdi.clicked.connect(self.on_calculate_sdi_clicked)
        if self.btn_open_sdi_window:
            self.btn_open_sdi_window.clicked.connect(self.on_open_sdi_window_clicked)
        if self.btn_info:
            self.btn_info.clicked.connect(self.on_info_clicked)
        if self.rad_univariate:
            self.rad_univariate.toggled.connect(self.on_framework_mode_changed)
        if self.rad_full:
            self.rad_full.toggled.connect(self.on_framework_mode_changed)
        if self.btn_evaluate_methods:
            self.btn_evaluate_methods.clicked.connect(self.on_evaluate_methods_clicked)
        if self.btn_go_to_validation:
            self.btn_go_to_validation.hide()

        if self.btn_load_covariates:
            self.btn_load_covariates.clicked.connect(self.on_load_covariates_clicked)
        if self.btn_reuse_covariates:
            self.btn_reuse_covariates.clicked.connect(self.on_reuse_covariates_clicked)
        if self.btn_remove_covariate:
            self.btn_remove_covariate.clicked.connect(self.on_remove_covariate_clicked)
        if self.btn_clear_covariates:
            self.btn_clear_covariates.clicked.connect(self.on_clear_covariates_clicked)
        if self.btn_compute_correlation:
            self.btn_compute_correlation.clicked.connect(self.on_compute_correlation_clicked)

        for widget_name in ("Points", "Points_2", "poly", "cmbPointsLayer", "cmbVariable", "cmbPolygonLayer", "spinPixelSize"):
            widget = getattr(self.plugin.dlg, widget_name, None) if self.plugin is not None and getattr(self.plugin, "dlg", None) is not None else None
            if widget is None:
                continue
            try:
                if hasattr(widget, "currentIndexChanged"):
                    widget.currentIndexChanged.connect(self.refresh_from_plugin_context)
                elif hasattr(widget, "valueChanged"):
                    widget.valueChanged.connect(self.refresh_from_plugin_context)
            except Exception:
                pass


        if self.btn_select_suggested:
            self.btn_select_suggested.clicked.connect(self.on_select_suggested_clicked)
        if self.btn_run_validation:
            self.btn_run_validation.clicked.connect(self.on_run_validation_clicked)
        if self.table_validation:
            self.table_validation.itemSelectionChanged.connect(self._on_validation_table_selection_changed)
        if self.cmb_validation_plot_type:
            self.cmb_validation_plot_type.currentIndexChanged.connect(self._on_validation_plot_type_changed)
        if self.cmb_validation_method:
            self.cmb_validation_method.currentIndexChanged.connect(self._on_validation_method_changed)
            self.cmb_validation_method.activated.connect(self._on_validation_method_changed)
            self.cmb_validation_method.hide()
            self.cmb_validation_method.setEnabled(False)
        if self.lbl_validation_method:
            self.lbl_validation_method.hide()
        if self.btn_validation_graph:
            self.btn_validation_graph.hide()

        if self.chk_use_best:
            self.chk_use_best.toggled.connect(self.on_use_best_method_toggled)
        if self.cmb_final_method:
            self.cmb_final_method.currentTextChanged.connect(self.on_final_method_changed)
        if self.btn_run_interpolation:
            self.btn_run_interpolation.clicked.connect(self.on_run_interpolation_clicked)
        if self.btn_preview_report:
            self.btn_preview_report.clicked.connect(self.on_preview_report_clicked)
        if self.btn_export_pdf:
            self.btn_export_pdf.clicked.connect(self.on_export_pdf_clicked)

    def _initialize_ui(self) -> None:
        """Apply default behavior and placeholders."""

        if self.rad_univariate:
            self.rad_univariate.setChecked(True)
        if self.framework_subtabs and hasattr(self.framework_subtabs, "setCurrentIndex"):
            self.framework_subtabs.setCurrentIndex(0)
        if self.chk_use_best:
            self.chk_use_best.setChecked(True)
        self.on_use_best_method_toggled(bool(self.chk_use_best and self.chk_use_best.isChecked()))
        self._hide_framework_covariates_tab()

        if self.lbl_info_text:
            self.lbl_info_text.setText(
                "Framework guidance is derived from the master's work. "
                "Click the info button to view the article summary used in this tab."
            )

        self._apply_info_button_icon()
        self._attach_preview_canvases()
        self._attach_framework_result_canvases()
        self._ensure_view_covariates_button()
        self._show_framework_mode_image()
        self._ensure_observed_method_live_selector()
        self._ensure_observed_method_buttons()
        self._ensure_report_decision_tree_checkbox()
        self._polish_framework_mode_controls()
        self._polish_report_option_grid()

        if self.cmb_validation_plot_type and self.cmb_validation_plot_type.count() == 0:
            self.cmb_validation_plot_type.addItems(
                ["LCCC comparison", "RMSE comparison", "Observed vs Predicted"]
            )

        covariate_maps_report = self._get("chkFrameworkReportCovariateMaps")
        if covariate_maps_report:
            covariate_maps_report.setChecked(False)
            covariate_maps_report.hide()

        self.refresh_from_plugin_context()
        self.refresh_from_state()
        self._set_validation_method_controls_visible(False)
        self._update_view_covariates_button_state()

    def _polish_framework_mode_controls(self) -> None:
        """Give the Framework mode row enough height for a readable covariates button."""
        group = self._get("groupFrameworkMode")
        layout = group.layout() if group is not None else None
        try:
            group.setMinimumHeight(66)
            group.setMaximumHeight(78)
        except Exception:
            pass
        if layout is not None:
            try:
                layout.setContentsMargins(14, 8, 14, 8)
                layout.setSpacing(18)
            except Exception:
                pass
            try:
                layout.setStretch(0, 1)
                layout.setStretch(1, 1)
                layout.setStretch(2, 1)
            except Exception:
                pass

        for widget in (self.rad_univariate, self.rad_full, getattr(self, "btn_view_covariates", None)):
            if widget is None:
                continue
            try:
                widget.setMinimumHeight(28)
            except Exception:
                pass
        btn = getattr(self, "btn_view_covariates", None)
        if btn is not None:
            try:
                btn.setMinimumWidth(170)
                btn.setMaximumWidth(360)
            except Exception:
                pass

    def _polish_report_option_grid(self) -> None:
        """Arrange visible PDF report options into a balanced 3-column grid."""
        group = self._get("groupFrameworkReport")
        layout = group.layout() if group is not None else None
        if layout is None or not hasattr(layout, "addWidget"):
            return

        option_names = [
            "chkFrameworkReportPointMap",
            "chkFrameworkReportSemivariogram",
            "chkFrameworkReportCovariates",
            "chkFrameworkReportLCCCPlot",
            "chkFrameworkReportCorrelationPlot",
            "chkFrameworkReportMetricsTable",
            "chkFrameworkReportDecisionTree",
            "chkFrameworkReportObsPred",
            "chkFrameworkReportFinalMap",
        ]
        options = [self._get(name) for name in option_names]
        options = [widget for widget in options if widget is not None]

        hidden_cov_maps = self._get("chkFrameworkReportCovariateMaps")
        if hidden_cov_maps is not None:
            try:
                layout.removeWidget(hidden_cov_maps)
                hidden_cov_maps.hide()
            except Exception:
                pass

        for widget in options:
            try:
                layout.removeWidget(widget)
            except Exception:
                pass

        for index, widget in enumerate(options):
            row, col = divmod(index, 3)
            try:
                widget.show()
                layout.addWidget(widget, row, col)
            except Exception:
                pass

        button_layout = getattr(self, "_framework_report_button_layout", None)
        if button_layout is None:
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item is not None and item.layout() is not None:
                    candidate = item.layout()
                    if candidate.objectName() == "horizontalLayout_frameworkReportButtons":
                        button_layout = candidate
                        self._framework_report_button_layout = button_layout
                        break
        if button_layout is not None:
            try:
                layout.addLayout(button_layout, 3, 0, 1, 3)
            except Exception:
                pass

        try:
            layout.setHorizontalSpacing(28)
            layout.setVerticalSpacing(12)
            layout.setColumnStretch(0, 1)
            layout.setColumnStretch(1, 1)
            layout.setColumnStretch(2, 1)
        except Exception:
            pass

    def _ensure_report_decision_tree_checkbox(self) -> None:
        """Add the Framework Decision tree option to the PDF report controls."""
        checkbox = self._get("chkFrameworkReportDecisionTree")
        if checkbox is None:
            group = self._get("groupFrameworkReport")
            if group is None:
                return
            checkbox = QCheckBox("Include framework decision tree", group)
            checkbox.setObjectName("chkFrameworkReportDecisionTree")
            checkbox.setChecked(True)
            try:
                checkbox.setToolTip("Include the dynamic Framework Decision flowchart in the exported PDF report.")
            except Exception:
                pass

            layout = group.layout()
            if layout is not None:
                try:
                    layout.addWidget(checkbox, 2, 0)
                except Exception:
                    pass
        self.chk_report_decision_tree = checkbox

    def _include_report_decision_tree(self) -> bool:
        checkbox = getattr(self, "chk_report_decision_tree", None) or self._get("chkFrameworkReportDecisionTree")
        if checkbox is None:
            return True
        try:
            return bool(checkbox.isChecked())
        except Exception:
            return True


    # ------------------------------------------------------------------
    # Automatic Framework overview sync and previews
    # ------------------------------------------------------------------
    def _attach_preview_canvases(self) -> None:
        self.point_map_fig = Figure(figsize=(4.6, 3.4))
        self.point_map_canvas = FigureCanvas(self.point_map_fig)
        self.variogram_fig = Figure(figsize=(4.6, 3.4))
        self.variogram_canvas = FigureCanvas(self.variogram_fig)
        self._stabilize_canvas_widget(self.point_map_canvas)
        self._stabilize_canvas_widget(self.variogram_canvas)

        self._embed_canvas(self.frame_point_map, self.point_map_canvas, self.lbl_point_placeholder)
        self._embed_canvas(self.frame_variogram, self.variogram_canvas, self.lbl_variogram_placeholder)
        self._install_canvas_menu(self.point_map_canvas, lambda: self.point_map_fig, "framework_point_map", "Point map")
        self._install_canvas_menu(self.variogram_canvas, lambda: self.variogram_fig, "framework_semivariogram", "Semivariogram")

    def _attach_framework_result_canvases(self) -> None:
        self.validation_fig = Figure(figsize=(5.2, 3.6))
        self.validation_canvas = FigureCanvas(self.validation_fig)
        self.interpolation_fig = Figure(figsize=(5.2, 3.8))
        self.interpolation_canvas = FigureCanvas(self.interpolation_fig)
        self._stabilize_canvas_widget(self.validation_canvas)
        self._stabilize_canvas_widget(self.interpolation_canvas)
        self._embed_canvas(self.frame_validation_plot, self.validation_canvas, self.lbl_validation_plot_placeholder)
        self._embed_canvas(self.frame_interpolation_map, self.interpolation_canvas, self.lbl_interpolation_map_placeholder)
        self._install_canvas_menu(self.validation_canvas, lambda: self.validation_fig, "framework_validation", "Validation plot")
        self._install_canvas_menu(self.interpolation_canvas, lambda: self.interpolation_fig, "framework_interpolation", "Interpolation map")

    def _ensure_observed_method_buttons(self) -> None:
        """Create a direct method selector for the observed/predicted plot."""
        if getattr(self, "_observed_method_panel", None) is not None:
            return
        parent = self.frame_validation_plot or self._get("groupFrameworkValidationPlotControls")
        if parent is None:
            return
        layout = parent.layout()
        if layout is None:
            layout = QVBoxLayout(parent)
            layout.setContentsMargins(0, 0, 0, 0)
        panel = QWidget(parent)
        panel_layout = QHBoxLayout(panel)
        panel_layout.setContentsMargins(4, 2, 4, 2)
        panel_layout.setSpacing(6)
        panel.hide()
        self._observed_method_panel = panel
        self._observed_method_layout = panel_layout
        self._observed_method_buttons = {}
        if hasattr(layout, "insertWidget"):
            layout.insertWidget(0, panel)
        else:
            layout.addWidget(panel)

    def _ensure_observed_method_live_selector(self) -> None:
        """Create hidden legacy controls; the visible selector lives inside the plot."""
        if getattr(self, "cmb_observed_plot_method", None) is not None:
            return
        group = self._get("groupFrameworkValidationPlotControls")
        if group is None:
            return
        layout = group.layout()
        if layout is None:
            return
        lbl = QLabel("Observed/predicted method", group)
        cmb = QComboBox(group)
        btn = QPushButton("Update observed/predicted plot", group)
        lbl.hide()
        cmb.hide()
        btn.hide()
        cmb.setMinimumWidth(220)
        btn.setMinimumWidth(210)
        self.lbl_observed_plot_method = lbl
        self.cmb_observed_plot_method = cmb
        self.btn_observed_plot_update = btn
        try:
            layout.addWidget(lbl, 1, 0, 1, 1)
            layout.addWidget(cmb, 1, 1, 1, 1)
            layout.addWidget(btn, 1, 2, 1, 1)
        except TypeError:
            layout.addWidget(lbl)
            layout.addWidget(cmb)
            layout.addWidget(btn)
        cmb.activated.connect(self._on_observed_live_selector_changed)
        btn.clicked.connect(self._on_observed_live_selector_changed)

    def _ensure_view_covariates_button(self) -> None:
        """Add a button beside the Full framework radio to reopen covariates."""
        if getattr(self, "btn_view_covariates", None) is not None:
            return
        group = self._get("groupFrameworkMode")
        if group is None:
            return
        layout = group.layout()
        if layout is None:
            return
        btn = QPushButton("View covariates", group)
        btn.setObjectName("btnFrameworkViewCovariates")
        btn.setMinimumWidth(170)
        btn.setMinimumHeight(28)
        btn.clicked.connect(self._open_framework_covariates_dialog)
        self.btn_view_covariates = btn
        try:
            layout.addWidget(btn)
        except TypeError:
            layout.addWidget(btn)

    def _update_view_covariates_button_state(self) -> None:
        btn = getattr(self, "btn_view_covariates", None)
        if btn is not None:
            btn.setEnabled(bool(self.rad_full and self.rad_full.isChecked()))

    def _install_canvas_menu(self, canvas: Optional[FigureCanvas], get_figure_fn, save_prefix: str, zoom_title: str) -> None:
        if canvas is None:
            return
        if not hasattr(self, "_canvas_menu_bound"):
            self._canvas_menu_bound = set()
        key = id(canvas)
        if key in self._canvas_menu_bound:
            return
        try:
            canvas.setContextMenuPolicy(Qt.CustomContextMenu)
            canvas.customContextMenuRequested.connect(
                lambda pos, c=canvas, gf=get_figure_fn, sp=save_prefix, zt=zoom_title: self._show_canvas_context_menu(c, gf, sp, zt, pos)
            )
            self._canvas_menu_bound.add(key)
        except Exception:
            pass

    def _stabilize_canvas_widget(self, canvas: Optional[FigureCanvas]) -> None:
        """Keep Matplotlib canvases from resizing their parent after redraws."""
        if canvas is None:
            return
        try:
            canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            canvas.setMinimumSize(1, 1)
            canvas.updateGeometry()
        except Exception:
            pass

    def _sync_figure_to_canvas(self, fig: Optional[Figure], canvas: Optional[FigureCanvas], fallback=(5.2, 3.6)) -> None:
        """Match figure inches to the current Qt canvas size before plotting."""
        if fig is None or canvas is None:
            return
        try:
            width = max(int(canvas.width()), 80)
            height = max(int(canvas.height()), 80)
            dpi = float(fig.get_dpi() or 100.0)
            try:
                canvas.resize(int(width), int(height))
                canvas.setMinimumSize(int(width), int(height))
                canvas.updateGeometry()
            except Exception:
                pass
            fig.set_size_inches(width / dpi, height / dpi, forward=True)
        except Exception:
            try:
                fig.set_size_inches(float(fallback[0]), float(fallback[1]), forward=True)
            except Exception:
                pass

    def _show_canvas_context_menu(self, canvas: FigureCanvas, get_figure_fn, save_prefix: str, zoom_title: str, pos) -> None:
        fig = get_figure_fn() if callable(get_figure_fn) else None
        menu = QMenu(self.dlg)
        act_view = menu.addAction("View larger view")
        act_copy = menu.addAction("Copy graph")
        act_save = menu.addAction("Save graph")
        if fig is None:
            act_view.setEnabled(False)
            act_copy.setEnabled(False)
            act_save.setEnabled(False)
        chosen = menu.exec_(canvas.mapToGlobal(pos))
        if chosen == act_copy and fig is not None:
            self._copy_figure_to_clipboard(fig)
        elif chosen == act_save and fig is not None:
            suggested = os.path.join(tempfile.gettempdir(), f"{save_prefix}.png")
            path, _ = QFileDialog.getSaveFileName(self.dlg, "Save graph", suggested, "PNG Images (*.png)")
            if path:
                try:
                    fig.savefig(path, dpi=300, bbox_inches="tight")
                except Exception as exc:
                    QMessageBox.warning(self.dlg, "Save graph", f"Could not save graph:\n{exc}")
        elif chosen == act_view and fig is not None:
            self._open_larger_figure(fig, zoom_title)

    def _copy_figure_to_clipboard(self, fig: Figure) -> None:
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
        except Exception as exc:
            QMessageBox.warning(self.dlg, "Copy graph", f"Could not copy graph:\n{exc}")

    def _open_larger_figure(self, source_fig: Figure, title: str) -> None:
        dlg = QDialog(self.dlg)
        dlg.setWindowTitle(title)
        layout = QVBoxLayout(dlg)
        fig = Figure(figsize=(9, 6.5))
        canvas = FigureCanvas(fig)
        layout.addWidget(canvas)
        try:
            import io
            import matplotlib.image as mpimg
            buf = io.BytesIO()
            source_fig.savefig(buf, format="png", dpi=180, bbox_inches="tight")
            buf.seek(0)
            arr = mpimg.imread(buf)
            fig.clear()
            ax = fig.add_subplot(111)
            ax.imshow(arr)
            ax.axis("off")
            canvas.draw()
        except Exception:
            pass
        dlg.resize(980, 720)
        dlg.exec_()

    def _embed_canvas(self, frame: Optional[QWidget], canvas: Optional[FigureCanvas], placeholder: Optional[QWidget] = None) -> None:
        if frame is None or canvas is None:
            return
        try:
            from qgis.PyQt.QtWidgets import QVBoxLayout
        except Exception:  # pragma: no cover
            from PyQt5.QtWidgets import QVBoxLayout
        layout = frame.layout()
        if layout is None:
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(0, 0, 0, 0)
        for i in reversed(range(layout.count())):
            item = layout.itemAt(i)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        if placeholder is not None:
            try:
                placeholder.hide()
            except Exception:
                pass
        self._stabilize_canvas_widget(canvas)
        layout.addWidget(canvas)

    def _hide_framework_covariates_tab(self) -> None:
        if self.framework_subtabs is None:
            return
        tab = self._get("tabFrameworkCovariates")
        if tab is None:
            return
        try:
            idx = self.framework_subtabs.indexOf(tab)
            if idx >= 0:
                if hasattr(self.framework_subtabs, "setTabVisible"):
                    self.framework_subtabs.setTabVisible(idx, False)
                else:
                    self.framework_subtabs.removeTab(idx)
        except Exception:
            pass

    def refresh_from_plugin_context(self, *args) -> None:
        """Read the current Data tab context automatically and update Framework."""
        if self.plugin is None or getattr(self.plugin, "dlg", None) is None:
            return
        try:
            data = self._collect_current_plugin_data()
            if not data:
                return
            self.load_from_data_tab(data)
            self._draw_framework_point_map(data)
            self._draw_framework_variogram_preview(data, use_state=False)
        except Exception:
            pass

    def refresh_variogram_preview_from_state(self) -> None:
        """Redraw the Framework variogram preview using the current saved SDI state."""
        try:
            data = self._collect_current_plugin_data()
            if data:
                self._draw_framework_variogram_preview(data, use_state=True)
        except Exception:
            pass

    def reset_for_data_change(self, keep_data_context: bool = True) -> None:
        """Clear Framework outputs that belong to the previous dataset."""
        current_mode = self.state.framework_mode
        covariates = list(self.state.covariates)
        self.state = FrameworkDataState()
        self.state.framework_mode = current_mode
        self.state.covariates = covariates
        self.state.decision_summary = "Dataset changed. Run diagnostics and evaluate methods again."

        for key in (
            "sdi_class",
            "variogram_model",
            "nugget",
            "psill",
            "range",
            "fit_method",
            "ok_fit_method",
            "decision_path",
            "selected_method",
            "validation_plot_method",
            "lag_count",
            "max_distance",
            "lag_width",
            "experimental_distances",
            "experimental_semivariances",
        ):
            self.state.__dict__.pop(key, None)

        for fig_name, canvas_name in (
            ("point_map_fig", "point_map_canvas"),
            ("variogram_fig", "variogram_canvas"),
            ("validation_fig", "validation_canvas"),
            ("interpolation_fig", "interpolation_canvas"),
        ):
            fig = getattr(self, fig_name, None)
            canvas = getattr(self, canvas_name, None)
            try:
                if fig is not None:
                    fig.clear()
                if canvas is not None:
                    canvas.draw_idle()
            except Exception:
                pass

        try:
            self._populate_validation_table([])
        except Exception:
            pass
        try:
            self._refresh_observed_plot_controls_from_results()
        except Exception:
            pass

        if self.lbl_validation_summary:
            self.lbl_validation_summary.setText("Validation pending for the current dataset.")

        if keep_data_context and self.plugin is not None:
            try:
                data = self._collect_current_plugin_data()
                if data:
                    self.load_from_data_tab(data)
                    self._draw_framework_point_map(data)
                    self._draw_framework_variogram_preview(data, use_state=False)
                    return
            except Exception:
                pass
        self.refresh_from_state()

    def _collect_current_plugin_data(self) -> Optional[Dict[str, Any]]:
        dlg = self.plugin.dlg
        points_widget = getattr(dlg, "Points", None) or getattr(dlg, "cmbPointsLayer", None)
        variable_widget = getattr(dlg, "Points_2", None) or getattr(dlg, "cmbVariable", None)
        poly_widget = getattr(dlg, "poly", None) or getattr(dlg, "cmbPolygonLayer", None)
        pixel_widget = getattr(dlg, "spinPixelSize", None)

        layer_name = points_widget.currentText().strip() if points_widget is not None else ""
        variable_name = variable_widget.currentText().strip() if variable_widget is not None else ""
        polygon_name = poly_widget.currentText().strip() if poly_widget is not None else ""
        pixel_size = float(pixel_widget.value()) if pixel_widget is not None and hasattr(pixel_widget, "value") else None

        if not layer_name or not variable_name:
            return None

        layers = QgsProject.instance().mapLayersByName(layer_name)
        if not layers:
            return None
        point_layer = layers[0]

        xs, ys, zs = [], [], []
        for feat in point_layer.getFeatures():
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue
            try:
                pt = geom.asPoint()
                val = float(feat[variable_name])
            except Exception:
                continue
            if np.isfinite(val):
                xs.append(float(pt.x()))
                ys.append(float(pt.y()))
                zs.append(val)

        if len(zs) == 0:
            return None

        moran_i = None
        moran_p = None
        pattern = "Not evaluated"
        try:
            if hasattr(self.plugin, "_compute_moran_index_knn"):
                pts = []
                class _P:
                    def __init__(self, x, y):
                        self._x = x; self._y = y
                    def x(self): return self._x
                    def y(self): return self._y
                pts = [_P(x, y) for x, y in zip(xs, ys)]
                mor = self.plugin._compute_moran_index_knn(pts, zs, k=8, n_permutations=199)
                if mor is not None:
                    moran_i = mor.get("I")
                    moran_p = mor.get("p")
                    pattern = mor.get("pattern", pattern)
        except Exception:
            pass

        polygon_layer = None
        if polygon_name:
            polys = QgsProject.instance().mapLayersByName(polygon_name)
            polygon_layer = polys[0] if polys else None

        return {
            "variable_name": variable_name,
            "pixel_size": pixel_size,
            "sample_count": len(zs),
            "moran_i": moran_i,
            "moran_p_value": moran_p,
            "spatial_pattern": pattern,
            "x": np.asarray(xs, dtype=float),
            "y": np.asarray(ys, dtype=float),
            "z": np.asarray(zs, dtype=float),
            "point_layer": point_layer,
            "polygon_layer": polygon_layer,
        }

    def _draw_framework_point_map(self, data: Dict[str, Any]) -> None:
        if getattr(self, "point_map_fig", None) is None:
            return
        self.point_map_fig.clear()
        ax = self.point_map_fig.add_subplot(111)
        x = np.asarray(data.get("x", []), dtype=float)
        y = np.asarray(data.get("y", []), dtype=float)
        z = np.asarray(data.get("z", []), dtype=float)
        if x.size == 0 or y.size == 0:
            self.point_map_canvas.draw_idle()
            return

        poly_layer = data.get("polygon_layer")
        if poly_layer is not None:
            for feat in poly_layer.getFeatures():
                geom = feat.geometry()
                if geom is None or geom.isEmpty():
                    continue
                try:
                    if geom.isMultipart():
                        polygons = geom.asMultiPolygon()
                    else:
                        polygons = [geom.asPolygon()]
                    for poly in polygons:
                        for ring in poly:
                            xs = [pt.x() for pt in ring]
                            ys = [pt.y() for pt in ring]
                            ax.plot(xs, ys, color="black", linewidth=0.8)
                except Exception:
                    pass

        sc = ax.scatter(x, y, c=z, cmap="viridis", s=16, edgecolors="k", linewidths=0.25)
        try:
            cbar = self.point_map_fig.colorbar(sc, ax=ax, orientation="vertical", fraction=0.045, pad=0.02)
            cbar.ax.tick_params(labelsize=6)
            cbar.set_label(data.get("variable_name", ""), fontsize=7)
        except Exception:
            pass
        ax.set_title("Point map", fontsize=8)
        ax.set_aspect("equal", adjustable="box")
        ax.margins(0.05)
        ax.tick_params(axis='both', labelsize=6)
        ax.grid(True, linestyle='--', linewidth=0.4, alpha=0.4)
        self.point_map_fig.tight_layout(pad=0.7)
        self.point_map_canvas.draw_idle()

    def _draw_framework_variogram_preview(self, data: Dict[str, Any], use_state: bool = False) -> None:
        if getattr(self, "variogram_fig", None) is None:
            return
        self.variogram_fig.clear()
        ax = self.variogram_fig.add_subplot(111)

        x = np.asarray(data.get("x", []), dtype=float)
        y = np.asarray(data.get("y", []), dtype=float)
        z = np.asarray(data.get("z", []), dtype=float)
        if z.size < 5:
            self.variogram_canvas.draw_idle()
            return

        model_name = "Spherical"
        nugget = psill = rng = None
        fit_method = "MoM"
        lags_plot = None
        gamma_plot = None

        dmax = float(np.nanmax(self._pairwise_distances(x, y))) if z.size > 1 else 1.0
        cutoff = 0.5 * dmax
        lagw = self._safe_lag_width(x, y, cutoff, self._nearest_neighbor_dist(x, y))
        lags, gamma = self._bin_variogram(x, y, z, cutoff, lagw)

        persisted = self._persisted_variogram_state() if use_state else None
        if persisted is not None:
            model_name = persisted["model"]
            nugget = persisted["nugget"]
            psill = persisted["psill"]
            rng = persisted["range"]
            fit_method = persisted["fit_method"]
            cutoff = persisted.get("max_distance") or cutoff
            lagw = persisted.get("lag_width") or lagw
            lagw = self._safe_lag_width(x, y, cutoff, lagw)
            lags_plot = persisted.get("lags")
            gamma_plot = persisted.get("gamma")
        else:
            if z.size < self.REML_SAMPLE_LIMIT and self._has_reml():
                fit_method = "REML"
                nugget, psill, rng = self._fit_reml_from_mom_seed(x, y, z, lags, gamma, cutoff, model_name)
            elif lags.size > 0:
                fit_method = "MoM"
                nugget, psill, rng = self._guess_initial_params(
                    lags,
                    gamma,
                    cutoff,
                    model=self._normalize_model_token(model_name),
                )
                lags_plot = lags
                gamma_plot = gamma
            else:
                fit_method = "MoM"
                nugget, psill, rng = 0.0, max(float(np.var(z, ddof=1)), 1e-9), max(cutoff * 0.5, 1e-9)

        if fit_method != "REML" and lags_plot is not None and getattr(lags_plot, "size", 0) > 0:
            ax.plot(lags_plot, gamma_plot, 'o', color="#2f0dee", markersize=4, label="Experimental")

        xmax = max(
            float(cutoff) if cutoff is not None else 1.0,
            float(np.nanmax(lags_plot)) if lags_plot is not None and getattr(lags_plot, "size", 0) > 0 else 1.0,
            float(rng) if rng is not None else 1.0,
        )
        h_line = np.linspace(0.0, xmax, 200)
        th = self._model_func(h_line, self._normalize_model_token(model_name), float(nugget), float(psill), float(rng))
        ax.plot(h_line, th, '-', color='black', linewidth=1.8, label=f"Theoretical ({fit_method})")

        ax.set_title("Semivariogram preview", fontsize=9)
        ax.set_xlabel("Lag distance (h)", fontsize=8)
        ax.set_ylabel("Semivariance Î³(h)", fontsize=8)
        ax.tick_params(axis='both', labelsize=7)
        ax.grid(True, linestyle='--', linewidth=0.4, alpha=0.5)
        ax.legend(fontsize=7, frameon=False, loc='best')
        ax.set_xlim(left=0.0, right=xmax)
        ax.set_ylim(bottom=0.0)
        self.variogram_fig.tight_layout(pad=0.7)
        self.variogram_canvas.draw_idle()

        sdi_value = float(psill) / max(float(nugget) + float(psill), 1e-12) * 100.0
        sdi_class = self._classify_sdi(sdi_value)
        self.load_sdi_result({
            "sdi_value": sdi_value,
            "sdi_status": sdi_class,
            "sdi_class": sdi_class,
            "fit_method": fit_method,
            "variogram_model": model_name,
            "nugget": float(nugget),
            "psill": float(psill),
            "range": float(rng),
            "max_distance": float(cutoff),
            "lag_width": float(lagw),
            "experimental_distances": lags_plot.tolist() if fit_method != "REML" and lags_plot is not None and hasattr(lags_plot, "tolist") else [],
            "experimental_semivariances": gamma_plot.tolist() if fit_method != "REML" and gamma_plot is not None and hasattr(gamma_plot, "tolist") else [],
        })

    @staticmethod
    def _has_reml() -> bool:
        return bool(_HAS_REML and fit_ok_reml_interface is not None)

    def _resolve_ok_fit_method(self, sample_count: int) -> str:
        if self._has_reml() and int(sample_count or 0) < self.REML_SAMPLE_LIMIT:
            return "REML"
        return "MoM"

    def _persisted_variogram_state(self) -> Optional[Dict[str, Any]]:
        state = getattr(self, "state", None)
        if state is None:
            return None
        d = state.__dict__
        try:
            nugget = float(d.get("nugget"))
            psill = float(d.get("psill"))
            rng = float(d.get("range"))
        except Exception:
            return None
        if not all(np.isfinite(v) for v in (nugget, psill, rng)):
            return None
        if rng <= 0 or psill <= 0 or (nugget + psill) <= 0:
            return None
        lags = np.asarray(d.get("experimental_distances", []), dtype=float)
        gamma = np.asarray(d.get("experimental_semivariances", []), dtype=float)
        return {
            "model": str(d.get("variogram_model") or "Spherical"),
            "nugget": nugget,
            "psill": psill,
            "range": rng,
            "fit_method": str(d.get("fit_method") or "MoM"),
            "max_distance": self._safe_float(d.get("max_distance")),
            "lag_width": self._safe_float(d.get("lag_width")),
            "lags": lags if lags.size else None,
            "gamma": gamma if gamma.size else None,
        }

    def _fit_reml_from_mom_seed(self, x, y, z, lags, gamma, cutoff, model_name):
        if lags.size > 0:
            nugget0, psill0, rng0 = self._guess_initial_params(
                lags,
                gamma,
                cutoff,
                model=self._normalize_model_token(model_name),
            )
        else:
            nugget0, psill0, rng0 = 0.0, float(np.var(z, ddof=1) if z.size > 1 else 1.0), max(cutoff * 0.5, 1.0)
        try:
            result = fit_ok_reml_interface(
                sample_xyz=np.column_stack([x, y, z]),
                model=self._ok_model_token_for_reml(model_name),
                init_from_mom={"nugget": nugget0, "psill": psill0, "range": rng0},
                random_state=123,
            )
            nugget = float(result.get("nugget", nugget0))
            psill = float(result.get("psill", psill0))
            rng = float(result.get("range", rng0))
            if all(np.isfinite(v) for v in (nugget, psill, rng)):
                return nugget, psill, rng
        except Exception:
            pass
        return nugget0, psill0, rng0

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
            mi = float(np.min(dist))
            if mi < dmin:
                dmin = mi
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

    @staticmethod
    def _semivariances(z):
        def gamma(i_val, j_vals):
            diff = i_val - j_vals
            return 0.5 * (diff * diff)
        return gamma

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
        gamma_of = self._semivariances(z)
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
            gj = gamma_of(zi, zj[mask])
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

    def _guess_initial_params(self, lags, gamma, cutoff, model="exponential"):
        """Estimate transparent MoM initial parameters for the Framework fit."""
        lags = np.asarray(lags, dtype=float)
        gamma = np.asarray(gamma, dtype=float)
        keep = np.isfinite(lags) & np.isfinite(gamma) & (lags > 0)
        lags = lags[keep]
        gamma = gamma[keep]

        if lags.size == 0:
            return 0.0, 1.0, max(1.0, cutoff * 0.4)

        order = np.argsort(lags)
        lags = lags[order]
        gamma = gamma[order]

        first_vals = gamma[:max(1, min(3, gamma.size))]
        tail_vals = gamma[-max(3, max(1, gamma.size // 3)):]

        first_bin = float(first_vals[0]) if first_vals.size else 0.0
        first_max = float(np.nanmax(first_vals)) if first_vals.size else first_bin
        nugget_intercept = first_bin
        if lags.size >= 2:
            h1, h2 = float(lags[0]), float(lags[1])
            g1, g2 = float(gamma[0]), float(gamma[1])
            if abs(h2 - h1) > 1e-12:
                slope = (g2 - g1) / (h2 - h1)
                nugget_intercept = float(g1 - slope * h1)

        nugget_floor = 0.75 * first_bin
        nugget_seed = float(max(0.0, max(max(0.0, nugget_intercept), nugget_floor, first_bin)))
        plateau_seed = float(np.nanmedian(tail_vals))
        max_seed = float(np.nanmax(gamma))
        sill_total_seed = max(plateau_seed, max_seed, first_max, nugget_seed + 1e-6)

        target = 0.90 * sill_total_seed
        idx = np.where(gamma >= target)[0]
        range_seed = float(lags[idx[0]]) if idx.size > 0 else float(0.60 * cutoff)
        range_seed = max(range_seed, float(np.nanmin(lags)), 1e-9)

        nugget_cap = max(0.0, min(first_max, 0.90 * sill_total_seed))
        nugget_seed = float(np.clip(nugget_seed, 0.0, nugget_cap)) if nugget_cap > 0 else 0.0
        # Keep the MoM nugget tied to the first empirical structure. Let the
        # search refine range/partial sill only; otherwise the least-squares
        # search can force an unrealistically low nugget for flat variograms.
        nugget_candidates = np.array([nugget_seed], dtype=float)

        lag_min = max(float(np.nanmin(lags)), 1e-9)
        lag_max = max(float(np.nanmax(lags)), lag_min)
        low = max(lag_min, 0.20 * range_seed)
        high = max(low * 1.05, min(float(cutoff), max(lag_max * 1.15, range_seed * 1.8, low)))
        range_candidates = np.unique(np.concatenate([
            np.linspace(low, high, 28),
            np.array([range_seed, 0.5 * cutoff, 0.75 * cutoff, lag_max], dtype=float),
        ]))
        range_candidates = range_candidates[np.isfinite(range_candidates) & (range_candidates > 0)]

        lag_scale = max(float(np.nanmedian(lags)), 1e-9)
        weights = 1.0 / (1.0 + (lags / lag_scale))
        best = None
        model_token = self._normalize_model_token(model)

        for nugget in nugget_candidates:
            y = gamma - float(nugget)
            for rng in range_candidates:
                basis = self._model_func(lags, model_token, 0.0, 1.0, float(rng))
                denom = float(np.sum(weights * basis * basis))
                if denom <= 0:
                    continue
                psill = float(np.sum(weights * basis * y) / denom)
                psill = max(psill, 1e-9)
                pred = float(nugget) + psill * basis
                sse = float(np.sum(weights * (gamma - pred) ** 2))
                sse += 1e-6 * (float(rng) / max(float(cutoff), 1e-9)) ** 2
                if best is None or sse < best[0]:
                    best = (sse, float(nugget), float(psill), float(rng))

        if best is None:
            return nugget_seed, max(sill_total_seed - nugget_seed, 1e-6), range_seed

        _, nugget, psill, rng = best
        return nugget, psill, rng

    @staticmethod
    def _normalize_model_token(model_text: str) -> str:
        m = str(model_text).strip().lower()
        if m.startswith('sph') or m.startswith('spher'):
            return 'spherical'
        if m.startswith('exp'):
            return 'exponential'
        if m.startswith('gau'):
            return 'gaussian'
        return 'exponential'

    def _model_func(self, h, model, nugget, psill, rng):
        """Use the same theoretical variogram equations as the geostatistics tab."""
        h = np.asarray(h, dtype=float)
        c0 = float(nugget)
        c = float(psill)
        a = max(float(rng), 1e-9)
        model = self._normalize_model_token(model)
        if model == 'spherical':
            hr = np.clip(h / a, 0.0, 1.0)
            sph = c * (1.5 * hr - 0.5 * (hr ** 3))
            return np.where(h <= a, c0 + sph, c0 + c)
        elif model == 'gaussian':
            return c0 + c * (1.0 - np.exp(-(h * h) / (a * a)))
        else:
            return c0 + c * (1.0 - np.exp(-h / a))

    # ------------------------------------------------------------------
    # Public integration methods
    # ------------------------------------------------------------------
    def load_from_data_tab(self, data: Dict[str, Any]) -> None:
        """Load diagnostics values coming from the existing Data tab.

        Expected keys are flexible to ease integration. Missing keys are simply
        ignored.
        """

        self.state.variable_name = str(data.get("variable_name", self.state.variable_name) or "")
        self.state.pixel_size = self._safe_float(data.get("pixel_size", self.state.pixel_size))
        self.state.sample_count = self._safe_int(data.get("sample_count", self.state.sample_count))
        self.state.moran_i = self._safe_float(data.get("moran_i", self.state.moran_i))
        self.state.moran_p_value = self._safe_float(data.get("moran_p_value", self.state.moran_p_value))
        self.state.spatial_pattern = str(data.get("spatial_pattern", self.state.spatial_pattern) or self.state.spatial_pattern)
        self.refresh_from_state()

    def load_sdi_result(self, sdi_data: Dict[str, Any]) -> None:
        """Load SDI result after the semivariogram popup is executed."""

        self.state.sdi_value = self._safe_float(sdi_data.get("sdi_value", self.state.sdi_value))
        self.state.sdi_status = str(sdi_data.get("sdi_status", sdi_data.get("sdi_class", "Not calculated")))

        # Store extra semivariogram details when available so the Framework tab
        # and the future PDF report can reuse them later.
        self.state.__dict__["sdi_class"] = sdi_data.get("sdi_class", self.state.__dict__.get("sdi_class", ""))
        self.state.__dict__["variogram_model"] = sdi_data.get("variogram_model", self.state.__dict__.get("variogram_model", ""))
        self.state.__dict__["nugget"] = sdi_data.get("nugget", self.state.__dict__.get("nugget"))
        self.state.__dict__["psill"] = sdi_data.get("psill", self.state.__dict__.get("psill"))
        self.state.__dict__["range"] = sdi_data.get("range", self.state.__dict__.get("range"))
        self.state.__dict__["fit_method"] = sdi_data.get("fit_method", self.state.__dict__.get("fit_method", "MoM"))
        self.state.__dict__["lag_count"] = sdi_data.get("lag_count", self.state.__dict__.get("lag_count"))
        self.state.__dict__["max_distance"] = sdi_data.get("max_distance", self.state.__dict__.get("max_distance"))
        self.state.__dict__["lag_width"] = sdi_data.get("lag_width", self.state.__dict__.get("lag_width"))
        self.state.__dict__["experimental_distances"] = sdi_data.get("experimental_distances", self.state.__dict__.get("experimental_distances", []))
        self.state.__dict__["experimental_semivariances"] = sdi_data.get("experimental_semivariances", self.state.__dict__.get("experimental_semivariances", []))
        self.refresh_from_state()

    def request_refresh_from_plugin(self) -> None:
        """Ask the main plugin to refresh Framework values from the Data tab."""
        if self.plugin is None:
            return
        try:
            self.plugin._sync_framework_from_current_data()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # UI refresh
    # ------------------------------------------------------------------
    def refresh_from_state(self) -> None:
        """Push the internal state values to the UI."""

        self._set_text(self.txt_variable, self.state.variable_name)
        self._set_text(self.txt_pixel, self._fmt(self.state.pixel_size))
        self._set_text(self.txt_samples, self._fmt(self.state.sample_count))
        self._set_text(self.txt_moran, self._fmt(self.state.moran_i))
        self._set_text(self.txt_pvalue, self._fmt(self.state.moran_p_value))
        self._set_text(self.txt_pattern, self.state.spatial_pattern)
        self._set_text(self.txt_sdi, self._fmt(self.state.sdi_value))
        self._set_text(self.txt_sdi_status, self.state.sdi_status)

        self._set_text(self.txt_summary_mode, self.state.framework_mode)
        selected_method = self.state.__dict__.get("selected_method") or self.state.selected_winner
        self._set_text(self.txt_summary_winner, selected_method or "Pending")
        self._set_plain_text(
            self.txt_summary_diagnostics,
            self._build_diagnostics_summary(),
        )
        self._set_plain_text(
            self.txt_summary_methods,
            self._build_methods_summary(),
        )
        self._set_plain_text(self.txt_decision_summary, self.state.decision_summary)

        if self.lbl_eligibility_preview:
            preview = ", ".join(self.state.suggested_methods) if self.state.suggested_methods else "No methods evaluated yet."
            self.lbl_eligibility_preview.setText(preview)

        self._update_framework_decision_tree()
        self._refresh_covariate_list()
        self._refresh_validation_method_combo()
        self._refresh_final_method_combo()
        self._refresh_method_checkboxes()
        self._sync_validation_method_controls_visibility()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def on_calculate_sdi_clicked(self) -> None:
        """Open the standalone SDI popup used by the Framework overview."""
        if FrameworkSDIDialog is None:
            self._show_warning(
                "Framework SDI",
                "The SDI dialog module is not available. Make sure framework_sdi_dialog.py is in the plugin folder."
            )
            return

        dlg = FrameworkSDIDialog(parent=self.dlg, plugin=self.plugin)
        try:
            dlg.exec_()
        except AttributeError:
            dlg.exec()

    def on_open_sdi_window_clicked(self) -> None:
        """Alias placeholder for a dedicated semivariogram settings popup."""
        self.on_calculate_sdi_clicked()

    def on_info_clicked(self) -> None:
        """Show article/framework information in a popup."""
        article_html = (
            f"<p><b>{html.escape(ARTICLE_TITLE)}</b></p>"
            f"<p>{html.escape(ARTICLE_AUTHORS)}</p>"
            "<p><b>Purpose</b></p>"
            "<p>The selection of interpolation methods in digital soil mapping lacks a systematic approach, "
            "reducing map accuracy. This study aimed to evaluate whether data characteristics, such as "
            "sample size and spatial structure, influence the selection and performance of interpolation methods.</p>"
            "<p><b>Citation</b></p>"
            f"<p>{html.escape(ARTICLE_CITATION)}</p>"
            "<p><b>Article link</b><br>"
            f'<a href="{ARTICLE_LINK_URL}">{ARTICLE_LINK_URL}</a></p>'
        )
        self._show_rich_info("Framework information", article_html)

    def on_framework_mode_changed(self, checked: Optional[bool] = None) -> None:
        """Switch between univariate and full framework modes."""

        sender = self.sender()
        should_open_covariates = bool(sender is self.rad_full and checked)
        self.state.framework_mode = "Full" if self.rad_full and self.rad_full.isChecked() else "Univariate"
        self._update_covariates_tab_state()
        self._update_view_covariates_button_state()
        self._show_framework_mode_image()
        self._update_decision_summary()
        self.refresh_from_state()
        if self.state.framework_mode == "Full" and should_open_covariates:
            self._open_framework_covariates_dialog()

    def on_evaluate_methods_clicked(self) -> None:
        """Compute eligible methods from the univariate/full framework diagrams."""

        n = self.state.sample_count or 0
        clustered = self._has_spatial_structure()
        sdi = float(self.state.sdi_value) if self.state.sdi_value is not None else None
        mode = self.state.framework_mode
        sdi_val = -1.0 if sdi is None else sdi
        ok_fit = "MoM" if n >= 100 else "REML"
        full_ready = bool(self.state.covariates)

        if mode == "Full" and full_ready:
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

        if mode == "Full" and not full_ready:
            path += " Full framework selected, but no covariates have been applied yet; using univariate path."

        eligible = ["TPS", "IDW", "OK", "SVM", "RFE", "RK"] if mode == "Full" and full_ready else ["TPS", "IDW", "OK"]
        suggested = [m for m in recommended if m in eligible]
        self.state.__dict__["ok_fit_method"] = ok_fit
        self.state.__dict__["decision_path"] = path

        self.state.eligible_methods = eligible
        self.state.suggested_methods = suggested
        self._update_decision_summary()
        self.refresh_from_state()
        self._refresh_method_checkboxes(apply_recommended=True)

    def on_go_to_validation_clicked(self) -> None:
        """The validation navigation button is intentionally hidden."""
        return

    def on_load_covariates_clicked(self) -> None:
        """Load covariate files from disk."""

        files, _ = QFileDialog.getOpenFileNames(
            self.dlg,
            "Select covariate rasters",
            "",
            "Raster files (*.tif *.tiff *.img *.vrt);;All files (*)",
        )
        if not files:
            return

        for path in files:
            if path not in self.state.covariates:
                self.state.covariates.append(path)
        self.refresh_from_state()

    def on_reuse_covariates_clicked(self) -> None:
        """Import covariates from the Machine Learning tab state."""
        self._sync_covariates_from_ml()
        self.refresh_from_state()

    def on_remove_covariate_clicked(self) -> None:
        """Remove the selected covariate from the list."""
        if not self.list_covariates:
            return
        row = self.list_covariates.currentRow()
        if row < 0 or row >= len(self.state.covariates):
            return
        self.state.covariates.pop(row)
        self.refresh_from_state()

    def on_clear_covariates_clicked(self) -> None:
        """Clear all loaded covariates."""
        self.state.covariates.clear()
        self.refresh_from_state()

    def on_compute_correlation_clicked(self) -> None:
        """Reuse the Machine Learning correlation workflow when available."""
        ml_ctrl = getattr(self.plugin, "ml_ctrl", None) if self.plugin is not None else None
        if ml_ctrl is not None and hasattr(ml_ctrl, "_on_compute_correlations_clicked"):
            ml_ctrl._on_compute_correlations_clicked()
            self._sync_covariates_from_ml()
            return
        self._show_warning("Correlation", "Machine Learning correlation workflow is not available.")

    def on_select_suggested_clicked(self) -> None:
        """Tick only the currently suggested methods."""
        for method, widget_name in self.METHOD_CHECKBOXES.items():
            checkbox = self._get(widget_name)
            if checkbox:
                checkbox.setChecked(method in self.state.suggested_methods)

    def on_run_validation_clicked(self) -> None:
        """Build the Framework validation table and plots."""

        selected_methods = self._selected_methods_from_checkboxes()
        if not selected_methods:
            self._show_warning("Validation", "Select at least one method before running validation.")
            return

        data = self._collect_current_plugin_data() or {}
        obs = np.asarray(data.get("z", []), dtype=float)
        if obs.size == 0:
            obs = np.linspace(1.0, 10.0, 10)
        n_effective = self._effective_valid_sample_count(data)
        if n_effective < 10:
            self._show_warning(
                "Validation",
                "At least 10 valid samples are required for Framework validation. "
                f"The current dataset has {n_effective} valid samples.",
            )
            return

        results: List[Dict[str, Any]] = []
        failures: List[str] = []
        small_sample_warnings: List[str] = []
        for method in selected_methods:
            min_required = self._minimum_samples_for_method(method)
            if n_effective < min_required:
                failures.append(
                    f"{method}: requires at least {min_required} valid samples; current dataset has {n_effective}."
                )
                continue
            if self._should_warn_small_sample_method(method, n_effective):
                small_sample_warnings.append(
                    f"{method}: {n_effective} samples is below the recommended 30-sample threshold, "
                    "but the method will still be executed."
                )
            try:
                row = self._run_framework_validation_method(method, data)
            except Exception as exc:
                row = None
                failures.append(f"{method}: {self._friendly_interpolation_error(exc)}")
            if row is None:
                failures.append(f"{method}: validation is not available with the current inputs.")
                continue
            results.append(row)

        if not results:
            message = "No validation result was produced."
            if failures:
                message += "\n\n" + "\n".join(failures[:6])
            self._show_warning("Validation", message)
            return

        results.sort(key=lambda x: (-(float(x["lccc"]) if x["lccc"] != "" else -np.inf), x["rmse"]))
        for rank, row in enumerate(results, start=1):
            row["rank"] = rank

        self.state.validation_results = results
        self.state.validated_methods = [r["method"] for r in results]
        self.state.selected_winner = results[0]["method"] if results else ""
        self.state.__dict__["validation_plot_method"] = self.state.validated_methods[0] if self.state.validated_methods else ""
        self._populate_validation_table(results)
        self._refresh_observed_plot_controls_from_results()
        self._refresh_validation_method_combo()
        if self.chk_use_best and self.chk_use_best.isChecked():
            self.state.__dict__["selected_method"] = self.state.selected_winner
        self._draw_validation_plot()

        if self.lbl_validation_summary:
            self.lbl_validation_summary.setText(
                f"Winner: {self.state.selected_winner} | Methods validated: {len(results)}"
            )
        if failures:
            self._show_warning("Validation", "Some selected methods could not be validated:\n" + "\n".join(failures[:6]))
        if small_sample_warnings:
            self._show_warning(
                "Small sample warning",
                "The following methods were run with fewer than 30 valid samples. "
                "Interpret validation results with caution:\n" + "\n".join(small_sample_warnings[:6]),
            )

        self.refresh_from_state()

    def _effective_valid_sample_count(self, data: Dict[str, Any]) -> int:
        """Return the number of finite sample rows available for validation."""
        try:
            x = np.asarray(data.get("x", []), dtype=float)
            y = np.asarray(data.get("y", []), dtype=float)
            z = np.asarray(data.get("z", []), dtype=float)
            mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
            return int(np.count_nonzero(mask))
        except Exception:
            return 0

    def _dedupe_training_by_xy_keep_first(self, x, y, z):
        """Return one TPS training sample per exact XY coordinate, keeping the first row."""
        x = np.asarray(x, dtype=float).ravel()
        y = np.asarray(y, dtype=float).ravel()
        z = np.asarray(z, dtype=float).ravel()
        if x.size != y.size or x.size != z.size or z.size <= 1:
            return x, y, z, 0, 0

        xy = np.column_stack([x, y])
        _, first_idx, counts = np.unique(xy, axis=0, return_index=True, return_counts=True)
        duplicate_groups = int(np.count_nonzero(counts > 1))
        duplicate_rows = int(np.sum(counts - 1))
        if duplicate_rows <= 0:
            return x, y, z, 0, 0

        keep = np.sort(first_idx)
        return x[keep], y[keep], z[keep], duplicate_rows, duplicate_groups

    def _confirm_tps_duplicate_handling(self, duplicate_rows: int, duplicate_groups: int) -> bool:
        reply = QMessageBox.question(
            self.dlg,
            "TPS duplicate locations",
            (
                "TPS requires one sample per coordinate.\n\n"
                f"{duplicate_rows} repeated samples were found in "
                f"{duplicate_groups} duplicated locations.\n"
                "Continue using only the first sample at each repeated coordinate?\n\n"
                "The original layer will not be modified."
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        return reply == QMessageBox.Yes

    def _minimum_samples_for_method(self, method: str) -> int:
        """Return absolute sample minimums by method without blocking article-supported paths."""
        method = str(method or "").strip().upper()
        if method == "IDW":
            return 10
        if method == "TPS":
            return 10
        if method == "OK":
            return 30
        if method in {"RF", "RFE", "SVM", "RK"}:
            return 10
        return 10

    def _should_warn_small_sample_method(self, method: str, n_effective: int) -> bool:
        """Warn, but do not block, ML/hybrid methods below 30 samples."""
        method = str(method or "").strip().upper()
        return method in {"RF", "RFE", "SVM", "RK"} and int(n_effective) < 30

    def _friendly_interpolation_error(self, exc: Exception) -> str:
        """Hide raw NumPy/SciPy dimension errors behind a clearer message."""
        text = str(exc)
        if "dimension" in text.lower() or "shape" in text.lower() or "matmul" in text.lower():
            if format_shape_error is not None:
                return format_shape_error(exc)
            return "input coordinates were not correctly shaped."
        return text

    def on_use_best_method_toggled(self, checked: bool) -> None:
        """Disable manual method selection when automatic winner is used."""
        if self.cmb_final_method:
            self.cmb_final_method.setEnabled(not checked)
            if checked and self.state.selected_winner:
                idx = self.cmb_final_method.findText(self.state.selected_winner)
                if idx >= 0:
                    self.cmb_final_method.setCurrentIndex(idx)
                self.state.__dict__["selected_method"] = self.state.selected_winner
            elif not checked:
                self._refresh_final_method_combo()

    def on_final_method_changed(self, method_name: str) -> None:
        """Update the final selected method without changing the validation winner."""
        if self.chk_use_best and self.chk_use_best.isChecked():
            return
        self.state.__dict__["selected_method"] = method_name
        self.refresh_from_state()

    def on_run_interpolation_clicked(self) -> None:
        """Dispatch final Framework interpolation to the real plugin workflows."""
        use_best = bool(self.chk_use_best and self.chk_use_best.isChecked())
        method = self.state.selected_winner if use_best else ""
        if not method and self.cmb_final_method:
            method = self.cmb_final_method.currentText().strip()
        if not method:
            self._show_warning("Interpolation", "No interpolation method is available yet.")
            return
        self.state.__dict__["selected_method"] = method
        if not self._dispatch_interpolation_method(method):
            self._show_warning("Interpolation", f"Could not dispatch interpolation for method: {method}.")

    def on_preview_report_clicked(self) -> None:
        """Preview a lightweight HTML summary of the PDF report."""
        self._show_rich_info("Report preview", self._build_report_preview_html())

    def on_export_pdf_clicked(self) -> None:
        """Export the Framework validation report template to PDF."""
        path, _ = QFileDialog.getSaveFileName(
            self.dlg,
            "Export Framework report",
            "framework_validation_report.pdf",
            "PDF files (*.pdf);;All files (*)",
        )
        if not path:
            return
        if not str(path).lower().endswith(".pdf"):
            path = f"{path}.pdf"
        try:
            doc = QTextDocument()
            doc.setHtml(self._build_report_html())
            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(path)
            doc.print_(printer)
            self._show_info("Export PDF", f"Framework report template exported:\n{path}")
        except Exception as exc:
            self._show_warning("Export PDF", f"Could not export PDF:\n{exc}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _update_covariates_tab_state(self) -> None:
        """Enable covariate controls only in full framework mode."""
        enabled = self.state.framework_mode == "Full"
        for name in [
            "tabFrameworkCovariates",
            "groupFrameworkCovariates",
            "groupFrameworkCovariateOptions",
            "groupFrameworkCorrelationPlot",
            "groupFrameworkCovariateMaps",
        ]:
            widget = self._get(name)
            if widget:
                widget.setEnabled(enabled)
        self._hide_framework_covariates_tab()

    def _open_framework_covariates_dialog(self) -> None:
        """Open a modal covariates window mirroring the Machine Learning covariates tab."""
        if getattr(self, "_covariates_dialog_open", False):
            return
        self._sync_covariates_from_ml()
        self._covariates_dialog_open = True
        try:
            dlg = QDialog(self.dlg)
            dlg.setWindowTitle("Framework full - Covariates")
            dlg.resize(1050, 720)
            root = QVBoxLayout(dlg)

            top_group = QGroupBox("Covariate rasters")
            top = QHBoxLayout(top_group)
            top.addWidget(QLabel("Raster:"))
            cmb_raster = QComboBox()
            self._fill_raster_combo(cmb_raster)
            top.addWidget(cmb_raster, 1)
            btn_load = QPushButton("Load")
            top.addWidget(btn_load)
            top.addWidget(QLabel("Pixel size: (from Data)"))
            top.addWidget(QLabel(self._fmt(self.state.pixel_size)))
            root.addWidget(top_group)

            splitter = QSplitter(Qt.Horizontal)
            left = QWidget()
            left_layout = QVBoxLayout(left)
            group_pre = QGroupBox("Covariates  preprocessing")
            pre_layout = QVBoxLayout(group_pre)
            pre_layout.addWidget(QLabel("Loaded covariates:"))
            list_widget = QListWidget()
            pre_layout.addWidget(list_widget, 1)
            btn_remove = QPushButton("Remove selected")
            btn_clear = QPushButton("Clear")
            pre_layout.addWidget(btn_remove)
            pre_layout.addWidget(btn_clear)
            left_layout.addWidget(group_pre, 1)

            group_res = QGroupBox("Resampling")
            res_layout = QVBoxLayout(group_res)
            res_layout.addWidget(QLabel("Resample all covariate rasters to a common pixel size."))
            row_res = QHBoxLayout()
            row_res.addWidget(QLabel("Target pixel size:"))
            spin_pixel = QDoubleSpinBox()
            spin_pixel.setDecimals(4)
            spin_pixel.setRange(0.0001, 99999999.0)
            spin_pixel.setValue(float(self.state.pixel_size or 0.01))
            row_res.addWidget(spin_pixel)
            btn_resample = QPushButton("Resample covariates")
            row_res.addWidget(btn_resample)
            res_layout.addLayout(row_res)
            row_std = QHBoxLayout()
            row_std.addWidget(QLabel("Standardization:"))
            cmb_std = QComboBox()
            cmb_std.addItems(["Z-score", "Range [-1,1]"])
            row_std.addWidget(cmb_std)
            btn_std = QPushButton("Standardize covariates")
            row_std.addWidget(btn_std)
            res_layout.addLayout(row_std)
            btn_extract = QPushButton("Extract covariates to sample points")
            btn_view = QPushButton("View data with extractions ")
            btn_export = QPushButton("Export extractions CSV")
            res_layout.addWidget(btn_extract)
            res_layout.addWidget(btn_view)
            res_layout.addWidget(btn_export)
            left_layout.addWidget(group_res)

            right = QWidget()
            right_layout = QVBoxLayout(right)
            title = QLabel("Correlation Matrix")
            title.setAlignment(Qt.AlignCenter)
            right_layout.addWidget(title)
            frame_corr = QWidget()
            frame_corr.setMinimumSize(420, 360)
            right_layout.addWidget(frame_corr, 1)
            corr_fig = Figure(figsize=(5, 4))
            self.framework_corr_fig = corr_fig
            corr_canvas = FigureCanvas(corr_fig)
            corr_layout = QVBoxLayout(frame_corr)
            corr_layout.setContentsMargins(0, 0, 0, 0)
            corr_layout.addWidget(corr_canvas)
            self._install_canvas_menu(corr_canvas, lambda f=corr_fig: f, "framework_covariates_correlation", "Covariates correlation")
            corr_row = QHBoxLayout()
            btn_corr = QPushButton("Compute correlations")
            btn_export_corr = QPushButton("Export correlations CSV")
            corr_row.addStretch(1)
            corr_row.addWidget(btn_corr)
            corr_row.addWidget(btn_export_corr)
            corr_row.addStretch(1)
            right_layout.addLayout(corr_row)
            splitter.addWidget(left)
            splitter.addWidget(right)
            splitter.setStretchFactor(0, 1)
            splitter.setStretchFactor(1, 1)
            root.addWidget(splitter, 1)
            btn_apply_to_framework = QPushButton("Apply covariates to Framework")
            root.addWidget(btn_apply_to_framework)

            def _sync_dialog_list():
                self._sync_covariates_from_ml()
                list_widget.clear()
                for name in self.state.covariates:
                    list_widget.addItem(name)

            def _set_ml_combo_from_popup():
                ml_combo = getattr(self.plugin.dlg, "cmbMLRaster", None) if self.plugin is not None else None
                if ml_combo is None:
                    return
                data = cmb_raster.currentData()
                for i in range(ml_combo.count()):
                    if ml_combo.itemData(i) == data or ml_combo.itemText(i) == cmb_raster.currentText():
                        ml_combo.setCurrentIndex(i)
                        return

            def _call_ml(method_name):
                ml_ctrl = getattr(self.plugin, "ml_ctrl", None) if self.plugin is not None else None
                if ml_ctrl is not None and hasattr(ml_ctrl, method_name):
                    getattr(ml_ctrl, method_name)()
                    _sync_dialog_list()
                    if method_name == "_on_compute_correlations_clicked":
                        self._copy_source_figure_to_target(getattr(ml_ctrl, "_corr_fig", None), corr_fig, corr_canvas)
                else:
                    self._show_warning("Covariates", "Machine Learning covariates workflow is not available.")

            def _apply_to_framework():
                self._sync_covariates_from_ml()
                self._update_decision_summary()
                self.refresh_from_state()
                self._show_info("Framework covariates", f"{len(self.state.covariates)} covariate(s) are now available for Full Framework.")
                dlg.accept()

            def _load():
                _set_ml_combo_from_popup()
                _call_ml("_on_add_covariate")

            def _remove():
                ml_list = getattr(self.plugin.dlg, "listCovariates", None) if self.plugin is not None else None
                if ml_list is not None:
                    ml_list.clearSelection()
                    selected = [i.text() for i in list_widget.selectedItems()]
                    for i in range(ml_list.count()):
                        if ml_list.item(i).text() in selected:
                            ml_list.item(i).setSelected(True)
                _call_ml("_on_remove_selected_covariates")

            def _clear():
                _call_ml("_on_clear_covariates")

            def _resample():
                spin = getattr(self.plugin.dlg, "spinTargetPixelSize", None) if self.plugin is not None else None
                if spin is not None:
                    spin.setValue(float(spin_pixel.value()))
                _call_ml("_on_resample_covariates")

            def _standardize():
                combo = getattr(self.plugin.dlg, "cmbStandardizeMethod", None) if self.plugin is not None else None
                if combo is not None:
                    idx = combo.findText(cmb_std.currentText())
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
                _call_ml("_on_apply_standardization_clicked")

            btn_load.clicked.connect(_load)
            btn_remove.clicked.connect(_remove)
            btn_clear.clicked.connect(_clear)
            btn_resample.clicked.connect(_resample)
            btn_std.clicked.connect(_standardize)
            btn_extract.clicked.connect(lambda: _call_ml("_on_extract_covariates_clicked"))
            btn_view.clicked.connect(lambda: _call_ml("_on_show_extracted_table_clicked"))
            btn_export.clicked.connect(lambda: self._show_warning("Covariates", "Extraction CSV export is not connected in the Machine Learning workflow."))
            btn_corr.clicked.connect(lambda: _call_ml("_on_compute_correlations_clicked"))
            btn_export_corr.clicked.connect(lambda: _call_ml("_on_export_correlations_csv"))
            btn_apply_to_framework.clicked.connect(_apply_to_framework)
            _sync_dialog_list()
            self._copy_source_figure_to_target(getattr(getattr(self.plugin, "ml_ctrl", None), "_corr_fig", None), corr_fig, corr_canvas)
            dlg.exec_()
            self._sync_covariates_from_ml()
            self.refresh_from_state()
        finally:
            self._covariates_dialog_open = False

    def _fill_raster_combo(self, combo: QComboBox) -> None:
        combo.clear()
        try:
            for layer in QgsProject.instance().mapLayers().values():
                if isinstance(layer, QgsRasterLayer):
                    combo.addItem(layer.name(), layer.id())
        except Exception:
            pass

    def _sync_covariates_from_ml(self) -> None:
        ml_list = getattr(self.plugin.dlg, "listCovariates", None) if self.plugin is not None and getattr(self.plugin, "dlg", None) is not None else None
        if ml_list is None:
            return
        values = []
        for i in range(ml_list.count()):
            values.append(ml_list.item(i).text())
        self.state.covariates = values
        self._refresh_covariate_list()

    def _has_spatial_structure(self) -> bool:
        try:
            if self.state.moran_p_value is not None:
                return float(self.state.moran_p_value) < 0.05
        except Exception:
            pass
        txt = (self.state.spatial_pattern or "").strip().lower()
        return "cluster" in txt or "spatial" in txt

    def _update_decision_summary(self) -> None:
        """Create a concise decision summary for the Framework page."""
        n = self.state.sample_count
        pattern = self.state.spatial_pattern or "Not evaluated"
        sdi_text = self._fmt(self.state.sdi_value) if self.state.sdi_value is not None else "Not calculated"
        candidates = ", ".join(self.state.suggested_methods) if self.state.suggested_methods else "Pending"
        available = ", ".join(self.state.eligible_methods) if self.state.eligible_methods else "Pending"
        decision_path = self.state.__dict__.get("decision_path", "Run Evaluate methods to trace the framework path.")
        ok_fit = self.state.__dict__.get("ok_fit_method", "")
        if self.state.sample_count:
            ok_fit = "MoM" if int(self.state.sample_count) >= 100 else "REML"
            self.state.__dict__["ok_fit_method"] = ok_fit
        covariates = ", ".join(self.state.covariates) if self.state.covariates else "None"

        self.state.decision_summary = (
            f"Mode: {self.state.framework_mode}.\n"
            f"Samples: {self._fmt(n)}.\n"
            f"Spatial pattern: {pattern}.\n"
            f"SDI: {sdi_text}.\n"
            f"Decision path: {decision_path}\n"
            f"Candidate methods: {candidates}.\n"
            f"Available methods: {available}.\n"
            f"OK fit: {ok_fit or 'Not selected'}.\n"
            f"Covariates: {covariates}.\n"
            f"Next step: run LOOCV/LCCC validation for the selected methods."
        )

    def _build_diagnostics_summary(self) -> str:
        """Build the final diagnostics summary shown in the report area."""
        lines = [
            f"Variable: {self.state.variable_name or 'Pending'}",
            f"Pixel size: {self._fmt(self.state.pixel_size)}",
            f"Samples: {self._fmt(self.state.sample_count)}",
            f"Moran's I: {self._fmt(self.state.moran_i)}",
            f"p-value: {self._fmt(self.state.moran_p_value)}",
            f"Spatial pattern: {self.state.spatial_pattern}",
            f"SDI: {self._fmt(self.state.sdi_value)}",
            f"SDI status: {self.state.sdi_status}",
            f"Covariates: {', '.join(self.state.covariates) if self.state.covariates else 'None'}",
        ]
        return "\n".join(lines)

    def _build_methods_summary(self) -> str:
        """Build the final methods summary block."""
        available = ", ".join(self.state.eligible_methods) if self.state.eligible_methods else "Pending"
        recommended = ", ".join(self.state.suggested_methods) if self.state.suggested_methods else "Pending"
        selected = self.state.__dict__.get("selected_method") or self.state.selected_winner or "Pending"
        ok_fit = self.state.__dict__.get("ok_fit_method", "")
        if self.state.sample_count:
            ok_fit = "MoM" if int(self.state.sample_count) >= 100 else "REML"
        return (
            f"Recommended: {recommended}\n"
            f"Available: {available}\n"
            f"Winner: {self.state.selected_winner or 'Pending'}\n"
            f"Selected: {selected}\n"
            f"OK fit: {ok_fit or 'Pending'}"
        )

    def _build_pdf_preview_text(self) -> str:
        """Build a short textual preview of the future PDF report."""
        covariates = ", ".join(self.state.covariates[:5]) if self.state.covariates else "None"
        return (
            "Framework PDF report preview\n\n"
            f"Mode: {self.state.framework_mode}\n"
            f"Variable: {self.state.variable_name or 'Pending'}\n"
            f"Samples: {self._fmt(self.state.sample_count)}\n"
            f"Moran's I: {self._fmt(self.state.moran_i)}\n"
            f"SDI: {self._fmt(self.state.sdi_value)}\n"
            f"Winner: {self.state.selected_winner or 'Pending'}\n"
            f"Covariates: {covariates}"
        )

    def _build_report_preview_html(self) -> str:
        """Build a lightweight report preview without embedded figures."""
        esc = lambda v: html.escape(str(v if v not in (None, "") else "Pending"))
        selected = self.state.__dict__.get("selected_method") or self.state.selected_winner or "Pending"
        methods = ", ".join(self.state.validated_methods or self._selected_methods_from_checkboxes()) or "Pending"
        validation_table = self._validation_metrics_table_html()
        return (
            "<html><body style='font-family: Arial, sans-serif;'>"
            "<style>table { border-collapse: collapse; width: 100%; margin-top: 8px; } "
            "th, td { border: 1px solid #bbb; padding: 4px; font-size: 9pt; } "
            "th { background: #e8eef7; }</style>"
            "<h2>Framework Validation Report Preview</h2>"
            f"<p><b>Variable:</b> {esc(self.state.variable_name)}</p>"
            f"<p><b>Framework:</b> {esc(self.state.framework_mode)}</p>"
            f"<p><b>Samples:</b> {esc(self._fmt(self.state.sample_count))}</p>"
            f"<p><b>SDI:</b> {esc(self._fmt(self.state.sdi_value))} ({esc(self.state.sdi_status)})</p>"
            f"<p><b>Recommended methods:</b> {esc(', '.join(self.state.suggested_methods) or 'Pending')}</p>"
            f"<p><b>Methods evaluated:</b> {esc(methods)}</p>"
            f"<p><b>Validation winner:</b> {esc(self.state.selected_winner)}</p>"
            f"<p><b>Selected final method:</b> {esc(selected)}</p>"
            "<h3>Validation metrics</h3>"
            f"{validation_table}"
            "<p>The exported PDF will include the generated maps and validation plots.</p>"
            "</body></html>"
        )

    def _validation_metrics_table_html(self) -> str:
        """Build the validation metrics table used by both preview and final PDF."""
        esc = lambda v: html.escape(str(v if v not in (None, "") else "Pending"))
        rows = []
        for row in self.state.validation_results or []:
            rows.append(
                "<tr>"
                f"<td>{esc(row.get('rank'))}</td>"
                f"<td>{esc(row.get('method'))}</td>"
                f"<td>{esc(row.get('rmse'))}</td>"
                f"<td>{esc(row.get('rmse_pct'))}</td>"
                f"<td>{esc(row.get('mae'))}</td>"
                f"<td>{esc(row.get('r2'))}</td>"
                f"<td>{esc(row.get('r'))}</td>"
                f"<td>{esc(row.get('lccc'))}</td>"
                "</tr>"
            )
        body = "".join(rows) or "<tr><td colspan='8'>Validation metrics pending</td></tr>"
        return (
            "<table>"
            "<tr><th>Rank</th><th>Method</th><th>RMSE</th><th>RMSE%</th><th>MAE</th><th>R2</th><th>Pearson</th><th>LCCC</th></tr>"
            f"{body}"
            "</table>"
        )

    def _build_report_html(self) -> str:
        """Build the English Framework validation report template."""
        esc = lambda v: html.escape(str(v if v not in (None, "") else "Pending"))
        recommended = ", ".join(self.state.suggested_methods) if self.state.suggested_methods else "Pending"
        selected = ", ".join(self.state.validated_methods) if self.state.validated_methods else "Pending"
        final_selected = self.state.__dict__.get("selected_method") or self.state.selected_winner or "Pending"
        covariates = self.state.covariates or []
        covariate_items = "".join(f"<li>{esc(c)}</li>" for c in covariates) or "<li>None</li>"
        point_map_img = self._report_figure_block("Point map", getattr(self, "point_map_fig", None))
        semivariogram_img = self._report_figure_block("Semivariogram", getattr(self, "variogram_fig", None))
        decision_tree_img = self._report_decision_tree_block() if self._include_report_decision_tree() else ""
        lccc_img = self._report_figure_block("LCCC comparison", self._make_validation_bar_figure("lccc"))
        rmse_img = self._report_figure_block("RMSE comparison", self._make_validation_bar_figure("rmse"))
        obs_pred_imgs = "".join(
            self._report_figure_block(f"Observed vs Predicted - {row.get('method', '')}", self._make_observed_predicted_figure(row))
            for row in (self.state.validation_results or [])
        )
        interpolation_img = self._report_figure_block("Interpolation map", getattr(self, "interpolation_fig", None))
        correlation_img = self._report_figure_block("Covariate correlation plot", self._get_correlation_report_figure())
        covariate_map_imgs = ""
        validation_table = self._validation_metrics_table_html()
        idw_details = []
        for row in self.state.validation_results or []:
            if str(row.get("method", "")).upper() == "IDW" and row.get("parameters"):
                idw_details.append(str(row.get("parameters")))
        fit_method = self.state.__dict__.get("ok_fit_method") or self.state.__dict__.get("fit_method", "Pending")
        if self.state.sample_count:
            fit_method = "MoM" if int(self.state.sample_count) >= 100 else "REML"
        idw_block = ""
        if idw_details:
            idw_block = "<p><b>IDW optimization parameters:</b> " + esc("; ".join(idw_details)) + "</p>"
        semivariogram_params = (
            "<table class='semivariogram-params'>"
            "<tr><th>Semivariogram parameter</th><th>Value</th></tr>"
            f"<tr><td>Model</td><td>{esc(self.state.__dict__.get('variogram_model', 'Pending'))}</td></tr>"
            f"<tr><td>Nugget (Co)</td><td>{esc(self._fmt(self.state.__dict__.get('nugget')))}</td></tr>"
            f"<tr><td>Partial sill (C1)</td><td>{esc(self._fmt(self.state.__dict__.get('psill')))}</td></tr>"
            f"<tr><td>Range (a)</td><td>{esc(self._fmt(self.state.__dict__.get('range')))}</td></tr>"
            "</table>"
        )
        citation_html = esc(ARTICLE_CITATION)
        return f"""
        <html>
        <head>
        <style>
            body {{ font-family: Arial, sans-serif; color: #202020; }}
            h1 {{ font-size: 18pt; margin: 0 0 4px 0; }}
            h2 {{ font-size: 12pt; margin: 10px 0 5px 0; border-bottom: 1px solid #999; }}
            p {{ margin: 3px 0; line-height: 1.15; }}
            table {{ border-collapse: collapse; width: 100%; margin-top: 6px; }}
            th, td {{ border: 1px solid #bbb; padding: 3px; font-size: 8pt; }}
            th {{ background: #e8eef7; }}
            .placeholder {{ border: 1px dashed #777; padding: 16px; color: #555; margin: 8px 0; }}
            .figure-block {{ margin: 4px auto 8px auto; page-break-inside: avoid; text-align: center; width: 100%; }}
            .figure-caption {{ font-size: 8pt; font-weight: bold; margin: 2px 0 0 0; line-height: 1.05; color: #333; }}
            img.report-figure {{ width: 430px; height: auto; border: 1px solid #ccc; }}
            img.decision-tree-figure {{ width: 680px; height: auto; border: 1px solid #ccc; }}
            .semivariogram-params {{ margin-bottom: 18px; page-break-inside: avoid; }}
        </style>
        </head>
        <body>
            <h1>Framework Validation Report</h1>
            <p><b>Variable:</b> {esc(self.state.variable_name)} | <b>Framework type:</b> {esc(self.state.framework_mode)}</p>

            <h2>1. Study Data</h2>
            <table>
                <tr><th>Item</th><th>Value</th></tr>
                <tr><td>Pixel size</td><td>{esc(self._fmt(self.state.pixel_size))}</td></tr>
                <tr><td>Number of samples</td><td>{esc(self._fmt(self.state.sample_count))}</td></tr>
                <tr><td>Semivariogram calculation method</td><td>{esc(fit_method)}</td></tr>
                <tr><td>Moran's I</td><td>{esc(self._fmt(self.state.moran_i))}</td></tr>
                <tr><td>p-value</td><td>{esc(self._fmt(self.state.moran_p_value))}</td></tr>
                <tr><td>Spatial pattern</td><td>{esc(self.state.spatial_pattern)}</td></tr>
                <tr><td>SDI</td><td>{esc(self._fmt(self.state.sdi_value))}</td></tr>
                <tr><td>SDI class</td><td>{esc(self.state.sdi_status)}</td></tr>
            </table>
            {point_map_img}
            {semivariogram_img}
            {semivariogram_params}

            <h2>2. Framework Decision</h2>
            <p><b>Decision path:</b> {esc(self.state.__dict__.get("decision_path", "Pending"))}</p>
            <p><b>Recommended methods:</b> {esc(recommended)}</p>
            <p><b>Methods evaluated:</b> {esc(selected)}</p>
            <p><b>Validation winner:</b> {esc(self.state.selected_winner)}</p>
            <p><b>Selected final method:</b> {esc(final_selected)}</p>
            {decision_tree_img}

            <h2>3. Multivariate Framework</h2>
            <p><b>Covariates:</b></p>
            <ul>{covariate_items}</ul>
            {correlation_img}
            {covariate_map_imgs}

            <h2>4. Validation Results</h2>
            {lccc_img}
            {rmse_img}
            {obs_pred_imgs}
            {idw_block}
            {validation_table}

            <h2>5. Interpolation Output</h2>
            <p><b>Validation winner:</b> {esc(self.state.selected_winner)}</p>
            <p><b>Selected final method:</b> {esc(final_selected)}</p>
            {interpolation_img}

            <h2>Reference</h2>
            <p>{citation_html}</p>
        </body>
        </html>
        """

    def _dispatch_interpolation_method(self, method: str) -> bool:
        """Run the selected method through the existing plugin interpolation code."""
        if self.plugin is None:
            return False
        m = str(method or "").strip().upper()
        try:
            if m == "OK":
                ok_ctrl, active_ok, params = self._prepare_ok_from_framework_variogram()
                if active_ok is not None and hasattr(active_ok, "_on_interpolate_clicked"):
                    active_ok._on_interpolate_clicked()
                    self._copy_source_figure_to_framework_map(getattr(active_ok, "_krig_map_fig", None))
                    return True
                if hasattr(self.plugin, "run_ok_interpolation"):
                    self._push_ok_params_to_dialog(params)
                    self.plugin.run_ok_interpolation()
                    self._copy_source_figure_to_framework_map(getattr(self.plugin, "det_interp_fig", None))
                    return True
            if m == "TPS":
                if hasattr(self.plugin, "_on_option_toggled"):
                    self.plugin._on_option_toggled("tps", True)
                elif hasattr(self.plugin, "_current_mode"):
                    self.plugin._current_mode = getattr(self.plugin, "MODE_TPS", self.plugin._current_mode)
                self.plugin.run_interpolation()
                self._copy_source_figure_to_framework_map(getattr(self.plugin, "det_interp_fig", None))
                return True
            if m == "IDW":
                if hasattr(self.plugin, "_on_option_toggled"):
                    self.plugin._on_option_toggled("opt", True)
                elif hasattr(self.plugin, "_current_mode"):
                    self.plugin._current_mode = getattr(self.plugin, "MODE_IDW_OPT", self.plugin._current_mode)
                self.plugin.run_interpolation()
                self._copy_source_figure_to_framework_map(getattr(self.plugin, "det_interp_fig", None))
                return True
            if m in {"RFE", "RF"}:
                ml_ctrl = getattr(self.plugin, "ml_ctrl", None)
                if ml_ctrl is not None and hasattr(ml_ctrl, "_on_run_rf_interpolation"):
                    ml_ctrl._on_run_rf_interpolation()
                    self._copy_source_figure_to_framework_map(getattr(ml_ctrl, "_rf_map_fig", None))
                    return True
            if m == "SVM":
                ml_ctrl = getattr(self.plugin, "ml_ctrl", None)
                if ml_ctrl is not None and hasattr(ml_ctrl, "_on_run_svm_interpolation"):
                    ml_ctrl._on_run_svm_interpolation()
                    self._copy_source_figure_to_framework_map(getattr(ml_ctrl, "_svm_map_fig", None))
                    return True
            if m == "RK":
                rk_ctrl = getattr(self.plugin, "rk_ctrl", None)
                if rk_ctrl is not None and hasattr(rk_ctrl, "_run_rk_prediction"):
                    self._run_rk_interpolation_from_framework(rk_ctrl)
                    self._copy_source_figure_to_framework_map(getattr(rk_ctrl, "_map_fig", None))
                    return True
        except Exception as exc:
            self._show_warning("Interpolation", f"Interpolation failed:\n{self._friendly_interpolation_error(exc)}")
            return True
        return False

    def _framework_variogram_params_for_ok(self) -> Dict[str, Any]:
        """Return valid Framework variogram parameters for final OK interpolation."""
        persisted = self._persisted_variogram_state()
        if persisted is not None and not self._is_ok_model_auto(str(persisted.get("model") or "")):
            return persisted

        data = self._collect_current_plugin_data() or {}
        x = np.asarray(data.get("x", []), dtype=float)
        y = np.asarray(data.get("y", []), dtype=float)
        z = np.asarray(data.get("z", []), dtype=float)
        mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
        x, y, z = x[mask], y[mask], z[mask]
        if z.size < 5:
            raise ValueError("At least 5 valid points are required to fit the OK semivariogram.")

        model_name = str(self.state.__dict__.get("variogram_model") or "Automatic")
        if self._is_ok_model_auto(model_name):
            model_name = self._select_best_ok_variogram_model(x, y, z)
        dmax = float(np.nanmax(self._pairwise_distances(x, y))) if z.size > 1 else 1.0
        cutoff = float(self.state.__dict__.get("max_distance") or 0.5 * dmax)
        lagw = float(self.state.__dict__.get("lag_width") or self._nearest_neighbor_dist(x, y))
        lagw = self._safe_lag_width(x, y, cutoff, lagw)
        lags, gamma = self._bin_variogram(x, y, z, cutoff, lagw)
        if self._resolve_ok_fit_method(z.size) == "REML":
            fit_method = "REML"
            nugget, psill, rng = self._fit_reml_from_mom_seed(x, y, z, lags, gamma, cutoff, model_name)
            lags_store, gamma_store = [], []
        else:
            fit_method = "MoM"
            nugget, psill, rng = self._guess_initial_params(
                lags,
                gamma,
                cutoff,
                model=self._normalize_model_token(model_name),
            )
            lags_store = lags.tolist() if hasattr(lags, "tolist") else []
            gamma_store = gamma.tolist() if hasattr(gamma, "tolist") else []

        if rng <= 0 or psill <= 0 or not all(np.isfinite(v) for v in (nugget, psill, rng)):
            raise ValueError(
                f"Invalid OK variogram parameters from Framework: nugget={nugget}, psill={psill}, range={rng}."
            )

        sdi_value = float(psill) / max(float(nugget) + float(psill), 1e-12) * 100.0
        sdi_class = self._classify_sdi(sdi_value)
        params = {
            "model": model_name,
            "nugget": float(nugget),
            "psill": float(psill),
            "range": float(rng),
            "fit_method": fit_method,
            "max_distance": float(cutoff),
            "lag_width": float(lagw),
            "lags": np.asarray(lags_store, dtype=float) if lags_store else None,
            "gamma": np.asarray(gamma_store, dtype=float) if gamma_store else None,
        }
        self.state.sdi_value = sdi_value
        self.state.sdi_status = sdi_class
        self.state.__dict__.update({
            "sdi_class": sdi_class,
            "variogram_model": model_name,
            "nugget": params["nugget"],
            "psill": params["psill"],
            "range": params["range"],
            "fit_method": fit_method,
            "max_distance": params["max_distance"],
            "lag_width": params["lag_width"],
            "experimental_distances": lags_store,
            "experimental_semivariances": gamma_store,
        })
        return params

    def _model_token_for_ok_dialog(self, model_text: str) -> str:
        token = self._normalize_model_token(model_text)
        return {"spherical": "Sph", "exponential": "Exp", "gaussian": "Gau"}.get(token, "Sph")

    def _push_ok_params_to_dialog(self, params: Dict[str, Any]) -> None:
        """Write Framework variogram params into the OK UI before interpolation."""
        if self.plugin is None or getattr(self.plugin, "dlg", None) is None:
            return
        dlg = self.plugin.dlg
        model_short = self._model_token_for_ok_dialog(params.get("model", "Spherical"))
        combo = getattr(dlg, "cmbOKModel", None)
        if combo is not None and hasattr(combo, "findText"):
            idx = combo.findText(model_short)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        for widget_name, key in (
            ("spinOKNugget", "nugget"),
            ("spinOKPsill", "psill"),
            ("spinOKRange", "range"),
            ("spinOKCutoff", "max_distance"),
            ("spinOKLag", "lag_width"),
        ):
            widget = getattr(dlg, widget_name, None)
            value = params.get(key)
            if widget is not None and value is not None and hasattr(widget, "setValue"):
                try:
                    widget.setValue(float(value))
                except Exception:
                    pass

    def _prepare_ok_from_framework_variogram(self):
        """Initialize OK controller and inject the Framework semivariogram state."""
        params = self._framework_variogram_params_for_ok()
        if hasattr(self.plugin, "_update_ok_context"):
            self.plugin._update_ok_context()
        self._push_ok_params_to_dialog(params)
        ok_ctrl = getattr(self.plugin, "ok_ctrl", None)
        active_ok = getattr(ok_ctrl, "_active", None) or ok_ctrl
        if active_ok is not None:
            try:
                token = self._normalize_model_token(params.get("model", "Spherical"))
                if hasattr(active_ok, "_set_model_combo_by_token"):
                    active_ok._set_model_combo_by_token(token)
                active_ok._ok_fit_method = str(params.get("fit_method") or "MoM")
                active_ok._use_reml = str(params.get("fit_method") or "").upper() == "REML"
                active_ok._cutoff = float(params.get("max_distance") or 0.0)
                active_ok._lag_width = float(params.get("lag_width") or 0.0)
                active_ok._init_params = (
                    float(params["nugget"]),
                    float(params["psill"]),
                    float(params["range"]),
                )
                lags = params.get("lags")
                gamma = params.get("gamma")
                if lags is not None and gamma is not None and getattr(lags, "size", 0) and getattr(gamma, "size", 0):
                    if float(lags[0]) != 0.0:
                        lags = np.insert(lags, 0, 0.0)
                        gamma = np.insert(gamma, 0, 0.0)
                    active_ok._exp_lags = lags
                    active_ok._exp_gamma = gamma
            except Exception:
                pass
        return ok_ctrl, active_ok, params

    def _run_rk_interpolation_from_framework(self, rk_ctrl: Any) -> None:
        """Run Regression Kriging end-to-end from Framework, including RF and variogram stages."""
        progress = QProgressDialog("Running Regression Kriging from Framework...", "Cancel", 0, 100, self.dlg)
        progress.setWindowTitle("Regression Kriging")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        QCoreApplication.processEvents()

        def _progress(done, total, label=None):
            if label:
                progress.setLabelText(str(label))
            total = int(total) if total else 100
            progress.setRange(0, max(total, 1))
            progress.setValue(int(done))
            QCoreApplication.processEvents()
            if progress.wasCanceled():
                raise KeyboardInterrupt("Canceled by user")

        try:
            if getattr(rk_ctrl, "_rf_model", None) is None:
                progress.setLabelText("Fitting RF stage for Regression Kriging...")
                progress.setRange(0, 0)
                QCoreApplication.processEvents()
                rk_ctrl._fit_rf_stage(progress_fn=_progress)
            if getattr(rk_ctrl, "_variogram_lags", None) is None or getattr(rk_ctrl, "_variogram_gamma", None) is None:
                progress.setLabelText("Fitting residual semivariogram...")
                progress.setRange(0, 0)
                QCoreApplication.processEvents()
                rk_ctrl._fit_variogram_stage()
            rk_ctrl._run_rk_prediction(progress_fn=_progress)
        except KeyboardInterrupt:
            self._show_warning("Regression Kriging", "Operation canceled by the user.")
        except Exception as exc:
            self._show_warning("Regression Kriging", f"Interpolation failed:\n{exc}")
        finally:
            progress.close()

    def _copy_source_figure_to_framework_map(self, source_fig: Optional[Figure]) -> None:
        if source_fig is None or getattr(self, "interpolation_fig", None) is None:
            return
        self._copy_source_figure_to_target(source_fig, self.interpolation_fig, self.interpolation_canvas)

    def _copy_source_figure_to_target(self, source_fig: Optional[Figure], target_fig: Optional[Figure], target_canvas: Optional[FigureCanvas]) -> None:
        if source_fig is None or target_fig is None or target_canvas is None:
            return
        try:
            import io
            import matplotlib.image as mpimg
            buf = io.BytesIO()
            source_fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
            buf.seek(0)
            arr = mpimg.imread(buf)
            target_fig.clear()
            ax = target_fig.add_subplot(111)
            ax.imshow(arr)
            ax.axis("off")
            target_fig.tight_layout(pad=0.2)
            target_canvas.draw_idle()
        except Exception:
            pass

    def _report_figure_block(self, title: str, fig: Optional[Figure]) -> str:
        """Convert a matplotlib figure to an HTML image block for the report."""
        if fig is None or not getattr(fig, "axes", None):
            return f"<p><b>{html.escape(title)}:</b> not generated yet.</p>"
        try:
            if not hasattr(self, "_report_image_paths"):
                self._report_image_paths = []
            safe = "".join(ch if ch.isalnum() else "_" for ch in str(title).lower()).strip("_") or "figure"
            fd, path = tempfile.mkstemp(prefix=f"framework_{safe}_", suffix=".png")
            os.close(fd)
            fig.savefig(path, dpi=420, bbox_inches="tight", pad_inches=0.08)
            self._report_image_paths.append(path)
            src = Path(path).as_posix()
            return (
                f"<div class='figure-block' align='center'>"
                f"<img class='report-figure' width='430' src='file:///{html.escape(src)}'>"
                f"<p class='figure-caption'>{html.escape(title)}</p></div>"
            )
        except Exception:
            return f"<p><b>{html.escape(title)}:</b> could not be rendered.</p>"

    def _report_decision_tree_block(self) -> str:
        """Export the dynamic Framework Decision tree for the PDF report."""
        tree = getattr(self, "_framework_decision_tree_view", None)
        if tree is None or not hasattr(tree, "export_png"):
            return "<p><b>Framework decision tree:</b> not generated yet.</p>"
        try:
            self._update_framework_decision_tree()
            if not hasattr(self, "_report_image_paths"):
                self._report_image_paths = []
            fd, path = tempfile.mkstemp(prefix="framework_decision_tree_", suffix=".png")
            os.close(fd)
            if not tree.export_png(path):
                return "<p><b>Framework decision tree:</b> could not be rendered.</p>"
            self._report_image_paths.append(path)
            src = Path(path).as_posix()
            return (
                "<div class='figure-block' align='center'>"
                f"<img class='decision-tree-figure' width='680' src='file:///{html.escape(src)}'>"
                "<p class='figure-caption'>Framework Decision Tree</p></div>"
            )
        except Exception:
            return "<p><b>Framework decision tree:</b> could not be rendered.</p>"

    def _make_validation_bar_figure(self, metric: str) -> Optional[Figure]:
        rows = list(self.state.validation_results or [])
        if not rows:
            return None
        metric = str(metric).lower()
        methods = [str(r.get("method", "")) for r in rows]
        values = [float(r.get(metric, 0.0) or 0.0) for r in rows]
        fig = Figure(figsize=(5.4, 3.0))
        ax = fig.add_subplot(111)
        xpos = np.arange(len(methods))
        ax.bar(xpos, values, color=self._viridis_colors(len(methods)), edgecolor="black", linewidth=0.4)
        ax.set_xticks(xpos)
        ax.set_xticklabels(methods)
        ax.set_ylabel(metric.upper())
        ax.set_title(f"{metric.upper()} comparison", fontsize=10, pad=6)
        ax.grid(axis="y", linestyle="--", alpha=0.35)
        fig.tight_layout(pad=0.45)
        return fig

    def _make_observed_predicted_figure(self, row: Dict[str, Any]) -> Optional[Figure]:
        obs = np.asarray(row.get("observed", []), dtype=float)
        pred = np.asarray(row.get("predicted", []), dtype=float)
        mask = np.isfinite(obs) & np.isfinite(pred)
        obs = obs[mask]
        pred = pred[mask]
        if obs.size == 0:
            return None
        fig = Figure(figsize=(4.8, 3.6))
        ax = fig.add_subplot(111)
        mn = float(min(np.nanmin(obs), np.nanmin(pred)))
        mx = float(max(np.nanmax(obs), np.nanmax(pred)))
        if not np.isfinite(mn) or not np.isfinite(mx) or mn == mx:
            mn, mx = 0.0, 1.0
        pad = 0.02 * (mx - mn if mx > mn else 1.0)
        vmin, vmax = mn - pad, mx + pad
        ax.scatter(obs, pred, s=24, alpha=0.9, facecolors="none", edgecolors="black", label="Data")
        ax.plot([vmin, vmax], [vmin, vmax], "-", color="black", linewidth=1.0, label="1:1")
        if obs.size >= 2:
            slope, intercept = np.polyfit(obs, pred, 1)
            ax.plot([vmin, vmax], [slope * vmin + intercept, slope * vmax + intercept], "-", color="#d62728", linewidth=1.0, label="Fit")
        ax.set_xlim(vmin, vmax)
        ax.set_ylim(vmin, vmax)
        ax.set_aspect("auto")
        ax.set_xlabel("Observed", fontsize=8)
        ax.set_ylabel("Predicted", fontsize=8)
        ax.set_title(f"Observed vs Predicted - {row.get('method', '')}", fontsize=8)
        ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.6)
        ax.tick_params(axis="both", labelsize=7)
        ax.legend(loc="best", frameon=False, fontsize=8)
        fig.tight_layout()
        return fig

    def _get_correlation_report_figure(self) -> Optional[Figure]:
        ml_ctrl = getattr(self.plugin, "ml_ctrl", None) if self.plugin is not None else None
        fig = getattr(ml_ctrl, "_corr_fig", None)
        if fig is not None and getattr(fig, "axes", None):
            return fig
        return getattr(self, "framework_corr_fig", None)

    def _make_covariate_map_figures(self) -> List[tuple]:
        ml_ctrl = getattr(self.plugin, "ml_ctrl", None) if self.plugin is not None else None
        cov_layers = getattr(ml_ctrl, "covariate_layers", {}) if ml_ctrl is not None else {}
        figures = []
        for name in self.state.covariates:
            layer = cov_layers.get(name) if isinstance(cov_layers, dict) else None
            if not isinstance(layer, QgsRasterLayer):
                try:
                    matches = QgsProject.instance().mapLayersByName(str(name))
                    if not matches:
                        matches = QgsProject.instance().mapLayersByName(Path(str(name)).stem)
                    layer = matches[0] if matches else None
                except Exception:
                    layer = None
            if not isinstance(layer, QgsRasterLayer):
                continue
            fig = self._make_raster_preview_figure(layer, name)
            if fig is not None:
                figures.append((f"Covariate map - {name}", fig))
        return figures

    def _make_raster_preview_figure(self, layer: QgsRasterLayer, title: str) -> Optional[Figure]:
        try:
            provider = layer.dataProvider()
            extent = layer.extent()
            width = max(8, min(int(layer.width()), 520))
            height = max(8, min(int(layer.height()), 520))
            block = provider.block(1, extent, width, height)
            arr = np.full((height, width), np.nan, dtype=float)
            for r in range(height):
                for c in range(width):
                    val = block.value(r, c)
                    try:
                        arr[r, c] = float(val)
                    except Exception:
                        arr[r, c] = np.nan
            if not np.isfinite(arr).any():
                return None
            fig = Figure(figsize=(4.8, 3.4))
            ax = fig.add_subplot(111)
            im = ax.imshow(arr, cmap="viridis", origin="upper")
            ax.set_title(str(title), fontsize=10, pad=6)
            ax.axis("off")
            fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            fig.tight_layout(pad=0.45)
            return fig
        except Exception:
            return None

    def _populate_validation_table(self, rows: List[Dict[str, Any]]) -> None:
        """Populate the validation results table."""
        if not self.table_validation:
            return

        headers = ["Rank", "Method", "RMSE", "RMSE%", "MAE", "R2", "Pearson", "LCCC"]
        self.table_validation.setColumnCount(len(headers))
        self.table_validation.setHorizontalHeaderLabels(headers)
        self.table_validation.setRowCount(len(rows))

        try:
            from qgis.PyQt.QtWidgets import QTableWidgetItem
        except Exception:  # pragma: no cover
            from PyQt5.QtWidgets import QTableWidgetItem

        for r, row in enumerate(rows):
            values = [
                row.get("rank", ""),
                row.get("method", ""),
                row.get("rmse", ""),
                row.get("rmse_pct", ""),
                row.get("mae", ""),
                row.get("r2", ""),
                row.get("r", ""),
                row.get("lccc", ""),
            ]
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                self.table_validation.setItem(r, c, item)

        self.table_validation.resizeColumnsToContents()

    def _on_validation_plot_type_changed(self, *args) -> None:
        self._refresh_observed_plot_controls_from_results()
        self._refresh_validation_method_combo()
        self._sync_validation_method_controls_visibility()
        self._draw_validation_plot()

    def _on_validation_method_changed(self, *args) -> None:
        method = self._current_validation_plot_method()
        if method:
            self._select_validation_plot_method(method, sync_combo=False)

    def _on_observed_live_selector_changed(self, *args) -> None:
        combo = getattr(self, "cmb_observed_plot_method", None)
        if combo is None or combo.count() == 0:
            return
        method = str(combo.currentData() or combo.currentText() or "").strip()
        if method:
            self._select_validation_plot_method(method)

    def _on_validation_table_selection_changed(self) -> None:
        """Let a validation-table row switch the observed/predicted method."""
        plot_type = self.cmb_validation_plot_type.currentText() if self.cmb_validation_plot_type else ""
        if "Observed" not in plot_type and "Predicted" not in plot_type:
            return
        table = self.table_validation
        if table is None:
            return
        try:
            row = table.currentRow()
            item = table.item(row, 1) if row >= 0 else None
            method = item.text().strip() if item is not None else ""
        except Exception:
            method = ""
        if method:
            self._select_validation_plot_method(method)

    def _current_validation_plot_method(self) -> str:
        """Return the selected validation method from the combo data/text."""
        live_combo = getattr(self, "cmb_observed_plot_method", None)
        if live_combo is not None and live_combo.isVisible() and live_combo.count():
            data = live_combo.currentData()
            text = live_combo.currentText()
            if data not in (None, ""):
                return str(data).strip()
            if text:
                return str(text).strip()
        if self.cmb_validation_method and self.cmb_validation_method.count():
            data = self.cmb_validation_method.currentData()
            text = self.cmb_validation_method.currentText()
            if data not in (None, ""):
                return str(data).strip()
            if text:
                return str(text).strip()
        return str(self.state.__dict__.get("validation_plot_method", "") or "").strip()

    def _select_validation_plot_method(self, method: str, sync_combo: bool = True) -> None:
        """Select a method and redraw the observed/predicted plot directly."""
        method = str(method or "").strip()
        if not method:
            return
        self.state.__dict__["validation_plot_method"] = method
        if sync_combo and self.cmb_validation_method:
            idx = self.cmb_validation_method.findData(method)
            if idx < 0:
                idx = self.cmb_validation_method.findText(method)
            if idx >= 0:
                self.cmb_validation_method.blockSignals(True)
                self.cmb_validation_method.setCurrentIndex(idx)
                self.cmb_validation_method.blockSignals(False)
        live_combo = getattr(self, "cmb_observed_plot_method", None)
        if sync_combo and live_combo is not None:
            idx = live_combo.findData(method)
            if idx < 0:
                idx = live_combo.findText(method)
            if idx >= 0:
                live_combo.blockSignals(True)
                live_combo.setCurrentIndex(idx)
                live_combo.blockSignals(False)
        self._set_observed_method_button_state(method)
        plot_type = self.cmb_validation_plot_type.currentText() if self.cmb_validation_plot_type else ""
        if "Observed" in plot_type or "Predicted" in plot_type:
            self.validation_fig.clear()
            self.validation_fig.add_subplot(111)
            self._draw_observed_predicted_plot(list(self.state.validation_results or []), method_override=method)

    def _set_observed_method_button_state(self, method: str) -> None:
        buttons = getattr(self, "_observed_method_buttons", {}) or {}
        for name, button in buttons.items():
            try:
                button.blockSignals(True)
                button.setChecked(str(name).upper() == str(method).upper())
                button.blockSignals(False)
            except Exception:
                pass

    def _refresh_observed_method_buttons(self, methods: List[str]) -> None:
        """Refresh direct method buttons for Observed vs Predicted."""
        self._ensure_observed_method_buttons()
        panel = getattr(self, "_observed_method_panel", None)
        layout = getattr(self, "_observed_method_layout", None)
        if panel is None or layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._observed_method_buttons = {}
        current = self._current_validation_plot_method()
        label = QLabel("Observed vs Predicted method:", panel)
        label.setStyleSheet("font-weight: bold;")
        layout.addWidget(label)
        for method in methods:
            button = QPushButton(str(method), panel)
            button.setCheckable(True)
            button.setMinimumWidth(54)
            button.setStyleSheet(
                "QPushButton { padding: 3px 8px; } "
                "QPushButton:checked { background-color: #2f0dee; color: white; font-weight: bold; }"
            )
            button.clicked.connect(lambda checked=False, m=method: self._select_validation_plot_method(m))
            layout.addWidget(button)
            self._observed_method_buttons[str(method)] = button
        layout.addStretch(1)
        self._set_observed_method_button_state(current)

    def _refresh_observed_live_selector(self, methods: List[str]) -> None:
        self._ensure_observed_method_live_selector()
        combo = getattr(self, "cmb_observed_plot_method", None)
        if combo is None:
            return
        current = self.state.__dict__.get("validation_plot_method") or self._current_validation_plot_method()
        combo.blockSignals(True)
        combo.clear()
        for method in methods:
            combo.addItem(str(method), str(method))
        idx = combo.findData(current)
        if idx < 0:
            idx = combo.findText(current)
        if idx < 0 and combo.count():
            idx = 0
        if idx >= 0:
            combo.setCurrentIndex(idx)
            self.state.__dict__["validation_plot_method"] = str(combo.currentData() or combo.currentText() or "")
        combo.blockSignals(False)

    def _observed_predicted_methods_from_results(self) -> List[str]:
        """Return methods with finite observed/predicted validation vectors."""
        methods: List[str] = []
        for row in self.state.validation_results or []:
            method = str(row.get("method", "") or "").strip()
            if not method:
                continue
            obs = np.asarray(row.get("observed", []), dtype=float)
            pred = np.asarray(row.get("predicted", []), dtype=float)
            mask = np.isfinite(obs) & np.isfinite(pred)
            if mask.sum() >= 2 and method not in methods:
                methods.append(method)
        return methods

    def _refresh_observed_plot_controls_from_results(self) -> None:
        """Populate Observed vs Predicted controls from validated prediction data."""
        methods = self._observed_predicted_methods_from_results()
        if methods:
            current = str(self.state.__dict__.get("validation_plot_method", "") or "").strip()
            if current not in methods:
                current = methods[0]
                self.state.__dict__["validation_plot_method"] = current
        self._refresh_observed_live_selector(methods)
        self._refresh_observed_method_buttons(methods)
        self._sync_validation_method_controls_visibility()

    def _sync_validation_method_controls_visibility(self) -> None:
        plot_type = self.cmb_validation_plot_type.currentText() if self.cmb_validation_plot_type else ""
        show_method = "Observed" in plot_type or "Predicted" in plot_type
        self._set_validation_method_controls_visible(show_method)

    def _set_validation_method_controls_visible(self, visible: bool) -> None:
        if self.lbl_validation_method is not None:
            self.lbl_validation_method.setVisible(False)
            self.lbl_validation_method.setEnabled(False)
        if self.cmb_validation_method is not None:
            self.cmb_validation_method.setVisible(False)
            self.cmb_validation_method.setEnabled(False)
        panel = getattr(self, "_observed_method_panel", None)
        if panel is not None:
            panel.setVisible(bool(visible) and bool(getattr(self, "_observed_method_buttons", {})))
            panel.setEnabled(bool(visible))
        for widget in (
            getattr(self, "lbl_observed_plot_method", None),
            getattr(self, "cmb_observed_plot_method", None),
            getattr(self, "btn_observed_plot_update", None),
        ):
            if widget is not None:
                widget.setVisible(False)
                widget.setEnabled(False)

    def _draw_validation_plot(self, *args) -> None:
        """Draw validation comparison bars in the Framework validation plot tab."""
        if getattr(self, "validation_fig", None) is None:
            return
        self._sync_figure_to_canvas(self.validation_fig, self.validation_canvas, fallback=(5.2, 3.6))
        self.validation_fig.clear()
        ax = self.validation_fig.add_subplot(111)
        rows = list(self.state.validation_results or [])
        if not rows:
            ax.text(0.5, 0.5, "No validation results", ha="center", va="center")
            ax.axis("off")
            self.validation_canvas.draw_idle()
            return

        plot_type = self.cmb_validation_plot_type.currentText() if self.cmb_validation_plot_type else "LCCC comparison"
        if "Observed" in plot_type or "Predicted" in plot_type:
            self._draw_observed_predicted_plot(rows)
            return
        methods = [str(r.get("method", "")) for r in rows]
        if "RMSE" in plot_type.upper():
            values = [float(r.get("rmse", 0.0) or 0.0) for r in rows]
            ylabel = "RMSE"
        else:
            values = [float(r.get("lccc", 0.0) or 0.0) for r in rows]
            ylabel = "LCCC"
        xpos = np.arange(len(methods))
        colors = self._viridis_colors(len(methods))
        ax.bar(xpos, values, color=colors, edgecolor="black", linewidth=0.4)
        ax.set_xticks(xpos)
        ax.set_xticklabels(methods, rotation=0)
        ax.set_ylabel(ylabel)
        ax.set_title(plot_type)
        ax.grid(axis="y", linestyle="--", alpha=0.35)
        self.validation_fig.tight_layout(pad=0.8)
        self.validation_canvas.draw_idle()

    def _draw_observed_predicted_plot(self, rows: List[Dict[str, Any]], method_override: Optional[str] = None) -> None:
        self._sync_figure_to_canvas(self.validation_fig, self.validation_canvas, fallback=(5.2, 3.6))
        method = str(method_override or self._current_validation_plot_method() or "").strip()
        if not method and rows:
            method = str(rows[0].get("method", ""))
            if self.cmb_validation_method and method:
                idx = self.cmb_validation_method.findData(method)
                if idx < 0:
                    idx = self.cmb_validation_method.findText(method)
                if idx >= 0:
                    self.cmb_validation_method.blockSignals(True)
                    self.cmb_validation_method.setCurrentIndex(idx)
                    self.cmb_validation_method.blockSignals(False)
            self.state.__dict__["validation_plot_method"] = method
        row = next((r for r in rows if str(r.get("method", "")).strip().upper() == str(method).strip().upper()), None)
        ax = self.validation_fig.axes[0] if self.validation_fig.axes else self.validation_fig.add_subplot(111)
        ax.clear()
        if row is None:
            available = ", ".join(str(r.get("method", "")) for r in rows if r.get("method")) or "None"
            ax.text(
                0.5,
                0.5,
                f"No observed/predicted data for {method or 'selected method'}\nAvailable: {available}",
                ha="center",
                va="center",
            )
            ax.axis("off")
            self.validation_canvas.draw_idle()
            return
        obs = np.asarray(row.get("observed", []), dtype=float)
        pred = np.asarray(row.get("predicted", []), dtype=float)
        mask = np.isfinite(obs) & np.isfinite(pred)
        obs = obs[mask]
        pred = pred[mask]
        if obs.size == 0:
            ax.text(0.5, 0.5, "No observed/predicted data", ha="center", va="center")
            ax.axis("off")
            self.validation_canvas.draw_idle()
            return
        mn = float(min(np.nanmin(obs), np.nanmin(pred)))
        mx = float(max(np.nanmax(obs), np.nanmax(pred)))
        if not np.isfinite(mn) or not np.isfinite(mx) or mn == mx:
            mn, mx = 0.0, 1.0
        pad = 0.02 * (mx - mn if mx > mn else 1.0)
        vmin, vmax = mn - pad, mx + pad
        ax.scatter(obs, pred, s=24, alpha=0.9, facecolors="none", edgecolors="black", label="Data")
        ax.plot([vmin, vmax], [vmin, vmax], "-", color="black", linewidth=1.0, label="1:1")
        if obs.size >= 2:
            slope, intercept = np.polyfit(obs, pred, 1)
            ax.plot([vmin, vmax], [slope * vmin + intercept, slope * vmax + intercept], "-", color="#d62728", linewidth=1.0, label="Fit")
        ax.set_xlim(vmin, vmax)
        ax.set_ylim(vmin, vmax)
        ax.set_aspect("auto")
        ax.set_xlabel("Observed", fontsize=8)
        ax.set_ylabel("Predicted", fontsize=8)
        ax.set_title(f"Observed vs Predicted - {row.get('method', method)}", fontsize=8)
        ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.6)
        ax.tick_params(axis="both", labelsize=7)
        ax.legend(loc="best", frameon=False, fontsize=8)
        self.validation_fig.tight_layout()
        self.validation_canvas.draw_idle()

    @staticmethod
    def _viridis_colors(n: int):
        try:
            import matplotlib.cm as cm
            vals = np.linspace(0.15, 0.85, max(int(n), 1))
            return cm.viridis(vals)
        except Exception:
            return ["#2f0dee"] * max(int(n), 1)

    @staticmethod
    def _pearson_r(obs, pred) -> float:
        o = np.asarray(obs, dtype=float)
        p = np.asarray(pred, dtype=float)
        mask = np.isfinite(o) & np.isfinite(p)
        if mask.sum() < 2:
            return float("nan")
        o = o[mask]
        p = p[mask]
        so = float(np.std(o, ddof=1))
        sp = float(np.std(p, ddof=1))
        if so <= 0 or sp <= 0:
            return float("nan")
        return float(np.corrcoef(o, p)[0, 1])

    @staticmethod
    def _lccc(obs, pred) -> float:
        o = np.asarray(obs, dtype=float)
        p = np.asarray(pred, dtype=float)
        mask = np.isfinite(o) & np.isfinite(p)
        if mask.sum() < 2:
            return float("nan")
        o = o[mask]
        p = p[mask]
        mean_o = float(np.mean(o))
        mean_p = float(np.mean(p))
        std_o = float(np.std(o))
        std_p = float(np.std(p))
        cov_op = float(np.mean((o - mean_o) * (p - mean_p)))
        denom = std_o ** 2 + std_p ** 2 + (mean_o - mean_p) ** 2
        if not np.isfinite(denom) or abs(denom) < 1e-12:
            return float("nan")
        return float((2.0 * cov_op) / denom)

    def _run_framework_validation_method(self, method: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Run real validation for a Framework method and return a metrics row."""
        method = str(method or "").strip().upper()
        if method in {"TPS", "IDW", "OK"}:
            return self._run_deterministic_or_ok_loocv(method, data)
        return self._run_existing_controller_cv(method)

    def _run_deterministic_or_ok_loocv(self, method: str, data: Dict[str, Any]) -> Dict[str, Any]:
        if finite_training_arrays is not None:
            x, y, z = finite_training_arrays(data.get("x", []), data.get("y", []), data.get("z", []))
        else:
            x = np.asarray(data.get("x", []), dtype=float)
            y = np.asarray(data.get("y", []), dtype=float)
            z = np.asarray(data.get("z", []), dtype=float)
            mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
            x, y, z = x[mask], y[mask], z[mask]
        if method == "TPS":
            x2, y2, z2, duplicate_rows, duplicate_groups = self._dedupe_training_by_xy_keep_first(x, y, z)
            if duplicate_rows > 0:
                if not self._confirm_tps_duplicate_handling(duplicate_rows, duplicate_groups):
                    raise ValueError("TPS validation canceled because duplicate locations were not accepted.")
                x, y, z = x2, y2, z2
        min_required = self._minimum_samples_for_method(method)
        if z.size < min_required:
            raise ValueError(f"at least {min_required} valid points are required.")

        preds = np.full(z.size, np.nan, dtype=float)
        params_text = ""
        if method == "TPS":
            if tps_interpolation is None:
                raise ValueError("TPS interpolation backend is not available.")
            for i in range(z.size):
                train = np.ones(z.size, dtype=bool)
                train[i] = False
                train_xy = ensure_xy_2d(np.column_stack([x[train], y[train]]), "training coordinates") if ensure_xy_2d else np.column_stack([x[train], y[train]])
                test_xy = ensure_xy_2d([[x[i], y[i]]], "prediction coordinates") if ensure_xy_2d else np.asarray([[x[i], y[i]]], dtype=float)
                train_values = ensure_values_1d(z[train], "training values") if ensure_values_1d else np.asarray(z[train], dtype=float).ravel()
                pred = tps_interpolation(
                    train_xy[:, 0], train_xy[:, 1], train_values,
                    test_xy[:, 0], test_xy[:, 1],
                )
                preds[i] = float(np.asarray(pred, dtype=float).ravel()[0])
        elif method == "IDW":
            if idw_interpolation is None:
                raise ValueError("IDW interpolation backend is not available.")
            try:
                best_p, best_n, _, _ = optimize_idw(x, y, z) if optimize_idw is not None else (2.0, min(12, z.size - 1), None, None)
            except Exception:
                best_p, best_n = 2.0, min(12, z.size - 1)
            params_text = f"Optimized power p={float(best_p):.3f}; neighbors n={int(best_n)}"
            for i in range(z.size):
                train = np.ones(z.size, dtype=bool)
                train[i] = False
                n_eff = max(1, min(int(best_n), int(train.sum())))
                train_xy = ensure_xy_2d(np.column_stack([x[train], y[train]]), "training coordinates") if ensure_xy_2d else np.column_stack([x[train], y[train]])
                test_xy = ensure_xy_2d([[x[i], y[i]]], "prediction coordinates") if ensure_xy_2d else np.asarray([[x[i], y[i]]], dtype=float)
                train_values = ensure_values_1d(z[train], "training values") if ensure_values_1d else np.asarray(z[train], dtype=float).ravel()
                pred = idw_interpolation(
                    train_xy[:, 0], train_xy[:, 1], train_values,
                    test_xy[:, 0], test_xy[:, 1],
                    best_p, n_eff,
                )
                preds[i] = float(np.asarray(pred, dtype=float).ravel()[0])
        elif method == "OK":
            preds = self._run_ok_framework_cv(x, y, z)
        else:
            raise ValueError(f"unsupported method {method}.")
        row = self._validation_row_from_predictions(method, z, preds)
        if params_text:
            row["parameters"] = params_text
        return row

    @staticmethod
    def _ok_model_text_from_token(token: str) -> str:
        token = str(token or "").strip().lower()
        if token.startswith("sph"):
            return "Spherical"
        if token.startswith("gau"):
            return "Gaussian"
        return "Exponential"

    def _ok_model_token_for_reml(self, model_text: str) -> str:
        token = self._normalize_model_token(model_text)
        return {"spherical": "Sph", "exponential": "Exp", "gaussian": "Gau"}.get(token, "Exp")

    def _is_ok_model_auto(self, model_name: str) -> bool:
        return str(model_name or "").strip().lower().startswith("auto")

    def _select_best_ok_variogram_model(self, x: np.ndarray, y: np.ndarray, z: np.ndarray) -> str:
        rows = []
        for token in ("spherical", "exponential", "gaussian"):
            model_name = self._ok_model_text_from_token(token)
            try:
                preds = self._run_ok_framework_cv(x, y, z, model_name=model_name)
                row = self._validation_row_from_predictions(model_name, z, preds)
                row["token"] = token
                rows.append(row)
            except Exception as exc:
                rows.append({
                    "method": model_name,
                    "token": token,
                    "rmse": "",
                    "rmse_pct": "",
                    "mae": "",
                    "r2": "",
                    "r": "",
                    "lccc": "",
                    "error": str(exc),
                })
        ranked = sorted(
            rows,
            key=lambda row: (
                -(float(row.get("r2")) if str(row.get("r2", "")).strip() else -1e300),
                float(row.get("rmse")) if str(row.get("rmse", "")).strip() else 1e300,
            ),
        )
        best = ranked[0] if ranked else {"method": "Exponential"}
        self.state.ok_model_validation_results = ranked
        best_model = str(best.get("method") or "Exponential")
        self.state.__dict__["variogram_model"] = best_model
        return best_model

    def _show_ok_model_validation_dialog(self) -> None:
        rows = list(getattr(self.state, "ok_model_validation_results", []) or [])
        if not rows:
            self._show_info("Kriging model validation", "Run Framework diagnostics or validation first.")
            return
        dlg = QDialog(self.dlg)
        dlg.setWindowTitle("Framework kriging model validation")
        layout = QVBoxLayout(dlg)
        table = QTableWidget(dlg)
        headers = ["Model", "RMSE", "RMSE%", "MAE", "R2", "Pearson", "LCCC"]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            values = [
                row.get("method", ""),
                row.get("rmse", ""),
                row.get("rmse_pct", ""),
                row.get("mae", ""),
                row.get("r2", ""),
                row.get("r", ""),
                row.get("lccc", ""),
            ]
            for c, value in enumerate(values):
                table.setItem(r, c, QTableWidgetItem(str(value if value != "" else "--")))
        try:
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        except Exception:
            table.resizeColumnsToContents()
        layout.addWidget(table)
        dlg.resize(760, 260)
        dlg.exec_()

    def _run_ok_framework_cv(self, x: np.ndarray, y: np.ndarray, z: np.ndarray, model_name: Optional[str] = None) -> np.ndarray:
        model_name = str(model_name or self.state.__dict__.get("variogram_model") or "Spherical")
        if self._is_ok_model_auto(model_name):
            model_name = self._select_best_ok_variogram_model(x, y, z)
        dmax = float(np.nanmax(self._pairwise_distances(x, y))) if z.size > 1 else 1.0
        cutoff = 0.5 * dmax
        lagw = self._safe_lag_width(x, y, cutoff, self._nearest_neighbor_dist(x, y))
        lags, gamma = self._bin_variogram(x, y, z, cutoff, lagw)
        nugget, psill, rng = self._guess_initial_params(lags, gamma, cutoff, model=self._normalize_model_token(model_name))

        selected_fit = self._resolve_ok_fit_method(z.size)
        if selected_fit == "REML" and cv_ok_reml_interface is not None:
            sample_xyz = np.column_stack([x, y, z])
            fit = fit_ok_reml_interface(
                sample_xyz=sample_xyz,
                model=self._ok_model_token_for_reml(model_name),
                init_from_mom={"nugget": nugget, "psill": psill, "range": rng},
                random_state=123,
            )
            cv = cv_ok_reml_interface(sample_xyz, fit, k=0)
            pred = cv.get("y_pred", cv.get("pred"))
            if pred is not None:
                return np.asarray(pred, dtype=float)
        elif selected_fit == "REML":
            self._show_warning("Framework OK validation", "REML cross-validation is not available. MoM will be used instead.")

        if ordinary_kriging_interpolation is None:
            raise ValueError("Ordinary Kriging backend is not available.")
        preds = np.full(z.size, np.nan, dtype=float)
        for i in range(z.size):
            train = np.ones(z.size, dtype=bool)
            train[i] = False
            preds[i] = float(np.asarray(ordinary_kriging_interpolation(
                x[train], y[train], z[train], [x[i]], [y[i]],
                nugget=nugget, psill=psill, var_range=rng, model=model_name
            )).ravel()[0])
        return preds

    def _run_existing_controller_cv(self, method: str) -> Optional[Dict[str, Any]]:
        mapping = {
            "RFE": ("ml_ctrl", "_on_run_rf_cross_validation", "_last_rf_cv_result"),
            "RF": ("ml_ctrl", "_on_run_rf_cross_validation", "_last_rf_cv_result"),
            "SVM": ("ml_ctrl", "_on_run_svm_cross_validation", "_last_svm_cv_result"),
            "RK": ("rk_ctrl", "_on_run_rk_cv_clicked", "_last_rk_cv_result"),
        }
        entry = mapping.get(method)
        if entry is None or self.plugin is None:
            return None
        ctrl_name, runner_name, result_name = entry
        ctrl = getattr(self.plugin, ctrl_name, None)
        if ctrl is None or not hasattr(ctrl, runner_name):
            return None
        try:
            setattr(ctrl, result_name, None)
        except Exception:
            pass
        getattr(ctrl, runner_name)()
        result = getattr(ctrl, result_name, None)
        if not result:
            return None
        observed = result.get("observed")
        predicted = result.get("predicted")
        return self._validation_row_from_predictions(method, observed, predicted)

    def _validation_row_from_predictions(self, method: str, observed, predicted) -> Dict[str, Any]:
        obs = np.asarray(observed, dtype=float)
        pred = np.asarray(predicted, dtype=float)
        mask = np.isfinite(obs) & np.isfinite(pred)
        if mask.sum() < 2:
            raise ValueError("validation did not return enough finite predictions.")
        obs = obs[mask]
        pred = pred[mask]
        rmse = float(np.sqrt(np.mean((obs - pred) ** 2)))
        mean_obs = float(np.mean(obs))
        rmse_pct = float(100.0 * rmse / abs(mean_obs)) if np.isfinite(mean_obs) and abs(mean_obs) > 1e-12 else float("nan")
        mae = float(np.mean(np.abs(obs - pred)))
        r = self._pearson_r(obs, pred)
        ss_tot = float(np.sum((obs - np.mean(obs)) ** 2))
        r2 = float(1.0 - (np.sum((obs - pred) ** 2) / ss_tot)) if ss_tot > 0 else float("nan")
        lccc = self._lccc(obs, pred)
        return {
            "rank": "",
            "method": method,
            "group": self._method_group(method),
            "lccc": round(lccc, 3) if np.isfinite(lccc) else "",
            "rmse": round(rmse, 3),
            "rmse_pct": round(rmse_pct, 2) if np.isfinite(rmse_pct) else "",
            "mae": round(mae, 3),
            "r": round(r, 3) if np.isfinite(r) else "",
            "r2": round(r2, 3) if np.isfinite(r2) else "",
            "observed": obs.tolist(),
            "predicted": pred.tolist(),
        }

    def _refresh_covariate_list(self) -> None:
        """Refresh the covariate list widget."""
        if not self.list_covariates:
            return
        self.list_covariates.clear()
        for path in self.state.covariates:
            self.list_covariates.addItem(QListWidgetItem(path))

    def _refresh_validation_method_combo(self) -> None:
        """Refresh the validation method combo used for single-method plots."""
        valid_obs_methods = self._observed_predicted_methods_from_results()
        if valid_obs_methods:
            self._refresh_observed_live_selector(valid_obs_methods)
            self._refresh_observed_method_buttons(valid_obs_methods)
        if not self.cmb_validation_method:
            self._sync_validation_method_controls_visibility()
            return
        current = self._current_validation_plot_method()
        methods = list(valid_obs_methods)
        methods.extend(self._validation_methods_from_table())
        methods.extend(self.state.validated_methods or [])
        methods.extend(self._selected_methods_from_checkboxes())
        methods.extend(self.state.suggested_methods or [])
        methods = [m for m in methods if m]
        deduped = []
        for method in methods:
            method = str(method or "").strip()
            if method and method not in deduped:
                deduped.append(method)
        methods = deduped
        self.cmb_validation_method.blockSignals(True)
        self.cmb_validation_method.clear()
        for method in methods:
            self.cmb_validation_method.addItem(method, method)
        idx = self.cmb_validation_method.findData(current)
        if idx < 0:
            idx = self.cmb_validation_method.findText(current)
        if idx >= 0:
            self.cmb_validation_method.setCurrentIndex(idx)
        elif methods:
            self.cmb_validation_method.setCurrentIndex(0)
        if self.cmb_validation_method.count():
            data = self.cmb_validation_method.currentData()
            text = self.cmb_validation_method.currentText()
            self.state.__dict__["validation_plot_method"] = str(data or text or "")
        self.cmb_validation_method.blockSignals(False)
        self.cmb_validation_method.setEnabled(bool(methods))
        self._refresh_observed_live_selector(valid_obs_methods)
        self._refresh_observed_method_buttons(valid_obs_methods)
        self._sync_validation_method_controls_visibility()

    def _validation_methods_from_table(self) -> List[str]:
        """Read validated method names directly from the validation table as a UI fallback."""
        methods: List[str] = []
        table = self.table_validation
        if table is None:
            return methods
        try:
            for row in range(table.rowCount()):
                item = table.item(row, 1)
                if item is not None:
                    text = item.text().strip()
                    if text:
                        methods.append(text)
        except Exception:
            pass
        return methods

    def _refresh_final_method_combo(self) -> None:
        """Refresh the final interpolation method combo."""
        if not self.cmb_final_method:
            return
        current = self.cmb_final_method.currentText()
        methods = self.state.validated_methods or self.state.eligible_methods or ["TPS", "IDW", "OK"]
        self.cmb_final_method.blockSignals(True)
        self.cmb_final_method.clear()
        self.cmb_final_method.addItems(methods)
        preferred = self.state.__dict__.get("selected_method") or self.state.selected_winner or current
        idx = self.cmb_final_method.findText(preferred)
        if idx >= 0:
            self.cmb_final_method.setCurrentIndex(idx)
        self.cmb_final_method.blockSignals(False)

    def _refresh_method_checkboxes(self, apply_recommended: bool = False) -> None:
        """Keep all method boxes selectable while optionally checking recommendations."""
        suggested_set = set(self.state.suggested_methods)

        for method, widget_name in self.METHOD_CHECKBOXES.items():
            checkbox = self._get(widget_name)
            if not checkbox:
                continue
            checkbox.setEnabled(True)
            if apply_recommended:
                checkbox.setChecked(method in suggested_set)

    def _selected_methods_from_checkboxes(self) -> List[str]:
        """Return the currently selected validation methods."""
        selected: List[str] = []
        for method, widget_name in self.METHOD_CHECKBOXES.items():
            checkbox = self._get(widget_name)
            if checkbox and checkbox.isChecked():
                selected.append(method)
        return selected

    def _method_group(self, method: str) -> str:
        """Return a simple family label for each method."""
        if method in {"TPS", "IDW"}:
            return "Deterministic"
        if method == "OK":
            return "Geostatistical"
        if method == "RK":
            return "Hybrid"
        return "Machine learning"

    def _show_framework_mode_image(self) -> None:
        """Create or refresh the dynamic Framework decision tree."""
        if self.frame_decision_figure is None:
            return
        if FrameworkDecisionTreeView is None:
            return

        layout = self.frame_decision_figure.layout()
        if layout is None:
            layout = QVBoxLayout(self.frame_decision_figure)
            layout.setContentsMargins(0, 0, 0, 0)
        tree = getattr(self, "_framework_decision_tree_view", None)
        if tree is None:
            for i in reversed(range(layout.count())):
                item = layout.itemAt(i)
                w = item.widget()
                if w is not None:
                    w.setParent(None)
            tree = FrameworkDecisionTreeView(self.frame_decision_figure)
            layout.addWidget(tree)
            self._framework_decision_tree_view = tree

        self._update_framework_decision_tree()

    def _resize_framework_image(self) -> None:
        tree = getattr(self, "_framework_decision_tree_view", None)
        if tree is not None and hasattr(tree, "_fit_to_view"):
            tree._fit_to_view()

    def _update_framework_decision_tree(self) -> None:
        """Push current Framework state into the vector decision tree."""
        tree = getattr(self, "_framework_decision_tree_view", None)
        if tree is None or FrameworkDecisionTreeView is None:
            return
        framework_type = "full" if self.state.framework_mode == "Full" else "univariate"
        try:
            tree.update_tree(framework_type, self._framework_tree_characteristics())
        except Exception:
            pass

    def _framework_tree_characteristics(self) -> Dict[str, Any]:
        """Collect diagnostics for the dynamic tree without changing decisions."""
        ok_fit = self.state.__dict__.get("ok_fit_method") or self.state.__dict__.get("fit_method")
        if not ok_fit and self.state.sample_count:
            ok_fit = "MoM" if int(self.state.sample_count) >= 100 else "REML"
        return {
            "n_samples": self.state.sample_count,
            "moran_pvalue": self.state.moran_p_value,
            "spatial_pattern": self.state.spatial_pattern,
            "sdi_value": self.state.sdi_value,
            "sdi_class": self.state.sdi_status or self.state.__dict__.get("sdi_class", ""),
            "framework_type": self.state.framework_mode,
            "recommended_methods": list(self.state.suggested_methods),
            "validation_metric": "LOOCV / LCCC",
            "variogram_fitting_method": ok_fit,
            "ok_fit_method": ok_fit,
            "covariates_available": bool(self.state.covariates),
        }

    def _get(self, name: str) -> Optional[QWidget]:
        """Find a child widget by name safely."""
        try:
            return self.dlg.findChild(QWidget, name)
        except Exception:
            return None

    def _set_text(self, widget: Optional[QWidget], value: str) -> None:
        """Set text on QLineEdit/QLabel-like widgets safely."""
        if widget is None:
            return
        if hasattr(widget, "setText"):
            widget.setText(value)

    def _set_plain_text(self, widget: Optional[QPlainTextEdit], value: str) -> None:
        """Set plain text safely."""
        if widget is not None:
            widget.setPlainText(value)

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        """Convert a value to float safely."""
        try:
            if value in (None, ""):
                return None
            return float(value)
        except Exception:
            return None

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        """Convert a value to int safely."""
        try:
            if value in (None, ""):
                return None
            return int(value)
        except Exception:
            return None

    @staticmethod
    def _fmt(value: Any) -> str:
        """Format values with up to two decimals when appropriate."""
        if value in (None, ""):
            return "Pending"
        if isinstance(value, float):
            return f"{value:.2f}"
        return str(value)

    @staticmethod
    def _classify_sdi(sdi: float) -> str:
        if sdi < 20.0:
            return "Very Low"
        if sdi < 40.0:
            return "Low"
        if sdi < 60.0:
            return "Moderate"
        if sdi < 80.0:
            return "High"
        return "Very High"

    def _apply_info_button_icon(self) -> None:
        """Apply the info PNG icon to the Framework info button when available."""
        if not self.btn_info:
            return
        pixmap = self._find_info_icon_pixmap()
        if pixmap is not None:
            self.btn_info.setIcon(QIcon(pixmap))
            try:
                self.btn_info.setToolTip("Framework article information")
            except Exception:
                pass

    def _find_info_icon_pixmap(self) -> Optional[QPixmap]:
        """Find an info PNG icon in the plugin folder."""
        plugin_dir = getattr(self.plugin, "plugin_dir", "") if self.plugin is not None else ""
        if not plugin_dir:
            return None

        candidates = [
            "info.png",
            "Info.png",
            "icon_info.png",
            "info_icon.png",
            "information.png",
        ]
        for name in candidates:
            path = Path(plugin_dir) / name
            if path.exists():
                pm = QPixmap(str(path))
                if not pm.isNull():
                    return pm

        for path_str in glob.glob(str(Path(plugin_dir) / "*.png")):
            name = Path(path_str).name.lower()
            if "info" in name:
                pm = QPixmap(path_str)
                if not pm.isNull():
                    return pm
        return None

    def _show_info(self, title: str, message: str) -> None:
        """Show an information message safely."""
        QMessageBox.information(self.dlg, title, message)

    def _show_rich_info(self, title: str, html: str) -> None:
        """Show rich text information with clickable links."""
        box = QMessageBox(self.dlg)
        box.setWindowTitle(title)
        box.setIcon(QMessageBox.Information)
        box.setTextFormat(Qt.RichText)
        box.setTextInteractionFlags(Qt.TextBrowserInteraction)
        box.setText(html)
        box.setStandardButtons(QMessageBox.Ok)
        for label in box.findChildren(QLabel):
            try:
                label.setOpenExternalLinks(True)
                label.setTextInteractionFlags(Qt.TextBrowserInteraction)
            except Exception:
                pass
        box.exec_()

    def _show_warning(self, title: str, message: str) -> None:
        """Show a warning message safely."""
        QMessageBox.warning(self.dlg, title, message)

