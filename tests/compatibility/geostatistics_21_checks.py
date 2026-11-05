"""Real QGIS UI, prediction rasters and original validation checks."""
import json
import numpy as np
from osgeo import gdal
from qgis.PyQt.QtWidgets import QPushButton
from bestfitinterpolator.compat import is_alive


def check_geostatistics_21(suite, events, wait_jobs):
    p, dlg = suite.plugin, suite.plugin.dlg
    dlg.mainTabs.setCurrentIndex(2); events(); p._update_ok_context()
    p.ok_ctrl._active._set_model_combo_by_token("spherical")
    evidence = []
    for backend in ("MoM", "REML"):
        dlg.cmbOKFitMethod.setCurrentText(backend); events()
        for degree in (1, 0):
            dlg.cmbOKKrigingType.setCurrentIndex(degree); events()
            active = p.ok_ctrl._active
            active._on_interpolate_clicked(); events()
            assert p._last_ok_interpolation is not None, suite.alerts[-4:]
            state = p._last_ok_interpolation
            assert state["trend_degree"] == degree and state["backend"] == backend
            assert p._last_interpolation_result.method == ("UK" if degree else "OK")
            assert p._last_interpolation_result.parameters["trend_degree"] == degree
            assert active._map_cache is not None
            maps = active._map_cache["maps"]
            assert np.array_equal(np.isfinite(maps["prediction"]), np.isfinite(maps["variance"]))
            np.testing.assert_allclose(maps["std"] ** 2, maps["variance"], atol=1e-10)
            pred_ds, sd_ds = gdal.Open(active._last_output_path), gdal.Open(active._last_uncertainty_path)
            assert pred_ds and sd_ds
            assert pred_ds.GetGeoTransform() == sd_ds.GetGeoTransform()
            assert pred_ds.GetProjection() == sd_ds.GetProjection()
            assert (pred_ds.RasterXSize, pred_ds.RasterYSize) == (sd_ds.RasterXSize, sd_ds.RasterYSize)
            np.testing.assert_allclose(sd_ds.ReadAsArray(), maps["std"], rtol=1e-6, equal_nan=True)
            pred_ds = sd_ds = None
            dlg.cmbOKMapOutput.setCurrentIndex(1); events()
            assert active._krig_map_fig.axes[0].get_title() == "Kriging standard deviation"
            dlg.grab().save(str(suite.output / f'geostatistics-{backend}-{"UK" if degree else "OK"}-uncertainty.png'))
            dlg.cmbOKMapOutput.setCurrentIndex(2); events()
            assert active._krig_map_fig.axes[0].get_title() == "Kriging variance"
            dlg.cmbOKMapOutput.setCurrentIndex(0); events()
            assert active._krig_map_fig.axes[0].get_title() == ("Universal Kriging" if degree else "Ordinary Kriging")
            # Different output units must never inherit prediction color limits.
            display = active._krig_map_canvas._bfi_map_display
            display.controls.minimum.setValue(10); display.controls.maximum.setValue(20)
            display.controls.automatic.setChecked(False); events()
            dlg.cmbOKMapOutput.setCurrentIndex(1); events()
            assert active._krig_map_fig.axes[0].collections[0].get_clim() != (10., 20.)
            dlg.cmbOKMapOutput.setCurrentIndex(0); events()
            np.testing.assert_allclose(active._krig_map_fig.axes[0].collections[0].get_clim(), (10., 20.))
            display.controls.automatic.setChecked(True); events()
            evidence.append(dict(backend=backend, trend_degree=degree, prediction=active._last_output_path,
                                 uncertainty=active._last_uncertainty_path, sample_count=len(state["sample_xyz"])))
    # Advanced semivariogram preview must use residuals in UK as well.
    dlg.cmbOKFitMethod.setCurrentText("MoM"); dlg.cmbOKKrigingType.setCurrentIndex(1); events()
    active = p.ok_ctrl._active
    from bestfitinterpolator.semivariogram_dialog import SemivariogramSettingsDialog
    advanced = SemivariogramSettingsDialog(active)
    advanced.show(); advanced.calculate(); wait_jobs(advanced)
    assert advanced.trend_degree == 1 and advanced.payload is not None
    advanced.close(); advanced.deleteLater(); events()
    active._on_interpolate_clicked(); events()
    p._cv_mode_ok = p.CV_KFOLD; p.spin_k_ok.setValue(3)
    p.run_ok_cv(); events()
    assert p._last_ok_cv_result["trend_degree"] == 1
    assert p._last_ok_cv_result["validation_n"] == len(p._last_ok_interpolation["sample_xyz"])
    # Original data/model controls retain their original grid cells and visibility.
    for name, grid, cell in (("valOKSamples", dlg.gridOKLeft, (1, 1)), ("cmbOKModel", dlg.gridOKRight, (1, 1))):
        widget = getattr(dlg, name)
        assert grid.getItemPosition(grid.indexOf(widget))[:2] == cell
        assert not widget.isHidden()
    assert not hasattr(dlg, "valOKContextSummary")
    # Spatial block controls and routes have been removed from every window.
    from qgis.PyQt.QtWidgets import QWidget
    assert not any('SpatialCV' in widget.objectName() or 'SpatialSettings' in widget.objectName()
                   or 'SpatialExport' in widget.objectName() for widget in dlg.findChildren(QWidget))
    assert not hasattr(p, '_spatial_cv_results')
    audit = {}
    for method in ('IDW', 'TPS'):
        (p.btn_idw_man if method == 'IDW' else p.btn_tps).setChecked(True)
        p.run_interpolation(); events()
        p.run_cross_validation(); events()
        scatter = p.det_val_fig.axes[0].collections[0].get_offsets()
        assert len(scatter) == len(p._get_last_det_interpolation_for_validation()['training_data']['z']) and np.isfinite(scatter).all(), (method, suite.alerts[-4:])
        np.testing.assert_allclose(scatter[:, 0], p._get_last_det_interpolation_for_validation()['training_data']['z'])
        assert np.any(np.abs(scatter[:, 0] - scatter[:, 1]) > 1e-6)
        audit[method] = 'original deterministic validation'
    ml, rk = p.ml_ctrl, p.rk_ctrl
    original_prompt = ml._prompt_covariate_selection
    ml._prompt_covariate_selection = lambda *args, **kwargs: ['x', 'y']
    ml._rf_manual_widget.setChecked(True); ml._svm_manual_widget.setChecked(True)
    dlg.spinRF_ntree_manual.setValue(10); dlg.spinRF_nodesize_manual.setValue(1)
    try:
        for method in ('RF', 'SVM'):
            getattr(ml, '_on_run_' + method.lower() + '_interpolation')(); events()
            getattr(ml, '_on_run_' + method.lower() + '_cross_validation')(); events()
            result = getattr(ml, '_last_' + method.lower() + '_cv_result')
            assert result is not None, (method, suite.alerts[-4:])
            assert result['validation_strategy'] in ('loocv', 'kfold')
            audit[method] = result['validation_strategy']
    finally:
        ml._prompt_covariate_selection = original_prompt
    rk._rk_manual_widget.setChecked(True); dlg.spinRK_ntree_manual.setValue(10)
    rk._fit_rf_stage(feature_names=['x', 'y'], prompt_for_predictors=False)
    rk._fit_variogram_stage(); rk._run_rk_prediction(); events()
    rk._on_run_rk_cv_clicked(); events()
    assert rk._last_rk_cv_result is not None, suite.alerts[-4:]
    assert rk._last_rk_cv_result['validation_strategy'] in ('loocv', 'kfold')
    audit['RK'] = rk._last_rk_cv_result['validation_strategy']
    framework = p.framework_ctrl
    framework.load_from_data_tab(framework._collect_current_plugin_data())
    for method, name in framework.METHOD_CHECKBOXES.items():
        getattr(dlg, name).setChecked(method in ('IDW','TPS'))
    framework.on_run_validation_clicked(); events()
    assert set(framework.state.validated_methods) == {'IDW','TPS'}
    assert all(row.get('validation_strategy') != 'spatial_block_cv' for row in framework.state.validation_results)
    from bestfitinterpolator.report_model import snapshot_framework_report
    assert not any(section.key == 'spatial_cross_validation' for section in snapshot_framework_report(framework).sections)
    # Explicit exclusions still propagate through the original validation path.
    from bestfitinterpolator.diagnostics_ui import capture_data
    state, source_layer = capture_data(p)
    excluded_id = int(state.ids[np.flatnonzero(state.analysis_mask)[0]])
    original_count = int(state.analysis_mask.sum()); source_count = source_layer.featureCount()
    state.decide([excluded_id], 'Exclude')
    p._on_analysis_mask_changed(state.layer_id, state.field_name); events()
    dlg.cmbOKKrigingType.setCurrentIndex(0); events()
    p.ok_ctrl._active._on_interpolate_clicked(); events()
    p.run_ok_cv(); events()
    assert len(p._last_ok_interpolation['sample_xyz']) == original_count - 1
    scatter = p.ok_cv_fig.axes[0].collections[0].get_offsets()
    assert len(scatter) == original_count - 1 and np.isfinite(scatter).all()
    np.testing.assert_allclose(scatter[:, 0], p._last_ok_interpolation['sample_xyz'][:, 2])
    assert source_layer.featureCount() == source_count
    state.decide([excluded_id], 'Reset')
    p._on_analysis_mask_changed(state.layer_id, state.field_name); events()
    assert capture_data(p)[0].analysis_mask.sum() == original_count
    p._clear_all_plots(preserve_covariates=True); events()
    dlg.cmbOKKrigingType.setCurrentIndex(0); dlg.cmbOKFitMethod.setCurrentText('MoM'); events()
    p._cv_mode_ok = p.CV_AUTO
    (suite.output / 'geostatistics_21_audit.json').write_text(json.dumps(dict(status='PASS', runs=evidence,
        original_validation=audit, spatial_block_controls_removed=True,
        original_widget_grid_positions_preserved=True, exclusions_propagated=True), indent=2), encoding='utf-8')
