# -*- coding: utf-8 -*-
"""Cross-validation: the shared automatic policy (moved verbatim from
validation_policy.py), fold generation (formerly duplicated ×5), and the
generic fit-per-fold runner every interpolation method uses by default."""

from __future__ import annotations

import numpy as np

from .exceptions import OperationCancelled
from .metrics import compute_metrics
from .types import CVPlan, CVResult, TrainingData

AUTO_CV_LOOCV_MAX_SAMPLES = 100
AUTO_CV_TEN_FOLD_MAX_SAMPLES = 1000

AUTO_CV_HELP_TEXT = (
    "Automatic cross-validation selects the validation strategy from the sample size. "
    "It uses LOOCV for up to and including 100 samples (n <= 100). "
    "Starting at 101 samples (n >= 101), it switches to K-Fold. "
    "From 101 to 1000 samples, Automatic uses 10 folds; above 1000 samples, it uses 5 folds. "
    "LOOCV leaves one sample out at a time and validates on that sample. "
    "K-Fold splits the samples into k groups, trains on k-1 groups, and validates on the remaining group."
)


def decide_automatic_cv(sample_count):
    """Return ``(mode, folds)`` for the shared automatic CV policy."""
    n = int(sample_count)
    if n <= AUTO_CV_LOOCV_MAX_SAMPLES:
        return "loocv", None
    if n <= AUTO_CV_TEN_FOLD_MAX_SAMPLES:
        return "kfold", 10
    return "kfold", 5


def kfold_indices(n_samples, n_splits=5, shuffle=True, random_state=42):
    """Lightweight replacement for sklearn KFold; yields (train_idx, test_idx).
    Semantics identical to the legacy IDW_optimized._kfold_indices."""
    n_splits = int(max(2, min(n_splits, n_samples)))
    idx = np.arange(n_samples)
    if shuffle:
        rng = np.random.default_rng(int(random_state))
        rng.shuffle(idx)

    fold_sizes = np.full(n_splits, n_samples // n_splits, dtype=int)
    fold_sizes[: n_samples % n_splits] += 1

    current = 0
    for fold_size in fold_sizes:
        start, stop = current, current + fold_size
        test_idx = idx[start:stop]
        train_idx = np.concatenate([idx[:start], idx[stop:]])
        current = stop
        yield train_idx, test_idx


def loocv_indices(n_samples):
    """Leave-one-out folds."""
    idx = np.arange(n_samples)
    for i in range(n_samples):
        yield np.delete(idx, i), idx[i : i + 1]


def fold_indices(n_samples, plan: CVPlan):
    if plan.mode == "loocv":
        return loocv_indices(n_samples)
    return kfold_indices(
        n_samples, n_splits=plan.folds or 5, shuffle=True, random_state=plan.seed
    )


def run_cross_validation(
    method,
    data: TrainingData,
    params: dict,
    plan: CVPlan,
    *,
    progress=None,
    should_stop=None,
) -> CVResult:
    """Generic fit-per-fold CV. ``method`` follows the InterpolationMethod
    protocol; ``params`` must already be resolved (no auto-tuning inside the
    folds — tuning happens once on the full data, matching legacy behavior)."""
    n = data.n
    observed = np.asarray(data.values, dtype=float)
    predicted = np.full(n, np.nan, dtype=float)

    folds = list(fold_indices(n, plan))
    total = len(folds)
    for i, (train_idx, test_idx) in enumerate(folds):
        if should_stop is not None and should_stop():
            raise OperationCancelled()
        train = TrainingData(
            xy=data.xy[train_idx],
            values=observed[train_idx],
            covariates=None if data.covariates is None else data.covariates[train_idx],
            covariate_names=data.covariate_names,
            crs_authid=data.crs_authid,
        )
        fit = method.fit(train, params=params, should_stop=should_stop)
        predicted[test_idx] = fit.model.predict(
            data.xy[test_idx],
            covariates=None if data.covariates is None else data.covariates[test_idx],
            should_stop=should_stop,
        )
        if progress is not None:
            progress(i + 1, total)

    return CVResult(
        observed=observed,
        predicted=predicted,
        metrics=compute_metrics(observed, predicted),
        plan=plan,
        params=dict(params or {}),
    )
