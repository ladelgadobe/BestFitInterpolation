"""Shared display-only controls for Matplotlib maps and map comparisons."""
from dataclasses import dataclass
import numpy as np
from qgis.PyQt.QtCore import pyqtSignal, QObject, QEvent, QSize, Qt
from qgis.PyQt.QtGui import QPixmap, QPainter, QColor, QIcon
from qgis.PyQt.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QFormLayout, QDialog, QToolButton, QLabel, QComboBox, QDoubleSpinBox, QCheckBox, QPushButton
from .theme import PALETTES, action_icon, apply_theme
from .compat import enum_value, is_alive


@dataclass
class MapDisplayState:
    palette: str = "viridis"
    automatic: bool = True
    minimum: float = 0.
    maximum: float = 1.
    scale: float = 5000.


def palette_icon(name):
    """Display the actual colormap, including the fallback on old Matplotlib."""
    cmap=scientific_colormap(name)
    pixmap=QPixmap(112,16)
    painter=QPainter(pixmap)
    for x in range(112):
        rgba=cmap(x/111.)
        painter.setPen(QColor.fromRgbF(*map(float,rgba)))
        painter.drawLine(x,0,x,15)
    painter.end()
    return QIcon(pixmap)


class SettingsButton(QToolButton):
    def __init__(self, canvas, callback):
        super().__init__(canvas)
        self.setProperty('bfiSettings',True)
        self.setIcon(action_icon('settings')); self.setIconSize(QSize(19,19))
        self.setFixedSize(30,30)
        self.setToolTip('Visualization settings'); self.setAccessibleName('Visualization settings')
        self.clicked.connect(callback)
        canvas.installEventFilter(self)
        self.reposition()

    def reposition(self):
        if getattr(self.parentWidget(),'_bfi_no_display_settings',False):
            self.hide(); return
        self.move(max(0,self.parentWidget().width()-self.width()-8),8)
        self.raise_(); self.show()

    def eventFilter(self, obj, event):
        if event.type() in (enum_value(QEvent,'Type','Resize'),enum_value(QEvent,'Type','Show')):
            self.reposition()
        return False


class MapDisplayControls(QWidget):
    changed = pyqtSignal()
    fitRequested = pyqtSignal()
    scaleRequested = pyqtSignal(float)

    def __init__(self,parent=None):
        super().__init__(parent)
        self.state=MapDisplayState()
        self._customized=False
        layout=QVBoxLayout(self); layout.setContentsMargins(0,0,0,0); layout.setSpacing(10)
        form=QFormLayout(); form.setSpacing(8); layout.addLayout(form)
        self.scale=QDoubleSpinBox(); self.scale.setRange(1.,1.e12); self.scale.setDecimals(0); self.scale.setValue(5000.); self.scale.setKeyboardTracking(False)
        self.form=form
        scale_row=QHBoxLayout(); scale_row.addWidget(self.scale)
        scale_button=QPushButton("Set scale"); scale_button.clicked.connect(lambda:self.scaleRequested.emit(self.scale.value())); scale_row.addWidget(scale_button)
        self.scale_button=scale_button
        form.addRow('Scale 1 :',scale_row)
        fit=QPushButton("Fit to layer"); fit.clicked.connect(self.fitRequested); form.addRow('',fit)
        self.palette=QComboBox(); self.palette.setIconSize(QSize(112,16))
        for name in PALETTES: self.palette.addItem(palette_icon(name.lower() if name not in ('Spectral','RdYlGn') else name),name)
        form.addRow('Palette',self.palette)
        self.automatic=QCheckBox("Automatic value range"); self.automatic.setChecked(True); form.addRow('',self.automatic)
        self.minimum=QDoubleSpinBox(); self.maximum=QDoubleSpinBox()
        for label,spin in (("Min",self.minimum),("Max",self.maximum)):
            spin.setRange(-1.e15,1.e15); spin.setDecimals(6); spin.setKeyboardTracking(False); form.addRow(label,spin)
        self.maximum.setValue(1.)
        self.palette.currentIndexChanged.connect(self.update_state)
        self.automatic.toggled.connect(self.update_state)
        self.minimum.valueChanged.connect(self.update_state); self.maximum.valueChanged.connect(self.update_state)
        self.update_state()
        self._customized=False
        self.hide()

    def show_settings(self):
        dialog=getattr(self,'_settings_dialog',None)
        if not is_alive(dialog):
            dialog=QDialog(self.window()); dialog.setWindowTitle('Visualization settings')
            layout=QVBoxLayout(dialog); layout.setContentsMargins(16,16,16,16)
            layout.addWidget(self)
            close=QPushButton('Done'); close.clicked.connect(dialog.close); layout.addWidget(close)
            apply_theme(dialog); dialog.resize(370,300)
            self._settings_dialog=dialog
        self.show(); dialog.show(); dialog.raise_(); dialog.activateWindow()

    def update_state(self,*args):
        name=self.palette.currentText()
        self.state.palette=name if name in ('Spectral','RdYlGn') else name.lower()
        self.state.automatic=self.automatic.isChecked()
        self.state.minimum,self.state.maximum=self.minimum.value(),self.maximum.value()
        for spin in (self.minimum,self.maximum): spin.setEnabled(not self.state.automatic)
        if self.state.automatic or self.state.minimum < self.state.maximum:
            self.setToolTip(""); self._customized=True; self.changed.emit()
        else: self.setToolTip("Minimum must be smaller than maximum.")


