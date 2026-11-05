"""End-to-end exclusion audit through real UI decisions and numerical backends."""
from functools import wraps
import importlib
import json
import numpy as np
from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY
from osgeo import gdal, osr


def check_exclusions(suite, events, wait_jobs):
    from bestfitinterpolator.diagnostics_ui import capture_data, SpatialDiagnosticsDialog
    from bestfitinterpolator.framework_sdi_dialog import FrameworkSDIDialog
    from bestfitinterpolator.semivariogram_dialog import SemivariogramSettingsDialog
    from bestfitinterpolator.report_model import snapshot_framework_report, report_html
    p=suite.plugin; dlg=p.dlg; ml=p.ml_ctrl; framework=p.framework_ctrl; rk=p.rk_ctrl
    dlg.mainTabs.setCurrentIndex(0); events()
    # Retain Framework's existing 30-sample eligibility threshold for OK.
    samples=QgsVectorLayer('Point?crs=EPSG:31983&field=value:double','Exclusion workflow samples','memory')
    sample_features=[]
    for i,(x,y) in enumerate(np.random.default_rng(19).uniform(0.,100.,(37,2))):
        feature=QgsFeature(samples.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(x),float(y))))
        feature.setAttributes([None if i==36 else float(np.sin(x/20.)+np.cos(y/30.))])
        sample_features.append(feature)
    samples.dataProvider().addFeatures(sample_features); samples.updateExtents()
    QgsProject.instance().addMapLayer(samples)
    dlg.Points.setCurrentText(samples.name()); dlg.Points_2.setCurrentText('value'); events()
    dlg.mainTabs.setCurrentIndex(2); events(); p._update_ok_context()
    dlg.mainTabs.setCurrentIndex(0); events()
    state,layer=capture_data(p)
    original_ids=[f.id() for f in layer.getFeatures()]
    original_values=[f['value'] for f in layer.getFeatures()]
    row=int(np.flatnonzero(state.analysis_mask)[0]); fid=int(state.ids[row])
    excluded_xy=state.coordinates[row].copy(); excluded_value=float(state.values[row])
    total=int(state.analysis_mask.sum()); retained=total-1
    assert total==36 and layer.featureCount()==37
    raster_path=suite.output/'exclusion-covariate.tif'
    ds=gdal.GetDriverByName('GTiff').Create(str(raster_path),12,12,1,gdal.GDT_Float32)
    ds.SetGeoTransform((-10.,10.,0.,110.,0.,-10.))
    srs=osr.SpatialReference(); srs.ImportFromEPSG(31983); ds.SetProjection(srs.ExportToWkt())
    ds.GetRasterBand(1).WriteArray(np.arange(144,dtype=np.float32).reshape(12,12)); ds=None
    raster=QgsRasterLayer(str(raster_path),'Exclusion covariate'); assert raster.isValid()
    QgsProject.instance().addMapLayer(raster)
    ml.covariate_layers[raster.name()]=raster; dlg.listCovariates.addItem(raster.name())
    features=['x','y',raster.name()]
    ml._rf_manual_widget.setChecked(True); ml._rf_grid_widget.setChecked(False)
    ml._svm_manual_widget.setChecked(True); ml._svm_grid_widget.setChecked(False)
    dlg.spinRF_ntree_manual.setValue(20); dlg.spinRF_mtry_manual.setValue(2); dlg.spinRF_nodesize_manual.setValue(1)
    rk._rk_manual_widget.setChecked(True); rk._rk_grid_widget.setChecked(False)
    dlg.spinRK_ntree_manual.setValue(20); dlg.spinRK_mtry_manual.setValue(2); dlg.spinRK_nodesize_manual.setValue(1)
    # Real stale snapshots from prior cases plus explicit RF/SVM saved populations.
    ml._last_rf_interpolation_config={'points_df':'pre-exclusion'}
    ml._last_svm_interpolation_config={'points_df':'pre-exclusion'}
    ml._extracted_headers=['old']; ml._extracted_rows=[[excluded_value]]
    semivariogram=SemivariogramSettingsDialog(p.ok_ctrl._active)
    semivariogram.show(); events()
    sdi=FrameworkSDIDialog(parent=dlg,plugin=p,framework_ctrl=framework)
    sdi.show(); events()
    diagnostic=SpatialDiagnosticsDialog(p,state,layer)
    diagnostic.show(); diagnostic.calculate(); wait_jobs(diagnostic)
    diagnostic.table.selectRow(row); events()
    diagnostic.decide('Exclude'); events()
    assert state.analysis_mask.sum()==retained and layer.featureCount()==37
    assert ml._last_rf_interpolation_config is None and ml._last_svm_interpolation_config is None
    assert rk._last_interpolation_config is None and p._last_det_interpolation is None and p._last_ok_interpolation is None
    assert ml._extracted_rows is None and raster.name() in ml.covariate_layers
    assert raster.name() in [dlg.listCovariates.item(i).text() for i in range(dlg.listCovariates.count())]
    assert not framework.state.validation_results and framework.report_state is None
    from bestfitinterpolator.compat import is_alive
    assert not is_alive(semivariogram) or not semivariogram.isVisible()
    assert not sdi.isVisible()
    assert p._current_valid_sample_count()==retained
    assert len(p.ok_ctrl._active._read_xy_z()[2])==retained
    new_sdi=FrameworkSDIDialog(parent=dlg,plugin=p,framework_ctrl=framework)
    assert len(new_sdi._inputs.z)==retained
    direct=new_sdi._read_plugin_dataset()
    assert len(direct.z)==retained and excluded_value not in direct.z
    new_sdi.close(); new_sdi.deleteLater(); events()
    patches=[]; phase=['standalone']; auditing=[True]; calls={'standalone':{},'framework':{}}
    def register(label):
        counts=calls[phase[0]]; counts[label]=counts.get(label,0)+1
    def check_xy(x,y,label):
        if not auditing[0]: return
        x,y=np.asarray(x),np.asarray(y)
        assert not np.any((x==excluded_xy[0]) & (y==excluded_xy[1])),(phase[0],label,'excluded conditioning point')
        assert len(x)<=retained,(label,len(x))
        register(label)
    def replace(owner,name,wrapper):
        old=getattr(owner,name); patches.append((owner,name,old)); setattr(owner,name,wrapper(old))
    def array_wrapper(label):
        def make(original):
            @wraps(original)
            def wrapped(*args,**kwargs):
                x=args[0] if args else kwargs['x']; y=args[1] if len(args)>1 else kwargs['y']
                check_xy(x,y,label)
                return original(*args,**kwargs)
            return wrapped
        return make
    modules=['BestFitInterpolator','framework_tab','ok_r_integration_MoM','ok_r_integration_reml',
             'semivariogram_engine','RF_RegressionKriging','IDW_optimized','Thin_plate_spline']
    for name in modules:
        module=importlib.import_module('bestfitinterpolator.'+name)
        for function,label in (('idw_interpolation','IDW'),('tps_interpolation','TPS'),('ordinary_kriging_interpolation','OK/RK')):
            if callable(getattr(module,function,None)): replace(module,function,array_wrapper(label))
    def reml_wrapper(original):
        @wraps(original)
        def wrapped(*args,**kwargs):
            xy=np.asarray(args[0] if args else kwargs['coords'])
            check_xy(xy[:,0],xy[:,1],'REML')
            return original(*args,**kwargs)
        return wrapped
    bridge=importlib.import_module('bestfitinterpolator.reml_bridge')
    replace(bridge,'fit_variogram_reml',reml_wrapper)
    replace(bridge,'ok_predict',reml_wrapper)
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.svm import SVR
    def fitted_response(label):
        def make(original):
            @wraps(original)
            def wrapped(self,X,y,*args,**kwargs):
                if auditing[0]:
                    assert not np.any(np.asarray(y)==excluded_value),(phase[0],label,'excluded response')
                    assert len(y)<=retained
                    register(label)
                return original(self,X,y,*args,**kwargs)
            return wrapped
        return make
    replace(RandomForestRegressor,'fit',fitted_response('RF'))
    replace(SVR,'fit',fitted_response('SVM'))
    old_prompt=ml._prompt_covariate_selection
    ml._prompt_covariate_selection=lambda available:features
    def observed(values):
        values=np.asarray(values,dtype=float)
        assert len(values)==retained and not np.any(values==excluded_value)
    try:
        # Separate tabs: complete interpolation and the corresponding saved-data CV.
        for method,mode in (('IDW',p.MODE_IDW_MAN),('TPS',p.MODE_TPS)):
            (p.btn_idw_man if method=='IDW' else p.btn_tps).setChecked(True)
            p.run_interpolation(); events()
            saved=p._last_det_interpolation
            assert saved and len(saved['training_data']['z'])==retained,method
            p.run_cross_validation(); events()
            observed(p.det_val_fig.axes[0].collections[0].get_offsets()[:,0])
        for method in ('MoM','REML'):
            dlg.cmbOKFitMethod.setCurrentText(method); events()
            controller=p.ok_ctrl._active
            assert len(controller._read_xy_z()[2])==retained
            controller._on_interpolate_clicked(); controller._on_run_cv_clicked(); events()
            assert len(p._last_ok_interpolation['sample_xyz'])==retained
            observed(p.ok_cv_fig.axes[0].collections[0].get_offsets()[:,0])
        for method in ('rf','svm'):
            getattr(ml,'_on_run_'+method+'_interpolation')(); events()
            config=getattr(ml,'_last_'+method+'_interpolation_config')
            assert config and len(config['points_df'])==retained,method
            getattr(ml,'_on_run_'+method+'_cross_validation')(); events()
            observed(getattr(ml,'_last_'+method+'_cv_result')['observed'])
        rk._fit_rf_stage(feature_names=features,prompt_for_predictors=False)
        rk._fit_variogram_stage(); rk._run_rk_prediction(); rk._on_run_rk_cv_clicked(); events()
        assert len(rk._last_interpolation_config['train_df'])==retained
        observed(rk._last_rk_cv_result['observed'])
        # Framework: all six validation routes and all six prediction routes.
        phase[0]='framework'
        framework.load_from_data_tab(framework._collect_current_plugin_data())
        assert framework.state.sample_count==retained
        for method,name in framework.METHOD_CHECKBOXES.items():
            checkbox=framework._get(name)
            if checkbox is not None: checkbox.setChecked(True)
        dlg.mainTabs.setCurrentIndex(4); events()
        framework.on_run_validation_clicked(); events()
        assert {('RF' if m=='RFE' else m) for m in framework.state.validated_methods}=={'IDW','TPS','OK','RF','RK','SVM'},framework.state.validated_methods
        for result in framework.state.validation_results:
            observed(result['observed'])
        for method in ('IDW','TPS','OK','RFE','RK','SVM'):
            assert framework._dispatch_and_register_map(method),method
        report=report_html(snapshot_framework_report(framework))
        assert 'excluded by user: 1' in report and 'analysis observations: {}'.format(retained) in report
        for scope in calls:
            assert {'IDW','TPS','OK/RK','RF','SVM'} <= set(calls[scope]),calls[scope]
        diagnostic.grab().save(str(suite.output/'exclusion-decision-v2_1.png'))
        # Keep/Reset restores the valid observation and invalidates all new caches.
        auditing[0]=False
        phase[0]='standalone'
        diagnostic.table.selectRow(row); events(); diagnostic.decide('Keep'); events()
        assert state.analysis_mask.sum()==total
        assert len(p.ok_ctrl._active._read_xy_z()[2])==total
        frame,_,_=ml._build_points_dataframe_for_rf(features,False)
        assert len(frame)==total and excluded_value in frame['value'].to_numpy()
        assert ml._last_rf_interpolation_config is None and rk._last_interpolation_config is None
        assert not framework.state.validation_results and framework.report_state is None
        diagnostic.table.selectRow(row); events(); diagnostic.decide('Exclude'); events()
        diagnostic.table.selectRow(row); events(); diagnostic.decide('Reset'); events()
        assert state.analysis_mask.sum()==total and fid not in state.decisions
        assert [f.id() for f in layer.getFeatures()]==original_ids
        assert [f['value'] for f in layer.getFeatures()]==original_values
        receipt=dict(status='PASS',version='2.1',excluded_feature_id=fid,
            original_features=37,original_valid=total,analysis_valid=retained,
            restored_valid=total,source_layer_unchanged=True,calls=calls,
            standalone_methods=['IDW','TPS','OK MoM','OK REML','RF','SVM','RK'],
            framework_methods=['IDW','TPS','OK','RF','SVM','RK'])
        (suite.output/'exclusion_audit.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    finally:
        auditing[0]=False
        ml._prompt_covariate_selection=old_prompt
        for owner,name,original in reversed(patches): setattr(owner,name,original)
        if state.decisions.get(fid)=='Exclude':
            state.decide([fid],'Reset'); p._on_analysis_mask_changed(state.layer_id,state.field_name)
        diagnostic.close(); diagnostic.deleteLater(); events()
