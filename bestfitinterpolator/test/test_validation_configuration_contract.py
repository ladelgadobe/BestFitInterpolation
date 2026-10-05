import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "BestFitInterpolator.py").exists():
    ROOT = ROOT / "bestfitinterpolator"


def function_source(path, name):
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(source, node)
    raise AssertionError(f"Function {name} not found in {path.name}")


def test_validation_uses_saved_interpolation_configuration():
    main = ROOT / "BestFitInterpolator.py"
    ml = ROOT / "machine_learning_tab.py"
    rk = ROOT / "RF_RegressionKriging.py"

    det_cv = function_source(main, "run_cross_validation")
    ok_cv = function_source(main, "run_ok_cv")
    ok_reml_cv = function_source(main, "run_ok_cv_reml")
    rf_cv = function_source(ml, "_on_run_rf_cross_validation")
    svm_cv = function_source(ml, "_on_run_svm_cross_validation")
    rk_cv = function_source(rk, "_on_run_rk_cv_clicked")

    assert "training_data" in det_cv
    assert "cmbPointsLayer" not in det_cv
    assert "cmbVariable" not in det_cv

    assert "_get_last_ok_interpolation_for_validation" in ok_cv
    assert "_read_ok_params" not in ok_cv
    assert "cmbPointsLayer" not in ok_cv
    assert "reml_fit" in ok_reml_cv
    assert "fit_ok_reml_interface" not in ok_reml_cv

    forbidden_calls = (
        (rf_cv, ("_build_points_dataframe_for_rf", "_get_rf_manual_params", "_get_rf_grid_params", "_is_rf_using_grid_search")),
        (svm_cv, ("_build_points_dataframe_for_rf", "_get_svm_manual_params", "_get_svm_grid_params", "_is_svm_using_grid_search")),
        (rk_cv, ("_prepare_training_data", "_get_manual_params", "_get_grid_params", "_is_using_grid_search", "_fit_variogram_candidates")),
    )
    for text, forbidden in forbidden_calls:
        for name in forbidden:
            assert name not in text

    assert "_last_rf_interpolation_config" in rf_cv
    assert "resolved_params" in rf_cv
    assert "_last_svm_interpolation_config" in svm_cv
    assert "resolved_params" in svm_cv
    assert "_last_interpolation_config" in rk_cv
    assert "fixed_variogram_fit" in rk_cv

    ui = (ROOT / "BestFitInterpolator_dialog_base.ui").read_text(encoding="utf-8-sig")
    assert "btnFrameworkRunInterpolation" in ui
    assert "Run interpolation" in ui


def test_manual_ml_interpolation_is_marked_complete_only_after_raster_export():
    ml = ROOT / "machine_learning_tab.py"
    rk = ROOT / "RF_RegressionKriging.py"

    rf_run = function_source(ml, "_on_run_rf_interpolation")
    svm_run = function_source(ml, "_on_run_svm_interpolation")
    rk_run = function_source(rk, "_run_rk_prediction")

    assert rf_run.index("_write_rf_raster_from_grid_df") < rf_run.index("self._last_rf_interpolation_config = rf_config")
    assert svm_run.index("_write_svm_raster_from_grid_df") < svm_run.index("self._last_svm_interpolation_config = svm_config")
    assert rk_run.index("self.raster_writer") < rk_run.index("self._last_interpolation_config = interpolation_config")


def test_ml_raster_writer_streams_by_blocks_for_large_grids():
    ml = ROOT / "machine_learning_tab.py"
    writer = function_source(ml, "_write_prediction_raster_from_grid_df")
    rf_writer = function_source(ml, "_write_rf_raster_from_grid_df")
    svm_writer = function_source(ml, "_write_svm_raster_from_grid_df")

    assert "pred_column=None" in writer
    assert "value_col = str(pred_column or f\"{target_column}_pred\")" in writer
    assert "\"__flat_index\" in grid_df.columns" in writer
    assert "for row_start in range(0, int(n_rows), block_rows)" in writer
    assert "band.WriteArray(block, 0, row_start)" in writer
    assert "BIGTIFF=IF_SAFER" in writer
    assert "np.full((n_rows, n_cols)" not in writer
    assert "_write_prediction_raster_from_grid_df" in rf_writer
    assert "_write_prediction_raster_from_grid_df" in svm_writer


