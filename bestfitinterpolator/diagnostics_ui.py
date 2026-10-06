"""Data's spatial diagnostic subwindow, with explicit feature-ID decisions."""
import numpy as np
from qgis.PyQt.QtCore import Qt, QSize
from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QComboBox, QDoubleSpinBox, QSpinBox, QCheckBox, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QSplitter, QWidget, QMessageBox, QTableView, QTextBrowser, QApplication)
from matplotlib.figure import Figure
from .mpl_compat import FigureCanvas,NavigationToolbar
from .compat import enum_value, is_alive, arrays_equal_with_nan
from .theme import apply_theme, COLORS, InfoButton
from .diagnostics_engine import DiagnosticsState, DiagnosticsEngine
from .async_jobs import submit
from .diagnostics_plot import draw_diagnostics
from .diagnostics_table import DiagnosticsTableModel,HEADERS
from .map_controls import MapDisplayControls,MatplotlibMapDisplay,selected_map_units,SettingsButton

def feature_in_analysis(plugin, layer, feature):
    if plugin is None:
        return True
    state = getattr(plugin, "diagnostics_states", {}).get((layer.id(), plugin.dlg.Points_2.currentText()))
    if state is None: return True
    fid=int(feature.id())
    return fid not in state.invalid_feature_ids and state.decisions.get(fid) != "Exclude"


def capture_data(plugin):
    from qgis.core import QgsProject
    layers = QgsProject.instance().mapLayersByName(plugin.dlg.Points.currentText())
    field = plugin.dlg.Points_2.currentText()
    if not layers or not field:
        raise ValueError("Select a point layer and target variable in Data first.")
    layer = layers[0]
    ids, coords, values = [], [], []
    for feat in layer.getFeatures():
        ids.append(int(feat.id()))
        try:
            geom = feat.geometry()
            if geom.isEmpty(): raise ValueError("Missing point geometry")
            pt = geom.asMultiPoint()[0] if geom.isMultipart() else geom.asPoint()
            coords.append((float(pt.x()), float(pt.y())))
        except (TypeError, ValueError, IndexError, RuntimeError):
            coords.append((np.nan, np.nan))
        try:
            values.append(float(feat[field]))
        except (TypeError, ValueError):
            values.append(np.nan)
    old = plugin.diagnostics_states.get((layer.id(), field))
    state = DiagnosticsState(layer.id(), field, np.asarray(ids, dtype=np.int64),
        np.asarray(coords, dtype=float).reshape((-1, 2)), np.asarray(values, dtype=float))
    if old is not None:
        state.decisions = {fid:old.decisions[fid] for fid in ids if fid in old.decisions}
        state.settings = dict(old.settings)
        if np.array_equal(state.ids, old.ids) and arrays_equal_with_nan(state.values, old.values) and arrays_equal_with_nan(state.coordinates, old.coordinates):
            return old, layer
    plugin.diagnostics_states[(layer.id(), field)] = state
    return state, layer


