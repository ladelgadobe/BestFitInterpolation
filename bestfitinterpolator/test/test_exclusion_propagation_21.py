"""Regression tests for explicit observation exclusions and stale model inputs."""
from types import SimpleNamespace
import numpy as np
from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY
from bestfitinterpolator.diagnostics_ui import capture_data, feature_in_analysis, SpatialDiagnosticsDialog
from bestfitinterpolator.framework_sdi_dialog import FrameworkSDIDialog
from bestfitinterpolator.machine_learning_tab import MachineLearningTabController


def fixture():
    layer=QgsVectorLayer('Point?crs=EPSG:31983&field=value:double','Exclusion regression','memory')
    features=[]
    for i in range(12):
        f=QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(i*7.,float(i%3))))
        f.setAttributes([1000. if i==5 else float(i)])
        features.append(f)
    layer.dataProvider().addFeatures(features)
    QgsProject.instance().addMapLayer(layer)
    plugin=SimpleNamespace(dlg=SimpleNamespace(Points=SimpleNamespace(currentText=lambda:layer.name()),
        Points_2=SimpleNamespace(currentText=lambda:'value')), diagnostics_states={})
    state,_=capture_data(plugin)
    return layer, plugin, state


def test_framework_sdi_direct_reader_omits_excluded_observations():
    layer,plugin,state=fixture()
    try:
        state.decide([state.ids[5]],'Exclude')
        inputs=FrameworkSDIDialog._read_plugin_dataset(SimpleNamespace(plugin=plugin))
        assert len(inputs.z)==11 and 1000. not in inputs.z
        assert layer.featureCount()==12
        state.decide([state.ids[5]],'Keep')
        restored=FrameworkSDIDialog._read_plugin_dataset(SimpleNamespace(plugin=plugin))
        assert len(restored.z)==12 and 1000. in restored.z
    finally:
        QgsProject.instance().removeMapLayer(layer.id())


def bare_ml():
    controller=object.__new__(MachineLearningTabController)
    controller.dlg=SimpleNamespace()
    controller.covariate_layers={'retained_covariate':object()}
    controller._last_rf_interpolation_config={'points_df':'old training data'}
    controller._last_svm_interpolation_config={'points_df':'old training data'}
    controller._last_rf_cv_result={'old':True}
    controller._last_svm_cv_result={'old':True}
    return controller


def test_clearing_ml_results_invalidates_saved_validation_populations():
    controller=bare_ml()
    controller.clear_plots()
    assert controller._last_rf_interpolation_config is None
    assert controller._last_svm_interpolation_config is None
    assert controller._last_rf_cv_result is None
    assert controller._last_svm_cv_result is None


def test_analysis_reset_keeps_covariates_predictor_selection_and_settings():
    controller=bare_ml()
    covariates=controller.covariate_layers.copy()
    controller._active_covariate_selection=['retained_covariate']
    controller._standardization_for_extraction=True
    controller._extracted_headers=['old']; controller._extracted_rows=[[1.]]
    controller.reset_for_analysis_change()
    assert controller.covariate_layers==covariates
    assert controller._active_covariate_selection==['retained_covariate']
    assert controller._standardization_for_extraction is True
    assert controller._extracted_rows is None and controller._extracted_headers is None


def test_decision_ui_invalidates_only_effective_population_changes():
    layer,plugin,state=fixture()
    calls=[]
    plugin._on_analysis_mask_changed=lambda *args:calls.append(args)
    rows=[]
    table=SimpleNamespace(selectionModel=lambda:SimpleNamespace(selectedRows=lambda:rows))
    dialog=SimpleNamespace(state=state, plugin=plugin, table=table, render=lambda:None)
    try:
        SpatialDiagnosticsDialog.decide(dialog,'Exclude')
        assert not calls and not state.decisions
        rows.append(SimpleNamespace(row=lambda:5))
        SpatialDiagnosticsDialog.decide(dialog,'Keep')
        assert not calls
        SpatialDiagnosticsDialog.decide(dialog,'Exclude')
        assert calls==[(layer.id(),'value')] and state.analysis_mask.sum()==11
        SpatialDiagnosticsDialog.decide(dialog,'Exclude')
        assert len(calls)==1
        SpatialDiagnosticsDialog.decide(dialog,'Keep')
        assert len(calls)==2 and state.analysis_mask.sum()==12
        SpatialDiagnosticsDialog.decide(dialog,'Exclude')
        SpatialDiagnosticsDialog.decide(dialog,'Reset')
        assert len(calls)==4 and state.analysis_mask.sum()==12 and not state.decisions
        assert layer.featureCount()==12
    finally:
        QgsProject.instance().removeMapLayer(layer.id())


def test_exclusion_is_scoped_by_layer_and_target_and_survives_recapture():
    layer,plugin,state=fixture()
    other=QgsVectorLayer('Point?crs=EPSG:31983&field=value:double','Other layer','memory')
    try:
        features=list(layer.getFeatures())
        excluded=features[5]
        state.decide([excluded.id()],'Exclude')
        refreshed,_=capture_data(plugin)
        assert not feature_in_analysis(plugin,layer,excluded)
        assert refreshed.decisions[int(excluded.id())]=='Exclude'
        assert feature_in_analysis(plugin,other,excluded)
        plugin.dlg.Points_2.currentText=lambda:'different_target'
        assert feature_in_analysis(plugin,layer,excluded)
    finally:
        QgsProject.instance().removeMapLayer(layer.id())


def test_cancellation_after_worker_return_never_applies_its_old_result():
    from bestfitinterpolator import async_jobs
    from qgis.PyQt.QtWidgets import QWidget
    original_task,original_application=async_jobs.QgsTask,async_jobs.QgsApplication
    class Task:
        canceled=False
        def isCanceled(self): return self.canceled
        def cancel(self): self.canceled=True
    task=Task(); pending={}; applied=[]
    def create(title,worker,on_finished):
        pending['worker'],pending['finished']=worker,on_finished
        return task
    async_jobs.QgsTask=SimpleNamespace(fromFunction=create)
    async_jobs.QgsApplication=SimpleNamespace(taskManager=lambda:SimpleNamespace(addTask=lambda t:None))
    owner=QWidget()
    try:
        async_jobs.submit(owner,'Old population',lambda canceled:[1000.],lambda error,value:applied.append((error,value)))
        result=pending['worker'](task)
        task.cancel()
        pending['finished'](None,result)
        assert len(applied)==1 and isinstance(applied[0][0],InterruptedError) and applied[0][1] is None
        assert not owner._bfi_jobs
    finally:
        async_jobs.QgsTask,async_jobs.QgsApplication=original_task,original_application
        owner.deleteLater()
