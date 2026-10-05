"""Test the actual dynamically loaded plugin dialog with current QGIS wrappers."""
from pathlib import Path
from bestfitinterpolator.BestFitInterpolator import BestFitInterpolatorDialog


def test_dialog_loads_all_current_pages():
    dialog=BestFitInterpolatorDialog(str(Path(__file__).resolve().parents[1]))
    names=[dialog.mainTabs.tabText(i) for i in range(dialog.mainTabs.count())]
    assert "Data" in names and "Geostatistics" in names and "Framework" in names
    assert dialog.cmbPointsLayer is not None and dialog.cmbVariable is not None
    dialog.deleteLater()
