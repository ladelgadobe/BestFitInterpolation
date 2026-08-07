# -*- coding: utf-8 -*-
"""FitWorker — fit / auto-tune one method (RF/SVM search, IDW optimize,
variogram fit: use method_key="ok" and read FitResult.diagnostics)."""

from __future__ import annotations

from ..core.methods import get_method
from ..core.types import TrainingData
from .base import BaseWorker


class FitWorker(BaseWorker):
    def __init__(self, data: TrainingData, method_key: str, params=None, parent=None):
        super().__init__(parent)
        self._data = data
        self._method_key = method_key
        self._params = params

    def _work(self, *, progress, status, should_stop):
        method = get_method(self._method_key)
        status(f"Fitting {method.info.label}…")
        method.validate(self._data)
        return method.fit(
            self._data, params=self._params, progress=progress, should_stop=should_stop
        )
