"""Private Framework controllers; only data inputs and published outputs cross tabs."""
from copy import copy
from functools import wraps
from inspect import getattr_static

from qgis.PyQt.QtCore import QObject
from qgis.PyQt.QtWidgets import QComboBox, QDoubleSpinBox, QSpinBox, QCheckBox
from matplotlib.figure import Figure


class _ExecutionView:
    """Run the existing Framework orchestration against its private plugin/UI."""
    def __init__(self, framework, worker):
        self.__dict__.update(framework.__dict__)
        self._controller_type = type(framework)
        self.plugin = worker
        self.dlg = worker.dlg
        self._copy_source_figure_to_framework_map = framework._copy_source_figure_to_framework_map

    def __getattr__(self, name):
        value = getattr_static(self._controller_type, name)
        return value.__get__(self, self._controller_type) if hasattr(value, '__get__') else value


class FrameworkExecutionWorkspace:
    """Reuse the numerical workflows without writing into standalone widgets/state."""
    def __init__(self, framework):
        from .BestFitInterpolator import BestFitInterpolatorDialog
        from .machine_learning_tab import MachineLearningTabController
        from .RF_RegressionKriging import RegressionKrigingRFController
        self.framework = framework
        source = framework.plugin
        worker = copy(source)
        self.plugin = worker
        # Shallow copies retain input layers, but no mutable UI or controller state.
        for name, value in list(worker.__dict__.items()):
            if isinstance(value, (QObject, Figure)):
                setattr(worker, name, None)
            elif isinstance(value, (dict, list, set)):
                setattr(worker, name, copy(value))
        worker._framework_owner = source
        worker.framework_ctrl = None
        worker.ml_ctrl = worker.rk_ctrl = worker.ok_ctrl = None
        worker.language_ctrl = None
        worker._last_det_interpolation = worker._last_ok_interpolation = None
        worker._last_interpolation_result = worker._last_interpolation_figure = None
        worker._latest_produced_result = None
        worker._save_handlers = set()
        worker._proj_signals_connected = False
        worker._watch_input_layer = lambda layer: None
        worker.dlg = BestFitInterpolatorDialog(worker.plugin_dir, source.dlg)
        worker.dlg._bfi_plugin = worker
        worker._bind_ui_aliases()
        worker._attach_canvases()
        worker._attach_ok_cv_canvas()
        worker._wire_deterministic_controls()
        worker._wire_cv_controls()
        worker._wire_ok_cv_controls()
        worker.ml_ctrl = MachineLearningTabController(worker.dlg, worker.iface)
        worker.ml_ctrl.parent_plugin = worker
        worker.rk_ctrl = RegressionKrigingRFController(worker.dlg, worker.iface,
            worker._build_rk_points_callback, worker._build_rk_grid_callback,
            worker._write_rk_raster_callback)
        worker.rk_ctrl.parent_plugin = worker
        source.dlg.finished.connect(self.dispose)
        self.sync_inputs()

    def sync_inputs(self):
        source = self.framework.plugin
        worker = self.plugin
        # Data and covariate preparation are shared inputs; fitted configurations,
        # validation results, metrics, figures and output selectors remain private.
        for name in ('Points', 'Points_2', 'poly'):
            original = getattr(source.dlg, name)
            target = getattr(worker.dlg, name)
            blocked = target.blockSignals(True)
            target.clear()
            for index in range(original.count()):
                target.addItem(original.itemText(index), original.itemData(index))
            target.setCurrentIndex(original.currentIndex())
            target.blockSignals(blocked)
        for name in ('spinPixelSize', 'chkExportRaster', 'cmbStandardizeMethod'):
            original = getattr(source.dlg, name, None)
            target = getattr(worker.dlg, name, None)
            if original is None or target is None:
                continue
            blocked = target.blockSignals(True)
            if isinstance(target, QComboBox): target.setCurrentIndex(original.currentIndex())
            elif isinstance(target, (QSpinBox, QDoubleSpinBox)): target.setValue(original.value())
            elif isinstance(target, QCheckBox): target.setChecked(original.isChecked())
            target.blockSignals(blocked)
        worker.output_dir = source.output_dir
        worker.diagnostics_states = source.diagnostics_states
        original_ml = source.ml_ctrl
        worker.ml_ctrl.covariate_layers = dict(original_ml.covariate_layers)
        target = worker.dlg.listCovariates
        target.clear()
        for index in range(source.dlg.listCovariates.count()):
            target.addItem(source.dlg.listCovariates.item(index).clone())
        worker.ml_ctrl._standardization_for_extraction = original_ml._standardization_for_extraction
        worker.ml_ctrl._sync_pixel_size_from_data(set_target_default=False)
        options = self.framework.__dict__.get('_pending_framework_sd_options', {})
        for method, name in (('OK', 'chkOKUncertaintyLayer'), ('RF', 'chkRFUncertaintyLayer'),
                             ('RK', 'chkRKUncertaintyLayer')):
            control = getattr(worker.dlg, name, None)
            if control is not None: control.setChecked(options.get(method, True))
        worker._bfi_interpolation_purpose = getattr(source, '_bfi_interpolation_purpose', 'standalone')

    def invalidate(self):
        worker = self.plugin
        worker.ml_ctrl.reset_for_analysis_change()
        worker.rk_ctrl.clear_plots()
        for owner in (worker.ml_ctrl, worker.rk_ctrl):
            owner.__dict__.pop('_framework_search_cache', None)
        worker._last_det_interpolation = worker._last_ok_interpolation = None
        if worker.ok_ctrl is not None:
            worker.ok_ctrl.clear_plots()

    def dispose(self, *args):
        worker = self.plugin
        if worker is None: return
        self.invalidate()
        if worker.ok_ctrl is not None: worker.ok_ctrl.dispose()
        worker.dlg.deleteLater()
        self.plugin = None
        self.framework.__dict__.pop('_execution_workspace', None)


def isolated_framework_execution(function):
    @wraps(function)
    def execute(framework, *args, **kwargs):
        if framework.plugin is None:
            return function(framework, *args, **kwargs)
        workspace = getattr(framework, '_execution_workspace', None)
        if workspace is None:
            workspace = FrameworkExecutionWorkspace(framework)
            framework._execution_workspace = workspace
        else:
            workspace.sync_inputs()
        return function(_ExecutionView(framework, workspace.plugin), *args, **kwargs)
    return execute
