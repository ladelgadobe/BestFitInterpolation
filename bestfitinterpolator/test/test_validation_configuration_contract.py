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
    assert "btnFrameworkRunInterpolation" not in ui
    assert "Run interpolation" not in ui
