# -*- coding: utf-8 -*-
"""InterpolationWorker — raster generation. _cleanup_partial deletes the
output path so a cancel never leaves a file behind (the service also only
writes once at the very end)."""

from __future__ import annotations

import os

from ..core.types import GridSpec, TrainingData
from ..logger import get_logger
from ..services.interpolation_service import generate_raster
from .base import BaseWorker

logger = get_logger(__name__)


class InterpolationWorker(BaseWorker):
    def __init__(
        self,
        data: TrainingData,
        method_key: str,
        params,
        grid: GridSpec,
        boundary_wkts,
        out_path: str,
        covariate_paths=(),
        parent=None,
    ):
        super().__init__(parent)
        self._data = data
        self._method_key = method_key
        self._params = params
        self._grid = grid
        self._boundary_wkts = list(boundary_wkts)
        self._out_path = out_path
        self._covariate_paths = list(covariate_paths)

    def _work(self, *, progress, status, should_stop):
        return generate_raster(
            self._data,
            self._method_key,
            self._params,
            self._grid,
            self._boundary_wkts,
            self._out_path,
            covariate_paths=self._covariate_paths,
            progress=progress,
            status=status,
            should_stop=should_stop,
        )

    def _cleanup_partial(self):
        try:
            if os.path.exists(self._out_path):
                os.remove(self._out_path)
        except Exception:
            logger.debug("Could not remove partial raster %s", self._out_path, exc_info=True)
