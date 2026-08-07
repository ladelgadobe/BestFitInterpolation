# -*- coding: utf-8 -*-
"""Behavioral tests for core.exceptions and core.deps."""

import pytest

from bestfitinterpolator.core import deps
from bestfitinterpolator.core.exceptions import (
    BFIError,
    DependencyMissing,
    InsufficientSamples,
    OperationCancelled,
)


def test_dependency_missing_carries_package_and_message():
    exc = DependencyMissing("scikit-learn")
    assert exc.package == "scikit-learn"
    assert "scikit-learn" in exc.user_message()
    assert isinstance(exc, BFIError)


def test_insufficient_samples_message():
    exc = InsufficientSamples("Ordinary Kriging", 10, 4)
    assert "Ordinary Kriging" in str(exc)
    assert "10" in str(exc) and "4" in str(exc)


def test_operation_cancelled_is_bfi_error():
    assert issubclass(OperationCancelled, BFIError)


def test_import_scipy_returns_module_when_available():
    pytest.importorskip("scipy")
    assert deps.import_scipy().__name__ == "scipy"
    assert deps.import_scipy_rbf().__name__ == "Rbf"


def test_check_imports_reports_all_deps():
    res = deps.check_imports()
    assert set(res) == {"scipy", "scikit-learn", "joblib"}
    assert all(isinstance(v, bool) for v in res.values())