def test_large_ml_previews_are_lightweight():
    ml = ROOT / "machine_learning_tab.py"
    source = ml.read_text(encoding="utf-8-sig")
    rf_preview = function_source(ml, "_draw_rf_interpolation_preview")
    svm_preview = function_source(ml, "_draw_svm_interpolation_preview")

    assert "def _draw_lightweight_grid_preview" in source
    assert "def _store_grid_preview_payload" in source
    assert "_grid_cell_count(grid_meta) > 2000000" in rf_preview
    assert "_grid_cell_count(grid_meta) > 2000000" in svm_preview
    assert "_draw_lightweight_grid_preview" in rf_preview
    assert "_draw_lightweight_grid_preview" in svm_preview


def test_ml_and_rk_keep_flat_grid_index_through_prediction():
    ml = ROOT / "machine_learning_tab.py"
    rf = ROOT / "RF_Interpolation.py"
    svm = ROOT / "SVM_Interpolation.py"
    rk = ROOT / "RF_RegressionKriging.py"
    main = ROOT / "BestFitInterpolator.py"

    grid_builder = function_source(ml, "_build_grid_dataframe_for_rf")
    rf_backend = function_source(rf, "rf_interpolation")
    svm_prepare = function_source(svm, "_prepare_feature_matrices")
    svm_backend = function_source(svm, "svm_interpolation")
    rk_run = function_source(rk, "_run_rk_prediction")
    rk_grid_callback = function_source(main, "_build_rk_grid_callback")
    rk_writer_callback = function_source(main, "_write_rk_raster_callback")

    assert "__flat_index" in grid_builder
    assert "__grid_row" in grid_builder
    assert "__grid_col" in grid_builder
    assert "local_flat + row_start * n_cols" in grid_builder
    assert "\"__flat_index\" in merged.columns" in rf_backend
    assert "\"__flat_index\", \"__grid_row\", \"__grid_col\"" in svm_prepare
    assert "if col in grid_df.columns" in svm_prepare
    assert "\"__flat_index\" in grid_df.columns" in svm_backend
    assert "\"__flat_index\" in merged.columns" in rk_run
    assert "context_name=\"Regression Kriging\"" in rk_grid_callback
    assert "pred_column=pred_column" in rk_writer_callback


def test_dense_geo_model_selection_uses_spatial_holdout_with_full_metrics():
    evaluator=(ROOT/"semivariogram_engine.py").read_text(encoding="utf-8")
    assert "representative_sample_indices" in evaluator and '"spatial_holdout"' in evaluator
    assert "validation_n" in evaluator and "_validation_metrics" in evaluator
    for file_name in ("ok_r_integration_MoM.py","ok_r_integration_reml.py"):
        assert "SemivariogramEngine" in function_source(ROOT/file_name,"_evaluate_model_cv")
        assert "_evaluate_model_variogram_fit" not in function_source(ROOT/file_name,"_choose_best_model_by_validation")


def test_geostat_model_validation_dialog_recomputes_current_data_and_shows_metrics_only():
    advanced=(ROOT/"semivariogram_dialog.py").read_text(encoding="utf-8")
    assert "self.arrays()" in advanced and "submit(self" in advanced
    assert '"RMSE"' in advanced and '"Pearson"' in advanced and '"LCCC"' in advanced
    for file_name in ("ok_r_integration_MoM.py","ok_r_integration_reml.py"):
        dialog=function_source(ROOT/file_name,"_show_model_validation_dialog")
        assert "_ensure_inputs_from_ui" in dialog and "show_advanced_settings(self,validate=True)" in dialog


def test_geostat_semivariogram_lag_count_ui_preserves_lag_width_math():
    for file_name in ("ok_r_integration_MoM.py", "ok_r_integration_reml.py"):
        source = (ROOT / file_name).read_text(encoding="utf-8-sig")
        ensure = function_source(ROOT / file_name, "_ensure_lag_mode_controls")
        apply_count = function_source(ROOT / file_name, "_apply_lag_count_to_width")
        resolve = function_source(ROOT / file_name, "_lag_width_from_controls")
        on_tab = function_source(ROOT / file_name, "_on_tab_changed")

        assert "cmbOKLagMode" in ensure
        assert "spinOKLagCount" in ensure
        assert "[\"Lag distance\", \"Number of lags\"]" in ensure
        assert "self._programmatic_variogram_update = True" in ensure
        assert "cutoff_val / float(max(1, self._lag_count_value()))" in apply_count
        assert "self._safe_lag_width" in resolve
        assert "_ensure_inputs_from_ui" in on_tab
        assert "_ensure_variogram_ready" in on_tab
        assert "_field_exists_in_layer" in source
        assert "currentData" in source


