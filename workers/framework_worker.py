# -*- coding: utf-8 -*-
"""FrameworkWorker — multi-method comparison through the registry."""

from __future__ import annotations

from ..core.types import CVPlan, TrainingData
from ..services.framework_service import run_comparison
from .base import BaseWorker


class FrameworkWorker(BaseWorker):
    def __init__(self, data: TrainingData, method_keys, plan: CVPlan | None = None,
                 params_by_method=None, parent=None):
        super().__init__(parent)
        self._data = data
        self._method_keys = list(method_keys)
        self._plan = plan
        self._params_by_method = params_by_method or {}

    def _work(self, *, progress, status, should_stop):
        return run_comparison(
            self._data,
            self._method_keys,
            self._plan,
            self._params_by_method,
            progress=progress,
            status=status,
            should_stop=should_stop,
        )
