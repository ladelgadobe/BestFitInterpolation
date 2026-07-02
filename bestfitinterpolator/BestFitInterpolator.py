# -*- coding: utf-8 -*-
"""
BestFitInterpolator.py
Main plugin entry point and dialog orchestration.
All code comments are in English. User-facing messages are in English.
"""

import os
import uuid
import tempfile
import math
import numpy as np
import matplotlib.pyplot as plt
import random
import pandas as pd

from qgis.PyQt import uic
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, QVariant, Qt, QSize
from qgis.PyQt.QtGui import QIcon, QPixmap
from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QTabWidget,
    QPushButton, QWidget, QProgressDialog, QFileDialog, QMenu, QMessageBox,
    QSizePolicy, QGroupBox, QLabel
)
from matplotlib.ticker import FuncFormatter

from qgis.core import (
    QgsProject,
    QgsMapLayer,
    QgsWkbTypes,
    QgsRasterLayer,
    QgsSettings,
    QgsUnitTypes,
)

from matplotlib.path import Path
from matplotlib.patches import Polygon as MplPolygon
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from osgeo import gdal, osr

from .resources import *
from .IDW_optimized import idw_interpolation, optimize_idw
from .kriging_ordinary import ordinary_kriging_interpolation  # <-- used for OK CV and export
from .reml_bridge import fit_ok_reml_interface, predict_ok_reml_interface, cv_ok_reml_interface
from .array_shape_utils import (
    InterpolationShapeError,
    ensure_xy_components,
    ensure_xy_2d,
    ensure_values_1d,
    finite_training_arrays,
    format_shape_error,
)
from .ml_bootstrap import _add_deps_to_sys_path


class BestFitTemporaryRasterLayer(QgsRasterLayer):
    """Raster layer wrapper used so QGIS can identify plugin temp outputs."""
    def isTemporary(self):
        return True


_FRAMEWORK_IMPORT_ERROR = None
_OK_DISPATCHER_IMPORT_ERROR = None
_add_deps_to_sys_path()
from .machine_learning_tab import MachineLearningTabController
try:
    from .framework_tab import FrameworkTabController
except Exception as _framework_exc:
    FrameworkTabController = None
    _FRAMEWORK_IMPORT_ERROR = str(_framework_exc)
try:
    from .RF_RegressionKriging import RegressionKrigingRFController
except Exception:
    RegressionKrigingRFController = None


# Optional TPS
try:
    from .Thin_plate_spline import tps_interpolation
    _HAS_TPS = True
except Exception:
    _HAS_TPS = False

# Ordinary Kriging dispatcher (selects MoM or REML controller)
try:
    from .ok_dispatcher import OKDispatcherController
except Exception as _ok_dispatcher_exc:
    OKDispatcherController = None
    _OK_DISPATCHER_IMPORT_ERROR = str(_ok_dispatcher_exc)


# ------------------------------- Dialog wrapper -------------------------------

