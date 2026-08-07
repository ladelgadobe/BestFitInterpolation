# -*- coding: utf-8 -*-
"""InterpolationMethod protocol — the one interface every interpolation
method implements and every tab (and the Framework) consumes."""

from __future__ import annotations

import abc
from dataclasses import dataclass

import numpy as np

from ..cv import run_cross_validation
from ..exceptions import InsufficientSamples, InvalidDataError
from ..types import CVPlan, CVResult, FitResult, TrainingData


@dataclass(frozen=True)
class MethodInfo:
    key: str                          # "idw" | "tps" | "ok" | "rf" | "svm" | "rk"
    label: str
    min_samples: int
    requires: tuple = ()              # e.g. ("scipy",) or ("scipy", "scikit-learn")
    supports_covariates: bool = False
    needs_covariates: bool = False    # RF/SVM/RK need covariates OR use_xy features
    supports_variance: bool = False   # kriging variance
    tunable: bool = True


class InterpolationMethod(abc.ABC):
    """fit / predict / cross_validate over plain numpy — no Qt, no QGIS.

    ``fit(params=None)`` auto-tunes (IDW grid search, RF/SVM search, variogram
    auto-fit); passing resolved params skips tuning. ``progress`` is a
    ``callable(done, total)`` and ``should_stop`` a ``callable() -> bool``;
    implementations check it at chunk/fold boundaries and raise
    OperationCancelled.
    """

    info: MethodInfo

    def validate(self, data: TrainingData) -> None:
        """Raise InsufficientSamples/InvalidDataError before any worker runs."""
        n = data.n
        if n < self.info.min_samples:
            raise InsufficientSamples(self.info.label, self.info.min_samples, n)
        if not np.all(np.isfinite(data.values)):
            raise InvalidDataError(
                f"{self.info.label}: training values contain non-finite entries."
            )
        if not np.all(np.isfinite(data.xy)):
            raise InvalidDataError(
                f"{self.info.label}: training coordinates contain non-finite entries."
            )

    @abc.abstractmethod
    def fit(
        self,
        data: TrainingData,
        params: dict | None = None,
        *,
        progress=None,
        should_stop=None,
    ) -> FitResult: ...

    def cross_validate(
        self,
        data: TrainingData,
        params: dict | None,
        plan: CVPlan,
        *,
        progress=None,
        should_stop=None,
    ) -> CVResult:
        """Default: resolve params once on the full data (tuning happens here,
        not per fold — legacy semantics), then generic fit-per-fold CV."""
        self.validate(data)
        if params is None:
            fit = self.fit(data, params=None, should_stop=should_stop)
            params = fit.params
        return run_cross_validation(
            self, data, params, plan, progress=progress, should_stop=should_stop
        )
