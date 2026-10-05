"""Check real Qt preview pixels without prescribing a theme or exact layout."""
import numpy as np
from qgis.PyQt.QtGui import QImage
from qgis.PyQt.QtWidgets import QTabWidget
from qgis.PyQt.QtCore import QCoreApplication
from bestfitinterpolator.compat import enum_value


def select_preview(canvas):
    ancestors=[]
    cursor=canvas
    while cursor is not None:
        ancestors.append(cursor)
        cursor=cursor.parentWidget()
    for widget in reversed(ancestors):
        if isinstance(widget,QTabWidget):
            for i in range(widget.count()):
                if widget.widget(i) in ancestors:
                    widget.setCurrentIndex(i)
                    break
    QCoreApplication.processEvents()


def assert_rendered(canvas, path):
    assert canvas.isVisible(), 'Preview is hidden: '+str(path)
    assert canvas.width()>100 and canvas.height()>80, 'Preview is clipped: {} ({} x {})'.format(path,canvas.width(),canvas.height())
    canvas.draw()
    image=canvas.grab().toImage().convertToFormat(enum_value(QImage,'Format','Format_RGBA8888'))
    pixels=np.frombuffer(image.bits().asstring(image.bytesPerLine()*image.height()),dtype=np.uint8)
    pixels=pixels.reshape(image.height(),image.bytesPerLine())[:,:image.width()*4].reshape(image.height(),image.width(),4)
    rgb=pixels[:,:,:3]
    assert float(rgb.mean())>10., 'Preview is black: '+str(path)
    assert float((rgb.min(axis=2)<235).mean())>.002, 'Preview is empty: '+str(path)
    assert float(rgb.std())>5., 'Preview has no plotted content: '+str(path)
    assert canvas.figure.axes, 'Preview has no axes: '+str(path)
    assert any(ax.images or ax.collections or ax.lines for ax in canvas.figure.axes if ax.get_label()!='<colorbar>'), 'Preview has no artists: '+str(path)
    assert image.save(str(path)), 'Could not preserve preview evidence'
    display=getattr(canvas,'_bfi_map_display',None)
    if display is not None:
        assert display.controls.isHidden(), 'Settings leaked into the tab'
        assert not canvas._bfi_settings_button.isHidden(), 'Missing visualization settings'
    return dict(width=image.width(),height=image.height(),mean=float(rgb.mean()),std=float(rgb.std()))
