# -*- coding: utf-8 -*-
"""Matplotlib Qt backend compatibility for QGIS 3.x and future Qt6 builds."""

try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as _FigureCanvas
    from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
except Exception:  # pragma: no cover - older QGIS/Matplotlib Qt5 stacks
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as _FigureCanvas
    from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar


from .theme import style_figure
from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtWidgets import QSizePolicy
from .compat import enum_value


def clone_figure(figure):
    """Clone our own figure graph on Matplotlib versions that forbid transform copies."""
    import copy
    try:
        cloned = copy.deepcopy(figure)
    except NotImplementedError:
        # These bytes originate only from the in-memory figure, never from external files.
        import pickle
        cloned = pickle.loads(pickle.dumps(figure,protocol=4))
    # Matplotlib 3.1 removes this required attribute from its serialized state.
    if hasattr(figure, '_cachedRenderer') and not hasattr(cloned, '_cachedRenderer'):
        cloned._cachedRenderer = None
    return cloned


def canvas_pixel_ratio(canvas):
    return getattr(canvas, 'device_pixel_ratio', getattr(canvas, '_dpi_ratio', 1.))
try:
    from matplotlib.colors import TwoSlopeNorm
except ImportError:
    try:
        from matplotlib.colors import DivergingNorm as TwoSlopeNorm
    except ImportError:
        import numpy as np
        from matplotlib.colors import Normalize
        class TwoSlopeNorm(Normalize):
            """Display-only centered normalization for older Matplotlib releases."""
            def __init__(self,vcenter=0.,vmin=None,vmax=None):
                super().__init__(vmin,vmax); self.vcenter=vcenter
            def __call__(self,value,clip=None):
                self.autoscale_None(value)
                return np.ma.masked_array(np.interp(value,[self.vmin,self.vcenter,self.vmax],[0.,.5,1.]),mask=np.ma.getmask(value))
            def inverse(self,value): return np.interp(value,[0.,.5,1.],[self.vmin,self.vcenter,self.vmax])

class FigureCanvas(_FigureCanvas):
    def __init__(self,figure):
        original_dpi=getattr(figure,'_original_dpi',figure.dpi)
        figure._set_dpi(original_dpi,forward=False)
        figure.dpi_scale_trans.clear().scale(original_dpi)
        figure.bbox.invalidate()
        super().__init__(figure)
        self._bfi_base_dpi=original_dpi
        self.setMinimumSize(120,160)
        self.setSizePolicy(enum_value(QSizePolicy,'Policy','Expanding'),enum_value(QSizePolicy,'Policy','Expanding'))

    def minimumSizeHint(self):
        return QSize(120,160)

    def sizeHint(self):
        return QSize(480,300)

    def draw(self):
        if self.isVisible() and self.width()>0 and self.height()>0:
            ratio=canvas_pixel_ratio(self)
            self.figure._original_dpi=self._bfi_base_dpi
            self.figure._set_dpi(self._bfi_base_dpi*ratio,forward=False)
            # Figure.__getstate__ resets DPI but retains the copied physical transform.
            if self.figure.dpi_scale_trans.get_matrix()[0,0]!=self.figure.dpi:
                self.figure.dpi_scale_trans.clear().scale(self.figure.dpi)
            self.figure.set_size_inches(self.width()*ratio/self.figure.dpi,self.height()*ratio/self.figure.dpi,forward=False)
            self.figure.bbox.invalidate()
        validation=getattr(self,'_bfi_no_display_settings',False) or getattr(self.figure,'_bfi_validation',False)
        if validation:
            from .map_controls import disable_display_settings
            disable_display_settings(self)
        if not validation and not getattr(self,'_bfi_display_source',False) and self.figure.axes:
            from .map_controls import attach_map_controls
            attach_map_controls(self)
            display=getattr(self,'_bfi_map_display',None)
            if display is not None and display.controls._customized: display.apply_current()
        style_figure(self.figure)
        geometry=(self.width(),self.height(),self.figure.dpi,tuple(id(ax) for ax in self.figure.axes))
        if self.isVisible() and self.width()>=250 and self.height()>=160 and geometry!=getattr(self,'_bfi_plot_geometry',None):
            axes=[ax for ax in self.figure.axes if ax.get_label()!='<colorbar>']
            if axes and all(getattr(ax,'get_subplotspec',lambda:None)() is not None for ax in axes):
                self.figure.tight_layout(pad=.8)
            self._bfi_plot_geometry=geometry
        return super().draw()

    def print_figure(self, *args, **kwargs):
        # Older Qt backends draw before setting is_saving; keep export draws isolated.
        previous = getattr(self, '_bfi_exporting', False)
        self._bfi_exporting = True
        try:
            return super().print_figure(*args, **kwargs)
        finally:
            self._bfi_exporting = previous
