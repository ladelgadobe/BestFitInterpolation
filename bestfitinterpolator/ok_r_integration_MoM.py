# -*- coding: utf-8 -*-
"""
ok_r_integration.py
Ordinary Kriging tab controller in pure Python (no R dependency).
All code comments are in English. UI labels are updated in place.

What this file does:
- Computes the experimental semivariogram in Python.
- Estimates initial variogram parameters (nugget, partial sill, range) via MoM-like heuristics.
- Overlays a theoretical model curve (Spherical / Exponential / Gaussian) on the experimental variogram.
- Builds a prediction grid inside a polygon and performs Ordinary Kriging predictions in Python.
- Plots the clipped prediction map with a viridis colormap.

Note:
- The "MoM/REML" label in the UI is informational only. No REML fit is executed here.
"""

import math
import os
import tempfile
import uuid
import numpy as np
from qgis.PyQt.QtCore import Qt, QCoreApplication, QEvent
from qgis.PyQt.QtGui import QCursor, QPixmap
from qgis.PyQt.QtWidgets import (
    QProgressDialog, QFileDialog, QMenu, QToolTip,
    QDialog, QMessageBox, QSizePolicy, QTableWidget, QTableWidgetItem,
    QHeaderView,
)

from qgis.PyQt.QtWidgets import QVBoxLayout
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.ticker import MaxNLocator, ScalarFormatter
from matplotlib.path import Path as MplPath
from matplotlib.patches import Polygon as MplPolygon
from qgis.core import QgsProject, QgsWkbTypes, QgsMapLayer, QgsRasterLayer
from osgeo import gdal, osr

# Optional REML backend (SciPy-based); fall back to MoM if unavailable
try:
    from .reml_bridge import fit_ok_reml_interface
    from .kriging_reml import _HAS_SCIPY as _REML_SCIPY
    _HAS_REML = bool(_REML_SCIPY)
except Exception:
    _HAS_REML = False

# Pure-Python kriging backend (already used by your other path)
from .kriging_ordinary import ordinary_kriging_interpolation

# Centralized colors
EXP_COLOR = "#2f0dee"   # experimental points
TH_COLOR  = "#000000"   # theoretical curve


class BestFitTemporaryRasterLayer(QgsRasterLayer):
    """Raster layer wrapper used so QGIS can identify plugin temp outputs."""
    def isTemporary(self):
        return True


