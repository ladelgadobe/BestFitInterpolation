# -*- coding: utf-8 -*-
"""Machine Learning page (prefix ml_; Regression Kriging widgets rk_) —
Covariables / Random Forest / SVM / Kriging (RK) sub-tabs (legacy mlSubTabs)."""

from __future__ import annotations

from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from qgis.core import QgsMapLayerProxyModel
from qgis.gui import QgsMapLayerComboBox

from .common import (
    make_cv_group,
    make_figure_panel,
    make_info_label,
    make_metrics_table,
    make_run_button,
    make_subtabs,
    tr,
)

USE_XY_TOOLTIP = (
    "Include the point x and y coordinates as predictor features in addition "
    "to the loaded covariate rasters."
)
RF_GRID_TOOLTIP = (
    "Search several candidate values for ntree, mtry and nodesize over the "
    "ranges below (random search) and keep the best combination found. "
    "Manual values are ignored while enabled."
)
SVM_GRID_TOOLTIP = (
    "Search several candidate values for C, gamma and epsilon and keep the "
    "best combination found."
)
SVM_C_TOOLTIP = (
    "Penalty for prediction errors in SVR. Higher values fit the training "
    "data more strictly; lower values produce smoother models."
)
SVM_GAMMA_TOOLTIP = (
    "RBF kernel influence radius. Higher values create more local and complex "
    "responses; lower values produce smoother responses."
)
SVM_EPSILON_TOOLTIP = (
    "Insensitive margin around the regression function. Smaller values fit "
    "the data more tightly; larger values tolerate more error."
)
RK_NOTE = (
    "Regression Kriging uses the Random Forest settings from the Random "
    "Forest sub-tab for the trend model, then kriges the RF residuals."
)


def _int_spin(minimum, maximum, value, *, tooltip=""):
    spin = QSpinBox()
    spin.setMinimum(int(minimum))
    spin.setMaximum(int(maximum))
    spin.setValue(int(value))
    if tooltip:
        spin.setToolTip(tr(tooltip))
    return spin


def _dbl_spin(minimum, maximum, value, *, step=0.1, decimals=4, tooltip=""):
    spin = QDoubleSpinBox()
    spin.setDecimals(int(decimals))
    spin.setMinimum(float(minimum))
    spin.setMaximum(float(maximum))
    spin.setSingleStep(float(step))
    spin.setValue(float(value))
    if tooltip:
        spin.setToolTip(tr(tooltip))
    return spin


def setup_ml_page(dialog, page):
    page.setObjectName("tabMachineLearning")
    root = QVBoxLayout(page)
    root.setContentsMargins(10, 10, 10, 10)

    subtabs = make_subtabs(dialog, "ml_subtabs", [
        (tr("Covariables"), _build_covariables_tab(dialog)),
        (tr("Random Forest"), _build_rf_tab(dialog)),
        (tr("SVM"), _build_svm_tab(dialog)),
        (tr("Kriging"), _build_rk_tab(dialog)),
    ])
    root.addWidget(subtabs)


# ------------------------------ Covariables ---------------------------------

def _build_covariables_tab(dialog):
    tab = QWidget()
    root = QHBoxLayout(tab)
    root.setSpacing(12)

    controls = QVBoxLayout()
    controls.setSpacing(10)

    rasters_group = QGroupBox(tr("Covariate rasters"))
    rasters_layout = QVBoxLayout(rasters_group)
    raster_row = QHBoxLayout()
    raster_row.addWidget(QLabel(tr("Raster:")))
    dialog.ml_cov_layer_combo = QgsMapLayerComboBox()
    dialog.ml_cov_layer_combo.setFilters(QgsMapLayerProxyModel.RasterLayer)
    dialog.ml_cov_layer_combo.setAllowEmptyLayer(True)
    raster_row.addWidget(dialog.ml_cov_layer_combo, 1)
    dialog.ml_btn_add_cov = QPushButton(tr("Add covariate"))
    raster_row.addWidget(dialog.ml_btn_add_cov)
    rasters_layout.addLayout(raster_row)
    controls.addWidget(rasters_group)

    loaded_group = QGroupBox(tr("Covariates preprocessing"))
    loaded_layout = QVBoxLayout(loaded_group)
    loaded_layout.addWidget(QLabel(tr("Loaded covariates:")))
    dialog.ml_cov_list = QListWidget()
    dialog.ml_cov_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
    loaded_layout.addWidget(dialog.ml_cov_list, 1)
    dialog.ml_btn_remove_cov = QPushButton(tr("Remove selected"))
    loaded_layout.addWidget(dialog.ml_btn_remove_cov)
    controls.addWidget(loaded_group, 1)

    dialog.ml_use_xy_check = QCheckBox(tr("Use x, y coordinates as predictors"))
    dialog.ml_use_xy_check.setChecked(True)
    dialog.ml_use_xy_check.setToolTip(tr(USE_XY_TOOLTIP))
    controls.addWidget(dialog.ml_use_xy_check)

    controls.addWidget(make_run_button(
        dialog, "ml_btn_correlation", tr("Compute correlations")
    ))
    controls.addStretch()
    root.addLayout(controls, 1)

    corr_column = QVBoxLayout()
    corr_column.addWidget(QLabel(tr("Correlation Matrix")))
    dialog.ml_corr_panel = make_figure_panel(tab)
    corr_column.addWidget(dialog.ml_corr_panel.container, 1)
    root.addLayout(corr_column, 2)
    return tab


