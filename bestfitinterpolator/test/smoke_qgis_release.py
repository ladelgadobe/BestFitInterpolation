"""Headless QGIS smoke test for the release dialog."""

import os
import sys
import configparser
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qgis.core import QgsApplication
from qgis.PyQt.QtWidgets import QLabel


PLUGIN_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_DIR.parent))

app = QgsApplication([], False)
app.initQgis()

from bestfitinterpolator.BestFitInterpolator import BestFitInterpolatorDialog


dialog = BestFitInterpolatorDialog(str(PLUGIN_DIR))
tabs = [dialog.mainTabs.tabText(index) for index in range(dialog.mainTabs.count())]
version_label = dialog.findChild(QLabel, "lblAboutVersion")
assert version_label is not None
version = version_label.text()

print(f"Tabs: {tabs}")
print(f"About version: {version}")

assert tabs[-1] == "About"
metadata = configparser.ConfigParser(interpolation=None)
metadata.read(PLUGIN_DIR / "metadata.txt", encoding="utf-8-sig")
assert version == "Version " + metadata["general"]["version"]

dialog.deleteLater()
app.exitQgis()
print("QGIS_SMOKE_OK")
