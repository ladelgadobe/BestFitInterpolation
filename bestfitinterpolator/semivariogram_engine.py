"""Shared semivariogram primitives and unchanged named fitting/validation policies.

Ordinary MoM, Ordinary REML and residual grid fitting intentionally retain their
existing mathematical policies. UI controllers delegate to this numerical engine.
"""
from dataclasses import dataclass
from typing import List
import numpy as np
from .variogram_utils import bin_experimental_variogram
from .performance_policy import is_dense_dataset, is_massive_dataset, representative_sample_indices
from .validation_policy import decide_automatic_cv
from .kriging_ordinary import ordinary_kriging_interpolation
from .reml_bridge import fit_ok_reml_interface, cv_ok_reml_interface
from .kriging_reml import _HAS_SCIPY as _HAS_REML

GEOSTAT_DENSE_HOLDOUT_MAX_TEST=2000
GEOSTAT_MASSIVE_HOLDOUT_MAX_TEST=5000
REML_SAMPLE_LIMIT=500

@dataclass
class VariogramFit:
    """Container for one residual variogram fit."""
    model: str
    nugget: float
    psill: float
    range_: float
    sse: float
    weak_structure: bool = False

class _OrdinaryPolicy:
    def _normalize_model_token(self, txt: str) -> str:
        t = (txt or "").strip().lower()
        if t.startswith(("sph", "esf")):   # Spherical, including its existing Spanish token alias.
            return "spherical"
        if t.startswith(("gau", "gaus")):  # Gaussian
            return "gaussian"
        if t.startswith(("exp", "expon")): # Exponential
            return "exponential"
        if "spher" in t:
            return "spherical"
        if "gaus" in t:
            return "gaussian"
        return "exponential"


    def _model_func(self, h, model, nugget, psill, rng):
        """Theoretical semivariogram models: Spherical / Exponential / Gaussian."""
        h = np.asarray(h, dtype=float)
        c0 = float(nugget)
        c = float(psill)
        a = max(float(rng), 1e-9)
        if model == "spherical":
            hr = np.clip(h / a, 0.0, 1.0)
            sph = c * (1.5 * hr - 0.5 * (hr ** 3))
            return np.where(h <= a, c0 + sph, c0 + c)
        elif model == "gaussian":
            return c0 + c * (1.0 - np.exp(-(h * h) / (a * a)))
        else:
            # exponential
            return c0 + c * (1.0 - np.exp(-h / a))


    def _guess_initial_params(self, lags, gamma, cutoff, model="exponential"):
        """Estimate a closer automatic MoM fit for (nugget, psill, range).

        The previous version used only very simple heuristics (tail max/median and
        first crossing of 95% of the sill). That could leave the initial theoretical
        curve visibly far from the experimental semivariogram, especially for the
        spherical model. Here we keep the MoM spirit, but refine the automatic
        starting values with a lightweight coarse search over the range and nugget,
        solving the partial sill analytically for each candidate.
        """
        lags = np.asarray(lags, dtype=float)
        gamma = np.asarray(gamma, dtype=float)
        keep = np.isfinite(lags) & np.isfinite(gamma) & (lags > 0)
        lags = lags[keep]
        gamma = gamma[keep]

        if lags.size == 0:
            return 0.0, 1.0, max(1.0, cutoff * 0.4)

        # Sort to ensure monotone support for the fitting search
        order = np.argsort(lags)
        lags = lags[order]
        gamma = gamma[order]

        # --- Base robust heuristics ---
        first_vals = gamma[:max(1, min(3, gamma.size))]
        tail_vals = gamma[-max(3, max(1, gamma.size // 3)):]

        first_bin = float(first_vals[0]) if first_vals.size else 0.0
        first_max = float(np.nanmax(first_vals)) if first_vals.size else first_bin

        # Linear back-extrapolation using the first two bins when possible.
        # This gives a more permissive estimate for cases with a relevant nugget effect
        # and avoids biasing the search toward unrealistically low nuggets.
        nugget_intercept = first_bin
        if lags.size >= 2:
            h1, h2 = float(lags[0]), float(lags[1])
            g1, g2 = float(gamma[0]), float(gamma[1])
            if abs(h2 - h1) > 1e-12:
                slope = (g2 - g1) / (h2 - h1)
                nugget_intercept = float(g1 - slope * h1)

        nugget_floor = 0.75 * first_bin
        nugget_seed = float(max(0.0, max(max(0.0, nugget_intercept), nugget_floor, first_bin)))
        plateau_seed = float(np.nanmedian(tail_vals))
        max_seed = float(np.nanmax(gamma))
        sill_total_seed = max(plateau_seed, max_seed, first_max, nugget_seed + 1e-6)

        # Initial range seed from the first empirical crossing near the plateau
        target = 0.90 * sill_total_seed
        idx = np.where(gamma >= target)[0]
        if idx.size > 0:
            range_seed = float(lags[idx[0]])
        else:
            range_seed = float(0.60 * cutoff)
        range_seed = max(range_seed, float(np.nanmin(lags)), 1e-9)

        # Candidate nugget values: include low and high possibilities from the first bins.
        # This preserves flexibility for real nugget effects instead of favoring small nuggets.
        nugget_cap = max(0.0, min(first_max, 0.90 * sill_total_seed))
        nugget_seed = float(np.clip(nugget_seed, 0.0, nugget_cap)) if nugget_cap > 0 else 0.0
        nugget_candidates = np.array([nugget_seed], dtype=float)

        # Candidate ranges spanning from early structure to almost the cutoff.
        lag_min = max(float(np.nanmin(lags)), 1e-9)
        lag_max = max(float(np.nanmax(lags)), lag_min)
        low = max(lag_min, 0.20 * range_seed)
        high = max(low * 1.05, min(float(cutoff), max(lag_max * 1.15, range_seed * 1.8, low)))
        range_candidates = np.unique(np.concatenate([
            np.linspace(low, high, 28),
            np.array([range_seed, 0.5 * cutoff, 0.75 * cutoff, lag_max], dtype=float),
        ]))
        range_candidates = range_candidates[np.isfinite(range_candidates) & (range_candidates > 0)]

        # Give slightly more weight to the first half of the variogram so the
        # automatic fit follows the experimental points more closely near the origin.
        lag_scale = max(float(np.nanmedian(lags)), 1e-9)
        weights = 1.0 / (1.0 + (lags / lag_scale))

        best = None
        model_token = self._normalize_model_token(model)

        for nugget in nugget_candidates:
            y = gamma - float(nugget)
            for rng in range_candidates:
                basis = self._model_func(lags, model_token, 0.0, 1.0, float(rng))
                denom = float(np.sum(weights * basis * basis))
                if denom <= 0:
                    continue
                psill = float(np.sum(weights * basis * y) / denom)
                psill = max(psill, 1e-9)

                pred = float(nugget) + psill * basis
                sse = float(np.sum(weights * (gamma - pred) ** 2))

                # Very small regularization only on the range. We intentionally avoid
                # penalizing larger nuggets here because some datasets may genuinely
                # present a relevant nugget effect right from the initial fit.
                sse += 1e-6 * (rng / max(cutoff, 1e-9)) ** 2

                if (best is None) or (sse < best[0]):
                    best = (sse, float(nugget), float(psill), float(rng))

        if best is None:
            floor=getattr(self,"_fallback_psill_floor",1e-6)
            return nugget_seed, max(sill_total_seed - nugget_seed, floor), range_seed

        _, nugget, psill, rng = best
        return nugget, psill, rng


    @staticmethod
    def _model_text_from_token(token: str) -> str:
        token = str(token or "").strip().lower()
        if token.startswith("sph"):
            return "Sph"
        if token.startswith("gau"):
            return "Gau"
        return "Exp"


    @staticmethod
    def _validation_metrics(obs, pred):
        obs = np.asarray(obs, dtype=float)
        pred = np.asarray(pred, dtype=float)
        mask = np.isfinite(obs) & np.isfinite(pred)
        obs = obs[mask]
        pred = pred[mask]
        if obs.size < 2:
            raise ValueError("not enough finite validation predictions")
        err = obs - pred
        rmse = float(np.sqrt(np.mean(err ** 2)))
        mean_obs = float(np.mean(obs))
        rmse_pct = float(100.0 * rmse / abs(mean_obs)) if abs(mean_obs) > 1e-12 else float("nan")
        mae = float(np.mean(np.abs(err)))
        ss_tot = float(np.sum((obs - np.mean(obs)) ** 2))
        r2 = float(1.0 - (np.sum(err ** 2) / ss_tot)) if ss_tot > 0 else float("nan")
        if obs.size >= 2 and float(np.std(obs, ddof=1)) > 0 and float(np.std(pred, ddof=1)) > 0:
            pearson = float(np.corrcoef(obs, pred)[0, 1])
        else:
            pearson = float("nan")
        mean_pred = float(np.mean(pred))
        std_obs = float(np.std(obs))
        std_pred = float(np.std(pred))
        cov = float(np.mean((obs - mean_obs) * (pred - mean_pred)))
        denom = std_obs ** 2 + std_pred ** 2 + (mean_obs - mean_pred) ** 2
        lccc = float((2.0 * cov) / denom) if abs(denom) > 1e-12 else float("nan")
        return {
            "rmse": rmse,
            "rmse_pct": rmse_pct,
            "mae": mae,
            "r2": r2,
            "pearson": pearson,
            "lccc": lccc,
        }


    def _evaluate_model_cv(self, model_key: str, x, y, z, cutoff, lagw):
        lags, gamma = self._bin_variogram(x, y, z, cutoff, lagw)
        nugget, psill, rng = self._guess_initial_params(lags, gamma, cutoff, model=model_key)
        preds = np.full(z.size, np.nan, dtype=float)
        if is_dense_dataset(z.size):
            max_test = GEOSTAT_MASSIVE_HOLDOUT_MAX_TEST if is_massive_dataset(z.size) else GEOSTAT_DENSE_HOLDOUT_MAX_TEST
            test_size = min(max_test, max(100, int(round(0.2 * z.size))), z.size - 5)
            test_idx, _ = representative_sample_indices(
                x,
                y,
                max_samples=max(2, int(test_size)),
                random_state=20,
            )
            folds = [np.asarray(test_idx, dtype=int)]
            selection = "spatial_holdout"
        else:
            mode, k = decide_automatic_cv(z.size)
            if mode == "loocv":
                folds = [np.asarray([i], dtype=int) for i in range(z.size)]
            else:
                shuffled = np.arange(z.size, dtype=int)
                np.random.default_rng(20).shuffle(shuffled)
                folds = [part for part in np.array_split(shuffled, int(k)) if part.size]
            selection = mode
        for test_idx in folds:
            train = np.ones(z.size, dtype=bool)
            train[test_idx] = False
            fold_pred = ordinary_kriging_interpolation(
                x[train], y[train], z[train], x[test_idx], y[test_idx],
                nugget=nugget, psill=psill, var_range=rng, model=model_key
            )
            preds[test_idx] = np.asarray(fold_pred, dtype=float).ravel()
        metrics = self._validation_metrics(z, preds)
        metrics.update({
            "model": self._model_text_from_token(model_key),
            "model_key": model_key,
            "nugget": float(nugget),
            "psill": float(psill),
            "range": float(rng),
            "selection": selection,
            "validation_n": int(np.count_nonzero(np.isfinite(preds))),
        })
        return metrics


    def _evaluate_model_variogram_fit(self, model_key: str, x, y, z, cutoff, lagw):
        """Evaluate a candidate model using experimental-semivariogram fit only."""
        lags, gamma = self._bin_variogram(x, y, z, cutoff, lagw)
        nugget, psill, rng = self._guess_initial_params(lags, gamma, cutoff, model=model_key)
        if lags.size:
            theoretical = self._model_func(lags, model_key, nugget, psill, rng)
            residual = np.asarray(gamma, dtype=float) - np.asarray(theoretical, dtype=float)
            sse = float(np.nansum(residual ** 2))
            rmse = float(np.sqrt(np.nanmean(residual ** 2)))
        else:
            sse = float("inf")
            rmse = float("nan")
        return {
            "model": self._model_text_from_token(model_key),
            "model_key": model_key,
            "rmse": rmse,
            "rmse_pct": float("nan"),
            "mae": float("nan"),
            "r2": float("nan"),
            "pearson": float("nan"),
            "lccc": float("nan"),
            "sse": sse,
            "nugget": float(nugget),
            "psill": float(psill),
            "range": float(rng),
            "selection": "variogram_fit",
        }


    def _bin_variogram(self, x, y, z, cutoff, lag_width):
        return bin_experimental_variogram(x, y, z, cutoff, lag_width)

class _REMLPolicy(_OrdinaryPolicy):
    def _evaluate_model_cv(self, model_key: str, x, y, z, cutoff, lagw):
        lags, gamma = self._bin_variogram(x, y, z, cutoff, lagw)
        nugget, psill, rng = self._guess_initial_params(lags, gamma, cutoff, model=model_key)
        if self._use_reml and _HAS_REML and cv_ok_reml_interface is not None and not is_dense_dataset(z.size):
            sample_xyz = np.column_stack([x, y, z])
            fit = fit_ok_reml_interface(
                sample_xyz=sample_xyz,
                model=self._model_text_from_token(model_key),
                init_from_mom={"nugget": nugget, "psill": psill, "range": rng},
                random_state=123,
            )
            mode, k = decide_automatic_cv(z.size)
            cv = cv_ok_reml_interface(sample_xyz, fit, k=0 if mode == "loocv" else int(k))
            pred = cv.get("y_pred", cv.get("pred"))
            obs = cv.get("y_true", cv.get("obs", z))
            if pred is None:
                raise ValueError("REML CV did not return predictions")
            preds = np.asarray(pred, dtype=float)
            obs = np.asarray(obs, dtype=float)
            selection = "reml_cv"
            fitted_params = tuple(float(fit[key]) for key in ("nugget", "psill", "range"))
        else:
            preds = np.full(z.size, np.nan, dtype=float)
            if is_dense_dataset(z.size):
                max_test = GEOSTAT_MASSIVE_HOLDOUT_MAX_TEST if is_massive_dataset(z.size) else GEOSTAT_DENSE_HOLDOUT_MAX_TEST
                test_size = min(max_test, max(100, int(round(0.2 * z.size))), z.size - 5)
                test_idx, _ = representative_sample_indices(
                    x,
                    y,
                    max_samples=max(2, int(test_size)),
                    random_state=20,
                )
                folds = [np.asarray(test_idx, dtype=int)]
                selection = "spatial_holdout"
            else:
                mode, k = decide_automatic_cv(z.size)
                if mode == "loocv":
                    folds = [np.asarray([i], dtype=int) for i in range(z.size)]
                else:
                    shuffled = np.arange(z.size, dtype=int)
                    np.random.default_rng(20).shuffle(shuffled)
                    folds = [part for part in np.array_split(shuffled, int(k)) if part.size]
                selection = mode
            for test_idx in folds:
                train = np.ones(z.size, dtype=bool)
                train[test_idx] = False
                fold_pred = ordinary_kriging_interpolation(
                    x[train], y[train], z[train], x[test_idx], y[test_idx],
                    nugget=nugget, psill=psill, var_range=rng, model=model_key
                )
                preds[test_idx] = np.asarray(fold_pred, dtype=float).ravel()
            obs = z
            fitted_params = (float(nugget), float(psill), float(rng))
        metrics = self._validation_metrics(obs, preds)
        metrics.update({
            "model": self._model_text_from_token(model_key),
            "model_key": model_key,
            "nugget": float(nugget),
            "psill": float(psill),
            "range": float(rng),
            "selection": selection,
            "validation_n": int(np.count_nonzero(np.isfinite(preds))),
            "fitted_params": fitted_params,
        })
        return metrics


class _ResidualPolicy(_OrdinaryPolicy):
    def _guess_initial_params(self, lags, gamma, cutoff):
        if lags.size == 0:
            return 0.0, 1.0, max(1.0, cutoff * 0.4)
        nugget = float(max(0.0, np.nanmin(gamma[: max(1, min(3, gamma.size))])))
        plateau = float(np.nanmedian(gamma[-max(3, gamma.size // 4):]))
        sill_total = float(max(np.nanmax(gamma), plateau))
        sill_total = max(sill_total, nugget + 1e-6)
        target = 0.95 * sill_total
        idx = np.where(gamma >= target)[0]
        if idx.size > 0:
            rng = float(lags[idx[0]])
        else:
            rng = float(0.5 * cutoff)
        rng = max(rng, float(lags[0]) if lags.size else 1.0)
        return nugget, sill_total - nugget, rng


    def _fit_variogram_candidates(self, lags, gamma, cutoff) -> List[VariogramFit]:
        nugget0, psill0, range0 = self._guess_initial_params(lags, gamma, cutoff)
        candidates = []
        nugget_grid = [max(0.0, nugget0 * f) for f in (0.0, 0.5, 1.0, 1.5)]
        psill_grid = [max(1e-9, psill0 * f) for f in (0.5, 1.0, 1.5, 2.0)]
        range_grid = [max(1e-9, range0 * f) for f in (0.5, 0.75, 1.0, 1.25, 1.5)]
        weak_structure = False
        if gamma.size >= 3:
            head = float(np.nanmean(gamma[: min(3, gamma.size)]))
            tail = float(np.nanmean(gamma[-min(3, gamma.size):]))
            weak_structure = tail <= 0 or ((tail - head) / max(abs(tail), 1e-12) < 0.10)

        for model in ("spherical", "exponential", "gaussian"):
            best_fit = None
            for nugget in nugget_grid:
                for psill in psill_grid:
                    for range_ in range_grid:
                        theo = self._model_func(lags, model, nugget, psill, range_)
                        sse = float(np.nansum((gamma - theo) ** 2))
                        fit = VariogramFit(
                            model=model,
                            nugget=float(nugget),
                            psill=float(psill),
                            range_=float(range_),
                            sse=sse,
                            weak_structure=weak_structure,
                        )
                        if best_fit is None or fit.sse < best_fit.sse:
                            best_fit = fit
            if best_fit is not None:
                candidates.append(best_fit)
        return candidates


    @staticmethod
    def _validation_metrics(obs, pred):
        obs = np.asarray(obs, dtype=float).ravel()
        pred = np.asarray(pred, dtype=float).ravel()
        mask = np.isfinite(obs) & np.isfinite(pred)
        obs = obs[mask]
        pred = pred[mask]
        if obs.size < 2:
            raise ValueError("not enough finite validation predictions")
        err = pred - obs
        rmse = float(np.sqrt(np.mean(err ** 2)))
        mae = float(np.mean(np.abs(err)))
        ss_tot = float(np.sum((obs - np.mean(obs)) ** 2))
        r2 = float(1.0 - (np.sum(err ** 2) / ss_tot)) if ss_tot > 0 else float("nan")
        try:
            pearson = float(np.corrcoef(obs, pred)[0, 1])
        except Exception:
            pearson = float("nan")
        mean_obs = float(np.mean(obs))
        mean_pred = float(np.mean(pred))
        var_obs = float(np.var(obs))
        var_pred = float(np.var(pred))
        cov = float(np.mean((obs - mean_obs) * (pred - mean_pred)))
        denom = var_obs + var_pred + (mean_obs - mean_pred) ** 2
        lccc = float((2.0 * cov) / denom) if abs(denom) > 1e-12 else float("nan")
        return {"rmse": rmse, "mae": mae, "r2": r2, "pearson": pearson, "lccc": lccc, "n": int(obs.size)}


    def _residual_model_cv_metrics(self, x, y, z, fit):
        n = int(len(z))
        if n < 5:
            raise ValueError("at least 5 residuals are required")
        if n > 2000:
            test_idx, _ = representative_sample_indices(x, y, max_samples=2000, random_state=20)
            folds = [np.asarray(test_idx, dtype=int)]
            strategy = "spatial_holdout"
        elif n > 200:
            rng = np.random.default_rng(20)
            test_size = max(40, int(round(0.2 * n)))
            test_size = min(test_size, n - 5)
            folds = [np.sort(rng.choice(n, size=test_size, replace=False)).astype(int)]
            strategy = "holdout"
        else:
            k = min(5, n)
            idx = np.arange(n, dtype=int)
            rng = np.random.default_rng(20)
            rng.shuffle(idx)
            folds = [fold for fold in np.array_split(idx, k) if fold.size]
            strategy = f"{k}-fold"

        preds = np.full(n, np.nan, dtype=float)
        model_token = {"spherical": "Sph", "exponential": "Exp", "gaussian": "Gau"}[fit.model]
        for test_idx in folds:
            train_mask = np.ones(n, dtype=bool)
            train_mask[np.asarray(test_idx, dtype=int)] = False
            pred = ordinary_kriging_interpolation(
                x[train_mask],
                y[train_mask],
                z[train_mask],
                x[test_idx],
                y[test_idx],
                float(fit.nugget),
                float(fit.psill),
                float(fit.range_),
                model_token,
            )
            preds[test_idx] = np.asarray(pred, dtype=float).ravel()
        metrics = self._validation_metrics(z, preds)
        metrics["strategy"] = strategy
        return metrics


    def _select_best_variogram_fit(self, candidates, validation_rows):
        valid_rows = [
            row for row in (validation_rows or [])
            if np.isfinite(float(row.get("rmse", float("nan"))))
        ]
        if valid_rows:
            return sorted(
                valid_rows,
                key=lambda row: (
                    float(row.get("rmse", float("inf"))),
                    float(row.get("sse", float("inf"))),
                ),
            )[0]["fit"]
        return sorted(candidates, key=lambda item: item.sse)[0]


class _FrameworkPolicy(_OrdinaryPolicy):
    """Retain Framework token normalization with the shared MoM search."""
    @staticmethod
    def _normalize_model_token(model_text):
        token=str(model_text).strip().lower()
        if token.startswith("sph") or token.startswith("spher"): return "spherical"
        if token.startswith("exp"): return "exponential"
        if token.startswith("gau"): return "gaussian"
        return "exponential"

    def _model_func(self,h,model,nugget,psill,rng):
        return super()._model_func(h,self._normalize_model_token(model),nugget,psill,rng)


class _FrameworkSDIPolicy(_FrameworkPolicy):
    """Preserve the SDI popup's established fallback partial-sill floor."""
    _fallback_psill_floor=1e-9


class SemivariogramEngine:
    def __init__(self, profile="ok_mom", use_reml=None):
        self.profile=profile
        self.policy={"ok_mom":_OrdinaryPolicy, "ok_reml":_REMLPolicy, "residual":_ResidualPolicy,
                     "framework":_FrameworkPolicy,"framework_sdi":_FrameworkSDIPolicy}[profile]()
        self.policy._use_reml = profile == "ok_reml" if use_reml is None else use_reml

    def __getattr__(self, name):
        return getattr(self.policy,name)

    def validate_framework(self, x, y, z, cutoff, lag, fit_method, folds, cancelled=lambda:False):
        """Validate the popup's settings using Framework's existing CV and ranking.

        Framework ranks the rounded R² first, then rounded RMSE. Its REML path
        uses LOOCV; its MoM path uses the existing automatic Framework folds.
        """
        lags,gamma=bin_experimental_variogram(x,y,z,cutoff,lag)
        rows=[]
        for token in ("spherical","exponential","gaussian"):
            if cancelled(): raise InterruptedError("Model validation cancelled")
            row=dict(model=token.capitalize(),model_key=token,fit_method=fit_method,
                maximum_distance=float(cutoff),lag=float(lag))
            try:
                params=self._guess_initial_params(lags,gamma,cutoff,token)
                if fit_method=="REML":
                    fit=fit_ok_reml_interface(np.column_stack((x,y,z)),
                        {"spherical":"Sph","exponential":"Exp","gaussian":"Gau"}[token],
                        init_from_mom=dict(zip(("nugget","psill","range"),params)),random_state=123)
                    cv=cv_ok_reml_interface(np.column_stack((x,y,z)),fit,k=0)
                    pred=cv.get("y_pred",cv.get("pred"))
                    if pred is None: raise ValueError("REML CV did not return predictions")
                    preds=np.asarray(pred,float)
                    params=tuple(float(fit[key]) for key in ("nugget","psill","range"))
                    row["reml_meta"]={key:fit.get(key) for key in ("converged","niter","reml_value")}
                else:
                    preds=np.full(z.size,np.nan,float)
                    for test_idx in folds:
                        if cancelled(): raise InterruptedError("Model validation cancelled")
                        train=np.ones(z.size,bool); train[test_idx]=False
                        preds[test_idx]=ordinary_kriging_interpolation(x[train],y[train],z[train],x[test_idx],y[test_idx],
                            nugget=params[0],psill=params[1],var_range=params[2],model=token)
                metrics=self._validation_metrics(z,preds)
                if np.count_nonzero(np.isfinite(preds))<2:
                    raise ValueError("Validation did not return enough finite predictions")
                row.update({key:round(float(metrics[key]),2 if key=="rmse_pct" else 3)
                    for key in ("rmse","rmse_pct","mae","r2","pearson","lccc")})
                row["fitted_params"]=params
                row["validation_n"]=int(np.count_nonzero(np.isfinite(preds)))
            except InterruptedError:
                raise
            except Exception as exc:
                row["error"]=str(exc)
                row.update({key:float("nan") for key in ("rmse","rmse_pct","mae","r2","pearson","lccc")})
            rows.append(row)
        rows.sort(key=lambda r:(bool(r.get("error")),-(r["r2"] if np.isfinite(r["r2"]) else -1e300),
            r["rmse"] if np.isfinite(r["rmse"]) else 1e300))
        return rows

    def validate(self, x, y, z, cutoff, lag, candidates, cancelled=lambda:False):
        rows=[]
        if self.profile=="residual":
            lags,gamma=bin_experimental_variogram(x,y,z,cutoff,lag)
            fits=[f for f in self.policy._fit_variogram_candidates(lags,gamma,cutoff) if f.model in candidates]
            for fit in fits:
                if cancelled(): raise InterruptedError("Model validation cancelled")
                metrics=self.policy._residual_model_cv_metrics(x,y,z,fit)
                rows.append(dict(model=fit.model,model_key=fit.model,fit=fit,sse=fit.sse,**metrics))
            rows.sort(key=lambda r:(r["rmse"],r["sse"]))
        else:
            for token in candidates:
                if cancelled(): raise InterruptedError("Model validation cancelled")
                try:
                    row=self.policy._evaluate_model_cv(token,x,y,z,cutoff,lag)
                except Exception as exc:
                    # Keep the established per-candidate failure policy visible.
                    row=dict(model=self.policy._model_text_from_token(token),model_key=token,error=str(exc),
                             **{key:float("nan") for key in ("rmse","rmse_pct","mae","r2","pearson","lccc")})
                rows.append(row)
            rows.sort(key=lambda r:(-(r["lccc"] if np.isfinite(r["lccc"]) else -1e300),
                r["rmse"] if np.isfinite(r["rmse"]) else 1e300,-(r["r2"] if np.isfinite(r["r2"]) else -1e300)))
        return rows
