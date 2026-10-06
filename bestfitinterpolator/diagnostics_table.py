"""Lazy table values keep large diagnostic datasets out of QTableWidget items."""
import numpy as np
from qgis.PyQt.QtCore import QAbstractTableModel,Qt,QModelIndex
from .compat import enum_value

HEADERS = ("ID", "Value", "X", "Y", "IQR flag", "MAD flag", "Z flag", "Statistical votes",
    "Statistical flag", "Neighbors", "Local median", "Local residual", "Robust local score",
    "Local Moran I", "Pseudo p", "LISA class", "Spatial outlier", "Combined class", "User decision")


class DiagnosticsTableModel(QAbstractTableModel):
    def __init__(self,state,parent=None):
        super().__init__(parent); self.state=state

    def rowCount(self,parent=QModelIndex()):
        return 0 if parent.isValid() or not self.state.result else len(self.state.ids)

    def columnCount(self,parent=QModelIndex()): return 0 if parent.isValid() else len(HEADERS)

    def headerData(self,section,orientation,role=enum_value(Qt,"ItemDataRole","DisplayRole")):
        if role != enum_value(Qt,"ItemDataRole","DisplayRole"): return None
        return HEADERS[section] if orientation == enum_value(Qt,"Orientation","Horizontal") else section+1

    def data(self,index,role=enum_value(Qt,"ItemDataRole","DisplayRole")):
        if not index.isValid() or role != enum_value(Qt,"ItemDataRole","DisplayRole"): return None
        i,j=index.row(),index.column(); s=self.state; r=s.result
        row=(s.ids[i],s.values[i],*s.coordinates[i],*[r["flags"][key][i] for key in ("IQR","MAD","Z")],
             "{}/{}".format(r["votes"][i],len(r["methods"])),r["statistical"][i],r["neighbors"][i],
             r["local_median"][i],r["local_residual"][i],r["robust_local_score"][i],r["local_i"][i],
             r["pseudo_p"][i],r["lisa"][i],r["spatial_outlier"][i],r["combined"][i],s.decisions.get(int(s.ids[i]),"Undecided"))
        value=row[j]
        if isinstance(value,(bool,np.bool_)): return "Flagged" if value else "Normal"
        return "{:.6g}".format(value) if isinstance(value,(float,np.floating)) else str(value)

    def refresh(self): self.beginResetModel(); self.endResetModel()
