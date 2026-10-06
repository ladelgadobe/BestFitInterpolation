"""Editable report configuration and a paginated preview of the same PDF source."""
import os
from qgis.PyQt.QtCore import QSizeF,QRectF,Qt,QUrl
from qgis.PyQt.QtGui import QTextDocument,QPageSize,QPageLayout,QPainter,QFont,QColor,QDesktopServices
from qgis.PyQt.QtPrintSupport import QPrinter,QPrintPreviewWidget
from qgis.PyQt.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QCheckBox,QLineEdit,QLabel,QPushButton,QFileDialog,QMessageBox,QScrollArea,QWidget,QSplitter,QListWidget,QTextBrowser,QSizePolicy
from .compat import enum_value,print_document
from .theme import apply_theme,COLORS
from .report_model import report_html,export_report_html,TemporaryHtmlReport


def open_temporary_html(owner,state):
    """Keep browser assets alive for the plugin session without a Save dialog."""
    preview=getattr(owner,'_html_preview',None)
    if preview is None:
        preview=TemporaryHtmlReport()
        owner._html_preview=preview
        owner.destroyed.connect(lambda *args:preview.cleanup())
    path=preview.render(state)
    if not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
        raise OSError('The default browser could not open the report.')
    return path


def configure_printer(printer):
    printer.setOutputFormat(enum_value(QPrinter,"OutputFormat","PdfFormat"))
    printer.setPageSize(QPageSize(enum_value(QPageSize,"PageSizeId","A4")))
    printer.setPageMargins(14.,14.,14.,14.,enum_value(QPrinter,"Unit","Millimeter")) if not hasattr(printer,"setPageLayout") else printer.setPageLayout(
        QPageLayout(QPageSize(enum_value(QPageSize,"PageSizeId","A4")),enum_value(QPageLayout,"Orientation","Portrait"),__import__('qgis.PyQt.QtCore',fromlist=['QMarginsF']).QMarginsF(14.,14.,14.,14.),enum_value(QPageLayout,"Unit","Millimeter")))


def create_document(state,printer):
    document=QTextDocument()
    document.documentLayout().setPaintDevice(printer)
    document.setHtml(report_html(state))
    document.setDefaultFont(__import__('qgis.PyQt.QtGui',fromlist=['QFont']).QFont("Arial",10))
    rect=printer.pageLayout().paintRectPixels(printer.resolution())
    document.setPageSize(QSizeF(rect.width(),rect.height()-24.*printer.resolution()/72.))
    return document


def paint_report_document(document, printer):
    """Paint identical paginated content and page numbers for preview and PDF."""
    painter=QPainter(printer)
    if not painter.isActive(): raise OSError("Could not start the report printer.")
    page=document.pageSize(); count=document.pageCount()
    footer=24.*printer.resolution()/72.
    try:
        for index in range(count):
            if index and not printer.newPage(): raise OSError("Could not create the next report page.")
            painter.save()
            painter.translate(0.,-index*page.height())
            rect=QRectF(0.,index*page.height(),page.width(),page.height())
            painter.setClipRect(rect)
            document.drawContents(painter,rect)
            painter.restore()
            painter.setFont(QFont("Arial",8)); painter.setPen(QColor(COLORS["text_secondary"]))
            rect=QRectF(0.,page.height()+footer/3.,page.width(),footer*2./3.)
            painter.drawText(rect,enum_value(Qt,"AlignmentFlag","AlignRight"),
                             "Best Fit Interpolator  |  {} / {}".format(index+1,count))
    finally: painter.end()


def export_report_pdf(state,path):
    printer=QPrinter(enum_value(QPrinter,"PrinterMode","HighResolution")); configure_printer(printer)
    printer.setOutputFileName(path)
    document=create_document(state,printer); paint_report_document(document,printer)
    if not os.path.isfile(path) or os.path.getsize(path)==0: raise OSError("PDF output was not created.")
    return path


