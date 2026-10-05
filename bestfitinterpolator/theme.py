"""Plugin-wide visual tokens, information controls and figure identity."""
import os
import re
from functools import lru_cache
from qgis.PyQt.QtWidgets import QToolButton, QWidget, QLayout, QPushButton, QAbstractButton, QGroupBox, QTabWidget
from qgis.PyQt.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QPolygonF, QFont
from qgis.PyQt.QtCore import Qt, QSize, QPointF
from .compat import enum_value

COLORS = dict(primary="#008eab", primary_dark="#092447", primary_light="#64dfe1",
              accent="#ff8a39", background="#f4f7f9", surface="#ffffff",
              surface_translucent="rgba(0,142,171,24)", border="#cad8df",
              text_primary="#142b42", text_secondary="#536a7d", success="#237b64",
              warning="#a05a12", error="#b63743")
SPACING = dict(small=4, medium=8, large=12)
TYPOGRAPHY = dict(family="Sans Serif", body=9, title=12)
BORDER_RADIUS = 7
PALETTES = ("Viridis", "Plasma", "Inferno", "Magma", "Cividis", "Turbo", "Spectral", "RdYlGn")
BRANDING_ENABLED = False


def stylesheet():
    c = dict(COLORS)
    c['assets'] = os.path.dirname(__file__).replace('\\', '/')
    return """
    QDialog, QWidget#bfiRoot { background: %(surface)s; color: %(text_primary)s; }
    QGroupBox { background: transparent; border: none;
      border-radius: 7px; margin-top: 16px; padding: 4px; }
    QGroupBox::title { subcontrol-origin: margin; left: 4px; padding: 0 3px;
      color: %(primary_dark)s; font-weight: bold; }
    QGroupBox[bfiSection="true"] { border: 1px solid %(border)s; border-radius: 7px;
      margin-top: 14px; padding: 8px; }
    QPushButton { border: 1px solid #dde6ec; border-radius: 6px;
      padding: 5px 10px; background: #f4f7f9; color: %(text_primary)s; }
    QToolButton { border: none; border-radius: 6px; padding: 2px; background: transparent; }
    QPushButton:hover, QToolButton:hover { background: %(surface_translucent)s; border-color: %(primary)s; }
    QPushButton:pressed, QToolButton:pressed, QPushButton:checked { background: %(primary_light)s; color: %(primary_dark)s; }
    QPushButton[bfiPrimary="true"] { background: %(primary)s; border-color: %(primary)s; color: white; font-weight: bold; }
    QPushButton[bfiPrimary="true"]:hover { background: #007c96; }
    QPushButton[bfiPrimary="true"]:pressed { background: %(primary_dark)s; }
    QPushButton[bfiPrimary="true"]:checked { background: %(primary_dark)s; color: white; }
    QPushButton:disabled { background: #f1f4f6; border-color: #e8edf0; color: #98a7b2; }
    QToolButton[bfiInfo="true"], QToolButton[bfiSettings="true"] { padding: 0; background: white; }
    QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit { padding: 4px 6px; border: 1px solid #dde6ec;
      border-radius: 5px; background: %(surface)s; color: %(text_primary)s; selection-background-color: %(primary)s; }
    QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus { border-color: %(primary)s; }
    QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QLineEdit:disabled { background: #eef2f5; color: #9aa9b4; border-color: #e8edf0; }
    QComboBox::drop-down { border: none; width: 24px; }
    QComboBox::down-arrow { image: url(%(assets)s/ui_arrow_down.svg); width: 10px; height: 10px; }
    QSpinBox::up-button, QDoubleSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 19px; border: none; }
    QSpinBox::down-button, QDoubleSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 19px; border: none; }
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url(%(assets)s/ui_arrow_up.svg); width: 8px; height: 8px; }
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url(%(assets)s/ui_arrow_down.svg); width: 8px; height: 8px; }
    QTabWidget::pane { border: none; background: white; }
    QTabBar::tab { border: none; border-bottom: 2px solid transparent; background: transparent; padding: 7px 10px; color: %(text_secondary)s; }
    QTabBar::tab:selected { border-bottom-color: %(primary)s; background: %(surface_translucent)s; color: %(primary_dark)s; }
    QTabBar::tab:hover { color: %(primary)s; }
    QHeaderView::section { border: none; border-bottom: 1px solid #dde6ec; background: #f4f7f9; color: %(primary_dark)s; padding: 7px 6px; }
    QTableView { border: none; gridline-color: #eef2f5; background: white; alternate-background-color: #f7f9fb; selection-background-color: %(surface_translucent)s; selection-color: %(primary_dark)s; }
    QScrollArea { border: none; background: transparent; }
    QFrame { border: none; }
    QPlainTextEdit, QTextEdit { border: 1px solid #e5ebef; border-radius: 5px; background: white; padding: 4px; }
    QScrollBar:vertical { border: none; background: #f4f7f9; width: 10px; margin: 0; }
    QScrollBar:horizontal { border: none; background: #f4f7f9; height: 10px; margin: 0; }
    QScrollBar::handle { background: #cfdae1; border-radius: 4px; min-height: 24px; min-width: 24px; }
    QScrollBar::add-line, QScrollBar::sub-line { border: none; width: 0; height: 0; }
    QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
    QProgressBar { border: none; border-radius: 4px; background: #eaf0f4; text-align: center; }
    QProgressBar::chunk { border-radius: 4px; background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 %(primary)s,stop:1 %(primary_light)s); }
    QLabel[bfiCard="true"] { background: %(surface_translucent)s; border: 1px solid %(border)s;
      border-radius: 7px; padding: 6px; color: %(text_primary)s; }
    QToolTip { background: %(primary_dark)s; color: white; border: 1px solid %(primary)s; padding: 6px; }
    """ % c


