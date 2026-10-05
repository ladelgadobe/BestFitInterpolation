# -*- coding: utf-8 -*-
"""
framework_sdi_dialog.py

Standalone SDI / semivariogram popup for the Framework tab.
This version keeps the Framework workflow isolated while mirroring the
semivariogram logic already used in the geostatistics path.

All code comments are in English.
"""

from __future__ import annotations
from .theme import save_figure
from .compat import enum_value, qt_exec
from .semivariogram_engine import SemivariogramEngine
from .theme import COLORS

from dataclasses import dataclass
from typing import Any, Dict, Optional

import math
import os
import tempfile
import numpy as np

try:
    from .variogram_utils import (
        bin_experimental_variogram,
        max_pairwise_distance,
        nearest_neighbor_distance,
        safe_lag_width,
    )
except Exception:  # pragma: no cover
    from variogram_utils import (  # type: ignore
        bin_experimental_variogram,
        max_pairwise_distance,
        nearest_neighbor_distance,
        safe_lag_width,
    )

try:
    from qgis.PyQt.QtCore import Qt, QCoreApplication
    from qgis.PyQt.QtWidgets import (
        QDialog,
        QVBoxLayout,
        QHBoxLayout,
        QFormLayout,
        QGroupBox,
        QLabel,
        QDoubleSpinBox,
        QPushButton,
        QComboBox,
        QMessageBox,
        QFileDialog,
        QMenu,
        QDialogButtonBox,
        QWidget,
    )
    from matplotlib.figure import Figure
    try:
        from .mpl_compat import FigureCanvas
    except Exception:  # pragma: no cover
        from mpl_compat import FigureCanvas  # type: ignore
    from matplotlib.ticker import MaxNLocator, ScalarFormatter
except Exception:  # pragma: no cover
    from qgis.PyQt.QtCore import Qt, QCoreApplication
    from qgis.PyQt.QtWidgets import (
        QDialog,
        QVBoxLayout,
        QHBoxLayout,
        QFormLayout,
        QGroupBox,
        QLabel,
        QDoubleSpinBox,
        QPushButton,
        QComboBox,
        QMessageBox,
        QFileDialog,
        QMenu,
        QDialogButtonBox,
        QWidget,
    )
    from matplotlib.figure import Figure
    try:
        from .mpl_compat import FigureCanvas
    except Exception:  # pragma: no cover
        from mpl_compat import FigureCanvas  # type: ignore
    from matplotlib.ticker import MaxNLocator, ScalarFormatter

try:
    from .kriging_reml import _HAS_SCIPY as _HAS_REML
    from .reml_bridge import fit_ok_reml_interface
except Exception:
    try:
        from kriging_reml import _HAS_SCIPY as _HAS_REML
        from reml_bridge import fit_ok_reml_interface
    except Exception:
        fit_ok_reml_interface = None
        _HAS_REML = False

EXP_COLOR = "#2f0dee"
TH_COLOR = "#000000"


@dataclass
class SemivariogramInputs:
    """Container for the current dataset used by the Framework SDI popup."""
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    variable_name: str = ""


