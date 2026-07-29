import ast
import importlib.util
from pathlib import Path
import re
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]


def load_validation_policy():
    path = ROOT / "validation_policy.py"
    spec = importlib.util.spec_from_file_location("validation_policy", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_auto_cv_boundary_and_help_text_are_consistent():
    policy = load_validation_policy()

    assert policy.decide_automatic_cv(100) == ("loocv", None)
    assert policy.decide_automatic_cv(101) == ("kfold", 10)
    assert policy.decide_automatic_cv(1000) == ("kfold", 10)
    assert policy.decide_automatic_cv(1001) == ("kfold", 5)
    assert "100 samples" in policy.AUTO_CV_HELP_TEXT
    assert "101 samples" in policy.AUTO_CV_HELP_TEXT
    assert "10 folds" in policy.AUTO_CV_HELP_TEXT
    assert "5 folds" in policy.AUTO_CV_HELP_TEXT


def test_validation_labels_use_superscript_r_squared():
    ui_root = ET.parse(ROOT / "BestFitInterpolator_dialog_base.ui").getroot()
    visible_ui_text = [node.text or "" for node in ui_root.findall(".//string")]

    assert "R²:" in visible_ui_text
    assert visible_ui_text.count("R²") >= 5
    assert "R2:" not in visible_ui_text
    assert "R2" not in visible_ui_text

    offenders = []
    for name in (
        "BestFitInterpolator.py",
        "framework_tab.py",
        "machine_learning_tab.py",
        "RF_RegressionKriging.py",
        "ok_r_integration_MoM.py",
        "ok_r_integration_reml.py",
    ):
        path = ROOT / name
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if re.search(r"\bR2\b", node.value):
                    offenders.append(f"{name}: {node.value}")

    assert not offenders, "Visible R2 strings found:\n" + "\n".join(offenders)
