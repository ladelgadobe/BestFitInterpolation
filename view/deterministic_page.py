# -*- coding: utf-8 -*-
"""Deterministic page (prefix det_) — IDW (optimized/manual) + TPS options,
Interpolation and Validation sub-tabs (legacy detSubTabs)."""

from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QSpinBox,
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

IDW_POWER_TOOLTIP = (
    "IDW power controls how fast influence decreases with distance. Higher "
    "values give nearby points more weight; lower values produce smoother results."
)
IDW_NEIGHBORS_TOOLTIP = (
    "Number of nearest sample points used for each IDW prediction. More "
    "neighbors usually smooth the surface; fewer neighbors emphasize local variation."
)
IDW_OPTIMIZE_TOOLTIP = (
    "If checked, n and p will be estimated automatically; manual inputs will be ignored."
)


def setup_deterministic_page(dialog, page):
    page.setObjectName("tabDeterministic")
    root = QHBoxLayout(page)
    root.setContentsMargins(10, 10, 10, 10)
    root.setSpacing(12)

    # ---- options column ------------------------------------------------------
    options = QGroupBox(tr("Options"))
    opt_layout = QVBoxLayout(options)
    opt_layout.setSpacing(10)

    idw_group = QGroupBox(tr("IDW"))
    idw_layout = QFormLayout(idw_group)
    dialog.det_chk_optimize = QCheckBox(tr("Optimize IDW (p, n)"))
    dialog.det_chk_optimize.setToolTip(tr(IDW_OPTIMIZE_TOOLTIP))
    idw_layout.addRow(dialog.det_chk_optimize)
    dialog.det_rad_manual = QRadioButton(tr("Manual parameters"))
    idw_layout.addRow(dialog.det_rad_manual)

    dialog.det_spin_power = QDoubleSpinBox()
    dialog.det_spin_power.setDecimals(2)
    dialog.det_spin_power.setMinimum(0.01)
    dialog.det_spin_power.setMaximum(10.0)
    dialog.det_spin_power.setSingleStep(0.1)
    dialog.det_spin_power.setValue(2.0)
    dialog.det_spin_power.setToolTip(tr(IDW_POWER_TOOLTIP))
    power_label = QLabel(tr("Power (p)"))
    power_label.setToolTip(tr(IDW_POWER_TOOLTIP))
    idw_layout.addRow(power_label, dialog.det_spin_power)

    dialog.det_spin_neighbors = QSpinBox()
    dialog.det_spin_neighbors.setMinimum(1)
    dialog.det_spin_neighbors.setMaximum(200)
    dialog.det_spin_neighbors.setValue(12)
    dialog.det_spin_neighbors.setToolTip(tr(IDW_NEIGHBORS_TOOLTIP))
    neigh_label = QLabel(tr("Neighbors (n)"))
    neigh_label.setToolTip(tr(IDW_NEIGHBORS_TOOLTIP))
    idw_layout.addRow(neigh_label, dialog.det_spin_neighbors)
    opt_layout.addWidget(idw_group)

    tps_group = QGroupBox(tr("TPS"))
    tps_layout = QVBoxLayout(tps_group)
    dialog.det_chk_tps = QCheckBox(tr("Thin plate spline"))
    tps_layout.addWidget(dialog.det_chk_tps)
    opt_layout.addWidget(tps_group)

    opt_layout.addWidget(make_run_button(dialog, "det_btn_interpolate", tr("Interpolate")))
    opt_layout.addStretch()
    root.addWidget(options, 1)

    # ---- sub-tabs ------------------------------------------------------------
    interp_tab = QWidget()
    interp_layout = QVBoxLayout(interp_tab)
    dialog.det_interp_panel = make_figure_panel(interp_tab)
    interp_layout.addWidget(dialog.det_interp_panel.container)

    val_tab = QWidget()
    val_layout = QVBoxLayout(val_tab)
    metrics_group = QGroupBox(tr("Metrics"))
    metrics_layout = QVBoxLayout(metrics_group)
    metrics_layout.addWidget(make_cv_group(dialog, "det"))
    dialog.det_metrics_table = make_metrics_table(metrics_group)
    metrics_layout.addWidget(dialog.det_metrics_table)
    metrics_layout.addWidget(
        make_run_button(dialog, "det_btn_cv", tr("Run Cross-Validation"))
    )
    val_layout.addWidget(metrics_group)
    dialog.det_val_panel = make_figure_panel(val_tab)
    val_layout.addWidget(dialog.det_val_panel.container, 1)

    subtabs = make_subtabs(dialog, "det_subtabs", [
        (tr("Interpolation"), interp_tab),
        (tr("Validation"), val_tab),
    ])
    root.addWidget(subtabs, 2)
