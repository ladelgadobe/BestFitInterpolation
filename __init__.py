# -*- coding: utf-8 -*-
"""QGIS plugin entry point for Best Fit Interpolator."""


def classFactory(iface):
    """Load Best Fit Interpolator into QGIS."""
    from . import resources  # noqa: F401
    from .BestFitInterpolator import BestFitInterpolator

    return BestFitInterpolator(iface)
