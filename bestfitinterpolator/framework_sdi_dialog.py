# -*- coding: utf-8 -*-
"""
framework_sdi_dialog.py

Standalone SDI / semivariogram popup for the Framework tab.
This version keeps the Framework workflow isolated while mirroring the
semivariogram logic already used in the geostatistics path.

All code comments are in English.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import math
import os
import tempfile
import numpy as np

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
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    from matplotlib.ticker import MaxNLocator, ScalarFormatter
except Exception:  # pragma: no cover
    from PyQt5.QtCore import Qt, QCoreApplication
    from PyQt5.QtWidgets import (
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
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
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

    def __init__(self, parent: Optional[QWidget] = None, plugin: Optional[Any] = None) -> None:
        super().__init__(parent)
        self.plugin = plugin
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
        self.btn_model_validation = QPushButton("View validation")
        self.btn_model_validation.setToolTip(
            "View the Framework validation used to compare the Spherical, Exponential, and Gaussian kriging models."
        )
        model_row = QWidget()
        model_layout = QHBoxLayout(model_row)
        model_layout.setContentsMargins(0, 0, 0, 0)
        model_layout.addWidget(self.cmb_model)
        model_layout.addWidget(self.btn_model_validation)

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

        self.button_box = QDialogButtonBox(QDialogButtonBox.Close)
        root.addWidget(self.button_box)

        self.btn_autofill.clicked.connect(self._autofill_from_plugin)
        self.btn_recompute.clicked.connect(self._reset_to_automatic_fit)
        self.btn_apply_sdi.clicked.connect(self._apply_to_framework)
        self.button_box.rejected.connect(self.reject)

        self.cmb_model.currentIndexChanged.connect(self._on_model_changed)
        self.btn_model_validation.clicked.connect(self._on_model_validation_clicked)
        for w in (self.spin_nugget, self.spin_psill, self.spin_range):
            w.valueChanged.connect(self._on_manual_params_changed)
        self.spin_lag_width.valueChanged.connect(self._on_structure_control_changed)
        self.spin_max_distance.valueChanged.connect(self._on_structure_control_changed)

    def _install_canvas_menu(self) -> None:
        try:
            self.canvas.setContextMenuPolicy(Qt.CustomContextMenu)
            self.canvas.customContextMenuRequested.connect(self._show_canvas_context_menu)
        except Exception:
            pass

    def _show_canvas_context_menu(self, pos) -> None:
        menu = QMenu(self)
        act_view = menu.addAction("View larger view")
        act_copy = menu.addAction("Copy graph")
        act_save = menu.addAction("Save graph")
        chosen = menu.exec_(self.canvas.mapToGlobal(pos))
        if chosen == act_copy:
            self._copy_figure_to_clipboard()
        elif chosen == act_save:
            suggested = os.path.join(tempfile.gettempdir(), "framework_sdi_semivariogram.png")
            path, _ = QFileDialog.getSaveFileName(self, "Save graph", suggested, "PNG Images (*.png)")
            if path:
                self.fig.savefig(path, dpi=300, bbox_inches="tight")
        elif chosen == act_view:
            self._show_larger_graph()

    def _copy_figure_to_clipboard(self) -> None:
        """Copy the semivariogram figure to the system clipboard as a PNG image."""
        try:
            import io
            from qgis.PyQt.QtGui import QPixmap
            from qgis.PyQt.QtWidgets import QApplication
            buf = io.BytesIO()
            self.fig.savefig(buf, format="png", dpi=300, bbox_inches="tight")
            pixmap = QPixmap()
            pixmap.loadFromData(buf.getvalue(), "PNG")
            QApplication.clipboard().setPixmap(pixmap)
        except Exception as exc:
            QMessageBox.warning(self, "Copy graph", f"Could not copy graph:\n{exc}")

    def _show_larger_graph(self) -> None:
        try:
            import io
            import matplotlib.image as mpimg
            dlg = QDialog(self)
            dlg.setWindowTitle("Semivariogram - larger view")
            layout = QVBoxLayout(dlg)
            fig = Figure(figsize=(9, 6.5))
            canvas = FigureCanvas(fig)
            layout.addWidget(canvas)
            buf = io.BytesIO()
            self.fig.savefig(buf, format="png", dpi=180, bbox_inches="tight")
            buf.seek(0)
            arr = mpimg.imread(buf)
            ax = fig.add_subplot(111)
            ax.imshow(arr)
            ax.axis("off")
            canvas.draw()
            dlg.resize(980, 720)
            dlg.exec_()
        except Exception as exc:
            QMessageBox.warning(self, "View larger view", f"Could not open larger view:\n{exc}")

    # ------------------------------------------------------------------
    # Context loading
    # ------------------------------------------------------------------
    def _load_current_context(self) -> None:
        try:
            data = self._read_plugin_dataset()
        except Exception as exc:
            QMessageBox.warning(self, "Framework SDI", f"Failed to read current data\n{exc}")
            return

        if data is None:
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
            except Exception:
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
        framework_ctrl = getattr(self.plugin, "framework_ctrl", None) if self.plugin is not None else None
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
        seeded_lags = max(6, min(15, int(round(math.sqrt(len(z))))))

        persisted = None
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
                if persisted.get("lag_count") not in (None, ""):
                    seeded_lags = int(persisted["lag_count"])
                if persisted.get("max_distance") not in (None, ""):
                    cutoff = float(persisted["max_distance"])
                if persisted.get("fit_method") not in (None, ""):
                    self._fit_method = str(persisted["fit_method"])
            except Exception:
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
                except Exception:
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
        except Exception:
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
        framework_ctrl = getattr(self.plugin, "framework_ctrl", None)
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
        except Exception:
            pass

    def _sync_framework_preview(self) -> None:
        """Push current SDI values to the Framework preview without closing the dialog."""
        if self._result is None:
            return
        framework_ctrl = getattr(self.plugin, "framework_ctrl", None) if self.plugin is not None else None
        if framework_ctrl is None:
            return
        try:
            framework_ctrl.load_sdi_result(self._result)
            if hasattr(framework_ctrl, "refresh_variogram_preview_from_state"):
                framework_ctrl.refresh_variogram_preview_from_state()
        except Exception:
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
        coords = np.column_stack([x, y])
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
            except Exception:
                pass

    def _update_method_labels(self) -> None:
        self.lbl_fit_method.setText(self._fit_method)
        self.lbl_used_model.setText(self.cmb_model.currentText())

    def _apply_to_framework(self) -> None:
        self._update_result_labels()
        if self._result is None:
            QMessageBox.warning(self, "Framework SDI", "No valid SDI result is available.")
            return

        if self.plugin is not None and getattr(self.plugin, "framework_ctrl", None) is not None:
            try:
                self.plugin.framework_ctrl.load_sdi_result(self._result)
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
                h_start = float(lags_plot.min())
            else:
                h_start = 0.0
        else:
            lags_plot = np.asarray([], dtype=float)
            gamma_plot = np.asarray([], dtype=float)
            h_start = 0.0

        nugget = float(self.spin_nugget.value())
        psill = float(self.spin_psill.value())
        rng = float(self.spin_range.value())
        model = self._normalize_model_token(self.cmb_model.currentText())
        xmax = max(float(self.spin_max_distance.value()), float(lags_plot.max()) if lags_plot.size else 1.0)
        h_line = np.linspace(0.0, xmax, 200)
        th = self._model_func(h_line, model, nugget, psill, rng)
        label = f"Theoretical ({self.cmb_model.currentText()} — {self._fit_method})"
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
        def gamma(i_val, j_vals):
            diff = i_val - j_vals
            return 0.5 * (diff * diff)
        return gamma

    def _bin_variogram(self, x, y, z, cutoff, lag_width):
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
            xj = x[i + 1:]
            yj = y[i + 1:]
            zj = z[i + 1:]
            dd = np.hypot(xj - xi, yj - yi)
            mask = (dd > 0) & (dd <= cutoff)
            if not np.any(mask):
                continue
            dd = dd[mask]
            gj = gamma_of(zi, zj[mask])
            bin_idx = np.floor(dd / lag_width).astype(int)
            bin_idx[bin_idx == nbins] = nbins - 1
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

    def _guess_initial_params(self, lags, gamma, cutoff, model="exponential"):
        lags = np.asarray(lags, dtype=float)
        gamma = np.asarray(gamma, dtype=float)
        keep = np.isfinite(lags) & np.isfinite(gamma) & (lags > 0)
        lags = lags[keep]
        gamma = gamma[keep]

        if lags.size == 0:
            return 0.0, 1.0, max(1.0, cutoff * 0.4)

        order = np.argsort(lags)
        lags = lags[order]
        gamma = gamma[order]

        first_vals = gamma[:max(1, min(3, gamma.size))]
        tail_vals = gamma[-max(3, max(1, gamma.size // 3)):]

        first_bin = float(first_vals[0]) if first_vals.size else 0.0
        first_med = float(np.nanmedian(first_vals)) if first_vals.size else first_bin
        first_max = float(np.nanmax(first_vals)) if first_vals.size else first_bin

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

        target = 0.90 * sill_total_seed
        idx = np.where(gamma >= target)[0]
        if idx.size > 0:
            range_seed = float(lags[idx[0]])
        else:
            range_seed = float(0.60 * cutoff)
        range_seed = max(range_seed, float(np.nanmin(lags)), 1e-9)

        nugget_cap = max(0.0, min(first_max, 0.90 * sill_total_seed))
        nugget_seed = float(np.clip(nugget_seed, 0.0, nugget_cap)) if nugget_cap > 0 else 0.0
        nugget_candidates = np.array([nugget_seed], dtype=float)

        lag_min = max(float(np.nanmin(lags)), 1e-9)
        lag_max = max(float(np.nanmax(lags)), lag_min)
        low = max(lag_min, 0.20 * range_seed)
        high = max(low * 1.05, min(float(cutoff), max(lag_max * 1.15, range_seed * 1.8, low)))
        range_candidates = np.unique(np.concatenate([
            np.linspace(low, high, 28),
            np.array([range_seed, 0.5 * cutoff, 0.75 * cutoff, lag_max], dtype=float),
        ]))
        range_candidates = range_candidates[np.isfinite(range_candidates) & (range_candidates > 0)]

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
                sse += 1e-6 * (float(rng) / max(float(cutoff), 1e-9)) ** 2
                if (best is None) or (sse < best[0]):
                    best = (sse, float(nugget), float(psill), float(rng))

        if best is None:
            return nugget_seed, max(1e-9, sill_total_seed - nugget_seed), range_seed
        return best[1], best[2], best[3]

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
        """Use the same theoretical variogram equations as the geostatistics tab."""
        h = np.asarray(h, dtype=float)
        c0 = float(nugget)
        c = float(psill)
        a = max(float(rng), 1e-9)
        model = self._normalize_model_token(model)
        if model == 'spherical':
            hr = np.clip(h / a, 0.0, 1.0)
            sph = c * (1.5 * hr - 0.5 * (hr ** 3))
            return np.where(h <= a, c0 + sph, c0 + c)
        elif model == 'gaussian':
            return c0 + c * (1.0 - np.exp(-(h * h) / (a * a)))
        else:
            return c0 + c * (1.0 - np.exp(-h / a))

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
        spin.setAlignment(Qt.AlignRight)
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
