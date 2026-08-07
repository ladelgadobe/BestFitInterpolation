# -*- coding: utf-8 -*-
"""Validation metrics — the single implementation of the RMSE / RMSE% / MAE /
R² / Pearson r / LCCC set formerly duplicated across every tab controller.

Numerics are byte-close to the legacy BestFitInterpolator._rmse/_mae/... so
cross-validation results are unchanged by the restructure.
"""

from __future__ import annotations

import numpy as np

from .types import Metrics


def rmse(obs, pred) -> float:
    obs = np.asarray(obs, dtype=float)
    pred = np.asarray(pred, dtype=float)
    return float(np.sqrt(np.nanmean((obs - pred) ** 2)))


def rmse_pct(obs, pred) -> float:
    obs = np.asarray(obs, dtype=float)
    value = rmse(obs, pred)
    mu = float(np.nanmean(obs))
    if not np.isfinite(mu) or abs(mu) < 1e-12:
        return float("nan")
    return float(value / mu * 100.0)


def mae(obs, pred) -> float:
    o = np.asarray(obs, dtype=float)
    p = np.asarray(pred, dtype=float)
    return float(np.nanmean(np.abs(o - p)))


def r2(obs, pred) -> float:
    o = np.asarray(obs, dtype=float)
    p = np.asarray(pred, dtype=float)
    mask = np.isfinite(o) & np.isfinite(p)
    if mask.sum() < 2:
        return float("nan")
    o = o[mask]
    p = p[mask]
    ss_res = float(np.sum((o - p) ** 2))
    ss_tot = float(np.sum((o - np.mean(o)) ** 2))
    if ss_tot <= 0:
        return float("nan")
    return float(1.0 - ss_res / ss_tot)


def pearson_r(obs, pred) -> float:
    o = np.asarray(obs, dtype=float)
    p = np.asarray(pred, dtype=float)
    mask = np.isfinite(o) & np.isfinite(p)
    if mask.sum() < 2:
        return float("nan")
    o = o[mask]
    p = p[mask]
    cov = float(np.nanmean((o - np.nanmean(o)) * (p - np.nanmean(p))))
    so = float(np.nanstd(o))
    sp = float(np.nanstd(p))
    if so <= 0 or sp <= 0:
        return float("nan")
    return float(cov / (so * sp))


def lccc(obs, pred) -> float:
    """Lin's concordance correlation coefficient."""
    o = np.asarray(obs, dtype=float)
    p = np.asarray(pred, dtype=float)
    mask = np.isfinite(o) & np.isfinite(p)
    if mask.sum() < 2:
        return float("nan")
    o = o[mask]
    p = p[mask]
    mu_o = float(np.mean(o))
    mu_p = float(np.mean(p))
    std_o = float(np.std(o))
    std_p = float(np.std(p))
    cov = float(np.mean((o - mu_o) * (p - mu_p)))
    denom = std_o ** 2 + std_p ** 2 + (mu_o - mu_p) ** 2
    if not np.isfinite(denom) or abs(denom) < 1e-12:
        return float("nan")
    return float((2.0 * cov) / denom)


def compute_metrics(obs, pred) -> Metrics:
    """All standard metrics over the finite (obs, pred) pairs."""
    o = np.asarray(obs, dtype=float)
    p = np.asarray(pred, dtype=float)
    mask = np.isfinite(o) & np.isfinite(p)
    return Metrics(
        rmse=rmse(o, p),
        rmse_pct=rmse_pct(o, p),
        mae=mae(o, p),
        r2=r2(o, p),
        lccc=lccc(o, p),
        pearson_r=pearson_r(o, p),
        n=int(mask.sum()),
    )


# ---- IDW optimizer helpers (legacy IDW_optimized.py names preserved) --------

def mean_absolute_error(ypred, yobs) -> float:
    ypred = np.asarray(ypred, dtype=float).ravel()
    yobs = np.asarray(yobs, dtype=float).ravel()
    return float(np.mean(np.abs(ypred - yobs)))


def std_error(ypred, yobs) -> float:
    """Standard deviation of errors."""
    ypred = np.asarray(ypred, dtype=float).ravel()
    yobs = np.asarray(yobs, dtype=float).ravel()
    return float(np.std(ypred - yobs))


def calculate_isi(mae_value, sae, max_abs_ae, min_sae, max_sae) -> float:
    """ISI = normalized MAE + normalized SAE (IDW parameter-search score)."""
    if max_abs_ae <= 0:  # avoid division by zero
        normalized_mae = 0.0
    else:
        normalized_mae = mae_value / max_abs_ae

    if max_sae == min_sae:
        normalized_sae = 0.0
    else:
        normalized_sae = (sae - min_sae) / (max_sae - min_sae)

    return float(normalized_mae + normalized_sae)
