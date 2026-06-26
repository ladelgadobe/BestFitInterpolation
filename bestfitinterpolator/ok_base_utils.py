# -*- coding: utf-8 -*-
"""
Shared helpers for the split Ordinary Kriging controllers.
All code comments are in English.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

try:
    from .kriging_reml import _HAS_SCIPY as _REML_SCIPY
except Exception:
    _REML_SCIPY = False


@dataclass
class OKStrategyDecision:
    """Small container for the selected kriging strategy."""
    mode: str
    sample_count: int
    reason: str


class OKStrategySelector:
    """Encapsulate the decision rule between MoM and REML.

    Current rule:
    - Automatic mode keeps the original rule: if REML is available and n < 100 -> REML
    - Manual REML is allowed only while n < 500 to avoid overloading the system
    - Otherwise -> MoM
    """

    def __init__(
        self,
        reml_available: Optional[bool] = None,
        automatic_reml_threshold: int = 100,
        manual_reml_limit: int = 500,
    ):
        self.reml_available = bool(_REML_SCIPY if reml_available is None else reml_available)
        self.automatic_reml_threshold = int(automatic_reml_threshold)
        self.manual_reml_limit = int(manual_reml_limit)

    def choose(self, sample_count: int, requested_mode: str = "Automatic") -> OKStrategyDecision:
        n = int(sample_count or 0)
        requested = str(requested_mode or "Automatic").strip().upper()
        if requested == "MOM":
            return OKStrategyDecision(
                mode="MoM",
                sample_count=n,
                reason="User selected MoM",
            )
        if requested == "REML":
            if not self.reml_available:
                return OKStrategyDecision(
                    mode="MoM",
                    sample_count=n,
                    reason="REML requested but backend is unavailable; using MoM",
                )
            if n >= self.manual_reml_limit:
                return OKStrategyDecision(
                    mode="MoM",
                    sample_count=n,
                    reason=f"REML requested but n >= {self.manual_reml_limit}; using MoM",
                )
            return OKStrategyDecision(
                mode="REML",
                sample_count=n,
                reason=f"User selected REML and n < {self.manual_reml_limit}",
            )
        if self.reml_available and n < self.automatic_reml_threshold:
            return OKStrategyDecision(
                mode="REML",
                sample_count=n,
                reason=f"REML available and n < {self.automatic_reml_threshold}",
            )
        return OKStrategyDecision(
            mode="MoM",
            sample_count=n,
            reason=(
                f"Using MoM because REML is unavailable" if not self.reml_available
                else f"Using MoM because n >= {self.automatic_reml_threshold}"
            ),
        )


def count_valid_samples(layer, field_name: str) -> int:
    """Count finite numeric values in a point layer field."""
    if layer is None or not field_name:
        return 0
    count = 0
    try:
        for feat in layer.getFeatures():
            try:
                value = float(feat[field_name])
            except Exception:
                continue
            if value == value:
                count += 1
    except Exception:
        return 0
    return count


def same_layer(layer_a, layer_b) -> bool:
    """Safely compare two QGIS layers."""
    if layer_a is None or layer_b is None:
        return False
    try:
        return layer_a.id() == layer_b.id()
    except Exception:
        return layer_a is layer_b
