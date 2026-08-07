# -*- coding: utf-8 -*-
"""GUI-tier tests: the code-built dialog constructs offscreen with every
promised widget attribute, and the About tab reflects metadata.txt."""

import pytest

pytestmark = pytest.mark.gui

# One dialog.<attr> per interactive widget the controllers rely on.
EXPECTED_ATTRS = [
    # Data (dt_)
    "dt_points_combo", "dt_variable_combo", "dt_polygon_combo", "dt_pixel_size",
    "dt_export_check", "dt_btn_load", "dt_crs_label", "dt_moran_label",
    "dt_samples_label", "dt_preview_panel",
    # Deterministic (det_)
    "det_chk_optimize", "det_rad_manual", "det_spin_power", "det_spin_neighbors",
    "det_chk_tps", "det_btn_interpolate", "det_btn_cv", "det_metrics_table",
    "det_interp_panel", "det_val_panel", "det_cv_auto", "det_cv_loocv",
    "det_cv_kfold", "det_cv_k", "det_subtabs",
    # Geostatistics (ok_)
    "ok_spin_cutoff", "ok_spin_lag", "ok_fit_method_combo", "ok_fit_label",
    "ok_samples_label", "ok_z_label", "ok_btn_calculate", "ok_btn_reset",
    "ok_model_combo", "ok_btn_model_validation", "ok_spin_nugget",
    "ok_spin_psill", "ok_spin_range", "ok_sdi_label", "ok_btn_interpolate",
    "ok_vario_panel", "ok_map_panel", "ok_btn_cv", "ok_metrics_table",
    "ok_val_panel", "ok_subtabs",
    # Machine Learning (ml_ / rk_)
    "ml_subtabs", "ml_cov_layer_combo", "ml_btn_add_cov", "ml_cov_list",
    "ml_btn_remove_cov", "ml_use_xy_check", "ml_btn_correlation", "ml_corr_panel",
    "ml_rf_ntree", "ml_rf_mtry", "ml_rf_nodesize", "ml_rf_grid_search",
    "ml_rf_btn_interpolate", "ml_rf_map_panel", "ml_rf_importance_panel",
    "ml_rf_btn_importance", "ml_rf_btn_cv", "ml_rf_metrics_table", "ml_rf_val_panel",
    "ml_svm_c", "ml_svm_gamma", "ml_svm_epsilon", "ml_svm_grid_search",
    "ml_svm_btn_interpolate", "ml_svm_map_panel", "ml_svm_btn_cv",
    "ml_svm_metrics_table", "ml_svm_val_panel",
    "rk_model_combo", "rk_btn_interpolate", "rk_map_panel", "rk_vario_panel",
    "rk_importance_panel", "rk_btn_importance", "rk_btn_cv", "rk_metrics_table",
    "rk_val_panel",
    # Framework (fw_)
    "fw_subtabs", "fw_n_label", "fw_moran_label", "fw_sdi_label", "fw_cov_label",
    "fw_btn_analyze", "fw_decision_view", "fw_recommendation_label",
    "fw_btn_recommend", "fw_method_list", "fw_btn_compare", "fw_results_table",
    "fw_val_panel", "fw_method_combo", "fw_btn_interpolate", "fw_map_panel",
    "fw_cv_auto", "fw_cv_loocv", "fw_cv_kfold", "fw_cv_k",
]

TAB_TITLES = ["Data", "Deterministic", "Geostatistics", "Machine Learning",
              "Framework", "About"]


@pytest.fixture(scope="module")
def dialog(qgis_app):
    import pathlib

    from bestfitinterpolator.dialog import BestFitInterpolatorDialog

    plugin_dir = str(pathlib.Path(__file__).resolve().parents[2])
    return BestFitInterpolatorDialog(plugin_dir)


def test_tab_titles(dialog):
    titles = [dialog.main_tabs.tabText(i) for i in range(dialog.main_tabs.count())]
    assert titles == TAB_TITLES


@pytest.mark.parametrize("attr", EXPECTED_ATTRS)
def test_widget_attribute_exists(dialog, attr):
    assert hasattr(dialog, attr), f"dialog.{attr} missing after page setup"


def test_about_version_matches_metadata(dialog):
    from qgis.PyQt.QtWidgets import QLabel

    from bestfitinterpolator.metadata_utils import read_plugin_metadata

    version = read_plugin_metadata(dialog.plugin_dir).get("version", "Unknown")
    label = dialog.findChild(QLabel, "lblAboutVersion")
    assert label is not None
    assert version in label.text()


def test_cv_defaults(dialog):
    assert dialog.det_cv_auto.isChecked()
    assert dialog.det_cv_k.value() == 10
    assert dialog.det_spin_power.value() == 2.0
    assert dialog.det_spin_neighbors.value() == 12