# ------------------------------ Random Forest -------------------------------

def _rf_params_group(dialog):
    group = QGroupBox(tr("Random Forest parameters"))
    grid = QGridLayout(group)
    grid.setContentsMargins(10, 8, 10, 8)
    headers = (
        tr("Parameter"), tr("Manual/Selected"),
        tr("Grid min"), tr("Grid max"), tr("Step"),
    )
    for col, text in enumerate(headers):
        grid.addWidget(QLabel(text), 0, col)

    dialog.ml_rf_grid_search = QCheckBox(tr("Optimize hyperparameters (random search)"))
    dialog.ml_rf_grid_search.setToolTip(tr(RF_GRID_TOOLTIP))

    rows = (
        ("ntree", tr("Number of trees (ntree)"), (500, 1, 10000), (100, 1000, 100)),
        ("mtry", tr("Number of variables at each split (mtry)"), (2, 1, 100), (1, 6, 1)),
        ("nodesize", tr("Minimum node size (nodesize)"), (5, 1, 100), (1, 10, 2)),
    )
    for r, (name, label, (value, lo, hi), grid_defaults) in enumerate(rows, start=1):
        grid.addWidget(QLabel(label), r, 0)
        manual = _int_spin(lo, hi, value)
        setattr(dialog, f"ml_rf_{name}", manual)
        grid.addWidget(manual, r, 1)
        for col, (suffix, default) in enumerate(
            zip(("min", "max", "step"), grid_defaults), start=2
        ):
            spin = _int_spin(1, 100000, default)
            spin.setEnabled(False)
            # purely visual pairing
            dialog.ml_rf_grid_search.toggled.connect(spin.setEnabled)
            setattr(dialog, f"ml_rf_grid_{name}_{suffix}", spin)
            grid.addWidget(spin, r, col)

    grid.addWidget(dialog.ml_rf_grid_search, len(rows) + 1, 0, 1, 5)
    return group


def _build_rf_tab(dialog):
    tab = QWidget()
    root = QVBoxLayout(tab)

    interp_tab = QWidget()
    interp_root = QHBoxLayout(interp_tab)
    interp_root.setSpacing(12)

    controls = QVBoxLayout()
    controls.setSpacing(10)
    controls.addWidget(_rf_params_group(dialog))
    controls.addWidget(make_run_button(
        dialog, "ml_rf_btn_interpolate", tr("Run Random Forest interpolation")
    ))
    controls.addStretch()
    interp_root.addLayout(controls, 1)

    panels = QVBoxLayout()
    map_group = QGroupBox(tr("RF interpolation map"))
    map_layout = QVBoxLayout(map_group)
    dialog.ml_rf_map_panel = make_figure_panel(map_group)
    map_layout.addWidget(dialog.ml_rf_map_panel.container)
    panels.addWidget(map_group, 1)

    imp_group = QGroupBox(tr("Variable importance"))
    imp_layout = QVBoxLayout(imp_group)
    dialog.ml_rf_importance_panel = make_figure_panel(imp_group)
    imp_layout.addWidget(dialog.ml_rf_importance_panel.container)
    dialog.ml_rf_btn_importance = QPushButton(tr("Variable importance"))
    imp_layout.addWidget(dialog.ml_rf_btn_importance)
    panels.addWidget(imp_group, 1)
    interp_root.addLayout(panels, 2)

    val_tab = QWidget()
    val_layout = QVBoxLayout(val_tab)
    metrics_group = QGroupBox(tr("Validation metrics"))
    metrics_layout = QVBoxLayout(metrics_group)
    metrics_layout.addWidget(make_cv_group(dialog, "ml_rf"))
    dialog.ml_rf_metrics_table = make_metrics_table(metrics_group)
    metrics_layout.addWidget(dialog.ml_rf_metrics_table)
    metrics_layout.addWidget(make_run_button(
        dialog, "ml_rf_btn_cv", tr("Run Cross-Validation")
    ))
    val_layout.addWidget(metrics_group)
    dialog.ml_rf_val_panel = make_figure_panel(val_tab)
    val_layout.addWidget(dialog.ml_rf_val_panel.container, 1)

    subtabs = make_subtabs(dialog, "ml_rf_subtabs", [
        (tr("Interpolation"), interp_tab),
        (tr("Validation"), val_tab),
    ])
    root.addWidget(subtabs)
    return tab


