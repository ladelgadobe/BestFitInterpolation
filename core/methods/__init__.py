# -*- coding: utf-8 -*-
"""The method registry — every tab and the Framework consume this one dict.

Import-safe at plugin load: no method module imports scipy/sklearn at top
level; heavy imports happen inside fit/predict via core.deps.
"""

from __future__ import annotations

from ..deps import check_imports
from .base import InterpolationMethod, MethodInfo
from .idw import IDWMethod
from .kriging_ok import OrdinaryKrigingMethod
from .rf import RandomForestMethod
from .rk import RegressionKrigingMethod
from .svm import SVMMethod
from .tps import TPSMethod

METHOD_REGISTRY: dict = {}


def register(method: InterpolationMethod) -> None:
    METHOD_REGISTRY[method.info.key] = method


def get_method(key: str) -> InterpolationMethod:
    try:
        return METHOD_REGISTRY[key]
    except KeyError:
        raise ValueError(
            f"Unknown interpolation method {key!r}. "
            f"Known methods: {sorted(METHOD_REGISTRY)}"
        )


def available_methods(check_deps: bool = False) -> list:
    """MethodInfo list; with check_deps=True, methods whose required packages
    are not importable are filtered out (feeds the dependency panel)."""
    infos = [m.info for m in METHOD_REGISTRY.values()]
    if not check_deps:
        return infos
    status = check_imports()
    return [
        info
        for info in infos
        if all(status.get(pkg, False) for pkg in info.requires)
    ]


register(IDWMethod())
register(TPSMethod())
register(OrdinaryKrigingMethod())
register(RandomForestMethod())
register(SVMMethod())
register(RegressionKrigingMethod())
