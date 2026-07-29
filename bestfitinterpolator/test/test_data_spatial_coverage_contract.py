import ast
from pathlib import Path
import textwrap


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


def test_coverage_warning_is_called_only_from_data_preview():
    main = ROOT / "BestFitInterpolator.py"
    source = main.read_text(encoding="utf-8-sig")
    plot_source = function_source(main, "plot_map_tab1")

    assert "_warn_if_points_outside_polygon(" in plot_source
    assert source.count("self._warn_if_points_outside_polygon(") == 1
    assert "intersects(point_geometry)" in function_source(
        main,
        "_count_points_outside_polygon",
    )


def test_boundary_and_inside_points_are_accepted():
    counter = standalone_method(
        ROOT / "BestFitInterpolator.py",
        "_count_points_outside_polygon",
    )

    class Point:
        def __init__(self, name):
            self.name = name

        def isEmpty(self):
            return False

    class Polygon:
        def intersects(self, point):
            return point.name in {"inside", "boundary"}

    total, outside = counter(
        [Point("inside"), Point("boundary"), Point("outside")],
        Polygon(),
    )

    assert total == 3
    assert outside == 1


def test_outside_warning_is_shown_only_once_for_same_selection():
    class FakeMessageBox:
        calls = []

        @classmethod
        def warning(cls, parent, title, message):
            cls.calls.append((parent, title, message))

    warning = standalone_method(
        ROOT / "BestFitInterpolator.py",
        "_warn_if_points_outside_polygon",
        {"QMessageBox": FakeMessageBox},
    )

    class Layer:
        def __init__(self, layer_id):
            self.layer_id = layer_id

        def id(self):
            return self.layer_id

    class Controller:
        dlg = "dialog"
        _spatial_coverage_warning_keys = set()

        @staticmethod
        def _point_polygon_coverage_counts(
            points_layer,
            polygon_layer,
            variable_name,
        ):
            return 5, 2

    controller = Controller()
    points = Layer("points")
    polygon = Layer("polygon")

    warning(controller, points, polygon, "value")
    warning(controller, points, polygon, "value")

    assert len(FakeMessageBox.calls) == 1
    assert FakeMessageBox.calls[0][1] == "Points outside polygon"
    assert "2 of 5 valid sample points" in FakeMessageBox.calls[0][2]


def test_interpolation_is_blocked_when_every_valid_point_is_outside():
    class FakeMessageBox:
        calls = []

        @classmethod
        def critical(cls, parent, title, message):
            cls.calls.append((parent, title, message))

    validator = standalone_method(
        ROOT / "BestFitInterpolator.py",
        "_validate_interpolation_spatial_coverage",
        {"QMessageBox": FakeMessageBox},
    )

    class Controller:
        dlg = "dialog"
        counts = (5, 5)

        def _point_polygon_coverage_counts(
            self,
            points_layer,
            polygon_layer,
            variable_name,
        ):
            return self.counts

    controller = Controller()
    assert not validator(controller, "points", "polygon", "value", "TPS")
    assert len(FakeMessageBox.calls) == 1
    assert FakeMessageBox.calls[0][1] == "TPS blocked"
    assert "No raster was created" in FakeMessageBox.calls[0][2]

    controller.counts = (5, 4)
    assert validator(controller, "points", "polygon", "value", "TPS")
    assert len(FakeMessageBox.calls) == 1


def test_interpolation_is_blocked_when_layer_crs_differ():
    class FakeMessageBox:
        calls = []

        @classmethod
        def critical(cls, parent, title, message):
            cls.calls.append((parent, title, message))

    validator = standalone_method(
        ROOT / "BestFitInterpolator.py",
        "_validate_interpolation_spatial_coverage",
        {"QMessageBox": FakeMessageBox},
    )

    class Crs:
        def __init__(self, authid):
            self.authid = authid

        def isValid(self):
            return True

        def __eq__(self, other):
            return self.authid == other.authid

    class Layer:
        def __init__(self, authid):
            self.layer_crs = Crs(authid)

        def crs(self):
            return self.layer_crs

    class Controller:
        dlg = "dialog"

        @staticmethod
        def _point_polygon_coverage_counts(*args):
            raise AssertionError("Coverage must not run for mismatched CRS")

    allowed = validator(
        Controller(),
        Layer("EPSG:32618"),
        Layer("EPSG:4326"),
        "value",
        "TPS",
    )

    assert not allowed
    assert len(FakeMessageBox.calls) == 1
    assert "different coordinate reference systems" in FakeMessageBox.calls[0][2]


def test_every_interpolation_entrypoint_runs_the_blocking_preflight():
    expected = {
        "BestFitInterpolator.py": [
            "run_interpolation",
            "run_ok_interpolation",
            "run_ok_interpolation_reml",
        ],
        "ok_r_integration_MoM.py": ["_on_interpolate_clicked"],
        "ok_r_integration_reml.py": ["_on_interpolate_clicked"],
        "machine_learning_tab.py": [
            "_on_run_rf_interpolation",
            "_on_run_svm_interpolation",
        ],
        "RF_RegressionKriging.py": ["_run_rk_prediction"],
        "framework_tab.py": ["on_run_interpolation_clicked"],
    }

    for filename, functions in expected.items():
        path = ROOT / filename
        for function_name in functions:
            source = function_source(path, function_name)
            assert "_validate_current_interpolation_coverage" in source, (
                f"{filename}:{function_name} bypasses spatial coverage validation"
            )