def test_matplotlib_backend_compatibility_uses_qt_fallback():
    compat = (ROOT / "mpl_compat.py").read_text(encoding="utf-8-sig")
    assert "backend_qtagg" in compat
    assert "backend_qt5agg" in compat
    for file_name in (
        "BestFitInterpolator.py",
        "machine_learning_tab.py",
        "RF_RegressionKriging.py",
        "ok_r_integration_MoM.py",
        "ok_r_integration_reml.py",
        "framework_tab.py",
        "framework_sdi_dialog.py",
    ):
        source = (ROOT / file_name).read_text(encoding="utf-8-sig")
        assert "mpl_compat" in source
        assert "matplotlib.backends.backend_qtagg" not in source


def test_data_profile_info_and_map_comparison_tab_are_present():
    profile=function_source(ROOT/"BestFitInterpolator.py","_ensure_data_profile_info_button")
    assert "Data profile classification" in profile
    framework=(ROOT/"framework_tab.py").read_text(encoding="utf-8")
    assert "MapComparisonWidget" in framework
    comparison=(ROOT/"map_comparison_ui.py").read_text(encoding="utf-8")
    assert "validated_methods" in comparison and "interpolation_outputs" in comparison
    assert "Use same palette" in comparison and "Use same value range" in comparison
    assert "compare_rasters" in comparison and "Include this comparison in report" in comparison


def test_framework_massive_validation_uses_holdout_without_replacing_data():
    framework = ROOT / "framework_tab.py"
    runtime_data = function_source(framework, "_framework_validation_runtime_data")
    folds = function_source(framework, "_automatic_fold_indices")
    table = function_source(framework, "_populate_validation_table")

    assert "\"massive_spatial_holdout\"" in runtime_data
    assert "runtime_data[\"x\"] =" not in runtime_data
    assert "runtime_data[\"y\"] =" not in runtime_data
    assert "runtime_data[\"z\"] =" not in runtime_data
    assert "FRAMEWORK_VALIDATION_SUBSET_THRESHOLD" in folds
    assert "representative_sample_indices" in folds
    assert "\"Strategy\"" not in table
    assert "validation_n" not in table


def test_framework_sdi_dialog_does_not_show_model_validation_button():
    sdi = ROOT / "framework_sdi_dialog.py"
    source = sdi.read_text(encoding="utf-8-sig")
    build_ui = function_source(sdi, "_build_ui")

    assert "self.btn_model_validation = None" in build_ui
    assert "View validation" not in build_ui
    assert "model_layout.addWidget(self.btn_model_validation)" not in build_ui
    assert "self.btn_model_validation.clicked.connect" not in source


def test_framework_sdi_dialog_uses_framework_state_dataset():
    sdi = ROOT / "framework_sdi_dialog.py"
    framework = ROOT / "framework_tab.py"

    init = function_source(sdi, "__init__")
    load_context = function_source(sdi, "_load_current_context")
    read_state = function_source(sdi, "_read_framework_state_dataset")
    read_collected = function_source(sdi, "_read_framework_collected_dataset")
    load_data = function_source(framework, "load_from_data_tab")
    open_sdi = function_source(framework, "on_calculate_sdi_clicked")

    assert "framework_ctrl: Optional[Any] = None" in init
    assert "self.framework_ctrl = framework_ctrl" in init
    assert "_read_framework_state_dataset" in load_context
    assert "_read_plugin_dataset" in load_context
    assert "_read_framework_collected_dataset" in load_context
    assert "getattr(state, \"__dict__\", {})" in read_state
    assert "SemivariogramInputs" in read_state
    assert "_collect_current_plugin_data" in read_collected
    assert "load_from_data_tab" in read_collected
    assert "self.state.__dict__[key] = arr" in load_data
    assert "FrameworkSDIDialog(parent=self.dlg, plugin=self.plugin, framework_ctrl=self)" in open_sdi


