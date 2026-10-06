"""One advanced semivariogram window for ordinary and residual kriging."""
import numpy as np
import hashlib
from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QGridLayout, QHBoxLayout,
    QLabel, QComboBox, QDoubleSpinBox, QSpinBox, QPushButton, QCheckBox,
    QTableWidget, QTableWidgetItem, QMessageBox)
from matplotlib.figure import Figure
from .mpl_compat import FigureCanvas
from .compat import is_alive, enum_value
from .theme import apply_theme, COLORS
from .semivariogram_engine import SemivariogramEngine
from .async_jobs import submit


class SemivariogramSettingsDialog(QDialog):
    def __init__(self, controller, residual=False):
        super().__init__(controller.dlg)
        self.controller,self.residual=controller,residual
        self.use_reml=bool(not residual and getattr(controller,"_use_reml",False))
        self.engine=SemivariogramEngine("residual" if residual else ("ok_reml" if self.use_reml else "ok_mom"))
        self.setWindowTitle("Residual semivariogram settings" if residual else "Semivariogram model validation")
        self.resize(840,680)
        root=QVBoxLayout(self); layout=QGridLayout(); root.addLayout(layout)
        root.insertWidget(0,QLabel("Residuals of the fitted regression model" if residual else
            "Selected target variable ordinary kriging | Fit: " + ("REML" if self.use_reml else "MoM")))
        prefix="RK" if residual else "OK"
        self.cutoff=QDoubleSpinBox(); self.lag=QDoubleSpinBox()
        for spin in (self.cutoff,self.lag): spin.setDecimals(6); spin.setRange(.000001,1.e12)
        cutoff=float(getattr(controller.dlg,"spin"+prefix+"Cutoff").value())
        lag=float(getattr(controller.dlg,"spin"+prefix+"Lag").value())
        if residual and (cutoff<=0 or lag<=0) and controller._train_df is not None:
            frame=controller._train_df
            default_cutoff,default_lag=controller._default_cutoff_and_lag(frame["x"].to_numpy(float),frame["y"].to_numpy(float))
            if cutoff<=0: cutoff=default_cutoff
            if lag<=0: lag=default_lag
        self.cutoff.setValue(max(.000001,cutoff))
        self.lag.setValue(max(.000001,lag))
        self.mode=QComboBox(); self.mode.addItems(("Lag distance","Number of lags"))
        self.count=QSpinBox(); self.count.setRange(1,10000); self.count.setValue(max(1,int(round(self.cutoff.value()/self.lag.value()))))
        for row,(label,w) in enumerate((("Maximum distance",self.cutoff),("Lag input",self.mode),("Lag distance",self.lag),("Number of lags",self.count))):
            layout.addWidget(QLabel(label),row,0); layout.addWidget(w,row,1)
        self.candidates={}
        for col,token in enumerate(("spherical","exponential","gaussian")):
            chk=QCheckBox(token.capitalize()); chk.setChecked(token in getattr(controller,"_candidate_overrides",("spherical","exponential","gaussian")))
            layout.addWidget(chk,0,col+2); self.candidates[token]=chk
        self.status=QLabel("Existing automatic selection policy is preserved: " + ("RMSE, then SSE." if residual else "LCCC, then RMSE, then R².")); self.status.setWordWrap(True); root.addWidget(self.status)
        self.fig=Figure(figsize=(7,3)); self.canvas=FigureCanvas(self.fig); root.addWidget(self.canvas,1)
        from .map_controls import disable_display_settings
        disable_display_settings(self.canvas)
        self.table=QTableWidget(0,7); self.table.setHorizontalHeaderLabels(("Model","RMSE","RMSE%","MAE","R²","Pearson","LCCC")); root.addWidget(self.table)
        actions=QHBoxLayout(); root.addLayout(actions)
        self.preview=QPushButton("Update preview"); self.validate=QPushButton("Validate models"); self.apply=QPushButton("Apply selected model")
        for b in (self.preview,self.validate,self.apply): actions.addWidget(b)
        self.preview.clicked.connect(self.update_preview); self.validate.clicked.connect(self.run_validation); self.apply.clicked.connect(self.apply_settings)
        self.mode.currentIndexChanged.connect(self.sync_lag); self.count.valueChanged.connect(self.sync_lag); self.cutoff.valueChanged.connect(self.sync_lag)
        self.rows=[]; self.payload=None; self._revision=0
        self.lag.valueChanged.connect(self.invalidate)
        for checkbox in self.candidates.values(): checkbox.toggled.connect(self.invalidate)
        apply_theme(self)
        self.canvas.setMinimumHeight(180); self.table.setMaximumHeight(140)
        root.removeItem(actions)
        from .ui_refinement import scroll_content
        scroll_content(self); self.layout().addLayout(actions)
        from qgis.PyQt.QtWidgets import QApplication
        self.setMinimumSize(600,420); self.setSizeGripEnabled(True)
        screen=QApplication.primaryScreen()
        if screen is not None:
            available=screen.availableGeometry()
            self.resize(min(840,available.width()-40),min(680,available.height()-60))

    def sync_lag(self,*args):
        counted=self.mode.currentIndex()==1
        self.lag.setEnabled(not counted); self.count.setEnabled(counted)
        if counted: self.lag.setValue(self.cutoff.value()/self.count.value())
        self.invalidate()

    def invalidate(self, *args):
        self._revision += 1
        self.rows=[]; self.payload=None; self.table.setRowCount(0)
        self.status.setText("Settings changed. Update preview or run automatic validation.")

    @staticmethod
    def fingerprint(arrays):
        digest=hashlib.sha256()
        for array in arrays: digest.update(np.ascontiguousarray(array, dtype=float).tobytes())
        return digest.hexdigest()

    def arrays(self):
        c=self.controller
        if self.residual:
            if c._train_df is None or c._residuals is None: raise ValueError("Fit the regression stage before reviewing its residual semivariogram.")
            return c._train_df["x"].to_numpy(float).copy(),c._train_df["y"].to_numpy(float).copy(),np.asarray(c._residuals,float).copy()
        x,y,z=c._read_xy_z()
        if x is None: raise ValueError("Select at least five valid observations in Data.")
        return x.copy(),y.copy(),z.copy()

    def calculate(self,validation=False):
        if getattr(self,"_bfi_jobs",set()): return
        try: x,y,z=self.arrays()
        except Exception as exc: self.status.setText(str(exc)); return
        cutoff,lag=self.cutoff.value(),self.lag.value()
        candidates=tuple(k for k,v in self.candidates.items() if v.isChecked())
        if not candidates: self.status.setText("Select at least one candidate model."); return
        revision=self._revision; fingerprint=self.fingerprint((x,y,z))
        engine=self.engine
        self.preview.setEnabled(False); self.validate.setEnabled(False); self.apply.setEnabled(False)
        self.status.setText("Calculating residual semivariogram" if self.residual else "Calculating semivariogram")
        from .variogram_utils import bin_experimental_variogram
        def work(cancel):
            lags,gamma=bin_experimental_variogram(x,y,z,cutoff,lag)
            if not len(lags) and not self.use_reml: raise ValueError("No positive-distance pairs within the selected maximum distance.")
            rows=engine.validate(x,y,z,cutoff,lag,candidates,cancel) if validation else []
            if self.residual:
                fits=engine._fit_variogram_candidates(lags,gamma,cutoff)
                fit=next((f for f in fits if f.model==candidates[0]),fits[0])
                params=(fit.nugget,fit.psill,fit.range_)
            else:
                params=engine._guess_initial_params(lags,gamma,cutoff,candidates[0])
                if self.use_reml and not validation:
                    from .reml_bridge import fit_ok_reml_interface
                    fit=fit_ok_reml_interface(np.column_stack((x,y,z)),engine._model_text_from_token(candidates[0]),
                        init_from_mom=dict(zip(("nugget","psill","range"),params)),random_state=123)
                    params=tuple(float(fit[key]) for key in ("nugget","psill","range"))
            return lags,gamma,rows,params,candidates[0],cutoff,lag,candidates
        def completed(error,result):
            for b in (self.preview,self.validate,self.apply): b.setEnabled(True)
            if error: self.status.setText(str(error)); return
            try: unchanged=self.fingerprint(self.arrays()) == fingerprint
            except ValueError: unchanged=False
            if revision != self._revision or not unchanged:
                self.status.setText("Inputs changed during calculation. Run again with the current data and settings."); return
            self._validated_fingerprint=fingerprint
            self.payload=result; lags,gamma,rows,params,token,cutoff,lag,candidates=result
            self.rows=rows
            if rows and all(row.get("error") for row in rows):
                self.apply.setEnabled(False)
                self.fig.clear(); self.canvas.draw_idle()
                self.status.setText("No model passed validation. " + "; ".join(row["model"]+": "+row["error"] for row in rows))
                return
            if rows and "error" not in rows[0]:
                best=rows[0]; token=best["model_key"]
                params=(best["fit"].nugget,best["fit"].psill,best["fit"].range_) if self.residual else best.get("fitted_params",(best["nugget"],best["psill"],best["range"]))
            self.fig.clear(); ax=self.fig.add_subplot(111)
            if not self.use_reml:
                ax.plot(lags,gamma,"o",color=COLORS["primary"],label="Experimental")
            h=np.linspace(0,cutoff,200); ax.plot(h,self.engine._model_func(h,token,*params),color=COLORS["primary_dark"],label=token.capitalize())
            ax.set(xlabel="Lag distance (layer CRS units)",ylabel="Semivariance",title="Residual semivariogram" if self.residual else
                ("Semivariogram (REML model)" if self.use_reml else "Semivariogram"))
            ax.legend(); self.fig.tight_layout(); self.canvas.draw_idle()
            self.table.setRowCount(len(rows))
            for i,row in enumerate(rows):
                for j,key in enumerate(("model","rmse","rmse_pct","mae","r2","pearson","lccc")):
                    value=row.get(key,"—"); self.table.setItem(i,j,QTableWidgetItem(str(value) if isinstance(value,str) else "{:.5g}".format(value)))
            self.table.resizeColumnsToContents()
            self.status.setText("Selected: " + token.capitalize() + (". Lowest RMSE; SSE breaks ties." if self.residual else
                ". Highest LCCC; lower RMSE, then higher R² break ties.") + " Select a validation row to apply a different model." if rows else
                "Preview updated. Validate models to compare their cross validation metrics.")
            failures=[row["model"]+": "+row["error"] for row in rows if row.get("error")]
            if failures: self.status.setText(self.status.text()+" | "+"; ".join(failures))
        submit(self,"Semivariogram model validation" if validation else "Semivariogram preview",work,completed)

    def update_preview(self): self.calculate(False)
    def run_validation(self): self.calculate(True)

    def apply_settings(self):
        c=self.controller; prefix="RK" if self.residual else "OK"
        candidates=tuple(k for k,v in self.candidates.items() if v.isChecked())
        if not candidates: self.status.setText("Select at least one model."); return
        if self.rows and self.rows[max(0,self.table.currentRow())].get("error"):
            self.status.setText("The selected model failed validation. Select a successful model before applying."); return
        if self.payload:
            try: current=self.fingerprint(self.arrays())
            except ValueError as exc: self.status.setText(str(exc)); return
            if current != self._validated_fingerprint:
                self.invalidate(); self.status.setText("Data changed. Run validation again before applying a model."); return
        c._candidate_overrides=candidates
        c._programmatic_variogram_update=True
        try:
            for name,value in (("Cutoff",self.cutoff.value()),("Lag",self.lag.value())):
                widget=getattr(c.dlg,"spin"+prefix+name); blocked=widget.blockSignals(True); widget.setValue(value); widget.blockSignals(blocked)
            if not self.residual:
                c.dlg.cmbOKLagMode.setCurrentIndex(self.mode.currentIndex()); c.dlg.spinOKLagCount.setValue(self.count.value())
        finally: c._programmatic_variogram_update=False
        if self.residual:
            c._on_variogram_binning_changed()
            c._rk_cutoff,c._rk_lag_width=self.cutoff.value(),self.lag.value()
            if self.payload and self.payload[5:7]==(self.cutoff.value(),self.lag.value()):
                c._variogram_lags=np.insert(self.payload[0],0,0); c._variogram_gamma=np.insert(self.payload[1],0,0)
                if self.rows:
                    row=self.rows[max(0,self.table.currentRow())]; c._variogram_fit=row["fit"]
                    c._rk_model_validation_results=self.rows; c._set_variogram_ui(c._variogram_fit); c._update_variogram_validation_summary(); c._draw_variogram_plot()
        else:
            if self.rows:
                row=self.rows[max(0,self.table.currentRow())]
                c._programmatic_variogram_update=True
                try:
                    c._set_model_combo_by_token(row["model_key"])
                    params=row.get("fitted_params",(row["nugget"],row["psill"],row["range"]))
                    for name,value in zip(("Nugget","Psill","Range"),params):
                        getattr(c.dlg,"spinOK"+name).setValue(value)
                finally: c._programmatic_variogram_update=False
                c._user_variogram_overrides=True
                if c._use_reml: c._reml_fitted=True
            c._sync_variogram_state_from_ui(); c._schedule_rebin()
            c._rebin_timer.stop(); c._recalculate_stale()
            if self.rows:
                c._model_validation_results=self.rows
        self.status.setText("Settings applied. Existing fitting and validation criteria are retained.")

    def reject(self):
        for task in tuple(getattr(self,"_bfi_jobs",())): task.cancel()
        super().reject()


