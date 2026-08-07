# -*- coding: utf-8 -*-
"""QGIS plugin entry point for Best Fit Interpolator.

The extlibs/ path insert MUST happen before any plugin module is imported so
optional compiled deps (scikit-learn stack) resolve from the first import.
"""

import os
import sys

_plugin_dir = os.path.dirname(__file__)
_extlibs_path = os.path.join(_plugin_dir, "extlibs")

if os.path.isdir(_extlibs_path) and _extlibs_path not in sys.path:
    sys.path.insert(0, _extlibs_path)


def classFactory(iface):
    """Load Best Fit Interpolator into QGIS."""
    from . import extlibs_manager

    # Provision (or re-provision after a QGIS Python upgrade) the deps matching
    # the running interpreter; tag-aware so a stale build triggers a refresh.
    if extlibs_manager.needs_provision():
        extlibs_manager.start_download()

    from .plugin import BestFitInterpolatorPlugin

    return BestFitInterpolatorPlugin(iface)
