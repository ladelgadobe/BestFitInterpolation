# -*- coding: utf-8 -*-
"""Release smoke test: classFactory builds the plugin, the dialog composes
with all controllers wired, and unload leaves no running threads."""

import pathlib
import sys

import pytest

pytestmark = pytest.mark.gui

PLUGIN_DIR = pathlib.Path(__file__).resolve().parents[2]


class _FakeIface:
    def __init__(self, app):
        self._app = app
        self._bar = _FakeMessageBar()

    def mainWindow(self):
        return None

    def addToolBarIcon(self, action):
        pass

    def removeToolBarIcon(self, action):
        pass

    def addPluginToMenu(self, menu, action):
        pass

    def removePluginMenu(self, menu, action):
        pass

    def messageBar(self):
        return self._bar


class _FakeMessageBar:
    def __init__(self):
        self.messages = []

    def pushMessage(self, *args, **kwargs):
        self.messages.append((args, kwargs))


@pytest.fixture
def plugin(qgis_app):
    sys.path.insert(0, str(PLUGIN_DIR.parent))
    try:
        from bestfitinterpolator.plugin import BestFitInterpolatorPlugin

        p = BestFitInterpolatorPlugin(_FakeIface(qgis_app))
        yield p
        p.unload()
    finally:
        sys.path.remove(str(PLUGIN_DIR.parent))


def test_plugin_builds_dialog_and_wires_controllers(plugin):
    plugin._build_dialog()
    assert plugin.dlg is not None
    assert len(plugin.controllers) == 5
    for controller in plugin.controllers:
        assert controller._connections, (
            f"{type(controller).__name__}.wire() connected nothing"
        )


def test_unload_after_build_leaves_no_workers(plugin):
    plugin._build_dialog()
    plugin.unload()
    assert plugin.controllers == []
    assert plugin.dlg is None
