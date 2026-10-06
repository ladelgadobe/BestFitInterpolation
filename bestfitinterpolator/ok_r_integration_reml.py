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
from .theme import save_figure
from .compat import enum_value, qt_exec
from .theme import COLORS

from .compat import ControllerConnections, is_alive, log_exception
import math
import os
from .semivariogram_engine import SemivariogramEngine
from .diagnostics_ui import feature_in_analysis
from .compat import geometry_type, enum_value
import numpy as np
from qgis.PyQt.QtCore import Qt, QCoreApplication
from qgis.PyQt.QtWidgets import (
    QProgressDialog, QFileDialog, QMenu, QDialog, QMessageBox, QSizePolicy,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QLabel, QSpinBox,
)

from qgis.PyQt.QtWidgets import QVBoxLayout
from matplotlib.figure import Figure
from .mpl_compat import FigureCanvas
from matplotlib.ticker import MaxNLocator, ScalarFormatter
from matplotlib.path import Path as MplPath
from matplotlib.patches import Polygon as MplPolygon
from qgis.core import QgsProject, QgsWkbTypes, QgsMapLayer, QgsRasterLayer
from osgeo import gdal, osr
import tempfile
import uuid

# Optional REML backend (SciPy-based); fall back to MoM if unavailable
try:
    from .reml_bridge import fit_ok_reml_interface, cv_ok_reml_interface
    from .kriging_reml import _HAS_SCIPY as _REML_SCIPY
    _HAS_REML = bool(_REML_SCIPY)
except Exception:
    _HAS_REML = False
    cv_ok_reml_interface = None

# Pure-Python kriging backend (already used by your other path)
from .kriging_ordinary import ordinary_kriging_interpolation
from .grid_utils import build_inside_grid_points
from .performance_policy import (
    dense_method_notice,
    is_dense_dataset,
    is_massive_dataset,
    representative_sample_indices,
)
from .validation_policy import decide_automatic_cv
from .variogram_utils import (
    bin_experimental_variogram,
    max_pairwise_distance,
    nearest_neighbor_distance,
    safe_lag_width,
)

# Centralized colors
EXP_COLOR = COLORS["primary"]   # experimental points
TH_COLOR  = COLORS["primary_dark"]   # theoretical curve
REML_SAMPLE_LIMIT = 500
GEOSTAT_DENSE_HOLDOUT_MAX_TEST = 2000
GEOSTAT_MASSIVE_HOLDOUT_MAX_TEST = 5000


class BestFitTemporaryRasterLayer(QgsRasterLayer):
    """Raster layer wrapper used so QGIS can identify plugin temp outputs."""
    def isTemporary(self):
        return True


