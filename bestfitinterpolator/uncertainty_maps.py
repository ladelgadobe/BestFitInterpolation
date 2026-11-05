"""Display, export and record explicitly defined RF/RK uncertainty components."""
from .localization import _combo_text, _find_text, _new, _ui
import copy
import os
import numpy as np
from qgis.PyQt.QtWidgets import QWidget, QHBoxLayout, QLabel, QComboBox, QCheckBox
from qgis.core import QgsProject, QgsRasterLayer
from .forest_uncertainty import RF_DESCRIPTION, RK_DESCRIPTION

LABELS = dict(kriging_std='Kriging standard deviation', kriging_variance='Kriging variance',
              rf_std='RF tree standard deviation', rf_variance='RF tree variance',
              rk_std='Residual kriging standard deviation', rk_variance='Residual kriging variance')


def output_label(key, method):
    label = LABELS[key]
    return label.replace('RF tree', 'RF trend tree') if method == 'RK' else label


def output_definition(key):
    if key.startswith('kriging_'):
        from .geostatistics_options import UNCERTAINTY_DESCRIPTION
        return UNCERTAINTY_DESCRIPTION
    return RK_DESCRIPTION if key.startswith('rk_') else RF_DESCRIPTION


def output_value_label(target, key):
    return str(target) + ('² (variance)' if key.endswith('variance') else ' (SD)')


def ordered_output_keys(method, paths):
    if canonical_method(method) in ('OK','UK'):
        order = ('kriging_std','kriging_variance')
    else:
        order = ('rk_std','rk_variance','rf_std','rf_variance') if method == 'RK' else ('rf_std','rf_variance')
    return [key for key in order if key in paths]


def canonical_method(method):
    value = str(method or '').strip().upper()
    return 'RF' if value == 'RFE' else value


def result_uncertainty_paths(result):
    """Normalize old kriging SD records and current RF/RK/kriging outputs."""
    if result is None or canonical_method(result.method) not in ('OK','UK','RF','RK'):
        return {}
    parameters = result.parameters
    paths = dict(parameters.get('uncertainty_paths') or {})
    if canonical_method(result.method) in ('OK','UK') and parameters.get('uncertainty_path'):
        paths.setdefault('kriging_std', parameters['uncertainty_path'])
    return {key: str(paths[key]) for key in ordered_output_keys(result.method, paths)
            if paths[key] and os.path.isfile(str(paths[key]))}


def result_output_definition(result, key):
    parameters = result.parameters
    return (parameters.get('uncertainty_definitions', {}).get(key)
            or parameters.get('uncertainty_definition') or output_definition(key))


def result_target(result):
    values = result.parameters
    return values.get('target_name') or values.get('variable') or 'Value'


def install_sd_control(dialog, method, selector):
    """Use the same checked-by-default Add SD layer option as OK."""
    checkbox = _new(QCheckBox, 'Add SD layer', selector.widget)
    name = 'chk{}UncertaintyLayer'.format(method)
    checkbox.setObjectName(name)
    checkbox.setChecked(True)
    _ui(checkbox, 'setToolTip', RF_DESCRIPTION if method == 'RF' else RK_DESCRIPTION)
    selector.widget.layout().addWidget(checkbox)
    setattr(dialog, name, checkbox)


def add_sd_to_canvas(owner, method):
    checkbox = getattr(owner.dlg, 'chk{}UncertaintyLayer'.format(method), None)
    return bool(checkbox.isChecked()) if checkbox is not None else True


def uncertainty_layer(path, title):
    """Reports and plugin previews also work for outputs not added to QGIS."""
    layer = next((item for item in QgsProject.instance().mapLayers().values()
                  if item.source().split('|')[0] == path), None)
    if layer is None:
        layer = QgsRasterLayer(path, title)
    return layer if layer.isValid() else None