class ReportBuilderDialog(QDialog):
    def __init__(self,state,parent=None):
        super().__init__(parent); self.state=state; self.setWindowTitle("Report Builder"); self.resize(1150,850)
        root=QVBoxLayout(self); fields=QHBoxLayout(); root.addLayout(fields)
        self.study,self.author,self.notes=QLineEdit(state.study_name),QLineEdit(state.author),QLineEdit(state.notes)
        for name,w in (("Study",self.study),("Author",self.author),("Notes",self.notes)):
            fields.addWidget(QLabel(name)); fields.addWidget(w); w.editingFinished.connect(self.refresh)
        split=QSplitter(); root.addWidget(split,1)
        options=QWidget(); layout=QVBoxLayout(options); self.checks=[]
        for section in state.sections:
            chk=QCheckBox(section.title); chk.setChecked(section.enabled or section.mandatory); chk.setEnabled(not section.mandatory)
            chk.toggled.connect(self.refresh); layout.addWidget(chk); self.checks.append((section,chk))
        layout.addStretch(); scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(options); split.addWidget(scroll)
        self.printer=QPrinter(enum_value(QPrinter,"PrinterMode","HighResolution")); configure_printer(self.printer)
        self.preview=QPrintPreviewWidget(self.printer,self); self.preview.paintRequested.connect(self.paint); split.addWidget(self.preview)
        split.setSizes((280,800))
        actions=QHBoxLayout(); root.addLayout(actions)
        refresh=QPushButton("Refresh preview"); refresh.clicked.connect(self.refresh); actions.addWidget(refresh)
        export=QPushButton("Export PDF"); export.clicked.connect(self.export); actions.addWidget(export)
        html_button=QPushButton('View HTML'); html_button.clicked.connect(self.export_html); actions.addWidget(html_button)
        self.document=create_document(state,self.printer); apply_theme(self)
        from qgis.PyQt.QtWidgets import QApplication
        self.setMinimumSize(600,420); self.setSizeGripEnabled(True)
        screen=QApplication.primaryScreen()
        if screen is not None:
            available=screen.availableGeometry()
            self.resize(min(1150,available.width()-40),min(850,available.height()-60))
        self.preview.setZoomMode(enum_value(QPrintPreviewWidget,'ZoomMode','FitInView'))

    def refresh(self,*args):
        self.state.study_name,self.state.author,self.state.notes=self.study.text(),self.author.text(),self.notes.text()
        for section,check in self.checks: section.enabled=check.isChecked() or section.mandatory
        self.document=create_document(self.state,self.printer); self.preview.updatePreview()

    def paint(self,printer): paint_report_document(self.document,printer)

    def export(self):
        self.refresh()
        path,_=QFileDialog.getSaveFileName(self,"Export technical report","best_fit_report.pdf","PDF (*.pdf)")
        if not path: return
        if not path.lower().endswith(".pdf"): path+=".pdf"
        try: export_report_pdf(self.state,path)
        except Exception as exc: QMessageBox.warning(self,"Report export",str(exc))

    def export_html(self):
        self.refresh()
        try: open_temporary_html(self,self.state)
        except Exception as exc: QMessageBox.warning(self,'Report preview',str(exc))


