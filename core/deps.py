# -*- coding: utf-8 -*-
"""Optional dependency helpers.

scipy ships with QGIS but may be absent in exotic builds; the scikit-learn
stack is provisioned into extlibs/ and may be missing until the download
finishes. Core code calls these guards inside functions — never a top-level
``import scipy`` / ``import sklearn`` anywhere in the plugin — and raises
:class:`DependencyMissing`, which workers surface as their ``dep_missing``
signal.
"""
from .exceptions import DependencyMissing


def import_scipy():
    try:
        import scipy

        return scipy
    except Exception:
        raise DependencyMissing("scipy")


def import_scipy_spatial():
    try:
        from scipy import spatial

        return spatial
    except Exception:
        raise DependencyMissing("scipy")


def import_scipy_linalg():
    try:
        from scipy import linalg

        return linalg
    except Exception:
        raise DependencyMissing("scipy")


def import_scipy_optimize():
    try:
        from scipy import optimize

        return optimize
    except Exception:
        raise DependencyMissing("scipy")


def import_scipy_rbf():
    try:
        from scipy.interpolate import Rbf

        return Rbf
    except Exception:
        raise DependencyMissing("scipy")


def import_sklearn():
    try:
        import sklearn

        return sklearn
    except Exception:
        raise DependencyMissing("scikit-learn")


# (display name, import module) for the optional Python deps.
PY_DEPS = (("scipy", "scipy"), ("scikit-learn", "sklearn"), ("joblib", "joblib"))


def check_imports() -> dict:
    """Return {display_name: importable_bool} — feeds the dependency panel and
    lets controllers grey out ML methods before provisioning finishes."""
    res = {}
    for name, mod in PY_DEPS:
        try:
            __import__(mod)
            res[name] = True
        except Exception:
            res[name] = False
    return res
