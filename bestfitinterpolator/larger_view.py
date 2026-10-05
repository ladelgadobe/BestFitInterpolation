"""Enlarge the current figure without recomputing or changing its display state."""
import copy
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout,QApplication
from .compat import enum_value, is_alive
from .mpl_compat import FigureCanvas, NavigationToolbar
from .map_controls import SettingsButton
from .theme import apply_theme,clean_display_name


class LargerViewDialog(QDialog):
    def __init__(self, source_figure, parent=None, title='Larger view'):
        super().__init__(parent)
        self.setAttribute(enum_value(Qt,'WidgetAttribute','WA_DeleteOnClose'),True)
        self.setWindowTitle(clean_display_name(title))
        self.source=source_figure
        self.source_canvas=source_figure.canvas
        self.figure=copy.deepcopy(source_figure)
        self.canvas=FigureCanvas(self.figure)
        self.canvas._bfi_display_source=self.source_canvas
        self.layout_=QVBoxLayout(self)
        self.layout_.addWidget(NavigationToolbar(self.canvas,self))
        self.layout_.addWidget(self.canvas,1)
        callback=getattr(self.source_canvas,'_bfi_open_settings',None)
        if callback is not None: self.settings_button=SettingsButton(self.canvas,callback)
        self._source_connection=self.source_canvas.mpl_connect('draw_event',self.source_changed)
        self.finished.connect(self.disconnect_source)
        apply_theme(self)
        self.resize(980,700)
        screen=QApplication.primaryScreen()
        if screen is not None:
            available=screen.availableGeometry()
            self.resize(min(980,available.width()-40),min(700,available.height()-60))
        self.canvas.draw()

    def source_changed(self,event):
        if not is_alive(self.canvas): return
        if event.canvas is not self.source_canvas or self.source_canvas.is_saving(): return
        # A figure copy retains images, masks, normalizations, artists and limits.
        figure=copy.deepcopy(self.source)
        self.canvas.figure=figure; figure.set_canvas(self.canvas)
        self.figure=figure
        self.canvas.draw_idle()

    def disconnect_source(self,*args):
        self.source_canvas.mpl_disconnect(self._source_connection)


def show_larger_view(source_figure,parent=None,title='Larger view'):
    dialog=LargerViewDialog(source_figure,parent,title)
    # Keep nonmodal windows alive and release them when Qt closes them.
    if parent is not None:
        views=getattr(parent,'_bfi_larger_views',[])
        views[:]=[view for view in views if is_alive(view)]
        views.append(dialog); parent._bfi_larger_views=views
    dialog.show(); dialog.raise_(); dialog.activateWindow()
    return dialog
