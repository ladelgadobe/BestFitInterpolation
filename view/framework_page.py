# -*- coding: utf-8 -*-
"""Framework page (prefix fw_) — the article's method-selection framework:
Overview, Data characteristics, Decision, Validation (multi-method
comparison) and Interpolation sub-tabs (legacy tabFramework/frameworkSubTabs).

Pure widget building — the FrameworkCtrl wires everything and reads the
session; this page never touches other tabs' widgets."""

from __future__ import annotations

import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QPixmap
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.methods import get_method
from .common import (
    make_cv_group,
    make_figure_panel,
    make_info_label,
    make_run_button,
    make_subtabs,
    tr,
)
from .decision_tree_view import DecisionTreeView

#: Registry keys shown by the framework, in display order.
FRAMEWORK_METHOD_KEYS = ("idw", "tps", "ok", "rf", "svm", "rk")

#: Columns of the comparison results table.
RESULT_COLUMNS = ("Method", "Status", "RMSE", "RMSE %", "MAE",
                  "Pearson r", "R²", "LCCC")

_IMAGE_WIDTH = 700

INTRO_TEXT = (
    "This framework guides the selection of the interpolation method from "
    "measurable characteristics of the dataset: sample size, spatial "
    "structure (global Moran's I), strength of the spatial dependence "
    "(SDI from the fitted semivariogram) and the availability of "
    "environmental covariates. Run \"Analyze data\" on the Data "
    "characteristics sub-tab, then \"Recommend method\" on the Decision "
    "sub-tab to trace the decision path shown in the reference diagrams "
    "below. The Validation sub-tab cross-validates the candidate methods "
    "side by side, and the Interpolation sub-tab generates the raster for "
    "the winning (or manually chosen) method. The univariate framework "
    "applies when no covariates are loaded; the full framework applies "
    "when covariates are available."
)

DATA_TAB_HINT = (
    "These diagnostics feed the recommendation: sample count, Moran's I "
    "spatial pattern (KNN weights, permutation test), the Spatial "
    "Dependence Index from a method-of-moments semivariogram fit "
    "(SDI = 100·C1/(C0+C1)) and the number of covariate rasters selected "
    "in the Machine Learning tab."
)


# ------------------------------------------------------------- sub-tabs

def _build_overview_tab(dialog):
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    inner = QWidget()
    layout = QVBoxLayout(inner)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(12)

    layout.addWidget(make_info_label(tr(INTRO_TEXT)))

    plugin_dir = getattr(dialog, "plugin_dir", "") or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
    images = (
        ("framework_univariate.png", tr("Univariate framework (no covariates)")),
        ("framework_full.png", tr("Full framework (with covariates)")),
    )
    for filename, caption in images:
        caption_label = QLabel(caption)
        font = caption_label.font()
        font.setBold(True)
        caption_label.setFont(font)
        layout.addWidget(caption_label)

        image_label = QLabel()
        pixmap = QPixmap(os.path.join(plugin_dir, filename))
        if pixmap.isNull():
            image_label.setText(tr("Image not found:") + " " + filename)
        else:
            if pixmap.width() > _IMAGE_WIDTH:
                pixmap = pixmap.scaled(
                    _IMAGE_WIDTH, 16 * _IMAGE_WIDTH,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation,
                )
            image_label.setPixmap(pixmap)
        layout.addWidget(image_label)

    layout.addStretch()
    scroll.setWidget(inner)
    return scroll


def _build_data_tab(dialog):
    tab = QWidget()
    layout = QVBoxLayout(tab)
    layout.setSpacing(10)

    layout.addWidget(make_info_label(tr(DATA_TAB_HINT)))

    group = QGroupBox(tr("Data characteristics"))
    form = QFormLayout(group)
    form.setContentsMargins(10, 8, 10, 8)
    dialog.fw_n_label = QLabel("—")
    form.addRow(QLabel(tr("Samples (n):")), dialog.fw_n_label)
    dialog.fw_moran_label = QLabel("—")
    form.addRow(QLabel(tr("Moran's I:")), dialog.fw_moran_label)
    dialog.fw_sdi_label = QLabel("—")
    form.addRow(QLabel(tr("Spatial Dependence Index (SDI):")), dialog.fw_sdi_label)
    dialog.fw_cov_label = QLabel("—")
    form.addRow(QLabel(tr("Covariates loaded:")), dialog.fw_cov_label)
    layout.addWidget(group)

    layout.addWidget(make_run_button(dialog, "fw_btn_analyze", tr("Analyze data")))
    layout.addStretch()
    return tab


