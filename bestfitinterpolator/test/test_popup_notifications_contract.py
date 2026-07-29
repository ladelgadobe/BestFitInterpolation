import ast
import importlib.util
from pathlib import Path
import sys
import types


ROOT = Path(__file__).resolve().parents[1]


class FakeApplicationInstance:
    def activeModalWidget(self):
        return None

    def activeWindow(self):
        return "active-window"


class FakeApplication:
    @staticmethod
    def instance():
        return FakeApplicationInstance()


class FakeMessageBox:
    calls = []

    @classmethod
    def information(cls, parent, title, text):
        cls.calls.append(("information", parent, title, text))
        return "information"

    @classmethod
    def warning(cls, parent, title, text):
        cls.calls.append(("warning", parent, title, text))
        return "warning"

    @classmethod
    def critical(cls, parent, title, text):
        cls.calls.append(("critical", parent, title, text))
        return "critical"


class FakeNativeMessageBar:
    calls = []

    def pushMessage(self, *args, **kwargs):
        self.calls.append(("pushMessage", args, kwargs))
        return "message-bar"

    def pushSuccess(self, *args, **kwargs):
        self.calls.append(("pushSuccess", args, kwargs))
        return "success-bar"


def load_notifications():
    widgets = types.ModuleType("qgis.PyQt.QtWidgets")
    widgets.QApplication = FakeApplication
    widgets.QMessageBox = FakeMessageBox
    pyqt = types.ModuleType("qgis.PyQt")
    pyqt.QtWidgets = widgets
    qgis = types.ModuleType("qgis")
    qgis.PyQt = pyqt

    sys.modules["qgis"] = qgis
    sys.modules["qgis.PyQt"] = pyqt
    sys.modules["qgis.PyQt.QtWidgets"] = widgets

    path = ROOT / "notifications.py"
    spec = importlib.util.spec_from_file_location("popup_notifications", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_only_warning_and_error_levels_open_popup_windows():
    module = load_notifications()

    class Iface:
        native_bar = FakeNativeMessageBar()

        def mainWindow(self):
            return "main-window"

        def messageBar(self):
            return self.native_bar

        def addToolBarIcon(self, action):
            return action

    FakeMessageBox.calls.clear()
    FakeNativeMessageBar.calls.clear()
    proxy = module.PopupIfaceProxy(Iface())
    message_bar = proxy.messageBar()

    message_bar.pushMessage(
        "Error",
        "At least 10 valid samples are required for TPS interpolation.",
        level=3,
    )
    message_bar.pushWarning("Interpolation", "Operation canceled by user.")
    message_bar.pushMessage("Interpolation", "Interpolation complete.", level=0)
    message_bar.pushSuccess("Interpolation", "Raster added to QGIS.")
    message_bar.pushCritical("Kriging", "Backend unavailable.")

    assert [call[0] for call in FakeMessageBox.calls] == [
        "critical",
        "warning",
        "critical",
    ]
    assert "10 valid samples" in FakeMessageBox.calls[0][3]
    assert [call[0] for call in FakeNativeMessageBar.calls] == [
        "pushMessage",
        "pushSuccess",
    ]
    assert FakeNativeMessageBar.calls[0][1] == (
        "Interpolation",
        "Interpolation complete.",
    )
    assert proxy.addToolBarIcon("action") == "action"


def test_plugin_wraps_iface_and_all_message_bar_calls_use_it():
    main_source = (ROOT / "BestFitInterpolator.py").read_text(encoding="utf-8-sig")
    main_tree = ast.parse(main_source)
    init_assignments = [
        node
        for node in ast.walk(main_tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
            and target.attr == "iface"
            for target in node.targets
        )
    ]
    assert any(
        isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "PopupIfaceProxy"
        for node in init_assignments
    )

    offenders = []
    for path in ROOT.glob("*.py"):
        if path.name in {"resources.py", "resources_rc.py"}:
            continue
        source = path.read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in {"pushMessage", "pushWarning", "pushCritical", "pushSuccess"}:
                continue
            receiver = ast.unparse(node.func.value)
            if receiver != "self.iface.messageBar()":
                offenders.append(f"{path.name}:{node.lineno}: {receiver}")

    assert not offenders, "Unrouted message-bar calls found:\n" + "\n".join(offenders)
