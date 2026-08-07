# -*- coding: utf-8 -*-
"""Pure computation layer.

Rules (grep-enforced):
  * numpy may be imported at module top level; scipy/scikit-learn only inside
    functions via :mod:`core.deps` (they may be absent until provisioned).
  * No ``qgis`` or Qt imports anywhere under ``core/``.
"""
