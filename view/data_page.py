# -*- coding: utf-8 -*-
"""Data page (prefix dt_) — faithful recreation of the legacy tabData:
point/variable/polygon pickers, Load button, pixel size, export checkbox,
CRS + Moran labels, and the sample-map preview."""

from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)
from qgis.core import QgsMapLayerProxyModel
from qgis.gui import QgsFieldComboBox, QgsMapLayerComboBox

from .common import make_figure_panel, make_run_button, tr


def setup_data_page(dialog, page):
    page.setObjectName("tabData")
    root = QHBoxLayout(page)
    root.setContentsMargins(10, 10, 10, 10)
    root.setSpacing(12)

    # ---- left column: inputs -------------------------------------------------
    left = QVBoxLayout()
    left.setSpacing(10)

    inputs = QGroupBox(tr("Inputs"))
    form = QFormLayout(inputs)
    form.setContentsMargins(10, 8, 10, 8)

    dialog.dt_points_combo = QgsMapLayerComboBox()
    dialog.dt_points_combo.setFilters(QgsMapLayerProxyModel.PointLayer)
    dialog.dt_points_combo.setAllowEmptyLayer(True)
    form.addRow(QLabel(tr("Load data points")), dialog.dt_points_combo)

    dialog.dt_variable_combo = QgsFieldComboBox()
    dialog.dt_points_combo.layerChanged.connect(dialog.dt_variable_combo.setLayer)
    form.addRow(QLabel(tr("Variable")), dialog.dt_variable_combo)

    dialog.dt_polygon_combo = QgsMapLayerComboBox()
    dialog.dt_polygon_combo.setFilters(QgsMapLayerProxyModel.PolygonLayer)
    dialog.dt_polygon_combo.setAllowEmptyLayer(True)
    form.addRow(QLabel(tr("Polygon")), dialog.dt_polygon_combo)

    dialog.dt_pixel_size = QSpinBox()
    dialog.dt_pixel_size.setMinimum(1)
    dialog.dt_pixel_size.setMaximum(100000)
    dialog.dt_pixel_size.setValue(10)
    form.addRow(QLabel(tr("Pixel size:")), dialog.dt_pixel_size)

    dialog.dt_export_check = QCheckBox(tr("Export Rasters to project folder"))
    dialog.dt_export_check.setChecked(True)
    form.addRow(dialog.dt_export_check)

    left.addWidget(inputs)
    left.addWidget(make_run_button(dialog, "dt_btn_load", tr("Load")))

    diagnostics = QGroupBox(tr("Diagnostics"))
    diag_form = QFormLayout(diagnostics)
    diag_form.setContentsMargins(10, 8, 10, 8)
    dialog.dt_crs_label = QLabel(tr("CRS:"))
    dialog.dt_crs_label.setWordWrap(True)
    diag_form.addRow(dialog.dt_crs_label)
    dialog.dt_moran_label = QLabel("-")
    dialog.dt_moran_label.setWordWrap(True)
    diag_form.addRow(QLabel(tr("Spatial structure")), dialog.dt_moran_label)
    dialog.dt_samples_label = QLabel("—")
    diag_form.addRow(QLabel(tr("Samples:")), dialog.dt_samples_label)
    left.addWidget(diagnostics)
    left.addStretch()

    root.addLayout(left, 1)

    # ---- right column: preview ----------------------------------------------
    preview = QGroupBox(tr("Preview"))
    preview_layout = QVBoxLayout(preview)
    preview_layout.setContentsMargins(8, 8, 8, 8)
    dialog.dt_preview_panel = make_figure_panel(preview)
    preview_layout.addWidget(dialog.dt_preview_panel.container)
    root.addWidget(preview, 2)
