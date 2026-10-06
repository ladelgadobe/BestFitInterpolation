"""Behavioral regressions for display preservation and executed-result identity."""
from types import SimpleNamespace
import tempfile
from pathlib import Path
import numpy as np
from matplotlib.figure import Figure
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtWidgets import QWidget,QVBoxLayout,QDialog,QRadioButton,QCheckBox,QSpinBox,QDoubleSpinBox
from bestfitinterpolator.mpl_compat import FigureCanvas


def events():
    QCoreApplication.processEvents()


def set_pixel_ratio(canvas, ratio):
    if hasattr(canvas, '_set_device_pixel_ratio'):
        canvas._set_device_pixel_ratio(ratio)
    else:
        # Matplotlib 3.1 reads the Qt ratio directly; inject a controlled test ratio.
        canvas.device_pixel_ratio = ratio


def test_larger_view_preserves_mask_palette_normalization_limits_and_updates():
    from bestfitinterpolator.mpl_compat import TwoSlopeNorm
    from bestfitinterpolator.larger_view import LargerViewDialog
    owner=QWidget(); layout=QVBoxLayout(owner)
    fig=Figure(); canvas=FigureCanvas(fig); canvas._bfi_is_map=True; layout.addWidget(canvas)
    ax=fig.subplots(); values=np.ma.array([[-3.,0.],[1.,5.]],mask=[[0,0],[1,0]])
    image=ax.imshow(values,cmap='plasma',norm=TwoSlopeNorm(0.,-3.,5.),extent=(10,20,30,40))
    fig.colorbar(image,ax=ax); ax.set_xlim(12,18); ax.set_ylim(31,39)
    canvas.draw(); window=LargerViewDialog(fig,owner); window.show();events()
    copy=window.figure.axes[0].images[0]
    assert copy.get_cmap().name=='plasma' and isinstance(copy.norm,TwoSlopeNorm)
    assert copy.get_clim()==(-3.,5.)
    np.testing.assert_array_equal(copy.get_array().mask,values.mask)
    np.testing.assert_array_equal(window.figure.axes[0].get_xlim(),ax.get_xlim())
    np.testing.assert_array_equal(window.figure.axes[0].get_ylim(),ax.get_ylim())
    assert window.settings_button.isVisible()
    canvas._bfi_map_display.controls.palette.setCurrentText('Magma');canvas.draw();events()
    assert window.figure.axes[0].images[0].get_cmap().name=='magma'
    np.testing.assert_array_equal(image.get_array().data,values.data)
    assert getattr(window.figure,'_bfi_brand_artist',None) is None
    window.close();owner.close();events()


def test_palette_choices_show_the_actual_gradient_and_controls_stay_in_popup():
    from bestfitinterpolator.map_controls import MapDisplayControls,scientific_colormap
    from bestfitinterpolator.compat import enum_value
    from qgis.PyQt.QtCore import Qt
    owner=QWidget();controls=MapDisplayControls(owner)
    assert not controls.isVisible()
    assert controls.palette.count()==8
    for i in range(controls.palette.count()):
        icon=controls.palette.itemIcon(i)
        assert not icon.isNull()
        pixels=icon.pixmap(112,16).toImage()
        assert pixels.pixelColor(0,8)!=pixels.pixelColor(111,8)
        name=controls.palette.itemText(i)
        cmap=scientific_colormap(name if name in ('Spectral','RdYlGn') else name.lower())
        expected=np.array(cmap(0.)[:3])*255
        actual=pixels.pixelColor(0,8)
        np.testing.assert_allclose([actual.red(),actual.green(),actual.blue()],expected,atol=1)
    controls.show_settings();events()
    assert controls._settings_dialog.isVisible()
    controls._settings_dialog.close(); owner.close();events()


