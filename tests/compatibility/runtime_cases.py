"""Functional widgets, signals and calculations; no pixel-perfect assertions."""
import importlib
import json
import sys
import time
import traceback
from pathlib import Path
import numpy as np
from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY
from qgis.PyQt.QtCore import QCoreApplication, QEvent, QUrl
from qgis.PyQt.QtWidgets import QWidget, QMessageBox, QTabWidget
from bestfitinterpolator.compat import enum_value, is_alive


def events():
    QCoreApplication.processEvents()
    QCoreApplication.sendPostedEvents(None, enum_value(QEvent, 'Type', 'DeferredDelete'))


def wait_jobs(owner):
    deadline = time.monotonic() + 60
    while getattr(owner, '_bfi_jobs', set()):
        events()
        time.sleep(.01)
        if time.monotonic() > deadline:
            raise RuntimeError('Background task timeout')
    events()


class Iface:
    def __init__(self, alerts):
        from qgis.gui import QgsMapCanvas
        self.window = QWidget()
        self.canvas = QgsMapCanvas(self.window)
        self.toolbar, self.menu, self.alerts = [], [], alerts

    def mainWindow(self): return self.window
    def mapCanvas(self): return self.canvas
    def messageBar(self): return self
    def addToolBarIcon(self, action): self.toolbar.append(action)
    def addPluginToMenu(self, menu, action): self.menu.append(action)
    def removeToolBarIcon(self, action):
        if action in self.toolbar: self.toolbar.remove(action)
    def removePluginMenu(self, menu, action):
        if action in self.menu: self.menu.remove(action)
    def pushMessage(self, *args, **kwargs):
        if kwargs.get('level', 0) >= 2: self.alerts.append(str(args))
    def pushWarning(self, *args): self.alerts.append(str(args))
    def pushCritical(self, *args): self.alerts.append(str(args))