class ReportOverviewWidget(QWidget):
    """Browse current session results without opening the PDF builder."""
    def __init__(self,framework,parent=None):
        super().__init__(parent); self.framework=framework
        root=QVBoxLayout(self)
        self.description=QLabel('Explore the current session, validation and executed interpolation. View the interactive HTML report in your browser or open the PDF options.')
        self.description.setWordWrap(True); root.addWidget(self.description)
        actions=QHBoxLayout(); root.addLayout(actions)
        refresh=QPushButton('Refresh summary'); refresh.clicked.connect(self.refresh); actions.addWidget(refresh)
        pdf=QPushButton('PDF preview / options'); pdf.clicked.connect(framework.on_preview_report_clicked); actions.addWidget(pdf)
        html_button=QPushButton('View HTML'); html_button.clicked.connect(self.export_html); actions.addWidget(html_button)
        split=QSplitter(); root.addWidget(split,1)
        self.sections=QListWidget(); self.sections.addItems(('Overview','Validation','Interpolation','Diagnostics'))
        self.sections.setMaximumWidth(180); self.sections.setMinimumWidth(120); split.addWidget(self.sections)
        self.browser=QTextBrowser(); self.browser.setOpenLinks(False)
        self.browser.setSizePolicy(enum_value(QSizePolicy,'Policy','Ignored'),enum_value(QSizePolicy,'Policy','Expanding'))
        self.browser.anchorClicked.connect(self.navigate); split.addWidget(self.browser)
        split.setStretchFactor(1,1)
        self.sections.currentRowChanged.connect(self.refresh)
        self.sections.setCurrentRow(0)

    def navigate(self,url):
        if url.scheme()!='bfi':
            if url.hasFragment(): self.browser.scrollToAnchor(url.fragment())
            elif url.scheme() in ('https','http'): QDesktopServices.openUrl(url)
            return
        pages={'validation':'tabFrameworkValidation','interpolation':'tabFrameworkInterpolation'}
        key=url.path().strip('/') or url.toString().split(':',1)[-1].strip('/')
        target=self.framework.comparison_widget if key=='comparison' else self.framework._get(pages.get(key,''))
        if target is not None: self.framework.framework_subtabs.setCurrentWidget(target)

    def refresh(self,*args):
        import html
        from .report_model import ReportTable
        from .interpolation_result import executed_method
        f=self.framework; s=f.state; esc=lambda value:html.escape(str(value if value is not None else 'Pending'))
        result=s.__dict__.get('executed_result')
        section=self.sections.currentRow()
        content='<h2>'+esc(self.sections.currentItem().text() if self.sections.currentItem() else 'Overview')+'</h2>'
        if section==0:
            fields=(('Variable',s.variable_name or 'Pending'),('Samples',s.sample_count),('Pixel size',s.pixel_size),
                    ('Framework mode',s.framework_mode),('Evaluated methods',', '.join(s.validated_methods) or 'Pending'),
                    ('Recommended',s.selected_winner or 'Pending'),('Selected for next run',s.__dict__.get('selected_method') or s.selected_winner or 'Pending'),
                    ('Executed in Framework',executed_method(f)))
            content+=ReportTable(('Session','Value'),fields).html()
            content+='<p><a href="bfi:validation">Review validation</a> · <a href="bfi:interpolation">Open interpolation</a> · <a href="bfi:comparison">Compare maps</a></p>'
            content+='<p>Validation compares predictive accuracy. A recommendation does not create an interpolated map. Framework output appears after Run interpolation completes.</p>'
        elif section==1:
            rows=[(r.get('method'),r.get('rmse'),r.get('lccc'),r.get('r2'),r.get('mae'),r.get('parameters') or r.get('configuration') or 'Automatic') for r in s.validation_results]
            content+=ReportTable(('Method','RMSE','LCCC','R²','MAE','Validated configuration'),tuple(rows)).html() if rows else '<p>No validation has been run for the current inputs.</p>'
            content+='<p>Lower RMSE and MAE indicate smaller prediction errors. LCCC measures agreement between observed and predicted values. Compare these results using the same input data and validation strategy.</p><p><a href="bfi:validation">Open Validation</a></p>'
        elif section==2:
            if result is None: content+='<p>No Framework interpolation has been executed in this session.</p>'
            else:
                content+=ReportTable(('Executed output','Value'),(('Method',result.method),('Parameters',result.parameters),('Raster',result.raster_path),('Execution',result.executed_at))).html()
            content+='<p><a href="bfi:interpolation">Open the interpolation map</a> · <a href="bfi:comparison">Compare evaluated maps</a></p>'
        else:
            content+=ReportTable(('Spatial diagnostic','Value'),(('Global Moran I',s.moran_i),('p value',s.moran_p_value),('Spatial pattern',s.spatial_pattern or 'Pending'),('SDI',s.sdi_value),('SDI class',s.sdi_status or 'Pending'))).html()
            content+='<p>Open Outlier diagnostic in Data to review local clusters, statistical flags and Keep/Exclude/Reset decisions. Diagnostics help interpret the inputs; they do not automatically remove observations.</p>'
        self.browser.setHtml('<html><head><style>body{font-family:Arial;color:#142b42}h2{color:#008eab}table{width:100%;border-collapse:collapse}th{background:#e5f2f5}td,th{padding:7px;border:1px solid #cad8df}a{color:#008eab}p{line-height:1.4}</style></head><body>'+content+'</body></html>')

    def export_html(self):
        f=self.framework
        state=f._fresh_report_state()
        try: open_temporary_html(self,state)
        except Exception as exc: QMessageBox.warning(self,'Report preview',str(exc))