class SpatialDiagnosticsDialog(QDialog):
    def __init__(self, plugin, state, layer):
        super().__init__(plugin.dlg)
        self.plugin, self.state, self.layer = plugin, state, layer
        self.engine = DiagnosticsEngine()
        self.setWindowTitle("Outlier diagnostic (" + state.field_name + ")")
        self.resize(1250, 850)
        self.root = QVBoxLayout(self)
        introduction=QLabel("Review extremes, spatial outliers and clusters. Only Exclude affects subsequent analysis.")
        introduction.setWordWrap(True); self.root.addWidget(introduction)
        panel = QGridLayout()
        parameters=QWidget(); parameters.setLayout(panel)
        from .ui_refinement import ContentScrollArea
        self.parameters_dialog=QDialog(self)
        self.parameters_dialog.setWindowTitle('Outlier diagnostic settings')
        settings_layout=QVBoxLayout(self.parameters_dialog)
        scroll=ContentScrollArea(self.parameters_dialog); scroll.setWidgetResizable(True); scroll.setWidget(parameters)
        settings_layout.addWidget(scroll)
        done=QPushButton('Done'); done.clicked.connect(self.parameters_dialog.close); settings_layout.addWidget(done)
        self.parameters_dialog.resize(680,365)
        panel.setHorizontalSpacing(12); panel.setVerticalSpacing(8)
        self.methods = {}
        methods_row=QHBoxLayout()
        for col, name in enumerate(("IQR", "MAD", "Z")):
            chk = QCheckBox(name + (" (optional, nonrobust)" if name == "Z" else ""))
            chk.setChecked(name != "Z")
            self.methods[name] = chk
            methods_row.addWidget(chk)
        panel.addLayout(methods_row,0,0,1,4)
        self.iqr = self._number(panel, 1, 0, "Tukey k", 1.5, .01, 100.)
        self.mad = self._number(panel, 1, 2, "Modified Z threshold", 3.5, .01, 100.)
        self.z = self._number(panel, 2, 0, "Classical Z threshold", 3., .01, 100.)
        self.consensus = QComboBox(); self.consensus.addItems(("Any", "All", "At least N"))
        panel.addWidget(QLabel("Statistical consensus"), 3, 0); panel.addWidget(self.consensus, 3, 1)
        self.votes = QSpinBox(); self.votes.setRange(1, 3); self.votes.setValue(2)
        panel.addWidget(QLabel('Minimum flags (N)'),3,2); panel.addWidget(self.votes,3,3)
        self.neighborhood = QComboBox(); self.neighborhood.addItems(("KNN", "Distance threshold"))
        panel.addWidget(QLabel('Neighborhood'),4,0); panel.addWidget(self.neighborhood,4,1)
        self.knn = QSpinBox(); self.knn.setRange(1, 10000); self.knn.setValue(8)
        panel.addWidget(QLabel('KNN neighbors'),4,2); panel.addWidget(self.knn,4,3)
        self.distance = self._number(panel, 5, 0, "Distance (CRS units)", 100., .000001, 1.e12)
        self.permutations = QComboBox(); self.permutations.addItems(("99", "499", "999")); self.permutations.setCurrentText("499")
        panel.addWidget(QLabel('Permutations'),5,2); panel.addWidget(self.permutations,5,3)
        self.alpha = self._number(panel, 2, 2, "LISA alpha", .05, .001, .5)
        self.seed = QSpinBox(); self.seed.setRange(0, 2147483647); self.seed.setValue(42)
        panel.addWidget(QLabel("Seed"),6,0); panel.addWidget(self.seed,6,1)
        for column in (1,3): panel.setColumnStretch(column,1)
        self.run = QPushButton("Run / update diagnostics"); self.run.clicked.connect(self.calculate)
        parameters_button=QPushButton('Analysis settings')
        parameters_button.clicked.connect(self.show_analysis_settings)
        actions_top=QHBoxLayout(); actions_top.addWidget(self.run); actions_top.addWidget(parameters_button); actions_top.addStretch()
        self.info_button=InfoButton("Click to read how Outlier diagnostic works and how to use it.", self)
        self.info_button.setObjectName('btnMoranDiagnosticsInfo')
        self.info_button.setAccessibleName('Outlier diagnostic information')
        self.info_button.clicked.connect(self.show_information)
        actions_top.addWidget(self.info_button)
        self.root.addLayout(actions_top)
        self.consensus.currentIndexChanged.connect(lambda *a:self.votes.setEnabled(self.consensus.currentText()=='At least N'))
        self.neighborhood.currentIndexChanged.connect(self.update_neighborhood_controls)
        self.votes.setEnabled(False); self.update_neighborhood_controls()
        self.summary = QLabel(); self.summary.setWordWrap(True); self.root.addWidget(self.summary)
        self.map_mode=QComboBox(); self.map_mode.addItems(("LISA classes","Target values"))
        self.root.addWidget(self.map_mode)
        self.map_controls=MapDisplayControls(self)
        self.map_mode.currentIndexChanged.connect(lambda *args:self.render() if self.state.result else None)
        self.fig = Figure(figsize=(10, 3)); self.canvas = FigureCanvas(self.fig)
        self.canvas._bfi_display_source=True
        self.canvas._bfi_open_settings=self.map_controls.show_settings
        self.canvas._bfi_settings_button=SettingsButton(self.canvas,self.map_controls.show_settings)
        self.map_display=MatplotlibMapDisplay(self.canvas,self.map_controls,None)
        self.map_display.units_getter=lambda:selected_map_units(plugin)
        self.map_display.axes=lambda:[self.map_ax] if hasattr(self,"map_ax") else []
        self.canvas.setMinimumHeight(210)
        self.root.addWidget(self.canvas, 3)
        toolbar=NavigationToolbar(self.canvas,self); toolbar.setIconSize(QSize(18,18))
        self.root.insertWidget(self.root.count()-1,toolbar)
        self.table = QTableView(); self.table_model=DiagnosticsTableModel(state,self.table); self.table.setModel(self.table_model)
        self.table.setSelectionBehavior(enum_value(QAbstractItemView, "SelectionBehavior", "SelectRows"))
        self.table.setSelectionMode(enum_value(QAbstractItemView, "SelectionMode", "ExtendedSelection"))
        self.table.setEditTriggers(enum_value(QAbstractItemView, "EditTrigger", "NoEditTriggers"))
        self.table.setMinimumHeight(100)
        self.table.selectionModel().selectionChanged.connect(self.selection_changed); self.root.addWidget(self.table, 2)
        for column in range(len(HEADERS)): self.table.setColumnWidth(column,115 if column else 55)
        actions = QHBoxLayout(); self.root.addLayout(actions)
        for decision in ("Keep", "Exclude", "Reset"):
            btn = QPushButton(decision + " selected"); btn.clicked.connect(lambda checked=False, d=decision:self.decide(d)); actions.addWidget(btn)
        self.cancel = QPushButton("Cancel calculation"); self.cancel.clicked.connect(self.cancel_jobs); actions.addWidget(self.cancel)
        self.canvas.mpl_connect("pick_event", self.picked)
        self.canvas.mpl_connect("button_press_event", self.box_clicked)
        self.layer.selectionChanged.connect(self.layer_selection_changed)
        self.finished.connect(self.closed)
        apply_theme(self)
        from qgis.PyQt.QtWidgets import QApplication
        screen=QApplication.primaryScreen()
        if screen is not None:
            available=screen.availableGeometry(); self.resize(min(1100,available.width()-40),min(800,available.height()-60))
        if state.settings:
            self.restore_settings(state.settings)
        if state.result:
            self.render()

    def show_analysis_settings(self):
        apply_theme(self.parameters_dialog)
        self.parameters_dialog.show(); self.parameters_dialog.raise_(); self.parameters_dialog.activateWindow()

    def show_information(self):
        """Keep diagnostic guidance open for reading, scrolling and copying."""
        dialog=getattr(self,'information_dialog',None)
        if not is_alive(dialog):
            dialog=QDialog(self)
            dialog.setWindowTitle('Outlier diagnostic information')
            layout=QVBoxLayout(dialog)
            text=QTextBrowser(dialog)
            header_html = '<h2 style="color:{}">Outlier diagnostic</h2>'.format(COLORS['primary'])
            help_html = (
                '<h3>How it works</h3><p><b>IQR</b> checks quartile limits; <b>MAD</b> checks '
                'distance from the median; optional <b>Z</b> uses the mean and standard deviation. '
                '<b>Local Moran / LISA</b> compares each value with its neighbors and tests '
                'the pattern using conditional permutations and row standardized weights. '
                '<b>Global Moran</b> describes the overall pattern, not individual points.</p>'
                '<h3>LISA classes</h3><p>H = above the overall mean; L = below it. '
                'The first letter describes the point, the second the average of its neighbors.</p>'
                '<table cellspacing="4">'
                '<tr><td><b>HL</b></td><td>High value among low neighbors: potential spatial outlier.</td></tr>'
                '<tr><td><b>LH</b></td><td>Low value among high neighbors: potential spatial outlier.</td></tr>'
                '<tr><td><b>HH / LL</b></td><td>Clusters of high / low values.</td></tr>'
                '<tr><td><b>NS</b></td><td>No significant local pattern; statistical flags may still apply.</td></tr>'
                '</table><p>HL, LH, HH and LL require significance at the selected alpha. '
                'Pseudo p values are not adjusted for multiple comparisons. Invalid marks unusable data.</p>'
                '<h3>Main parameters</h3><ul>'
                '<li><b>Neighborhood:</b> KNN uses the nearest k points (default 8); '
                'distance uses a radius in layer CRS units.</li>'
                '<li><b>Permutations / seed:</b> default 499 / 42. More permutations take longer; '
                'the same inputs and seed make repeated runs reproducible.</li>'
                '<li><b>Alpha:</b> significance cutoff (default 0.05); lower values are stricter. '
                '<b>Statistical thresholds:</b> IQR k = 1.5, modified Z (MAD) = 3.5, optional Z = 3.</li>'
                '<li><b>Consensus:</b> Any, All or At least N selected methods must flag the point.</li>'
                '</ul><p>With MAD = 0, equal values score zero; others receive signed infinity.</p>'
                '<h3>Using the tool</h3><p>Run diagnostics, then select points in the map, '
                'histogram, boxplot or table and review their values and local pattern. '
                'A flag is not automatically an error.</p>'
                '<p><b>Keep</b> retains a point; <b>Exclude</b> omits it from subsequent analysis; '
                '<b>Reset</b> clears the decision. The original layer stays unchanged. '
                'See the manual for detailed methods and interpretation.</p>'
            )
            text.setHtml(header_html + help_html)
            layout.addWidget(text)
            close=QPushButton('Close',dialog); close.clicked.connect(dialog.close)
            layout.addWidget(close)
            dialog.resize(640,520)
            screen=QApplication.primaryScreen()
            if screen is not None:
                available=screen.availableGeometry()
                dialog.resize(min(640,available.width()-40),min(520,available.height()-60))
            apply_theme(dialog)
            self.information_dialog=dialog
        dialog.show(); dialog.raise_(); dialog.activateWindow()

    def update_neighborhood_controls(self,*args):
        knn=self.neighborhood.currentText()=='KNN'
        self.knn.setEnabled(knn); self.distance.setEnabled(not knn)

    @staticmethod
    def _number(layout, row, col, label, value, low, high):
        spin = QDoubleSpinBox(); spin.setDecimals(6); spin.setRange(low, high); spin.setValue(value)
        layout.addWidget(QLabel(label), row, col); layout.addWidget(spin, row, col+1)
        return spin

    def settings(self):
        return dict(methods=tuple(k for k,v in self.methods.items() if v.isChecked()), k=self.iqr.value(),
            mad_limit=self.mad.value(), z_limit=self.z.value(), consensus=self.consensus.currentText(),
            at_least=self.votes.value(), neighborhood=self.neighborhood.currentText(), neighbors=self.knn.value(),
            distance=self.distance.value(), permutations=int(self.permutations.currentText()), alpha=self.alpha.value(), seed=self.seed.value())

    def restore_settings(self, settings):
        for key, widget in (("k",self.iqr),("mad_limit",self.mad),("z_limit",self.z),("at_least",self.votes),
            ("neighbors",self.knn),("distance",self.distance),("alpha",self.alpha),("seed",self.seed)):
            if key in settings: widget.setValue(settings[key])
        for key, widget in (("consensus",self.consensus),("neighborhood",self.neighborhood),("permutations",self.permutations)):
            if key in settings: widget.setCurrentText(str(settings[key]))
        for name, widget in self.methods.items(): widget.setChecked(name in settings.get("methods",("IQR","MAD")))

    def calculate(self):
        if getattr(self, "_bfi_jobs", set()): return
        settings = self.settings()
        xy, v = self.state.coordinates.copy(), self.state.values.copy()
        self.run.setEnabled(False); self.summary.setText("Calculating diagnostics")
        def complete(error, result):
            self.run.setEnabled(True)
            if error:
                self.summary.setText(str(error)); return
            self.state.result, self.state.settings = result, settings
            self.render()
        submit(self, "Outlier diagnostic", lambda cancel:self.engine.calculate(xy, v, settings, cancel), complete)

    def cancel_jobs(self):
        for task in tuple(getattr(self, "_bfi_jobs", ())): task.cancel()
        self.run.setEnabled(True)

    def closed(self):
        self.cancel_jobs()
        information=getattr(self,'information_dialog',None)
        if is_alive(information): information.close()
        if is_alive(self.layer):
            try: self.layer.selectionChanged.disconnect(self.layer_selection_changed)
            except (TypeError, RuntimeError): pass

    def render(self):
        r, s = self.state.result, self.state
        n = r["neighborhood"]; g = r["global_moran"]; stats = r["summary"]
        self.summary.setText("Valid: {valid}; invalid: {invalid}; mean: {mean:.4g}; median: {median:.4g}. Neighbors min/mean/max: {mn}/{av:.2f}/{mx}; isolated: {iso}. Global Moran I={gi:.4g}, pseudo p={gp:.4g} (overall diagnostic only). Analysis rows: {used}/{total}.".format(
            valid=stats["valid"], invalid=stats["invalid"], mean=stats.get("mean", np.nan), median=stats.get("median",np.nan), mn=n["min"],av=n["mean"],mx=n["max"],iso=n["isolated"],gi=g["I"],gp=g["p"],used=np.count_nonzero(s.analysis_mask),total=len(s.ids)))
        self.table_model.refresh()
        continuous=self.map_mode.currentIndex()==1
        for widget in (self.map_controls.palette,self.map_controls.automatic,self.map_controls.minimum,self.map_controls.maximum): widget.setEnabled(continuous)
        axes,self.map_artist,self.map_rows,self.bins,self.hist_patches=draw_diagnostics(self.fig,s,continuous)
        self.map_ax,self.hist_ax,self.box_ax=axes
        if continuous: self.map_display.restyle()
        self.highlights=[]
        self.canvas.draw_idle()

    def select_rows(self, rows):
        selection = self.table.selectionModel()
        from qgis.PyQt.QtCore import QItemSelectionModel
        blocked=selection.blockSignals(True); selection.clearSelection()
        flags = enum_value(QItemSelectionModel,"SelectionFlag","Select") | enum_value(QItemSelectionModel,"SelectionFlag","Rows")
        for row in rows: selection.select(self.table.model().index(int(row),0),flags)
        selection.blockSignals(blocked); self.selection_changed()

    def picked(self,event):
        if event.artist is getattr(self,"map_artist",None): self.select_rows(self.map_rows[event.ind])
        elif event.artist in getattr(self,"hist_patches",[]):
            i=self.hist_patches.index(event.artist); v=self.state.values
            self.select_rows(np.flatnonzero((v>=self.bins[i]) & (v <= self.bins[i+1] if i==len(self.bins)-2 else v<self.bins[i+1])))

    def box_clicked(self,event):
        if event.inaxes is getattr(self,"box_ax",None) and event.xdata is not None:
            valid=np.flatnonzero(np.isfinite(self.state.values))
            if len(valid): self.select_rows([valid[np.argmin(abs(self.state.values[valid]-event.xdata))]])

    def selection_changed(self,*args):
        rows=[index.row() for index in self.table.selectionModel().selectedRows()]
        if is_alive(self.layer):
            self._syncing=True
            try: self.layer.selectByIds([int(self.state.ids[i]) for i in rows])
            finally: self._syncing=False
        if self.state.result and hasattr(self,"map_ax"):
            for previous in getattr(self,"highlights",[]):
                try: previous.remove()
                except ValueError: pass
            xy=self.state.coordinates[rows]
            values=self.state.values[rows]; values=values[np.isfinite(values)]
            self.highlights=[self.map_ax.scatter(xy[:,0],xy[:,1],facecolors="none",edgecolors=COLORS["accent"],s=60),
                             self.box_ax.scatter(values,np.ones(len(values)),color=COLORS["accent"],s=22,zorder=5)]
            if len(self.bins)>1:
                counts,_=np.histogram(values,bins=self.bins)
                self.highlights.extend(self.hist_ax.step(self.bins,np.r_[counts,counts[-1]],where="post",color=COLORS["accent"],linewidth=2))
            self.canvas.draw_idle()

    def layer_selection_changed(self,*args):
        if not getattr(self,"_syncing",False):
            selected=set(self.layer.selectedFeatureIds())
            self.select_rows([i for i,fid in enumerate(self.state.ids) if int(fid) in selected])

    def decide(self, decision):
        rows=[index.row() for index in self.table.selectionModel().selectedRows()]
        self.state.decide(self.state.ids[rows],decision)
        self.plugin._update_ok_context()
        self.plugin._last_det_interpolation=self.plugin._last_ok_interpolation=None
        self.plugin._moran_cache.clear()
        self.plugin._clear_all_plots()
        active=getattr(self.plugin.ok_ctrl,"_active",None)
        if active is not None:
            active._baseline_initial=None; active._init_params=None
            active._exp_lags=active._exp_gamma=None; active._semivariogram_stale=True
            active._schedule_rebin()
        self.render()