def test_framework_correlation_mirror_keeps_scalar_data_and_editable_colors():
    from bestfitinterpolator.mpl_compat import TwoSlopeNorm
    from bestfitinterpolator.framework_tab import FrameworkTabController
    from bestfitinterpolator.larger_view import LargerViewDialog
    source = Figure(); source_canvas = FigureCanvas(source)
    values = np.ma.array([[-1., .2], [.2, 1.]], mask=[[0, 1], [0, 0]])
    image = source.subplots().imshow(values, cmap='RdYlGn', norm=TwoSlopeNorm(0., -1., 1.))
    source.colorbar(image, ax=source.axes[0]); source_canvas.draw()
    source_colorbar_artists = tuple(source.axes[1].collections)
    owner = QWidget(); layout = QVBoxLayout(owner)
    placeholder = Figure(); target_canvas = FigureCanvas(placeholder); layout.addWidget(target_canvas)
    controller = SimpleNamespace(framework_corr_fig=placeholder)
    FrameworkTabController._copy_source_figure_to_target(controller, source, placeholder, target_canvas)
    owner.resize(600, 420); owner.show(); events(); target_canvas.draw()
    mirrored = target_canvas.figure.axes[0].images[0]
    assert controller.framework_corr_fig is target_canvas.figure
    assert mirrored.get_array().ndim == 2 and isinstance(mirrored.norm, TwoSlopeNorm)
    np.testing.assert_array_equal(mirrored.get_array().data, values.data)
    np.testing.assert_array_equal(mirrored.get_array().mask, values.mask)
    assert mirrored.get_clim() == (-1., 1.) and mirrored.get_cmap().name == 'RdYlGn'
    target_canvas._bfi_map_display.controls.palette.setCurrentText('Magma')
    target_canvas.draw(); events()
    assert mirrored.get_cmap().name == 'magma' and image.get_cmap().name == 'RdYlGn'
    colorbar = target_canvas.figure.axes[1]._colorbar
    assert colorbar.mappable is mirrored
    assert colorbar.cmap.name == 'magma' and colorbar.solids.get_cmap().name == 'magma'
    target_canvas._bfi_map_display.controls.automatic.setChecked(False)
    target_canvas._bfi_map_display.controls.minimum.setValue(-2.)
    target_canvas._bfi_map_display.controls.maximum.setValue(4.)
    target_canvas.draw(); events()
    assert colorbar.norm.vmin == -2. and colorbar.norm.vmax == 4.
    assert tuple(source.axes[1].collections) == source_colorbar_artists
    assert source.axes[1]._colorbar.cmap.name == 'RdYlGn' and image.get_clim() == (-1., 1.)
    enlarged = LargerViewDialog(target_canvas.figure, owner); enlarged.show(); events()
    assert enlarged.figure.axes[0].images[0].get_cmap().name == 'magma'
    assert enlarged.figure.axes[1]._colorbar.cmap.name == 'magma'
    assert enlarged.settings_button.isVisible()
    FrameworkTabController._copy_source_figure_to_target(controller, source, placeholder, target_canvas)
    events(); target_canvas.draw()
    assert controller.framework_corr_fig is target_canvas.figure
    assert target_canvas.figure.axes[0].images[0].get_cmap().name == 'RdYlGn'
    enlarged.close(); owner.close(); source_canvas.close(); events()


def test_idw_modes_disable_manual_inputs_and_tps_is_exclusive():
    from bestfitinterpolator.BestFitInterpolator import BestFitInterpolator
    plugin=BestFitInterpolator.__new__(BestFitInterpolator)
    dlg=QDialog();plugin.dlg=dlg
    dlg.manualParams=QRadioButton(dlg);dlg.chkOptimize=QCheckBox(dlg);dlg.TPS_Button=QCheckBox(dlg)
    dlg.manualNInput=QSpinBox(dlg);dlg.manualPInput=QDoubleSpinBox(dlg)
    plugin._wire_deterministic_controls()
    for i in range(3):
        dlg.manualParams.click(); assert dlg.manualNInput.isEnabled() and dlg.manualPInput.isEnabled()
        dlg.chkOptimize.click(); assert not dlg.manualNInput.isEnabled() and not dlg.manualPInput.isEnabled()
        dlg.TPS_Button.click(); assert not dlg.manualParams.isChecked() and not dlg.chkOptimize.isChecked()
        plugin._on_option_toggled('opt',True)
        assert dlg.chkOptimize.isChecked() and not dlg.TPS_Button.isChecked()
    dlg.close()