class MapOutputSelector:
    """One existing canvas with independent display settings for each output."""
    def __init__(self, container, canvas, name, render):
        self.canvas, self.render = canvas, render
        self.styles, self.current = {}, None
        self.widget = QWidget(container)
        row = QHBoxLayout(self.widget); row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(_new(QLabel, 'Map output', self.widget))
        self.combo = QComboBox(self.widget); self.combo.setObjectName(name)
        row.addWidget(self.combo, 1)
        container.layout().insertWidget(0, self.widget)
        self.entries = {}
        self.combo.currentIndexChanged.connect(self.show)
        self.clear()

    def clear(self):
        self.entries, self.styles, self.current = {}, {}, None
        self._execution_signature = None
        blocked = self.combo.blockSignals(True)
        self.combo.clear(); _ui(self.combo, 'addItem', 'Prediction', 'prediction')
        self.combo.setEnabled(False); _ui(self.combo, 'setToolTip', 'Run interpolation to produce map outputs.')
        self.combo.blockSignals(blocked)

    def configure(self, entries):
        self.entries, self.styles, self.current = entries, {}, None
        blocked = self.combo.blockSignals(True)
        self.combo.clear()
        for key, entry in entries.items():
            _ui(self.combo, 'addItem', entry['label'], key)
        self.combo.setCurrentIndex(0); self.combo.setEnabled(len(entries)>1)
        self.combo.blockSignals(blocked)
        self.show()

    def show(self, *args):
        key = self.combo.currentData()
        if key not in self.entries:
            return
        display = getattr(self.canvas, '_bfi_map_display', None)
        if display is not None:
            if self.current is not None:
                self.styles[self.current] = (copy.deepcopy(display.controls.state), display.controls._customized)
            display.controls._customized = False
        self.current = key
        _ui(self.combo, 'setToolTip', self.entries[key].get('definition', 'Prediction from the fitted model.'))
        self.render(key, self.entries[key])
        display = getattr(self.canvas, '_bfi_map_display', None)
        if display is None:
            return
        display.adopt_current(automatic=True)
        saved = self.styles.get(key)
        if saved is None or not saved[1]:
            return
        state, customized = saved
        controls = display.controls
        widgets = (controls.palette, controls.minimum, controls.maximum, controls.automatic, controls.scale)
        previous = [widget.blockSignals(True) for widget in widgets]
        try:
            index = _find_text(controls.palette, state.palette)
            if index >= 0: controls.palette.setCurrentIndex(index)
            controls.minimum.setValue(state.minimum); controls.maximum.setValue(state.maximum)
            controls.automatic.setChecked(state.automatic); controls.scale.setValue(state.scale)
            controls.minimum.setEnabled(not state.automatic); controls.maximum.setEnabled(not state.automatic)
            controls.state, controls._customized = copy.deepcopy(state), customized
        finally:
            for widget, blocked in zip(widgets, previous): widget.blockSignals(blocked)
        display.apply_current()


def map_entries(grid, target, method, columns):
    entries = dict(prediction=dict(label='Prediction', column=target+'_pred' if method=='RF' else target+'_rk_pred',
                                  value_label=target, title='Random Forest' if method=='RF' else 'Regression Kriging'))
    for key, column in columns.items():
        if column not in grid or not np.isfinite(grid[column].to_numpy(dtype=float)).any():
            continue
        entries[key] = dict(label=output_label(key, method), column=column, title=output_label(key, method),
                            value_label=output_value_label(target, key),
                            definition=output_definition(key))
    if method == 'RF' and columns and len(entries) == 1:
        entries['prediction']['definition'] = 'No finite RF dispersion was produced. Tree dispersion requires at least two trees. '+RF_DESCRIPTION
    return entries


