# -*- coding: utf-8 -*-
"""ModelValidationWorker — LOOCV comparison of the three variogram models
(the geostat tab's automatic model selection)."""

from __future__ import annotations

from ..core.methods.kriging_ok import choose_best_model_by_validation
from ..core.types import TrainingData
from .base import BaseWorker


class ModelValidationWorker(BaseWorker):
    def __init__(self, data: TrainingData, cutoff=None, lag_width=None, parent=None):
        super().__init__(parent)
        self._data = data
        self._cutoff = cutoff
        self._lag_width = lag_width

    def _work(self, *, progress, status, should_stop):
        status("Comparing variogram models (LOOCV)…")
        return choose_best_model_by_validation(
            self._data,
            cutoff=self._cutoff,
            lag_width=self._lag_width,
            progress=progress,
            should_stop=should_stop,
        )