class BestFitInterpolatorDialog(QDialog):
    """Load the .ui dynamically to avoid compiling with pyuic5 on each environment."""
    def __init__(self, plugin_dir, parent=None):
        super().__init__(parent)
        ui_path = os.path.join(plugin_dir, "BestFitInterpolator_dialog_base.ui")
        uic.loadUi(ui_path, self)

        # --- ADD THIS BLOCK: show minimize / maximize / close buttons ---
        flags = self.windowFlags()
        # Make sure it behaves as a normal top-level window
        flags |= Qt.Window
        # Add minimize and maximize buttons
        flags |= Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint
        # Remove the "?" help button if it appears
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        # Apply the updated flags
        self.setWindowFlags(flags)
        # ---------------------------------------------------------------


    def closeEvent(self, event):
        """Ask for confirmation before closing the plugin dialog."""
        try:
            reply = QMessageBox.question(
                self,
                "Close Best Fit Interpolator",
                "Are you sure you want to close Best Fit Interpolator? Any unsaved progress in the plugin window will be lost.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                event.accept()
            else:
                event.ignore()
        except Exception:
            event.accept()


# -------------------------------- Main plugin ---------------------------------

class BestFitInterpolator:
    # Deterministic mode ids
    MODE_IDW_OPT = 0
    MODE_IDW_MAN = 1
    MODE_TPS     = 2

    # CV modes
    CV_AUTO   = 0
    CV_LOOCV  = 1
    CV_KFOLD  = 2

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)

        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(self.plugin_dir, 'i18n', f'BestFitInterpolator_{locale}.qm')
        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        self.actions = []
        self.menu = self.tr(u'&Best Fit Interpolator')
        self.first_start = None

        self._proj_signals_connected = False
        self.ok_ctrl = None  # Ordinary kriging dispatcher/controller (tab Geostatistics)
        self._last_planar_crs_warning_key = None

        # Matplotlib canvases
        self.det_interp_fig = None           # Interpolation (Deterministic tab)
        self.det_interp_canvas = None
        self.det_val_fig = None              # Validation tab
        self.det_val_canvas = None

        # Dedicated canvas for Data tab (points-only)
        self.data_fig = None
        self.data_canvas = None

        # Dedicated canvas for Kriging CV (CV_Kriging_widget)
        self.ok_cv_fig = None
        self.ok_cv_canvas = None

        # Track the last data selection to avoid clearing plots unnecessarily
        self._last_data_selection = (None, None, None)
        self._last_det_interpolation = None
        self._last_ok_interpolation = None
        self._suppress_data_change_events = False

        # Output directory inside the QGIS project folder
        self.output_dir = None

        # Track canvases already wired with save handlers
        self._save_handlers = set()

        # Deterministic mode widgets (wired later)
        self.btn_idw_opt = None   # Optimize checkbox
        self.btn_idw_man = None   # Manual radio/checkbox
        self.btn_tps     = None   # TPS checkbox/radio
        self._current_mode = self.MODE_IDW_OPT  # default

        # CV widgets (Deterministic tab)
        self.rad_cv_auto = None
        self.rad_cv_loocv = None
        self.rad_cv_kfold = None
        self.spin_k = None
        self._cv_mode = self.CV_AUTO

        # CV widgets (Kriging tab)
        self.rad_cv_ok_auto = None
        self.rad_cv_ok_loocv = None
        self.rad_cv_ok_kfold = None
        self.spin_k_ok = None
        self._cv_mode_ok = self.CV_AUTO

        # Machine Learning tab controller
        self.ml_ctrl = None
        self.rk_ctrl = None
        self.framework_ctrl = None

    def tr(self, message):
        return QCoreApplication.translate('BestFitInterpolator', message)

    def add_action(self, icon_path, text, callback, enabled_flag=True,
                   add_to_menu=True, add_to_toolbar=True, status_tip=None,
                   whats_this=None, parent=None):
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)
        if status_tip is not None:
            action.setStatusTip(status_tip)
        if whats_this is not None:
            action.setWhatsThis(whats_this)
        if add_to_toolbar:
            self.iface.addToolBarIcon(action)
        if add_to_menu:
            self.iface.addPluginToMenu(self.menu, action)
        self.actions.append(action)
        return action

    def initGui(self):
        icon_path = ':/plugins/BestFitInterpolator/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Best Fit Interpolator'),
            callback=self.run,
            parent=self.iface.mainWindow()
        )
        self.first_start = True

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.tr(u'&Best Fit Interpolator'), action)
            self.iface.removeToolBarIcon(action)

    # -------------------------- Project & paths helpers --------------------------

    def _ensure_project_saved(self):
        """Ensure the QGIS project is saved; if not, ask user to save and try to trigger Save As."""
        proj = QgsProject.instance()
        path = proj.fileName()
        if path and os.path.isfile(path):
            return True
        QMessageBox.warning(
            self.iface.mainWindow(),
            "Project must be saved",
            "Please save the QGIS project before using the plugin.\n\n"
            "The output folder will be created next to the project file."
        )
        try:
            self.iface.actionSaveProjectAs().trigger()
        except Exception:
            pass
        path = proj.fileName()
        saved = bool(path and os.path.isfile(path))
        if not saved:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Project not saved",
                "The QGIS project is still not saved. Please save the project before using the plugin."
            )
        return saved

    def _ensure_output_dir(self):
        """Create BestFitInterpolation folder inside the project directory."""
        proj_path = QgsProject.instance().fileName()
        base_dir = os.path.dirname(proj_path)
        out_dir = os.path.join(base_dir, "BestFitInterpolation")
        os.makedirs(out_dir, exist_ok=True)
        self.output_dir = out_dir
        return out_dir

    def _should_export_raster(self):
        """Return True to export rasters to project folder. If widget not present, default True."""
        chk = getattr(self.dlg, "chkExportRaster", None)
        if chk is None:
            return True
        try:
            return bool(chk.isChecked())
        except Exception:
            return True

    def _is_temporary_output_path(self, path):
        """Return True when an output path is inside the system temp folder."""
        try:
            tmp_dir = os.path.abspath(tempfile.gettempdir())
            out_path = os.path.abspath(str(path))
            return os.path.commonpath([tmp_dir, out_path]) == tmp_dir
        except Exception:
            return False

    def _mark_temporary_layer(self, layer, raster_path=None):
        """Mark plugin outputs that were not exported to the project folder."""
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
        """Create a raster layer, using a temporary wrapper when the output is not exported."""
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

    def _get_pixel_size(self, default=0.01):
        """Read pixel size from the Data tab (spinPixelSize)."""
        w = getattr(self.dlg, "spinPixelSize", None)
        if w is None:
            w = getattr(self.dlg, "pixelsize", None)  # alias safety
        try:
            return float(w.value())
        except Exception:
            return float(default)

    # -------------------------- Project/layers helpers --------------------------

    def _activate_data_tab(self):
        """Select the main Data tab on open without touching nested tab widgets."""
        tabw = getattr(self.dlg, "mainTabs", None)
        if tabw is None:
            tabs = self.dlg.findChildren(QTabWidget)
            if not tabs:
                return
            tabw = tabs[0]
        target_idx = None
        for i in range(tabw.count()):
            t = (tabw.tabText(i) or "").lower()
            if 'data' in t or 'datos' in t:
                target_idx = i
                break
        tabw.setCurrentIndex(target_idx if target_idx is not None else 0)

    def _rename_interpolation_tab(self):
        """Keep the main deterministic tab name stable without renaming nested tabs."""
        tabw = getattr(self.dlg, "mainTabs", None)
        if tabw is None:
            tabs = self.dlg.findChildren(QTabWidget)
            if not tabs:
                return
            tabw = tabs[0]
        for i in range(tabw.count()):
            t = tabw.tabText(i)
            if 'interpolation' in (t or '').lower():
                tabw.setTabText(i, 'Deterministic Interpolation')

    def _connect_project_signals(self):
        """Connect to project signals so the combos refresh as layers change."""
        if self._proj_signals_connected:
            return
        proj = QgsProject.instance()
        if hasattr(proj, 'layersAdded'):
            proj.layersAdded.connect(self._on_project_layers_added)
        if hasattr(proj, 'layersRemoved'):
            proj.layersRemoved.connect(self._on_project_layers_removed)
        if hasattr(proj, 'layerWasAdded'):
            proj.layerWasAdded.connect(self._on_project_layer_was_added)
        self._proj_signals_connected = True

    def _disconnect_project_signals(self):
        if not self._proj_signals_connected:
            return
        proj = QgsProject.instance()
        for sig, slot in [
            ('layersAdded', self._on_project_layers_added),
            ('layersRemoved', self._on_project_layers_removed),
            ('layerWasAdded', self._on_project_layer_was_added),
        ]:
            try:
                if hasattr(proj, sig):
                    getattr(proj, sig).disconnect(slot)
            except Exception:
                pass
        self._proj_signals_connected = False

    def _on_project_layers_added(self, layers):
        self._refresh_layer_combos_preserving_selection()
        try:
            if self.ml_ctrl is not None:
                self.ml_ctrl.refresh_raster_combo()
        except Exception:
            pass

    def _on_project_layers_removed(self, layer_ids):
        self._refresh_layer_combos_preserving_selection()
        try:
            if self.ml_ctrl is not None:
                self.ml_ctrl.refresh_raster_combo()
        except Exception:
            pass

    def _on_project_layer_was_added(self, layer):
        self._refresh_layer_combos_preserving_selection()
        try:
            if self.ml_ctrl is not None:
                self.ml_ctrl.refresh_raster_combo()
        except Exception:
            pass

    def _refresh_layer_combos_preserving_selection(self):
        if not hasattr(self, 'dlg') or self.dlg is None:
            return
        old_points = self.dlg.Points.currentText()
        old_attr = self.dlg.Points_2.currentText()
        old_poly = self.dlg.poly.currentText()
        # Suppress data-change side effects while refreshing combos
        self._suppress_data_change_events = True
        try:
            self.load_layers()
            idx_points = self.dlg.Points.findText(old_points)
            if idx_points >= 0:
                self.dlg.Points.setCurrentIndex(idx_points)
                self.update_variables()
                idx_attr = self.dlg.Points_2.findText(old_attr)
                if idx_attr >= 0:
                    self.dlg.Points_2.setCurrentIndex(idx_attr)
                    if not self._suppress_data_change_events:
                        self._update_ok_context()
            idx_poly = self.dlg.poly.findText(old_poly)
            if idx_poly >= 0:
                self.dlg.poly.setCurrentIndex(idx_poly)
        finally:
            self._suppress_data_change_events = False
        try:
            self._last_data_selection = (
                self.dlg.Points.currentText(),
                self.dlg.Points_2.currentText(),
                self.dlg.poly.currentText(),
            )
        except Exception:
            pass
        try:
            self._sync_framework_from_current_data()
        except Exception:
            pass

    # -------------------------- UI aliasing & helpers --------------------------

    def _bind_ui_aliases(self):
        """
        Map new .ui object names to legacy attribute names expected by the code.
        Also normalize deterministic-option widget names (manual/optimize/tps)
        and CV widgets.
        """
        alias = {
            # Data tab (points-only)
            'Points': 'cmbPointsLayer',
            'Points_2': 'cmbVariable',
            'poly': 'cmbPolygonLayer',
            'LoadButton': 'btnLoad',

            # Deterministic tab
            'pixelsize': 'spinPixelSize',
            'manualParams': 'radManualParams',       # Manual (radio/checkbox)
            'manualNInput': 'spinNeighbors',
            'manualPInput': 'spinPower',
            'interpolateButton': 'btnInterpolate',
            'btnRunCV': 'btnRunCV',
            'canvasDetInterpolation': 'canvasDetInterpolation',
            'canvasDetValidation': 'canvasDetValidation',
            'valRMSE': 'valRMSE',
            'valLCCC': 'valLCCC',
            'chkExportRaster': 'chkExportRaster',

            # Optimize / TPS
            'chkOptimize': 'chkOptimize',
            'chkIDWOptimize': 'chkIDWOptimize',
            'radIDWOptimize': 'radIDWOptimize',
            'TPS_Button': 'chkTPS',
            'radTPS': 'radTPS',

            # CV widgets (shared)
            'radCVAuto': 'radCVAuto',
            'radCVLOOCV': 'radCVLOOCV',
            'radCVKFold': 'radCVKFold',
            'spinK': 'spinK',

            # Kriging Tab
            'tabKriging': 'tabKriging',
            'valOKZName': 'valOKZName',
            'valOKSamples': 'valOKSamples',
            'spinOKCutoff': 'spinOKCutoff',
            'spinOKLag': 'spinOKLag',
            'btnOKCalculate': 'btnOKCalculate',
            'cmbOKFitMethod': 'cmbOKFitMethod',
            'cmbOKModel': 'cmbOKModel',
            'spinOKNugget': 'spinOKNugget',
            'spinOKPsill': 'spinOKPsill',
            'spinOKRange': 'spinOKRange',
            'btnOKInterpolate': 'btnOKInterpolate',
            'canvasOKVariogram': 'CanvasOKVariogram',
            'canvasOKInterpolation': 'CanvasOKInterpolation',
            'canvasOKValidation': 'canvasOKValidation',
            # The .ui uses 'btn_OKRunCV' (underscore); map legacy name
            'btnOKRunCV': 'btn_OKRunCV',
            'CV_Kriging_widget': 'CV_Kriging_widget',  # new widget for OK CV plot

            # Kriging validation metrics (optional)
            'valOKRMSE': 'valOKRMSE',
            'valOKLCCC': 'valOKLCCC',
            'valOKRMSEpct': 'valOKRMSEpct',
            'valOKR2': 'valOKR2',
            'valOKMAE': 'valOKMAE',
            'valOKPearsonR': 'valOKPearsonR',

            # Kriging CV K-fold spin: in the .ui it's named 'spinBox'
            'spin_k_ok': 'spinBox',

            # Main tab widget
            'mainTabs': 'mainTabs',
        }

        # Deterministic extra label for RMSE%
        if hasattr(self.dlg, 'valRMSE_2'):
            setattr(self.dlg, 'valRMSE_2', self.dlg.valRMSE_2)

        # Direct aliases for known widgets present in your .ui
        self.dlg.Points = self.dlg.cmbPointsLayer
        self.dlg.Points_2 = self.dlg.cmbVariable
        self.dlg.poly = self.dlg.cmbPolygonLayer
        self.dlg.LoadButton = self.dlg.btnLoad
        self.dlg.canvasData = self.dlg.canvasData

        # Global pixel/export live in Data tab but names remain the same
        self.dlg.pixelsize = self.dlg.spinPixelSize
        self.dlg.chkExportRaster = self.dlg.chkExportRaster

        # Deterministic Tab
        self.dlg.manualParams = self.dlg.radManualParams
        self.dlg.manualNInput = self.dlg.spinNeighbors
        self.dlg.manualPInput = self.dlg.spinPower
        self.dlg.interpolateButton = self.dlg.btnInterpolate
        self.dlg.btnRunCV = self.dlg.btnRunCV
        self.dlg.canvasDetInterpolation = self.dlg.canvasDetInterpolation
        self.dlg.canvasDetValidation = self.dlg.canvasDetValidation
        self.dlg.valRMSE = self.dlg.valRMSE
        self.dlg.valLCCC = self.dlg.valLCCC
        self.dlg.chkOptimize = self.dlg.chkOptimize
        self.dlg.chkTPS = self.dlg.chkTPS

        # Kriging Tab - robust mapping for any alternative names
        for legacy, new in alias.items():
            if hasattr(self.dlg, legacy):
                continue
            if hasattr(self.dlg, new):
                setattr(self.dlg, legacy, getattr(self.dlg, new))

        self._polish_deterministic_options_layout()
        self._reorder_validation_metric_layouts()
        self._clear_all_validation_metric_labels()

    def _info_toolbutton(self, tooltip: str):
        lbl = QLabel(self.dlg)
        lbl.setObjectName(f"lblInfo_{uuid.uuid4().hex[:8]}")
        lbl.setFocusPolicy(Qt.NoFocus)
        lbl.setToolTip(tooltip)
        lbl.setFixedSize(18, 18)
        try:
            icon_path = os.path.join(self.plugin_dir, "info.png")
            if os.path.exists(icon_path):
                lbl.setPixmap(QPixmap(icon_path))
                lbl.setScaledContents(True)
        except Exception:
            pass
        return lbl

    def _add_info_icon_next_to_widget(self, widget_name: str, tooltip: str) -> None:
        """Add the standard hover info icon beside an existing widget."""
        if getattr(self, f"_info_added_{widget_name}", False):
            return
        widget = getattr(self.dlg, widget_name, None)
        if widget is None:
            return
        try:
            parent = widget.parentWidget()
            layout = parent.layout() if parent is not None else None
            if layout is None:
                return
            icon = self._info_toolbutton(tooltip)
            index = layout.indexOf(widget)
            if index < 0:
                return
            row, col, rowspan, colspan = layout.getItemPosition(index)
            if colspan and colspan > 1:
                layout.removeWidget(widget)
                layout.addWidget(widget, row, col, rowspan, max(1, colspan - 1))
                layout.addWidget(icon, row, col + max(1, colspan - 1), 1, 1)
            else:
                layout.addWidget(icon, row, col + 1, 1, 1)
            setattr(self, f"_info_added_{widget_name}", True)
        except Exception:
            pass

    def _add_validation_auto_info_icons(self) -> None:
        tooltip = (
            "Automatic cross-validation selects the validation strategy from the sample size. "
            "For small datasets it uses LOOCV; for larger datasets it uses K-Fold. "
            "LOOCV leaves one sample out at a time and validates on that sample. "
            "K-Fold splits the samples into k groups, trains on k-1 groups, and validates on the remaining group."
        )
        for name in (
            "radCVAuto",
            "radCV_OK_Auto",
            "radRF_CV_Auto",
            "radSVM_CV_Auto",
            "radRK_CV_Auto",
        ):
            self._add_info_icon_next_to_widget(name, tooltip)

    def _polish_deterministic_options_layout(self):
        """Group IDW and TPS controls separately and add hover help for IDW parameters."""
        group = getattr(self.dlg, "groupDetOptions", None)
        if group is None or getattr(self, "_det_options_polished", False):
            return

        controls = [
            getattr(self.dlg, name, None)
            for name in (
                "radManualParams", "lblNeighbors", "spinNeighbors", "lblPower",
                "spinPower", "chkOptimize", "chkTPS", "btnInterpolate"
            )
        ]
        old_layout = group.layout()
        if old_layout is not None:
            for widget in controls:
                if widget is not None:
                    try:
                        old_layout.removeWidget(widget)
                    except Exception:
                        pass
            while old_layout.count():
                item = old_layout.takeAt(0)
                widget = item.widget()
                if widget is not None and widget not in controls:
                    widget.setParent(None)

        if old_layout is not None:
            root = old_layout
        else:
            root = QHBoxLayout()
            try:
                group.setLayout(root)
            except Exception:
                pass
        try:
            root.setContentsMargins(8, 8, 8, 8)
            root.setSpacing(10)
        except Exception:
            pass

        idw_group = QGroupBox("IDW", group)
        idw_group.setObjectName("groupIDWOptions")
        idw_layout = QGridLayout(idw_group)
        idw_layout.setContentsMargins(8, 8, 8, 8)
        idw_layout.setHorizontalSpacing(6)
        idw_layout.setVerticalSpacing(4)

        tps_group = QGroupBox("TPS", group)
        tps_group.setObjectName("groupTPSOptions")
        tps_layout = QHBoxLayout(tps_group)
        tps_layout.setContentsMargins(8, 8, 8, 8)

        neighbor_tip = (
            "Number of nearest sample points used for each IDW prediction. "
            "More neighbors usually smooth the surface; fewer neighbors emphasize local variation."
        )
        power_tip = (
            "IDW power controls how fast influence decreases with distance. "
            "Higher values give nearby points more weight; lower values produce smoother results."
        )

        for name, tip in (("lblNeighbors", neighbor_tip), ("spinNeighbors", neighbor_tip),
                          ("lblPower", power_tip), ("spinPower", power_tip)):
            widget = getattr(self.dlg, name, None)
            if widget is not None and hasattr(widget, "setToolTip"):
                widget.setToolTip(tip)

        if getattr(self.dlg, "radManualParams", None) is not None:
            idw_layout.addWidget(self.dlg.radManualParams, 0, 0, 1, 1)
        if getattr(self.dlg, "lblNeighbors", None) is not None:
            idw_layout.addWidget(self.dlg.lblNeighbors, 0, 1, 1, 1)
        idw_layout.addWidget(self._info_toolbutton(neighbor_tip), 0, 2, 1, 1)
        if getattr(self.dlg, "spinNeighbors", None) is not None:
            idw_layout.addWidget(self.dlg.spinNeighbors, 0, 3, 1, 1)
        if getattr(self.dlg, "lblPower", None) is not None:
            idw_layout.addWidget(self.dlg.lblPower, 0, 4, 1, 1)
        idw_layout.addWidget(self._info_toolbutton(power_tip), 0, 5, 1, 1)
        if getattr(self.dlg, "spinPower", None) is not None:
            idw_layout.addWidget(self.dlg.spinPower, 0, 6, 1, 1)
        if getattr(self.dlg, "chkOptimize", None) is not None:
            idw_layout.addWidget(self.dlg.chkOptimize, 0, 7, 1, 1)

        if getattr(self.dlg, "chkTPS", None) is not None:
            tps_layout.addWidget(self.dlg.chkTPS)
        try:
            if isinstance(root, QGridLayout):
                root.addWidget(idw_group, 0, 0, 1, 1)
                root.addWidget(tps_group, 0, 1, 1, 1)
                if getattr(self.dlg, "btnInterpolate", None) is not None:
                    root.addWidget(self.dlg.btnInterpolate, 0, 2, 1, 1)
            else:
                root.addWidget(idw_group, 1)
                root.addWidget(tps_group, 0)
                if getattr(self.dlg, "btnInterpolate", None) is not None:
                    root.addWidget(self.dlg.btnInterpolate, 0)
        except Exception:
            pass

        self._det_options_polished = True

    def _move_metric_pair(self, grid, row: int, label_name: str, value_name: str, label_text: str):
        label = getattr(self.dlg, label_name, None)
        value = getattr(self.dlg, value_name, None)
        if label is not None:
            try:
                label.setText(label_text)
                grid.addWidget(label, row, 0, 1, 1)
            except Exception:
                pass
        if value is not None:
            try:
                grid.addWidget(value, row, 1, 1, 1)
            except Exception:
                pass

    def _reorder_metric_grid(self, grid_name: str, pairs):
        grid = getattr(self.dlg, grid_name, None)
        if grid is None:
            return
        for row, (label_name, value_name, label_text) in enumerate(pairs):
            self._move_metric_pair(grid, row, label_name, value_name, label_text)

    def _reorder_validation_metric_layouts(self):
        metric_sets = {
            "gridLayout_metrics": [
                ("lblRMSE", "valRMSE", "RMSE:"),
                ("lblRMSE_2", "valRMSE_2", "RMSE%:"),
                ("lblMAE", "valMAE", "MAE:"),
                ("lblR2", "valR2", "R2:"),
                ("lblPearsonR", "valPearsonR", "Pearson:"),
                ("lblLCCC", "valLCCC", "LCCC:"),
            ],
            "gridOKMetrics": [
                ("lblvalOKRMSE", "valOKRMSE", "RMSE"),
                ("lblvalOKRMSEpct", "valOKRMSEpct", "RMSE%"),
                ("lblvalOKMAE", "valOKMAE", "MAE"),
                ("lblvalOKR2", "valOKR2", "R2"),
                ("lblvalOKPearsonR", "valOKPearsonR", "Pearson"),
                ("lblvalOKLCCC", "valOKLCCC", "LCCC"),
            ],
            "gridLayoutRFMetrics": [
                ("labelRFRMSE", "valRFRMSE", "RMSE"),
                ("labelRFRMSEpct", "valRFRMSEpct", "RMSE%"),
                ("labelRFMAE", "valRFMAE", "MAE"),
                ("labelRFR2", "valRFR2", "R2"),
                ("labelRFPearsonR", "valRFPearsonR", "Pearson"),
                ("labelRFLCCC", "valRFLCCC", "LCCC"),
            ],
            "gridLayoutSVMMetrics": [
                ("labelSVMRMSE", "valSVMRMSE", "RMSE"),
                ("labelSVMRMSEpct", "valSVMRMSEpct", "RMSE%"),
                ("labelSVMMAE", "valSVMMAE", "MAE"),
                ("labelSVMR2", "valSVMR2", "R2"),
                ("labelSVMPearsonR", "valSVMPearsonR", "Pearson"),
                ("labelSVMLCCC", "valSVMLCCC", "LCCC"),
            ],
            "gridLayoutRKMetrics": [
                ("labelRKRMSE", "valRKRMSE", "RMSE"),
                ("labelRKRMSEpct", "valRKRMSEpct", "RMSE%"),
                ("labelRKMAE", "valRKMAE", "MAE"),
                ("labelRKR2", "valRKR2", "R2"),
                ("labelRKPearsonR", "valRKPearsonR", "Pearson"),
                ("labelRKLCCC", "valRKLCCC", "LCCC"),
            ],
        }
        for grid_name, pairs in metric_sets.items():
            self._reorder_metric_grid(grid_name, pairs)

    def _clear_validation_metric_labels(self, names):
        for name in names:
            widget = getattr(self.dlg, name, None)
            if widget is not None and hasattr(widget, "setText"):
                try:
                    widget.setText("--")
                except Exception:
                    pass

    def _clear_det_validation_outputs(self):
        self._clear_validation_metric_labels([
            "valRMSE", "valRMSE_2", "valRMSEpct", "valMAE", "valR2", "valPearsonR", "valLCCC"
        ])

    def _clear_all_validation_metric_labels(self):
        self._clear_validation_metric_labels([
            "valRMSE", "valRMSE_2", "valRMSEpct", "valMAE", "valR2", "valPearsonR", "valLCCC",
            "valOKRMSE", "valOKRMSEpct", "valOKMAE", "valOKR2", "valOKPearsonR", "valOKLCCC",
            "valRFRMSE", "valRFRMSEpct", "valRFMAE", "valRFR2", "valRFPearsonR", "valRFLCCC",
            "valSVMRMSE", "valSVMRMSEpct", "valSVMMAE", "valSVMR2", "valSVMPearsonR", "valSVMLCCC",
            "valRKRMSE", "valRKRMSEpct", "valRKMAE", "valRKR2", "valRKPearsonR", "valRKLCCC",
        ])

    def _read_numeric_from_widget(self, w, cast=float, default=None):
        """Read a number from QDoubleSpinBox/QSpinBox or QLineEdit; return default on failure."""
        try:
            if hasattr(w, 'value'):
                return cast(w.value())
            if hasattr(w, 'text'):
                txt = w.text().strip()
                return cast(float(txt)) if cast is not int else int(float(txt))
        except Exception:
            pass
        return default

    def _ensure_layout(self, widget):
        """Ensure a QVBoxLayout exists on a container widget."""
        layout = widget.layout()
        if layout is None:
            layout = QVBoxLayout(widget)
            layout.setContentsMargins(0, 0, 0, 0)
        return layout

    def _stabilize_canvas_widget(self, canvas):
        """Keep Matplotlib canvases from resizing their parent after redraws."""
        try:
            canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            canvas.setMinimumSize(1, 1)
            canvas.updateGeometry()
        except Exception:
            pass

    def _sync_figure_to_canvas(self, fig, canvas, fallback=(5.0, 4.0)):
        """Match figure inches to the current Qt canvas size before plotting."""
        return

    # ------------------ Deterministic mode exclusivity (manual) -----------------

    def _wire_deterministic_controls(self):
        """Wire deterministic options and enforce mutual exclusivity."""
        self.btn_idw_man = getattr(self.dlg, 'manualParams', None)
        self.btn_idw_opt = (
            getattr(self.dlg, 'chkOptimize', None)
            or getattr(self.dlg, 'chkIDWOptimize', None)
            or getattr(self.dlg, 'radIDWOptimize', None)
        )
        self.btn_tps = (
            getattr(self.dlg, 'TPS_Button', None)
            or getattr(self.dlg, 'chkTPS', None)
            or getattr(self.dlg, 'radTPS', None)
        )

        if self.btn_idw_opt is not None:
            try:
                self.btn_idw_opt.setChecked(True)
            except Exception:
                pass
            self._current_mode = self.MODE_IDW_OPT
        elif self.btn_idw_man is not None:
            try:
                self.btn_idw_man.setChecked(True)
            except Exception:
                pass
            self._current_mode = self.MODE_IDW_MAN
        elif self.btn_tps is not None:
            try:
                self.btn_tps.setChecked(True)
            except Exception:
                pass
            self._current_mode = self.MODE_TPS

        if self.btn_idw_opt is not None and hasattr(self.btn_idw_opt, 'toggled'):
            self.btn_idw_opt.toggled.connect(lambda s: self._on_option_toggled('opt', s))
        if self.btn_idw_man is not None and hasattr(self.btn_idw_man, 'toggled'):
            self.btn_idw_man.toggled.connect(lambda s: self._on_option_toggled('man', s))
        if self.btn_tps is not None and hasattr(self.btn_tps, 'toggled'):
            self.btn_tps.toggled.connect(lambda s: self._on_option_toggled('tps', s))
        self._apply_mode_ui()

    def _on_option_toggled(self, who: str, state: bool):
        if not state:
            if not self._any_option_checked():
                self._select_default_option()
            self._apply_mode_ui()
            return
        if who == 'opt':
            self._check(self.btn_idw_opt, True);  self._check(self.btn_idw_man, False); self._check(self.btn_tps, False)
            self._current_mode = self.MODE_IDW_OPT
        elif who == 'man':
            self._check(self.btn_idw_opt, False); self._check(self.btn_idw_man, True);  self._check(self.btn_tps, False)
            self._current_mode = self.MODE_IDW_MAN
        elif who == 'tps':
            self._check(self.btn_idw_opt, False); self._check(self.btn_idw_man, False); self._check(self.btn_tps, True)
            self._current_mode = self.MODE_TPS
        self._apply_mode_ui()

    def _any_option_checked(self) -> bool:
        for b in (self.btn_idw_opt, self.btn_tps, self.btn_idw_man):
            try:
                if b is not None and b.isChecked():
                    return True
            except Exception:
                pass
        return False

    def _select_default_option(self):
        if self.btn_idw_opt is not None:
            self._check(self.btn_idw_opt, True); self._current_mode = self.MODE_IDW_OPT
        elif self.btn_idw_man is not None:
            self._check(self.btn_idw_man, True); self._current_mode = self.MODE_IDW_MAN
        elif self.btn_tps is not None:
            self._check(self.btn_tps, True); self._current_mode = self.MODE_TPS

    @staticmethod
    def _check(btn, state: bool):
        try:
            if btn is not None and hasattr(btn, 'setChecked'):
                btn.setChecked(state)
        except Exception:
            pass

    def _apply_mode_ui(self):
        is_manual = (self._current_mode == self.MODE_IDW_MAN)
        if hasattr(self.dlg, 'manualNInput') and self.dlg.manualNInput is not None:
            try:
                self.dlg.manualNInput.setEnabled(is_manual)
            except Exception:
                pass
        if hasattr(self.dlg, 'manualPInput') and self.dlg.manualPInput is not None:
            try:
                self.dlg.manualPInput.setEnabled(is_manual)
            except Exception:
                pass

    # ---------------------------- CV controls wiring ----------------------------

    def _wire_cv_controls(self):
        """Wire CV widgets (Deterministic tab) and set defaults."""
        self.rad_cv_auto  = getattr(self.dlg, 'radCVAuto', None)
        self.rad_cv_loocv = getattr(self.dlg, 'radCVLOOCV', None)
        self.rad_cv_kfold = getattr(self.dlg, 'radCVKFold', None)
        self.spin_k       = getattr(self.dlg, 'spinK', None)

        # Default: Auto
        if self.rad_cv_auto and hasattr(self.rad_cv_auto, 'setChecked'):
            self.rad_cv_auto.setChecked(True)
        self._cv_mode = self.CV_AUTO

        # Signals
        def on_changed():
            self._cv_mode = self._get_cv_mode()
            # Enable K spin only for KFold
            if self.spin_k and hasattr(self.spin_k, 'setEnabled'):
                self.spin_k.setEnabled(self._cv_mode == self.CV_KFOLD)

        for w in (self.rad_cv_auto, self.rad_cv_loocv, self.rad_cv_kfold):
            if w is not None:
                if hasattr(w, 'toggled'):
                    w.toggled.connect(on_changed)
                if hasattr(w, 'clicked'):
                    w.clicked.connect(on_changed)

        # Initial enable/disable
        on_changed()

    def _wire_ok_cv_controls(self):
        """Wire CV widgets (Kriging) y activar spin sÃ³lo en K-fold."""
        # Guardar referencias directas
        self.rad_cv_ok_auto  = getattr(self.dlg, 'radCV_OK_Auto', None)
        self.rad_cv_ok_loocv = getattr(self.dlg, 'radCV_OK_LOOCV', None)
        self.rad_cv_ok_kfold = getattr(self.dlg, 'radCV_OK_Kfold', None)
        self.spin_k_ok       = getattr(self.dlg, 'spin_k_ok', None)
        self._cv_mode_ok = self.CV_AUTO

        # Default: Auto -> si no existe, LOOCV -> si no, K-fold
        if self.rad_cv_ok_auto and hasattr(self.rad_cv_ok_auto, 'setChecked'):
            self.rad_cv_ok_auto.setChecked(True)
        elif self.rad_cv_ok_loocv and hasattr(self.rad_cv_ok_loocv, 'setChecked'):
            self.rad_cv_ok_loocv.setChecked(True)
            self._cv_mode_ok = self.CV_LOOCV
        elif self.rad_cv_ok_kfold and hasattr(self.rad_cv_ok_kfold, 'setChecked'):
            self.rad_cv_ok_kfold.setChecked(True)
            self._cv_mode_ok = self.CV_KFOLD

        def on_changed_ok(*_):
            # Releer modo segÃºn radios
            try:
                if self.rad_cv_ok_loocv and self.rad_cv_ok_loocv.isChecked():
                    self._cv_mode_ok = self.CV_LOOCV
                elif self.rad_cv_ok_kfold and self.rad_cv_ok_kfold.isChecked():
                    self._cv_mode_ok = self.CV_KFOLD
                else:
                    self._cv_mode_ok = self.CV_AUTO
            except Exception:
                self._cv_mode_ok = self.CV_AUTO

            # Habilitar spin sÃ³lo para K-fold
            if self.spin_k_ok and hasattr(self.spin_k_ok, 'setEnabled'):
                self.spin_k_ok.setEnabled(self._cv_mode_ok == self.CV_KFOLD)

        # Conectar signals (toggled + clicked por seguridad)
        for w in (self.rad_cv_ok_auto, self.rad_cv_ok_loocv, self.rad_cv_ok_kfold):
            if w is not None:
                if hasattr(w, 'toggled'):
                    w.toggled.connect(on_changed_ok)
                if hasattr(w, 'clicked'):
                    w.clicked.connect(on_changed_ok)

        # Estado inicial coherente
        on_changed_ok()

    def _get_cv_mode_ok(self):
        """Current CV mode for OK (read from stored refs)."""
        try:
            if self.rad_cv_ok_loocv and self.rad_cv_ok_loocv.isChecked():
                return self.CV_LOOCV
            if self.rad_cv_ok_kfold and self.rad_cv_ok_kfold.isChecked():
                return self.CV_KFOLD
            return self.CV_AUTO
        except Exception:
            return self.CV_AUTO

    def _get_cv_mode(self):
        """Read current CV mode from UI (Deterministic tab)."""
        try:
            if self.rad_cv_loocv and self.rad_cv_loocv.isChecked():
                return self.CV_LOOCV
            if self.rad_cv_kfold and self.rad_cv_kfold.isChecked():
                return self.CV_KFOLD
            return self.CV_AUTO
        except Exception:
            return self.CV_AUTO

    # --------------------------------- Canvases --------------------------------

    def _attach_canvases(self):
        """Attach persistent Matplotlib canvases to Interpolation and Validation placeholders."""
        interp_container = getattr(self.dlg, "canvasDetInterpolation", None)
        self.det_interp_fig = Figure(figsize=(5, 4))
        self.det_interp_canvas = FigureCanvas(self.det_interp_fig)
        self._stabilize_canvas_widget(self.det_interp_canvas)
        if interp_container is not None:
            ilayout = self._ensure_layout(interp_container)
            for i in reversed(range(ilayout.count())):
                w = ilayout.itemAt(i).widget()
                if w is not None:
                    w.setParent(None)
            ilayout.addWidget(self.det_interp_canvas)
        self._install_save_png_handler(self.det_interp_canvas, self.det_interp_fig, default_prefix="deterministic_interpolation")

        val_container = getattr(self.dlg, "canvasDetValidation", None)
        self.det_val_fig = Figure(figsize=(5, 4))
        self.det_val_canvas = FigureCanvas(self.det_val_fig)
        self._stabilize_canvas_widget(self.det_val_canvas)
        if val_container is not None:
            vlayout = self._ensure_layout(val_container)
            for i in reversed(range(vlayout.count())):
                w = vlayout.itemAt(i).widget()
                if w is not None:
                    w.setParent(None)
            vlayout.addWidget(self.det_val_canvas)
        self._install_save_png_handler(self.det_val_canvas, self.det_val_fig, default_prefix="deterministic_cv")

    def _attach_data_canvas(self):
        """Attach persistent Matplotlib canvas to Data tab placeholder."""
        data_container = getattr(self.dlg, "canvasData", None)
        self.data_fig = Figure(figsize=(5, 4))
        self.data_canvas = FigureCanvas(self.data_fig)
        self._stabilize_canvas_widget(self.data_canvas)
        if data_container is not None:
            dlayout = self._ensure_layout(data_container)
            for i in reversed(range(dlayout.count())):
                w = dlayout.itemAt(i).widget()
                if w is not None:
                    w.setParent(None)
            dlayout.addWidget(self.data_canvas)
        self._install_save_png_handler(self.data_canvas, self.data_fig, default_prefix="data_tab")

    def _attach_ok_cv_canvas(self):
        """Attach persistent Matplotlib canvas to Kriging Validation area."""
        okcv_container = getattr(self.dlg, "canvasOKValidation", None)
        if okcv_container is None:
            okcv_container = getattr(self.dlg, "CV_Kriging_widget", None)  # fallback
        if okcv_container is None:
            return
        if self.ok_cv_fig is None:
            self.ok_cv_fig = Figure(figsize=(5, 4))
        self.ok_cv_canvas = FigureCanvas(self.ok_cv_fig)
        self._stabilize_canvas_widget(self.ok_cv_canvas)
        layout = self._ensure_layout(okcv_container)
        for i in reversed(range(layout.count())):
            w = layout.itemAt(i).widget()
            if w is not None:
                w.setParent(None)
        layout.addWidget(self.ok_cv_canvas)
        self._install_save_png_handler(self.ok_cv_canvas, self.ok_cv_fig, default_prefix="kriging_cv")

    # ----------------------------- Save PNG hooks -----------------------------

    def _install_save_png_handler(self, canvas, fig, default_prefix: str):
        """Install a right-click context menu ('Save graphâ€¦') on a Matplotlib canvas."""
        try:
            key = id(canvas)
            if key in self._save_handlers or canvas is None or fig is None:
                return

            # Use Qt context menu for right-click
            try:
                from qgis.PyQt.QtCore import Qt
                canvas.setContextMenuPolicy(Qt.CustomContextMenu)
            except Exception:
                pass

            def _show_menu(pos):
                try:
                    menu = QMenu(self.dlg)
                    act_view = menu.addAction("View larger view")
                    act_copy = menu.addAction("Copy graph")
                    act_save = menu.addAction("Save graphâ€¦")
                    chosen = menu.exec_(canvas.mapToGlobal(pos))
                    if chosen == act_view:
                        self._show_larger_graph(fig, default_prefix)
                    elif chosen == act_copy:
                        self._copy_figure_to_clipboard(fig)
                    elif chosen == act_save:
                        suggested_dir = self._ensure_output_dir() or os.path.expanduser("~")
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
                # Fallback: basic right-click via mpl event if custom menu is unavailable
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
            try:
                QMessageBox.warning(self.dlg, "Copy graph", f"Could not copy graph:\n{exc}")
            except Exception:
                pass

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

    def _ensure_canvases_attached(self):
        """Ensure all canvases exist before plotting."""
        if self.det_interp_fig is None or self.det_interp_canvas is None:
            try:
                self._attach_canvases()
            except Exception:
                self.det_interp_fig = FigureCanvas(Figure(figsize=(5, 4))).figure
                self.det_interp_canvas = FigureCanvas(self.det_interp_fig)
        if self.det_val_fig is None or self.det_val_canvas is None:
            try:
                self._attach_canvases()
            except Exception:
                self.det_val_fig = FigureCanvas(Figure(figsize=(5, 4))).figure
                self.det_val_canvas = FigureCanvas(self.det_val_fig)
        if self.data_fig is None or self.data_canvas is None:
            try:
                self._attach_data_canvas()
            except Exception:
                self.data_fig = FigureCanvas(Figure(figsize=(5, 4))).figure
                self.data_canvas = FigureCanvas(self.data_fig)
        if self.ok_cv_fig is None or self.ok_cv_canvas is None:
            try:
                self._attach_ok_cv_canvas()
            except Exception:
                pass

    def _build_rk_points_callback(self):
        if self.ml_ctrl is None:
            raise ValueError("Machine Learning controller is not initialized.")
        return self.ml_ctrl._build_points_dataframe_for_rf()

    def _build_rk_grid_callback(self, covariate_names):
        if self.ml_ctrl is None:
            raise ValueError("Machine Learning controller is not initialized.")
        return self.ml_ctrl._build_grid_dataframe_for_rf(covariate_names)

    def _write_rk_raster_callback(self, grid_df, grid_meta, target_name, pred_column, layer_title):
        """Write RK final predictions to GeoTIFF and add them to QGIS without depending on the RF writer."""
        try:
            if grid_df is None or grid_meta is None or pred_column not in grid_df.columns:
                return None

            xmin = float(grid_meta["xmin"])
            ymin = float(grid_meta["ymin"])
            xmax = float(grid_meta["xmax"])
            ymax = float(grid_meta["ymax"])
            n_cols = int(grid_meta["n_cols"])
            n_rows = int(grid_meta["n_rows"])
            pixel_size = float(grid_meta["pixel_size"])
            poly_layer = grid_meta["poly_layer"]

            raster_array = np.full((n_rows, n_cols), np.nan, dtype=np.float32)
            xs = grid_df["x"].to_numpy(dtype=float)
            ys = grid_df["y"].to_numpy(dtype=float)
            vals = grid_df[pred_column].to_numpy(dtype=float)

            for x, y, v in zip(xs, ys, vals):
                col = int((x - xmin) / pixel_size)
                row = int((ymax - y) / pixel_size)
                if 0 <= col < n_cols and 0 <= row < n_rows:
                    raster_array[row, col] = float(v)

            out_dir = self._ensure_output_dir() if self._should_export_raster() else tempfile.gettempdir()
            safe_var = "".join(ch if ch.isalnum() else "_" for ch in str(target_name))
            base_name = f"RK_{safe_var}_{uuid.uuid4().hex[:6]}.tif"
            out_path = os.path.join(out_dir, base_name)

            driver = gdal.GetDriverByName("GTiff")
            ds = driver.Create(out_path, n_cols, n_rows, 1, gdal.GDT_Float32)
            if ds is None:
                raise RuntimeError("Could not create GeoTIFF for Regression Kriging.")

            geotransform = (xmin, pixel_size, 0.0, ymax, 0.0, -pixel_size)
            ds.SetGeoTransform(geotransform)

            srs = osr.SpatialReference()
            srs.ImportFromWkt(poly_layer.crs().toWkt())
            ds.SetProjection(srs.ExportToWkt())

            nodata_value = -9999.0
            raster_array_to_write = np.where(np.isfinite(raster_array), raster_array, nodata_value)
            band = ds.GetRasterBand(1)
            band.WriteArray(raster_array_to_write)
            band.SetNoDataValue(nodata_value)
            band.FlushCache()
            ds.FlushCache()
            ds = None

            layer_name = f"Regression Kriging ({target_name})"
            raster_layer = self._create_output_raster_layer(out_path, layer_name)
            if not raster_layer.isValid():
                raise RuntimeError("RK raster was written but could not be loaded as a QGIS layer.")

            self._mark_temporary_layer(raster_layer, out_path)
            QgsProject.instance().addMapLayer(raster_layer)
            self.iface.messageBar().pushMessage(
                "Regression Kriging",
                f"RK raster created: {out_path}",
                level=0,
            )
            return out_path
        except Exception as e:
            try:
                self.iface.messageBar().pushWarning("Regression Kriging", f"Failed to export RK raster: {e}")
            except Exception:
                pass
            return None

    # ---------------------------------- Run -----------------------------------

    def run(self):
        if not self._ensure_project_saved():
            return
        self._ensure_output_dir()

        self.dlg = BestFitInterpolatorDialog(plugin_dir=self.plugin_dir, parent=self.iface.mainWindow())
        self._bind_ui_aliases()

        self.reset_plugin_state()
        self.load_layers()
        try:
            self._last_data_selection = (
                self.dlg.Points.currentText(),
                self.dlg.Points_2.currentText(),
                self.dlg.poly.currentText(),
            )
        except Exception:
            pass

        self.dlg.Points.currentIndexChanged.connect(self.update_variables)
        # Clear plots only when the data selection actually changes
        try:
            self.dlg.Points.currentIndexChanged.connect(self._on_data_selection_changed)
        except Exception:
            pass
        self.dlg.Points_2.currentIndexChanged.connect(self._on_variable_changed_for_kriging)
        try:
            self.dlg.Points_2.currentIndexChanged.connect(self._on_data_selection_changed)
        except Exception:
            pass
        try:
            self.dlg.poly.currentIndexChanged.connect(self._on_data_selection_changed)
        except Exception:
            pass
        if hasattr(self.dlg, 'LoadButton') and hasattr(self.dlg.LoadButton, 'clicked'):
            self.dlg.LoadButton.clicked.connect(self.plot_map_tab1)
        if hasattr(self.dlg, 'interpolateButton'):
            self.dlg.interpolateButton.clicked.connect(self.run_interpolation)
        if hasattr(self.dlg, 'btnRunCV'):
            self.dlg.btnRunCV.clicked.connect(self.run_cross_validation)

        # Kriging actions are handled by the dispatcher/controller; avoid double-connecting here

        self._attach_canvases()
        self._attach_data_canvas()
        self._attach_ok_cv_canvas()

        self._wire_deterministic_controls()
        self._wire_cv_controls()
        self._wire_ok_cv_controls()
        self._add_validation_auto_info_icons()
        self._activate_data_tab()
        self._rename_interpolation_tab()

        # Initialize Machine Learning tab controller
        try:
            self.ml_ctrl = MachineLearningTabController(self.dlg, self.iface)
        except Exception as e:
            try:
                self.iface.messageBar().pushWarning("Machine Learning", f"Failed to initialize ML tab: {e}")
            except Exception:
                pass

        try:
            if RegressionKrigingRFController is not None and self.ml_ctrl is not None:
                self.rk_ctrl = RegressionKrigingRFController(
                    self.dlg,
                    self.iface,
                    points_builder=self._build_rk_points_callback,
                    grid_builder=self._build_rk_grid_callback,
                    raster_writer=self._write_rk_raster_callback,
                )
        except Exception as e:
            self.rk_ctrl = None
            try:
                self.iface.messageBar().pushWarning("Regression Kriging", f"Failed to initialize RK tab: {e}")
            except Exception:
                pass

        self._add_validation_auto_info_icons()

        try:
            if FrameworkTabController is not None:
                self.framework_ctrl = FrameworkTabController(self.dlg, plugin=self)
                try:
                    self._sync_framework_from_current_data()
                except Exception:
                    pass
            elif _FRAMEWORK_IMPORT_ERROR:
                try:
                    self.iface.messageBar().pushWarning("Framework", f"Framework tab is not available: {_FRAMEWORK_IMPORT_ERROR}")
                except Exception:
                    pass
        except Exception as e:
            self.framework_ctrl = None
            try:
                self.iface.messageBar().pushWarning("Framework", f"Failed to initialize Framework tab: {e}")
            except Exception:
                pass

        # Ensure both interpolation tabs default to their first sub-tab
        try:
            if hasattr(self.dlg, 'detSubTabs') and self.dlg.detSubTabs is not None:
                self.dlg.detSubTabs.setCurrentIndex(0)
        except Exception:
            pass
        try:
            if hasattr(self.dlg, 'tabWidgetOK') and self.dlg.tabWidgetOK is not None:
                self.dlg.tabWidgetOK.setCurrentIndex(0)
        except Exception:
            pass

        self._connect_project_signals()
        self.dlg.finished.connect(self._disconnect_project_signals)

        # Kriging is handled on its tab by the dispatcher/controller. We still provide CV/export here.
        self.dlg.mainTabs.currentChanged.connect(self._on_main_tab_changed)

        self.dlg.show()

    # ---------------------------- Deterministic part ---------------------------

    def reset_plugin_state(self):
        self.dlg.Points.clear();    self.dlg.Points.addItem("")
        self.dlg.Points_2.clear();  self.dlg.Points_2.addItem("")
        self.dlg.poly.clear();      self.dlg.poly.addItem("")
        self._last_data_selection = (None, None, None)
        self._last_det_interpolation = None
        self._last_ok_interpolation = None
        if hasattr(self.dlg, 'manualNInput'):
            try:
                self.dlg.manualNInput.setValue(12)
            except (AttributeError, TypeError):
                self.dlg.manualNInput.setText("12")
        if hasattr(self.dlg, 'manualPInput'):
            try:
                self.dlg.manualPInput.setValue(2.0)
            except Exception:
                pass
        self._clear_det_validation_outputs()
        self._reset_moran_index_label()
        self._reset_data_crs_label()

    def load_layers(self):
        self._reset_moran_index_label()
        self._reset_data_crs_label()
        layers = QgsProject.instance().mapLayers().values()
        self.dlg.Points.clear();   self.dlg.Points.addItem("")
        self.dlg.Points_2.clear(); self.dlg.Points_2.addItem("")
        self.dlg.poly.clear();     self.dlg.poly.addItem("")
        added_points = set(); added_polygons = set()
        for layer in layers:
            if isinstance(layer, QgsRasterLayer):
                continue
            if isinstance(layer, QgsMapLayer):
                gt = layer.geometryType()
                if gt == QgsWkbTypes.PointGeometry or (QgsWkbTypes.isMultiType(layer.wkbType()) and gt == QgsWkbTypes.PointGeometry):
                    if layer.name() not in added_points:
                        self.dlg.Points.addItem(layer.name()); added_points.add(layer.name())
                elif gt == QgsWkbTypes.PolygonGeometry or (QgsWkbTypes.isMultiType(layer.wkbType()) and gt == QgsWkbTypes.PolygonGeometry):
                    if layer.name() not in added_polygons:
                        self.dlg.poly.addItem(layer.name()); added_polygons.add(layer.name())

    def update_variables(self):
        points_layer_name = self.dlg.Points.currentText()
        self.dlg.Points_2.clear(); self.dlg.Points_2.addItem("")
        if not points_layer_name:
            return
        layers = QgsProject.instance().mapLayersByName(points_layer_name)
        if not layers:
            return
        points_layer = layers[0]
        if points_layer and not points_layer.fields().isEmpty():
            # Allow user to pick any field (numeric check could be added if needed)
            for field in points_layer.fields():
                self.dlg.Points_2.addItem(field.name())
        try:
            current_label = self.dlg.mainTabs.tabText(self.dlg.mainTabs.currentIndex())
            if self._is_geostatistics_tab(current_label):
                if self.dlg.Points_2.currentIndex() <= 0 and self.dlg.Points_2.count() > 1:
                    self.dlg.Points_2.setCurrentIndex(1)
                self._update_ok_context()
        except Exception:
            pass

    def _on_variable_changed_for_kriging(self):
        """If the Geostatistics tab is active, update its context when the variable changes."""
        tab_widget = self.dlg.mainTabs
        current_label = tab_widget.tabText(tab_widget.currentIndex())
        if self._is_geostatistics_tab(current_label):
            self._update_ok_context()
        try:
            self._sync_framework_from_current_data()
        except Exception:
            pass

    @staticmethod
    def _is_geostatistics_tab(label: str) -> bool:
        """Return True only for the classic Geostatistics/OK tab, never for Regression Kriging."""
        text = (label or "").strip().lower()

        # Keep the classic geostatistics tab isolated from the Regression Kriging tab.
        # The previous logic matched any tab containing "kriging", which also captured
        # "Regression Kriging" and caused OK-specific context/refresh logic to run when
        # the user was actually working in RK.
        if "regression kriging" in text:
            return False
        if text in {"rk", "regression kriging"}:
            return False
        return ("geostat" in text) or (text == "kriging") or ("ordinary kriging" in text)

    # ------------------- Kriging tab context (pure Python) ---------------------

    def _update_ok_context(self):
        """Ensure the Kriging dispatcher/controller exists and has the current layer/field."""
        if getattr(self, "_suppress_data_change_events", False):
            return

        points_layer_name = self.dlg.Points.currentText()
        z_field = self.dlg.Points_2.currentText()
        if not points_layer_name or not z_field:
            return

        if OKDispatcherController is None:
            detail = _OK_DISPATCHER_IMPORT_ERROR or "Missing ok_dispatcher.py or one of its dependencies."
            self.iface.messageBar().pushCritical("Kriging", f"OKDispatcherController not available: {detail}")
            return

        if self.ok_ctrl is None:
            try:
                self.ok_ctrl = OKDispatcherController(self.iface, self.dlg, plugin_dir=self.plugin_dir, r_folder_path=None)
                try:
                    self.ok_ctrl.run_ok_cv_function = self.run_ok_cv
                except Exception:
                    pass
                if hasattr(self.dlg, 'tabKriging') and self.dlg.tabKriging is not None:
                    self.dlg.tabKriging.setEnabled(True)
            except Exception as e:
                self.iface.messageBar().pushWarning("Kriging", f"Failed to initialize Kriging dispatcher: {e}")
                self.ok_ctrl = None
                return

        layers = QgsProject.instance().mapLayersByName(points_layer_name)
        if not layers:
            return

        if hasattr(self.ok_ctrl, 'run_ok_cv_function'):
            self.ok_ctrl.run_ok_cv_function = self.run_ok_cv

        self.ok_ctrl.set_points_layer_and_field(layers[0], z_field)

    def _is_framework_tab(self, label: str) -> bool:
        text = (label or "").strip().lower()
        return "framework" in text

    def _sync_framework_from_current_data(self):
        """Push current Data-tab diagnostics into the Framework controller."""
        if self.framework_ctrl is None or not hasattr(self, 'dlg') or self.dlg is None:
            return

        points_layer_name = self.dlg.Points.currentText().strip() if hasattr(self.dlg, 'Points') else ""
        variable_name = self.dlg.Points_2.currentText().strip() if hasattr(self.dlg, 'Points_2') else ""
        polygon_name = self.dlg.poly.currentText().strip() if hasattr(self.dlg, 'poly') else ""
        pixel_size = self._get_pixel_size(default=0.01)

        if not points_layer_name or not variable_name:
            return

        layers = QgsProject.instance().mapLayersByName(points_layer_name)
        if not layers:
            return
        point_layer = layers[0]

        points_coords = []
        variable_values = []
        for feature in point_layer.getFeatures():
            geom = feature.geometry()
            if geom is None or geom.isEmpty():
                continue
            try:
                pt = geom.asPoint()
                val = float(feature[variable_name])
            except Exception:
                continue
            if np.isfinite(val):
                points_coords.append(pt)
                variable_values.append(val)

        if not points_coords or not variable_values:
            return

        moran_i = None
        moran_p = None
        spatial_pattern = "Not evaluated"
        try:
            moran_result = self._compute_moran_index_knn(points_coords, variable_values, k=8, n_permutations=199)
            if moran_result is not None:
                moran_i = moran_result.get("I")
                moran_p = moran_result.get("p")
                spatial_pattern = moran_result.get("pattern", spatial_pattern)
        except Exception:
            pass

        payload = {
            "variable_name": variable_name,
            "pixel_size": pixel_size,
            "sample_count": len(variable_values),
            "moran_i": moran_i,
            "moran_p_value": moran_p,
            "spatial_pattern": spatial_pattern,
            "points_layer_name": points_layer_name,
            "polygon_layer_name": polygon_name,
        }
        self.framework_ctrl.load_from_data_tab(payload)
        try:
            self.framework_ctrl.refresh_from_plugin_context()
        except Exception:
            pass

    def _on_main_tab_changed(self, index):
        """Handler for when the main tab (Data, Deterministic, Kriging, ML) changes."""
        if not hasattr(self, 'dlg') or self.dlg is None:
            return

        tab_widget = self.dlg.mainTabs
        current_text = tab_widget.tabText(index).lower()

        # When enter to Deterministic interpolation
        try:
            if "deterministic" in current_text or "interpolation" in current_text:
                det_tabs = getattr(self.dlg, 'detSubTabs', None)
                if det_tabs is not None and hasattr(det_tabs, 'setCurrentIndex'):
                    det_tabs.setCurrentIndex(0)
        except Exception:
            pass

        # When enter to  Kriging / Geostatistics
        if self._is_geostatistics_tab(current_text):
            try:
                self._auto_select_first_points_and_field()
            except Exception:
                pass
            self._update_ok_context()
            self._attach_ok_cv_canvas()
            try:
                ok_tabs = getattr(self.dlg, 'tabWidgetOK', None)
                if ok_tabs is not None and hasattr(ok_tabs, 'setCurrentIndex'):
                    ok_tabs.setCurrentIndex(0)
            except Exception:
                pass

        if self._is_framework_tab(current_text):
            try:
                framework_tabs = getattr(self.dlg, "frameworkSubTabs", None)
                if framework_tabs is not None and hasattr(framework_tabs, "setCurrentIndex"):
                    framework_tabs.setCurrentIndex(0)
            except Exception:
                pass
            try:
                self._sync_framework_from_current_data()
            except Exception:
                pass

        # When enter to Machine Learning
        if "machine" in current_text:
            # 1) Force to start in 0 
            try:
                from qgis.PyQt.QtWidgets import QTabWidget
                for tw in self.dlg.findChildren(QTabWidget):
                    
                    if tw is tab_widget:
                        continue
                    try:
                        tw.setCurrentIndex(0)
                    except Exception:
                        pass
            except Exception:
                pass

            # 2) Sincronize pixel size with ML
            try:
                if getattr(self, 'ml_ctrl', None) is not None:
                    
                    self.ml_ctrl._sync_pixel_size_from_data(set_target_default=False)
            except Exception:
                pass



    def _auto_select_first_points_and_field(self):
        """If no points layer/variable selected, pick the first available ones to enable Kriging init."""
        # Points layer
        try:
            if hasattr(self.dlg, 'Points') and (not self.dlg.Points.currentText()):
                # Find first point layer in project
                for lyr in QgsProject.instance().mapLayers().values():
                    if isinstance(lyr, QgsMapLayer):
                        gt = lyr.geometryType()
                        if gt == QgsWkbTypes.PointGeometry or (QgsWkbTypes.isMultiType(lyr.wkbType()) and gt == QgsWkbTypes.PointGeometry):
                            idx = self.dlg.Points.findText(lyr.name())
                            if idx >= 0:
                                self.dlg.Points.setCurrentIndex(idx)
                                break
                # Refresh variables after setting points
                self.update_variables()
        except Exception:
            pass
        # Variable (field)
        try:
            if hasattr(self.dlg, 'Points_2') and (not self.dlg.Points_2.currentText()):
                if self.dlg.Points_2.count() > 1:
                    # Index 0 is empty string; choose first real field
                    self.dlg.Points_2.setCurrentIndex(1)
        except Exception:
            pass

    # ---------------------------- Data helpers ---------------------------------

    def filter_incomplete_data(self, points_coords, variable_values):
        filtered_coords = []; filtered_values = []; removed = 0
        for coord, value in zip(points_coords, variable_values):
            if (coord is not None and value is not None and
                not isinstance(value, QVariant) and not np.isnan(value)):
                filtered_coords.append(coord); filtered_values.append(value)
            else:
                removed += 1
        if removed > 0:
            self.iface.messageBar().pushMessage(
                "Warning", f"Removed {removed} rows with incomplete or invalid data.", level=1
            )
        return filtered_coords, filtered_values

    def _dedupe_training_by_xy_keep_first(self, x, y, z):
        """Return one TPS training sample per exact XY coordinate, keeping the first row."""
        x = np.asarray(x, dtype=float).ravel()
        y = np.asarray(y, dtype=float).ravel()
        z = np.asarray(z, dtype=float).ravel()
        if x.size != y.size or x.size != z.size or z.size <= 1:
            return x, y, z, 0, 0

        xy = np.column_stack([x, y])
        _, first_idx, counts = np.unique(xy, axis=0, return_index=True, return_counts=True)
        duplicate_groups = int(np.count_nonzero(counts > 1))
        duplicate_rows = int(np.sum(counts - 1))
        if duplicate_rows <= 0:
            return x, y, z, 0, 0

        keep = np.sort(first_idx)
        return x[keep], y[keep], z[keep], duplicate_rows, duplicate_groups

    def _confirm_tps_duplicate_handling(self, duplicate_rows, duplicate_groups):
        reply = QMessageBox.question(
            self.dlg,
            "TPS duplicate locations",
            (
                "TPS requires one sample per coordinate.\n\n"
                f"{duplicate_rows} repeated samples were found in "
                f"{duplicate_groups} duplicated locations.\n"
                "Continue using only the first sample at each repeated coordinate?\n\n"
                "The original layer will not be modified."
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        return reply == QMessageBox.Yes

    def _prepare_tps_training_data(self, x, y, z, context_title="TPS"):
        x2, y2, z2, duplicate_rows, duplicate_groups = self._dedupe_training_by_xy_keep_first(x, y, z)
        if duplicate_rows <= 0:
            return np.asarray(x, dtype=float).ravel(), np.asarray(y, dtype=float).ravel(), np.asarray(z, dtype=float).ravel()

        if not self._confirm_tps_duplicate_handling(duplicate_rows, duplicate_groups):
            self.iface.messageBar().pushWarning(
                context_title,
                "TPS canceled because duplicate locations were not accepted.",
            )
            return None

        self.iface.messageBar().pushMessage(
            context_title,
            (
                f"Using {z2.size} unique locations for TPS; "
                f"{duplicate_rows} repeated samples ignored for this run only."
            ),
            level=1,
        )
        return x2, y2, z2

    def _record_det_interpolation(
        self,
        method,
        points_layer_name,
        variable_name,
        polygon_layer_name,
        pixel_size,
        training_data,
        **params,
    ):
        x, y, z = finite_training_arrays(*training_data)
        self._last_det_interpolation = {
            "method": method,
            "points_layer": points_layer_name,
            "variable": variable_name,
            "polygon_layer": polygon_layer_name,
            "pixel_size": float(pixel_size),
            "training_data": {
                "x": np.asarray(x, dtype=float).copy(),
                "y": np.asarray(y, dtype=float).copy(),
                "z": np.asarray(z, dtype=float).copy(),
            },
            "params": dict(params),
        }

    def _get_last_det_interpolation_for_validation(self):
        state = getattr(self, "_last_det_interpolation", None)
        if not state:
            self.iface.messageBar().pushMessage(
                "Validation",
                "Run deterministic interpolation first, then run validation.",
                level=2,
            )
            return None

        return state

    def _record_ok_interpolation(
        self,
        backend,
        points_layer_name,
        variable_name,
        polygon_layer_name,
        pixel_size,
        sample_xyz,
        model,
        nugget,
        psill,
        var_range,
        reml_fit=None,
    ):
        sample_xyz = np.asarray(sample_xyz, dtype=float).copy()
        if sample_xyz.ndim != 2 or sample_xyz.shape[1] != 3:
            raise ValueError("Kriging training data must have x, y, and value columns.")
        self._last_ok_interpolation = {
            "backend": str(backend),
            "points_layer": points_layer_name,
            "variable": variable_name,
            "polygon_layer": polygon_layer_name,
            "pixel_size": float(pixel_size),
            "sample_xyz": sample_xyz,
            "model": str(model),
            "nugget": float(nugget),
            "psill": float(psill),
            "var_range": float(var_range),
            "reml_fit": reml_fit,
        }

    def _get_last_ok_interpolation_for_validation(self):
        state = getattr(self, "_last_ok_interpolation", None)
        if not state:
            self.iface.messageBar().pushMessage(
                "Kriging validation",
                "Run Ordinary Kriging interpolation first, then run validation.",
                level=2,
            )
            return None
        return state

    def _on_data_selection_changed(self, *_):
        """
        Clear plots only when the data tab selections change (points/variable/polygon).
        This prevents the Data preview from being reset just by switching tabs.
        """
        try:
            current = (
                self.dlg.Points.currentText(),
                self.dlg.Points_2.currentText(),
                self.dlg.poly.currentText(),
            )
        except Exception:
            return

        if getattr(self, "_suppress_data_change_events", False):
            self._last_data_selection = current
            return

        if current != getattr(self, "_last_data_selection", None):
            self._last_det_interpolation = None
            self._last_ok_interpolation = None
            self._clear_all_plots(reset_framework=False)
            self._clear_ok_validation_outputs()
            self._reset_ok_validation_canvas()
            try:
                current_label = self.dlg.mainTabs.tabText(self.dlg.mainTabs.currentIndex())
                if self._is_geostatistics_tab(current_label):
                    self._update_ok_context()
            except Exception:
                pass
            try:
                if self.framework_ctrl is not None and hasattr(self.framework_ctrl, "reset_for_data_change"):
                    self.framework_ctrl.reset_for_data_change(keep_data_context=True)
                else:
                    self._sync_framework_from_current_data()
            except Exception:
                pass
        self._last_data_selection = current

    # ---------------------------- Data tab plotting ----------------------------
    @staticmethod
    def _apply_million_formatter(ax):
        """Keep normal numeric axes but improve readability with smaller labels and fewer ticks."""
        try:
            from matplotlib.ticker import MaxNLocator
            ax.xaxis.set_major_locator(MaxNLocator(nbins=6))
            ax.yaxis.set_major_locator(MaxNLocator(nbins=6))
        except Exception:
            pass
        ax.tick_params(axis='both', labelsize=8)
        # Keep plain labels without 10^6 scaling
        ax.set_xlabel("X")
        ax.set_ylabel("Y")

    def _reset_moran_index_label(self):
        """Reset the Moran index label on the Data tab."""
        try:
            if hasattr(self.dlg, "lblMoranIndexValue") and self.dlg.lblMoranIndexValue is not None:
                self.dlg.lblMoranIndexValue.setText("-")
        except Exception:
            pass

    def _reset_data_crs_label(self):
        """Reset the Data tab CRS label."""
        try:
            if hasattr(self.dlg, "lblDataCrsValue") and self.dlg.lblDataCrsValue is not None:
                self.dlg.lblDataCrsValue.setText("CRS:")
        except Exception:
            pass

    def _crs_display_name(self, crs):
        """Return a compact CRS display name."""
        try:
            authid = str(crs.authid() or "").strip()
        except Exception:
            authid = ""
        try:
            desc = str(crs.description() or "").strip()
        except Exception:
            desc = ""
        if authid and desc:
            return f"{authid} - {desc}"
        return authid or desc or "Unknown CRS"

    def _crs_uses_meter_units(self, crs) -> bool:
        """Return True when the CRS map units are meters."""
        try:
            unit = crs.mapUnits()
            meter_units = []
            for name in ("DistanceMeters", "Meters"):
                if hasattr(QgsUnitTypes, name):
                    meter_units.append(getattr(QgsUnitTypes, name))
            if meter_units and unit in meter_units:
                return True
            try:
                unit_name = str(QgsUnitTypes.toString(unit)).strip().lower()
            except Exception:
                unit_name = str(unit).strip().lower()
            return unit_name in {"meter", "meters", "metre", "metres", "m"}
        except Exception:
            return False

    def _update_data_crs_label_and_warn(self, layer):
        """Show selected data CRS and warn when its units are not meters."""
        try:
            crs = layer.crs() if layer is not None and hasattr(layer, "crs") else None
            if crs is None or not crs.isValid():
                self._reset_data_crs_label()
                return
            crs_name = self._crs_display_name(crs)
            if hasattr(self.dlg, "lblDataCrsValue") and self.dlg.lblDataCrsValue is not None:
                self.dlg.lblDataCrsValue.setText(f"CRS: {crs_name}")
            if not self._crs_uses_meter_units(crs):
                try:
                    key = f"{layer.id()}::{crs.authid()}"
                except Exception:
                    key = crs_name
                if key != getattr(self, "_last_planar_crs_warning_key", None):
                    self._last_planar_crs_warning_key = key
                    QMessageBox.warning(
                        self.dlg,
                        "Metric CRS required",
                        "The selected point layer CRS does not use meter units.\n\n"
                        f"Current CRS: {crs_name}\n\n"
                        "Distance-based interpolation and Moran's Index should be run with a projected CRS in meters."
                    )
        except Exception:
            pass

    def _set_moran_index_label(self, moran_i, pattern=None, p_value=None):
        """Update the Moran index label with value, p-value, and classification."""
        try:
            if not hasattr(self.dlg, "lblMoranIndexValue") or self.dlg.lblMoranIndexValue is None:
                return

            if moran_i is None or not np.isfinite(moran_i):
                self.dlg.lblMoranIndexValue.setText("-")
                return

            txt = f"Moran's Index: {float(moran_i):.4f}"

            if p_value is not None and np.isfinite(float(p_value)):
                txt += f" | p: {float(p_value):.4f}"
            else:
                txt += " | p: -"

            if pattern:
                txt += f" ({pattern})"

            self.dlg.lblMoranIndexValue.setText(txt)
        except Exception:
            pass

    def _normal_cdf(self, z):
        """Standard normal CDF without external dependencies."""
        return 0.5 * (1.0 + math.erf(float(z) / math.sqrt(2.0)))

    def _compute_moran_index_knn(self, points_coords, variable_values, k=8, n_permutations=199, random_seed=20):
        """
        Compute global Moran's I using KNN weights and classify the pattern as
        Clustered, Random, or Dispersed.

        Notes
        -----
        - Neighbor structure: KNN with k=8
        - Weights: row-standardized binary weights
        - Significance: permutation-based z-score and p-value
        """
        coords = np.array([(pt.x(), pt.y()) for pt in points_coords], dtype=float)
        values = np.asarray(variable_values, dtype=float)

        mask = np.isfinite(coords).all(axis=1) & np.isfinite(values)
        coords = coords[mask]
        values = values[mask]

        n = values.size
        if n < 3:
            return None

        k = max(1, min(int(k), n - 1))

        diff_x = coords[:, 0][:, None] - coords[:, 0][None, :]
        diff_y = coords[:, 1][:, None] - coords[:, 1][None, :]
        dist2 = diff_x * diff_x + diff_y * diff_y
        np.fill_diagonal(dist2, np.inf)
        neighbor_idx = np.argpartition(dist2, kth=k - 1, axis=1)[:, :k]

        x_dev = values - float(np.mean(values))
        den = float(np.sum(x_dev ** 2))
        if den <= 0:
            return {
                "I": 0.0,
                "z": 0.0,
                "p": 1.0,
                "pattern": "Random",
                "k": k,
                "n": n,
            }

        neighbor_mean = np.mean(x_dev[neighbor_idx], axis=1)
        observed_i = float(np.sum(x_dev * neighbor_mean) / den)

        rng = np.random.default_rng(random_seed)
        sim_i = np.empty(int(max(19, n_permutations)), dtype=float)
        for b in range(sim_i.size):
            perm = rng.permutation(x_dev)
            perm_neighbor_mean = np.mean(perm[neighbor_idx], axis=1)
            sim_i[b] = float(np.sum(perm * perm_neighbor_mean) / den)

        sim_mean = float(np.mean(sim_i))
        sim_std = float(np.std(sim_i, ddof=1)) if sim_i.size > 1 else 0.0
        if sim_std > 0:
            z_score = float((observed_i - sim_mean) / sim_std)
            p_value = float(2.0 * (1.0 - self._normal_cdf(abs(z_score))))
        else:
            z_score = 0.0
            p_value = 1.0

        if z_score > 1.96:
            pattern = "Clustered"
        elif z_score < -1.96:
            pattern = "Dispersed"
        else:
            pattern = "Random"

        return {
            "I": observed_i,
            "z": z_score,
            "p": p_value,
            "pattern": pattern,
            "k": k,
            "n": n,
        }

    def plot_map_tab1(self):
        self._ensure_canvases_attached()
        points_layer_name = self.dlg.Points.currentText()
        polygon_layer_name = self.dlg.poly.currentText()
        variable_name = self.dlg.Points_2.currentText()
        if not polygon_layer_name:
            self._reset_moran_index_label()
            self._reset_data_crs_label()
            QMessageBox.warning(
                self.dlg,
                "Polygon required",
                "Please load and select a polygon layer in the Data tab.",
            )
            return
        if not points_layer_name or not variable_name:
            self._reset_moran_index_label()
            self._reset_data_crs_label()
            self.iface.messageBar().pushMessage("Error","Please select a point layer, polygon layer, and variable.", level=3)
            return
        points_matches = QgsProject.instance().mapLayersByName(points_layer_name)
        polygon_matches = QgsProject.instance().mapLayersByName(polygon_layer_name)
        if not polygon_matches:
            self._reset_moran_index_label()
            self._reset_data_crs_label()
            QMessageBox.warning(
                self.dlg,
                "Polygon required",
                "The selected polygon layer is not loaded in QGIS. Please load it and try again.",
            )
            return
        if not points_matches:
            self._reset_moran_index_label()
            self._reset_data_crs_label()
            self.iface.messageBar().pushMessage("Error","Selected point layer is not loaded in QGIS.", level=3)
            return
        points_layer = points_matches[0]
        polygon_layer = polygon_matches[0]
        self._update_data_crs_label_and_warn(points_layer)

        polygon_coords = []
        for feature in polygon_layer.getFeatures():
            geometry = feature.geometry()
            if geometry.isMultipart():
                for part in geometry.asMultiPolygon():
                    for ring in part:
                        polygon_coords.extend([(pt.x(), pt.y()) for pt in ring])
            else:
                for ring in geometry.asPolygon():
                    polygon_coords.extend([(pt.x(), pt.y()) for pt in ring])
        if not polygon_coords:
            self._reset_moran_index_label()
            QMessageBox.warning(
                self.dlg,
                "Invalid polygon",
                "No valid coordinates were found in the selected polygon layer.",
            )
            return

        points_coords = []; variable_values = []
        for feature in points_layer.getFeatures():
            geom = feature.geometry()
            if geom.isEmpty(): continue
            points_coords.append(geom.asPoint())
            val = feature[variable_name]
            try: val = float(val)
            except Exception: val = None
            variable_values.append(val)

        points_coords, variable_values = self.filter_incomplete_data(points_coords, variable_values)
        if not points_coords or not variable_values:
            self._reset_moran_index_label()
            self.iface.messageBar().pushMessage("Error","No valid points or values found after filtering.", level=3)
            return

        try:
            moran_result = self._compute_moran_index_knn(points_coords, variable_values, k=8, n_permutations=199)
            if moran_result is not None:
                self._set_moran_index_label(moran_result.get("I"), moran_result.get("pattern"), moran_result.get("p"))
            else:
                self._reset_moran_index_label()
        except Exception:
            self._reset_moran_index_label()

        if self.data_fig is None or self.data_canvas is None:
            self._attach_data_canvas()

        self.data_fig.clear()
        ax = self.data_fig.add_subplot(111)
        ax.set_title("Points & Polygon (Data tab)")
        self._apply_million_formatter(ax)

        x_poly, y_poly = zip(*polygon_coords)
        ax.plot(x_poly, y_poly, lw=1)

        x_points, y_points = zip(*[(p.x(), p.y()) for p in points_coords])
        sc = ax.scatter(x_points, y_points, c=variable_values, cmap='viridis', s=40, edgecolor='k', alpha=1)
        cbar = self.data_fig.colorbar(sc, ax=ax, orientation='vertical')
        cbar.set_label(f"'{variable_name}'")
        self.data_canvas.draw()

    # ---------------------------- Validation helpers ---------------------------

    @staticmethod
    def _rmse(obs, pred):
        obs = np.asarray(obs, dtype=float)
        pred = np.asarray(pred, dtype=float)
        return float(np.sqrt(np.nanmean((obs - pred) ** 2)))

    @staticmethod
    def _rmse_pct(obs, pred):
        obs = np.asarray(obs, dtype=float)
        rmse = BestFitInterpolator._rmse(obs, pred)
        mu = float(np.nanmean(obs))
        if not np.isfinite(mu) or abs(mu) < 1e-12:
            return float('nan')
        return float(rmse / mu * 100.0)

    @staticmethod
    def _mae(obs, pred):
        o = np.asarray(obs, dtype=float)
        p = np.asarray(pred, dtype=float)
        return float(np.nanmean(np.abs(o - p)))

    @staticmethod
    def _r2(obs, pred):
        o = np.asarray(obs, dtype=float)
        p = np.asarray(pred, dtype=float)
        mask = np.isfinite(o) & np.isfinite(p)
        if mask.sum() < 2: return float('nan')
        o = o[mask]; p = p[mask]
        ss_res = float(np.sum((o - p) ** 2))
        ss_tot = float(np.sum((o - np.mean(o)) ** 2))
        if ss_tot <= 0: return float('nan')
        return float(1.0 - ss_res / ss_tot)

    @staticmethod
    def _pearson_r(obs, pred):
        o = np.asarray(obs, dtype=float)
        p = np.asarray(pred, dtype=float)
        mask = np.isfinite(o) & np.isfinite(p)
        if mask.sum() < 2: return float('nan')
        o = o[mask]; p = p[mask]
        cov = float(np.nanmean((o - np.nanmean(o)) * (p - np.nanmean(p))))
        so = float(np.nanstd(o)); sp = float(np.nanstd(p))
        if so <= 0 or sp <= 0: return float('nan')
        return float(cov / (so * sp))

    @staticmethod
    def _lccc(obs, pred):
        o = np.asarray(obs, dtype=float)
        p = np.asarray(pred, dtype=float)
        mask = np.isfinite(o) & np.isfinite(p)
        if mask.sum() < 2:
            return float('nan')
        o = o[mask]
        p = p[mask]
        mu_o = float(np.mean(o)); mu_p = float(np.mean(p))
        std_o = float(np.std(o)); std_p = float(np.std(p))
        cov = float(np.mean((o - mu_o) * (p - mu_p)))
        denom = std_o ** 2 + std_p ** 2 + (mu_o - mu_p) ** 2
        if not np.isfinite(denom) or abs(denom) < 1e-12:
            return float('nan')
        return float((2.0 * cov) / denom)

    def _update_metrics_labels(self, rmse_value, lccc_value,
                               rmse_pct=None, r2=None, mae=None, pearson_r=None):
        if hasattr(self.dlg, "valRMSE"):
            self.dlg.valRMSE.setText(f"{rmse_value:.3f}" if np.isfinite(rmse_value) else "â€”")
        if hasattr(self.dlg, "valLCCC"):
            self.dlg.valLCCC.setText(f"{lccc_value:.3f}" if np.isfinite(lccc_value) else "â€”")
        if hasattr(self.dlg, "valRMSEpct"):
            self.dlg.valRMSEpct.setText(f"{rmse_pct:.2f}%" if (rmse_pct is not None and np.isfinite(rmse_pct)) else "â€”")
        if hasattr(self.dlg, "valR2"):
            self.dlg.valR2.setText(f"{r2:.3f}" if (r2 is not None and np.isfinite(r2)) else "â€”")
        if hasattr(self.dlg, "valMAE"):
            self.dlg.valMAE.setText(f"{mae:.3f}" if (mae is not None and np.isfinite(mae)) else "â€”")
        if hasattr(self.dlg, "valPearsonR"):
            self.dlg.valPearsonR.setText(f"{pearson_r:.3f}" if (pearson_r is not None and np.isfinite(pearson_r)) else "â€”")

        # Mirror into valRMSE_2 if present (extra RMSE%)
        if hasattr(self.dlg, "valRMSE_2"):
            if rmse_pct is not None and np.isfinite(rmse_pct):
                self.dlg.valRMSE_2.setText(f"{rmse_pct:.2f}%")
            else:
                self.dlg.valRMSE_2.setText("â€”")

    def _clear_ok_validation_outputs(self):
        for name in ("valOKRMSE", "valOKRMSEpct", "valOKLCCC", "valOKR2", "valOKMAE", "valOKPearsonR"):
            try:
                widget = getattr(self.dlg, name, None)
                if widget is not None and hasattr(widget, "setText"):
                    widget.setText("--")
            except Exception:
                pass
        try:
            if self.ok_cv_fig is not None:
                self.ok_cv_fig.clear()
                if self.ok_cv_canvas is not None:
                    self.ok_cv_canvas.draw_idle()
        except Exception:
            pass

    def _reset_ok_validation_canvas(self):
        try:
            if self.ok_cv_canvas is not None:
                self.ok_cv_canvas.setParent(None)
                self.ok_cv_canvas.deleteLater()
        except Exception:
            pass
        try:
            if self.ok_cv_fig is not None:
                self.ok_cv_fig.clear()
        except Exception:
            pass
        self.ok_cv_canvas = None
        self.ok_cv_fig = None
        self._attach_ok_cv_canvas()

    def _plot_validation_scatter(self, obs, pred, fig=None, canvas=None, title="Observed vs Predicted"):
        """Generic scatter for CV; unified styling for all tabs."""
        if fig is None or canvas is None:
            self._ensure_canvases_attached()
            fig = self.det_val_fig
            canvas = self.det_val_canvas

        fig.clear()
        ax = fig.add_subplot(111)
        try:
            fig.subplots_adjust(left=0.12, right=0.97, bottom=0.14, top=0.96)
        except Exception:
            pass

        valid_mask = np.isfinite(obs) & np.isfinite(pred)
        obs_valid = np.asarray(obs)[valid_mask]
        pred_valid = np.asarray(pred)[valid_mask]

        if len(obs_valid) >= 1 and len(pred_valid) >= 1:
            vmin = float(min(np.min(obs_valid), np.min(pred_valid)))
            vmax = float(max(np.max(obs_valid), np.max(pred_valid)))
        else:
            vmin, vmax = 0.0, 1.0
        if not np.isfinite(vmin) or not np.isfinite(vmax) or vmin == vmax:
            vmin, vmax = 0.0, 1.0

        pad = 0.02 * (vmax - vmin if vmax > vmin else 1.0)
        vmin -= pad
        vmax += pad

        if len(obs_valid) < 2:
            ax.scatter(obs, pred, s=18, alpha=0.9, facecolors='none', edgecolors='black')
        else:
            ax.scatter(obs_valid, pred_valid, s=18, alpha=0.9, facecolors='none', edgecolors='black', label='Data')
            ax.plot([vmin, vmax], [vmin, vmax], '-', color='black', linewidth=1.0, label='1:1')
            m, b = np.polyfit(obs_valid, pred_valid, 1)
            ax.plot([vmin, vmax], [m * vmin + b, m * vmax + b], '-', color='#d62728', linewidth=1.0, label='Fit')
            ax.legend(loc='upper left', frameon=False, fontsize=8, handlelength=1.8, borderaxespad=0.25)

        ax.set_xlim(vmin, vmax)
        ax.set_ylim(vmin, vmax)
        try:
            ax.set_box_aspect(1)
        except Exception:
            ax.set_aspect('equal', adjustable='box')

        ax.grid(True, linestyle='--', linewidth=0.5, alpha=0.6)
        ax.tick_params(axis='both', labelsize=7)
        ax.set_xlabel("Observed", fontsize=8)
        ax.set_ylabel("Predicted", fontsize=8)

        canvas.draw_idle()

    def _clear_all_plots(self, reset_framework: bool = True):
        """Clear interpolation, validation, and kriging plots when data/variable changes."""
        # Deterministic canvases
        try:
            if self.det_interp_fig is not None and self.det_interp_canvas is not None:
                self.det_interp_fig.clear(); self.det_interp_canvas.draw_idle()
        except Exception:
            pass
        try:
            if self.det_val_fig is not None and self.det_val_canvas is not None:
                self.det_val_fig.clear(); self.det_val_canvas.draw_idle()
        except Exception:
            pass
        self._clear_det_validation_outputs()
        # Data canvas
        try:
            if self.data_fig is not None and self.data_canvas is not None:
                self.data_fig.clear(); self.data_canvas.draw_idle()
        except Exception:
            pass
        # Kriging CV
        try:
            if self.ok_cv_fig is not None and self.ok_cv_canvas is not None:
                self.ok_cv_fig.clear(); self.ok_cv_canvas.draw_idle()
        except Exception:
            pass
        # Kriging controller plots (variogram/map)
        try:
            if self.ok_ctrl is not None:
                self.ok_ctrl.clear_plots()
        except Exception:
            pass
        try:
            if self.ml_ctrl is not None and hasattr(self.ml_ctrl, "reset_for_data_change"):
                self.ml_ctrl.reset_for_data_change()
            elif self.ml_ctrl is not None and hasattr(self.ml_ctrl, "clear_plots"):
                self.ml_ctrl.clear_plots()
        except Exception:
            pass
        try:
            if self.rk_ctrl is not None and hasattr(self.rk_ctrl, "clear_plots"):
                self.rk_ctrl.clear_plots()
        except Exception:
            pass
        if reset_framework:
            try:
                if self.framework_ctrl is not None and hasattr(self.framework_ctrl, "reset_for_data_change"):
                    self.framework_ctrl.reset_for_data_change(keep_data_context=False)
            except Exception:
                pass
        self._reset_moran_index_label()

    # ---------------------------- CV folds generator ---------------------------

    def _decide_auto_cv(self, n: int):
        """Return (mode, k) for AUTO policy based on n."""
        if n <= 100:
            return self.CV_LOOCV, None
        elif n <= 1000:
            return self.CV_KFOLD, 10
        else:
            return self.CV_KFOLD, 5

    def _make_kfold_indices(self, n: int, k: int):
        """Create K roughly equal folds of indices 0..n-1 (random shuffle)."""
        idx = list(range(n))
        random.Random(20).shuffle(idx)
        folds = []
        base, rem = divmod(n, k)
        start = 0
        for i in range(k):
            size = base + (1 if i < rem else 0)
            folds.append(idx[start:start+size])
            start += size
        return folds

    # ---------------------------- Cross-validation (Det) -----------------------

    def run_cross_validation(self):
        """Run CV (LOOCV or K-fold) for the selected deterministic method."""
        self._clear_det_validation_outputs()
        self._ensure_canvases_attached()

        det_state = self._get_last_det_interpolation_for_validation()
        if det_state is None:
            return
        det_method = det_state.get("method")
        det_params = det_state.get("params", {})
        training_data = det_state.get("training_data") or {}
        try:
            x, y, z = finite_training_arrays(
                training_data.get("x", []),
                training_data.get("y", []),
                training_data.get("z", []),
            )
        except Exception as exc:
            QMessageBox.warning(
                self.dlg,
                "Validation",
                f"The saved interpolation data are unavailable. Run interpolation again.\n\n{format_shape_error(exc)}",
            )
            return
        using_tps = (det_method == "TPS")
        if using_tps:
            prepared = self._prepare_tps_training_data(x, y, z, "Validation")
            if prepared is None:
                return
            x, y, z = prepared
        n = len(z)
        if n < 10:
            self.iface.messageBar().pushMessage(
                "Error",
                "At least 10 valid samples are required for deterministic validation.",
                level=3,
            )
            return

        # Respect the validation selector for all deterministic methods.
        mode = self._get_cv_mode()
        k = self._read_numeric_from_widget(self.spin_k, cast=int, default=10)
        if mode == self.CV_AUTO:
            mode, k_auto = self._decide_auto_cv(n)
            if k_auto is not None:
                k = k_auto

        # Build folds
        if mode == self.CV_LOOCV:
            folds = [[i] for i in range(n)]
        else:
            k = max(2, min(int(k), n))
            folds = self._make_kfold_indices(n, k)

        preds = np.full(n, np.nan, dtype=float)

        # Determine method params
        if using_tps and not _HAS_TPS:
            self.iface.messageBar().pushMessage("Error","TPS is selected but Thin_plate_spline.py was not found or failed to import.", level=3)
            return

        if not using_tps:
            p_value = det_params.get("p")
            n_value = det_params.get("n")
            if p_value is None or n_value is None:
                self.iface.messageBar().pushMessage(
                    "Validation",
                    "The last IDW interpolation has no saved p/n parameters. Run interpolation again first.",
                    level=2,
                )
                return
            p_value = float(p_value)
            n_value = int(n_value)
        else:
            epsilon_value = float(det_params.get("epsilon", 1e-4))

        # Run CV
        for test_idx_list in folds:
            mask = np.ones(n, dtype=bool)
            mask[test_idx_list] = False
            if mask.sum() < 1:
                continue
            test_idx = np.asarray(test_idx_list, dtype=int)
            train_xy = np.column_stack([x[mask], y[mask]])
            test_xy = ensure_xy_2d(np.column_stack([x[test_idx], y[test_idx]]), "validation coordinates")
            train_values = ensure_values_1d(z[mask], "training values")

            if using_tps:
                try:
                    pi = tps_interpolation(
                        train_xy[:, 0], train_xy[:, 1], train_values,
                        test_xy[:, 0], test_xy[:, 1],
                        epsilon=epsilon_value,
                    )
                    preds[test_idx] = np.asarray(pi, dtype=float).ravel()
                except Exception as e:
                    self.iface.messageBar().pushWarning("Validation", format_shape_error(e, train_xy, test_xy, train_values))
            else:
                n_eff = max(1, min(int(n_value), int(mask.sum())))
                pi = idw_interpolation(
                    train_xy[:, 0], train_xy[:, 1], train_values,
                    test_xy[:, 0], test_xy[:, 1],
                    p_value, n_eff
                )
                preds[test_idx] = np.asarray(pi, dtype=float).ravel()

        # Metrics + plot
        rmse = self._rmse(z, preds)
        lccc = self._lccc(z, preds)
        rmse_pct = self._rmse_pct(z, preds)
        r2 = self._r2(z, preds)
        mae = self._mae(z, preds)
        pearson_r = self._pearson_r(z, preds)

        self._update_metrics_labels(rmse, lccc, rmse_pct, r2, mae, pearson_r)
        self._plot_validation_scatter(z, preds, fig=self.det_val_fig, canvas=self.det_val_canvas,
                                      title="Observed vs Predicted (Deterministic CV)")

        self.iface.messageBar().pushMessage(
            "Validation",
            f"CV finished. RMSE={rmse:.3f}, RMSE%={(rmse_pct if np.isfinite(rmse_pct) else float('nan')):.2f}%, "
            f"MAE={mae:.3f}, RÂ²={(r2 if np.isfinite(r2) else float('nan')):.3f}, "
            f"Pearson r={(pearson_r if np.isfinite(pearson_r) else float('nan')):.3f}, "
            f"LCCC={(lccc if np.isfinite(lccc) else float('nan')):.3f}",
            level=0
        )

    # ---------------------------- Kriging CV (OK) ------------------------------

    def _read_ok_params(self):
        """Read OK variogram params from UI. Returns (model, nugget, psill, var_range)."""
        if getattr(self, "ok_ctrl", None) is not None and hasattr(self.ok_ctrl, "_get_selected_model"):
            model = self.ok_ctrl._get_selected_model()
        else:
            model = getattr(self.dlg, 'cmbOKModel', None).currentText() if hasattr(self.dlg, 'cmbOKModel') else "Sph"
            if str(model or "").strip().lower().startswith("auto"):
                model = "exponential"
        nugget = self._read_numeric_from_widget(getattr(self.dlg, 'spinOKNugget', None), cast=float, default=0.0)
        psill  = self._read_numeric_from_widget(getattr(self.dlg, 'spinOKPsill',  None), cast=float, default=1.0)
        var_range = self._read_numeric_from_widget(getattr(self.dlg, 'spinOKRange', None), cast=float, default=1.0)
        return model, nugget, psill, var_range

    def run_ok_cv(self):
        """Run LOOCV/K-Fold CV for Ordinary Kriging and plot into CV_Kriging_widget."""
        self._clear_ok_validation_outputs()
        self._reset_ok_validation_canvas()
        self._ensure_canvases_attached()
        if self.ok_cv_fig is None or self.ok_cv_canvas is None:
            self._attach_ok_cv_canvas()
        ok_state = self._get_last_ok_interpolation_for_validation()
        if ok_state is None:
            return
        if ok_state.get("backend") == "REML":
            return self.run_ok_cv_reml(ok_state)

        sample_xyz = np.asarray(ok_state.get("sample_xyz"), dtype=float)
        if sample_xyz.ndim != 2 or sample_xyz.shape[1] != 3:
            self.iface.messageBar().pushMessage(
                "Kriging validation",
                "The saved interpolation data are unavailable. Run interpolation again.",
                level=2,
            )
            return
        x = sample_xyz[:, 0].copy()
        y = sample_xyz[:, 1].copy()
        z = sample_xyz[:, 2].copy()
        n = len(z)

        # CV mode and folds (usar refs guardadas)
        mode = getattr(self, '_cv_mode_ok', self.CV_AUTO)

        # Lee K de spin_k_ok (si existe)
        k = 10
        if self.spin_k_ok is not None:
            try:
                k = int(self.spin_k_ok.value())
            except Exception:
                k = 10

        if mode == self.CV_AUTO:
            mode, k_auto = self._decide_auto_cv(n)
            if k_auto is not None:
                k = k_auto

        if mode == self.CV_LOOCV:
            folds = [[i] for i in range(n)]
            cv_desc = f"OK LOOCV (n={n})"
        else:
            k = max(2, min(int(k), n))
            folds = self._make_kfold_indices(n, k)
            cv_desc = f"OK {k}-fold CV (n={n})"

        preds = np.full(n, np.nan, dtype=float)

        model = ok_state["model"]
        nugget = float(ok_state["nugget"])
        psill = float(ok_state["psill"])
        var_range = float(ok_state["var_range"])

        # Progress dialog
        progress = QProgressDialog("Running Kriging CVâ€¦", "Cancel", 0, len(folds), self.dlg)
        progress.setWindowModality(True)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        # Run folds
        for i, test_idx_list in enumerate(folds, start=1):
            if progress.wasCanceled():
                self.iface.messageBar().pushWarning("Kriging CV", "Operation canceled by user.")
                return
            mask = np.ones(n, dtype=bool)
            mask[test_idx_list] = False
            if mask.sum() < 1:
                progress.setValue(i)
                continue

            try:
                pi = ordinary_kriging_interpolation(
                    x[mask], y[mask], z[mask],
                    x[np.array(test_idx_list)], y[np.array(test_idx_list)],
                    nugget=nugget, psill=psill, var_range=var_range, model=model
                )
                preds[np.array(test_idx_list)] = np.asarray(pi, dtype=float)
            except Exception as e:
                self.iface.messageBar().pushWarning("Kriging CV", f"Fold failed: {e}")

            progress.setValue(i)

        # Metrics + plot into OK CV widget
        rmse = self._rmse(z, preds)
        lccc = self._lccc(z, preds)
        rmse_pct = self._rmse_pct(z, preds)
        r2 = self._r2(z, preds)
        mae = self._mae(z, preds)
        pearson_r = self._pearson_r(z, preds)

        # Update OK metrics labels if present
        if hasattr(self.dlg, "valOKRMSE"):      self.dlg.valOKRMSE.setText(f"{rmse:.3f}" if np.isfinite(rmse) else "â€”")
        if hasattr(self.dlg, "valOKLCCC"):      self.dlg.valOKLCCC.setText(f"{lccc:.3f}" if np.isfinite(lccc) else "â€”")
        if hasattr(self.dlg, "valOKRMSEpct"):   self.dlg.valOKRMSEpct.setText(f"{rmse_pct:.2f}%" if np.isfinite(rmse_pct) else "â€”")
        if hasattr(self.dlg, "valOKR2"):        self.dlg.valOKR2.setText(f"{r2:.3f}" if np.isfinite(r2) else "â€”")
        if hasattr(self.dlg, "valOKMAE"):       self.dlg.valOKMAE.setText(f"{mae:.3f}" if np.isfinite(mae) else "â€”")
        if hasattr(self.dlg, "valOKPearsonR"):  self.dlg.valOKPearsonR.setText(f"{pearson_r:.3f}" if np.isfinite(pearson_r) else "â€”")

        # Plot scatter in dedicated Kriging CV widget
        if self.ok_cv_fig is None or self.ok_cv_canvas is None:
            self._attach_ok_cv_canvas()
        self._plot_validation_scatter(z, preds, fig=self.ok_cv_fig, canvas=self.ok_cv_canvas,
                                      title=f"{cv_desc} â€” Observed vs Predicted")

        self.iface.messageBar().pushMessage(
            "Kriging CV",
            f"{cv_desc} finished. RMSE={rmse:.3f}, RMSE%={(rmse_pct if np.isfinite(rmse_pct) else float('nan')):.2f}%, "
            f"MAE={mae:.3f}, RÂ²={(r2 if np.isfinite(r2) else float('nan')):.3f}, "
            f"Pearson r={(pearson_r if np.isfinite(pearson_r) else float('nan')):.3f}, "
            f"LCCC={(lccc if np.isfinite(lccc) else float('nan')):.3f}",
            level=0
        )

    def run_ok_cv_reml(self, ok_state=None):
        """Run LOOCV for Ordinary Kriging using the REML backend."""
        self._clear_ok_validation_outputs()
        self._reset_ok_validation_canvas()
        self._ensure_canvases_attached()
        if self.ok_cv_fig is None or self.ok_cv_canvas is None:
            self._attach_ok_cv_canvas()

        ok_state = ok_state or self._get_last_ok_interpolation_for_validation()
        if ok_state is None:
            return
        if ok_state.get("backend") != "REML":
            self.iface.messageBar().pushMessage(
                "Kriging validation",
                "The last interpolation used MoM. Run the matching Kriging validation.",
                level=2,
            )
            return

        sample_xyz = np.asarray(ok_state.get("sample_xyz"), dtype=float)
        reml_fit = ok_state.get("reml_fit")
        if sample_xyz.ndim != 2 or sample_xyz.shape[1] != 3 or reml_fit is None:
            self.iface.messageBar().pushMessage(
                "Kriging validation",
                "The saved REML interpolation configuration is unavailable. Run interpolation again.",
                level=2,
            )
            return

        try:
            cv_result = cv_ok_reml_interface(sample_xyz, reml_fit, k=0)
        except Exception as e:
            self.iface.messageBar().pushMessage("Error", f"REML CV failed: {e}", level=3)
            return

        obs = cv_result.get("y_true", cv_result.get("obs"))
        pred = cv_result.get("y_pred", cv_result.get("pred"))
        if obs is None or pred is None:
            self.iface.messageBar().pushMessage("Error", "REML CV did not return predictions.", level=3)
            return

        rmse = self._rmse(obs, pred)
        lccc = self._lccc(obs, pred)
        rmse_pct = self._rmse_pct(obs, pred)
        r2 = self._r2(obs, pred)
        mae = self._mae(obs, pred)
        pearson_r = self._pearson_r(obs, pred)

        self._plot_validation_scatter(
            obs, pred, fig=self.ok_cv_fig, canvas=self.ok_cv_canvas,
            title="OK REML â€” Observed vs Predicted"
        )

        if hasattr(self.dlg, "valOKRMSE"):     self.dlg.valOKRMSE.setText(f"{rmse:.3f}" if np.isfinite(rmse) else "â€”")
        if hasattr(self.dlg, "valOKLCCC"):     self.dlg.valOKLCCC.setText(f"{lccc:.3f}" if np.isfinite(lccc) else "â€”")
        if hasattr(self.dlg, "valOKRMSEpct"):  self.dlg.valOKRMSEpct.setText(f"{rmse_pct:.2f}%" if np.isfinite(rmse_pct) else "â€”")
        if hasattr(self.dlg, "valOKR2"):       self.dlg.valOKR2.setText(f"{r2:.3f}" if np.isfinite(r2) else "â€”")
        if hasattr(self.dlg, "valOKMAE"):      self.dlg.valOKMAE.setText(f"{mae:.3f}" if np.isfinite(mae) else "â€”")
        if hasattr(self.dlg, "valOKPearsonR"): self.dlg.valOKPearsonR.setText(f"{pearson_r:.3f}" if np.isfinite(pearson_r) else "â€”")

        self.iface.messageBar().pushMessage(
            "Kriging REML CV",
            f"Finished REML CV â€” RMSE={rmse:.3f}, RMSE%={(rmse_pct if np.isfinite(rmse_pct) else float('nan')):.2f}%, "
            f"MAE={mae:.3f}, RÂ²={(r2 if np.isfinite(r2) else float('nan')):.3f}, "
            f"r={(pearson_r if np.isfinite(pearson_r) else float('nan')):.3f}, "
            f"LCCC={(lccc if np.isfinite(lccc) else float('nan')):.3f}",
            level=0
        )
    # ----------------------- Interpolation (map preview/raster) ----------------

    def run_interpolation(self):
        """Deterministic interpolation entrypoint with progress dialog."""
        self._ensure_canvases_attached()
        if getattr(self.ok_ctrl, "_use_reml", False):
            return self.run_ok_interpolation_reml()
        points_layer_name = self.dlg.Points.currentText()
        variable_name = self.dlg.Points_2.currentText()
        polygon_layer_name = self.dlg.poly.currentText()
        pixel_size = self._get_pixel_size(default=0.01)

        if not points_layer_name or not variable_name or not polygon_layer_name:
            self.iface.messageBar().pushMessage("Error", "All inputs are required.", level=3)
            return

        points_layer = QgsProject.instance().mapLayersByName(points_layer_name)[0]
        pts_coords, vals = [], []
        for feat in points_layer.getFeatures():
            if feat.geometry().isEmpty():
                continue
            g = feat.geometry().asPoint()
            v = feat[variable_name]
            try:
                v = float(v)
            except Exception:
                v = None
            pts_coords.append(g)
            vals.append(v)

        pts_coords, vals = self.filter_incomplete_data(pts_coords, vals)
        if len(pts_coords) < 10:
            self.iface.messageBar().pushMessage("Error", "At least 10 valid data points are required for interpolation.", level=3)
            return

        try:
            x, y, z = finite_training_arrays(
                [p.x() for p in pts_coords],
                [p.y() for p in pts_coords],
                vals,
            )
        except Exception as exc:
            QMessageBox.warning(self.dlg, "Interpolation", format_shape_error(exc))
            return

        # ------- Thin Plate Spline -------
        if self._current_mode == self.MODE_TPS:
            if not _HAS_TPS:
                self.iface.messageBar().pushMessage("Error", "TPS is selected but Thin_plate_spline.py was not found or failed to import.", level=3)
                return
            prepared = self._prepare_tps_training_data(x, y, z, "TPS")
            if prepared is None:
                return
            x, y, z = prepared
            self.create_and_display_raster_tps(points_layer_name, variable_name, polygon_layer_name, pixel_size, x, y, z)

        # ------- Inverse Distance Weighting -------
        elif self._current_mode == self.MODE_IDW_MAN or self._current_mode == self.MODE_IDW_OPT:
            if self._current_mode == self.MODE_IDW_MAN:
                p_value = self._read_numeric_from_widget(self.dlg.manualPInput, cast=float, default=None)
                n_value = self._read_numeric_from_widget(self.dlg.manualNInput, cast=int, default=None)
                if p_value is None or n_value is None:
                    self.iface.messageBar().pushMessage("Error", "Manual p or n value is invalid.", level=3)
                    return
            else:
                try:
                    best_p, best_n, best_isi, _ = optimize_idw(x, y, z)
                    p_value, n_value = best_p, best_n
                    self.iface.messageBar().pushMessage(
                        "Optimization Complete",
                        f"Optimized parameters: p={best_p}, n={best_n}, ISI={best_isi:.5f}",
                        level=0
                    )
                except ValueError as e:
                    self.iface.messageBar().pushMessage("Error", str(e), level=3)
                    return

            self.create_and_display_raster(points_layer_name, variable_name, polygon_layer_name, pixel_size, p_value, n_value)

        # Note: Ordinary Kriging rasterization is handled by run_ok_interpolation() on the "Kriging" tab.

    def _choose_raster_output_path(self, method_tag, variable_name):
        base_name = f"{method_tag}_{variable_name}_{uuid.uuid4().hex[:6]}.tif"
        if self._should_export_raster() and self.output_dir:
            return os.path.join(self.output_dir, base_name)
        return os.path.join(tempfile.gettempdir(), base_name)

    def _init_grid_and_mask(self, polygon_layer, pixel_size):
        """Build grid coordinates and inside-polygon mask. Returns (xmin,xmax,ymin,ymax,n_cols,n_rows,grid_points,inside_idx)."""
        extent = polygon_layer.extent()
        xmin, ymin, xmax, ymax = extent.toRectF().getCoords()
        n_cols = int(np.ceil((xmax - xmin) / pixel_size))
        n_rows = int(np.ceil((ymax - ymin) / pixel_size))
        if n_cols < 1 or n_rows < 1:
            raise ValueError("Invalid pixel size or polygon extent is too small.")
        x_coords = xmin + pixel_size * (np.arange(n_cols) + 0.5)
        y_coords = ymax - pixel_size * (np.arange(n_rows) + 0.5)
        grid_points = np.array([(x_coords[c], y_coords[r]) for r in range(n_rows) for c in range(n_cols)])

        combined_mask = np.zeros(grid_points.shape[0], dtype=bool)
        for feature in polygon_layer.getFeatures():
            geom = feature.geometry()
            if geom.isMultipart():
                for part in geom.asMultiPolygon():
                    for ring in part:
                        ring_coords = [(pt.x(), pt.y()) for pt in ring]
                        ring_path = Path(ring_coords)
                        mask_i = ring_path.contains_points(grid_points)
                        combined_mask = np.logical_or(combined_mask, mask_i)
            else:
                for ring in geom.asPolygon():
                    ring_coords = [(pt.x(), pt.y()) for pt in ring]
                    ring_path = Path(ring_coords)
                    mask_i = ring_path.contains_points(grid_points)
                    combined_mask = np.logical_or(combined_mask, mask_i)
        inside_indices = np.where(combined_mask)[0]
        return xmin, xmax, ymin, ymax, n_cols, n_rows, grid_points, inside_indices

    def _write_raster_and_add(self, raster_array, polygon_layer, pixel_size, variable_name, method_tag, title_prefix):
        """Write GeoTIFF and add to QGIS."""
        extent = polygon_layer.extent()
        xmin, ymin, xmax, ymax = extent.toRectF().getCoords()
        n_rows, n_cols = raster_array.shape

        raster_path = self._choose_raster_output_path(method_tag, variable_name)
        wkt = polygon_layer.crs().toWkt()
        driver = gdal.GetDriverByName("GTiff")
        dataset = driver.Create(raster_path, n_cols, n_rows, 1, gdal.GDT_Float32)
        if not dataset:
            self.iface.messageBar().pushMessage("Error","Failed to create GTiff.", level=3); return

        geotransform = (xmin, pixel_size, 0, ymax, 0, -pixel_size)
        dataset.SetGeoTransform(geotransform)
        srs = osr.SpatialReference(); srs.ImportFromWkt(wkt)
        dataset.SetProjection(srs.ExportToWkt())

        band = dataset.GetRasterBand(1)
        band.WriteArray(raster_array)
        band.SetNoDataValue(np.nan); band.FlushCache()
        dataset.FlushCache(); dataset = None

        layer_name = f"{title_prefix} ({variable_name})"
        raster_layer = self._create_output_raster_layer(raster_path, layer_name)
        if not raster_layer.isValid():
            self.iface.messageBar().pushMessage("Error","Raster layer is not valid.", level=3); return
        self._mark_temporary_layer(raster_layer, raster_path)
        QgsProject.instance().addMapLayer(raster_layer)
        self.iface.messageBar().pushMessage("Info", f"Raster layer created: {raster_path}", level=0)
        return raster_path

    def _draw_interpolation_preview(self, result_array, polygon_layer, variable_name, title):
        """Draws the preview on the deterministic interpolation canvas."""
        self.det_interp_fig.clear()
        ax = self.det_interp_fig.add_subplot(111)
        ax.set_title(title)

        extent = polygon_layer.extent()
        xmin, ymin, xmax, ymax = extent.toRectF().getCoords()
        n_rows, n_cols = result_array.shape
        x_edges = np.linspace(xmin, xmax, n_cols + 1)
        y_edges = np.linspace(ymin, ymax, n_rows + 1)
        disp_array = np.flipud(result_array)
        masked_data = np.ma.masked_invalid(disp_array)
        pm = ax.pcolormesh(x_edges, y_edges, masked_data, cmap="viridis", shading="auto")
        cbar = self.det_interp_fig.colorbar(pm, ax=ax, orientation='vertical'); cbar.set_label(variable_name)

        for feat in polygon_layer.getFeatures():
            geom = feat.geometry()
            if geom.isMultipart():
                for part in geom.asMultiPolygon():
                    for ring in part:
                        ring_xy = [(pt.x(), pt.y()) for pt in ring]
                        patch = MplPolygon(ring_xy, closed=True, edgecolor="black", facecolor="none")
                        ax.add_patch(patch)
            else:
                for ring in geom.asPolygon():
                    ring_xy = [(pt.x(), pt.y()) for pt in ring]
                    patch = MplPolygon(ring_xy, closed=True, edgecolor="black", facecolor="none")
                    ax.add_patch(patch)

        ax.set_xlim(xmin, xmax); ax.set_ylim(ymin, ymax)
        self._apply_million_formatter(ax)
        self.det_interp_canvas.draw()

    def create_and_display_raster(self, points_layer_name, variable_name,
                                  polygon_layer_name, pixel_size, p_value, n_value):
        """IDW raster with progress dialog."""
        self._ensure_canvases_attached()
        points_layer = QgsProject.instance().mapLayersByName(points_layer_name)[0]
        pts_coords, vals = [], []
        for feat in points_layer.getFeatures():
            if feat.geometry().isEmpty(): continue
            g = feat.geometry().asPoint()
            v = feat[variable_name]
            try: v = float(v)
            except Exception: v = None
            pts_coords.append(g); vals.append(v)
        pts_coords, vals = self.filter_incomplete_data(pts_coords, vals)
        if not pts_coords or not vals:
            self.iface.messageBar().pushMessage("Error","No valid points or values found for interpolation.", level=3)
            return

        try:
            x_vals, y_vals, z_vals = finite_training_arrays(
                [p.x() for p in pts_coords],
                [p.y() for p in pts_coords],
                vals,
            )
            xy_pts = ensure_xy_2d(np.column_stack([x_vals, y_vals]), "training coordinates")
        except Exception as exc:
            QMessageBox.warning(self.dlg, "Interpolation", format_shape_error(exc))
            return

        if z_vals.size < 10:
            self.iface.messageBar().pushMessage("Error", "At least 10 valid samples are required for IDW interpolation.", level=3)
            return

        polygon_layer = QgsProject.instance().mapLayersByName(polygon_layer_name)[0]

        try:
            xmin, xmax, ymin, ymax, n_cols, n_rows, grid_points, inside_indices = self._init_grid_and_mask(polygon_layer, pixel_size)
        except ValueError as e:
            self.iface.messageBar().pushMessage("Error", str(e), level=3)
            return

        result_array = np.full((n_rows, n_cols), np.nan, dtype=np.float32)

        # Progress dialog (chunked)
        total_inside = len(inside_indices)
        progress = QProgressDialog("Interpolating (IDW)â€¦", "Cancel", 0, total_inside, self.dlg)
        progress.setWindowModality(True)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        # Chunk through inside points to show progress
        chunk = max(1, total_inside // 50)  # ~50 updates
        for start in range(0, total_inside, chunk):
            if progress.wasCanceled():
                self.iface.messageBar().pushWarning("Interpolation", "Operation canceled by user.")
                return
            end = min(total_inside, start + chunk)
            inside_pts = ensure_xy_2d(grid_points[inside_indices[start:end]], "prediction coordinates")
            try:
                interpolated_vals = idw_interpolation(
                    xy_pts[:, 0], xy_pts[:, 1], z_vals,
                    inside_pts[:, 0], inside_pts[:, 1],
                    p_value, max(1, min(int(n_value), len(z_vals)))
                )
            except Exception as exc:
                QMessageBox.warning(self.dlg, "Interpolation", format_shape_error(exc, xy_pts, inside_pts, z_vals))
                return
            # Write into raster array
            for local_i, gi in enumerate(inside_indices[start:end]):
                col_i = gi % n_cols
                row_i = gi // n_cols
                result_array[row_i, col_i] = float(interpolated_vals[local_i])
            progress.setValue(end)

        # Write GeoTIFF and add to QGIS
        raster_path = self._write_raster_and_add(result_array, polygon_layer, pixel_size, variable_name, "IDW", "Interpolated IDW")
        # Preview
        self._draw_interpolation_preview(result_array, polygon_layer, variable_name, f"IDW Interpolation \np={p_value}, n={n_value}")
        method = "IDW_MAN" if self._current_mode == self.MODE_IDW_MAN else "IDW_OPT"
        self._record_det_interpolation(
            method,
            points_layer_name,
            variable_name,
            polygon_layer_name,
            pixel_size,
            training_data=(x_vals, y_vals, z_vals),
            p=float(p_value),
            n=int(n_value),
            raster_path=raster_path,
        )
        self.iface.messageBar().pushMessage("Interpolation Complete", level=0)

    def create_and_display_raster_tps(self, points_layer_name, variable_name,
                                      polygon_layer_name, pixel_size, x, y, z):
        """TPS raster with progress dialog."""
        self._ensure_canvases_attached()
        try:
            x, y, z = finite_training_arrays(x, y, z)
        except Exception as exc:
            QMessageBox.warning(self.dlg, "Interpolation", format_shape_error(exc))
            return
        prepared = self._prepare_tps_training_data(x, y, z, "TPS")
        if prepared is None:
            return
        x, y, z = prepared
        if z.size < 10:
            self.iface.messageBar().pushMessage("Error", "At least 10 valid samples are required for TPS interpolation.", level=3)
            return
        polygon_layer = QgsProject.instance().mapLayersByName(polygon_layer_name)[0]
        try:
            xmin, xmax, ymin, ymax, n_cols, n_rows, grid_points, inside_indices = self._init_grid_and_mask(polygon_layer, pixel_size)
        except ValueError as e:
            self.iface.messageBar().pushMessage("Error", str(e), level=3)
            return

        result_array = np.full((n_rows, n_cols), np.nan, dtype=np.float32)

        total_inside = len(inside_indices)
        if total_inside == 0:
            self.iface.messageBar().pushMessage("Warning","No grid cells fall inside the polygon.", level=2)
            return

        progress = QProgressDialog("Interpolating (TPS)â€¦", "Cancel", 0, total_inside, self.dlg)
        progress.setWindowModality(True)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        chunk = max(1, total_inside // 50)
        for start in range(0, total_inside, chunk):
            if progress.wasCanceled():
                self.iface.messageBar().pushWarning("Interpolation", "Operation canceled by user.")
                return
            end = min(total_inside, start + chunk)
            inside_pts = ensure_xy_2d(grid_points[inside_indices[start:end]], "prediction coordinates")
            try:
                tps_vals = tps_interpolation(x, y, z, inside_pts[:, 0], inside_pts[:, 1], epsilon=1e-4)
            except Exception as e:
                QMessageBox.warning(self.dlg, "Interpolation", format_shape_error(e, np.column_stack([x, y]), inside_pts, z))
                return
            for local_i, gi in enumerate(inside_indices[start:end]):
                col_i = gi % n_cols
                row_i = gi // n_cols
                result_array[row_i, col_i] = float(tps_vals[local_i])
            progress.setValue(end)

        raster_path = self._write_raster_and_add(result_array, polygon_layer, pixel_size, variable_name, "TPS", "Interpolated TPS")
        self._record_det_interpolation(
            "TPS",
            points_layer_name,
            variable_name,
            polygon_layer_name,
            pixel_size,
            training_data=(x, y, z),
            epsilon=1e-4,
            raster_path=raster_path,
        )
        self._draw_interpolation_preview(result_array, polygon_layer, variable_name, "TPS Interpolation \nÎµ=0.0001")
        self.iface.messageBar().pushMessage("Interpolation Complete", level=0)

    # ---------------------------- Kriging interpolation -------------------------

    def run_ok_interpolation(self):
        """Export Ordinary Kriging raster to QGIS, mirroring deterministic export behavior."""
        points_layer_name = self.dlg.Points.currentText()
        variable_name = self.dlg.Points_2.currentText()
        polygon_layer_name = self.dlg.poly.currentText()
        pixel_size = self._get_pixel_size(default=0.01)

        if not points_layer_name or not variable_name or not polygon_layer_name:
            self.iface.messageBar().pushMessage("Error", "All inputs are required.", level=3)
            return

        layers = QgsProject.instance().mapLayersByName(points_layer_name)
        if not layers:
            self.iface.messageBar().pushMessage("Error","Point layer not found.", level=3)
            return

        layer = layers[0]
        coords, vals = [], []
        for feat in layer.getFeatures():
            g = feat.geometry()
            if g.isEmpty(): continue
            pt = g.asPoint()
            v = feat[variable_name]
            try: v = float(v)
            except Exception: v = None
            coords.append(pt); vals.append(v)

        coords, vals = self.filter_incomplete_data(coords, vals)
        if len(coords) < 5:
            self.iface.messageBar().pushMessage("Error","At least 5 valid data points are required for interpolation.", level=3)
            return

        x = np.array([p.x() for p in coords])
        y = np.array([p.y() for p in coords])
        z = np.array(vals, dtype=float)

        model, nugget, psill, var_range = self._read_ok_params()

        polygon_layer = QgsProject.instance().mapLayersByName(polygon_layer_name)[0]
        try:
            xmin, xmax, ymin, ymax, n_cols, n_rows, grid_points, inside_indices = self._init_grid_and_mask(polygon_layer, pixel_size)
        except ValueError as e:
            self.iface.messageBar().pushMessage("Error", str(e), level=3)
            return

        result_array = np.full((n_rows, n_cols), np.nan, dtype=np.float32)

        total_inside = len(inside_indices)
        if total_inside == 0:
            self.iface.messageBar().pushMessage("Warning","No grid cells fall inside the polygon.", level=2)
            return

        progress = QProgressDialog("Interpolating (Ordinary Kriging)â€¦", "Cancel", 0, total_inside, self.dlg)
        progress.setWindowModality(True)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        # Chunk the OK predictions for progress and memory friendliness
        chunk = max(1, total_inside // 50)
        for start in range(0, total_inside, chunk):
            if progress.wasCanceled():
                self.iface.messageBar().pushWarning("Kriging", "Operation canceled by user.")
                return
            end = min(total_inside, start + chunk)
            inside_pts = grid_points[inside_indices[start:end]]
            try:
                preds = ordinary_kriging_interpolation(
                    x, y, z,
                    inside_pts[:, 0], inside_pts[:, 1],
                    nugget=nugget, psill=psill, var_range=var_range, model=model
                )
            except Exception as e:
                self.iface.messageBar().pushMessage("Error", f"Kriging failed: {e}", level=3)
                return

            for local_i, gi in enumerate(inside_indices[start:end]):
                col_i = gi % n_cols
                row_i = gi // n_cols
                result_array[row_i, col_i] = float(preds[local_i])

            progress.setValue(end)

        # Write GeoTIFF, add to QGIS, and draw preview
        raster_path = self._write_raster_and_add(result_array, polygon_layer, pixel_size, variable_name, "OK", "Interpolated OK")
        if raster_path is None:
            return

        self._record_ok_interpolation(
            "MoM",
            points_layer_name,
            variable_name,
            polygon_layer_name,
            pixel_size,
            np.column_stack((x, y, z)),
            model,
            nugget,
            psill,
            var_range,
        )

        # Preview (usa el canvas determinÃ­stico para mantener consistencia visual)
        self._draw_interpolation_preview(result_array, polygon_layer, variable_name,
                                         f"OK Interpolation \n{model} nug={nugget}, psill={psill}, range={var_range}")

        self.iface.messageBar().pushMessage("Kriging", "Interpolation Complete", level=0)

    def run_ok_interpolation_reml(self):
        """Run REML-based OK interpolation without requiring an experimental variogram."""
        self._ensure_canvases_attached()
        points_layer_name = self.dlg.Points.currentText()
        variable_name = self.dlg.Points_2.currentText()
        polygon_layer_name = self.dlg.poly.currentText()
        pixel_size = self._get_pixel_size(default=0.01)

        if not points_layer_name or not variable_name or not polygon_layer_name:
            self.iface.messageBar().pushMessage("Error", "All inputs are required.", level=3)
            return

        layer = QgsProject.instance().mapLayersByName(points_layer_name)[0]
        coords, vals = [], []
        for feat in layer.getFeatures():
            g = feat.geometry()
            if g.isEmpty():
                continue
            pt = g.asPoint()
            v = feat[variable_name]
            try:
                v = float(v)
            except Exception:
                v = None
            coords.append(pt)
            vals.append(v)

        coords, vals = self.filter_incomplete_data(coords, vals)
        if len(coords) < 5:
            self.iface.messageBar().pushMessage("Error", "At least 5 valid data points are required for interpolation.", level=3)
            return

        sample_xyz = np.column_stack((
            [p.x() for p in coords],
            [p.y() for p in coords],
            np.array(vals, dtype=float)
        ))

        model, nugget, psill, var_range = self._read_ok_params()
        mom_fit = {"model": model, "psill": psill, "range": var_range, "nugget": nugget}

        try:
            reml_fit = fit_ok_reml_interface(sample_xyz, model=model, init_from_mom=mom_fit)
        except Exception as e:
            self.iface.messageBar().pushMessage("Error", f"REML fit failed: {e}", level=3)
            return

        polygon_layer = QgsProject.instance().mapLayersByName(polygon_layer_name)[0]
        xmin, xmax, ymin, ymax, n_cols, n_rows, grid_points, inside_indices = self._init_grid_and_mask(polygon_layer, pixel_size)
        result_array = np.full((n_rows, n_cols), np.nan, dtype=np.float32)

        inside_pts = grid_points[inside_indices]
        preds, _ = predict_ok_reml_interface(reml_fit, sample_xyz, inside_pts)

        for local_i, gi in enumerate(inside_indices):
            col_i = gi % n_cols
            row_i = gi // n_cols
            result_array[row_i, col_i] = float(preds[local_i])

        raster_path = self._write_raster_and_add(
            result_array,
            polygon_layer,
            pixel_size,
            variable_name,
            "OK_REML",
            "Interpolated OK (REML)",
        )
        if raster_path is None:
            return
        self._record_ok_interpolation(
            "REML",
            points_layer_name,
            variable_name,
            polygon_layer_name,
            pixel_size,
            sample_xyz,
            model,
            nugget,
            psill,
            var_range,
            reml_fit=reml_fit,
        )
        self._draw_interpolation_preview(result_array, polygon_layer, variable_name, f"OK REML Interpolation â€” {model}")
        self.iface.messageBar().pushMessage("Kriging REML", "Interpolation Complete", level=0)


