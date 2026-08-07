# -*- coding: utf-8 -*-
"""Shared dataclasses — the contracts between core, services, workers and UI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol

import numpy as np


@dataclass
class TrainingData:
    """Point samples extracted from a layer, already validated finite."""

    xy: np.ndarray                                # (n, 2) float64
    values: np.ndarray                            # (n,)
    covariates: Optional[np.ndarray] = None       # (n, k) for RF/SVM/RK
    covariate_names: tuple = ()
    crs_authid: Optional[str] = None

    @property
    def n(self) -> int:
        return int(self.xy.shape[0])

    @property
    def x(self) -> np.ndarray:
        return self.xy[:, 0]

    @property
    def y(self) -> np.ndarray:
        return self.xy[:, 1]


@dataclass(frozen=True)
class GridSpec:
    """A north-up output grid. Cell centers follow the legacy convention:
    x = xmin + px*(col+0.5), y = ymax - px*(row+0.5)."""

    geotransform: tuple                            # GDAL 6-tuple
    shape: tuple                                   # (rows, cols)
    crs_wkt: str = ""

    @property
    def n_rows(self) -> int:
        return int(self.shape[0])

    @property
    def n_cols(self) -> int:
        return int(self.shape[1])

    @property
    def pixel_size(self) -> float:
        return float(self.geotransform[1])

    def cell_centers(self):
        """Return (xs, ys) flattened row-major arrays of every cell center."""
        gt = self.geotransform
        cols = np.arange(self.n_cols)
        rows = np.arange(self.n_rows)
        x_coords = gt[0] + gt[1] * (cols + 0.5)
        y_coords = gt[3] + gt[5] * (rows + 0.5)
        xx, yy = np.meshgrid(x_coords, y_coords)
        return xx.ravel(), yy.ravel()


@dataclass(frozen=True)
class CVPlan:
    mode: str                       # "loocv" | "kfold"
    folds: Optional[int] = None
    seed: int = 42

    @staticmethod
    def automatic(n: int) -> "CVPlan":
        from .cv import decide_automatic_cv

        mode, folds = decide_automatic_cv(n)
        return CVPlan(mode=mode, folds=folds)

    def label(self) -> str:
        if self.mode == "loocv":
            return "LOOCV"
        return f"{self.folds}-fold"


@dataclass
class Metrics:
    rmse: float
    rmse_pct: float
    mae: float
    r2: float
    lccc: float
    pearson_r: float
    n: int


class FittedModel(Protocol):
    def predict(
        self,
        xy: np.ndarray,
        covariates: Optional[np.ndarray] = None,
        *,
        progress: Optional[Callable] = None,
        should_stop: Optional[Callable] = None,
    ) -> np.ndarray: ...


@dataclass
class FitResult:
    model: FittedModel
    params: dict                    # resolved hyperparameters
    diagnostics: dict = field(default_factory=dict)


@dataclass
class CVResult:
    observed: np.ndarray
    predicted: np.ndarray
    metrics: Metrics
    plan: CVPlan
    params: dict
    per_fold: list = field(default_factory=list)


@dataclass
class VariogramModel:
    model: str                      # "spherical" | "exponential" | "gaussian"
    nugget: float
    psill: float
    range_: float
    strategy: str = "mom"           # "mom" | "reml"
    fit_report: dict = field(default_factory=dict)

    @property
    def sill(self) -> float:
        return float(self.nugget) + float(self.psill)


@dataclass
class RasterResult:
    path: str
    grid: GridSpec
    method_key: str
    params: dict
    layer_name: str = ""
    stats: dict = field(default_factory=dict)


@dataclass
class FrameworkEntry:
    method_key: str
    status: str                     # "ok" | "failed" | "skipped_deps" | "skipped_samples"
    cv: Optional[CVResult] = None
    error: Optional[str] = None


@dataclass
class FrameworkResult:
    entries: list = field(default_factory=list)

    def successful(self) -> list:
        return [e for e in self.entries if e.status == "ok"]