def scientific_colormap(name):
    from matplotlib import cm
    try: return cm.get_cmap(name)
    except ValueError:
        # Turbo is absent in older Matplotlib. Use a named built-in fallback.
        return cm.get_cmap("viridis")


def common_value_range(*arrays):
    lows,highs=[],[]
    for array in arrays:
        array=np.ma.masked_invalid(array)
        valid=array.compressed()
        if valid.size: lows.append(float(np.min(valid))); highs.append(float(np.max(valid)))
    if not lows: return 0.,1.
    lo,hi=min(lows),max(highs)
    if lo==hi: hi=lo+max(abs(lo)*1.e-6,1.e-6)
    return lo,hi


class MatplotlibMapDisplay(QObject):
    def __init__(self,canvas,controls,meters_per_unit=1.):
        super().__init__(canvas)
        self.canvas,self.controls,self.meters_per_unit=canvas,controls,meters_per_unit
        self.extents={}
        controls.changed.connect(self.restyle); controls.fitRequested.connect(self.fit)
        controls.scaleRequested.connect(self.set_scale)

    def axes(self):
        return [ax for ax in self.canvas.figure.axes if ax.get_label()!="<colorbar>" and (ax.images or ax.collections or ax.lines or ax.patches)]

    def restyle(self):
        self.apply_current()
        self.canvas.draw_idle()

    def adopt_current(self, automatic=None):
        """Read an existing figure without applying defaults or changing its colors."""
        axes=self.axes()
        if not axes: return
        numeric=[a for a in list(axes[0].images)+list(axes[0].collections)
                 if a.get_array() is not None and np.ndim(a.get_array())<=2]
        if not numeric: return
        controls=self.controls
        widgets=(controls.palette,controls.minimum,controls.maximum,controls.automatic)
        blocked=[widget.blockSignals(True) for widget in widgets]
        try:
            artist=numeric[0]; name=artist.get_cmap().name
            index=controls.palette.findText(name,enum_value(Qt,'MatchFlag','MatchFixedString'))
            if index<0:
                controls.palette.addItem(palette_icon(name),name); index=controls.palette.count()-1
            controls.palette.setCurrentIndex(index)
            lo,hi=artist.get_clim()
            for spin,value in ((controls.minimum,lo),(controls.maximum,hi)):
                if value is not None: spin.setValue(value)
            if automatic is not None: controls.automatic.setChecked(automatic)
            controls.state.palette=name
            controls.state.minimum=controls.minimum.value(); controls.state.maximum=controls.maximum.value()
            controls.state.automatic=controls.automatic.isChecked()
            for spin in (controls.minimum,controls.maximum): spin.setEnabled(not controls.state.automatic)
            controls._customized=False
        finally:
            for widget,previous in zip(widgets,blocked): widget.blockSignals(previous)

    def apply_current(self):
        s=self.controls.state
        if not s.automatic and s.minimum>=s.maximum: return
        updated=[]
        for ax in self.axes():
            numeric=False
            for artist in list(ax.images)+list(ax.collections):
                data=artist.get_array()
                if data is None or not np.size(data) or np.ndim(data)>2: continue
                numeric=True
                artist.set_cmap(scientific_colormap(s.palette))
                if s.automatic: artist.set_clim(*common_value_range(data))
                else: artist.set_clim(s.minimum,s.maximum)
                updated.append(artist)
            if not numeric and not getattr(self.canvas,'_bfi_is_map',False):
                cmap=scientific_colormap(s.palette)
                lines=list(ax.lines)
                for i,line in enumerate(lines): line.set_color(cmap((i+.5)/max(1,len(lines))))
                bars=[p for p in ax.patches if p.get_facecolor()[-1]>0]
                for i,bar in enumerate(bars): bar.set_facecolor(cmap((i+.5)/max(1,len(bars))))
                if not s.automatic: ax.set_ylim(s.minimum,s.maximum)
        # Figure copies can lose the weak callback linking an artist to its colorbar.
        for ax in self.canvas.figure.axes:
            colorbar=getattr(ax,'_colorbar',None)
            if colorbar is not None and any(colorbar.mappable is artist for artist in updated):
                # deepcopy retains a built-in remove callback bound to the original list.
                for artist in [colorbar.solids]+list(getattr(colorbar,'solids_patches',[])):
                    if artist is not None and any(artist is child for child in ax._children):
                        artist._remove_method=ax._children.remove
                colorbar.update_normal(colorbar.mappable)

    def fit(self):
        for ax in self.axes():
            if ax.images:
                xmin,xmax,ymin,ymax=ax.images[0].get_extent(); ax.set_xlim(xmin,xmax); ax.set_ylim(ymin,ymax)
            else: ax.autoscale(enable=True)
        self.canvas.draw_idle()

    def set_scale(self,scale):
        getter=getattr(self,"units_getter",None)
        if getter is not None: self.meters_per_unit=getter()
        if self.meters_per_unit is None or self.meters_per_unit<=0:
            self.controls.setToolTip("Numeric scale requires a projected CRS with known linear units."); return
        self.controls.state.scale=scale
        for ax in self.axes():
            bbox=ax.get_window_extent(); dpi=self.canvas.figure.dpi
            width=bbox.width/dpi*.0254*scale/self.meters_per_unit
            height=bbox.height/dpi*.0254*scale/self.meters_per_unit
            x0,x1=ax.get_xlim(); y0,y1=ax.get_ylim(); cx,cy=(x0+x1)/2,(y0+y1)/2
            ax.set_xlim(cx-width/2,cx+width/2); ax.set_ylim(cy-height/2,cy+height/2)
        self.canvas.draw_idle()


