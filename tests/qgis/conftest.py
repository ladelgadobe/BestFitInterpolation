# -*- coding: utf-8 -*-
"""QGIS-tier fixtures: one offscreen QgsApplication per session."""

import pytest


@pytest.fixture(scope="session")
def qgis_app():
    from qgis.core import QgsApplication

    app = QgsApplication.instance()
    created = False
    if app is None:
        app = QgsApplication([], False)
        app.initQgis()
        created = True
    yield app
    if created:
        app.exitQgis()