class RuntimeCases:
    def __init__(self, app, output, pdf):
        self.app, self.output, self.pdf = app, output, pdf
        self.plugin = None
        self.numerical_results = {}
        self.slot_errors, self.alerts = [], []
        self.previous_hook = sys.excepthook
        sys.excepthook = lambda kind, error, tb: self.slot_errors.append(''.join(traceback.format_exception(kind, error, tb)))
        self.message_methods = {name: getattr(QMessageBox, name) for name in ('warning', 'critical', 'information', 'question')}
        for name in ('warning', 'critical'):
            setattr(QMessageBox, name, lambda *a, **k: self.alerts.append(str(a[1:])))
        QMessageBox.information = lambda *a, **k: None
        QMessageBox.question = lambda *a, **k: enum_value(QMessageBox, 'StandardButton', 'Yes')

    def cases(self):
        return [('plugin_import', self.imports), ('classFactory', self.factory),
                ('initGui_unload_signals', self.gui_lifecycle), ('main_window', self.main_window),
                ('data_loading', self.data), ('deterministic_semivariogram_geostatistics', self.numerical),
                ('spatial_diagnostics', self.diagnostics), ('regression_kriging', self.regression),
                ('framework', self.framework), ('map_comparison', self.comparison),
                ('report', self.report), ('repeated_open_close', self.reopen)]

    def imports(self):
        root = Path(__file__).resolve().parents[2] / 'bestfitinterpolator'
        for path in sorted(root.glob('*.py')):
            importlib.import_module('bestfitinterpolator.' + path.stem)

    def factory(self):
        from bestfitinterpolator import classFactory
        self.iface = Iface(self.alerts)
        self.plugin = classFactory(self.iface)
        assert self.plugin is not None
        self.plugin._ensure_project_saved = lambda: True
        self.plugin._ensure_output_dir = lambda: setattr(self.plugin, 'output_dir', str(self.output))

    def gui_lifecycle(self):
        for iteration in range(2):
            self.plugin.initGui()
            assert len(self.iface.toolbar) == len(self.iface.menu) == 1
            self.plugin.actions[-1].trigger()
            events()
            assert self.plugin.dlg.isVisible()
            self.plugin.unload()
            events()
            assert not self.iface.toolbar and not self.iface.menu
        self.plugin.run()
        events()

    def main_window(self):
        p = self.plugin
        assert p.framework_ctrl is not None and p.rk_ctrl is not None and p.ml_ctrl is not None
        labels = [p.dlg.mainTabs.tabText(i) for i in range(p.dlg.mainTabs.count())]
        assert all(name in labels for name in ('Data', 'Deterministics', 'Geostatistics', 'Machine Learning', 'Framework'))
        assert p.dlg.grpRKRF is not None and p.dlg.grpRKKriging is not None
        for tabs in p.dlg.findChildren(QTabWidget):
            for i in range(tabs.count()): tabs.setCurrentIndex(i); events()
        from bestfitinterpolator.mpl_compat import FigureCanvas
        from matplotlib.figure import Figure
        figure = Figure()
        canvas = FigureCanvas(figure)
        figure.subplots().plot([0, 1], [1, 0])
        canvas.draw()
        canvas.close()

    def data(self):
        p = self.plugin
        points = QgsVectorLayer('Point?crs=EPSG:31983&field=value:double', 'Synthetic points', 'memory')
        assert points.isValid()
        features = []
        rng = np.random.default_rng(12)
        for i, (x, y) in enumerate(rng.uniform(0, 100, (25, 2))):
            feature = QgsFeature(points.fields())
            feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(float(x), float(y))))
            feature.setAttributes([None if i == 24 else float(np.sin(x / 20.) + np.cos(y / 30.))])
            features.append(feature)
        points.dataProvider().addFeatures(features)
        points.updateExtents()
        boundary = QgsVectorLayer('Polygon?crs=EPSG:31983', 'Synthetic boundary', 'memory')
        feature = QgsFeature()
        feature.setGeometry(QgsGeometry.fromWkt('POLYGON((-10 -10,110 -10,110 110,-10 110,-10 -10))'))
        boundary.dataProvider().addFeatures([feature])
        boundary.updateExtents()
        for layer in (points, boundary): QgsProject.instance().addMapLayer(layer)
        p.dlg.Points.setCurrentText(points.name())
        p.dlg.Points_2.setCurrentText('value')
        p.dlg.poly.setCurrentText(boundary.name())
        p.dlg.spinPixelSize.setValue(30)
        p.dlg.cmbOKFitMethod.setCurrentText('MoM')
        events()
        from bestfitinterpolator.diagnostics_ui import capture_data
        self.state, self.points = capture_data(p)
        assert self.state.analysis_mask.sum() == 24 and self.points.featureCount() == 25
        expected = [item for item in self.alerts if 'Removed 1 rows with incomplete or invalid data.' in item]
        assert len(expected) <= 1
        self.alerts[:] = [item for item in self.alerts if item not in expected]
        data = p.framework_ctrl._collect_current_plugin_data()
        assert len(data['z']) == 24 and np.isfinite(data['z']).all()

    def numerical(self):
        from numerical import calculate
        baseline = json.loads((Path(__file__).resolve().parents[1] / 'data/numerical_baseline.json').read_text(encoding='utf-8'))
        self.numerical_results = calculate()
        for key, expected in baseline['results'].items():
            actual = self.numerical_results[key]
            if key == 'lisa': assert actual == expected, 'NUMERICAL LISA classes differ'
            else: np.testing.assert_allclose(actual, expected, rtol=baseline['rtol'], atol=baseline['atol'], err_msg=key)
        self.plugin.dlg.mainTabs.setCurrentIndex(2)
        events()
        controller = self.plugin.ok_ctrl._active
        assert controller._exp_lags is not None and len(controller._exp_lags) > 1
        controller._on_interpolate_clicked()
        controller._on_run_cv_clicked()
        events()
        assert controller._krig_map_fig.axes and self.plugin.ok_cv_fig.axes

    def diagnostics(self):
        from bestfitinterpolator.diagnostics_engine import DiagnosticsEngine, classify
        from bestfitinterpolator.diagnostics_ui import SpatialDiagnosticsDialog
        result = DiagnosticsEngine().calculate(self.state.coordinates, self.state.values, {'permutations': 99})
        assert 'global_moran' in result and 'MAD' in result['methods'] and 'IQR' in result['methods']
        self.state.result = result
        spatial = dict(centered=np.array([2., -2., 2., -2.]), spatial_lag=np.array([1., -1., -1., 1.]), pseudo_p=np.full(4, .01), neighbors=np.ones(4))
        assert classify(np.zeros(4, dtype=bool), spatial)[0].tolist() == ['HH', 'LL', 'HL', 'LH']
        for iteration in range(3):
            dialog = SpatialDiagnosticsDialog(self.plugin, self.state, self.points)
            dialog.show(); events()
            dialog.info_button.click(); events()
            assert dialog.information_dialog.isVisible()
            dialog.close(); dialog.deleteLater(); events()

    def regression(self):
        p = self.plugin
        rk = p.rk_ctrl
        rk._fit_rf_stage(feature_names=['x', 'y'], prompt_for_predictors=False)
        assert rk._rf_model is not None and np.isfinite(rk._residuals).all()
        rk._fit_variogram_stage()
        assert rk._variogram_fit is not None
        rk._run_rk_prediction()
        assert rk._last_interpolation_config is not None
        rk._on_run_rk_cv_clicked()
        assert rk._last_rk_cv_result is not None

    def framework(self):
        f = self.plugin.framework_ctrl
        f.load_from_data_tab(f._collect_current_plugin_data())
        for method, name in f.METHOD_CHECKBOXES.items():
            checkbox = f._get(name)
            if checkbox is not None: checkbox.setChecked(method in ('IDW', 'TPS'))
        f.on_run_validation_clicked()
        assert set(f.state.validated_methods) == {'IDW', 'TPS'}
        assert f.state.validation_results and f.state.selected_winner in ('IDW', 'TPS')
        for method in ('IDW', 'TPS'): assert f._dispatch_and_register_map(method)

    def comparison(self):
        from bestfitinterpolator.map_comparison import difference_arrays, check_grids
        a = np.array([[1., 2.], [np.nan, -9999.]])
        b = np.array([[0., 4.], [1., 2.]])
        diff = difference_arrays(a, b, nodata_a=-9999.)
        np.testing.assert_allclose(diff[0], [1., -2.])
        np.testing.assert_allclose(np.abs(diff[0]), [1., 2.])
        assert np.isnan(diff[1]).all()
        grid = dict(shape=(2, 2), crs='EPSG:31983', transform=(0., 1., 0., 2., 0., -1.))
        check_grids(grid, grid)
        for altered in (dict(grid, shape=(3, 2)), dict(grid, transform=(0., 2., 0., 2., 0., -2.))):
            try: check_grids(grid, altered)
            except ValueError: pass
            else: raise AssertionError('Mismatched extent/pixel size was accepted')
        widget = self.plugin.framework_ctrl.comparison_widget
        widget.refresh()
        assert widget.method_a.count() == widget.method_b.count() == 2
        widget.calculate(); wait_jobs(widget)
        assert widget.state.statistics['count'] > 0 and len(widget.axes) == 3

    def report(self):
        from bestfitinterpolator.report_model import snapshot_framework_report, report_html, export_report_html
        from bestfitinterpolator.report_builder import ReportBuilderDialog, export_report_pdf
        state = snapshot_framework_report(self.plugin.framework_ctrl)
        assert state.sections and '<table' in report_html(state)
        assert any(section.figures for section in state.sections)
        for iteration in range(3):
            dialog = ReportBuilderDialog(state, self.plugin.dlg)
            dialog.show(); events(); dialog.close(); dialog.deleteLater(); events()
        export_report_html(state, str(self.output / 'report.html'))
        from qgis.PyQt.QtGui import QDesktopServices
        from qgis.PyQt.QtWidgets import QFileDialog
        browser_open=QDesktopServices.openUrl
        save_dialog=QFileDialog.getSaveFileName
        opened=[]
        QDesktopServices.openUrl=lambda url:opened.append(url.toLocalFile()) or True
        QFileDialog.getSaveFileName=lambda *a,**k:(_ for _ in ()).throw(AssertionError('HTML preview must not ask for a download path'))
        try:
            overview=self.plugin.framework_ctrl.report_overview
            overview.export_html()
            assert len(opened)==1 and Path(opened[0]).is_file()
            document=Path(opened[0]).read_text(encoding='utf-8')
            assert 'data-sections="close"' in document and 'scrollIntoView' in document
            assert 'bfi:' not in document and 'data:image/png;base64,' in document
            overview.navigate(QUrl('bfi:validation'))
            assert self.plugin.framework_ctrl.framework_subtabs.currentWidget() is self.plugin.dlg.tabFrameworkValidation
            overview.navigate(QUrl('bfi:comparison'))
            assert self.plugin.framework_ctrl.framework_subtabs.currentWidget() is self.plugin.framework_ctrl.comparison_widget
        finally:
            QDesktopServices.openUrl=browser_open
            QFileDialog.getSaveFileName=save_dialog
        if self.pdf:
            path = export_report_pdf(state, str(self.output / 'smoke.pdf'))
            assert Path(path).read_bytes().startswith(b'%PDF')

    def reopen(self):
        from bestfitinterpolator.semivariogram_dialog import SemivariogramSettingsDialog
        p = self.plugin
        controller = p.ok_ctrl._active
        for iteration in range(3):
            dialog = SemivariogramSettingsDialog(controller, p.dlg)
            dialog.show(); events(); dialog.close(); dialog.deleteLater(); events()
        for iteration in range(3):
            previous = p.dlg
            previous.close(); events(); p.run(); events()
            assert p.dlg is not previous and not is_alive(previous)
            assert p.dlg.mainTabs.currentIndex() == 0 and p.dlg.Points.currentText() == ''
            assert p.framework_ctrl is not None and not p.framework_ctrl.interpolation_fig.axes

    def cleanup(self):
        if self.plugin is not None: self.plugin.unload()
        events()
        for name, method in self.message_methods.items(): setattr(QMessageBox, name, method)
        sys.excepthook = self.previous_hook
        QgsProject.instance().removeAllMapLayers()
