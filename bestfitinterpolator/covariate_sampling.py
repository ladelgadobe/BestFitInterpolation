"""Sample each predictor in its own CRS and account for rejected input rows."""
import numpy as np
from qgis.core import QgsCoordinateTransform, QgsPointXY, QgsRasterLayer


class CovariateSampler:
    def __init__(self, names, layers, source_crs, project):
        self.names = list(names)
        self.layers = list(layers)
        # Display providers can retain stale read state in a long QGIS session.
        # Keep private file readers alive for this extraction, with the same
        # source and explicit NoData rules, without altering project layers.
        self.readers = []
        self.providers = []
        for layer in self.layers:
            source_provider = layer.dataProvider()
            if isinstance(layer, QgsRasterLayer) and layer.providerType() == 'gdal':
                reader = QgsRasterLayer(layer.source(), layer.name(), 'gdal')
                if not reader.isValid():
                    raise ValueError('Could not open predictor raster: ' + layer.source())
                provider = reader.dataProvider()
                provider.setUseSourceNoDataValue(1, source_provider.useSourceNoDataValue(1))
                provider.setUserNoDataValue(1, source_provider.userNoDataValues(1))
                self.readers.append(reader)
            else:
                provider = source_provider
            self.providers.append(provider)
        self.transforms = [QgsCoordinateTransform(source_crs, layer.crs(), project)
                           if source_crs.isValid() and layer.crs().isValid() and source_crs != layer.crs()
                           else None for layer in layers]
        self.valid_counts = [0] * len(layers)

    def sample(self, point):
        values = []
        for index, (provider, transform) in enumerate(zip(self.providers, self.transforms)):
            try:
                sample_point = QgsPointXY(point)
                if transform is not None:
                    sample_point = transform.transform(sample_point)
                value, ok = provider.sample(sample_point, 1)
                value = float(value) if ok and value is not None else float('nan')
            except Exception:
                value = float('nan')
            if np.isfinite(value):
                self.valid_counts[index] += 1
            values.append(value)
        return values if np.isfinite(values).all() else None

    def summary(self, supplied, retained):
        return dict(supplied=int(supplied), retained=int(retained),
                    fraction=float(retained / supplied) if supplied else 0.,
                    predictors=[dict(name=name, source=layer.source(), crs=layer.crs().authid(),
                                     valid=int(count), missing=int(supplied-count))
                                for name, layer, count in zip(self.names, self.layers, self.valid_counts)])


def severe_coverage_loss(summary):
    """Reject a silently truncated run, while allowing ordinary edge NoData.

    This is a catastrophic-input-loss guard, not a predictive-accuracy criterion.
    It does not impute, replace or silently remove a selected predictor.
    """
    return bool(summary['supplied'] and summary['retained'] * 2 < summary['supplied'])


def coverage_message(summary):
    lines = ['Complete predictor data: {retained} / {supplied}.'.format(**summary)]
    lines += ["Predictor '{}': {} / {}\n{}".format(item['name'], item['valid'], summary['supplied'], item['source'])
              for item in summary['predictors']]
    lines.append('Less than half of the requested input has complete predictors. Check the listed raster sources, CRS and NoData coverage before running interpolation.')
    return '\n\n'.join(lines)