def install_diagnostics(plugin):
    if not hasattr(plugin,"diagnostics_states"): plugin.diagnostics_states={}
    from .theme import apply_theme
    button=QPushButton("Outlier diagnostic",plugin.dlg)
    button.setObjectName("btnSpatialDiagnostics")
    page=next((plugin.dlg.mainTabs.widget(i) for i in range(plugin.dlg.mainTabs.count()) if plugin.dlg.mainTabs.tabText(i).strip().lower()=="data"),None)
    if page is None: return
    layout=page.layout()
    button.setText('Outlier diagnostic')
    button.setToolTip('Global Moran, Anselin Local Moran / LISA, IQR, MAD and Z score; review points and choose Keep / Exclude / Reset.')
    grid=getattr(plugin.dlg,'gridLayout_data',None)
    if grid is not None:
        grid.addWidget(button,4,0,1,3)
        detail=QLabel('Global Moran · Local Moran / LISA · statistical outliers')
        detail.setWordWrap(True); grid.addWidget(detail,4,3,1,3)
    elif isinstance(layout,QGridLayout): layout.addWidget(button,layout.rowCount(),0,1,max(1,layout.columnCount()))
    else: layout.addWidget(button)
    plugin.dlg.btnSpatialDiagnostics=button
    def open_dialog():
        try:
            state,layer=capture_data(plugin)
            old=getattr(plugin,"diagnostics_dialog",None)
            if is_alive(old): old.cancel_jobs(); old.closed(); old.deleteLater()
            dialog=SpatialDiagnosticsDialog(plugin,state,layer)
            plugin.diagnostics_dialog=dialog
            dialog.show()
        except Exception as exc:
            from .compat import log_exception
            log_exception("Opening Spatial Diagnostics")
            QMessageBox.warning(plugin.dlg,"Outlier diagnostic",str(exc))
    button.clicked.connect(open_dialog)
