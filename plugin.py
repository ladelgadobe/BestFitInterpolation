# -*- coding: utf-8 -*-
"""BestFitInterpolatorPlugin — lifecycle only. No computation, no widgets
beyond the dialog handle; each controller wires its own tab."""

from __future__ import annotations

import os

from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from . import logger as bfi_logger
from .controllers.data_ctrl import DataCtrl
from .controllers.deterministic_ctrl import DeterministicCtrl
from .controllers.framework_ctrl import FrameworkCtrl
from .controllers.geostat_ctrl import GeostatCtrl
from .controllers.ml_ctrl import MLCtrl
from .dialog import BestFitInterpolatorDialog
from .notify import Notifier
from .services.session import BFISession
from .view.plotting import PlotService

log = bfi_logger.get_logger(__name__)


def _tr(text):
    return QCoreApplication.translate("BestFitInterpolator", text)


class BestFitInterpolatorPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.dlg = None
        self.controllers = []
        self.actions = []
        self.menu = _tr("&Best Fit Interpolator")
        bfi_logger.setup()

    # ------------------------------------------------------------ lifecycle
    def initGui(self):
        icon = QIcon(os.path.join(self.plugin_dir, "icon.png"))
        action = QAction(icon, _tr("Best Fit Interpolator"), self.iface.mainWindow())
        action.triggered.connect(self.run)
        self.iface.addToolBarIcon(action)
        self.iface.addPluginToMenu(self.menu, action)
        self.actions.append(action)

    def unload(self):
        for controller in self.controllers:
            try:
                controller.shutdown()
            except Exception:
                log.exception("Controller shutdown failed")
        self.controllers = []
        if self.dlg is not None:
            self.dlg.close()
            self.dlg.deleteLater()
            self.dlg = None
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)
        self.actions = []

    # ------------------------------------------------------------------ run
    def run(self):
        if self.dlg is None:
            self._build_dialog()
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.activateWindow()

    def _build_dialog(self):
        self.dlg = BestFitInterpolatorDialog(self.plugin_dir, parent=self.iface.mainWindow())
        session = BFISession()
        notifier = Notifier(self.iface)
        plots = PlotService()
        args = (self.iface, self.dlg, session, notifier, plots)
        self.controllers = [
            DataCtrl(*args),
            DeterministicCtrl(*args),
            GeostatCtrl(*args),
            MLCtrl(*args),
            FrameworkCtrl(*args),
        ]
        for controller in self.controllers:
            controller.wire()
