"""Regressions for removed Matplotlib APIs and interrupted Qt construction."""
from unittest.mock import patch
import matplotlib
from matplotlib import cm
from qgis.PyQt.QtWidgets import QWidget
from bestfitinterpolator.map_controls import scientific_colormap, MapDisplayControls


def test_registry_does_not_call_removed_cm_get_cmap():
    registry=getattr(matplotlib,'colormaps',None)
    if registry is None:
        registry={name:cm.get_cmap(name) for name in ('viridis','plasma','Spectral')}
    with patch.object(matplotlib,'colormaps',registry,create=True), \
         patch.object(cm,'get_cmap',side_effect=AssertionError('Removed API was called'),create=True):
        for name in ('viridis','plasma','Spectral'):
            assert scientific_colormap(name).name==name
        assert scientific_colormap('unavailable-palette').name=='viridis'
        controls=MapDisplayControls()
        assert controls.palette.count()==8
        assert not any(controls.palette.itemIcon(i).isNull() for i in range(controls.palette.count()))
        controls.close()


def test_old_matplotlib_lookup_and_missing_turbo_fallback():
    registry=getattr(matplotlib,'colormaps',None)
    legacy=cm.get_cmap if registry is None else lambda name:registry[name]
    maps={name:legacy(name) for name in ('viridis','plasma')}
    calls=[]
    def old_lookup(name):
        calls.append(name)
        if name not in maps: raise ValueError(name)
        return maps[name]
    with patch.object(matplotlib,'colormaps',None,create=True), \
         patch.object(cm,'get_cmap',side_effect=old_lookup,create=True):
        assert scientific_colormap('plasma').name=='plasma'
        assert scientific_colormap('turbo').name=='viridis'
    assert calls==['plasma','turbo','viridis']


def test_failed_palette_creation_leaves_no_orphan_controls():
    parent=QWidget()
    before=parent.findChildren(QWidget)
    with patch('bestfitinterpolator.map_controls.palette_icon',side_effect=RuntimeError('Palette failure')):
        try: MapDisplayControls(parent)
        except RuntimeError: pass
        else: raise AssertionError('Palette failure was hidden')
    assert parent.findChildren(QWidget)==before
    parent.close()
