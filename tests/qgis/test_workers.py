# -*- coding: utf-8 -*-
"""QSignalSpy tests for the worker contract: result_ready on success, failed
(never result_ready) on error, cancelled + no partial file on cancel,
dep_missing for missing packages."""

import os

import numpy as np
import pytest

pytestmark = pytest.mark.qgis


SQUARE_WKT = "POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))"


def _data(n=20, seed=3):
    from bestfitinterpolator.core.types import TrainingData

    rng = np.random.default_rng(seed)
    xy = rng.uniform(0, 10, size=(n, 2))
    z = 5.0 + 0.3 * xy[:, 0] + rng.normal(0, 0.05, n)
    return TrainingData(xy=xy, values=z)


def _run(worker, timeout=30000):
    """Start a worker and wait for it to finish, collecting all signals."""
    from qgis.PyQt.QtTest import QSignalSpy

    spies = {
        "result_ready": QSignalSpy(worker.result_ready),
        "failed": QSignalSpy(worker.failed),
        "cancelled": QSignalSpy(worker.cancelled),
        "dep_missing": QSignalSpy(worker.dep_missing),
    }
    finished = QSignalSpy(worker.finished)  # QThread.finished (not shadowed)
    worker.start()
    assert finished.wait(timeout), "worker did not finish in time"
    worker.wait(5000)
    return spies


def test_cv_worker_happy_path(qgis_app):
    from bestfitinterpolator.core.types import CVPlan, CVResult
    from bestfitinterpolator.workers import CVWorker

    worker = CVWorker(_data(), "idw", {"p": 2.0, "n": 6}, CVPlan(mode="loocv"))
    spies = _run(worker)
    assert len(spies["result_ready"]) == 1
    assert len(spies["failed"]) == 0
    result = spies["result_ready"][0][0]
    assert isinstance(result, CVResult)
    assert result.metrics.n == 20


def test_fit_worker_insufficient_samples_fails_cleanly(qgis_app):
    from bestfitinterpolator.workers import FitWorker

    worker = FitWorker(_data(n=2), "idw")
    spies = _run(worker)
    assert len(spies["failed"]) == 1
    assert len(spies["result_ready"]) == 0  # false-success regression, signal level
    assert "at least" in spies["failed"][0][0]


def test_interpolation_worker_writes_raster(qgis_app, tmp_path):
    from bestfitinterpolator.core.types import RasterResult
    from bestfitinterpolator.gis.raster_io import grid_from_bounds
    from bestfitinterpolator.workers import InterpolationWorker

    out = str(tmp_path / "worker_out.tif")
    worker = InterpolationWorker(
        _data(), "idw", {"p": 2.0, "n": 6},
        grid_from_bounds((0.0, 0.0, 10.0, 10.0), 1.0), [SQUARE_WKT], out,
    )
    spies = _run(worker)
    assert len(spies["result_ready"]) == 1
    assert isinstance(spies["result_ready"][0][0], RasterResult)
    assert os.path.isfile(out)


def test_interpolation_worker_cancel_no_partial_file(qgis_app, tmp_path):
    from bestfitinterpolator.gis.raster_io import grid_from_bounds
    from bestfitinterpolator.workers import InterpolationWorker

    out = str(tmp_path / "cancelled.tif")
    # tight grid so the worker has real work; cancel immediately
    worker = InterpolationWorker(
        _data(n=200, seed=5), "idw", {"p": 2.0, "n": 6},
        grid_from_bounds((0.0, 0.0, 10.0, 10.0), 0.05), [SQUARE_WKT], out,
    )
    # requestInterruption() is a no-op on a non-running thread — cancel as
    # soon as the thread actually starts.
    worker.started.connect(worker.cancel)
    spies = _run(worker, timeout=60000)
    assert len(spies["cancelled"]) == 1
    assert len(spies["result_ready"]) == 0
    assert not os.path.exists(out)      # truncated-raster regression


def test_worker_dep_missing_signal(qgis_app, monkeypatch):
    from bestfitinterpolator.core.exceptions import DependencyMissing
    from bestfitinterpolator.core.methods import METHOD_REGISTRY
    from bestfitinterpolator.core.methods.base import InterpolationMethod, MethodInfo
    from bestfitinterpolator.workers import FitWorker

    class _NoDeps(InterpolationMethod):
        info = MethodInfo(key="nodeps", label="NoDeps", min_samples=1, requires=())

        def fit(self, data, params=None, *, progress=None, should_stop=None):
            raise DependencyMissing("scikit-learn")

    monkeypatch.setitem(METHOD_REGISTRY, "nodeps", _NoDeps())
    worker = FitWorker(_data(), "nodeps")
    spies = _run(worker)
    assert len(spies["dep_missing"]) == 1
    assert "scikit-learn" in spies["dep_missing"][0][0]
    assert len(spies["failed"]) == 0