class OKTabController:
    """Manages logic for the Ordinary Kriging tab (pure Python):
       - Computes the experimental variogram (Python)
       - Estimates initial parameters (Python, MoM-like heuristics)
       - Overlays a theoretical model (Python)
       - Interpolates via pure-Python ordinary kriging (no R/gstat)
       - Reset returns to the first auto-computed baseline for the current layer/field
    """

    def __init__(self, iface, dlg, plugin_dir=None, r_folder_path=None):
        # Plugin dir kept for symmetry (no longer used for R)
        self.plugin_dir = plugin_dir

        # QGIS iface & dialog
        self.iface = iface
        self.dlg = dlg

        # Data holders provided by the main plugin class
        self.points_layer = None
        self.z_field = None

        # Matplotlib holders
        self._krig_vario_fig = None
        self._krig_vario_canvas = None
        self._krig_map_fig = None
        self._krig_map_canvas = None
        self._interpolate_btn = None
        self._is_interpolating = False

        # Cached last computed data
        self._exp_lags = None
        self._exp_gamma = None
        self._cutoff = None
        self._lag_width = None
        self._n = 0
        self._init_params = None  # (nugget, psill, rng)
        self._ok_fit_method = "MoM"  # or "REML" when successful
        self._use_reml = False
        self._reml_fitted = False
        self._auto_selected_model = "exponential"
        self._model_validation_results = []

        # Handoff from main plugin class for CV
        self.run_ok_cv_function = None

        # Baselines
        self._baseline_initial = None  # first auto baseline (heuristics) for current layer/field
        self._baseline_last = None     # last computed (auto or manual)

        # Guard to avoid re-calculating variogram while interpolating
        self._block_variogram_updates = False
        self._programmatic_variogram_update = False
        self._user_variogram_overrides = False

        self._dispatcher_active = True
        self._wire_signals()
        # Initial SDI update
        try:
            self._update_sdi_label()
        except Exception:
            pass
        # Ensure SDI info icon is present
        try:
            self._ensure_sdi_info_icon()
        except Exception:
            pass

    def set_dispatcher_active(self, state: bool):
        """Enable or disable this controller when used by the dispatcher."""
        self._dispatcher_active = bool(state)

    def is_dispatcher_active(self) -> bool:
        return bool(getattr(self, "_dispatcher_active", True))

    # ------------------------- Model auto-selection --------------------------

    @staticmethod
    def _candidate_model_tokens():
        return ("spherical", "exponential", "gaussian")

    @staticmethod
    def _model_text_from_token(token: str) -> str:
        token = str(token or "").strip().lower()
        if token.startswith("sph"):
            return "Sph"
        if token.startswith("gau"):
            return "Gau"
        return "Exp"

    def _ensure_model_selector_defaults(self):
        cmb = getattr(self.dlg, "cmbOKModel", None)
        if cmb is None or not hasattr(cmb, "count"):
            return
        try:
            has_auto = any(str(cmb.itemText(i)).strip().lower().startswith("auto") for i in range(cmb.count()))
            if not has_auto:
                cmb.insertItem(0, "Automatic")
                cmb.setCurrentIndex(0)
        except Exception:
            pass

    def _is_auto_model_selection(self) -> bool:
        cmb = getattr(self.dlg, "cmbOKModel", None)
        if cmb is None or not hasattr(cmb, "currentText"):
            return False
        return str(cmb.currentText() or "").strip().lower().startswith("auto")

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

    @staticmethod
    def _fmt_metric(value, decimals=3, suffix=""):
        try:
            value = float(value)
        except Exception:
            return "--"
        if not np.isfinite(value):
            return "--"
        return f"{value:.{decimals}f}{suffix}"

    def _evaluate_model_cv(self, model_token: str, x, y, z, cutoff, lagw):
        lags, gamma = self._bin_variogram(x, y, z, cutoff, lagw)
        nugget, psill, rng = self._guess_initial_params(lags, gamma, cutoff, model=model_token)
        preds = np.full(z.size, np.nan, dtype=float)
        for i in range(z.size):
            train = np.ones(z.size, dtype=bool)
            train[i] = False
            preds[i] = float(np.asarray(ordinary_kriging_interpolation(
                x[train], y[train], z[train], [x[i]], [y[i]],
                nugget=nugget, psill=psill, var_range=rng, model=model_token
            )).ravel()[0])
        metrics = self._validation_metrics(z, preds)
        metrics.update({
            "model": self._model_text_from_token(model_token),
            "token": model_token,
            "nugget": float(nugget),
            "psill": float(psill),
            "range": float(rng),
        })
        return metrics

    def _choose_best_model_by_validation(self, x, y, z, cutoff, lagw):
        rows = []
        for token in self._candidate_model_tokens():
            try:
                rows.append(self._evaluate_model_cv(token, x, y, z, cutoff, lagw))
            except Exception as exc:
                rows.append({
                    "model": self._model_text_from_token(token),
                    "token": token,
                    "rmse": float("nan"),
                    "rmse_pct": float("nan"),
                    "mae": float("nan"),
                    "r2": float("nan"),
                    "pearson": float("nan"),
                    "lccc": float("nan"),
                    "error": str(exc),
                })
        ranked = sorted(
            rows,
            key=lambda r: (
                -(float(r.get("r2")) if np.isfinite(float(r.get("r2", float("nan")))) else -1e300),
                float(r.get("rmse")) if np.isfinite(float(r.get("rmse", float("nan")))) else 1e300,
            ),
        )
        best = ranked[0] if ranked else {"token": "exponential"}
        self._model_validation_results = ranked
        self._auto_selected_model = str(best.get("token") or "exponential")
        try:
            nugget = float(best.get("nugget"))
            psill = float(best.get("psill"))
            rng = float(best.get("range"))
            if all(np.isfinite(v) for v in (nugget, psill, rng)):
                self._init_params = (nugget, psill, rng)
                self._programmatic_variogram_update = True
                if hasattr(self.dlg, "spinOKNugget"):
                    self.dlg.spinOKNugget.setValue(nugget)
                if hasattr(self.dlg, "spinOKPsill"):
                    self.dlg.spinOKPsill.setValue(psill)
                if hasattr(self.dlg, "spinOKRange"):
                    self.dlg.spinOKRange.setValue(rng)
        except Exception:
            pass
        finally:
            self._programmatic_variogram_update = False
        btn = getattr(self.dlg, "btnOKModelValidation", None)
        if btn is not None and hasattr(btn, "setToolTip"):
            btn.setToolTip(
                f"Best automatic model: {self._model_text_from_token(self._auto_selected_model)} "
                f"(R2={self._fmt_metric(best.get('r2'))}). Click to view all model validation results."
            )
        return self._auto_selected_model

    def _show_model_validation_dialog(self):
        try:
            if not self._model_validation_results:
                x, y, z = self._read_xy_z()
                if x is None:
                    QMessageBox.information(self.dlg, "Kriging model validation", "Select a valid point layer and variable first.")
                    return
                cutoff = self._cutoff
                lagw = self._lag_width
                if cutoff is None or lagw is None:
                    all_d = self._pairwise_distances(x, y)
                    cutoff = 0.5 * float(np.nanmax(all_d))
                    lagw = self._safe_lag_width(x, y, cutoff, self._nearest_neighbor_dist(x, y))
                self._choose_best_model_by_validation(x, y, z, cutoff, lagw)
            dlg = QDialog(self.dlg)
            dlg.setWindowTitle("Kriging model validation")
            layout = QVBoxLayout(dlg)
            table = QTableWidget(dlg)
            headers = ["Model", "RMSE", "RMSE%", "MAE", "R2", "Pearson", "LCCC"]
            rows = list(self._model_validation_results or [])
            table.setColumnCount(len(headers))
            table.setHorizontalHeaderLabels(headers)
            table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                values = [
                    row.get("model", ""),
                    self._fmt_metric(row.get("rmse")),
                    self._fmt_metric(row.get("rmse_pct"), 2, "%"),
                    self._fmt_metric(row.get("mae")),
                    self._fmt_metric(row.get("r2")),
                    self._fmt_metric(row.get("pearson")),
                    self._fmt_metric(row.get("lccc")),
                ]
                for c, value in enumerate(values):
                    table.setItem(r, c, QTableWidgetItem(str(value)))
            try:
                table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            except Exception:
                table.resizeColumnsToContents()
            layout.addWidget(table)
            dlg.resize(720, 260)
            dlg.exec_()
        except Exception as exc:
            QMessageBox.warning(self.dlg, "Kriging model validation", f"Could not show validation:\n{exc}")

    # ------------------------------ Wiring ----------------------------------

    def _wire_signals(self):
        """Connect UI signals for Kriging tab."""
        self._ensure_model_selector_defaults()
        try:
            self.dlg.mainTabs.currentChanged.connect(self._on_tab_changed)
        except Exception:
            pass

        # Calculate (recompute experimental + overlay)
        if hasattr(self.dlg, "btnOKCalculate") and self.dlg.btnOKCalculate is not None:
            try:
                self.dlg.btnOKCalculate.clicked.connect(self._on_recalculate_clicked)
            except Exception:
                pass

        # CV button (in validation tab)
        btn_cv = getattr(self.dlg, "btnOKRunCV", None)
        if btn_cv is not None:
            btn_cv.clicked.connect(self._on_run_cv_clicked)

        # Interpolate (map)
        self._hook_interpolate_button()

        # Reset button(s): try common names, then generic scan
        if not self._hook_reset_button_by_common_names():
            self._hook_reset_button_generic()

        # Overlay model whenever user changes model or params
        for wname in ("cmbOKModel", "spinOKNugget", "spinOKPsill", "spinOKRange"):
            w = getattr(self.dlg, wname, None)
            if w is None:
                continue
            if hasattr(w, "valueChanged"):
                try:
                    w.valueChanged.connect(self._plot_with_model_if_possible)
                    w.valueChanged.connect(self._update_sdi_label)
                except Exception:
                    pass

        for wname in ("cmbOKModel", "spinOKCutoff", "spinOKLag", "spinOKNugget", "spinOKPsill", "spinOKRange"):
            w = getattr(self.dlg, wname, None)
            if w is None:
                continue
            if hasattr(w, "valueChanged"):
                try:
                    w.valueChanged.connect(self._on_variogram_ui_changed)
                except Exception:
                    pass
            if hasattr(w, "currentIndexChanged"):
                try:
                    w.currentIndexChanged.connect(self._on_variogram_ui_changed)
                except Exception:
                    pass
            if hasattr(w, "currentIndexChanged"):
                try:
                    w.currentIndexChanged.connect(self._plot_with_model_if_possible)
                    w.currentIndexChanged.connect(self._update_sdi_label)
                except Exception:
                    pass

        btn_model_validation = getattr(self.dlg, "btnOKModelValidation", None)
        if btn_model_validation is not None and hasattr(btn_model_validation, "clicked"):
            try:
                btn_model_validation.clicked.connect(self._show_model_validation_dialog)
            except Exception:
                pass

        # Data-layer and variable changes are coordinated by BestFitInterpolator._update_ok_context.
        # Do not connect them here; duplicate controller slots can fire while QGIS is rebuilding layers.

    def _hook_interpolate_button(self):
        """Wire the kriging interpolate button to run map generation."""
        btn = None
        for name in ("btnOKInterpolate", "btnKrigInterpolate", "btnOKRun"):
            w = getattr(self.dlg, name, None)
            if w is not None and hasattr(w, "clicked"):
                btn = w
                break
        if btn is not None:
            self._interpolate_btn = btn
            try:
                btn.clicked.connect(self._on_interpolate_clicked)
            except Exception:
                pass

    def _hook_reset_button_by_common_names(self) -> bool:
        """Try common reset button objectNames. Return True if hooked."""
        for bname in ("btnOKReset", "btnOKDefaults", "btnOKRevert", "btnOKParamsReset", "btnReset"):
            btn = getattr(self.dlg, bname, None)
            if btn is not None and hasattr(btn, "clicked"):
                try:
                    btn.clicked.connect(self._on_reset_clicked)
                    return True
                except Exception:
                    pass
        return False

    def _hook_reset_button_generic(self):
        """Scan dialog attributes for a QPushButton-like with 'reset'/'default' text/name."""
        try:
            for attr in dir(self.dlg):
                if attr.startswith("_"):
                    continue
                obj = getattr(self.dlg, attr, None)
                if obj is None:
                    continue
                if hasattr(obj, "clicked"):
                    name = ""
                    try:
                        if hasattr(obj, "objectName"):
                            name = (obj.objectName() or "").lower()
                    except Exception:
                        pass
                    text = ""
                    try:
                        if hasattr(obj, "text"):
                            text = (obj.text() or "").lower()
                    except Exception:
                        pass
                    hay = any(k in name for k in ("reset", "default", "reiniciar", "restablecer")) or \
                          any(k in text for k in ("reset", "default", "reiniciar", "restablecer"))
                    if hay:
                        try:
                            obj.clicked.connect(self._on_reset_clicked)
                            return
                        except Exception:
                            continue
        except Exception:
            pass

    # ---------------------- Layer/field handoff from main ---------------------

    def set_points_layer_and_field(self, layer, field):
        if not self.is_dispatcher_active():
            return
        """Receive the currently selected points layer and field from the main class."""
        # If layer/field didn't change, keep current user-adjusted variogram
        try:
            same_layer = (
                self.points_layer is not None
                and layer is not None
                and self.points_layer.id() == layer.id()
            )
        except Exception:
            same_layer = (self.points_layer is layer)
        same_field = (self.z_field == field)
        if same_layer and same_field:
            self._ensure_variogram_ready()
            return

        self.points_layer = layer
        self.z_field = field
        # Invalidate initial baseline for new context
        self._baseline_initial = None
        self._user_variogram_overrides = False
        # Reset REML state on context change
        self._use_reml = False
        self._reml_fitted = False
        # If we are in Kriging tab, compute immediately
        self.calculate_and_plot_experimental(initial_load=True)

    def _variogram_has_drawn_content(self) -> bool:
        try:
            if self._krig_vario_fig is None or not self._krig_vario_fig.axes:
                return False
            ax = self._krig_vario_fig.axes[0]
            return bool(ax.lines or ax.collections or ax.patches or ax.images)
        except Exception:
            return False

    def _ensure_variogram_ready(self) -> bool:
        """Rebuild the variogram if the canvas was cleared without a context change."""
        if getattr(self, "_block_variogram_updates", False):
            return False
        try:
            self._ensure_inputs_from_ui()
            if not self._ensure_canvas():
                return False
            had_params = self._init_params is not None
            self._sync_variogram_state_from_ui()
            if self._variogram_has_drawn_content() and (self._exp_lags is not None or self._reml_fitted):
                self._plot_with_model_if_possible()
                return True
            keep_user_params = self._user_variogram_overrides or had_params
            self.calculate_and_plot_experimental(
                initial_load=not keep_user_params,
                reseed_params=not keep_user_params,
            )
            if keep_user_params:
                self._sync_variogram_state_from_ui()
                self._plot_with_model_if_possible()
            return self._variogram_has_drawn_content()
        except Exception:
            return False

    def _on_variogram_ui_changed(self, *args) -> None:
        """Track manual edits so interpolation never restores automatic seeds."""
        if getattr(self, "_programmatic_variogram_update", False):
            return
        self._user_variogram_overrides = True
        self._sync_variogram_state_from_ui()

    def _sync_variogram_state_from_ui(self) -> None:
        """Mirror current semivariogram controls into controller state without fitting."""
        try:
            if hasattr(self.dlg, "spinOKCutoff"):
                self._cutoff = float(self.dlg.spinOKCutoff.value())
        except Exception:
            pass
        try:
            if hasattr(self.dlg, "spinOKLag"):
                self._lag_width = float(self.dlg.spinOKLag.value())
        except Exception:
            pass
        try:
            self._init_params = tuple(float(v) for v in self._read_params_from_ui())
        except Exception:
            pass

    def _on_tab_changed(self, index):
        """Triggered when the user switches tabs."""
        # This is now handled by the main plugin class, which calls set_points_layer_and_field
        # which in turn calls calculate_and_plot_experimental.
        pass

    # ----------------------- Model & variable helpers ------------------------

    def _normalize_model_token(self, txt: str) -> str:
        t = (txt or "").strip().lower()
        if t.startswith(("sph", "esf")):   # Spherical/Esférico
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

    def _get_selected_model(self) -> str:
        cmb = getattr(self.dlg, "cmbOKModel", None)
        if cmb is not None and hasattr(cmb, "currentText"):
            if str(cmb.currentText() or "").strip().lower().startswith("auto"):
                return str(getattr(self, "_auto_selected_model", "exponential") or "exponential")
            return self._normalize_model_token(cmb.currentText())
        return "exponential"

    def _set_model_combo_by_token(self, token: str):
        cmb = getattr(self.dlg, "cmbOKModel", None)
        if cmb is None or not hasattr(cmb, "count"):
            return
        try:
            if str(token or "").strip().lower().startswith("auto"):
                for i in range(cmb.count()):
                    if str(cmb.itemText(i)).strip().lower().startswith("auto"):
                        cmb.setCurrentIndex(i)
                        return
            for i in range(cmb.count()):
                itxt = cmb.itemText(i)
                if self._normalize_model_token(itxt) == token:
                    cmb.setCurrentIndex(i)
                    return
        except Exception:
            pass

    def _maybe_pull_field_from_ui(self):
        for name in ("cmbZField", "cmbField", "cmbVariable", "cmbOKField", "Points_2"):
            w = getattr(self.dlg, name, None)
            if w is not None and hasattr(w, "currentText"):
                txt = w.currentText()
                if txt:
                    self.z_field = txt
                    return

    def _on_variable_ui_changed(self, *args):
        if not self.is_dispatcher_active():
            return
        try:
            self._maybe_pull_field_from_ui()
            self._baseline_initial = None
            self.calculate_and_plot_experimental(initial_load=True)
            self._plot_with_model_if_possible()
        except RuntimeError:
            self.points_layer = None
            return

    # -------------------------- Click handlers -------------------------------

    def _on_run_cv_clicked(self):
        """Handler for the 'Run CV' button on the Kriging validation tab."""
        if self.run_ok_cv_function is not None:
            try:
                self._ensure_variogram_ready()
                self.run_ok_cv_function()
            except Exception as e:
                self.iface.messageBar().pushCritical("Kriging CV", f"Failed to trigger CV run: {e}")

    def _on_recalculate_clicked(self):
        if not self.is_dispatcher_active():
            return
        # Recompute experimental and MoM seeds
        self._ensure_inputs_from_ui()
        self.calculate_and_plot_experimental(initial_load=False, reseed_params=True)
        # If small sample size and REML available, fit now on Calculate
        try:
            x, y, z = self._read_xy_z()
        except Exception:
            x = y = z = None
        if False:
            try:
                # Enter REML mode, clear experimental, fit once, and plot theoretical only
                self._use_reml = True
                self._exp_lags, self._exp_gamma = None, None
                self._reml_fitted = False
                self._fit_reml_if_needed(x, y, z)
            except Exception:
                # If REML fails, stay with MoM overlay
                self._use_reml = False
                self._reml_fitted = False
                self._plot_with_model_if_possible()
        else:
            # MoM only: overlay model on experimental
            self._plot_with_model_if_possible()

    # --- Reset helpers ---

    def _restore_baseline_to_ui_and_state(self, baseline: dict):
        if not baseline:
            return False
        try:
            self._programmatic_variogram_update = True
            if hasattr(self.dlg, "spinOKCutoff"):
                self.dlg.spinOKCutoff.setValue(float(baseline["cutoff"]))
            if hasattr(self.dlg, "spinOKLag"):
                self.dlg.spinOKLag.setValue(float(baseline["lagw"]))
            if hasattr(self.dlg, "spinOKNugget"):
                self.dlg.spinOKNugget.setValue(float(baseline["nugget"]))
            if hasattr(self.dlg, "spinOKPsill"):
                self.dlg.spinOKPsill.setValue(float(baseline["psill"]))
            if hasattr(self.dlg, "spinOKRange"):
                self.dlg.spinOKRange.setValue(float(baseline["range"]))
        except Exception:
            pass
        finally:
            self._programmatic_variogram_update = False
        try:
            self._programmatic_variogram_update = True
            self._set_model_combo_by_token(baseline.get("model", "exponential"))
        except Exception:
            pass
        finally:
            self._programmatic_variogram_update = False
        try:
            self._cutoff      = float(baseline["cutoff"])
            self._lag_width   = float(baseline["lagw"])
            self._init_params = (
                float(baseline["nugget"]),
                float(baseline["psill"]),
                float(baseline["range"]),
            )
        except Exception:
            pass
        self._user_variogram_overrides = False
        return True

    def _on_reset_clicked(self):
        self._ensure_inputs_from_ui()
        if not self._baseline_initial:
            self.calculate_and_plot_experimental(initial_load=True)
            self._plot_with_model_if_possible()
            return
        ok = self._restore_baseline_to_ui_and_state(self._baseline_initial)
        if not ok:
            return
        self.calculate_and_plot_experimental(initial_load=False)
        self._plot_with_model_if_possible()

    # -------------------------- Data extraction ------------------------------

    def _read_xy_z(self):
        """Extract X, Y, Z from the selected points layer and field. Requires >=5 valid points."""
        self._ensure_inputs_from_ui()
        if self.points_layer is None or not self.z_field:
            return None, None, None
        xs, ys, zs = [], [], []
        try:
            features = self.points_layer.getFeatures()
        except RuntimeError:
            self.points_layer = None
            self._maybe_pull_points_layer_from_ui()
            if self.points_layer is None:
                return None, None, None
            try:
                features = self.points_layer.getFeatures()
            except RuntimeError:
                self.points_layer = None
                return None, None, None
        for feat in features:
            g = feat.geometry()
            if g is None or g.isEmpty():
                continue
            try:
                pt = g.asPoint()
            except Exception:
                try:
                    mpt = g.constGet()
                    if hasattr(mpt, "geometryN"):
                        pt = mpt.geometryN(0).asPoint()
                    else:
                        continue
                except Exception:
                    continue
            try:
                val = float(feat[self.z_field])
            except Exception:
                val = np.nan
            if np.isfinite(val):
                xs.append(pt.x()); ys.append(pt.y()); zs.append(val)
        if len(xs) < 5:
            return None, None, None
        return np.array(xs, dtype=float), np.array(ys, dtype=float), np.array(zs, dtype=float)

    # ----------------------- Variogram core (experimental) --------------------

    @staticmethod
    def _pairwise_distances(x, y):
        """Return condensed array of pairwise Euclidean distances."""
        n = x.size
        d = np.empty(n * (n - 1) // 2, dtype=float)
        k = 0
        for i in range(n - 1):
            dx = x[i + 1:] - x[i]
            dy = y[i + 1:] - y[i]
            m = np.hypot(dx, dy)
            d[k:k + m.size] = m
            k += m.size
        return d

    @staticmethod
    def _nearest_neighbor_dist(x, y):
        """Return the minimum positive nearest-neighbor distance."""
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        n = x.size
        if n < 2:
            return np.nan
        scale = max(float(np.nanmax(np.abs(x))) if x.size else 0.0,
                    float(np.nanmax(np.abs(y))) if y.size else 0.0,
                    1.0)
        zero_tol = np.finfo(float).eps * scale * 32.0
        dmin = np.inf
        for i in range(n):
            dx = x - x[i]
            dy = y - y[i]
            dist = np.hypot(dx, dy)
            dist[i] = np.inf
            dist = dist[np.isfinite(dist) & (dist > zero_tol)]
            if dist.size == 0:
                continue
            mi = float(np.min(dist))
            if mi < dmin:
                dmin = mi
        return dmin if np.isfinite(dmin) else np.nan

    def _safe_lag_width(self, x, y, cutoff, lag_width, max_bins=10000):
        """Keep lag width positive while preventing pathological bin counts."""
        try:
            cutoff = float(cutoff)
        except Exception:
            cutoff = np.nan
        if not np.isfinite(cutoff) or cutoff <= 0:
            return np.nan
        try:
            lag_width = float(lag_width)
        except Exception:
            lag_width = np.nan
        if not np.isfinite(lag_width) or lag_width <= 0:
            lag_width = float(self._nearest_neighbor_dist(x, y))
        if not np.isfinite(lag_width) or lag_width <= 0:
            lag_width = cutoff / 12.0
        min_width = cutoff / float(max(1, int(max_bins)))
        if lag_width < min_width:
            lag_width = min_width
        return float(lag_width)

    @staticmethod
    def _semivariances(z):
        """Return a callable γ(i, J) = 0.5 * (i - J)^2 to vectorize per-pair values."""
        def gamma(i_val, j_vals):
            diff = i_val - j_vals
            return 0.5 * (diff * diff)
        return gamma

    def _bin_variogram(self, x, y, z, cutoff, lag_width):
        """Compute binned experimental semivariogram up to 'cutoff' with bin size 'lag_width'."""
        cutoff = float(cutoff)
        lag_width = self._safe_lag_width(x, y, cutoff, lag_width)
        if not np.isfinite(cutoff) or cutoff <= 0 or not np.isfinite(lag_width) or lag_width <= 0:
            return np.array([], dtype=float), np.array([], dtype=float)
        nbins = max(1, int(math.floor(cutoff / lag_width)))
        if nbins > 10000:
            nbins = 10000
            lag_width = cutoff / float(nbins)
        sums = np.zeros(nbins, dtype=float)
        counts = np.zeros(nbins, dtype=int)
        dists = np.zeros(nbins, dtype=float)
        gamma_of = self._semivariances(z)
        n = x.size
        for i in range(n - 1):
            xi, yi, zi = x[i], y[i], z[i]
            xj = x[i + 1:]; yj = y[i + 1:]; zj = z[i + 1:]
            dd = np.hypot(xj - xi, yj - yi)
            mask = (dd > 0) & (dd <= cutoff)
            if not np.any(mask):
                continue
            dd = dd[mask]
            gj = gamma_of(zi, zj[mask])
            bin_idx = np.floor(dd / lag_width).astype(int)
            bin_idx[bin_idx == nbins] = nbins - 1  # clamp edge case
            for b, dval, gval in zip(bin_idx, dd, gj):
                sums[b] += gval
                counts[b] += 1
                dists[b] += dval
        valid = counts > 0
        default_centers = np.linspace(lag_width * 0.5, nbins * lag_width - lag_width * 0.5, nbins)
        lags = np.where(valid, dists / np.maximum(counts, 1), default_centers)
        gamma = np.where(valid, sums / np.maximum(counts, 1), np.nan)
        keep = ~np.isnan(gamma)
        return lags[keep], gamma[keep]

    # --------------------- Initial parameter estimation -----------------------

    @staticmethod
    def _robust_var(z):
        """Robust variance proxy via MAD. Falls back to sample variance if MAD=0."""
        med = np.median(z)
        mad = np.median(np.abs(z - med))
        if mad <= 0:
            return float(np.var(z, ddof=1))
        return float((1.4826 * mad) ** 2)

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
            return nugget_seed, max(sill_total_seed - nugget_seed, 1e-6), range_seed

        _, nugget, psill, rng = best
        return nugget, psill, rng

    # ----------------------------- UI helpers ---------------------------------

    def _ensure_canvas(self):
        """Ensure variogram and map canvases exist and are attached."""
        # Variogram
        container_v = getattr(self.dlg, "CanvasOKVariogram", None) or getattr(self.dlg, "canvasOKVariogram", None)
        if container_v is not None and self._krig_vario_canvas is None:
            self._krig_vario_fig = Figure(figsize=(5, 4), tight_layout=True)
            self._krig_vario_canvas = FigureCanvas(self._krig_vario_fig)
            self._stabilize_canvas_widget(self._krig_vario_canvas)
            layout = container_v.layout() or QVBoxLayout(container_v)
            for i in reversed(range(layout.count())):
                w = layout.itemAt(i).widget()
                if w is not None:
                    w.setParent(None)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._krig_vario_canvas)
            self._install_save_png_handler(self._krig_vario_canvas, self._krig_vario_fig, default_prefix="kriging_variogram")

        # Map
        container_m = getattr(self.dlg, "canvasOKInterpolation", None) or getattr(self.dlg, "CanvasOKInterpolation", None)
        if container_m is not None and self._krig_map_canvas is None:
            self._krig_map_fig = Figure(figsize=(5, 4), tight_layout=True)
            self._krig_map_canvas = FigureCanvas(self._krig_map_fig)
            self._stabilize_canvas_widget(self._krig_map_canvas)
            layout = container_m.layout() or QVBoxLayout(container_m)
            for i in reversed(range(layout.count())):
                w = layout.itemAt(i).widget()
                if w is not None:
                    w.setParent(None)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._krig_map_canvas)
            self._install_save_png_handler(self._krig_map_canvas, self._krig_map_fig, default_prefix="kriging_map")

        return (self._krig_vario_canvas is not None)

    def _stabilize_canvas_widget(self, canvas):
        """Keep Matplotlib canvases from resizing their parent after redraws."""
        try:
            canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            canvas.setMinimumSize(1, 1)
            canvas.updateGeometry()
        except Exception:
            pass

    # ----------------------------- Save PNG hooks -----------------------------

    def _install_save_png_handler(self, canvas, fig, default_prefix: str):
        """Install right-click context menu 'Save graph…' on a Matplotlib canvas."""
        try:
            if canvas is None or fig is None:
                return
            # Avoid multiple connections on the same canvas
            if not hasattr(self, "_save_handlers"):
                self._save_handlers = set()
            key = id(canvas)
            if key in self._save_handlers:
                return

            # Prefer Qt custom context menu
            try:
                canvas.setContextMenuPolicy(Qt.CustomContextMenu)
            except Exception:
                pass

            def _show_menu(pos):
                try:
                    menu = QMenu(self.dlg)
                    act_view = menu.addAction("View larger view")
                    act_copy = menu.addAction("Copy graph")
                    act_save = menu.addAction("Save graph…")
                    chosen = menu.exec_(canvas.mapToGlobal(pos))
                    if chosen == act_view:
                        self._show_larger_graph(fig, default_prefix)
                    elif chosen == act_copy:
                        self._copy_figure_to_clipboard(fig)
                    elif chosen == act_save:
                        suggested_dir = os.path.expanduser("~")
                        suggested = os.path.join(suggested_dir, f"{default_prefix}.png")
                        path, _ = QFileDialog.getSaveFileName(self.dlg, "Save graph", suggested, "PNG Images (*.png)")
                        if path:
                            fig.savefig(path, dpi=300, bbox_inches='tight')
                            try:
                                self.iface.messageBar().pushMessage("Saved", f"PNG saved to: {path}", level=0)
                            except Exception:
                                pass
                except Exception:
                    pass

            try:
                canvas.customContextMenuRequested.connect(_show_menu)
            except Exception:
                # Fallback to raw mpl right-click
                def _on_click(event):
                    try:
                        if getattr(event, 'button', None) == 3:
                            _show_menu(canvas.mapFromGlobal(canvas.cursor().pos()))
                    except Exception:
                        pass
                canvas.mpl_connect('button_press_event', _on_click)

            self._save_handlers.add(key)
        except Exception:
            pass

    def _copy_figure_to_clipboard(self, fig) -> None:
        """Copy a Matplotlib figure to the system clipboard as a PNG image."""
        try:
            import io
            from qgis.PyQt.QtGui import QPixmap
            from qgis.PyQt.QtWidgets import QApplication
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=300, bbox_inches="tight")
            pixmap = QPixmap()
            pixmap.loadFromData(buf.getvalue(), "PNG")
            QApplication.clipboard().setPixmap(pixmap)
            try:
                self.iface.messageBar().pushMessage("Copied", "Graph copied to clipboard.", level=0)
            except Exception:
                pass
        except Exception as exc:
            QMessageBox.warning(self.dlg, "Copy graph", f"Could not copy graph:\n{exc}")

    def _show_larger_graph(self, source_fig, title_prefix: str):
        try:
            import io
            import matplotlib.image as mpimg
            dlg = QDialog(self.dlg)
            dlg.setWindowTitle(f"{title_prefix} - larger view")
            layout = QVBoxLayout(dlg)
            fig = Figure(figsize=(9, 6.5))
            canvas = FigureCanvas(fig)
            layout.addWidget(canvas)
            buf = io.BytesIO()
            source_fig.savefig(buf, format="png", dpi=180, bbox_inches="tight")
            buf.seek(0)
            arr = mpimg.imread(buf)
            ax = fig.add_subplot(111)
            ax.imshow(arr)
            ax.axis("off")
            canvas.draw()
            dlg.resize(980, 720)
            dlg.exec_()
        except Exception as exc:
            QMessageBox.warning(self.dlg, "View larger view", f"Could not open larger view:\n{exc}")

    def _update_headers(self, var_name, n, cutoff, lagw):
        """Update small UI labels/fields regarding the current context."""
        if hasattr(self.dlg, "valOKZName") and hasattr(self.dlg, "valOKSamples"):
            try:
                self.dlg.valOKZName.setText(str(var_name))
                self.dlg.valOKSamples.setText(str(n))
            except Exception:
                pass
        # Display which fitting method is active (value label in UI is 'valOKModel')
        label_val = getattr(self.dlg, "valOKModel", None)
        if label_val is not None and hasattr(label_val, "setText"):
            try:
                label_val.setText(self._ok_fit_method)
            except Exception:
                pass
        else:
            # Backward-compat for older UI naming
            label_compat = getattr(self.dlg, "lblFitTitle", None) or getattr(self.dlg, "lblOKModel", None)
            if label_compat is not None and hasattr(label_compat, "setText"):
                try:
                    label_compat.setText(self._ok_fit_method)
                except Exception:
                    pass
        if hasattr(self.dlg, "spinOKCutoff") and hasattr(self.dlg, "spinOKLag"):
            try:
                self._programmatic_variogram_update = True
                self.dlg.spinOKCutoff.setValue(float(cutoff))
                self.dlg.spinOKLag.setValue(float(lagw))
            except Exception:
                pass
            finally:
                self._programmatic_variogram_update = False

    # -------------------------- Public main actions ---------------------------

    def calculate_and_plot_experimental(self, initial_load=True, reseed_params=None):
        """
        Compute and plot the experimental semivariogram, then seed initial params.

        Parameters
        ----------
        initial_load : bool
            True cuando se entra por primera vez con un nuevo layer/atributo.
        reseed_params : bool or None
            - True  -> recalcula semillas (nugget, psill, range) con heurística.
            - False -> NO toca los parámetros, usa lo que hay en los spin boxes.
            - None  -> por defecto: mismo valor que initial_load.
        """
        # If interpolation is running, do NOT touch the variogram or parameters
        if getattr(self, "_block_variogram_updates", False):
            return

        if not self._ensure_canvas():
            return

        # Resolver valor por defecto de reseed_params
        if reseed_params is None:
            reseed_params = bool(initial_load)

        x, y, z = self._read_xy_z()
        if x is None:
            self.iface.messageBar().pushMessage(
                "Kriging",
                "Select point layer and variable in the Data tab",
                level=1
            )
            return

        self._n = len(z)

        # Distancias, cutoff y lag
        all_d = self._pairwise_distances(x, y)
        d_max = float(np.nanmax(all_d))
        nn_min = float(self._nearest_neighbor_dist(x, y))

        cutoff = 0.5 * d_max
        lagw = self._safe_lag_width(x, y, cutoff, nn_min)

        # Si NO es initial_load, respetamos cutoff/lag que ya están en la UI
        if not initial_load:
            try:
                cutoff = float(self.dlg.spinOKCutoff.value())
            except Exception:
                pass
            try:
                lagw = float(self.dlg.spinOKLag.value())
            except Exception:
                pass
            lagw = self._safe_lag_width(x, y, cutoff, lagw)

        self._cutoff = cutoff
        self._lag_width = lagw

        # Experimental variogram
        lags, gamma = self._bin_variogram(x, y, z, cutoff, lagw)
        if lags.size == 0:
            lags = np.array([0.0])
            gamma = np.array([0.0])
        else:
            lags = np.insert(lags, 0, 0.0)
            gamma = np.insert(gamma, 0, 0.0)

        self._exp_lags, self._exp_gamma = lags, gamma

        if self._is_auto_model_selection():
            try:
                self._choose_best_model_by_validation(x, y, z, cutoff, lagw)
            except Exception:
                self._auto_selected_model = "exponential"

        # ------------------------------------------------------------------
        # 1) ¿Recalculamos semillas o respetamos lo que hay en la UI?
        # ------------------------------------------------------------------
        if reseed_params:
            # Usar heurística MoM como baseline
            nugget, psill, rng = self._guess_initial_params(
                lags[1:], gamma[1:], cutoff, model=self._get_selected_model()
            )
            self._init_params = (nugget, psill, rng)
            self._ok_fit_method = "MoM"

            # Escribimos las semillas en los spin boxes
            try:
                self._programmatic_variogram_update = True
                if hasattr(self.dlg, "spinOKNugget"):
                    self.dlg.spinOKNugget.setValue(float(nugget))
                if hasattr(self.dlg, "spinOKPsill"):
                    self.dlg.spinOKPsill.setValue(float(psill))
                if hasattr(self.dlg, "spinOKRange"):
                    self.dlg.spinOKRange.setValue(float(rng))
            except Exception:
                pass
            finally:
                self._programmatic_variogram_update = False

        else:
            # NO tocamos los parámetros: usamos lo que el usuario dejó en la UI
            nugget, psill, rng = self._read_params_from_ui()
            # Si nunca habíamos inicializado _init_params, los guardamos
            if self._init_params is None:
                self._init_params = (nugget, psill, rng)

        # Actualizar cabeceras y SDI
        self._update_headers(self.z_field, self._n, cutoff, lagw)
        try:
            self._update_sdi_label()
        except Exception:
            pass

        # Baselines (Reset usa baseline_initial; no queremos que cambie)
        current_baseline = {
            "cutoff": cutoff, "lagw": lagw,
            "nugget": nugget, "psill": psill, "range": rng,
            "model": self._get_selected_model()
        }
        if initial_load and not self._baseline_initial:
            self._baseline_initial = dict(current_baseline)
        self._baseline_last = dict(current_baseline)

        # Dibujar experimental con solo lags reales; el 0.0 artificial se conserva
        # internamente para el ajuste, pero no debe mostrarse en el gráfico.
        ax = (self._krig_vario_fig.axes[0]
              if self._krig_vario_fig.axes
              else self._krig_vario_fig.add_subplot(111))
        ax.clear()
        lags_plot = lags[1:] if lags.size > 1 else lags
        gamma_plot = gamma[1:] if gamma.size > 1 else gamma
        ax.plot(lags_plot, gamma_plot, 'o', label="Experimental", color=EXP_COLOR)
        ax.set_title("Semivariogram", fontsize=10)
        ax.set_xlabel("Lag distance (h)", fontsize=9)
        ax.set_ylabel("Semivariance γ(h)", fontsize=9)
        xmax_plot = max(cutoff, (lags_plot.max() if lags_plot.size else 1.0))
        ax.set_xlim(left=0.0, right=xmax_plot)
        ax.set_ylim(bottom=0.0)
        ax.xaxis.set_major_locator(MaxNLocator(nbins=8))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=6))
        xf = ScalarFormatter(useOffset=False, useMathText=False); xf.set_scientific(False)
        yf = ScalarFormatter(useOffset=False, useMathText=False); yf.set_scientific(False)
        ax.xaxis.set_major_formatter(xf); ax.yaxis.set_major_formatter(yf)
        ax.tick_params(axis='x', rotation=0)
        ax.tick_params(axis='both', labelsize=8)
        ax.grid(True, linestyle='--', linewidth=0.5, alpha=0.6)
        self._krig_vario_canvas.draw()

        # Sobreponer modelo teórico respetando lo que hay en UI
        self._plot_with_model_if_possible()
        try:
            QCoreApplication.processEvents()
        except Exception:
            pass

    # -------------------------- Theoretical model -----------------------------

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

    # ------------------------------- SDI helpers ------------------------------

    def _compute_sdi_text(self, nugget: float, psill: float) -> str:
        try:
            total = float(nugget) + float(psill)
            if not np.isfinite(total) or total <= 0:
                return "—"
            sdi = 100.0 * float(psill) / total
            if sdi < 20.0:
                cls = "Very Low"
            elif sdi < 40.0:
                cls = "Low"
            elif sdi < 60.0:
                cls = "Moderate"
            elif sdi < 80.0:
                cls = "High"
            else:
                cls = "Very High"
            return f"{sdi:.1f}% ({cls})"
        except Exception:
            return "—"

    def _update_sdi_label(self):
        try:
            if not hasattr(self.dlg, "lblSDI_value"):
                return
            nugget = float(self.dlg.spinOKNugget.value()) if hasattr(self.dlg, "spinOKNugget") else None
            psill = float(self.dlg.spinOKPsill.value()) if hasattr(self.dlg, "spinOKPsill") else None
            if nugget is None or psill is None:
                return
            self.dlg.lblSDI_value.setText(self._compute_sdi_text(nugget, psill))
        except Exception:
            pass

    def eventFilter(self, obj, event):
        try:
            lbl = getattr(self.dlg, "lbl_SDI", None)
            if obj is lbl and event is not None:
                if event.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick, QEvent.Enter):
                    try:
                        QToolTip.showText(QCursor.pos(), lbl.toolTip() or "", lbl)
                        return True
                    except Exception:
                        return False
        except Exception:
            pass
        return False

    def _ensure_sdi_info_icon(self):
        """Append an info icon to lbl_SDI and attach tooltip (hover + click).
        - If a Qt resource icon exists (e.g. :/plugins/BestFitInterpolator/info_sdi.png), it is used.
        - Otherwise falls back to a simple [i] text marker.
        """
        try:
            lbl = getattr(self.dlg, "lbl_SDI", None)
            if lbl is None:
                return
            tooltip_html = (
                "<div>"
                "<div style='margin-bottom:4px'><b>Equation</b>: SDI = C / (C + C<sub>0</sub>) × 100%</div>"
                "<div><b>Classes</b></div>"
                "<table border='1' cellspacing='0' cellpadding='3' style='border-collapse:collapse;'>"
                "<tr><td style='padding:2px'>&lt; 20%</td><td style='padding:2px'>Very Low</td></tr>"
                "<tr><td style='padding:2px'>[20, 40)</td><td style='padding:2px'>Low</td></tr>"
                "<tr><td style='padding:2px'>[40, 60)</td><td style='padding:2px'>Moderate</td></tr>"
                "<tr><td style='padding:2px'>[60, 80)</td><td style='padding:2px'>High</td></tr>"
                "<tr><td style='padding:2px'>&ge; 80%</td><td style='padding:2px'>Very High</td></tr>"
                "</table>"
                "</div>"
            )
            try:
                lbl.setToolTip(tooltip_html)
                # Ensure rich text rendering and clickable cursor
                try:
                    lbl.setTextFormat(Qt.RichText)
                except Exception:
                    pass
                try:
                    lbl.setCursor(Qt.PointingHandCursor)
                except Exception:
                    pass
                # Ensure white tooltip background (scoped to this dialog)
                try:
                    self._ensure_tooltip_style()
                except Exception:
                    pass
            except Exception:
                pass
            base = getattr(self, "_sdi_label_base_text", None)
            if base is None:
                try:
                    base = str(lbl.text())
                except Exception:
                    base = "SDI"
                self._sdi_label_base_text = base
            # Try to embed an icon named 'info.png' (resource or file fallback)
            icon_src = self._resolve_info_icon_src()
            if icon_src:
                img_tag = f"<img src='{icon_src}' width='12' height='12'/>"
                new_text = f"{base}  {img_tag}"
                try:
                    lbl.setText(new_text)
                except Exception:
                    pass
            else:
                # Fallback to a plain [i]
                try:
                    lbl.setText(f"{base}  [i]")
                except Exception:
                    pass
            if not hasattr(self, "_sdi_filter_installed") or not self._sdi_filter_installed:
                try:
                    lbl.installEventFilter(self)
                    self._sdi_filter_installed = True
                except Exception:
                    pass
        except Exception:
            pass

    def _ensure_tooltip_style(self):
        """Apply a white background style to QToolTip withsin this dialog only."""
        try:
            if getattr(self, "_tooltip_css_applied", False):
                return
            css = "QToolTip { background-color: #ffffff; color: #222222; border: 1px solid #888888; padding: 4px; }"
            prev = self.dlg.styleSheet() or ""
            if css not in prev:
                # Append to avoid clobbering existing styles
                combined = (prev + "\n" + css).strip()
                self.dlg.setStyleSheet(combined)
            self._tooltip_css_applied = True
        except Exception:
            pass

    def _resolve_info_icon_src(self) -> str:
        """Return a src string for an 'info.png' icon if available.
        Tries Qt resource first, then plugin folder fallbacks.
        """
        # 1) Qt resource
        for rsrc in (":/plugins/BestFitInterpolator/info.png",
                     ":/plugins/BestFitInterpolator/icons/info.png"):
            try:
                pm = QPixmap()
                if pm.load(rsrc):
                    return rsrc
            except Exception:
                pass
        # 2) File fallbacks
        try:
            base = getattr(self, 'plugin_dir', None)
            if base:
                for rel in ("info.png", os.path.join("icons", "info.png")):
                    full = os.path.join(base, rel)
                    pm = QPixmap()
                    if pm.load(full):
                        # file path works in <img src='...'>
                        return full
        except Exception:
            pass
        return ""

    def _fit_reml_if_needed(self, x, y, z):
        """Fit REML once if in REML mode and not yet fitted. Does not draw experimental."""
        if not self._use_reml or self._reml_fitted:
            return
        cutoff = self._cutoff or (float(np.max(np.hypot(x - x.mean(), y - y.mean()))) if x.size else 1.0)
        lagw = self._lag_width or max(1e-9, float(np.min(np.hypot(x[1:] - x[:-1], y[1:] - y[:-1]))) if x.size > 1 else 1.0)
        lagw = self._safe_lag_width(x, y, cutoff, lagw)
        # Seed with MoM-like heuristics using a temporary experimental (not stored)
        lags_tmp, gamma_tmp = self._bin_variogram(x, y, z, cutoff, lagw)
        if lags_tmp.size > 0:
            lags_tmp = np.insert(lags_tmp, 0, 0.0)
            gamma_tmp = np.insert(gamma_tmp, 0, 0.0)
            nugget0, psill0, rng0 = self._guess_initial_params(
                lags_tmp[1:], gamma_tmp[1:], cutoff, model=self._get_selected_model()
            )
        else:
            # Fallback seeds
            nugget0, psill0, rng0 = 0.0, float(np.var(z, ddof=1) if z.size > 1 else 1.0), max(cutoff * 0.5, 1.0)

        # Run REML optimization
        model_txt = self._model_text_from_token(self._get_selected_model())
        reml_res = fit_ok_reml_interface(
            sample_xyz=np.column_stack([x, y, z]),
            model=model_txt,
            init_from_mom={"nugget": nugget0, "psill": psill0, "range": rng0},
            random_state=123,
        )
        rnug = float(reml_res.get("nugget", nugget0))
        rps  = float(reml_res.get("psill", psill0))
        rrng = float(reml_res.get("range", rng0))
        if np.isfinite(rnug) and np.isfinite(rps) and np.isfinite(rrng):
            self._init_params = (rnug, rps, rrng)
            self._ok_fit_method = "REML"
            self._reml_fitted = True
            # Reflect into UI and overlay theoretical-only curve
            try:
                self._programmatic_variogram_update = True
                if hasattr(self.dlg, "spinOKNugget"):
                    self.dlg.spinOKNugget.setValue(float(rnug))
                if hasattr(self.dlg, "spinOKPsill"):
                    self.dlg.spinOKPsill.setValue(float(rps))
                if hasattr(self.dlg, "spinOKRange"):
                    self.dlg.spinOKRange.setValue(float(rrng))
            except Exception:
                pass
            finally:
                self._programmatic_variogram_update = False
            self._update_headers(self.z_field, self._n, cutoff, lagw)
            try:
                self._update_sdi_label()
            except Exception:
                pass
            self._plot_with_model_if_possible()
            try:
                QCoreApplication.processEvents()
            except Exception:
                pass

    def _plot_with_model_if_possible(self):
        """Overlay the theoretical model on the variogram axes.
        - If experimental exists, plot points + model.
        - If in REML mode (no experimental), plot model only.
        """
        if self._krig_vario_fig is None:
            return
        # In REML mode, avoid plotting until we have a fitted model
        if self._use_reml and not self._reml_fitted:
            ax = self._krig_vario_fig.axes[0] if self._krig_vario_fig.axes else self._krig_vario_fig.add_subplot(111)
            ax.clear()
            ax.set_title("Semivariogram (REML model)")
            ax.set_xlabel("Lag distance (h)")
            ax.set_ylabel("Semivariance γ(h)")
            ax.set_xlim(left=0.0, right=max(self._cutoff or 1.0, 1.0))
            ax.set_ylim(bottom=0.0)
            ax.grid(True)
            self._krig_vario_canvas.draw()
            return

        # Start with initial params; then allow UI overrides
        nugget = self._init_params[0] if self._init_params else 0.0
        psill  = self._init_params[1] if self._init_params else 1.0
        rng    = self._init_params[2] if self._init_params else max(1.0, (self._cutoff or 1.0) * 0.5)
        try:
            nugget = float(self.dlg.spinOKNugget.value())
        except Exception:
            pass
        try:
            psill = float(self.dlg.spinOKPsill.value())
        except Exception:
            pass
        try:
            rng = float(self.dlg.spinOKRange.value())
        except Exception:
            pass
        model = self._get_selected_model()

        ax = self._krig_vario_fig.axes[0] if self._krig_vario_fig.axes else self._krig_vario_fig.add_subplot(111)
        ax.clear()
        lags_plot = None
        gamma_plot = None
        if (self._exp_lags is not None) and (self._exp_gamma is not None) and (not self._use_reml):
            lags_plot = self._exp_lags[1:] if getattr(self._exp_lags, 'size', 0) > 1 else self._exp_lags
            gamma_plot = self._exp_gamma[1:] if getattr(self._exp_gamma, 'size', 0) > 1 else self._exp_gamma
            ax.plot(lags_plot, gamma_plot, 'o', label="Experimental", color=EXP_COLOR)

        if self._cutoff is not None:
            xmax = max(self._cutoff, 1.0)
        elif lags_plot is not None and hasattr(lags_plot, 'size') and lags_plot.size:
            xmax = max(float(lags_plot.max()), 1.0)
        elif (self._exp_lags is not None) and hasattr(self._exp_lags, 'size') and self._exp_lags.size:
            xmax = max(float(self._exp_lags.max()), 1.0)
        else:
            xmax = 1.0
        h_line = np.linspace(0.0, xmax, 200)
        th = self._model_func(h_line, model, nugget, psill, rng)
        ax.plot(h_line, th, '-', label=f"Theoretical ({model.capitalize()})", color=TH_COLOR, linewidth=2)

        ax.set_title("Semivariogram", fontsize=10)
        ax.set_xlabel("Lag distance (h)", fontsize=9)
        ax.set_ylabel("Semivariance γ(h)", fontsize=9)
        ax.set_xlim(left=0.0, right=xmax); ax.set_ylim(bottom=0.0)
        ax.xaxis.set_major_locator(MaxNLocator(nbins=8)); ax.yaxis.set_major_locator(MaxNLocator(nbins=6))
        xf = ScalarFormatter(useOffset=False, useMathText=False); xf.set_scientific(False)
        yf = ScalarFormatter(useOffset=False, useMathText=False); yf.set_scientific(False)
        ax.xaxis.set_major_formatter(xf); ax.yaxis.set_major_formatter(yf)
        ax.tick_params(axis='x', rotation=0)
        ax.tick_params(axis='both', labelsize=8)
        ax.grid(True, linestyle='--', linewidth=0.5, alpha=0.6)
        if (self._exp_lags is not None) and (self._exp_gamma is not None) and (not self._use_reml):
            ax.legend(fontsize=9, frameon=False)
        self._krig_vario_canvas.draw()

    # ---------------------------- Interpolation map ---------------------------

    def _on_interpolate_clicked(self):
        if not self.is_dispatcher_active():
            return
        """Predict on grid inside polygon extent (pure Python OK) with a modal progress dialog."""
        if self._is_interpolating:
            return
        self._is_interpolating = True
        if self._interpolate_btn is not None:
            try:
                self._interpolate_btn.setEnabled(False)
            except Exception:
                pass
        self._ensure_variogram_ready()
        self._sync_variogram_state_from_ui()

        # BLOQUEAMOS cualquier actualización del variograma durante la interpolación
        self._block_variogram_updates = True

        try:
            self._ensure_canvas()
            self._ensure_inputs_from_ui()

            # Inputs
            x, y, z = self._read_xy_z()
            if x is None:
                self.iface.messageBar().pushMessage("Kriging", "There are no valid points/variables.", level=2)
                return

            poly_layer = self._resolve_polygon_layer()
            if poly_layer is None:
                self.iface.messageBar().pushMessage("Kriging", "Select a polygon layer.", level=2)
                return

            pixel = self._resolve_pixel_size()
            if pixel is None or pixel <= 0:
                pixel = max((poly_layer.extent().width(), poly_layer.extent().height())) / 100.0

            # Build grid
            extent = poly_layer.extent()
            xmin, xmax = extent.xMinimum(), extent.xMaximum()
            ymin, ymax = extent.yMinimum(), extent.yMaximum()

            n_cols = int(max(1, np.ceil((xmax - xmin) / pixel)))
            n_rows = int(max(1, np.ceil((ymax - ymin) / pixel)))

            x_coords = xmin + pixel * (np.arange(n_cols) + 0.5)
            y_coords = ymax - pixel * (np.arange(n_rows) + 0.5)
            grid_points = np.array([(xc, yc) for yc in y_coords for xc in x_coords], dtype=float)

            # Clip to polygon(s)
            inside_mask = self._points_inside_polygon_mask(grid_points, poly_layer)
            if not np.any(inside_mask):
                self.iface.messageBar().pushMessage("Kriging", "The grid does not fall within the polygon.", level=1)
                return

            inside_idx = np.where(inside_mask)[0]
            inside_pts = grid_points[inside_idx]
            n_pred = inside_pts.shape[0]

            if n_pred > 800_000:
                self.iface.messageBar().pushWarning(
                    "Kriging",
                    f"Many cells to predict ({n_pred:,}). Consider increasing the pixel size."
                )

            prog = QProgressDialog("Running kriging...", "Cancel", 0, n_pred, self.dlg)
            prog.setWindowModality(Qt.ApplicationModal)
            prog.setMinimumDuration(0)
            prog.setValue(0)

            def _progress(done, total):
                prog.setValue(done)
                if prog.wasCanceled():
                    raise KeyboardInterrupt

            # --- AQUÍ usamos SIEMPRE lo que está en los spin boxes ---
            model = self._get_selected_model()
            nugget, psill, rng = self._read_params_from_ui()

            try:
                preds = ordinary_kriging_interpolation(
                    x, y, z,
                    inside_pts[:, 0], inside_pts[:, 1],
                    nugget, psill, rng, model,
                    progress_fn=_progress
                )
            except KeyboardInterrupt:
                prog.cancel()
                self.iface.messageBar().pushMessage("Kriging", "Canceled for the user.", level=1)
                return
            except Exception as e:
                prog.cancel()
                self.iface.messageBar().pushMessage("Kriging", f"Kriging failed: {e}", level=2)
                return
            finally:
                prog.close()

            # Rellenar grid
            result = np.full((n_rows, n_cols), np.nan, dtype=float)
            for j, flat_i in enumerate(inside_idx):
                col = flat_i % n_cols
                row = flat_i // n_cols
                result[row, col] = preds[j]

            var_label = self.z_field or "Z"
            self._maybe_export_ok_raster(result, xmin, xmax, ymin, ymax, pixel, poly_layer, var_label, model)
            self._plot_kriging_map(result, xmin, xmax, ymin, ymax, poly_layer, var_label=var_label)
            self._record_ok_interpolation_for_validation(
                "MoM", x, y, z, model, nugget, psill, rng, pixel, poly_layer, var_label
            )
            self.iface.messageBar().pushMessage("Kriging", "Interpolation complete.", level=0)

            # MUY IMPORTANTE: solo redibujamos el modelo con LOS VALORES ACTUALES,
            # sin recalcular semillas ni tocar el experimental.
            try:
                self._plot_with_model_if_possible()
            except Exception:
                pass

        finally:
            # Siempre liberamos el bloqueo y reactivamos el botón
            self._block_variogram_updates = False
            self._finish_interpolate_ui()

    def _finish_interpolate_ui(self):
        """Re-enable interpolate button after a run finishes."""
        self._is_interpolating = False
        if self._interpolate_btn is not None:
            try:
                self._interpolate_btn.setEnabled(True)
            except Exception:
                pass

    def _record_ok_interpolation_for_validation(self, backend, x, y, z, model, nugget, psill, rng, pixel, poly_layer, var_label):
        plugin = getattr(self, "parent_plugin", None)
        if plugin is None or not hasattr(plugin, "_record_ok_interpolation"):
            return
        try:
            points_name = self.points_layer.name() if self.points_layer is not None and hasattr(self.points_layer, "name") else ""
        except Exception:
            points_name = ""
        try:
            polygon_name = poly_layer.name() if poly_layer is not None and hasattr(poly_layer, "name") else ""
        except Exception:
            polygon_name = ""
        try:
            plugin._record_ok_interpolation(
                backend,
                points_name,
                var_label or self.z_field or "Z",
                polygon_name,
                float(pixel),
                np.column_stack((x, y, z)),
                model,
                nugget,
                psill,
                rng,
            )
        except Exception:
            pass

    def _resolve_polygon_layer(self):
        """Try common widget names to get selected polygon layer by name."""
        cand_names = ("poly", "cmbPolygonLayer", "cmbPoly", "cmbMask")
        layer_name = None
        for nm in cand_names:
            w = getattr(self.dlg, nm, None)
            if w is not None and hasattr(w, "currentText"):
                txt = w.currentText()
                if txt:
                    layer_name = txt
                    break
        if not layer_name:
            return None
        layers = QgsProject.instance().mapLayersByName(layer_name)
        if not layers:
            return None
        lyr = layers[0]
        try:
            gt = lyr.geometryType()
            if gt == QgsWkbTypes.PolygonGeometry or (QgsWkbTypes.isMultiType(lyr.wkbType()) and gt == QgsWkbTypes.PolygonGeometry):
                return lyr
        except Exception:
            pass
        return None

    def _resolve_pixel_size(self):
        """Try to fetch pixel size from common widgets (kriging or deterministic)."""
        for nm in ("spinOKPixelSize", "spinPixelSize", "pixelsize"):
            w = getattr(self.dlg, nm, None)
            if w is not None:
                try:
                    return float(w.value()) if hasattr(w, "value") else float(w.text())
                except Exception:
                    continue
        return None

    def _build_ok_raster_path(self, variable_name: str, model_token: str) -> str:
        """Create an output path inside the project folder (BestFitInterpolation) or temp."""
        proj_path = QgsProject.instance().fileName()
        if self._should_export_raster() and proj_path:
            base_dir = os.path.dirname(proj_path)
            out_dir = os.path.join(base_dir, "BestFitInterpolation")
        else:
            out_dir = tempfile.gettempdir()
        os.makedirs(out_dir, exist_ok=True)
        safe_var = (variable_name or "variable").replace(" ", "_")
        safe_model = (model_token or "OK").replace(" ", "_")
        fname = f"OK_{safe_model}_{safe_var}_{uuid.uuid4().hex[:6]}.tif"
        return os.path.join(out_dir, fname)

    def _should_export_raster(self):
        chk = getattr(self.dlg, "chkExportRaster", None)
        if chk is None:
            return True
        try:
            return bool(chk.isChecked())
        except Exception:
            return True

    def _is_temporary_output_path(self, path):
        try:
            tmp_dir = os.path.abspath(tempfile.gettempdir())
            out_path = os.path.abspath(str(path))
            return os.path.commonpath([tmp_dir, out_path]) == tmp_dir
        except Exception:
            return False

    def _mark_temporary_layer(self, layer, raster_path=None):
        is_temporary = (not self._should_export_raster()) or self._is_temporary_output_path(raster_path)
        if layer is None or not is_temporary:
            return
        try:
            layer.setCustomProperty("bestfitinterpolator/output_storage", "temporary")
            layer.setCustomProperty("bestfitinterpolator/exported_to_project_folder", False)
            layer.setCustomProperty("skipMemoryLayersCheck", 0)
        except Exception:
            pass

    def _create_output_raster_layer(self, raster_path, layer_name):
        is_temporary = (not self._should_export_raster()) or self._is_temporary_output_path(raster_path)
        layer_cls = BestFitTemporaryRasterLayer if is_temporary else QgsRasterLayer
        layer = layer_cls(raster_path, layer_name, "gdal")
        if is_temporary:
            if not hasattr(self, "_temporary_output_layers"):
                self._temporary_output_layers = []
            self._temporary_output_layers.append(layer)
        return layer
        for method_name in ("setIsTemporary", "setTemporary"):
            method = getattr(layer, method_name, None)
            if callable(method):
                try:
                    method(True)
                except Exception:
                    pass
        try:
            flag_enum = getattr(QgsMapLayer, "LayerFlag", None)
            flag = getattr(flag_enum, "Temporary", None) if flag_enum is not None else None
            if flag is None:
                flag = getattr(QgsMapLayer, "Temporary", None)
            if flag is not None and hasattr(layer, "setFlags") and hasattr(layer, "flags"):
                layer.setFlags(layer.flags() | flag)
        except Exception:
            pass

    def _write_ok_raster(self, array, xmin, xmax, ymin, ymax, pixel, polygon_layer, variable_name, model_token):
        """Persist the kriging grid as GeoTIFF and return the path."""
        if pixel is None or pixel <= 0:
            raise ValueError("Invalid pixel size for export.")
        n_rows, n_cols = array.shape
        raster_path = self._build_ok_raster_path(variable_name, model_token)
        driver = gdal.GetDriverByName("GTiff")
        dataset = driver.Create(raster_path, n_cols, n_rows, 1, gdal.GDT_Float32)
        if dataset is None:
            raise RuntimeError("Unable to create GeoTIFF dataset.")
        geotransform = (xmin, pixel, 0, ymax, 0, -pixel)
        dataset.SetGeoTransform(geotransform)
        try:
            crs = polygon_layer.crs() if polygon_layer is not None else None
            if crs and crs.isValid():
                srs = osr.SpatialReference()
                srs.ImportFromWkt(crs.toWkt())
                dataset.SetProjection(srs.ExportToWkt())
        except Exception:
            pass
        band = dataset.GetRasterBand(1)
        band.WriteArray(array)
        band.SetNoDataValue(np.nan)
        band.FlushCache()
        dataset.FlushCache()
        dataset = None
        return raster_path

    def _maybe_export_ok_raster(self, array, xmin, xmax, ymin, ymax, pixel, polygon_layer, variable_label, model_token):
        """Export and add the raster when the export checkbox is enabled."""
        try:
            out_path = self._write_ok_raster(
                array, xmin, xmax, ymin, ymax, pixel,
                polygon_layer, variable_label, model_token
            )
        except Exception as exc:
            self.iface.messageBar().pushWarning("Kriging", f"Failed to export raster: {exc}")
            return
        layer_name = f"OK {model_token.capitalize()} ({variable_label})"
        layer = self._create_output_raster_layer(out_path, layer_name)
        if not layer.isValid():
            self.iface.messageBar().pushWarning("Kriging", "Raster created but is invalid for QGIS.")
            return
        self._mark_temporary_layer(layer, out_path)
        QgsProject.instance().addMapLayer(layer)
        self.iface.messageBar().pushMessage("Kriging", f"Raster added to QGIS: {out_path}", level=0)

    def _points_inside_polygon_mask(self, grid_points, polygon_layer):
        """Return boolean mask of points inside any polygon (handles multipart)."""
        mask = np.zeros(grid_points.shape[0], dtype=bool)
        try:
            for feat in polygon_layer.getFeatures():
                geom = feat.geometry()
                if geom.isMultipart():
                    for part in geom.asMultiPolygon():
                        for ring in part:
                            ring_coords = [(pt.x(), pt.y()) for pt in ring]
                            path = MplPath(ring_coords)
                            mask = np.logical_or(mask, path.contains_points(grid_points))
                else:
                    for ring in geom.asPolygon():
                        ring_coords = [(pt.x(), pt.y()) for pt in ring]
                        path = MplPath(ring_coords)
                        mask = np.logical_or(mask, path.contains_points(grid_points))
        except Exception:
            pass
        return mask

    def _read_params_from_ui(self):
        """Read nugget/psill/range from UI, fallback to initial."""
        n, p, r = (0.0, 1.0, max(1.0, (self._cutoff or 1.0) * 0.5)) if not self._init_params else self._init_params
        try:
            n = float(self.dlg.spinOKNugget.value())
        except Exception:
            pass
        try:
            p = float(self.dlg.spinOKPsill.value())
        except Exception:
            pass
        try:
            r = float(self.dlg.spinOKRange.value())
        except Exception:
            pass
        return n, p, r

    # ------------------------- Pure-Python OK backend -------------------------

    def _krige_predict_python(self, x, y, z, grid_xy, model, nugget, psill, rng):
        """Predict via pure-Python ordinary kriging on (grid_xy[:,0], grid_xy[:,1])."""
        # Map normalized token -> the short token expected by our Python kriging
        model_short = {"exponential": "Exp", "gaussian": "Gau", "spherical": "Sph"}.get(model, "Exp")
        try:
            xp = grid_xy[:, 0]
            yp = grid_xy[:, 1]
            pred = ordinary_kriging_interpolation(
                x, y, z,
                xp, yp,
                float(nugget), float(psill), float(rng),
                model_short
            )
            return np.asarray(pred, dtype=float)
        except Exception as e:
            self.iface.messageBar().pushMessage("Kriging", f"Python kriging failed: {e}", level=2)
            return None

    # ------------------------------ Map plotting ------------------------------

    def _plot_kriging_map(self, result_array, xmin, xmax, ymin, ymax, polygon_layer, var_label="Z"):
        """Plot gridded predictions clipped by polygon using viridis and a labeled colorbar."""
        if self._krig_map_fig is None or self._krig_map_canvas is None:
            # Ensure canvas
            container_m = getattr(self.dlg, "canvasOKInterpolation", None) or getattr(self.dlg, "CanvasOKInterpolation", None)
            if container_m is None:
                self.iface.messageBar().pushMessage("Kriging", "There is no canvas for the kriging map.", level=1)
                return
            self._krig_map_fig = Figure(figsize=(5, 4), tight_layout=True)
            self._krig_map_canvas = FigureCanvas(self._krig_map_fig)
            self._stabilize_canvas_widget(self._krig_map_canvas)
            layout = container_m.layout() or QVBoxLayout(container_m)
            for i in reversed(range(layout.count())):
                w = layout.itemAt(i).widget()
                if w is not None:
                    w.setParent(None)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._krig_map_canvas)

        self._krig_map_fig.clear()
        ax = self._krig_map_fig.add_subplot(111)

        ax.set_title("Ordinary Kriging", fontsize=10)
        ax.set_xlabel("X", fontsize=9); ax.set_ylabel("Y", fontsize=9)

        n_rows, n_cols = result_array.shape
        x_edges = np.linspace(xmin, xmax, n_cols + 1)
        y_edges = np.linspace(ymin, ymax, n_rows + 1)

        disp_array = np.flipud(result_array)  # y increasing up
        masked = np.ma.masked_invalid(disp_array)

        pm = ax.pcolormesh(x_edges, y_edges, masked, cmap="viridis", shading="auto")
        cbar = self._krig_map_fig.colorbar(pm, ax=ax, orientation='vertical')
        cbar.set_label(var_label)

        # outline polygons
        try:
            for feat in polygon_layer.getFeatures():
                geom = feat.geometry()
                if geom.isMultipart():
                    for part in geom.asMultiPolygon():
                        for ring in part:
                            ring_xy = [(pt.x(), pt.y()) for pt in ring]
                            patch = MplPolygon(ring_xy, closed=True, edgecolor="black", facecolor="none", linewidth=1.0)
                            ax.add_patch(patch)
                else:
                    for ring in geom.asPolygon():
                        ring_xy = [(pt.x(), pt.y()) for pt in ring]
                        patch = MplPolygon(ring_xy, closed=True, edgecolor="black", facecolor="none", linewidth=1.0)
                        ax.add_patch(patch)
        except Exception:
            pass

        ax.set_xlim(xmin, xmax); ax.set_ylim(ymin, ymax)
        # Use normal number format, but smaller labels and fewer ticks for readability
        try:
            ax.xaxis.set_major_locator(MaxNLocator(nbins=6))
            ax.yaxis.set_major_locator(MaxNLocator(nbins=6))
        except Exception:
            pass
        ax.tick_params(axis='both', labelsize=8)
        try:
            self._krig_map_fig.tight_layout()
        except Exception:
            pass
        self._krig_map_canvas.draw()

    def clear_plots(self):
        """Clear variogram and map canvases and reset REML flags (used on data/variable change)."""
        # Clear variogram (blank)
        try:
            if self._krig_vario_fig is not None and self._krig_vario_canvas is not None:
                self._krig_vario_fig.clear()
                self._krig_vario_canvas.draw()
        except Exception:
            pass
        # Clear map (blank)
        try:
            if self._krig_map_fig is not None and self._krig_map_canvas is not None:
                self._krig_map_fig.clear()
                self._krig_map_canvas.draw()
        except Exception:
            pass
        # Reset state flags
        self._exp_lags, self._exp_gamma = None, None
        self._reml_fitted = False

    # ----------------------- Resolve inputs from UI if needed -----------------

    def _layer_is_alive(self, layer) -> bool:
        if layer is None:
            return False
        try:
            layer.id()
            return True
        except RuntimeError:
            return False
        except Exception:
            return False

    def _maybe_pull_points_layer_from_ui(self):
        for name in ("cmbPointsLayer", "cmbLayerPoints", "Points", "cmbPoints"):
            w = getattr(self.dlg, name, None)
            if w is not None and hasattr(w, "currentText"):
                lname = w.currentText()
                if lname:
                    layers = QgsProject.instance().mapLayersByName(lname)
                    if layers:
                        self.points_layer = layers[0]
                        return
        self.points_layer = None

    def _ensure_inputs_from_ui(self):
        if not self._layer_is_alive(self.points_layer):
            self.points_layer = None
        self._maybe_pull_points_layer_from_ui()
        if not self.z_field:
            self._maybe_pull_field_from_ui()
