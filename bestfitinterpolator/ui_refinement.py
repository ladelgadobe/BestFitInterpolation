"""Adapt existing Designer widgets without changing their controller bindings."""
from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtWidgets import QWidget,QScrollArea,QVBoxLayout,QHBoxLayout,QTabWidget,QSizePolicy,QApplication,QLabel
from .compat import enum_value
from .theme import refresh_controls,action_icon


class ContentScrollArea(QScrollArea):
    def minimumSizeHint(self):
        return QSize(120,80)

    def sizeHint(self):
        return QSize(640,420)


def scroll_content(page):
    if page.property('bfiScrollable') or page.layout() is None: return
    content=QWidget()
    content.setObjectName('bfiScrollContent')
    content.setLayout(page.layout())
    root=QVBoxLayout(page); root.setContentsMargins(0,0,0,0)
    scroll=ContentScrollArea(page); scroll.setWidgetResizable(True)
    scroll.viewport().setObjectName('bfiScrollViewport')
    scroll.viewport().setStyleSheet('QWidget#bfiScrollViewport { background: white; }')
    scroll.setWidget(content); root.addWidget(scroll)
    page.setProperty('bfiScrollable',True)
    content.setStyleSheet('QWidget#bfiScrollContent { background: white; }')
    page._bfi_content_scroll=scroll


def refine_rk(dialog):
    group=getattr(dialog,'groupRKParams',None)
    if group is None or group.property('bfiRefined'): return
    group.setMaximumHeight(16777215)
    rf,kriging=dialog.grpRKRF,dialog.grpRKKriging
    rf.setTitle('Random Forest trend'); kriging.setTitle('Residual kriging')
    for panel in (rf,kriging): panel.setProperty('bfiSection',True)
    # Keep both original parameter panels visible; advanced settings share one dialog.
    for name in ('spinRKCutoff','labelRKCutoff','spinRKLag','labelRKLagWidth',
                 'btnRKFitVariogram','valRKVariogramValidationSummary'):
        widget=getattr(dialog,name,None) or dialog.findChild(QWidget,name)
        if widget is not None: widget.hide()
    grid=rf.layout()
    grid.removeWidget(dialog.btnRKFitRF); grid.addWidget(dialog.btnRKFitRF,6,0,1,5)
    grid.removeWidget(dialog.valRKBestParams); grid.addWidget(dialog.valRKBestParams,7,0,1,5)
    dialog.valRKBestParams.setWordWrap(True)
    dialog.valRKBestParams.setSizePolicy(enum_value(QSizePolicy,'Policy','Ignored'),enum_value(QSizePolicy,'Policy','Preferred'))
    def compact_rf_controls(*args):
        searching=dialog.chkRKUseGrid.isChecked()
        names=['labelRKHeader'+str(i) for i in (2,3,4)]
        names += ['spinRK_{}_{}'.format(parameter,kind) for parameter in ('mtry','ntree','nodesize') for kind in ('min','max','step')]
        names += ['labelRKSearchK','spinRKSearchK','btnInfoRKSearchK','labelRKSearchIter','spinRKSearchIter','btnInfoRKSearchIter']
        for name in names:
            widget=getattr(dialog,name,None) or dialog.findChild(QWidget,name)
            if widget is not None: widget.setVisible(searching)
    dialog.chkRKUseGrid.toggled.connect(compact_rf_controls)
    dialog.chkRKUseManual.toggled.connect(compact_rf_controls)
    compact_rf_controls()
    mode_row=dialog.horizontalLayoutRKMode
    status_row=QHBoxLayout()
    for widget in (dialog.labelRKStatusTitle,dialog.valRKStatus):
        mode_row.removeWidget(widget)
        status_row.addWidget(widget)
    status_row.setStretch(1,1)
    group.layout().insertLayout(1,status_row)
    dialog.valRKStatus.setWordWrap(True)
    dialog.valRKStatus.setMinimumWidth(0)
    dialog.valRKStatus.setMinimumHeight(30)
    dialog.valRKStatus.setSizePolicy(enum_value(QSizePolicy,'Policy','Ignored'),enum_value(QSizePolicy,'Policy','Preferred'))
    dialog.btnRKValidateVariogramModels.setText('Adjust semivariogram')
    dialog.btnRKValidateVariogramModels.setToolTip('Adjust maximum distance, lag distance or count; preview, validate and apply residual models.')
    button=dialog.btnRKApplyVariogram
    # Retain the existing signal and backend; move the same button out of the form.
    kriging.layout().removeWidget(button)
    button.setText('Interpolate')
    dialog.tabRKInterpolation.layout().addWidget(button)
    dialog.groupRKDiagnostics.setMaximumWidth(16777215)
    dialog.horizontalLayoutRKDiagnosticsAndMap.setStretch(0,1)
    dialog.horizontalLayoutRKDiagnosticsAndMap.setStretch(1,2)
    for canvas in (dialog.RKMap,dialog.RKVariogram,dialog.RKImportance):
        canvas.setMinimumHeight(180)
    dialog.tabWidgetRKDiagnostics.setTabText(0,'Semivariogram')
    dialog.tabWidgetRKDiagnostics.setTabText(1,'Importance')
    dialog.tabWidgetRKDiagnostics.setTabToolTip(0,'Residual semivariogram')
    dialog.tabWidgetRKDiagnostics.setTabToolTip(1,'Random Forest variable importance')
    for page in (dialog.tabRKVariogram,dialog.tabRKImportance):
        page.setProperty('bfiScrollable',True)
    scroll_content(dialog.tabRKInterpolation)
    dialog.tabRKInterpolation._bfi_content_scroll.widget().layout().removeWidget(button)
    dialog.tabRKInterpolation.layout().addWidget(button)
    for name,text in (('labelRK_mtry','Variables per split (mtry)'),('labelRK_ntree','Trees (ntree)'),('labelRK_nodesize','Minimum node size'),('labelRKVarModel','Residual model'),('labelRKCutoff','Maximum distance')):
        label=getattr(dialog,name,None)
        if label is not None: label.setText(text)
    summary=getattr(dialog,'valRKVariogramValidationSummary',None)
    if summary is not None:
        summary.setWordWrap(True); summary.setMinimumHeight(32)
        summary.setSizePolicy(enum_value(QSizePolicy,'Policy','Ignored'),enum_value(QSizePolicy,'Policy','Preferred'))
    group.setProperty('bfiRefined',True)


