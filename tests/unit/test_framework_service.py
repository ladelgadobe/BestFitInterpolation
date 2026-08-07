# -*- coding: utf-8 -*-
"""Behavioral tests for framework_service — including the FALSE-SUCCESS
regression: the legacy framework recorded a method as run even when its
dispatch raised (framework_tab.py:2527 returned True from the except)."""

import numpy as np
import pytest

from bestfitinterpolator.core.exceptions import OperationCancelled
from bestfitinterpolator.core.methods import METHOD_REGISTRY
from bestfitinterpolator.core.methods.base import InterpolationMethod, MethodInfo
from bestfitinterpolator.core.types import CVPlan, TrainingData
from bestfitinterpolator.services.framework_service import rank_by_metric, run_comparison


def _data(n=30, seed=2):
    rng = np.random.default_rng(seed)
    xy = rng.uniform(0, 50, size=(n, 2))
    z = xy[:, 0] * 0.1 + rng.normal(0, 0.1, n)
    return TrainingData(xy=xy, values=z)


class _BoomMethod(InterpolationMethod):
    info = MethodInfo(key="boom", label="Boom", min_samples=1, requires=())

    def fit(self, data, params=None, *, progress=None, should_stop=None):
        raise RuntimeError("kaboom")


class _NeedsUnobtainium(InterpolationMethod):
    info = MethodInfo(key="unob", label="Unobtainium", min_samples=1, requires=("unobtainium",))

    def fit(self, data, params=None, *, progress=None, should_stop=None):
        raise AssertionError("must never be called when deps are missing")


@pytest.fixture
def fake_methods(monkeypatch):
    monkeypatch.setitem(METHOD_REGISTRY, "boom", _BoomMethod())
    monkeypatch.setitem(METHOD_REGISTRY, "unob", _NeedsUnobtainium())


def test_false_success_regression_failure_is_visible_not_ok(fake_methods):
    result = run_comparison(_data(), ["idw", "boom"], CVPlan(mode="kfold", folds=5),
                            params_by_method={"idw": {"p": 2.0, "n": 6}})
    by_key = {e.method_key: e for e in result.entries}
    assert by_key["idw"].status == "ok"
    assert by_key["boom"].status == "failed"
    assert "kaboom" in by_key["boom"].error
    assert by_key["boom"].cv is None
    # ranking never includes the failed method
    ranked = rank_by_metric(result, "rmse")
    assert [e.method_key for e in ranked] == ["idw"]


def test_missing_dependency_is_skipped_without_running(fake_methods):
    result = run_comparison(_data(), ["unob"], CVPlan(mode="kfold", folds=5))
    entry = result.entries[0]
    assert entry.status == "skipped_deps"
    assert "unobtainium" in entry.error


def test_insufficient_samples_is_skipped():
    result = run_comparison(_data(n=3), ["idw"], CVPlan(mode="loocv"))
    assert result.entries[0].status == "skipped_samples"


def test_cancellation_propagates(fake_methods):
    with pytest.raises(OperationCancelled):
        run_comparison(_data(), ["idw"], CVPlan(mode="loocv"), should_stop=lambda: True)


def test_progress_and_status_callbacks(fake_methods):
    seen = []
    statuses = []
    run_comparison(
        _data(), ["idw", "boom"], CVPlan(mode="kfold", folds=5),
        params_by_method={"idw": {"p": 2.0, "n": 6}},
        progress=lambda d, t: seen.append((d, t)),
        status=statuses.append,
    )
    assert seen == [(1, 2), (2, 2)]
    assert any("Inverse Distance" in s for s in statuses)
