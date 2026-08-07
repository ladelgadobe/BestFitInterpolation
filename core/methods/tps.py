# -*- coding: utf-8 -*-
"""Thin Plate Spline with the fit/predict split.

The legacy Thin_plate_spline.tps_interpolation rebuilt the O(n³) scipy Rbf
solve on EVERY call — once per raster progress chunk (~50 refits per map) and
once per LOOCV iteration. Here the Rbf is built once in fit(); predict only
evaluates it, chunked."""

from __future__ import annotations

import numpy as np

from ..arrays import ensure_values_1d, ensure_xy_2d
from ..deps import import_scipy_rbf
from ..exceptions import InvalidDataError, OperationCancelled
from ..types import FitResult, TrainingData
from .base import InterpolationMethod, MethodInfo

DEFAULT_EPSILON = 1e-4  # legacy default


class TPSModel:
    def __init__(self, rbf):
        self._rbf = rbf

    def predict(self, xy, covariates=None, *, progress=None, should_stop=None,
                chunk_size=50000):
        xy = ensure_xy_2d(xy, "prediction coordinates")
        m = xy.shape[0]
        out = np.empty(m, dtype=float)
        step = int(chunk_size) if chunk_size else m
        for start in range(0, m, step):
            if should_stop is not None and should_stop():
                raise OperationCancelled()
            end = min(m, start + step)
            pred = self._rbf(xy[start:end, 0], xy[start:end, 1])
            out[start:end] = np.asarray(pred, dtype=float).ravel()
            if progress is not None:
                progress(end, m)
        return out


class TPSMethod(InterpolationMethod):
    info = MethodInfo(
        key="tps",
        label="Thin Plate Spline",
        min_samples=3,
        requires=("scipy",),
        tunable=False,
    )

    def validate(self, data: TrainingData) -> None:
        super().validate(data)
        if data.n > 1:
            if np.unique(data.xy, axis=0).shape[0] < data.n:
                raise InvalidDataError(
                    "TPS training data contains duplicate coordinates. "
                    "Keep one sample per coordinate before interpolation."
                )

    def fit(self, data: TrainingData, params=None, *, progress=None, should_stop=None) -> FitResult:
        self.validate(data)
        Rbf = import_scipy_rbf()
        params = dict(params or {})
        epsilon = params.get("epsilon")
        if epsilon is None or float(epsilon) <= 0.0:
            epsilon = DEFAULT_EPSILON
        z = ensure_values_1d(data.values, "training values")
        rbf = Rbf(data.x, data.y, z, function="thin_plate", epsilon=float(epsilon))
        return FitResult(model=TPSModel(rbf), params={"epsilon": float(epsilon)})
