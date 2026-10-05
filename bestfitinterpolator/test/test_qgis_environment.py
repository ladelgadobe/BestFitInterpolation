"""Check the actual installed providers and CRS APIs."""
from qgis.core import QgsProviderRegistry,QgsCoordinateReferenceSystem

def test_installed_qgis_providers():
    providers=QgsProviderRegistry.instance().providerList()
    assert "gdal" in providers and "ogr" in providers

def test_epsg_reference_system():
    assert QgsCoordinateReferenceSystem("EPSG:4326").isValid()
