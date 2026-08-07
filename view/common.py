# -*- coding: utf-8 -*-
"""Shared widget factories for the code-built pages.

make_figure_panel is the ONLY place a matplotlib FigureCanvas is constructed
(the legacy code had ~25 ad-hoc construction sites)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from qgis.core import QgsMapLayerProxyModel
from qgis.gui import QgsFieldComboBox, QgsMapLayerComboBox

from .styles import STYLE_RUN_BUTTON


def tr(text):
    return QCoreApplication.translate("BestFitInterpolator", text)


# ------------------------------- figures ------------------------------------

@dataclass
class FigurePanel:
    figure: Figure
    canvas: FigureCanvas
    container: QWidget
    btn_copy: QPushButton = None
    btn_save: QPushButton = None


def make_figure_panel(parent=None, *, figsize=(5, 4), with_buttons=True,
                      min_height=220) -> FigurePanel:
    """Matplotlib canvas in a container widget with optional Copy/Save row.
    Buttons are left unwired — controllers connect them to PlotService."""
    container = QWidget(parent)
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)

    figure = Figure(figsize=figsize, tight_layout=True)
    canvas = FigureCanvas(figure)
    canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    canvas.setMinimumSize(1, max(1, int(min_height)))
    layout.addWidget(canvas, 1)

    btn_copy = btn_save = None
    if with_buttons:
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addStretch()
        btn_copy = QPushButton(tr("Copy"))
        btn_save = QPushButton(tr("Save…"))
        for b in (btn_copy, btn_save):
            b.setMaximumHeight(24)
            row.addWidget(b)
        layout.addLayout(row)

    return FigurePanel(
        figure=figure, canvas=canvas, container=container,
        btn_copy=btn_copy, btn_save=btn_save,
    )


# ------------------------------ params group --------------------------------

@dataclass
class ParamSpec:
    name: str
    label: str
    kind: str                     # "int" | "float" | "choice" | "bool"
    minimum: float = None
    maximum: float = None
    default: object = None
    step: float = None
    decimals: int = None
    tooltip: str = ""
    choices: tuple = ()


def make_params_group(title, params, dialog, prefix) -> QGroupBox:
    """QFormLayout of spin/combo/check widgets attached as
    dialog.<prefix>_<name>."""
    group = QGroupBox(title)
    form = QFormLayout(group)
    form.setContentsMargins(10, 8, 10, 8)
    for spec in params:
        widget = _make_param_widget(spec)
        setattr(dialog, f"{prefix}_{spec.name}", widget)
        if spec.kind == "bool":
            form.addRow(widget)
        else:
            form.addRow(QLabel(spec.label), widget)
    return group


def _make_param_widget(spec: ParamSpec):
    if spec.kind == "int":
        w = QSpinBox()
        if spec.minimum is not None:
            w.setMinimum(int(spec.minimum))
        if spec.maximum is not None:
            w.setMaximum(int(spec.maximum))
        if spec.step is not None:
            w.setSingleStep(int(spec.step))
        if spec.default is not None:
            w.setValue(int(spec.default))
    elif spec.kind == "float":
        w = QDoubleSpinBox()
        if spec.decimals is not None:
            w.setDecimals(int(spec.decimals))
        if spec.minimum is not None:
            w.setMinimum(float(spec.minimum))
        if spec.maximum is not None:
            w.setMaximum(float(spec.maximum))
        if spec.step is not None:
            w.setSingleStep(float(spec.step))
        if spec.default is not None:
            w.setValue(float(spec.default))
    elif spec.kind == "choice":
        w = QComboBox()
        w.addItems([str(c) for c in spec.choices])
        if spec.default is not None:
            idx = w.findText(str(spec.default))
            if idx >= 0:
                w.setCurrentIndex(idx)
    elif spec.kind == "bool":
        w = QCheckBox(spec.label)
        w.setChecked(bool(spec.default))
    else:
        raise ValueError(f"Unknown ParamSpec kind: {spec.kind}")
    if spec.tooltip:
        w.setToolTip(spec.tooltip)
    return w


# ------------------------------ metrics table -------------------------------

METRIC_ROWS = ("RMSE", "RMSE %", "MAE", "Pearson r", "R²", "LCCC")
_METRIC_ATTRS = ("rmse", "rmse_pct", "mae", "pearson_r", "r2", "lccc")


def make_metrics_table(parent=None, *, rows=METRIC_ROWS) -> QTableWidget:
    """2-column Metric/Value table used by every validation sub-tab."""
    table = QTableWidget(len(rows), 2, parent)
    table.setHorizontalHeaderLabels([tr("Metric"), tr("Value")])
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.setSelectionMode(QTableWidget.NoSelection)
    for i, name in enumerate(rows):
        table.setItem(i, 0, QTableWidgetItem(name))
        table.setItem(i, 1, QTableWidgetItem("—"))
    table.horizontalHeader().setStretchLastSection(True)
    table.setMaximumHeight(24 * (len(rows) + 1) + 8)
    return table


def fill_metrics_table(table: QTableWidget, metrics) -> None:
    """Populate a make_metrics_table with a core.types.Metrics."""
    import numpy as np

    for i, attr in enumerate(_METRIC_ATTRS):
        value = getattr(metrics, attr, float("nan"))
        if value is None or not np.isfinite(value):
            text = "—"
        elif attr == "rmse_pct":
            text = f"{value:.2f}%"
        else:
            text = f"{value:.3f}"
        table.setItem(i, 1, QTableWidgetItem(text))


# ---------------------------- layer/field row -------------------------------

def make_layer_field_row(dialog, prefix, *, layer_filter=None, with_field=True) -> QWidget:
    """dialog.<prefix>_layer_combo (+ dialog.<prefix>_field_combo bound to it)."""
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    layer_combo = QgsMapLayerComboBox()
    layer_combo.setFilters(
        QgsMapLayerProxyModel.PointLayer if layer_filter is None else layer_filter
    )
    layer_combo.setAllowEmptyLayer(True)
    setattr(dialog, f"{prefix}_layer_combo", layer_combo)
    layout.addWidget(layer_combo, 2)

    if with_field:
        field_combo = QgsFieldComboBox()
        layer_combo.layerChanged.connect(field_combo.setLayer)  # purely visual pairing
        setattr(dialog, f"{prefix}_field_combo", field_combo)
        layout.addWidget(field_combo, 1)

    return row


# ------------------------------ small helpers -------------------------------

def make_run_button(dialog, attr, text) -> QPushButton:
    btn = QPushButton(text)
    btn.setStyleSheet(STYLE_RUN_BUTTON)
    btn.setMinimumHeight(32)
    setattr(dialog, attr, btn)
    return btn


def make_info_label(text) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    return label


def make_subtabs(dialog, attr, pages) -> QTabWidget:
    """pages: [(title, QWidget)]; attached as dialog.<attr>."""
    tabs = QTabWidget()
    for title, widget in pages:
        tabs.addTab(widget, title)
    setattr(dialog, attr, tabs)
    return tabs


def make_cv_group(dialog, prefix, *, title=None) -> QGroupBox:
    """The Auto / LOOCV / K-Fold cross-validation option group repeated on
    every validation sub-tab. Attaches dialog.<prefix>_cv_auto/_cv_loocv/
    _cv_kfold/_cv_k."""
    from qgis.PyQt.QtWidgets import QRadioButton

    group = QGroupBox(title or tr("Cross-validation"))
    layout = QHBoxLayout(group)
    layout.setContentsMargins(10, 6, 10, 6)
    layout.setSpacing(10)

    auto = QRadioButton(tr("Auto"))
    auto.setChecked(True)
    auto.setToolTip(tr(
        "Automatic uses LOOCV for n <= 100 and changes to K-Fold from "
        "n = 101 (10 folds through n = 1000; 5 folds above 1000)."
    ))
    loocv = QRadioButton(tr("Leave-One-Out (LOOCV)"))
    kfold = QRadioButton(tr("K-Fold"))
    spin_k = QSpinBox()
    spin_k.setMinimum(2)
    spin_k.setMaximum(100)
    spin_k.setValue(10)
    spin_k.setEnabled(False)
    kfold.toggled.connect(spin_k.setEnabled)  # purely visual pairing

    layout.addWidget(auto)
    layout.addWidget(loocv)
    layout.addWidget(kfold)
    layout.addWidget(QLabel("k:"))
    layout.addWidget(spin_k)
    layout.addStretch()

    setattr(dialog, f"{prefix}_cv_auto", auto)
    setattr(dialog, f"{prefix}_cv_loocv", loocv)
    setattr(dialog, f"{prefix}_cv_kfold", kfold)
    setattr(dialog, f"{prefix}_cv_k", spin_k)
    return group


def read_cv_plan(dialog, prefix, n_samples):
    """Widget state of a make_cv_group -> CVPlan."""
    from ..core.types import CVPlan

    if getattr(dialog, f"{prefix}_cv_loocv").isChecked():
        return CVPlan(mode="loocv")
    if getattr(dialog, f"{prefix}_cv_kfold").isChecked():
        return CVPlan(mode="kfold", folds=int(getattr(dialog, f"{prefix}_cv_k").value()))
    return CVPlan.automatic(int(n_samples))


def info_icon_button(tooltip_html, plugin_dir) -> QToolButton:
    """The little info.png tool button used across the legacy UI."""
    btn = QToolButton()
    icon_path = os.path.join(plugin_dir, "info.png")
    if os.path.isfile(icon_path):
        btn.setIcon(QIcon(icon_path))
    else:
        btn.setText("?")
    btn.setAutoRaise(True)
    btn.setToolTip(tooltip_html)
    btn.setCursor(Qt.WhatsThisCursor)
    return btn