def install_advanced_button(controller,residual=False):
    dlg=controller.dlg; name="btnRKAdvancedSemivariogram" if residual else "btnOKAdvancedSemivariogram"
    button=getattr(dlg,name,None)
    if not is_alive(button):
        button=QPushButton("Advanced semivariogram settings",dlg); button.setObjectName(name); setattr(dlg,name,button)
        widget=getattr(dlg,"spinRKCutoff" if residual else "spinOKCutoff",None)
        parent=widget.parentWidget() if widget is not None else None
        layout=parent.layout() if parent is not None else None
        if isinstance(layout,QGridLayout): layout.addWidget(button,layout.rowCount(),0,1,max(1,layout.columnCount()))
        elif layout is not None: layout.addWidget(button)
    def open_settings(*args):
        show_advanced_settings(controller,residual)
    if hasattr(controller,"_connect"): controller._connect(button.clicked,open_settings)
    else: button.clicked.connect(open_settings)


def show_advanced_settings(controller,residual=False,validate=False):
    window=getattr(controller,"_advanced_dialog",None)
    if not is_alive(window):
        window=SemivariogramSettingsDialog(controller,residual)
        window.setAttribute(enum_value(__import__('qgis.PyQt.QtCore',fromlist=['Qt']).Qt,"WidgetAttribute","WA_DeleteOnClose"),True)
        controller._advanced_dialog=window
    window.show(); window.raise_()
    if validate: window.run_validation()
    return window