def refine_method_options(dialog):
    for name in ('groupIDWOptions','groupTPSOptions'):
        panel=getattr(dialog,name,None)
        if panel is not None: panel.setProperty('bfiSection',True)
    button=getattr(dialog,'btnRFRun',None)
    page=getattr(dialog,'tabRFInterpolation',None)
    if button is not None and page is not None:
        button.parentWidget().layout().removeWidget(button)
        scroll_content(page)
        page.layout().addWidget(button)


def refine_main_dialog(dialog):
    if dialog.property('bfiRefined'): return
    refine_rk(dialog)
    refine_method_options(dialog)
    # The leaves scroll internally; the main tab structure stays exactly where it was.
    tabs=list(dialog.findChildren(QTabWidget))
    for tab in tabs:
        for i in range(tab.count()):
            page=tab.widget(i)
            if not page.findChildren(QTabWidget): scroll_content(page)
    dialog.setMinimumSize(600,420)
    dialog.setSizeGripEnabled(True)
    refresh_controls(dialog)
    dialog.setProperty('bfiRefined',True)
    screen=QApplication.primaryScreen()
    if screen is not None:
        available=screen.availableGeometry()
        dialog.resize(min(1000,available.width()-40),min(720,available.height()-60))


def refresh_info_labels(dialog):
    for label in dialog.findChildren(QLabel):
        if 'info' in label.objectName().lower() and label.pixmap() is not None:
            label.setPixmap(action_icon().pixmap(18,18))