def attach_map_controls(canvas):
    if getattr(canvas,'_bfi_no_display_settings',False) or getattr(canvas.figure,'_bfi_validation',False):
        return
    if getattr(canvas,"_bfi_map_display",None) is not None: return
    parent=canvas.parentWidget()
    if parent is None: return
    controls=MapDisplayControls(parent)
    display=MatplotlibMapDisplay(canvas,controls,getattr(canvas,"_bfi_meters_per_unit",None))
    if not getattr(canvas,'_bfi_is_map',False):
        controls.scale.setEnabled(False); controls.scale_button.setEnabled(False)
        controls.scale.setToolTip('Numeric map scale applies only to spatial maps.')
    display.adopt_current()
    canvas._bfi_open_settings=controls.show_settings
    canvas._bfi_settings_button=SettingsButton(canvas,controls.show_settings)
    cursor=parent
    while cursor is not None:
        plugin=getattr(cursor,"_bfi_plugin",None)
        if plugin is not None:
            display.units_getter=lambda: selected_map_units(plugin)
            break
        cursor=cursor.parentWidget()
    canvas._bfi_map_display=display


def disable_display_settings(canvas):
    """Validation keeps fixed scientific colors and its existing navigation actions."""
    canvas._bfi_no_display_settings=True
    canvas.figure._bfi_validation=True
    canvas._bfi_open_settings=None
    button=getattr(canvas,'_bfi_settings_button',None)
    if button is not None: button.hide()


def selected_map_units(plugin):
    """Resolve actual CRS linear units; geographic degrees have no fixed scale."""
    from qgis.core import QgsProject, QgsUnitTypes
    from osgeo import osr
    layers=QgsProject.instance().mapLayersByName(plugin.dlg.Points.currentText())
    if not layers or not layers[0].crs().isValid() or layers[0].crs().isGeographic(): return None
    crs=osr.SpatialReference()
    if crs.SetFromUserInput(layers[0].crs().toWkt()) != 0 or not crs.IsProjected(): return None
    return float(crs.GetLinearUnits())