class OKTabController(ControllerConnections):
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
        self._programmatic_variogram_update = False
        self._user_variogram_overrides = False

        # Handoff from main plugin class for CV
        self.run_ok_cv_function = None

        # Baselines
        self._baseline_initial = None  # first auto baseline (heuristics) for current layer/field
        self._baseline_last = None     # last computed (auto or manual)

        self._dispatcher_active = True
        self._semivariogram_stale = True
        self._wire_signals()
        try:
            self._update_sdi_label()
        except Exception:  # nosec B110
            pass

    def set_dispatcher_active(self, state: bool):
        """Enable or disable this controller when used by the dispatcher."""
        self._dispatcher_active = bool(state)

    def is_dispatcher_active(self) -> bool:
        return bool(getattr(self, "_dispatcher_active", True))

    # ------------------------- Model auto-selection --------------------------

    def _candidate_model_tokens(self):
        return getattr(self, "_candidate_overrides", ("spherical", "exponential", "gaussian"))

    @staticmethod
    def _model_text_from_token(token: str) -> str:
        return SemivariogramEngine("ok_reml")._model_text_from_token(token)

    def _ensure_model_selector_defaults(self):
        cmb = getattr(self.dlg, "cmbOKModel", None)
        if cmb is None or not hasattr(cmb, "count"):
            return
        try:
            has_auto = any(str(cmb.itemText(i)).strip().lower().startswith("auto") for i in range(cmb.count()))
            if not has_auto:
                cmb.insertItem(0, "Automatic")
                cmb.setCurrentIndex(0)
        except Exception:  # nosec B110
            pass

    def _is_auto_model_selection(self) -> bool:
        cmb = getattr(self.dlg, "cmbOKModel", None)
        if cmb is None or not hasattr(cmb, "currentText"):
            return False
        return str(cmb.currentText() or "").strip().lower().startswith("auto")

    @staticmethod
    def _validation_metrics(obs, pred):
        return SemivariogramEngine("ok_reml")._validation_metrics(obs, pred)

    @staticmethod
    def _fmt_metric(value, decimals=3, suffix=""):
        try:
            value = float(value)
        except Exception:
            return "--"
        if not np.isfinite(value):
            return "--"
        return f"{value:.{decimals}f}{suffix}"

    def _evaluate_model_cv(self, model_key: str, x, y, z, cutoff, lagw):
        return SemivariogramEngine("ok_reml", use_reml=self._use_reml)._evaluate_model_cv(model_key, x, y, z, cutoff, lagw)

    def _evaluate_model_variogram_fit(self, model_key: str, x, y, z, cutoff, lagw):
        return SemivariogramEngine("ok_reml")._evaluate_model_variogram_fit(model_key, x, y, z, cutoff, lagw)

    def _choose_best_model_by_validation(self, x, y, z, cutoff, lagw):
        rows = []
        for model_key in self._candidate_model_tokens():
            try:
                rows.append(self._evaluate_model_cv(model_key, x, y, z, cutoff, lagw))
            except Exception as exc:
                rows.append({
                    "model": self._model_text_from_token(model_key),
                    "model_key": model_key,
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
                -(float(r.get("lccc")) if np.isfinite(float(r.get("lccc", float("nan")))) else -1e300),
                float(r.get("rmse")) if np.isfinite(float(r.get("rmse", float("nan")))) else 1e300,
                -(float(r.get("r2")) if np.isfinite(float(r.get("r2", float("nan")))) else -1e300),
            ),
        )
        best = ranked[0] if ranked else {"model_key": "exponential"}
        self._model_validation_results = ranked
        self._auto_selected_model = str(best.get("model_key") or "exponential")
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
        except Exception:  # nosec B110
            pass
        finally:
            self._programmatic_variogram_update = False
        btn = getattr(self.dlg, "btnOKModelValidation", None)
        if btn is not None and hasattr(btn, "setToolTip"):
            metric_text = (
                f"LCCC={self._fmt_metric(best.get('lccc'))}; "
                f"RMSE={self._fmt_metric(best.get('rmse'))}"
            )
            btn.setToolTip(
                f"Best automatic model: {self._model_text_from_token(self._auto_selected_model)} "
                f"({metric_text}). Click to view all model validation results."
            )
        return self._auto_selected_model

    def _show_model_validation_dialog(self):
        """Review current candidates in the shared asynchronous validation window."""
        from .semivariogram_dialog import show_advanced_settings
        self._ensure_inputs_from_ui()
        self._model_validation_results=[]
        show_advanced_settings(self,validate=True)

    # ------------------------------ Wiring ----------------------------------

    def _wire_signals(self):
        """Connect UI signals for Kriging tab."""
        self._ensure_model_selector_defaults()
        self._ensure_lag_mode_controls()
        try:
            self._connect(self.dlg.mainTabs.currentChanged, self._on_tab_changed)
        except Exception:  # nosec B110
            pass

        # Calculate (recompute experimental + overlay)
        if hasattr(self.dlg, "btnOKCalculate") and self.dlg.btnOKCalculate is not None:
            try:
                self._connect(self.dlg.btnOKCalculate.clicked, self._on_recalculate_clicked)
            except Exception:  # nosec B110
                pass

        # CV button (in validation tab)
        btn_cv = getattr(self.dlg, "btnOKRunCV", None)
        if btn_cv is not None:
            self._connect(btn_cv.clicked, self._on_run_cv_clicked)

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
                    self._connect(w.valueChanged, self._plot_with_model_if_possible)
                    self._connect(w.valueChanged, self._update_sdi_label)
                except Exception:  # nosec B110
                    pass

        for wname in ("cmbOKModel", "spinOKCutoff", "spinOKLag", "spinOKNugget", "spinOKPsill", "spinOKRange"):
            w = getattr(self.dlg, wname, None)
            if w is None:
                continue
            if hasattr(w, "valueChanged"):
                try:
                    self._connect(w.valueChanged, self._on_variogram_ui_changed)
                except Exception:  # nosec B110
                    pass
            if hasattr(w, "currentIndexChanged"):
                try:
                    self._connect(w.currentIndexChanged, self._on_variogram_ui_changed)
                except Exception:  # nosec B110
                    pass
            if hasattr(w, "currentIndexChanged"):
                try:
                    self._connect(w.currentIndexChanged, self._plot_with_model_if_possible)
                    self._connect(w.currentIndexChanged, self._update_sdi_label)
                except Exception:  # nosec B110
                    pass

        btn_model_validation = getattr(self.dlg, "btnOKModelValidation", None)
        if btn_model_validation is not None and hasattr(btn_model_validation, "clicked"):
            try:
                self._connect(btn_model_validation.clicked, self._show_model_validation_dialog)
            except Exception:  # nosec B110
                pass

        for name in ("spinOKCutoff", "spinOKLag"):
            widget = getattr(self.dlg, name, None)
            if widget is not None:
                self._connect(widget.valueChanged, self._schedule_rebin)

        # Data-layer and variable changes are coordinated by BestFitInterpolator._update_ok_context.
        # Do not connect them here; duplicate controller slots can fire while QGIS is rebuilding layers.

    def _ensure_lag_mode_controls(self):
        """Add optional lag-count controls next to the existing lag-width workflow."""
        if getattr(self.dlg, "cmbOKLagMode", None) is not None:
            self._connect(self.dlg.cmbOKLagMode.currentIndexChanged, self._on_lag_mode_changed)
            self._connect(self.dlg.spinOKLagCount.valueChanged, self._on_lag_count_changed)
            return
        spin_lag = getattr(self.dlg, "spinOKLag", None)
        if spin_lag is None:
            return
        parent = None
        layout = None
        try:
            parent = spin_lag.parentWidget()
            layout = parent.layout() if parent is not None else None
        except Exception:
            layout = None
        if layout is None or not hasattr(layout, "addWidget"):
            return
        try:
            mode_label = QLabel("Lag input:", parent)
            mode_label.setObjectName("lblOKLagMode")
            mode_combo = QComboBox(parent)
            mode_combo.setObjectName("cmbOKLagMode")
            mode_combo.addItems(["Lag distance", "Number of lags"])
            count_label = QLabel("Number of lags:", parent)
            count_label.setObjectName("lblOKLagCount")
            count_spin = QSpinBox(parent)
            count_spin.setObjectName("spinOKLagCount")
            count_spin.setRange(1, 10000)
            count_spin.setValue(24 if is_massive_dataset(getattr(self, "_n", 0)) else 36)
            row = layout.rowCount() if hasattr(layout, "rowCount") else 7
            layout.addWidget(mode_label, row, 0)
            layout.addWidget(mode_combo, row, 1)
            layout.addWidget(count_label, row + 1, 0)
            layout.addWidget(count_spin, row + 1, 1)
            self.dlg.cmbOKLagMode = mode_combo
            self.dlg.spinOKLagCount = count_spin
            self.dlg.lblOKLagMode = mode_label
            self.dlg.lblOKLagCount = count_label
            self._connect(mode_combo.currentIndexChanged, self._on_lag_mode_changed)
            self._connect(count_spin.valueChanged, self._on_lag_count_changed)
            self._programmatic_variogram_update = True
            try:
                self._on_lag_mode_changed()
            finally:
                self._programmatic_variogram_update = False
        except Exception:  # nosec B110
            pass

    def _lag_mode_is_count(self) -> bool:
        cmb = getattr(self.dlg, "cmbOKLagMode", None)
        try:
            return cmb is not None and "number" in str(cmb.currentText() or "").strip().lower()
        except Exception:
            return False

    def _lag_count_value(self) -> int:
        spin = getattr(self.dlg, "spinOKLagCount", None)
        try:
            return max(1, int(spin.value()))
        except Exception:
            return 24 if is_massive_dataset(getattr(self, "_n", 0)) else 36

    def _apply_lag_count_to_width(self, cutoff=None):
        if not self._lag_mode_is_count():
            return None
        try:
            cutoff_val = float(self._cutoff if cutoff is None else cutoff)
        except Exception:
            return None
        if not np.isfinite(cutoff_val) or cutoff_val <= 0:
            return None
        lagw = cutoff_val / float(max(1, self._lag_count_value()))
        spin = getattr(self.dlg, "spinOKLag", None)
        if spin is not None and hasattr(spin, "setValue"):
            try:
                self._programmatic_variogram_update = True
                spin.setValue(float(lagw))
            except Exception:  # nosec B110
                pass
            finally:
                self._programmatic_variogram_update = False
        return float(lagw)

    def _lag_width_from_controls(self, x, y, cutoff, default_lag_width):
        """Resolve lag width either directly or from a requested number of lags."""
        if self._lag_mode_is_count():
            lagw = self._apply_lag_count_to_width(cutoff)
            if lagw is None:
                lagw = float(default_lag_width)
        else:
            lagw = float(default_lag_width)
            try:
                spin = getattr(self.dlg, "spinOKLag", None)
                if spin is not None and hasattr(spin, "value") and float(spin.value()) > 0:
                    lagw = float(spin.value())
            except Exception:  # nosec B110
                pass
        lagw = self._safe_lag_width(x, y, cutoff, lagw)
        if self._lag_mode_is_count():
            spin = getattr(self.dlg, "spinOKLag", None)
            if spin is not None and hasattr(spin, "setValue"):
                try:
                    self._programmatic_variogram_update = True
                    spin.setValue(float(lagw))
                except Exception:  # nosec B110
                    pass
                finally:
                    self._programmatic_variogram_update = False
        return lagw

    def _on_lag_mode_changed(self, *args) -> None:
        spin = getattr(self.dlg, "spinOKLagCount", None)
        label = getattr(self.dlg, "lblOKLagCount", None)
        enabled = self._lag_mode_is_count()
        for widget in (spin, label):
            try:
                if widget is not None and hasattr(widget, "setEnabled"):
                    widget.setEnabled(enabled)
            except Exception:  # nosec B110
                pass
        if enabled:
            self._apply_lag_count_to_width()
        self._on_variogram_ui_changed()
        self._schedule_rebin()

    def _on_lag_count_changed(self, *args) -> None:
        self._apply_lag_count_to_width()
        self._on_variogram_ui_changed()
        self._schedule_rebin()

    def _hook_interpolate_button(self):
        """Wire the kriging interpolate button to run map generation."""
        btn = None
        for name in ("btnOKInterpolate", "btnKrigInterpolate", "btnOKRun"):
            w = getattr(self.dlg, name, None)
            if w is not None and hasattr(w, "clicked"):
                btn = w
                break
        if btn is not None:
            try:
                self._connect(btn.clicked, self._on_interpolate_clicked)
            except Exception:  # nosec B110
                pass

    def _hook_reset_button_by_common_names(self) -> bool:
        """Try common reset button objectNames. Return True if hooked."""
        for bname in ("btnOKReset", "btnOKDefaults", "btnOKRevert", "btnOKParamsReset", "btnReset"):
            btn = getattr(self.dlg, bname, None)
            if btn is not None and hasattr(btn, "clicked"):
                try:
                    self._connect(btn.clicked, self._on_reset_clicked)
                    return True
                except Exception:  # nosec B110
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
                    except Exception:  # nosec B110
                        pass
                    text = ""
                    try:
                        if hasattr(obj, "text"):
                            text = (obj.text() or "").lower()
                    except Exception:  # nosec B110
                        pass
                    hay = any(k in name for k in ("reset", "default", "reiniciar", "restablecer")) or \
                          any(k in text for k in ("reset", "default", "reiniciar", "restablecer"))
                    if hay:
                        try:
                            self._connect(obj.clicked, self._on_reset_clicked)
                            return
                        except Exception:  # nosec B112
                            continue
        except Exception:  # nosec B110
            pass

    # ---------------------- Layer/field handoff from main ---------------------

    def set_points_layer_and_field(self, layer, field):
        if not self.is_dispatcher_active():
            return
        """Receive the currently selected points layer and field from the main class."""
        self.points_layer = layer
        self.z_field = field
        # Invalidate initial baseline for new context
        self._baseline_initial = None
        self._user_variogram_overrides = False
        self._model_validation_results = []
        self._exp_lags = self._exp_gamma = None
        self._semivariogram_stale = True
        # Reset REML state on context change
        self._use_reml = False
        self._reml_fitted = False
        # Compute immediately for the current context.
        # The previous version only ran when the tab text was exactly "kriging",
        # which fails in this plugin because the visible tab name is "Geostatistics".
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
        try:
            self._ensure_inputs_from_ui()
            if not self._ensure_canvas():
                return False
            had_params = self._init_params is not None
            self._sync_variogram_state_from_ui()
            if self._semivariogram_stale:
                self.calculate_and_plot_experimental(initial_load=False, reseed_params=False)
            if self._variogram_has_drawn_content() and (self._exp_lags is not None or self._reml_fitted):
                self._plot_with_model_if_possible()
                return True
            if self._user_variogram_overrides or had_params:
                self._use_reml = True
                self._reml_fitted = True
                self._ok_fit_method = "REML"
                self._plot_with_model_if_possible()
                return self._variogram_has_drawn_content()
            self.calculate_and_plot_experimental(initial_load=(self._init_params is None))
            return self._variogram_has_drawn_content()
        except Exception:
            log_exception("Geostatistics readiness failed")
            return False

    def _on_variogram_ui_changed(self, *args) -> None:
        """Track manual edits so interpolation never restores automatic REML seeds."""
        if getattr(self, "_programmatic_variogram_update", False):
            return
        self._user_variogram_overrides = True
        self._sync_variogram_state_from_ui()
        if self._use_reml:
            self._reml_fitted = True

    def _sync_variogram_state_from_ui(self) -> None:
        """Mirror current semivariogram controls into controller state without fitting."""
        try:
            if hasattr(self.dlg, "spinOKCutoff"):
                self._cutoff = float(self.dlg.spinOKCutoff.value())
        except Exception:  # nosec B110
            pass
        try:
            if hasattr(self.dlg, "spinOKLag"):
                lagw = self._apply_lag_count_to_width(self._cutoff) if self._lag_mode_is_count() else None
                self._lag_width = float(lagw if lagw is not None else self.dlg.spinOKLag.value())
        except Exception:  # nosec B110
            pass
        try:
            self._init_params = tuple(float(v) for v in self._read_params_from_ui())
        except Exception:  # nosec B110
            pass

    def _on_tab_changed(self, index):
        """Triggered when the user switches tabs."""
        if not self.is_dispatcher_active():
            return
        try:
            tab_text = ""
            tabs = getattr(self.dlg, "mainTabs", None)
            if tabs is not None and hasattr(tabs, "tabText"):
                tab_text = str(tabs.tabText(index) or "").strip().lower()
            if "regression" in tab_text or (tab_text and not any(token in tab_text for token in ("geo", "krig", "geostat"))):
                return
            self._ensure_inputs_from_ui()
            self._ensure_variogram_ready()
        except Exception:
            log_exception("Geostatistics tab refresh failed")

    # ----------------------- Model & variable helpers ------------------------

    def _normalize_model_token(self, txt: str) -> str:
        return SemivariogramEngine("ok_reml")._normalize_model_token(txt)

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
                if str(itxt).strip().lower().startswith("auto"):
                    continue
                if self._normalize_model_token(itxt) == token:
                    cmb.setCurrentIndex(i)
                    return
        except Exception:  # nosec B110
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
        self.calculate_and_plot_experimental(initial_load=False)
        # If small sample size and REML available, fit now on Calculate
        try:
            x, y, z = self._read_xy_z()
        except Exception:
            x = y = z = None
        if x is not None and _HAS_REML and z is not None and len(z) < REML_SAMPLE_LIMIT:
            try:
                # Enter REML mode, clear experimental, fit once, and plot theoretical only
                self._use_reml = True
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
        except Exception:  # nosec B110
            pass
        finally:
            self._programmatic_variogram_update = False
        try:
            self._programmatic_variogram_update = True
            self._set_model_combo_by_token(baseline.get("model", "exponential"))
        except Exception:  # nosec B110
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
        except Exception:  # nosec B110
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
            if not feature_in_analysis(getattr(self, "parent_plugin", None), self.points_layer, feat):
                continue
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
                except Exception:  # nosec B112
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
        return np.asarray([max_pairwise_distance(x, y)], dtype=float)

    @staticmethod
    def _nearest_neighbor_dist(x, y):
        """Return the minimum positive nearest-neighbor distance."""
        return nearest_neighbor_distance(x, y)

    def _safe_lag_width(self, x, y, cutoff, lag_width, max_bins=10000):
        """Keep lag width positive while preventing pathological bin counts."""
        return safe_lag_width(x, y, cutoff, lag_width, max_bins=max_bins)

    @staticmethod
    def _semivariances(z):
        """Return a callable γ(i, J) = 0.5 * (i - J)^2 to vectorize per-pair values."""
        def gamma(i_val, j_vals):
            diff = i_val - j_vals
            return 0.5 * (diff * diff)
        return gamma

    def _bin_variogram(self, x, y, z, cutoff, lag_width):
        """Compute binned experimental semivariogram up to 'cutoff' with bin size 'lag_width'."""
        lags, gamma, info = bin_experimental_variogram(
            x, y, z, cutoff, lag_width, return_info=True
        )
        self._variogram_pair_info = info
        return lags, gamma

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
        return SemivariogramEngine("ok_reml")._guess_initial_params(lags, gamma, cutoff, model)

    # ----------------------------- UI helpers ---------------------------------

    def _ensure_canvas(self):
        """Ensure variogram and map canvases exist and are attached."""
        # Variogram
        container_v = getattr(self.dlg, "CanvasOKVariogram", None) or getattr(self.dlg, "canvasOKVariogram", None)
        if container_v is not None and not is_alive(self._krig_vario_canvas):
            self._krig_vario_fig = Figure(figsize=(5, 4), tight_layout=True)
            self._krig_vario_canvas = FigureCanvas(self._krig_vario_fig)
            self._stabilize_canvas_widget(self._krig_vario_canvas)
            layout = container_v.layout()
            if layout is None:
                layout = QVBoxLayout(container_v)
            for i in reversed(range(layout.count())):
                w = layout.itemAt(i).widget()
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._krig_vario_canvas)
            self._install_save_png_handler(self._krig_vario_canvas, self._krig_vario_fig, default_prefix="kriging_variogram")

        # Map
        container_m = getattr(self.dlg, "canvasOKInterpolation", None) or getattr(self.dlg, "CanvasOKInterpolation", None)
        if container_m is not None and not is_alive(self._krig_map_canvas):
            self._krig_map_fig = Figure(figsize=(5, 4), tight_layout=True)
            self._krig_map_canvas = FigureCanvas(self._krig_map_fig)
            self._krig_map_canvas._bfi_is_map = True
            self._stabilize_canvas_widget(self._krig_map_canvas)
            layout = container_m.layout()
            if layout is None:
                layout = QVBoxLayout(container_m)
            for i in reversed(range(layout.count())):
                w = layout.itemAt(i).widget()
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(self._krig_map_canvas)
            self._install_save_png_handler(self._krig_map_canvas, self._krig_map_fig, default_prefix="kriging_map")

        return (self._krig_vario_canvas is not None)

    def _stabilize_canvas_widget(self, canvas):
        """Keep Matplotlib canvases from resizing their parent after redraws."""
        try:
            canvas.setSizePolicy(enum_value(QSizePolicy, "Policy", "Expanding"), enum_value(QSizePolicy, "Policy", "Expanding"))
            canvas.setMinimumSize(120, 160)
            canvas.updateGeometry()
        except Exception:  # nosec B110
            pass

    # ----------------------------- Save PNG hooks -----------------------------

    def _install_save_png_handler(self, canvas, fig, default_prefix: str):
        """Install right-click context menu 'Save graph' on a Matplotlib canvas."""
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
                canvas.setContextMenuPolicy(enum_value(Qt, "ContextMenuPolicy", "CustomContextMenu"))
            except Exception:  # nosec B110
                pass

            def _show_menu(pos):
                try:
                    menu = QMenu(self.dlg)
                    act_view = menu.addAction("View larger view")
                    act_copy = menu.addAction("Copy graph")
                    act_save = menu.addAction("Save graph")
                    chosen = qt_exec(menu, canvas.mapToGlobal(pos))
                    if chosen == act_view:
                        self._show_larger_graph(fig, default_prefix)
                    elif chosen == act_copy:
                        self._copy_figure_to_clipboard(fig)
                    elif chosen == act_save:
                        suggested_dir = os.path.expanduser("~")
                        suggested = os.path.join(suggested_dir, f"{default_prefix}.png")
                        path, _ = QFileDialog.getSaveFileName(self.dlg, "Save graph", suggested, "PNG Images (*.png)")
                        if path:
                            save_figure(fig, path, dpi=300, bbox_inches='tight')
                            try:
                                self.iface.messageBar().pushMessage("Saved", f"PNG saved to: {path}", level=0)
                            except Exception:  # nosec B110
                                pass
                except Exception:  # nosec B110
                    pass

            try:
                self._connect(canvas.customContextMenuRequested, _show_menu)
            except Exception:
                # Fallback to raw mpl right-click
                def _on_click(event):
                    try:
                        if getattr(event, 'button', None) == 3:
                            _show_menu(canvas.mapFromGlobal(canvas.cursor().pos()))
                    except Exception:  # nosec B110
                        pass
                canvas.mpl_connect('button_press_event', _on_click)

            self._save_handlers.add(key)
        except Exception:  # nosec B110
            pass

    def _copy_figure_to_clipboard(self, fig) -> None:
        """Copy a Matplotlib figure to the system clipboard as a PNG image."""
        try:
            import io
            from qgis.PyQt.QtGui import QPixmap
            from qgis.PyQt.QtWidgets import QApplication
            buf = io.BytesIO()
            save_figure(fig, buf, format="png", dpi=300, bbox_inches="tight")
            pixmap = QPixmap()
            pixmap.loadFromData(buf.getvalue(), "PNG")
            QApplication.clipboard().setPixmap(pixmap)
            try:
                self.iface.messageBar().pushMessage("Copied", "Graph copied to clipboard.", level=0)
            except Exception:  # nosec B110
                pass
        except Exception as exc:
            QMessageBox.warning(self.dlg, "Copy graph", f"Could not copy graph:\n{exc}")

    def _show_larger_graph(self, source_fig, title_prefix: str):
        from .larger_view import show_larger_view
        return show_larger_view(source_fig,self.dlg,title_prefix + ' Larger view')

    def _update_headers(self, var_name, n, cutoff, lagw):
        """Update small UI labels/fields regarding the current context."""
        if hasattr(self.dlg, "valOKZName") and hasattr(self.dlg, "valOKSamples"):
            try:
                self.dlg.valOKZName.setText(str(var_name))
                self.dlg.valOKSamples.setText(str(n))
            except Exception:  # nosec B110
                pass
        # Display which fitting method is active (value label in UI is 'valOKModel')
        label_val = getattr(self.dlg, "valOKModel", None)
        if label_val is not None and hasattr(label_val, "setText"):
            try:
                label_val.setText(self._ok_fit_method)
            except Exception:  # nosec B110
                pass
        else:
            # Backward-compat for older UI naming
            label_compat = getattr(self.dlg, "lblFitTitle", None) or getattr(self.dlg, "lblOKModel", None)
            if label_compat is not None and hasattr(label_compat, "setText"):
                try:
                    label_compat.setText(self._ok_fit_method)
                except Exception:  # nosec B110
                    pass
        if hasattr(self.dlg, "spinOKCutoff") and hasattr(self.dlg, "spinOKLag"):
            try:
                self._programmatic_variogram_update = True
                self.dlg.spinOKCutoff.setValue(float(cutoff))
                self.dlg.spinOKLag.setValue(float(lagw))
            except Exception:  # nosec B110
                pass
            finally:
                self._programmatic_variogram_update = False
        try:
            self._update_sdi_label()
        except Exception:  # nosec B110
            pass

    # -------------------------- Public main actions ---------------------------

    def calculate_and_plot_experimental(self, initial_load=True, reseed_params=None):
        """Compute and plot the experimental semivariogram, then seed initial params."""
        reseed_params = bool(initial_load) if reseed_params is None else bool(reseed_params)
        if not self._ensure_canvas():
            return
        x, y, z = self._read_xy_z()
        if x is None:
            self._exp_lags = self._exp_gamma = None
            self._model_validation_results = []
            self._krig_vario_fig.clear()
            ax = self._krig_vario_fig.add_subplot(111)
            ax.text(.5, .5, "At least five valid observations are required", ha="center")
            self._krig_vario_canvas.draw_idle()
            self.iface.messageBar().pushMessage(
                "Kriging",
                "Select point layer and variable in the Data tab",
                level=1
            )
            return
        self._n = len(z)
        all_d = self._pairwise_distances(x, y)
        d_max = float(np.nanmax(all_d))
        nn_min = float(self._nearest_neighbor_dist(x, y))
        cutoff = 0.5 * d_max
        lagw = self._lag_width_from_controls(x, y, cutoff, nn_min)
        if not initial_load:
            try:
                cutoff = float(self.dlg.spinOKCutoff.value())
            except Exception:  # nosec B110
                pass
            lagw = self._lag_width_from_controls(x, y, cutoff, lagw)
        self._cutoff = cutoff
        self._lag_width = lagw

        # Published 1.1 fits REML from the observations. Bins are internal seeds,
        # never an experimental series displayed alongside the REML curve.
        self._use_reml = bool(_HAS_REML and (self._n < REML_SAMPLE_LIMIT))
        self._exp_lags = self._exp_gamma = None
        if not self._use_reml:
            display_lags, display_gamma = self._bin_variogram(x, y, z, cutoff, lagw)
            self._exp_lags = np.insert(display_lags, 0, 0.)
            self._exp_gamma = np.insert(display_gamma, 0, 0.)
        self._semivariogram_stale = False

        # Rebinning changes the experimental display, not a manually chosen fit.
        if not reseed_params and not self._is_auto_model_selection() and self._init_params is not None:
            self._sync_variogram_state_from_ui()
            self._update_headers(self.z_field, self._n, cutoff, lagw)
            self._plot_with_model_if_possible()
            return

        # Decide REML usage and, if enabled, fit immediately and draw theoretical-only curve
        if self._is_auto_model_selection():
            try:
                self._choose_best_model_by_validation(x, y, z, cutoff, lagw)
            except Exception:
                self._auto_selected_model = "exponential"
        if self._use_reml:
            self._ok_fit_method = "REML"
            self._reml_fitted = False
            try:
                self._fit_reml_if_needed(x, y, z)
            except Exception:
                # If REML fails, continue with MoM below
                self._use_reml = False
                self._ok_fit_method = "MoM"
            else:
                # Already plotted theoretical-only inside _fit_reml_if_needed
                return

        lags, gamma = self._bin_variogram(x, y, z, cutoff, lagw)
        if lags.size == 0:
            lags = np.array([0.0])
            gamma = np.array([0.0])
        else:
            # prepend the origin for nicer display
            lags = np.insert(lags, 0, 0.0)
            gamma = np.insert(gamma, 0, 0.0)

        self._exp_lags, self._exp_gamma = lags, gamma
        self._semivariogram_stale = False

        # Start with MoM-like heuristics as baseline and show immediately
        nugget, psill, rng = self._guess_initial_params(lags[1:], gamma[1:], cutoff, model=self._get_selected_model())
        # Always show MoM as initial method; REML will be applied on Interpolate
        self._ok_fit_method = "MoM"
        self._init_params = (nugget, psill, rng)

        # Update headers and parameter widgets (MoM seeds first for instant feedback)
        self._update_headers(self.z_field, self._n, cutoff, lagw)
        try:
            self._programmatic_variogram_update = True
            if hasattr(self.dlg, "spinOKNugget"):
                self.dlg.spinOKNugget.setValue(float(nugget))
            if hasattr(self.dlg, "spinOKPsill"):
                self.dlg.spinOKPsill.setValue(float(psill))
            if hasattr(self.dlg, "spinOKRange"):
                self.dlg.spinOKRange.setValue(float(rng))
        except Exception:  # nosec B110
            pass
        finally:
            self._programmatic_variogram_update = False

        # Store baselines (for Reset)
        current_baseline = {
            "cutoff": cutoff, "lagw": lagw,
            "nugget": nugget, "psill": psill, "range": rng,
            "model": self._get_selected_model()
        }
        if initial_load and not self._baseline_initial:
            self._baseline_initial = dict(current_baseline)
        self._baseline_last = dict(current_baseline)

        # Plot experimental points (draw now so UI updates even if REML takes time)
        ax = self._krig_vario_fig.axes[0] if self._krig_vario_fig.axes else self._krig_vario_fig.add_subplot(111)
        ax.clear()
        lags_plot = lags[1:] if lags.size > 1 else lags
        gamma_plot = gamma[1:] if gamma.size > 1 else gamma
        ax.plot(lags_plot, gamma_plot, 'o', label="Experimental", color=EXP_COLOR)
        ax.set_title("Semivariogram", fontsize=10)
        ax.set_xlabel("Lag distance (h)", fontsize=9)
        ax.set_ylabel("Semivariance γ(h)", fontsize=9)
        ax.set_xlim(left=0.0, right=max(cutoff, (lags_plot.max() if lags_plot.size else 1.0)))
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
        # Overlay with current params
        self._plot_with_model_if_possible()
        try:
            QCoreApplication.processEvents()
        except Exception:  # nosec B110
            pass

    # -------------------------- Theoretical model -----------------------------

    def _model_func(self, h, model, nugget, psill, rng):
        return SemivariogramEngine("ok_reml")._model_func(h, model, nugget, psill, rng)

    # ------------------------------- SDI helpers -------------------------------

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
            lbl = getattr(self.dlg, "lblSDI_value", None)
            if lbl is None:
                return
            nugget = float(self.dlg.spinOKNugget.value()) if hasattr(self.dlg, "spinOKNugget") else None
            psill = float(self.dlg.spinOKPsill.value()) if hasattr(self.dlg, "spinOKPsill") else None
            if nugget is None or psill is None:
                lbl.setText("—")
                return
            lbl.setText(self._compute_sdi_text(nugget, psill))
        except Exception:  # nosec B110
            pass


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
            nugget0, psill0, rng0 = self._guess_initial_params(lags_tmp[1:], gamma_tmp[1:], cutoff, model=self._get_selected_model())
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
            except Exception:  # nosec B110
                pass
            finally:
                self._programmatic_variogram_update = False
            self._update_headers(self.z_field, self._n, cutoff, lagw)
            try:
                self._update_sdi_label()
            except Exception:  # nosec B110
                pass
            self._plot_with_model_if_possible()
            try:
                QCoreApplication.processEvents()
            except Exception:  # nosec B110
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
        except Exception:  # nosec B110
            pass
        try:
            psill = float(self.dlg.spinOKPsill.value())
        except Exception:  # nosec B110
            pass
        try:
            rng = float(self.dlg.spinOKRange.value())
        except Exception:  # nosec B110
            pass
        model = self._get_selected_model()

        ax = self._krig_vario_fig.axes[0] if self._krig_vario_fig.axes else self._krig_vario_fig.add_subplot(111)
        ax.clear()
        lags_plot = None
        gamma_plot = None
        if (self._exp_lags is not None) and (self._exp_gamma is not None) and not self._use_reml:
            lags_plot = self._exp_lags[1:] if getattr(self._exp_lags, 'size', 0) > 1 else self._exp_lags
            gamma_plot = self._exp_gamma[1:] if getattr(self._exp_gamma, 'size', 0) > 1 else self._exp_gamma
            ax.plot(lags_plot, gamma_plot, 'o', label="Experimental", color=EXP_COLOR)

        if self._cutoff is not None:
            xmax = max(self._cutoff, 1.0)
        elif lags_plot is not None and hasattr(lags_plot, 'size') and lags_plot.size:
            xmax = max(float(lags_plot.max()), 1.0)
        else:
            xmax = 1.0
        h_line = np.linspace(0.0, xmax, 200)
        th = self._model_func(h_line, model, nugget, psill, rng)
        ax.plot(h_line, th, '-', label=f"Theoretical ({model.capitalize()})", color=TH_COLOR, linewidth=2)

        ax.set_title("Semivariogram (REML model)" if self._use_reml else "Semivariogram", fontsize=10)
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
        ax.legend(fontsize=9, frameon=False)
        self._krig_vario_canvas.draw()

    # ---------------------------- Interpolation map ---------------------------

    def _on_interpolate_clicked(self):
        if not self.is_dispatcher_active():
            return
        """Predict on grid inside polygon extent (pure Python OK) with a modal progress dialog."""
        self._ensure_variogram_ready()
        self._sync_variogram_state_from_ui()
        self._ensure_canvas()
        # Inputs
        x, y, z = self._read_xy_z()
        if x is None:
            self._exp_lags = self._exp_gamma = None
            self._model_validation_results = []
            self._krig_vario_fig.clear()
            ax = self._krig_vario_fig.add_subplot(111)
            ax.text(.5, .5, "At least five valid observations are required", ha="center")
            self._krig_vario_canvas.draw_idle()
            self.iface.messageBar().pushMessage("Kriging", "There are no valid points/variables.", level=2)
            return
        self._active_dense_notice = ""
        if is_dense_dataset(len(z)):
            self._active_dense_notice = dense_method_notice(len(z), "Ordinary Kriging")
        poly_layer = self._resolve_polygon_layer()
        if poly_layer is None:
            self.iface.messageBar().pushMessage("Kriging", "Select a polygon layer.", level=2)
            return
        plugin = getattr(self, "parent_plugin", None)
        if (
            plugin is not None
            and hasattr(plugin, "_validate_current_interpolation_coverage")
            and not plugin._validate_current_interpolation_coverage("Kriging")
        ):
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
        inside_pts, inside_idx = build_inside_grid_points(
            x_coords,
            y_coords,
            lambda points: self._points_inside_polygon_mask(points, poly_layer),
        )
        if inside_idx.size == 0:
            self.iface.messageBar().pushMessage("Kriging", "The grid does not fall within the polygon.", level=1)
            return
        n_pred = inside_pts.shape[0]

        # Warn and auto-guard very large grids
        if n_pred > 800_000:
            self.iface.messageBar().pushWarning("Kriging",
                f"Many cells to predict ({n_pred:,}). Consider increasing the pixel size.")
        # Setup progress dialog (modal, closes automatically)
        prog = QProgressDialog("Running kriging", "Cancel", 0, n_pred, self.dlg)
        prog.setWindowModality(enum_value(Qt, "WindowModality", "ApplicationModal"))
        prog.setMinimumDuration(0)
        prog.setValue(0)

        def _progress(done, total):
            prog.setValue(done)
            # allow UI to repaint
            QCoreApplication.processEvents()
            if prog.wasCanceled():
                # raise a lightweight exception to unwind cleanly
                raise KeyboardInterrupt

        model = self._get_selected_model()
        nugget, psill, rng = self._read_params_from_ui()

        try:
            # Call OK with progress callback
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

        # Fill array and plot
        result = np.full((n_rows, n_cols), np.nan, dtype=float)
        result[inside_idx // n_cols, inside_idx % n_cols] = preds

        self._maybe_export_ok_raster(result, xmin, xmax, ymin, ymax, pixel, poly_layer, (self.z_field or "Z"), model)
        self._plot_kriging_map(result, xmin, xmax, ymin, ymax, poly_layer, var_label=(self.z_field or "Z"))
        self._record_ok_interpolation_for_validation(
            "MoM", x, y, z, model, nugget, psill, rng, pixel, poly_layer, (self.z_field or "Z")
        )


    def _build_ok_raster_path(self, variable_name: str, model_token: str) -> str:
        proj_path = QgsProject.instance().fileName()
        if self._should_export_raster() and proj_path:
            base_dir = os.path.dirname(proj_path)
            out_dir = os.path.join(base_dir, "BestFitInterpolation")
        else:
            out_dir = tempfile.gettempdir()
        os.makedirs(out_dir, exist_ok=True)
        safe_var = (variable_name or "variable").replace(" ", "_")
        safe_model = (model_token or "OK_REML").replace(" ", "_")
        fname = f"OK_REML_{safe_model}_{safe_var}_{uuid.uuid4().hex[:6]}.tif"
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
        except Exception:  # nosec B110
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
                except Exception:  # nosec B110
                    pass
        try:
            flag_enum = getattr(QgsMapLayer, "LayerFlag", None)
            flag = getattr(flag_enum, "Temporary", None) if flag_enum is not None else None
            if flag is None:
                flag = getattr(QgsMapLayer, "Temporary", None)
            if flag is not None and hasattr(layer, "setFlags") and hasattr(layer, "flags"):
                layer.setFlags(layer.flags() | flag)
        except Exception:  # nosec B110
            pass

    def _write_ok_raster(self, array, xmin, xmax, ymin, ymax, pixel, polygon_layer, variable_name, model_token):
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
        except Exception:  # nosec B110
            pass
        dense_notice = str(getattr(self, "_active_dense_notice", "") or "")
        if dense_notice:
            dataset.SetMetadataItem("BESTFIT_DENSE_PROFILE", dense_notice)
        band = dataset.GetRasterBand(1)
        band.WriteArray(array)
        band.SetNoDataValue(np.nan)
        band.FlushCache()
        dataset.FlushCache()
        dataset = None
        return raster_path

    def _maybe_export_ok_raster(self, array, xmin, xmax, ymin, ymax, pixel, polygon_layer, variable_label, model_token):
        self._last_output_path=None
        try:
            out_path = self._write_ok_raster(array, xmin, xmax, ymin, ymax, pixel, polygon_layer, variable_label, model_token)
        except Exception as exc:
            self.iface.messageBar().pushWarning("Kriging REML", f"Failed to export raster: {exc}")
            return
        layer_name = f"OK REML {model_token.capitalize()} ({variable_label})"
        layer = self._create_output_raster_layer(out_path, layer_name)
        if not layer.isValid():
            self.iface.messageBar().pushWarning("Kriging REML", "Raster created but is invalid for QGIS.")
            return
        self._mark_temporary_layer(layer, out_path)
        QgsProject.instance().addMapLayer(layer)
        self._last_output_path=out_path
        self.iface.messageBar().pushMessage("Kriging REML", f"Raster added to QGIS: {out_path}", level=0)


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
            if gt == geometry_type("Polygon") or (QgsWkbTypes.isMultiType(lyr.wkbType()) and gt == geometry_type("Polygon")):
                return lyr
        except Exception:  # nosec B110
            pass
        return None

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
        except Exception:  # nosec B110
            pass

        from .interpolation_result import publish_result
        config=dict(backend=backend,variable=var_label,model=model,nugget=nugget,psill=psill,var_range=rng,pixel_size=pixel)
        publish_result(self,'OK',config,self._krig_map_fig,raster_path=getattr(self,'_last_output_path',None))

    def _resolve_pixel_size(self):
        """Try to fetch pixel size from common widgets (kriging or deterministic)."""
        for nm in ("spinOKPixelSize", "spinPixelSize", "pixelsize"):
            w = getattr(self.dlg, nm, None)
            if w is not None:
                try:
                    return float(w.value()) if hasattr(w, "value") else float(w.text())
                except Exception:  # nosec B112
                    continue
        return None

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
        except Exception:  # nosec B110
            pass
        return mask

    def _read_params_from_ui(self):
        """Read nugget/psill/range from UI, fallback to initial."""
        n, p, r = (0.0, 1.0, max(1.0, (self._cutoff or 1.0) * 0.5)) if not self._init_params else self._init_params
        try:
            n = float(self.dlg.spinOKNugget.value())
        except Exception:  # nosec B110
            pass
        try:
            p = float(self.dlg.spinOKPsill.value())
        except Exception:  # nosec B110
            pass
        try:
            r = float(self.dlg.spinOKRange.value())
        except Exception:  # nosec B110
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
            self._krig_map_canvas._bfi_is_map = True
            self._stabilize_canvas_widget(self._krig_map_canvas)
            layout = container_m.layout()
            if layout is None:
                layout = QVBoxLayout(container_m)
            for i in reversed(range(layout.count())):
                w = layout.itemAt(i).widget()
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()
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
        except Exception:  # nosec B110
            pass

        ax.set_xlim(xmin, xmax); ax.set_ylim(ymin, ymax)
        # Use normal number format, but smaller labels and fewer ticks for readability
        try:
            ax.xaxis.set_major_locator(MaxNLocator(nbins=6))
            ax.yaxis.set_major_locator(MaxNLocator(nbins=6))
        except Exception:  # nosec B110
            pass
        ax.tick_params(axis='both', labelsize=8)
        try:
            self._krig_map_fig.tight_layout()
        except Exception:  # nosec B110
            pass
        self._krig_map_canvas.draw()

    def clear_plots(self):
        """Clear variogram and map canvases and reset REML flags (used on data/variable change)."""
        # Clear variogram (blank)
        try:
            if self._krig_vario_fig is not None and self._krig_vario_canvas is not None:
                self._krig_vario_fig.clear()
                self._krig_vario_canvas.draw()
        except Exception:  # nosec B110
            pass
        # Clear map (blank)
        try:
            if self._krig_map_fig is not None and self._krig_map_canvas is not None:
                self._krig_map_fig.clear()
                self._krig_map_canvas.draw()
        except Exception:  # nosec B110
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
                try:
                    if hasattr(w, "currentData"):
                        layer_id = w.currentData()
                        if layer_id:
                            layer = QgsProject.instance().mapLayer(layer_id)
                            if layer is not None:
                                self.points_layer = layer
                                return
                except Exception:  # nosec B110
                    pass
                lname = w.currentText()
                if lname:
                    layers = QgsProject.instance().mapLayersByName(lname)
                    if layers:
                        self.points_layer = layers[0]
                        return
        self.points_layer = None

    def _field_exists_in_layer(self, field_name) -> bool:
        if not field_name or not self._layer_is_alive(self.points_layer):
            return False
        try:
            return self.points_layer.fields().indexOf(str(field_name)) >= 0
        except Exception:
            return False

    def _ensure_inputs_from_ui(self):
        if not self._layer_is_alive(self.points_layer):
            self.points_layer = None
        self._maybe_pull_points_layer_from_ui()
        current_field = None
        try:
            for name in ("cmbZField", "cmbField", "cmbVariable", "cmbOKField", "Points_2"):
                w = getattr(self.dlg, name, None)
                if w is not None and hasattr(w, "currentText"):
                    text = str(w.currentText() or "").strip()
                    if text:
                        current_field = text
                        break
        except Exception:  # nosec B110
            current_field = None
        if current_field and current_field != self.z_field:
            self.z_field = current_field
            self._model_validation_results = []
        if not self._field_exists_in_layer(self.z_field):
            self.z_field = None
            self._maybe_pull_field_from_ui()
        if not self._field_exists_in_layer(self.z_field):
            self.z_field = None
