# -*- coding: utf-8 -*-
"""Framework comparison — every method through the SAME registry.

Replaces the legacy framework tab flow that simulated button clicks on other
tabs and scraped their matplotlib figures, and that reported success even
when a method's dispatch raised (framework_tab.py:2527 returned True from the
except block). Here a failed method is a visible FrameworkEntry row with
status="failed"; only status=="ok" entries can be ranked."""

from __future__ import annotations

from ..core.deps import check_imports
from ..core.exceptions import DependencyMissing, InsufficientSamples, OperationCancelled
from ..core.methods import get_method
from ..core.types import CVPlan, FrameworkEntry, FrameworkResult, TrainingData
from ..logger import get_logger
from .cv_service import run_cv

logger = get_logger(__name__)


def run_comparison(
    data: TrainingData,
    method_keys,
    plan: CVPlan | None = None,
    params_by_method: dict | None = None,
    *,
    progress=None,
    status=None,
    should_stop=None,
) -> FrameworkResult:
    """Cross-validate each method; failures become visible rows, never
    fabricated passes. Cancellation propagates immediately."""
    params_by_method = params_by_method or {}
    deps = check_imports()
    entries = []
    total = len(list(method_keys))

    for i, key in enumerate(method_keys):
        if should_stop is not None and should_stop():
            raise OperationCancelled()
        method = get_method(key)
        if status is not None:
            status(f"Validating {method.info.label}…")

        missing = [pkg for pkg in method.info.requires if not deps.get(pkg, False)]
        if missing:
            entries.append(
                FrameworkEntry(
                    method_key=key,
                    status="skipped_deps",
                    error=f"Missing packages: {', '.join(missing)}",
                )
            )
            if progress is not None:
                progress(i + 1, total)
            continue

        try:
            cv = run_cv(
                data,
                key,
                params_by_method.get(key),
                plan,
                should_stop=should_stop,
            )
            entries.append(FrameworkEntry(method_key=key, status="ok", cv=cv))
        except OperationCancelled:
            raise
        except InsufficientSamples as exc:
            entries.append(
                FrameworkEntry(method_key=key, status="skipped_samples", error=str(exc))
            )
        except DependencyMissing as exc:
            entries.append(
                FrameworkEntry(method_key=key, status="skipped_deps", error=exc.user_message())
            )
        except Exception as exc:
            logger.exception("Framework validation failed for method %s", key)
            entries.append(FrameworkEntry(method_key=key, status="failed", error=str(exc)))

        if progress is not None:
            progress(i + 1, total)

    return FrameworkResult(entries=entries)


def rank_by_metric(result: FrameworkResult, metric: str = "rmse", ascending: bool = True):
    """Rank ONLY successful entries by a Metrics field."""
    ok = [e for e in result.entries if e.status == "ok" and e.cv is not None]
    return sorted(
        ok,
        key=lambda e: getattr(e.cv.metrics, metric),
        reverse=not ascending,
    )
