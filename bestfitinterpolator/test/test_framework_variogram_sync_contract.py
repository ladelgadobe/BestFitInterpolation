import ast
from pathlib import Path
import textwrap
from typing import Any, Dict, Optional

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def function_source(path, name):
    source = path.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(source, node)
    raise AssertionError(f"Function {name} not found in {path.name}")


def standalone_method(path, name):
    namespace = {
        "Any": Any,
        "Dict": Dict,
        "Optional": Optional,
        "np": np,
    }
    exec(compile(textwrap.dedent(function_source(path, name)), str(path), "exec"), namespace)
    return namespace[name]


def test_framework_preview_uses_active_geostatistics_variogram():
    framework = ROOT / "framework_tab.py"
    state_reader = function_source(framework, "_geostatistics_variogram_state")
    preview = function_source(framework, "_draw_framework_variogram_preview")

    assert "_update_ok_context" in state_reader
    assert "_get_selected_model" in state_reader
    assert "_read_params_from_ui" in state_reader
    assert "_exp_lags" in state_reader
    assert "_exp_gamma" in state_reader
    assert "_geostatistics_variogram_state(data)" in preview
    assert "Theoretical ({model_label})" in preview
    assert "Theoretical ({fit_method})" not in preview


def test_geostatistics_state_copies_model_parameters_and_experimental_points():
    reader = standalone_method(ROOT / "framework_tab.py", "_geostatistics_variogram_state")

    class Layer:
        def id(self):
            return "current-layer"

    class ActiveOK:
        z_field = "ID"
        points_layer = Layer()
        _cutoff = 905.0982
        _lag_width = 79.9912
        _use_reml = False
        _ok_fit_method = "MoM"
        _exp_lags = np.array([0.0, 120.0, 210.0])
        _exp_gamma = np.array([0.0, 3000.0, 11000.0])

        def _ensure_variogram_ready(self):
            return True

        def _get_selected_model(self):
            return "gaussian"

        def _read_params_from_ui(self):
            return 3619.9463, 254321.8938, 905.0982

    class Dispatcher:
        _active = ActiveOK()
        _field_name = "ID"
        _layer = _active.points_layer
        strategy_name = "MoM"

    class Plugin:
        ok_ctrl = Dispatcher()
        updates = 0

        def _update_ok_context(self):
            self.updates += 1

    class Controller:
        plugin = Plugin()

        @staticmethod
        def _pairwise_distances(x, y):
            return np.array([1.0])

        @staticmethod
        def _nearest_neighbor_dist(x, y):
            return 1.0

        @staticmethod
        def _safe_lag_width(x, y, cutoff, lagw):
            return float(lagw)

        @staticmethod
        def _normalize_model_token(model):
            return str(model).lower()

        @staticmethod
        def _ok_model_text_from_key(model):
            return {"gaussian": "Gaussian"}[model]

    data = {
        "variable_name": "ID",
        "point_layer": Dispatcher._layer,
        "x": np.array([0.0, 1.0]),
        "y": np.array([0.0, 1.0]),
    }
    result = reader(Controller(), data)

    assert Controller.plugin.updates == 1
    assert result["model"] == "Gaussian"
    assert result["nugget"] == 3619.9463
    assert result["psill"] == 254321.8938
    assert result["range"] == 905.0982
    assert result["fit_method"] == "MoM"
    np.testing.assert_array_equal(result["lags"], np.array([120.0, 210.0]))
    np.testing.assert_array_equal(result["gamma"], np.array([3000.0, 11000.0]))
