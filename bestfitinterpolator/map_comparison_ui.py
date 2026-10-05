"""Framework comparison of validated, generated method rasters."""
import numpy as np
from qgis.PyQt.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QComboBox,QLabel,QPushButton,QCheckBox,QTabWidget,QDialog
from qgis.PyQt.QtCore import Qt
from matplotlib.figure import Figure
from .mpl_compat import FigureCanvas,NavigationToolbar
from .map_controls import MapDisplayControls,MatplotlibMapDisplay,common_value_range,scientific_colormap,SettingsButton
from .map_comparison import MapComparisonState,compare_rasters
from .async_jobs import submit
from .compat import is_alive,enum_value
from .theme import COLORS,apply_theme


class MapComparisonWidget(QWidget):
    def __init__(self,framework):
        super().__init__(framework.dlg)
        self.framework=framework
        self.state=MapComparisonState()
        self._syncing=False; self._loading=False
        root=QVBoxLayout(self)
        top=QHBoxLayout(); root.addLayout(top)
        self.method_a,self.method_b=QComboBox(),QComboBox()
        for label,combo in (("Map A",self.method_a),("Map B",self.method_b)):
            top.addWidget(QLabel(label)); top.addWidget(combo)
        self.compare=QPushButton("Compare maps"); top.addWidget(self.compare); self.compare.clicked.connect(self.calculate)
        self.settings_dialog=QDialog(self); self.settings_dialog.setWindowTitle('Comparison visualization settings')
        settings=QVBoxLayout(self.settings_dialog)
        self.same_palette=QCheckBox("Use same palette"); self.same_range=QCheckBox("Use same value range"); self.same_extent=QCheckBox("Use same extent")
        self.include=QCheckBox("Include this comparison in report")
        for w in (self.same_palette,self.same_range,self.same_extent): w.setChecked(True); settings.addWidget(w); w.toggled.connect(self.render)
        root.addWidget(self.include); self.include.toggled.connect(self.save_state)
        self.controls_a,self.controls_b=MapDisplayControls(self),MapDisplayControls(self)
        display_tabs=QTabWidget(); settings.addWidget(display_tabs)
        display_tabs.addTab(self.controls_a,'Map A / shared'); display_tabs.addTab(self.controls_b,'Map B')
        self.controls_a.show(); self.controls_b.show()
        done=QPushButton('Done'); done.clicked.connect(self.settings_dialog.close); settings.addWidget(done)
        apply_theme(self.settings_dialog)
        self.fig=Figure(figsize=(11,4)); self.canvas=FigureCanvas(self.fig); root.addWidget(self.canvas,1)
        self.canvas._bfi_display_source=True
        self.canvas._bfi_open_settings=self.show_settings
        self.canvas._bfi_settings_button=SettingsButton(self.canvas,self.show_settings)
        root.insertWidget(root.count()-1,NavigationToolbar(self.canvas,self))
        self.fig._bfi_export_size=(11,4)
        self.controls_a.changed.connect(self.render); self.controls_b.changed.connect(self.render)
        self.controls_a.fitRequested.connect(self.fit); self.controls_b.fitRequested.connect(self.fit)
        self.controls_a.scaleRequested.connect(self.set_scale); self.controls_b.scaleRequested.connect(self.set_scale)
        self.status=QLabel("Choose two evaluated methods. Compare generates any missing maps on the current grid."); self.status.setWordWrap(True); root.addWidget(self.status)
        self.refresh()
        self.method_a.currentIndexChanged.connect(self.selection_changed)
        self.method_b.currentIndexChanged.connect(self.selection_changed)

    def selection_changed(self,*args):
        if self.state.previews and (self.method_a.currentText(),self.method_b.currentText()) != (self.state.method_a,self.state.method_b):
            self.state=MapComparisonState(); self.fig.clear(); self.axes=[]; self.canvas.draw_idle(); self.save_state()
            self.status.setText("Methods changed. Compare the current maps before including them in the report.")

    def save_state(self,*args):
        self.state.include_report=self.include.isChecked()
        self.framework.state.__dict__["map_comparison"]=self.state

    def refresh(self):
        from qgis.core import QgsProject
        f=self.framework
        outputs=f.state.__dict__.get("interpolation_outputs",{})
        rows=list(f.state.validation_results or [])
        valid=list(dict.fromkeys(str(row.get('method','')) for row in rows if row.get('method') in f.state.validated_methods))
        for combo in (self.method_a,self.method_b):
            blocked=combo.blockSignals(True)
            previous=combo.currentText(); combo.clear()
            for method in valid:
                layer_id=outputs.get(method)
                layer=QgsProject.instance().mapLayer(layer_id)
                combo.addItem(method,layer_id if is_alive(layer) and layer.isValid() else None)
            if previous: combo.setCurrentText(previous)
            combo.blockSignals(blocked)
        if self.method_b.count()>1 and self.method_a.currentIndex()==self.method_b.currentIndex(): self.method_b.setCurrentIndex(1)
        self.compare.setEnabled(len(valid)>1)

    def show_settings(self):
        self.settings_dialog.show(); self.settings_dialog.raise_(); self.settings_dialog.activateWindow()

    def calculate(self):
        if self._loading: return
        from qgis.core import QgsProject
        methods=(self.method_a.currentText(),self.method_b.currentText())
        if not all(methods) or methods[0]==methods[1]: self.status.setText('Choose two different evaluated methods.'); return
        for method in methods:
            layer_id=self.framework.state.__dict__.get('interpolation_outputs',{}).get(method)
            layer=QgsProject.instance().mapLayer(layer_id)
            if not is_alive(layer) or not layer.isValid():
                self.status.setText('Generating {} for comparison'.format(method))
                if not self.framework._dispatch_and_register_map(method,purpose='comparison'):
                    detail=self.framework.state.__dict__.pop('last_dispatch_error','')
                    self.status.setText('Could not generate {}. {} The final interpolation result is unchanged.'.format(method,detail)); return
        self.refresh()
        outputs=self.framework.state.__dict__.get('interpolation_outputs',{})
        la=QgsProject.instance().mapLayer(outputs.get(methods[0])); lb=QgsProject.instance().mapLayer(outputs.get(methods[1]))
        if not is_alive(la) or not is_alive(lb): self.status.setText("Select two validated results."); return
        paths=(la.source().split("|")[0],lb.source().split("|")[0])
        methods=(self.method_a.currentText(),self.method_b.currentText())
        framework_state=self.framework.state
        self._loading=True; self.compare.setEnabled(False); self.status.setText("Calculating A − B on all aligned pixels")
        def complete(error,result):
            self._loading=False; self.compare.setEnabled(True)
            if self.framework.state is not framework_state: return
            if methods != (self.method_a.currentText(),self.method_b.currentText()):
                self.status.setText("Selected maps changed during calculation. Compare again."); return
            if error: self.status.setText(str(error)); return
            previews,statistics,grid,path=result
            self.state=MapComparisonState(method_a=methods[0],method_b=methods[1],previews=previews,statistics=statistics,grid=grid,difference_path=path)
            self.render()
        submit(self,"Framework map comparison",lambda cancel:compare_rasters(*paths,cancelled=cancel),complete)

    def render(self,*args):
        if not self.state.previews: return
        s=self.state; a,b,d=s.previews
        s.same_palette,s.same_range,s.same_extent=self.same_palette.isChecked(),self.same_range.isChecked(),self.same_extent.isChecked()
        self.controls_b.palette.setEnabled(not s.same_palette)
        self.controls_b.automatic.setEnabled(not s.same_range)
        for spin in (self.controls_b.minimum,self.controls_b.maximum):
            spin.setEnabled(not s.same_range and not self.controls_b.state.automatic)
        ca,cb=self.controls_a.state,self.controls_b.state
        s.palette_a=ca.palette; s.palette_b=ca.palette if s.same_palette else cb.palette
        full_a=np.asarray(s.grid.get("value_range_a",common_value_range(a)))
        full_b=np.asarray(s.grid.get("value_range_b",common_value_range(b)))
        ra=common_value_range(full_a,full_b) if s.same_range else common_value_range(full_a)
        rb=ra if s.same_range else common_value_range(full_b)
        if not ca.automatic: ra=(ca.minimum,ca.maximum)
        if s.same_range: rb=ra
        elif not cb.automatic: rb=(cb.minimum,cb.maximum)
        s.value_range=ra
        s.value_range_b=rb
        old_limits=[(ax.get_xlim(),ax.get_ylim()) for ax in getattr(self,"axes",())]
        self.fig.clear(); self.axes=self.fig.subplots(1,3)
        gt=s.grid["transform"]; rows,cols=s.grid["shape"]
        x=gt[0]+np.array([0,cols,0,cols])*gt[1]+np.array([0,0,rows,rows])*gt[2]
        y=gt[3]+np.array([0,cols,0,cols])*gt[4]+np.array([0,0,rows,rows])*gt[5]
        extent=(float(min(x)),float(max(x)),float(min(y)),float(max(y)))
        extremes=np.asarray([s.statistics["minimum"],s.statistics["maximum"]])
        maxdiff=max(float(np.nanmax(np.abs(extremes))) if np.any(np.isfinite(extremes)) else 1.,1.e-12)
        from matplotlib.transforms import Affine2D
        affine=Affine2D.from_values(gt[1],gt[4],gt[2],gt[5],gt[0],gt[3])
        for ax,array,title,cmap,limits in zip(self.axes,(a,b,d),(s.method_a,s.method_b,"Signed difference\nA − B"),(s.palette_a,s.palette_b,"RdBu_r"),(ra,rb,(-maxdiff,maxdiff))):
            im=ax.imshow(np.ma.masked_invalid(array),origin="upper",extent=(0,cols,rows,0),transform=affine+ax.transData,
                cmap=scientific_colormap(cmap),vmin=limits[0],vmax=limits[1],interpolation="nearest")
            ax.set_xlim(extent[:2]); ax.set_ylim(extent[2:]); ax.set_aspect("equal"); ax.set_title(title,fontsize=10)
            ax.set_xlabel("X (CRS units)"); ax.set_ylabel("Y (CRS units)")
            self.fig.colorbar(im,ax=ax,shrink=.75)
        for i,ax in enumerate(self.axes):
            if i<len(old_limits): ax.set_xlim(old_limits[i][0]); ax.set_ylim(old_limits[i][1])
            ax.callbacks.connect("xlim_changed",self.sync_extent); ax.callbacks.connect("ylim_changed",self.sync_extent)
        if s.same_extent: self.sync_extent(self.axes[0])
        self.fig.tight_layout(); self.canvas.draw_idle()
        stats=s.statistics
        self.status.setText("{} vs {} | Grid {} × {}; pixel size {:.6g} × {:.6g}; preview sampling every {} pixels. A − B: mean {:.6g}, median {:.6g}, min {:.6g}, max {:.6g}; {} valid common pixels. NoData excluded; no resampling. Spatial comparison complements validation.".format(
            s.method_a,s.method_b,cols,rows,abs(gt[1]),abs(gt[5]),s.grid.get("preview_step",1),stats["mean"],stats["median"],stats["minimum"],stats["maximum"],stats["count"]))
        self.save_state()

    def sync_extent(self,source):
        if self._syncing or not self.same_extent.isChecked(): return
        self._syncing=True
        try:
            for ax in self.axes:
                if ax is not source: ax.set_xlim(source.get_xlim(),emit=False); ax.set_ylim(source.get_ylim(),emit=False)
        finally: self._syncing=False
        self.state.view_extent=tuple(source.get_xlim())+tuple(source.get_ylim())

    def fit(self):
        if self.state.previews:
            gt=self.state.grid["transform"]; rows,cols=self.state.grid["shape"]
            corners=np.array([[0,0],[cols,0],[0,rows],[cols,rows]])
            x=gt[0]+corners[:,0]*gt[1]+corners[:,1]*gt[2]
            y=gt[3]+corners[:,0]*gt[4]+corners[:,1]*gt[5]
            for ax in self.axes: ax.set_xlim(float(x.min()),float(x.max())); ax.set_ylim(float(y.min()),float(y.max()))
            self.state.scale=0.
            self.state.view_extent=tuple(self.axes[0].get_xlim())+tuple(self.axes[0].get_ylim())
            self.save_state()
            self.canvas.draw_idle()

    def set_scale(self,scale):
        if not self.state.previews: return
        from osgeo import osr
        crs=osr.SpatialReference(); crs.SetFromUserInput(self.state.grid.get("crs",""))
        if not crs.IsProjected(): self.status.setText("Numeric scale requires a projected CRS."); return
        display=MatplotlibMapDisplay.__new__(MatplotlibMapDisplay)
        from qgis.PyQt.QtCore import QObject
        QObject.__init__(display,self.canvas)
        display.canvas=self.canvas; display.controls=self.controls_a; display.meters_per_unit=crs.GetLinearUnits()
        display.axes=lambda:list(self.axes)
        display.set_scale(scale)
        self.state.scale=float(scale)
        self.state.view_extent=tuple(self.axes[0].get_xlim())+tuple(self.axes[0].get_ylim())
        self.save_state()
