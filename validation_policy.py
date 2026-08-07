# -*- coding: utf-8 -*-
"""Compatibility shim — the CV policy moved to core/cv.py.

Kept only until the legacy modules that import this name are deleted by the
restructure (phase 8)."""

from .core.cv import (  # noqa: F401
    AUTO_CV_HELP_TEXT,
    AUTO_CV_LOOCV_MAX_SAMPLES,
    AUTO_CV_TEN_FOLD_MAX_SAMPLES,
    decide_automatic_cv,
)
