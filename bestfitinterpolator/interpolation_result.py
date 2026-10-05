"""Explicit provenance for successfully produced interpolation results."""
import json
import uuid
from dataclasses import dataclass
from datetime import datetime,timezone
from qgis.core import QgsProject


def parameter_snapshot(configuration):
    """Capture executed settings, excluding training arrays and fitted objects."""
    keys=('method','backend','variable','target_name','points_layer','polygon_layer','pixel_size','params',
          'resolved_params','rf_params','search_mode','rf_search_mode','feature_names','model','nugget',
          'psill','var_range','variogram_fit','source','validation_sample_count','validation_full_sample_count')
    def simple(value):
        if value is None or isinstance(value,(str,bool,int,float)): return value
        if isinstance(value,dict): return {str(k):simple(v) for k,v in value.items() if k!='raster_path'}
        if isinstance(value,(list,tuple)): return [simple(v) for v in value]
        if hasattr(value,'model') and hasattr(value,'range_'):
            return {k:simple(getattr(value,k)) for k in ('model','nugget','psill','range_')}
        if hasattr(value,'item'): return value.item()
        return str(value)
    return {key:simple(configuration[key]) for key in keys if key in configuration}


@dataclass(frozen=True)
class InterpolationResult:
    execution_id: str
    method: str
    parameters_json: str
    raster_path: str
    layer_id: str
    executed_at: str

    @property
    def parameters(self):
        return json.loads(self.parameters_json)


def publish_result(owner,method,configuration,figure=None,raster_path=None):
    plugin=getattr(owner,'parent_plugin',None) or getattr(getattr(owner,'dlg',None),'_bfi_plugin',None) or owner
    path=raster_path or configuration.get('raster_path') or configuration.get('params',{}).get('raster_path')
    if not path: return None
    layers=[layer for layer in QgsProject.instance().mapLayers().values() if layer.source().split('|')[0]==str(path)]
    if not layers: return None
    layer=layers[-1]
    if not layer.isValid(): return None
    method='RF' if method=='RFE' else ('IDW' if str(method).startswith('IDW') else str(method).upper())
    result=InterpolationResult(uuid.uuid4().hex,method,json.dumps(parameter_snapshot(configuration),sort_keys=True),
                               str(path),layer.id(),datetime.now(timezone.utc).isoformat())
    layer.setCustomProperty('bestfitinterpolator/method',result.method)
    layer.setCustomProperty('bestfitinterpolator/executed_parameters',result.parameters_json)
    layer.setCustomProperty('bestfitinterpolator/execution_id',result.execution_id)
    if figure is not None: figure._bfi_execution_id=result.execution_id
    # Store provenance in the raster as well as in the current project.
    from osgeo import gdal
    dataset=gdal.Open(str(path),gdal.GA_Update)
    if dataset is not None:
        dataset.SetMetadataItem('BESTFIT_METHOD',result.method)
        dataset.SetMetadataItem('BESTFIT_EXECUTED_PARAMETERS',result.parameters_json)
        dataset.SetMetadataItem('BESTFIT_EXECUTION_ID',result.execution_id)
        dataset=None
    plugin._latest_produced_result=result
    purpose=getattr(plugin,'_bfi_interpolation_purpose','standalone')
    if purpose=='comparison': return result
    plugin._last_interpolation_result=result
    import copy
    plugin._last_interpolation_figure=copy.deepcopy(figure) if figure is not None else None
    framework=getattr(plugin,'framework_ctrl',None)
    if framework is not None and purpose=='final':
        framework.state.__dict__['executed_result']=result
        framework.report_state=None
        framework.state.__dict__.pop('report_state',None)
        if method in framework.state.validated_methods:
            framework.state.__dict__.setdefault('interpolation_outputs',{})[method]=layer.id()
        if figure is not None: framework._copy_source_figure_to_framework_map(figure)
        framework.refresh_from_state()
    return result


def executed_method(framework):
    result=framework.state.__dict__.get('executed_result')
    return result.method if result is not None else 'Not interpolated'