class FrameworkSDIDialog(QDialog):
    """Popup dialog used to compute SDI from the current Framework dataset."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        plugin: Optional[Any] = None,
        framework_ctrl: Optional[Any] = None,
    ) -> None:
        super().__init__(parent)
        self.plugin = plugin
        self.framework_ctrl = framework_ctrl or getattr(plugin, "framework_ctrl", None)
        self.setWindowTitle("Framework SDI / Semivariogram")
        self.resize(1080, 690)

        self._inputs: Optional[SemivariogramInputs] = None
        self._experimental = None
        self._result: Optional[Dict[str, Any]] = None
        self._cutoff: Optional[float] = None
        self._lag_width: Optional[float] = None
        self._init_params = None
        self._fit_method = "MoM"
        self._auto_method = "MoM"
        self._reml_meta: Dict[str, Any] = {}
        self._updating = False

        self._build_ui()
        self._load_current_context()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        top_layout = QHBoxLayout()
        left_col = QVBoxLayout()
        right_col = QVBoxLayout()

        grp_dataset = QGroupBox("Dataset")
        form_dataset = QFormLayout(grp_dataset)
        self.lbl_variable = QLabel("—")
        self.lbl_samples = QLabel("—")
        self.lbl_fit_method = QLabel("—")
        self.lbl_maxdist = QLabel("—")
        self.lbl_used_model = QLabel("—")
        form_dataset.addRow("Variable", self.lbl_variable)
        form_dataset.addRow("Valid samples", self.lbl_samples)
        form_dataset.addRow("Fit method", self.lbl_fit_method)
        form_dataset.addRow("Model used", self.lbl_used_model)
        form_dataset.addRow("Max pair distance", self.lbl_maxdist)
        left_col.addWidget(grp_dataset)

        grp_settings = QGroupBox("Semivariogram settings")
        form = QFormLayout(grp_settings)

        self.cmb_model = QComboBox()
        self.cmb_model.addItems(["Automatic", "Spherical", "Exponential", "Gaussian"])
        self.btn_model_validation = None
        model_row = QWidget()
        model_layout = QHBoxLayout(model_row)
        model_layout.setContentsMargins(0, 0, 0, 0)
        model_layout.addWidget(self.cmb_model)

        self.spin_nugget = self._make_double_spin(0.0, 1e12, 6)
        self.spin_psill = self._make_double_spin(0.0, 1e12, 6)
        self.spin_range = self._make_double_spin(0.0, 1e12, 6)
        self.spin_lag_width = self._make_double_spin(1e-12, 1e12, 12)
        self.spin_max_distance = self._make_double_spin(1e-12, 1e12, 6)
        self.lbl_lag_count = QLabel("—")

        form.addRow("Model", model_row)
        form.addRow("Nugget (Co)", self.spin_nugget)
        form.addRow("Partial sill (C1)", self.spin_psill)
        form.addRow("Range (a)", self.spin_range)
        form.addRow("Lag(h) width", self.spin_lag_width)
        form.addRow("Max distance", self.spin_max_distance)
        form.addRow("Lags", self.lbl_lag_count)
        left_col.addWidget(grp_settings)

        grp_actions = QGroupBox("Actions")
        action_layout = QVBoxLayout(grp_actions)
        self.btn_autofill = QPushButton("Autofill from geostatistics")
        self.btn_recompute = QPushButton("Recompute semivariogram")
        self.btn_apply_sdi = QPushButton("Apply SDI to Framework overview")
        action_layout.addWidget(self.btn_autofill)
        action_layout.addWidget(self.btn_recompute)
        action_layout.addWidget(self.btn_apply_sdi)
        left_col.addWidget(grp_actions)

        grp_result = QGroupBox("Result")
        form_result = QFormLayout(grp_result)
        self.lbl_sdi = QLabel("—")
        self.lbl_sdi_class = QLabel("—")
        self.lbl_sill_total = QLabel("—")
        form_result.addRow("SDI (%)", self.lbl_sdi)
        form_result.addRow("SDI class", self.lbl_sdi_class)
        form_result.addRow("Sill (Co + C1)", self.lbl_sill_total)
        left_col.addWidget(grp_result)
        left_col.addStretch(1)

        self.fig = Figure(constrained_layout=True)
        self.canvas = FigureCanvas(self.fig)
        right_col.addWidget(self.canvas, 1)
        self._install_canvas_menu()

        top_layout.addLayout(left_col, 0)
        top_layout.addLayout(right_col, 1)
        root.addLayout(top_layout, 1)

        self.button_box = QDialogButtonBox(enum_value(QDialogButtonBox, "StandardButton", "Close"))
        root.addWidget(self.button_box)

        self.btn_autofill.clicked.connect(self._autofill_from_plugin)
        self.btn_recompute.clicked.connect(self._reset_to_automatic_fit)
        self.btn_apply_sdi.clicked.connect(self._apply_to_framework)
        self.button_box.rejected.connect(self.reject)

        self.cmb_model.currentIndexChanged.connect(self._on_model_changed)
        for w in (self.spin_nugget, self.spin_psill, self.spin_range):
            w.valueChanged.connect(self._on_manual_params_changed)
        self.spin_lag_width.valueChanged.connect(self._on_structure_control_changed)
        self.spin_max_distance.valueChanged.connect(self._on_structure_control_changed)

    def _install_canvas_menu(self) -> None:
        try:
            self.canvas.setContextMenuPolicy(enum_value(Qt, "ContextMenuPolicy", "CustomContextMenu"))
            self.canvas.customContextMenuRequested.connect(self._show_canvas_context_menu)
        except Exception:  # nosec B110
            pass

    def _show_canvas_context_menu(self, pos) -> None:
        menu = QMenu(self)
        act_view = menu.addAction("View larger view")
        act_copy = menu.addAction("Copy graph")
        act_save = menu.addAction("Save graph")
        chosen = qt_exec(menu, self.canvas.mapToGlobal(pos))
        if chosen == act_copy:
            self._copy_figure_to_clipboard()
        elif chosen == act_save:
            suggested = os.path.join(tempfile.gettempdir(), "framework_sdi_semivariogram.png")
            path, _ = QFileDialog.getSaveFileName(self, "Save graph", suggested, "PNG Images (*.png)")
            if path:
                save_figure(self.fig, path, dpi=300, bbox_inches="tight")
        elif chosen == act_view:
            self._show_larger_graph()

    def _copy_figure_to_clipboard(self) -> None:
        """Copy the semivariogram figure to the system clipboard as a PNG image."""
        try:
            import io
            from qgis.PyQt.QtGui import QPixmap
            from qgis.PyQt.QtWidgets import QApplication
            buf = io.BytesIO()
            save_figure(self.fig, buf, format="png", dpi=300, bbox_inches="tight")
            pixmap = QPixmap()
            pixmap.loadFromData(buf.getvalue(), "PNG")
            QApplication.clipboard().setPixmap(pixmap)
        except Exception as exc:
            QMessageBox.warning(self, "Copy graph", f"Could not copy graph:\n{exc}")

    def _show_larger_graph(self) -> None:
        from .larger_view import show_larger_view
        return show_larger_view(self.fig,self,'Semivariogram Larger view')

    # ------------------------------------------------------------------
    # Context loading
    # ------------------------------------------------------------------
    def _load_current_context(self) -> None:
        data = None
        read_error = None
        try:
            data = self._read_framework_state_dataset()
            if data is None:
                data = self._read_plugin_dataset()
            if data is None:
                data = self._read_framework_collected_dataset()
        except Exception as exc:
            read_error = exc

        if data is None:
            if read_error is not None:
                QMessageBox.warning(self, "Framework SDI", f"Failed to read current data\n{read_error}")
                return
            QMessageBox.warning(
                self,
                "Framework SDI",
                "No valid point dataset is currently available.\nLoad the data first in the Data tab and then reopen this window."
            )
            return

        self._inputs = data
        self.lbl_variable.setText(data.variable_name or "—")
        self.lbl_samples.setText(str(len(data.z)))

        max_dist = float(np.nanmax(self._pairwise_distances(data.x, data.y))) if len(data.z) > 1 else 0.0
        self.lbl_maxdist.setText(self._fmt(max_dist))

        self._seed_defaults()
        self._recompute_plot()

    def _framework_controller(self):
        return getattr(self, "framework_ctrl", None) or (
            getattr(self.plugin, "framework_ctrl", None) if self.plugin is not None else None
        )

    def _read_framework_state_dataset(self) -> Optional[SemivariogramInputs]:
        """Read the data arrays already loaded in the Framework tab."""
        framework_ctrl = self._framework_controller()
        state = getattr(framework_ctrl, "state", None) if framework_ctrl is not None else None
        if state is None:
            return None
        d = getattr(state, "__dict__", {})
        try:
            x = np.asarray(d.get("x", []), dtype=float)
            y = np.asarray(d.get("y", []), dtype=float)
            z = np.asarray(d.get("z", []), dtype=float)
        except Exception:
            return None
        if x.size == 0 or y.size == 0 or z.size == 0:
            return None
        if x.size != y.size or x.size != z.size:
            return None
        try:
            mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
            x, y, z = x[mask], y[mask], z[mask]
        except Exception:
            return None
        if z.size < 5:
            return None
        return SemivariogramInputs(
            x=x,
            y=y,
            z=z,
            variable_name=str(getattr(state, "variable_name", "") or d.get("variable_name", "")),
        )

    def _read_framework_collected_dataset(self) -> Optional[SemivariogramInputs]:
        """Ask the Framework controller to collect current Data tab values."""
        framework_ctrl = self._framework_controller()
        collector = getattr(framework_ctrl, "_collect_current_plugin_data", None)
        if not callable(collector):
            return None
        data = collector()
        if not data:
            return None
        try:
            if hasattr(framework_ctrl, "load_from_data_tab"):
                framework_ctrl.load_from_data_tab(data)
        except Exception:  # nosec B110
            pass
        try:
            x = np.asarray(data.get("x", []), dtype=float)
            y = np.asarray(data.get("y", []), dtype=float)
            z = np.asarray(data.get("z", []), dtype=float)
        except Exception:
            return None
        if x.size != y.size or x.size != z.size:
            return None
        try:
            mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
            x, y, z = x[mask], y[mask], z[mask]
        except Exception:
            return None
        if z.size < 5:
            return None
        return SemivariogramInputs(
            x=x,
            y=y,
            z=z,
            variable_name=str(data.get("variable_name", "")),
        )

    def _read_plugin_dataset(self) -> Optional[SemivariogramInputs]:
        if self.plugin is None or not hasattr(self.plugin, "dlg"):
            return None

        dlg = self.plugin.dlg
        points_widget = getattr(dlg, "Points", None) or getattr(dlg, "cmbPointsLayer", None)
        variable_widget = getattr(dlg, "Points_2", None) or getattr(dlg, "cmbVariable", None)

        layer_name = points_widget.currentText().strip() if points_widget is not None else ""
        variable_name = variable_widget.currentText().strip() if variable_widget is not None else ""
        if not layer_name or not variable_name:
            return None

        try:
            from qgis.core import QgsProject
        except Exception:
            return None

        layers = QgsProject.instance().mapLayersByName(layer_name)
        if not layers:
            return None
        layer = layers[0]

        xs, ys, zs = [], [], []
        for feat in layer.getFeatures():
            geom = feat.geometry()
            if geom is None or geom.isEmpty():
                continue
            try:
                pt = geom.asPoint()
            except Exception:  # nosec B112
                continue
            try:
                val = float(feat[variable_name])
            except Exception:
                val = np.nan
            if np.isfinite(val):
                xs.append(float(pt.x()))
                ys.append(float(pt.y()))
                zs.append(val)

        if len(zs) < 5:
            return None

        return SemivariogramInputs(
            x=np.asarray(xs, dtype=float),
            y=np.asarray(ys, dtype=float),
            z=np.asarray(zs, dtype=float),
            variable_name=variable_name,
        )

    # ------------------------------------------------------------------
    # Controls and behavior
    # ------------------------------------------------------------------
    def _load_persisted_framework_params(self) -> Optional[Dict[str, Any]]:
        """Read the last semivariogram configuration stored in Framework state."""
        framework_ctrl = self._framework_controller()
        if framework_ctrl is None:
            return None
        state = getattr(framework_ctrl, "state", None)
        if state is None:
            return None

        data = {
            "model": state.__dict__.get("variogram_model"),
            "nugget": state.__dict__.get("nugget"),
            "psill": state.__dict__.get("psill"),
            "range": state.__dict__.get("range"),
            "lag_count": state.__dict__.get("lag_count"),
            "max_distance": state.__dict__.get("max_distance"),
            "fit_method": state.__dict__.get("fit_method"),
        }
        if all(v in (None, "") for v in data.values()):
            return None
        return data

    def _seed_defaults(self) -> None:
        if self._inputs is None:
            return

        x, y, z = self._inputs.x, self._inputs.y, self._inputs.z
        all_d = self._pairwise_distances(x, y)
        d_max = float(np.nanmax(all_d)) if all_d.size else 1.0
        nn_min = float(self._nearest_neighbor_dist(x, y))

        cutoff = 0.5 * d_max
        lagw = self._safe_lag_width(x, y, cutoff, nn_min)
        seeded_model = "Automatic"
        seeded_nugget = None
        seeded_psill = None
        seeded_range = None
        persisted = self._load_persisted_framework_params()
        if persisted is not None:
            try:
                if persisted.get("model"):
                    seeded_model = str(persisted["model"]).capitalize()
                if persisted.get("nugget") not in (None, ""):
                    seeded_nugget = float(persisted["nugget"])
                if persisted.get("psill") not in (None, ""):
                    seeded_psill = float(persisted["psill"])
                if persisted.get("range") not in (None, ""):
                    seeded_range = float(persisted["range"])
                if persisted.get("max_distance") not in (None, ""):
                    cutoff = float(persisted["max_distance"])
                if persisted.get("fit_method") not in (None, ""):
                    self._fit_method = str(persisted["fit_method"])
            except Exception:  # nosec B110
                pass
        else:
            ok_ctrl = getattr(self.plugin, "ok_ctrl", None) if self.plugin is not None else None
            if ok_ctrl is not None:
                try:
                    if getattr(ok_ctrl, "_cutoff", None) is not None:
                        cutoff = float(ok_ctrl._cutoff)
                    if getattr(ok_ctrl, "_lag_width", None) is not None:
                        lagw = float(ok_ctrl._lag_width)
                    seeded_model = getattr(ok_ctrl, "_get_selected_model", lambda: "spherical")().capitalize()
                    nugget, psill, rng = ok_ctrl._read_params_from_ui()
                    seeded_nugget = float(nugget)
                    seeded_psill = float(psill)
                    seeded_range = float(rng)
                    self._fit_method = str(getattr(ok_ctrl, "_ok_fit_method", "MoM"))
                except Exception:  # nosec B110
                    pass
        lagw = self._safe_lag_width(x, y, cutoff, lagw)

        if seeded_nugget is None or seeded_psill is None or seeded_range is None:
            exp_lags, exp_gamma = self._bin_variogram(x, y, z, cutoff, lagw)
            if exp_lags.size > 0:
                exp_lags = np.insert(exp_lags, 0, 0.0)
                exp_gamma = np.insert(exp_gamma, 0, 0.0)
                seeded_nugget, seeded_psill, seeded_range = self._guess_initial_params(
                    exp_lags[1:], exp_gamma[1:], cutoff, model=self._normalize_model_token(seeded_model)
                )
            else:
                seeded_nugget = 0.0
                seeded_psill = float(np.var(z, ddof=1) if z.size > 1 else 1.0)
                seeded_range = max(cutoff * 0.5, 1.0)

        self._updating = True
        try:
            self.cmb_model.setCurrentText(seeded_model if self.cmb_model.findText(seeded_model) >= 0 else "Automatic")
            self.spin_nugget.setValue(max(0.0, float(seeded_nugget)))
            self.spin_psill.setValue(max(0.0, float(seeded_psill)))
            self.spin_range.setValue(max(1e-12, float(seeded_range)))
            self.spin_max_distance.setValue(max(1e-12, float(cutoff)))
            self.spin_lag_width.setValue(max(1e-12, float(lagw)))
        finally:
            self._updating = False

    def _autofill_from_plugin(self) -> None:
        """Copy the active geostatistics variogram settings into this dialog."""
        if self._inputs is None:
            return

        ok_ctrl = self._active_ok_controller()
        if ok_ctrl is None:
            QMessageBox.warning(
                self,
                "Framework SDI",
                "No active geostatistics controller is available. Open the Geostatistics tab once and try again.",
            )
            return

        try:
            if self.plugin is not None and hasattr(self.plugin, "_update_ok_context"):
                self.plugin._update_ok_context()
                ok_ctrl = self._active_ok_controller() or ok_ctrl
        except Exception:  # nosec B110
            pass

        model = self._model_text_from_token(getattr(ok_ctrl, "_get_selected_model", lambda: "spherical")())
        try:
            nugget, psill, rng = ok_ctrl._read_params_from_ui()
        except Exception:
            nugget, psill, rng = self._read_params_from_controls()

        cutoff = getattr(ok_ctrl, "_cutoff", None)
        lagw = getattr(ok_ctrl, "_lag_width", None)
        if cutoff is None:
            cutoff = self.spin_max_distance.value()
        if lagw is None:
            lagw = self.spin_lag_width.value()
        lagw = self._safe_lag_width(self._inputs.x, self._inputs.y, cutoff, lagw)

        fit_method = str(getattr(ok_ctrl, "_ok_fit_method", getattr(ok_ctrl, "strategy_name", "MoM")) or "MoM")
        exp_lags = getattr(ok_ctrl, "_exp_lags", None)
        exp_gamma = getattr(ok_ctrl, "_exp_gamma", None)

        self._updating = True
        try:
            self.cmb_model.setCurrentText(model if self.cmb_model.findText(model) >= 0 else "Spherical")
            self.spin_nugget.setValue(max(0.0, float(nugget)))
            self.spin_psill.setValue(max(0.0, float(psill)))
            self.spin_range.setValue(max(1e-12, float(rng)))
            self.spin_max_distance.setValue(max(1e-12, float(cutoff)))
            self.spin_lag_width.setValue(max(1e-12, float(lagw)))
        finally:
            self._updating = False

        self._cutoff = float(self.spin_max_distance.value())
        self._lag_width = self._safe_lag_width(self._inputs.x, self._inputs.y, self._cutoff, self.spin_lag_width.value())
        self._fit_method = "REML" if fit_method.upper() == "REML" else "MoM"
        self._reml_meta = {}

        if exp_lags is not None and exp_gamma is not None:
            lags = np.asarray(exp_lags, dtype=float)
            gamma = np.asarray(exp_gamma, dtype=float)
            mode = "reml" if self._fit_method == "REML" else "mom"
            self._experimental = {"lags": lags, "gamma": gamma, "mode": mode}
        else:
            self._set_experimental_from_current_structure(mode="reml" if self._fit_method == "REML" else "mom")

        self._refresh_structure_labels()
        self._update_result_labels()
        self._draw_variogram()

    def _active_ok_controller(self):
        ok_ctrl = getattr(self.plugin, "ok_ctrl", None) if self.plugin is not None else None
        if ok_ctrl is None:
            return None
        return getattr(ok_ctrl, "_active", None) or ok_ctrl

    @staticmethod
    def _model_text_from_token(token: str) -> str:
        token = (token or "").strip().lower()
        if token.startswith("gau"):
            return "Gaussian"
        if token.startswith("exp"):
            return "Exponential"
        return "Spherical"

    def _read_params_from_controls(self):
        return (
            float(self.spin_nugget.value()),
            float(self.spin_psill.value()),
            float(self.spin_range.value()),
        )

    def _refresh_structure_labels(self) -> None:
        if self._lag_width is None or self._cutoff is None:
            self.lbl_lag_count.setText("0")
            return
        try:
            n_lags = max(1, int(math.floor(float(self._cutoff) / float(self._lag_width))))
            self.lbl_lag_count.setText(str(n_lags))
        except Exception:
            self.lbl_lag_count.setText("0")

    def _on_model_changed(self, *args) -> None:
        if self._updating:
            return
        self._update_method_labels()
        self._update_result_labels()
        self._draw_variogram()
        self._sync_framework_preview()

    def _on_model_validation_clicked(self) -> None:
        framework_ctrl = self._framework_controller()
        if framework_ctrl is not None and hasattr(framework_ctrl, "_show_ok_model_validation_dialog"):
            framework_ctrl._show_ok_model_validation_dialog()
            return
        QMessageBox.information(
            self,
            "Framework kriging model validation",
            "Run Framework diagnostics or validation first.",
        )

    def _on_manual_params_changed(self, *args) -> None:
        if self._updating:
            return
        self._update_result_labels()
        self._draw_variogram()
        self._sync_framework_preview()

    def _on_structure_control_changed(self, *args) -> None:
        if self._updating:
            return
        self._recompute_plot()

    def _reset_to_automatic_fit(self) -> None:
        """Reset cutoff, lag width, and model parameters from the current dataset."""
        if self._inputs is None:
            return

        x, y, z = self._inputs.x, self._inputs.y, self._inputs.z
        all_d = self._pairwise_distances(x, y)
        cutoff = 0.5 * float(np.nanmax(all_d)) if all_d.size else 1.0
        lagw = self._safe_lag_width(x, y, cutoff, self._nearest_neighbor_dist(x, y))

        self._cutoff = cutoff
        self._lag_width = lagw
        self._updating = True
        try:
            self.spin_max_distance.setValue(max(1e-12, float(cutoff)))
            self.spin_lag_width.setValue(max(1e-12, float(lagw)))
        finally:
            self._updating = False
        self._refresh_structure_labels()

        if self._should_use_reml():
            self._run_reml_mode(x, y, z)
        else:
            lags, gamma = self._bin_variogram(x, y, z, self._cutoff, self._lag_width)
            if lags.size == 0:
                lags = np.array([0.0])
                gamma = np.array([0.0])
                nugget, psill, rng = 0.0, float(np.var(z, ddof=1) if z.size > 1 else 1.0), max(self._cutoff * 0.5, 1.0)
            else:
                nugget, psill, rng = self._guess_initial_params(
                    lags,
                    gamma,
                    self._cutoff,
                    model=self._normalize_model_token(self.cmb_model.currentText()),
                )
                lags = np.insert(lags, 0, 0.0)
                gamma = np.insert(gamma, 0, 0.0)
            self._experimental = {"lags": lags, "gamma": gamma, "mode": "mom"}
            self._fit_method = "MoM"
            self._reml_meta = {}
            self._set_param_values(nugget, psill, rng)
            self._update_method_labels()

        self._update_result_labels()
        self._draw_variogram()
        self._sync_framework_preview()

    def _should_use_reml(self) -> bool:
        n = len(self._inputs.z) if self._inputs is not None else 0
        has_reml = bool(_HAS_REML and fit_ok_reml_interface is not None)
        return bool(has_reml and n < 100)

    def _recompute_plot(self) -> None:
        if self._inputs is None:
            return

        cutoff = float(self.spin_max_distance.value())
        lagw = float(self.spin_lag_width.value())
        if cutoff <= 0:
            QMessageBox.warning(self, "Framework SDI", "Max distance must be greater than zero.")
            return
        if lagw <= 0:
            lagw = self._safe_lag_width(self._inputs.x, self._inputs.y, cutoff, lagw)
            self._updating = True
            try:
                self.spin_lag_width.setValue(max(1e-12, float(lagw)))
            finally:
                self._updating = False
        if lagw >= cutoff:
            QMessageBox.warning(self, "Framework SDI", "Lag(h) width must be smaller than max distance.")
            return
        lagw = self._safe_lag_width(self._inputs.x, self._inputs.y, cutoff, lagw)

        x, y, z = self._inputs.x, self._inputs.y, self._inputs.z
        self._cutoff = cutoff
        self._lag_width = lagw
        self._refresh_structure_labels()

        if self._should_use_reml():
            self._run_reml_mode(x, y, z)
        else:
            self._run_mom_mode(x, y, z)

        self._update_result_labels()
        self._draw_variogram()
        self._sync_framework_preview()
        try:
            QCoreApplication.processEvents()
        except Exception:  # nosec B110
            pass

    def _sync_framework_preview(self) -> None:
        """Push current SDI values to the Framework preview without closing the dialog."""
        if self._result is None:
            return
        framework_ctrl = self._framework_controller()
        if framework_ctrl is None:
            return
        try:
            framework_ctrl.load_sdi_result(self._result)
            if hasattr(framework_ctrl, "refresh_variogram_preview_from_state"):
                framework_ctrl.refresh_variogram_preview_from_state()
        except Exception:  # nosec B110
            pass

    def _run_mom_mode(self, x: np.ndarray, y: np.ndarray, z: np.ndarray) -> None:
        lags, gamma = self._bin_variogram(x, y, z, self._cutoff, self._lag_width)
        if lags.size == 0:
            lags = np.array([0.0])
            gamma = np.array([0.0])
            nugget, psill, rng = 0.0, float(np.var(z, ddof=1) if z.size > 1 else 1.0), max((self._cutoff or 1.0) * 0.5, 1.0)
        else:
            nugget, psill, rng = self._guess_initial_params(
                lags,
                gamma,
                self._cutoff,
                model=self._normalize_model_token(self.cmb_model.currentText()),
            )
            lags = np.insert(lags, 0, 0.0)
            gamma = np.insert(gamma, 0, 0.0)

        self._experimental = {"lags": lags, "gamma": gamma, "mode": "mom"}
        self._fit_method = "MoM"
        self._reml_meta = {}
        self._set_param_values(nugget, psill, rng)
        self._update_method_labels()

    def _set_experimental_from_current_structure(self, mode: str = "mom") -> None:
        if self._inputs is None:
            return
        lags, gamma = self._bin_variogram(
            self._inputs.x,
            self._inputs.y,
            self._inputs.z,
            self._cutoff,
            self._lag_width,
        )
        if mode != "reml":
            if lags.size == 0:
                lags = np.array([0.0])
                gamma = np.array([0.0])
            else:
                lags = np.insert(lags, 0, 0.0)
                gamma = np.insert(gamma, 0, 0.0)
        self._experimental = {"lags": np.asarray(lags, dtype=float), "gamma": np.asarray(gamma, dtype=float), "mode": mode}

    def _run_reml_mode(self, x: np.ndarray, y: np.ndarray, z: np.ndarray) -> None:
        lags_tmp, gamma_tmp = self._bin_variogram(x, y, z, self._cutoff, self._lag_width)
        if lags_tmp.size > 0:
            lags_tmp0 = np.insert(lags_tmp, 0, 0.0)
            gamma_tmp0 = np.insert(gamma_tmp, 0, 0.0)
            nugget0, psill0, rng0 = self._guess_initial_params(
                lags_tmp0[1:], gamma_tmp0[1:], self._cutoff, model=self._normalize_model_token(self.cmb_model.currentText())
            )
        else:
            nugget0, psill0, rng0 = 0.0, float(np.var(z, ddof=1) if z.size > 1 else 1.0), max(self._cutoff * 0.5, 1.0)

        model_txt = self._model_text_from_token(self._normalize_model_token(self.cmb_model.currentText()))
        try:
            reml_res = fit_ok_reml_interface(
                sample_xyz=np.column_stack([x, y, z]),
                model=model_txt,
                init_from_mom={"nugget": nugget0, "psill": psill0, "range": rng0},
                random_state=123,
            )
            nugget = float(reml_res.get("nugget", nugget0))
            psill = float(reml_res.get("psill", psill0))
            rng = float(reml_res.get("range", rng0))
            self._reml_meta = {
                "converged": bool(reml_res.get("converged", False)),
                "niter": int(reml_res.get("niter", 0) or 0),
                "reml_value": reml_res.get("reml_value"),
            }
            self._fit_method = "REML"
        except Exception:
            nugget, psill, rng = nugget0, psill0, rng0
            self._reml_meta = {}
            self._fit_method = "MoM"

        self._experimental = {"lags": np.asarray(lags_tmp, dtype=float), "gamma": np.asarray(gamma_tmp, dtype=float), "mode": "reml"}
        self._set_param_values(nugget, psill, rng)
        self._update_method_labels()

    def _set_param_values(self, nugget: float, psill: float, rng: float) -> None:
        blockers = []
        for w in (self.spin_nugget, self.spin_psill, self.spin_range):
            try:
                blockers.append(w.blockSignals(True))
            except Exception:
                blockers.append(None)
        self.spin_nugget.setValue(max(0.0, float(nugget)))
        self.spin_psill.setValue(max(0.0, float(psill)))
        self.spin_range.setValue(max(1e-12, float(rng)))
        for w, old in zip((self.spin_nugget, self.spin_psill, self.spin_range), blockers):
            try:
                w.blockSignals(old if old is not None else False)
            except Exception:  # nosec B110
                pass

    def _update_method_labels(self) -> None:
        self.lbl_fit_method.setText(self._fit_method)
        self.lbl_used_model.setText(self.cmb_model.currentText())

    def _apply_to_framework(self) -> None:
        self._update_result_labels()
        if self._result is None:
            QMessageBox.warning(self, "Framework SDI", "No valid SDI result is available.")
            return

        framework_ctrl = self._framework_controller()
        if framework_ctrl is not None:
            try:
                framework_ctrl.load_sdi_result(self._result)
                QMessageBox.information(self, "Framework SDI", "SDI values were sent to the Framework overview.")
            except Exception as exc:
                QMessageBox.warning(self, "Framework SDI", f"Failed to update Framework overview\n{exc}")
                return
        self.accept()

    def _draw_variogram(self) -> None:
        self.fig.clear()
        ax = self.fig.add_subplot(111)

        mode = self._experimental.get("mode", "mom") if self._experimental else "mom"
        lags = self._experimental.get("lags", np.array([])) if self._experimental else np.array([])
        gamma = self._experimental.get("gamma", np.array([])) if self._experimental else np.array([])

        ax.clear()
        if mode != "reml":
            lags_plot = lags[1:] if lags.size > 1 else lags
            gamma_plot = gamma[1:] if gamma.size > 1 else gamma
            if lags_plot.size > 0:
                ax.plot(lags_plot, gamma_plot, 'o', label="Experimental", color=EXP_COLOR)
        else:
            lags_plot = np.asarray([], dtype=float)
            gamma_plot = np.asarray([], dtype=float)

        nugget = float(self.spin_nugget.value())
        psill = float(self.spin_psill.value())
        rng = float(self.spin_range.value())
        model = self._normalize_model_token(self.cmb_model.currentText())
        xmax = max(float(self.spin_max_distance.value()), float(lags_plot.max()) if lags_plot.size else 1.0)
        h_line = np.linspace(0.0, xmax, 200)
        th = self._model_func(h_line, model, nugget, psill, rng)
        label = f"Theoretical ({self.cmb_model.currentText()} {self._fit_method})"
        ax.plot(h_line, th, '-', label=label, color=TH_COLOR, linewidth=2)

        title = "Semivariogram (REML model)" if mode == "reml" else "Semivariogram"
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("Lag distance (h)", fontsize=9)
        ax.set_ylabel("Semivariance γ(h)", fontsize=9)
        ax.set_xlim(left=0.0, right=xmax)
        ax.set_ylim(bottom=0.0)
        ax.xaxis.set_major_locator(MaxNLocator(nbins=8))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=6))
        xf = ScalarFormatter(useOffset=False, useMathText=False); xf.set_scientific(False)
        yf = ScalarFormatter(useOffset=False, useMathText=False); yf.set_scientific(False)
        ax.xaxis.set_major_formatter(xf)
        ax.yaxis.set_major_formatter(yf)
        ax.tick_params(axis='x', rotation=0)
        ax.tick_params(axis='both', labelsize=8)
        ax.grid(True, linestyle='--', linewidth=0.5, alpha=0.6)
        ax.legend(fontsize=9, frameon=False)
        self.canvas.draw_idle()

    def _update_result_labels(self) -> None:
        nugget = max(0.0, float(self.spin_nugget.value()))
        psill = max(0.0, float(self.spin_psill.value()))
        sill_total = nugget + psill
        sdi = (psill / sill_total * 100.0) if sill_total > 0 else 0.0
        sdi_class = self._classify_sdi(sdi)

        self.lbl_sdi.setText(self._fmt(sdi))
        self.lbl_sdi_class.setText(sdi_class)
        self.lbl_sill_total.setText(self._fmt(sill_total))
        self._update_method_labels()

        lags = self._experimental.get('lags', np.array([])) if self._experimental else np.array([])
        gamma = self._experimental.get('gamma', np.array([])) if self._experimental else np.array([])
        mode = self._experimental.get('mode', 'mom') if self._experimental else 'mom'
        if mode == 'reml':
            lags_out = []
            gamma_out = []
        else:
            lags_out = (lags[1:] if lags.size > 1 else lags).tolist() if hasattr(lags, 'tolist') else []
            gamma_out = (gamma[1:] if gamma.size > 1 else gamma).tolist() if hasattr(gamma, 'tolist') else []

        self._result = {
            "sdi_value": sdi,
            "sdi_status": sdi_class,
            "sdi_class": sdi_class,
            "variogram_model": self.cmb_model.currentText(),
            "fit_method": self._fit_method,
            "nugget": nugget,
            "psill": psill,
            "range": float(self.spin_range.value()),
            "lag_width": float(self._lag_width) if self._lag_width is not None else None,
            "lag_count": int(self.lbl_lag_count.text()) if self.lbl_lag_count.text().isdigit() else None,
            "max_distance": float(self.spin_max_distance.value()),
            "experimental_distances": lags_out,
            "experimental_semivariances": gamma_out,
            "reml_meta": dict(self._reml_meta),
        }

    # ------------------------------------------------------------------
    # Logic replicated from ok_r_integration.py
    # ------------------------------------------------------------------
    @staticmethod
    def _pairwise_distances(x, y):
        return np.asarray([max_pairwise_distance(x, y)], dtype=float)

    @staticmethod
    def _nearest_neighbor_dist(x, y):
        return nearest_neighbor_distance(x, y)

    def _safe_lag_width(self, x, y, cutoff, lag_width, max_bins=10000):
        return safe_lag_width(x, y, cutoff, lag_width, max_bins=max_bins)

    @staticmethod
    def _semivariances(z):
        def gamma(i_val, j_vals):
            diff = i_val - j_vals
            return 0.5 * (diff * diff)
        return gamma

    def _bin_variogram(self, x, y, z, cutoff, lag_width):
        lags, gamma, info = bin_experimental_variogram(
            x, y, z, cutoff, lag_width, return_info=True
        )
        self._variogram_pair_info = info
        return lags, gamma

    def _guess_initial_params(self, lags, gamma, cutoff, model="exponential"):
        """Use the shared numerical engine without changing the established policy."""
        return SemivariogramEngine("framework_sdi")._guess_initial_params(lags,gamma,cutoff,model)

    @staticmethod
    def _normalize_model_token(model_text: str) -> str:
        m = str(model_text).strip().lower()
        if m.startswith('sph') or m.startswith('spher'):
            return 'spherical'
        if m.startswith('exp'):
            return 'exponential'
        if m.startswith('gau'):
            return 'gaussian'
        return 'exponential'

    def _model_func(self, h, model, nugget, psill, rng):
        """Use the shared numerical engine without changing the established policy."""
        return SemivariogramEngine("framework_sdi")._model_func(h,model,nugget,psill,rng)

    @staticmethod
    def _classify_sdi(sdi: float) -> str:
        if sdi < 20.0:
            return "Very Low"
        if sdi < 40.0:
            return "Low"
        if sdi < 60.0:
            return "Moderate"
        if sdi < 80.0:
            return "High"
        return "Very High"

    @staticmethod
    def _make_double_spin(minimum: float, maximum: float, decimals: int = 4) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setSingleStep(0.1)
        spin.setAlignment(enum_value(Qt, "AlignmentFlag", "AlignRight"))
        return spin

    @staticmethod
    def _fmt(value: Any) -> str:
        try:
            v = float(value)
            if not np.isfinite(v):
                return "—"
            return f"{v:.4f}"
        except Exception:
            return "—"