def test_grid_progress_close_does_not_trigger_false_cancelation():
    ml = ROOT / "machine_learning_tab.py"
    grid_builder = function_source(ml, "_build_grid_dataframe_for_rf")

    assert "progress.setAutoClose(False)" in grid_builder
    assert "progress.setAutoReset(False)" in grid_builder
    assert "canceled = False" in grid_builder
    assert "if canceled:" in grid_builder
    assert grid_builder.index("for idx_i") < grid_builder.index("if canceled:")
    assert grid_builder.index("if canceled:") < grid_builder.index("Grid preparation was canceled by the user.")


def test_rf_svm_interpolation_pages_report_selected_model_metrics():
    ml = ROOT / "machine_learning_tab.py"
    rf = ROOT / "RF_Interpolation.py"
    svm = ROOT / "SVM_Interpolation.py"

    ensure = function_source(ml, "_ensure_rf_svm_grid_summary_panels")
    rf_summary = function_source(ml, "_update_rf_grid_summary")
    svm_summary = function_source(ml, "_update_svm_grid_summary")
    rf_tune = function_source(rf, "_tune_random_forest")
    svm_tune = function_source(svm, "_tune_svm")
    rf_ui = function_source(ml, "_update_rf_metrics_ui")
    svm_run = function_source(ml, "_on_run_svm_interpolation")

    assert "valRFGridSearchSummary" in ensure
    assert "valSVMGridSearchSummary" in ensure
    assert "gridLayoutRFParams" in ensure
    assert "verticalLayoutSVMLeftPanel" in ensure
    assert "cv_mae" in rf_tune
    assert "cv_rmse" in svm_tune
    assert "Best params" in rf_summary
    assert "Final fit" in rf_summary
    assert "Best params" in svm_summary
    assert "Final fit" in svm_summary
    assert "_update_rf_grid_summary" in rf_ui
    assert "_update_svm_grid_summary" in svm_run


def test_regression_kriging_has_residual_variogram_adjustment_and_validation():
    rk = ROOT / "RF_RegressionKriging.py"

    ensure = function_source(rk, "_ensure_variogram_controls")
    fit = function_source(rk, "_fit_variogram_stage")
    candidates = function_source(ROOT / "semivariogram_engine.py", "_fit_variogram_candidates")
    validate = function_source(rk, "_validate_variogram_candidates")
    cv = function_source(ROOT / "semivariogram_engine.py", "_residual_model_cv_metrics")
    click = function_source(rk, "_on_validate_variogram_models_clicked")

    assert "spinRKCutoff" in ensure
    assert "spinRKLag" in ensure
    assert "btnRKFitVariogram" in ensure
    assert "btnRKValidateVariogramModels" in ensure
    assert "Validate 3 models" in ensure
    assert "_resolve_variogram_binning" in fit
    assert "_validate_variogram_candidates" in fit
    assert "_select_best_variogram_fit" in fit
    assert "\"spherical\"" in candidates
    assert "\"exponential\"" in candidates
    assert "\"gaussian\"" in candidates
    assert "for fit in candidates" in validate
    assert "\"spatial_holdout\"" in cv
    assert "\"holdout\"" in cv
    assert "array_split" in cv
    assert "_update_variogram_validation_summary" in validate
    assert "show_advanced_settings(self,residual=True,validate=True)" in click


def test_tps_final_map_is_scaled_and_clipped_to_observed_range():
    main = ROOT / "BestFitInterpolator.py"
    framework = ROOT / "framework_tab.py"
    tps = ROOT / "Thin_plate_spline.py"
    main_source = main.read_text(encoding="utf-8-sig")
    tps_source = tps.read_text(encoding="utf-8-sig")
    create_tps = function_source(main, "create_and_display_raster_tps")
    det_cv = function_source(main, "run_cross_validation")
    framework_cv = function_source(framework, "_run_deterministic_or_ok_loocv")

    assert "def _clip_to_observed_range" in main_source
    assert "tps_vals = self._clip_to_observed_range(tps_vals, z)" in create_tps
    assert "pi = self._clip_to_observed_range(pi, train_values)" in det_cv
    assert "pred = self._clip_to_training_range(pred, train_values)" in framework_cv
    assert "def _scale_coordinates_for_tps" in tps_source
    assert "_scale_coordinates_for_tps(x, y, xi, yi)" in tps_source
