"""Regression checks for strategy changes, visible method groups and model CV."""
import numpy as np
from qgis.PyQt.QtWidgets import QTabWidget
from bestfitinterpolator.compat import is_alive
from render_checks import assert_rendered,select_preview


def check_method_sections(plugin,output,events):
    from bestfitinterpolator.theme import COLORS
    from qgis.PyQt.QtGui import QColor
    dlg=plugin.dlg; original=(dlg.width(),dlg.height())
    dlg.mainTabs.setCurrentIndex(1)
    expected=QColor(COLORS['border'])
    for width,height in ((1000,700),(800,600)):
        dlg.resize(width,height); events()
        for name in ('groupIDWOptions','groupTPSOptions'):
            group=getattr(dlg,name)
            assert group.isVisible() and group.property('bfiSection')
            image=group.grab().toImage()
            matches=0
            for y in range(image.height()//3,2*image.height()//3):
                colors=[image.pixelColor(x,y) for x in (0,1,2,image.width()-3,image.width()-2,image.width()-1)]
                matches+=any(max(abs(c.red()-expected.red()),abs(c.green()-expected.green()),abs(c.blue()-expected.blue()))<12 for c in colors)
            assert matches>=image.height()/6.,'Method group has no visible separating border: '+name
            assert image.save(str(output/('{}-{}.png'.format(name,width))))
        for widget in (dlg.radManualParams,dlg.chkOptimize,dlg.spinNeighbors,dlg.spinPower):
            assert widget.width()>=widget.minimumSizeHint().width(),'IDW control was clipped: {} ({} < {})'.format(widget.objectName(),widget.width(),widget.minimumSizeHint().width())
        dlg.grab().save(str(output/('deterministic-options-{}.png'.format(width))))
    dlg.resize(*original); events()


def check_strategy_switches(plugin,output,events,wait_jobs):
    from bestfitinterpolator.semivariogram_dialog import SemivariogramSettingsDialog
    dlg=plugin.dlg
    dlg.mainTabs.setCurrentIndex(2); events()
    for i,mode in enumerate(('REML','MoM','REML','MoM','Automatic','MoM')):
        previous=plugin.ok_ctrl._active
        dlg.cmbOKFitMethod.setCurrentText(mode); events()
        c=plugin.ok_ctrl._active
        actual='REML' if mode=='Automatic' else mode
        assert plugin.ok_ctrl.strategy_name==actual and c._ok_fit_method==actual
        if c is not previous: assert not previous._connections
        canvas=c._krig_vario_canvas
        assert is_alive(canvas) and canvas.parentWidget() is dlg.CanvasOKVariogram
        assert canvas in [dlg.CanvasOKVariogram.layout().itemAt(j).widget() for j in range(dlg.CanvasOKVariogram.layout().count())]
        select_preview(canvas); assert_rendered(canvas,output/('switch-{}-{}.png'.format(i,actual)))
        labels=[line.get_label() for line in canvas.figure.axes[0].lines]
        assert ('Experimental' in labels)==(actual=='MoM'),labels
        assert (c._exp_lags is None)==(actual=='REML')
        before=canvas.figure.axes[0].lines[-1].get_ydata().copy()
        dlg.cmbOKModel.setCurrentText('Gau' if dlg.cmbOKModel.currentText()!='Gau' else 'Sph'); events()
        after=canvas.figure.axes[0].lines[-1].get_ydata()
        assert not np.array_equal(before,after),'The theoretical curve did not change with the model'
        dlg.mainTabs.setCurrentIndex(0); events(); dlg.mainTabs.setCurrentIndex(2); events()
        assert_rendered(canvas,output/('return-{}-{}.png'.format(i,actual)))
        if mode in ('Automatic','MoM') and i>=4:
            window=SemivariogramSettingsDialog(c)
            window.show(); window.run_validation(); wait_jobs(window)
            assert window.engine.profile==('ok_reml' if actual=='REML' else 'ok_mom')
            assert len(window.rows)==3 and all(not r.get('error') for r in window.rows),window.status.text()
            if actual=='REML': assert all(r['selection']=='reml_cv' for r in window.rows)
            assert 'LCCC' in window.status.text()
            labels=[line.get_label() for line in window.fig.axes[0].lines]
            assert ('Experimental' in labels)==(actual=='MoM')
            window.table.selectRow(1); selected=window.rows[1]
            window.apply_settings(); events()
            np.testing.assert_allclose(c._read_params_from_ui(),selected.get('fitted_params',tuple(selected[k] for k in ('nugget','psill','range'))),atol=5e-4,rtol=0)
            assert c._get_selected_model()==selected['model_key']
            assert_rendered(canvas,output/('validated-{}.png'.format(actual)))
            window.close(); window.deleteLater(); events()


def check_framework_validation(plugin,output,events,wait_jobs):
    from bestfitinterpolator.framework_sdi_dialog import FrameworkSDIDialog
    parent=FrameworkSDIDialog(parent=plugin.dlg,plugin=plugin,framework_ctrl=plugin.framework_ctrl)
    parent.show(); events()
    assert parent.btn_model_validation.isVisible()
    for mode in ('REML','MoM'):
        parent.spin_max_distance.setValue(parent.spin_max_distance.value()*.9)
        parent._fit_method=mode
        parent.btn_model_validation.click(); events()
        window=parent._model_validation_dialog; wait_jobs(window)
        assert window.isVisible() and len(window.rows)==3,window.status.text()
        assert all(not r.get('error') and r['fit_method']==mode for r in window.rows),window.rows
        assert all(r['maximum_distance']==parent.spin_max_distance.value() and r['lag']==parent.spin_lag_width.value() for r in window.rows)
        assert 'highest R²' in window.status.text() and 'RMSE' in window.status.text()
        ranked=sorted(window.rows,key=lambda r:(-r['r2'],r['rmse']))
        assert ranked==window.rows
        window.grab().save(str(output/('framework-validation-{}.png'.format(mode))))
        window.table.selectRow(1); row=window.rows[1]
        window.apply.click(); events()
        assert parent.cmb_model.currentText()==row['model']
        np.testing.assert_allclose(parent._read_params_from_controls(),row['fitted_params'],rtol=0,atol=6e-7)
        labels=[line.get_label() for line in parent.fig.axes[0].lines]
        assert ('Experimental' in labels)==(mode=='MoM')
        parent.spin_lag_width.setValue(parent.spin_lag_width.value()*.95); events()
        window.apply.click(); events()
        assert not window.rows and not window.apply.isEnabled(),'Stale validation was applied'
        window.close(); events()
    controller=plugin.framework_ctrl
    collector=controller._collect_current_plugin_data
    data=collector(); changed=dict(data,z=np.asarray(data['z'])+.1)
    try:
        controller._collect_current_plugin_data=lambda:changed
        parent.btn_model_validation.click(); events()
        window=parent._model_validation_dialog
        assert not window.rows and not getattr(window,'_bfi_jobs',set())
        assert 'dataset changed' in window.status.text()
        window.close(); events()
    finally: controller._collect_current_plugin_data=collector
    parent.close(); parent.deleteLater(); events()