def test_execution_provenance_is_frozen_and_comparisons_cannot_replace_final_result():
    from osgeo import gdal
    from qgis.core import QgsRasterLayer,QgsProject
    from bestfitinterpolator.interpolation_result import publish_result
    project=QgsProject.instance()
    with tempfile.TemporaryDirectory() as temporary:
        path=str(Path(temporary)/'result.tif')
        dataset=gdal.GetDriverByName('GTiff').Create(path,2,2,1,gdal.GDT_Float32)
        dataset.SetGeoTransform((0,1,0,2,0,-1));dataset.GetRasterBand(1).WriteArray(np.ones((2,2)));dataset=None
        layer=QgsRasterLayer(path,'Result');project.addMapLayer(layer)
        plugin=SimpleNamespace()
        params={'p':2.,'n':8}
        result=publish_result(plugin,'TPS',{'params':params,'raster_path':path})
        assert result.method=='TPS' and layer.customProperty('bestfitinterpolator/method')=='TPS'
        params['p']=99
        assert result.parameters['params']['p']==2.
        returned=result.parameters; returned['params']['p']=-1
        assert result.parameters['params']['p']==2.
        plugin._bfi_interpolation_purpose='comparison'
        comparison=publish_result(plugin,'IDW',{'params':{'p':3},'raster_path':path})
        assert comparison.method=='IDW' and plugin._last_interpolation_result is result
        assert publish_result(plugin,'OK',{'raster_path':path+'.missing'}) is None
        assert plugin._last_interpolation_result is result
        dataset=gdal.Open(path); assert dataset.GetMetadataItem('BESTFIT_METHOD')=='IDW';dataset=None
        project.removeMapLayer(layer.id()); layer=None


def test_figures_have_no_logo_unless_explicitly_requested():
    from bestfitinterpolator.theme import style_figure,apply_branding_to_figure
    fig=Figure();FigureCanvas(fig);fig.subplots().plot([0,1],[0,1])
    for i in range(3): style_figure(fig)
    assert getattr(fig,'_bfi_brand_artist',None) is None
    brand=apply_branding_to_figure(fig,enabled=True)
    assert brand is not None
    style_figure(fig);assert fig._bfi_brand_artist is brand


def test_standalone_interpolation_does_not_populate_or_replace_framework_output():
    from osgeo import gdal
    from qgis.core import QgsRasterLayer,QgsProject
    from bestfitinterpolator.interpolation_result import publish_result
    calls=[]
    framework=SimpleNamespace(state=SimpleNamespace(validated_methods=['TPS','RK']),report_state=None,
                              refresh_from_state=lambda:calls.append('refresh'),
                              _copy_source_figure_to_framework_map=lambda fig:calls.append(fig))
    plugin=SimpleNamespace(framework_ctrl=framework)
    with tempfile.TemporaryDirectory() as temporary:
        path=str(Path(temporary)/'result.tif')
        dataset=gdal.GetDriverByName('GTiff').Create(path,2,2,1,gdal.GDT_Float32)
        dataset.SetGeoTransform((0,1,0,2,0,-1));dataset.GetRasterBand(1).WriteArray(np.ones((2,2)));dataset=None
        layer=QgsRasterLayer(path,'Scoped result');QgsProject.instance().addMapLayer(layer)
        standalone=publish_result(plugin,'RK',{'raster_path':path})
        assert standalone is plugin._last_interpolation_result
        assert 'executed_result' not in framework.state.__dict__ and not calls
        plugin._bfi_interpolation_purpose='final'
        final=publish_result(plugin,'TPS',{'raster_path':path})
        assert framework.state.executed_result is final and calls==['refresh']
        plugin._bfi_interpolation_purpose='standalone'
        publish_result(plugin,'RK',{'raster_path':path})
        assert plugin._last_interpolation_result.method=='RK' and framework.state.executed_result is final
        assert calls==['refresh']
        QgsProject.instance().removeMapLayer(layer.id());layer=None


def test_validation_palette_is_absent_after_navigation_and_in_larger_view():
    from bestfitinterpolator.map_controls import disable_display_settings
    from bestfitinterpolator.larger_view import LargerViewDialog
    owner=QWidget();layout=QVBoxLayout(owner)
    fig=Figure();canvas=FigureCanvas(fig);layout.addWidget(canvas)
    image=fig.subplots().imshow([[0.,1.],[1.,0.]],cmap='viridis')
    owner.show();canvas.draw();events();assert canvas._bfi_settings_button.isVisible()
    disable_display_settings(canvas)
    owner.hide();owner.show();canvas.draw();events()
    assert not canvas._bfi_settings_button.isVisible() and canvas._bfi_open_settings is None
    large=LargerViewDialog(fig,owner);large.show();events()
    assert not hasattr(large,'settings_button') and image.get_cmap().name=='viridis'
    large.close();owner.close();events()