def export_uncertainty(owner, grid, meta, target, method, columns, configuration):
    plugin = getattr(owner, 'parent_plugin', None) or getattr(owner.dlg, '_bfi_plugin', None)
    writer = owner if hasattr(owner, '_write_prediction_raster_from_grid_df') else getattr(plugin, 'ml_ctrl', None)
    if writer is None:
        raise ValueError('The uncertainty raster writer is unavailable.')
    paths, definitions, canvas_outputs = {}, {}, []
    add_sd = add_sd_to_canvas(owner, method)
    primary_sd = 'rf_std' if method == 'RF' else 'rk_std'
    for key, entry in map_entries(grid, target, method, columns).items():
        if key == 'prediction': continue
        add_layer = add_sd and key == primary_sd
        path = writer._write_prediction_raster_from_grid_df(grid, meta, target,
            method+'_'+key.upper(), entry['label'], pred_column=entry['column'],
            add_to_project=add_layer)
        if path is None:
            raise ValueError('Could not export '+entry['label']+'.')
        paths[key], definitions[key] = str(path), entry['definition']
        if add_layer:
            canvas_outputs.append(key)
        for layer in QgsProject.instance().mapLayers().values():
            if layer.source().split('|')[0] == str(path):
                layer.setName(entry['label']+' ('+target+')')
                layer.setCustomProperty('bestfitinterpolator/output_kind', 'uncertainty_component')
                layer.setCustomProperty('bestfitinterpolator/uncertainty_component', key)
                layer.setCustomProperty('bestfitinterpolator/uncertainty_definition', entry['definition'])
        from osgeo import gdal
        ds = gdal.Open(str(path), gdal.GA_Update)
        if ds is not None:
            for name, value in dict(BESTFIT_UNCERTAINTY_COMPONENT=key, BESTFIT_UNCERTAINTY_DEFINITION=entry['definition'],
                                    BESTFIT_PARENT_METHOD=method, BESTFIT_SOURCE_PREDICTION=configuration['raster_path'],
                                    BESTFIT_UNCERTAINTY_CALIBRATED='NO',
                                    BESTFIT_UNITS='response_squared' if key.endswith('variance') else 'response').items():
                ds.SetMetadataItem(name, str(value))
            ds = None
    configuration['uncertainty_paths'] = paths
    configuration['uncertainty_definitions'] = definitions
    configuration['uncertainty_calibrated'] = False
    configuration['uncertainty_canvas_outputs'] = canvas_outputs
    return paths


def link_uncertainty(result):
    from osgeo import gdal
    for path in result.parameters.get('uncertainty_paths', {}).values():
        for layer in QgsProject.instance().mapLayers().values():
            if layer.source().split('|')[0] == path:
                layer.setCustomProperty('bestfitinterpolator/parent_execution_id', result.execution_id)
        ds = gdal.Open(path, gdal.GA_Update)
        if ds is not None:
            ds.SetMetadataItem('BESTFIT_PARENT_EXECUTION_ID', result.execution_id)
            ds = None


def framework_prediction_figure(framework):
    """Return only a prediction produced by this Framework execution."""
    result = framework.state.__dict__.get('executed_result')
    figure = getattr(framework, '_interpolation_prediction_figure', None)
    if result is not None and getattr(figure, '_bfi_execution_id', None) == result.execution_id:
        return figure
    return None


def clear_framework_preview(framework):
    """An unexecuted Framework has no map or active map settings."""
    figure = getattr(framework, 'interpolation_fig', None)
    canvas = getattr(framework, 'interpolation_canvas', None)
    if figure is not None: figure.clear()
    if canvas is None: return
    if canvas.figure is not figure:
        canvas.figure.clear()
    canvas._bfi_no_display_settings = True
    button = getattr(canvas, '_bfi_settings_button', None)
    if button is not None: button.hide()
    canvas.draw_idle()


