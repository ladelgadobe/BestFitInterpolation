# -*- coding: utf-8 -*-
"""BestFitInterpolatorDialog — logic-free shell that composes the code-built
pages. Signal wiring lives in the controllers."""

from __future__ import annotations

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QDialog, QTabWidget, QVBoxLayout, QWidget

from .metadata_utils import read_plugin_metadata
from .view.about_page import setup_about_page
from .view.common import tr
from .view.data_page import setup_data_page
from .view.deterministic_page import setup_deterministic_page
from .view.framework_page import setup_framework_page
from .view.geostat_page import setup_geostat_page
from .view.ml_page import setup_ml_page


class BestFitInterpolatorDialog(QDialog):
    def __init__(self, plugin_dir, parent=None):
        super().__init__(parent)
        self.plugin_dir = plugin_dir
        self.setWindowTitle("Best Fit Interpolator")
        self.resize(1060, 720)

        # Normal top-level window with minimize/maximize; no "?" help button.
        flags = self.windowFlags()
        flags |= Qt.Window
        flags |= Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint
        self.setWindowFlags(flags)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self.main_tabs = QTabWidget(self)
        self.main_tabs.setObjectName("mainTabs")
        layout.addWidget(self.main_tabs)

        for title, setup in (
            (tr("Data"), setup_data_page),
            (tr("Deterministic"), setup_deterministic_page),
            (tr("Geostatistics"), setup_geostat_page),
            (tr("Machine Learning"), setup_ml_page),
            (tr("Framework"), setup_framework_page),
        ):
            page = QWidget()
            setup(self, page)
            self.main_tabs.addTab(page, title)

        about = QWidget()
        setup_about_page(self, about, plugin_dir, read_plugin_metadata(plugin_dir))
        self.main_tabs.addTab(about, tr("About"))
