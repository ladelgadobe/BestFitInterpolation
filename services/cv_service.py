# -*- coding: utf-8 -*-
"""Cross-validation orchestration over the method registry."""

from __future__ import annotations

from ..core.methods import get_method
from ..core.types import CVPlan, CVResult, TrainingData


def run_cv(
    data: TrainingData,
    method_key: str,
    params: dict | None,
    plan: CVPlan | None = None,
    *,
    progress=None,
    should_stop=None,
) -> CVResult:
    """CV for one method. ``plan=None`` applies the automatic policy
    (LOOCV ≤100, 10-fold ≤1000, else 5-fold)."""
    method = get_method(method_key)
    method.validate(data)
    if plan is None:
        plan = CVPlan.automatic(data.n)
    return method.cross_validate(
        data, params, plan, progress=progress, should_stop=should_stop
    )
