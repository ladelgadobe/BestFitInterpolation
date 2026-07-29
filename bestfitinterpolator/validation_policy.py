# -*- coding: utf-8 -*-
"""Shared automatic cross-validation policy and user-facing explanation."""

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