# ----------------------------------- SVM ------------------------------------

def _svm_params_group(dialog):
    group = QGroupBox(tr("SVM parameters"))
    layout = QVBoxLayout(group)
    layout.setSpacing(8)

    manual_group = QGroupBox(tr("Manual"))
    manual_form = QFormLayout(manual_group)
    dialog.ml_svm_c = _dbl_spin(
        0.00001, 100000.0, 1.0, step=0.1, decimals=5, tooltip=SVM_C_TOOLTIP
    )
    manual_form.addRow(QLabel(tr("C")), dialog.ml_svm_c)
    dialog.ml_svm_gamma = _dbl_spin(
        0.00001, 100000.0, 0.1, step=0.01, decimals=6, tooltip=SVM_GAMMA_TOOLTIP
    )
    manual_form.addRow(QLabel(tr("gamma")), dialog.ml_svm_gamma)
    dialog.ml_svm_epsilon = _dbl_spin(
        0.0, 1000.0, 0.1, step=0.01, decimals=4, tooltip=SVM_EPSILON_TOOLTIP
    )
    manual_form.addRow(QLabel(tr("epsilon")), dialog.ml_svm_epsilon)
    layout.addWidget(manual_group)

    dialog.ml_svm_grid_search = QCheckBox(tr("Grid search"))
    dialog.ml_svm_grid_search.setToolTip(tr(SVM_GRID_TOOLTIP))
    layout.addWidget(dialog.ml_svm_grid_search)

    grid_group = QGroupBox(tr("Grid search"))
    grid = QGridLayout(grid_group)
    headers = (tr("Parameter"), tr("Min"), tr("Max"), tr("Step"))
    for col, text in enumerate(headers):
        grid.addWidget(QLabel(text), 0, col)
    rows = (
        ("c", tr("C (log2)"), (-30.0, 30.0), (-2.0, 6.0, 2.0), 2),
        ("gamma", tr("gamma (log2)"), (-30.0, 30.0), (-6.0, 2.0, 2.0), 2),
        ("epsilon", tr("epsilon"), (0.0, 10.0), (0.0, 0.4, 0.2), 4),
    )
    for r, (name, label, (lo, hi), defaults, decimals) in enumerate(rows, start=1):
        grid.addWidget(QLabel(label), r, 0)
        for col, (suffix, default) in enumerate(
            zip(("min", "max", "step"), defaults), start=1
        ):
            # Step spins must stay positive; min/max follow the row range.
            minimum = 0.01 if suffix == "step" else lo
            spin = _dbl_spin(minimum, hi, default, step=0.1, decimals=decimals)
            setattr(dialog, f"ml_svm_{name}_{suffix}", spin)
            grid.addWidget(spin, r, col)
    grid_group.setEnabled(False)
    # purely visual pairing
    dialog.ml_svm_grid_search.toggled.connect(grid_group.setEnabled)
    layout.addWidget(grid_group)
    return group


