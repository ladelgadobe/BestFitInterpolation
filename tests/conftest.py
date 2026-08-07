# -*- coding: utf-8 -*-
"""
Shared pytest fixtures + headless bootstrap for the Best Fit Interpolator
test suite.

Two tiers:
  * unit  — runs in any Python with the packages from requirements_test.txt
            (numpy, scipy, scikit-learn, matplotlib, pytest). ``qgis`` and
            ``osgeo`` are replaced with lightweight stubs when absent, so
            pure logic can be imported and exercised without QGIS.
  * qgis  — runs under a real QGIS Python (``qgis.core`` importable). Tests
            marked ``@pytest.mark.qgis`` are skipped automatically otherwise.

The plugin is registered under the import name ``bestfitinterpolator`` so
package-relative imports resolve. Importing it here does NOT execute
``__init__.py`` (that pulls in Qt) — it is registered as a namespace package
pointing at the plugin dir.
"""

import pathlib
import sys
import types
from unittest.mock import MagicMock

import pytest

PLUGIN_DIR = pathlib.Path(__file__).resolve().parent.parent
PKG = "bestfitinterpolator"


# --------------------------------------------------------------------------- #
# Make the plugin importable as a package without running __init__.py
# --------------------------------------------------------------------------- #
def _register_package():
    if PKG in sys.modules:
        return
    pkg = types.ModuleType(PKG)
    pkg.__path__ = [str(PLUGIN_DIR)]  # namespace package -> submodules resolve
    sys.modules[PKG] = pkg


# --------------------------------------------------------------------------- #
# Dependency detection
# --------------------------------------------------------------------------- #
def _importable(name):
    try:
        __import__(name)
        return True
    except Exception:
        return False


HAS_QGIS = _importable("qgis.core")
HAS_GDAL = _importable("osgeo.gdal")


# --------------------------------------------------------------------------- #
# Stubs (installed only when the real dependency is missing)
# --------------------------------------------------------------------------- #
class _AutoModule(types.ModuleType):
    """Module whose every missing attribute is a fresh MagicMock."""

    def __getattr__(self, name):
        m = MagicMock(name=f"{self.__name__}.{name}")
        setattr(self, name, m)
        return m


def _install_qgis_stub():
    """Stub the qgis namespace + the PyQt submodules the plugin imports."""
    for name in (
        "qgis",
        "qgis.core",
        "qgis.gui",
        "qgis.utils",
        "qgis.PyQt",
        "qgis.PyQt.QtCore",
        "qgis.PyQt.QtGui",
        "qgis.PyQt.QtWidgets",
    ):
        if name not in sys.modules:
            sys.modules[name] = _AutoModule(name)


def _install_gdal_stub():
    for name in ("osgeo", "osgeo.gdal", "osgeo.osr", "osgeo.ogr"):
        if name not in sys.modules:
            sys.modules[name] = _AutoModule(name)


# --------------------------------------------------------------------------- #
# Session bootstrap
# --------------------------------------------------------------------------- #
def pytest_configure(config):
    _register_package()
    if not HAS_QGIS:
        _install_qgis_stub()
    if not HAS_GDAL:
        _install_gdal_stub()
    # Plot tests render headless; must run before pyplot is first imported.
    try:
        import matplotlib

        matplotlib.use("Agg", force=True)
    except ImportError:
        pass


def pytest_collection_modifyitems(config, items):
    """Skip qgis-marked tests when no real QGIS interpreter is present."""
    if HAS_QGIS:
        return
    skip = pytest.mark.skip(reason="needs a real QGIS Python (qgis.core absent)")
    for item in items:
        if "qgis" in item.keywords or "gui" in item.keywords:
            item.add_marker(skip)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def has_qgis():
    return HAS_QGIS


@pytest.fixture
def fixtures_dir():
    return PLUGIN_DIR / "tests" / "fixtures"
