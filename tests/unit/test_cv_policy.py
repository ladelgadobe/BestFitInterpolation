# -*- coding: utf-8 -*-
"""Behavioral tests for fold generation and the CVPlan wrapper."""

import numpy as np

from bestfitinterpolator.core.cv import fold_indices, kfold_indices, loocv_indices
from bestfitinterpolator.core.types import CVPlan


def test_kfold_partitions_every_sample_exactly_once():
    folds = list(kfold_indices(23, n_splits=5, shuffle=True, random_state=42))
    assert len(folds) == 5
    all_test = np.concatenate([test for _, test in folds])
    assert sorted(all_test.tolist()) == list(range(23))
    for train, test in folds:
        assert set(train).isdisjoint(set(test))
        assert len(train) + len(test) == 23


def test_kfold_deterministic_with_fixed_seed():
    a = [t.tolist() for _, t in kfold_indices(50, 5, True, 42)]
    b = [t.tolist() for _, t in kfold_indices(50, 5, True, 42)]
    c = [t.tolist() for _, t in kfold_indices(50, 5, True, 7)]
    assert a == b
    assert a != c


def test_loocv_yields_n_folds():
    folds = list(loocv_indices(8))
    assert len(folds) == 8
    for i, (train, test) in enumerate(folds):
        assert test.tolist() == [i]
        assert len(train) == 7


def test_cvplan_automatic_matches_policy():
    assert CVPlan.automatic(50).mode == "loocv"
    assert CVPlan.automatic(500) == CVPlan(mode="kfold", folds=10)
    assert CVPlan.automatic(5000) == CVPlan(mode="kfold", folds=5)


def test_fold_indices_dispatches_on_plan():
    assert len(list(fold_indices(6, CVPlan(mode="loocv")))) == 6
    assert len(list(fold_indices(60, CVPlan(mode="kfold", folds=10)))) == 10