def _build_svm_tab(dialog):
    tab = QWidget()
    root = QVBoxLayout(tab)

    interp_tab = QWidget()
    interp_root = QHBoxLayout(interp_tab)
    interp_root.setSpacing(12)

    controls = QVBoxLayout()
    controls.setSpacing(10)
    controls.addWidget(_svm_params_group(dialog))
    controls.addWidget(make_run_button(dialog, "ml_svm_btn_interpolate", tr("Run SVM")))
    controls.addStretch()
    interp_root.addLayout(controls, 1)

    map_group = QGroupBox(tr("SVM interpolation"))
    map_layout = QVBoxLayout(map_group)
    dialog.ml_svm_map_panel = make_figure_panel(map_group)
    map_layout.addWidget(dialog.ml_svm_map_panel.container)
    interp_root.addWidget(map_group, 2)

    val_tab = QWidget()
    val_layout = QVBoxLayout(val_tab)
    metrics_group = QGroupBox(tr("Metrics"))
    metrics_layout = QVBoxLayout(metrics_group)
    metrics_layout.addWidget(make_cv_group(dialog, "ml_svm"))
    dialog.ml_svm_metrics_table = make_metrics_table(metrics_group)
    metrics_layout.addWidget(dialog.ml_svm_metrics_table)
    metrics_layout.addWidget(make_run_button(
        dialog, "ml_svm_btn_cv", tr("Run cross-validation")
    ))
    val_layout.addWidget(metrics_group)
    dialog.ml_svm_val_panel = make_figure_panel(val_tab)
    val_layout.addWidget(dialog.ml_svm_val_panel.container, 1)

    subtabs = make_subtabs(dialog, "ml_svm_subtabs", [
        (tr("Interpolation"), interp_tab),
        (tr("Validation"), val_tab),
    ])
    root.addWidget(subtabs)
    return tab


# ------------------------------ Kriging (RK) --------------------------------

def _build_rk_tab(dialog):
    tab = QWidget()
    root = QVBoxLayout(tab)

    interp_tab = QWidget()
    interp_root = QHBoxLayout(interp_tab)
    interp_root.setSpacing(12)

    controls = QVBoxLayout()
    controls.setSpacing(10)
    params_group = QGroupBox(tr("Regression Kriging parameters"))
    params_layout = QVBoxLayout(params_group)
    params_layout.addWidget(make_info_label(tr(RK_NOTE)))
    model_row = QHBoxLayout()
    model_row.addWidget(QLabel(tr("Residual variogram model")))
    dialog.rk_model_combo = QComboBox()
    dialog.rk_model_combo.addItems(
        [tr("Automatic"), tr("Spherical"), tr("Exponential"), tr("Gaussian")]
    )
    model_row.addWidget(dialog.rk_model_combo, 1)
    params_layout.addLayout(model_row)
    controls.addWidget(params_group)
    controls.addWidget(make_run_button(dialog, "rk_btn_interpolate", tr("Interpolate RK")))
    controls.addStretch()
    interp_root.addLayout(controls, 1)

    panels = QVBoxLayout()
    map_group = QGroupBox(tr("Regression Kriging map"))
    map_layout = QVBoxLayout(map_group)
    dialog.rk_map_panel = make_figure_panel(map_group)
    map_layout.addWidget(dialog.rk_map_panel.container)
    panels.addWidget(map_group, 1)

    diag_group = QGroupBox(tr("Diagnostics"))
    diag_layout = QVBoxLayout(diag_group)
    vario_tab = QWidget()
    vario_layout = QVBoxLayout(vario_tab)
    dialog.rk_vario_panel = make_figure_panel(vario_tab)
    vario_layout.addWidget(dialog.rk_vario_panel.container)
    imp_tab = QWidget()
    imp_layout = QVBoxLayout(imp_tab)
    dialog.rk_importance_panel = make_figure_panel(imp_tab)
    imp_layout.addWidget(dialog.rk_importance_panel.container)
    dialog.rk_btn_importance = QPushButton(tr("Variable importance"))
    imp_layout.addWidget(dialog.rk_btn_importance)
    diag_subtabs = QTabWidget()
    diag_subtabs.addTab(vario_tab, tr("Residual variogram"))
    diag_subtabs.addTab(imp_tab, tr("Variable importance"))
    diag_layout.addWidget(diag_subtabs)
    panels.addWidget(diag_group, 1)
    interp_root.addLayout(panels, 2)

    val_tab = QWidget()
    val_layout = QVBoxLayout(val_tab)
    metrics_group = QGroupBox(tr("Metrics"))
    metrics_layout = QVBoxLayout(metrics_group)
    metrics_layout.addWidget(make_cv_group(dialog, "rk"))
    dialog.rk_metrics_table = make_metrics_table(metrics_group)
    metrics_layout.addWidget(dialog.rk_metrics_table)
    metrics_layout.addWidget(make_run_button(
        dialog, "rk_btn_cv", tr("Run RK cross-validation")
    ))
    val_layout.addWidget(metrics_group)
    dialog.rk_val_panel = make_figure_panel(val_tab)
    val_layout.addWidget(dialog.rk_val_panel.container, 1)

    subtabs = make_subtabs(dialog, "rk_subtabs", [
        (tr("Interpolation"), interp_tab),
        (tr("Validation"), val_tab),
    ])
    root.addWidget(subtabs)
    return tab