def install_framework_selector(framework):
    def render(key, entry):
        source = framework_prediction_figure(framework)
        if source is None:
            clear_framework_preview(framework)
            return
        if key == 'prediction':
            from .mpl_compat import clone_figure
            figure = clone_figure(source)
        else:
            layer = uncertainty_layer(entry['path'], entry['label'])
            if layer is None: return
            figure = framework._make_raster_preview_figure(layer, entry['label'])
            if figure is None: return
            if len(figure.axes)>1:
                figure.axes[-1].set_ylabel(entry['value_label'], fontsize=8)
                figure.tight_layout()
        framework.interpolation_fig = figure
        if key == 'prediction': framework._interpolation_prediction_figure = figure
        framework.interpolation_canvas.figure = figure
        figure.set_canvas(framework.interpolation_canvas)
        figure._bfi_output_kind = key
        from .map_controls import attach_map_controls
        framework.interpolation_canvas._bfi_is_map = True
        framework.interpolation_canvas._bfi_no_display_settings = False
        attach_map_controls(framework.interpolation_canvas)
        button = getattr(framework.interpolation_canvas, '_bfi_settings_button', None)
        if button is not None: button.reposition()
        framework.interpolation_canvas.draw_idle()
    framework._uncertainty_map_selector = MapOutputSelector(framework.frame_interpolation_map,
        framework.interpolation_canvas, 'cmbFrameworkMapOutput', render)
    framework.dlg.cmbFrameworkMapOutput = framework._uncertainty_map_selector.combo
    checkbox = _new(QCheckBox, 'Add SD layer', framework._uncertainty_map_selector.widget)
    checkbox.setObjectName('chkFrameworkUncertaintyLayer')
    checkbox.setChecked(True); checkbox.setEnabled(False)
    _ui(checkbox, 'setToolTip', 'Add the selected method SD layer to QGIS when interpolation runs.')
    framework._uncertainty_map_selector.widget.layout().addWidget(checkbox)
    framework.dlg.chkFrameworkUncertaintyLayer = checkbox
    def changed(checked):
        method = selected_framework_method(framework)
        framework.__dict__.setdefault('_pending_framework_sd_options', {})[method] = bool(checked)
        source = framework_sd_source(framework, method)
        if source is not None:
            source.setChecked(bool(checked))
    checkbox.toggled.connect(changed)


def selected_framework_method(framework):
    selected = framework.state.__dict__.get('selected_method') or framework.state.selected_winner
    if not selected and getattr(framework, 'cmb_final_method', None) is not None:
        selected = _combo_text(framework.cmb_final_method)
    return canonical_method(selected)


def framework_sd_source(framework, method):
    name = {'OK':'chkOKUncertaintyLayer','UK':'chkOKUncertaintyLayer',
            'RF':'chkRFUncertaintyLayer','RK':'chkRKUncertaintyLayer'}.get(canonical_method(method))
    workspace = getattr(framework, '_execution_workspace', None)
    worker = getattr(workspace, 'plugin', None)
    control = getattr(getattr(worker, 'dlg', None), name, None) if name else None
    pending = framework.__dict__.get('_pending_framework_sd_options', {})
    key = canonical_method(method)
    if control is not None and key in pending:
        control.setChecked(pending[key])
    return control


def configure_framework_selector(framework, result=None):
    """Enable only outputs of the selected, successfully executed method."""
    selector = getattr(framework, '_uncertainty_map_selector', None)
    if selector is None: return
    method = selected_framework_method(framework)
    supported = method in ('OK','UK','RF','RK')
    checkbox = getattr(framework.dlg, 'chkFrameworkUncertaintyLayer', None)
    source = framework_sd_source(framework, method)
    if checkbox is not None:
        checkbox.setEnabled(supported)
        blocked = checkbox.blockSignals(True)
        checkbox.setChecked(source.isChecked() if source is not None else
            framework.__dict__.get('_pending_framework_sd_options', {}).get(method, True))
        checkbox.blockSignals(blocked)
    result = result or framework.state.__dict__.get('executed_result')
    matching = result is not None and canonical_method(result.method) == method
    paths = result_uncertainty_paths(result) if matching and supported else {}
    entries = dict(prediction=dict(label='Prediction'))
    for key in ordered_output_keys(method, paths):
        entries[key] = dict(label=output_label(key, method), path=paths[key],
                            value_label=output_value_label(result_target(result), key),
                            definition=result_output_definition(result, key))
    signature = (method, getattr(result, 'execution_id', None), tuple(paths.items()))
    if getattr(selector, '_execution_signature', None) != signature:
        selector.configure(entries)
        selector._execution_signature = signature
    selector.combo.setEnabled(bool(paths))
    if not paths:
        message = ('Run the selected method interpolation to produce its uncertainty maps.' if supported
                   else 'Uncertainty maps are available for Kriging, RF and RK.')
        _ui(selector.combo, 'setToolTip', message)