def test_html_report_is_portable_and_preserves_enabled_sections_and_metadata():
    from qgis.PyQt.QtGui import QPixmap,QColor
    from bestfitinterpolator.report_model import ReportState,ReportSection,ReportFigure,export_report_html
    with tempfile.TemporaryDirectory() as temporary:
        image_path=Path(temporary)/'figure with spaces.png'
        pixmap=QPixmap(4,4);pixmap.fill(QColor('#008eab'));assert pixmap.save(str(image_path))
        state=ReportState(study_name='<Study & name>',sections=[
            ReportSection('required','Executed output',body='<p>TPS</p>',mandatory=True,enabled=False),
            ReportSection('image','Map',figures=[ReportFigure('Map','<img src="'+image_path.as_uri()+'">')]),
            ReportSection('hidden','Excluded section',body='DO NOT EXPORT',enabled=False)])
        output=Path(export_report_html(state,Path(temporary)/'report.html')).read_text(encoding='utf-8')
        assert '<details' in output and 'href="#section-0"' in output
        assert 'data:image/png;base64,' in output and 'src="file:' not in output
        assert '&lt;Study &amp; name&gt;' in output and 'DO NOT EXPORT' not in output
        assert 'TPS' in output


def test_framework_figure_sync_never_freezes_canvas_size_and_respects_pixel_ratio():
    from bestfitinterpolator.framework_tab import FrameworkTabController
    owner=QWidget();layout=QVBoxLayout(owner);fig=Figure();canvas=FigureCanvas(fig);layout.addWidget(canvas)
    fig.subplots().plot([0,1],[1,0]);owner.resize(800,600);owner.show();events()
    minimum=canvas.minimumSize()
    for ratio in (1.,1.5,2.):
        set_pixel_ratio(canvas, ratio)
        for width,height in ((800,600),(640,480),(1000,700)):
            owner.resize(width,height);events()
            FrameworkTabController._sync_figure_to_canvas(None,fig,canvas)
            canvas.draw();events()
            assert canvas.minimumSize()==minimum
            np.testing.assert_allclose(fig.bbox.size,(canvas.width()*ratio,canvas.height()*ratio),atol=1.)
    owner.close();events()


def test_export_draw_does_not_replace_the_embedded_framework_map():
    from types import MethodType
    from bestfitinterpolator.framework_tab import FrameworkTabController
    owner=QWidget();layout=QVBoxLayout(owner)
    source=Figure();source_canvas=FigureCanvas(source);layout.addWidget(source_canvas)
    source.subplots().imshow([[0.,1.],[2.,3.]],cmap='viridis');source._bfi_execution_id='test-execution'
    target=FigureCanvas(Figure());layout.addWidget(target)
    controller=SimpleNamespace(plugin=SimpleNamespace(),state=SimpleNamespace(executed_result=SimpleNamespace(execution_id='test-execution')),
                               interpolation_canvas=target)
    controller._copy_source_figure_to_framework_map=MethodType(FrameworkTabController._copy_source_figure_to_framework_map,controller)
    owner.resize(800,700);owner.show();events();source_canvas.draw()
    controller._copy_source_figure_to_framework_map(source);events()
    mirrored=controller.interpolation_fig
    with tempfile.TemporaryDirectory() as temporary:
        source.savefig(str(Path(temporary)/'export.png'),dpi=300,bbox_inches='tight')
        assert controller.interpolation_fig is mirrored
    set_pixel_ratio(source_canvas,1.5);source_canvas.draw();events()
    assert controller.interpolation_fig is not mirrored
    for iteration in range(4): events()
    target.draw()
    from bestfitinterpolator.mpl_compat import canvas_pixel_ratio
    ratio=canvas_pixel_ratio(target)
    assert target.figure.dpi==target._bfi_base_dpi*ratio
    np.testing.assert_allclose(target.figure.bbox.size,(target.width()*ratio,target.height()*ratio),atol=1.)
    owner.close();events()
