# -*- coding: utf-8 -*-
"""Geostatistics page (prefix ok_) — Ordinary Kriging: semivariogram controls,
model adjust, interpolation preview + validation sub-tab (legacy tabKriging)."""

from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .common import (
    make_cv_group,
    make_figure_panel,
    make_metrics_table,
    make_run_button,
    make_subtabs,
    tr,
)

FIT_METHOD_TOOLTIP = (
    "Automatic keeps the original rule: REML is used only when available and "
    "the dataset has fewer than 100 valid samples; otherwise MoM is used. If "
    "REML is selected manually, it is allowed only for fewer than 500 valid "
    "samples to avoid overloading the system. MoM fits the theoretical "
    "variogram to the experimental semivariogram and shows experimental "
    "points. REML estimates variogram parameters by restricted maximum "
    "likelihood and does not display the experimental semivariogram."
)
MODEL_VALIDATION_TOOLTIP = (
    "View the automatic validation used to compare the Spherical, "
    "Exponential, and Gaussian kriging models."
)


def _param_spin(decimals=4, maximum=1e12):
    spin = QDoubleSpinBox()
    spin.setDecimals(decimals)
    spin.setMinimum(0.0)
    spin.setMaximum(maximum)
    return spin


def setup_geostat_page(dialog, page):
    page.setObjectName("tabKriging")
    root = QVBoxLayout(page)
    root.setContentsMargins(10, 10, 10, 10)

    # ---------------------------- Interpolation sub-tab ----------------------
    interp_tab = QWidget()
    interp_root = QHBoxLayout(interp_tab)
    interp_root.setSpacing(12)

    controls = QVBoxLayout()
    controls.setSpacing(10)

    vario_group = QGroupBox(tr("Semivariogram"))
    vario_form = QFormLayout(vario_group)
    dialog.ok_spin_cutoff = _param_spin(decimals=12)
    vario_form.addRow(QLabel(tr("Maximum distance:")), dialog.ok_spin_cutoff)
    dialog.ok_spin_lag = _param_spin(decimals=12)
    vario_form.addRow(QLabel(tr("Lag (h):")), dialog.ok_spin_lag)
    dialog.ok_fit_method_combo = QComboBox()
    dialog.ok_fit_method_combo.addItems(["Automatic", "MoM", "REML"])
    dialog.ok_fit_method_combo.setToolTip(tr(FIT_METHOD_TOOLTIP))
    vario_form.addRow(QLabel(tr("Fit method:")), dialog.ok_fit_method_combo)
    dialog.ok_fit_label = QLabel("—")
    vario_form.addRow(QLabel(tr("Fit:")), dialog.ok_fit_label)
    dialog.ok_samples_label = QLabel("—")
    vario_form.addRow(QLabel(tr("Samples:")), dialog.ok_samples_label)
    dialog.ok_z_label = QLabel("—")
    vario_form.addRow(QLabel(tr("Z:")), dialog.ok_z_label)
    btn_row = QHBoxLayout()
    dialog.ok_btn_calculate = QPushButton(tr("Calculate…"))
    dialog.ok_btn_reset = QPushButton(tr("Reset…"))
    btn_row.addWidget(dialog.ok_btn_calculate)
    btn_row.addWidget(dialog.ok_btn_reset)
    vario_form.addRow(btn_row)
    controls.addWidget(vario_group)

    model_group = QGroupBox(tr("Model Adjust"))
    model_form = QGridLayout(model_group)
    model_form.addWidget(QLabel(tr("Model:")), 0, 0)
    dialog.ok_model_combo = QComboBox()
    dialog.ok_model_combo.addItems(["Automatic", "Sph", "Exp", "Gau"])
    model_form.addWidget(dialog.ok_model_combo, 0, 1)
    dialog.ok_btn_model_validation = QPushButton(tr("View validation"))
    dialog.ok_btn_model_validation.setToolTip(tr(MODEL_VALIDATION_TOOLTIP))
    model_form.addWidget(dialog.ok_btn_model_validation, 0, 2)
    model_form.addWidget(QLabel(tr("Nugget (Co)")), 1, 0)
    dialog.ok_spin_nugget = _param_spin()
    model_form.addWidget(dialog.ok_spin_nugget, 1, 1, 1, 2)
    model_form.addWidget(QLabel(tr("Partial Sill (C1)")), 2, 0)
    dialog.ok_spin_psill = _param_spin()
    model_form.addWidget(dialog.ok_spin_psill, 2, 1, 1, 2)
    model_form.addWidget(QLabel(tr("Range (a)")), 3, 0)
    dialog.ok_spin_range = _param_spin()
    model_form.addWidget(dialog.ok_spin_range, 3, 1, 1, 2)
    model_form.addWidget(QLabel(tr("Spatial Dependence Index (SDI)")), 4, 0, 1, 2)
    dialog.ok_sdi_label = QLabel("—")
    model_form.addWidget(dialog.ok_sdi_label, 4, 2)
    controls.addWidget(model_group)

    controls.addWidget(make_run_button(dialog, "ok_btn_interpolate", tr("Interpolate…")))
    controls.addStretch()
    interp_root.addLayout(controls, 1)

    canvases = QVBoxLayout()
    dialog.ok_vario_panel = make_figure_panel(interp_tab)
    canvases.addWidget(dialog.ok_vario_panel.container, 1)
    dialog.ok_map_panel = make_figure_panel(interp_tab)
    canvases.addWidget(dialog.ok_map_panel.container, 1)
    interp_root.addLayout(canvases, 2)

    # ------------------------------ Validation sub-tab -----------------------
    val_tab = QWidget()
    val_layout = QVBoxLayout(val_tab)
    metrics_group = QGroupBox(tr("Validation metrics"))
    metrics_layout = QVBoxLayout(metrics_group)
    metrics_layout.addWidget(make_cv_group(dialog, "ok"))
    dialog.ok_metrics_table = make_metrics_table(metrics_group)
    metrics_layout.addWidget(dialog.ok_metrics_table)
    metrics_layout.addWidget(make_run_button(dialog, "ok_btn_cv", tr("Run Cross-Validation")))
    val_layout.addWidget(metrics_group)
    dialog.ok_val_panel = make_figure_panel(val_tab)
    val_layout.addWidget(dialog.ok_val_panel.container, 1)

    subtabs = make_subtabs(dialog, "ok_subtabs", [
        (tr("Interpolation"), interp_tab),
        (tr("Validation"), val_tab),
    ])
    root.addWidget(subtabs)
