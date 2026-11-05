"""Input coverage must not silently collapse to a small raster intersection."""
from types import SimpleNamespace
import numpy as np
from qgis.core import QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsPointXY, QgsProject
from bestfitinterpolator.covariate_sampling import CovariateSampler, severe_coverage_loss, coverage_message


def test_coverage_metadata_supports_frames_without_pandas_attrs():
    from bestfitinterpolator.covariate_sampling import frame_coverage, set_frame_coverage
    legacy = SimpleNamespace(columns=['x', 'y', 'value'])
    coverage = dict(supplied=114, retained=114)
    set_frame_coverage(legacy, coverage)
    assert frame_coverage(legacy) == coverage
    assert legacy.columns == ['x', 'y', 'value'] and not hasattr(legacy, 'attrs')
    assert frame_coverage(SimpleNamespace()) is None


def test_coverage_metadata_preserves_modern_frame_values_and_columns():
    import pandas as pd
    from bestfitinterpolator.covariate_sampling import frame_coverage, set_frame_coverage
    frame = pd.DataFrame({'x': [1., 2.], 'value': [3., 4.]})
    before = frame.copy(deep=True)
    coverage = dict(supplied=2, retained=2)
    set_frame_coverage(frame, coverage)
    assert frame_coverage(frame) == coverage
    np.testing.assert_array_equal(frame.to_numpy(), before.to_numpy())
    assert list(frame.columns) == list(before.columns)


class Raster:
    def __init__(self, crs, sample, name):
        self._crs, self._sample, self._name = crs, sample, name
    def crs(self): return self._crs
    def source(self): return self._name + '.tif'
    def dataProvider(self): return SimpleNamespace(sample=self._sample)


def test_each_predictor_uses_its_own_crs_transform():
    source = QgsCoordinateReferenceSystem('EPSG:32723')
    geographic = QgsCoordinateReferenceSystem('EPSG:4326')
    point = QgsPointXY(276000., 7488500.)
    expected = QgsCoordinateTransform(source, geographic, QgsProject.instance()).transform(point)
    observed = []
    def sample_geographic(actual, band):
        observed.append(actual)
        return (3., abs(actual.x()-expected.x()) < 1e-10 and abs(actual.y()-expected.y()) < 1e-10)
    layers = [Raster(source, lambda p, b: (2., True), 'Projected'), Raster(geographic, sample_geographic, 'Geographic')]
    sampler = CovariateSampler(['Projected', 'Geographic'], layers, source, QgsProject.instance())
    assert sampler.sample(point) == [2., 3.]
    assert observed and sampler.summary(1, 1)['retained'] == 1


def test_zero_values_remain_valid_and_missing_counts_are_per_predictor():
    crs = QgsCoordinateReferenceSystem('EPSG:32723')
    layers = [Raster(crs, lambda p, b: (np.nan, False), 'Missing'), Raster(crs, lambda p, b: (0., True), 'Zero')]
    sampler = CovariateSampler(['Missing', 'Zero'], layers, crs, QgsProject.instance())
    assert sampler.sample(QgsPointXY(1., 2.)) is None
    summary = sampler.summary(1, 0)
    assert [p['valid'] for p in summary['predictors']] == [0, 1]
    assert [p['missing'] for p in summary['predictors']] == [1, 0]
    assert 'Missing.tif' in coverage_message(summary)


def test_severe_loss_guard_distinguishes_the_reported_failure_from_edge_nodata():
    assert severe_coverage_loss(dict(supplied=114, retained=8))
    assert severe_coverage_loss(dict(supplied=43055, retained=2419))
    assert not severe_coverage_loss(dict(supplied=114, retained=112))
    assert not severe_coverage_loss(dict(supplied=43055, retained=42443))


def raster_file(tmp_path, values, nodata=None):
    from osgeo import gdal, osr
    from qgis.core import QgsRasterLayer
    path = tmp_path/'predictor.tif'
    values = np.asarray(values, dtype=np.float32)
    dataset = gdal.GetDriverByName('GTiff').Create(str(path), values.shape[1], values.shape[0], 1, gdal.GDT_Float32)
    dataset.SetGeoTransform((0., 1., 0., float(values.shape[0]), 0., -1.))
    srs = osr.SpatialReference(); srs.ImportFromEPSG(3857); dataset.SetProjection(srs.ExportToWkt())
    band = dataset.GetRasterBand(1); band.WriteArray(values)
    if nodata is not None: band.SetNoDataValue(nodata)
    band = None; dataset = None
    layer = QgsRasterLayer(str(path), 'Predictor')
    assert layer.isValid()
    return layer


def test_stale_display_provider_does_not_truncate_calculation_data(tmp_path, monkeypatch):
    layer = raster_file(tmp_path, np.arange(16).reshape(4,4))
    original = layer.dataProvider()
    stale = SimpleNamespace(sample=lambda p,b: (np.nan, False),
        useSourceNoDataValue=original.useSourceNoDataValue,
        userNoDataValues=original.userNoDataValues)
    monkeypatch.setattr(layer, 'dataProvider', lambda: stale)
    sampler = CovariateSampler(['Predictor'], [layer], layer.crs(), QgsProject.instance())
    values = [sampler.sample(QgsPointXY(column+.5, 4-row-.5))[0]
              for row in range(4) for column in range(4)]
    np.testing.assert_array_equal(values, np.arange(16))
    assert sampler.summary(16,16)['predictors'][0]['valid'] == 16


def test_private_reader_preserves_explicit_source_and_user_nodata_rules(tmp_path):
    from qgis.core import QgsRasterRange
    layer = raster_file(tmp_path, [[0.,1.],[-9999.,3.]], nodata=-9999.)
    original = layer.dataProvider()
    original.setUseSourceNoDataValue(1, False)
    original.setUserNoDataValue(1, [QgsRasterRange(0.,0.)])
    sampler = CovariateSampler(['Predictor'], [layer], layer.crs(), QgsProject.instance())
    assert sampler.sample(QgsPointXY(.5,1.5)) is None
    assert sampler.sample(QgsPointXY(1.5,1.5)) == [1.]
    assert sampler.sample(QgsPointXY(.5,.5)) == [-9999.]
    assert sampler.sample(QgsPointXY(1.5,.5)) == [3.]
    assert not original.useSourceNoDataValue(1)
    assert [(r.min(),r.max()) for r in original.userNoDataValues(1)] == [(0.,0.)]