def apply_theme(widget):
    widget.setWindowTitle(clean_display_name(widget.windowTitle()))
    widget.setObjectName(widget.objectName() or "bfiRoot")
    widget.setStyleSheet(stylesheet())
    refresh_controls(widget)


def action_icon(kind='info'):
    """Draw small, scalable Qt icons without font or resource-path dependencies."""
    import math
    pixmap = QPixmap(32, 32)
    pixmap.fill(enum_value(Qt, 'GlobalColor', 'transparent'))
    painter = QPainter(pixmap)
    painter.setRenderHint(enum_value(QPainter, 'RenderHint', 'Antialiasing'))
    painter.setPen(QPen(QColor(COLORS['primary']), 2.2))
    if kind == 'settings':
        points=[]
        for i in range(64):
            angle=i*math.pi/32
            radius=12 if i%8 in (1,2,3,4) else 9.5
            points.append(QPointF(16+radius*math.cos(angle),16+radius*math.sin(angle)))
        painter.drawPolygon(QPolygonF(points))
        painter.drawEllipse(QPointF(16,16),4,4)
    else:
        painter.drawEllipse(QPointF(16,16),12,12)
        painter.setFont(QFont('Arial',15,enum_value(QFont,'Weight','Bold')))
        painter.drawText(pixmap.rect(),enum_value(Qt,'AlignmentFlag','AlignCenter'),'i')
    painter.end()
    return QIcon(pixmap)


def clean_display_name(text):
    """Use plain names while retaining numeric signs and mathematical notation."""
    text=text.replace('…','').replace('...','')
    text=re.sub(r'\s+[—–-]\s+',' ',text)
    return re.sub(r'(?<=[A-Za-z])-(?=[A-Za-z])',' ',text)


