# -*- coding: utf-8 -*-
"""Behavioral tests for the automatic cross-validation policy.

Ported from the old test_validation_presentation_contract.py. Targets the
legacy validation_policy.py until the policy moves to core/cv.py; the
assertions stay identical across that move.
"""

import pytest


def _policy():
    try:
        from bestfitinterpolator.core import cv as policy  # new home
        return policy
    except ImportError:
        from bestfitinterpolator import validation_policy as policy  # legacy
        return policy


def test_auto_cv_boundaries():
    policy = _policy()
    assert policy.decide_automatic_cv(100) == ("loocv", None)
    assert policy.decide_automatic_cv(101) == ("kfold", 10)
    assert policy.decide_automatic_cv(1000) == ("kfold", 10)
    assert policy.decide_automatic_cv(1001) == ("kfold", 5)


def test_auto_cv_small_n_edge_cases():
    policy = _policy()
    assert policy.decide_automatic_cv(1) == ("loocv", None)
    assert policy.decide_automatic_cv(2) == ("loocv", None)


def test_help_text_matches_policy():
    policy = _policy()
    assert "100 samples" in policy.AUTO_CV_HELP_TEXT
    assert "101 samples" in policy.AUTO_CV_HELP_TEXT
    assert "10 folds" in policy.AUTO_CV_HELP_TEXT
    assert "5 folds" in policy.AUTO_CV_HELP_TEXT
