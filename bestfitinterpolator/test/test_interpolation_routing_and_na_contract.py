import ast
import importlib.util
from pathlib import Path
import sys
import textwrap

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def function_source(path, name):
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(source, node)
    raise AssertionError(f"Function {name} not found in {path.name}")


def standalone_method(path, name, namespace=None):
    scope = dict(namespace or {})
    exec(
        compile(textwrap.dedent(function_source(path, name)), str(path), "exec"),
        scope,
    )
    return scope[name]


def test_deterministic_interpolation_never_dispatches_to_reml():
    main = ROOT / "BestFitInterpolator.py"
    source = function_source(main, "run_interpolation")
    reml_source = function_source(main, "run_ok_interpolation_reml")

    assert "_selected_deterministic_mode()" in source
    assert "run_ok_interpolation_reml" not in source
    assert "REML prediction failed:" in reml_source


def test_selected_deterministic_mode_reads_the_tps_control():
    selector = standalone_method(ROOT / "BestFitInterpolator.py", "_selected_deterministic_mode")

    class Button:
        def __init__(self, checked):
            self.checked = checked

        def isChecked(self):
            return self.checked

    class Controller:
        MODE_IDW_OPT = 0
        MODE_IDW_MAN = 1
        MODE_TPS = 2
        _current_mode = MODE_IDW_OPT
        btn_tps = Button(True)
        btn_idw_man = Button(False)
        btn_idw_opt = Button(False)

    controller = Controller()
    assert selector(controller) == controller.MODE_TPS
    assert controller._current_mode == controller.MODE_TPS


def test_incomplete_data_warning_is_shown_once_per_layer_and_field():
    class QVariant:
        pass

    filter_rows = standalone_method(
        ROOT / "BestFitInterpolator.py",
        "filter_incomplete_data",
        {"np": np, "QVariant": QVariant},
    )

    class Combo:
        def __init__(self, text):
            self.text = text

        def currentText(self):
            return self.text

    class Dialog:
        Points = Combo("samples")
        Points_2 = Combo("value")

    class MessageBar:
        calls = []

        def pushMessage(self, title, message, level):
            self.calls.append((title, message, level))

    class Iface:
        bar = MessageBar()

        def messageBar(self):
            return self.bar

    class Controller:
        dlg = Dialog()
        iface = Iface()
        _incomplete_data_warning_keys = set()

    controller = Controller()
    coords = [(0.0, 0.0), (1.0, 1.0)]
    values = [1.0, np.nan]

    filter_rows(controller, coords, values)
    filter_rows(controller, coords, values)
    assert len(controller.iface.bar.calls) == 1

    controller.dlg.Points_2.text = "another_value"
    filter_rows(controller, coords, values)
    assert len(controller.iface.bar.calls) == 2


def test_reml_prediction_variance_uses_the_solved_covariance_matrix():
    path = ROOT / "kriging_reml.py"
    spec = importlib.util.spec_from_file_location("kriging_reml_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    coords = np.column_stack(
        (
            np.linspace(0.0, 13.0, 14),
            np.sin(np.linspace(0.0, 2.0, 14)),
        )
    )
    values = np.linspace(10.0, 30.0, 14)
    prediction_coords = np.array([[0.5, 0.1], [6.5, 0.8], [12.5, 0.9]])
    params = {
        "model": "Gaussian",
        "psill": 20.0,
        "range": 8.0,
        "nugget": 2.0,
    }

    prediction, variance = module.ok_predict(
        coords,
        values,
        params,
        prediction_coords,
        return_var=True,
    )

    assert prediction.shape == (3,)
    assert variance.shape == (3,)
    assert np.all(np.isfinite(prediction))
    assert np.all(np.isfinite(variance))
    assert np.all(variance >= 0.0)
