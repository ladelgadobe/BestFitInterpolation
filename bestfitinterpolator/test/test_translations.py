"""Check optional translations do not require a nonexistent template qm file."""
from qgis.PyQt.QtCore import QTranslator
from pathlib import Path

def test_missing_optional_translation_is_safe():
    translator=QTranslator()
    assert not translator.load(str(Path(__file__).parent/"nonexistent.qm"))