def refresh_controls(widget):
    """Keep existing widgets and assign only compact icons and action hierarchy."""
    for button in widget.findChildren(QAbstractButton):
        button.setText(clean_display_name(button.text()))
    for group in widget.findChildren(QGroupBox):
        group.setTitle(clean_display_name(group.title()))
    for tabs in widget.findChildren(QTabWidget):
        for index in range(tabs.count()):
            tabs.setTabText(index,clean_display_name(tabs.tabText(index)))
    for button in widget.findChildren(QToolButton):
        if 'info' in button.objectName().lower() or button.property('bfiInfo'):
            button.setProperty('bfiInfo',True)
            button.setIcon(action_icon())
            button.setIconSize(QSize(18,18)); button.setFixedSize(24,24)
    for button in widget.findChildren(QPushButton):
        text=button.text().strip().lower()
        primary=text.startswith(('interpolate','run ','validate','apply','compare','calculate')) and 'view' not in text
        button.setProperty('bfiPrimary',primary)
        button.style().unpolish(button); button.style().polish(button)


class InfoButton(QToolButton):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setProperty("bfiInfo", True)
        self.setIcon(action_icon())
        self.setIconSize(QSize(18,18)); self.setFixedSize(24,24)
        self.setText("i")
        self.setToolTip(text)
        self.setAccessibleName("Information")


def apply_branding_to_figure(figure, enabled=None):
    if enabled is not None: figure._bfi_branding_enabled=bool(enabled)
    enabled = getattr(figure,"_bfi_branding_enabled",BRANDING_ENABLED)
    previous = getattr(figure, "_bfi_brand_artist", None)
    if enabled and previous is not None and previous in figure.artists:
        return previous
    if previous is not None:
        try:
            previous.remove()
        except (ValueError, NotImplementedError):
            pass
    figure._bfi_brand_artist = None
    if not enabled or not figure.axes:
        return
    from matplotlib.offsetbox import OffsetImage, AnnotationBbox
    pixels = _brand_image()
    icon = OffsetImage(pixels, zoom=12. / pixels.shape[0], alpha=.75)
    # The icon sits in the footer, outside data axes, without adding a map axes.
    artist = AnnotationBbox(icon, (.99, .008), xycoords=figure.transFigure,
                            frameon=False, box_alignment=(1, 0), pad=0)
    artist.set_in_layout(False)
    figure.add_artist(artist)
    figure._bfi_brand_artist = artist
    return artist


@lru_cache(maxsize=1)
def _brand_image():
    from matplotlib.image import imread
    return imread(os.path.join(os.path.dirname(__file__), "icon.png"))


def style_figure(figure):
    figure.set_facecolor(COLORS["surface"])
    if getattr(figure,'_suptitle',None) is not None:
        figure._suptitle.set_text(clean_display_name(figure._suptitle.get_text()))
    for ax in figure.axes:
        for title in (ax.title,ax._left_title,ax._right_title):
            title.set_text(clean_display_name(title.get_text()))
        ax.tick_params(colors=COLORS["text_secondary"])
        ax.xaxis.label.set_color(COLORS["text_primary"])
        ax.yaxis.label.set_color(COLORS["text_primary"])
        ax.title.set_color(COLORS["primary_dark"])
        if ax.title.get_fontsize()>11: ax.title.set_fontsize(10)
        for label in (ax.xaxis.label,ax.yaxis.label):
            if label.get_fontsize()>10: label.set_fontsize(9)
        for label in ax.get_xticklabels()+ax.get_yticklabels():
            if label.get_fontsize()>9: label.set_fontsize(8)
        legend=ax.get_legend()
        if legend is not None:
            legend.get_title().set_text(clean_display_name(legend.get_title().get_text()))
            for label in legend.get_texts():
                label.set_text(clean_display_name(label.get_text()))
                if label.get_fontsize()>9: label.set_fontsize(8)
    apply_branding_to_figure(figure)


def save_figure(figure,*args,**kwargs):
    """Export the common style without cropping the footer branding."""
    style_figure(figure)
    artist=getattr(figure,"_bfi_brand_artist",None)
    if artist is not None:
        kwargs["bbox_extra_artists"]=tuple(kwargs.get("bbox_extra_artists",()))+(artist,)
    return figure.savefig(*args,**kwargs)
