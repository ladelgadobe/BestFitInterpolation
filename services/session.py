# -*- coding: utf-8 -*-
"""BFISession — the ONLY cross-tab state. Controllers read and write the
session; they never reach into each other's widgets (the legacy framework
tab drove other tabs by clicking their buttons and scraping their figures)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..core.exceptions import InvalidDataError
from ..core.types import CVResult, FitResult, TrainingData


@dataclass
class BFISession:
    # Data tab selections (layer refs live on the UI thread only)
    points_layer: object = None
    variable_field: str = ""
    boundary_layer: object = None
    pixel_size: float = 10.0
    export_rasters: bool = True
    output_dir: str = ""

    # Extracted training data (plain numpy — safe to hand to workers)
    training_data: Optional[TrainingData] = None

    # Covariates (ML tab writes; RF/SVM/RK and the Framework read)
    covariate_paths: dict = field(default_factory=dict)   # name -> raster path
    covariate_selection: list = field(default_factory=list)
    use_xy_features: bool = True

    # Last results per method key ("idw", "tps", "ok", "rf", "svm", "rk")
    fit_results: dict = field(default_factory=dict)        # key -> FitResult
    cv_results: dict = field(default_factory=dict)         # key -> CVResult

    def require_training_data(self) -> TrainingData:
        if self.training_data is None:
            raise InvalidDataError(
                "Load a point layer and select a variable in the Data tab first."
            )
        return self.training_data

    def selected_covariate_paths(self) -> list:
        return [
            self.covariate_paths[name]
            for name in self.covariate_selection
            if name in self.covariate_paths
        ]

    def store_fit(self, method_key: str, result: FitResult) -> None:
        self.fit_results[method_key] = result

    def store_cv(self, method_key: str, result: CVResult) -> None:
        self.cv_results[method_key] = result

    def reset_results(self) -> None:
        self.fit_results.clear()
        self.cv_results.clear()
