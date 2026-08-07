# -*- coding: utf-8 -*-
"""CVWorker — cross-validation for one method."""

from __future__ import annotations

from ..core.types import CVPlan, TrainingData
from ..services.cv_service import run_cv
from .base import BaseWorker


class CVWorker(BaseWorker):
    def __init__(self, data: TrainingData, method_key: str, params=None,
                 plan: CVPlan | None = None, parent=None):
        super().__init__(parent)
        self._data = data
        self._method_key = method_key
        self._params = params
        self._plan = plan

    def _work(self, *, progress, status, should_stop):
        status("Running cross-validation…")
        return run_cv(
            self._data,
            self._method_key,
            self._params,
            self._plan,
            progress=progress,
            should_stop=should_stop,
        )
