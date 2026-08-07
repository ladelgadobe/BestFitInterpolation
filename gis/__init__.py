# -*- coding: utf-8 -*-
"""QGIS/GDAL IO layer.

Rules (grep-enforced): ``qgis.core`` and ``osgeo`` are allowed here;
``QtWidgets`` is forbidden. Layer objects never cross a thread boundary —
controllers extract numpy/WKT on the UI thread and hand plain data to
workers.
"""