def _build_decision_tab(dialog):
    tab = QWidget()
    layout = QVBoxLayout(tab)
    layout.setSpacing(10)

    layout.addWidget(make_run_button(dialog, "fw_btn_recommend", tr("Recommend method")))

    dialog.fw_recommendation_label = QLabel("—")
    dialog.fw_recommendation_label.setWordWrap(True)
    dialog.fw_recommendation_label.setAlignment(Qt.AlignCenter)
    font = dialog.fw_recommendation_label.font()
    font.setBold(True)
    font.setPointSize(font.pointSize() + 3)
    dialog.fw_recommendation_label.setFont(font)
    layout.addWidget(dialog.fw_recommendation_label)

    dialog.fw_decision_view = DecisionTreeView(tab)
    layout.addWidget(dialog.fw_decision_view, 1)
    return tab


def _build_validation_tab(dialog):
    tab = QWidget()
    root = QHBoxLayout(tab)
    root.setSpacing(12)

    controls = QVBoxLayout()
    controls.setSpacing(10)

    methods_group = QGroupBox(tr("Methods to compare"))
    methods_layout = QVBoxLayout(methods_group)
    method_list = QListWidget()
    for key in FRAMEWORK_METHOD_KEYS:
        item = QListWidgetItem(tr(get_method(key).info.label))
        item.setData(Qt.UserRole, key)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        method_list.addItem(item)
    dialog.fw_method_list = method_list
    methods_layout.addWidget(method_list)
    controls.addWidget(methods_group)

    controls.addWidget(make_cv_group(dialog, "fw"))
    controls.addWidget(make_run_button(dialog, "fw_btn_compare", tr("Run comparison")))
    controls.addStretch()
    root.addLayout(controls, 1)

    results = QVBoxLayout()
    table = QTableWidget(0, len(RESULT_COLUMNS))
    table.setHorizontalHeaderLabels([tr(name) for name in RESULT_COLUMNS])
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setSelectionMode(QTableWidget.SingleSelection)
    table.horizontalHeader().setStretchLastSection(True)
    dialog.fw_results_table = table
    results.addWidget(table, 1)

    dialog.fw_val_panel = make_figure_panel(tab)
    results.addWidget(dialog.fw_val_panel.container, 2)
    root.addLayout(results, 2)
    return tab


def _build_interpolation_tab(dialog):
    tab = QWidget()
    root = QHBoxLayout(tab)
    root.setSpacing(12)

    controls = QVBoxLayout()
    controls.setSpacing(10)

    method_group = QGroupBox(tr("Method"))
    method_layout = QVBoxLayout(method_group)
    combo = QComboBox()
    for key in FRAMEWORK_METHOD_KEYS:
        combo.addItem(tr(get_method(key).info.label), key)
    dialog.fw_method_combo = combo
    method_layout.addWidget(combo)
    controls.addWidget(method_group)

    controls.addWidget(make_run_button(dialog, "fw_btn_interpolate", tr("Interpolate")))
    controls.addStretch()
    root.addLayout(controls, 1)

    dialog.fw_map_panel = make_figure_panel(tab)
    root.addWidget(dialog.fw_map_panel.container, 2)
    return tab


# ------------------------------------------------------------ page entry

def setup_framework_page(dialog, page):
    page.setObjectName("tabFramework")
    root = QVBoxLayout(page)
    root.setContentsMargins(10, 10, 10, 10)

    subtabs = make_subtabs(dialog, "fw_subtabs", [
        (tr("Overview"), _build_overview_tab(dialog)),
        (tr("Data characteristics"), _build_data_tab(dialog)),
        (tr("Decision"), _build_decision_tab(dialog)),
        (tr("Validation"), _build_validation_tab(dialog)),
        (tr("Interpolation"), _build_interpolation_tab(dialog)),
    ])
    root.addWidget(subtabs)
