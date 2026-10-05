"""One diagnostic figure renderer for the interactive window and report snapshots."""
import numpy as np
from .theme import COLORS, style_figure

LISA_COLORS = dict(HH="#c95742", LL="#3379ac", HL="#ed963c", LH="#5fb2a9", NS="#a7b2bc", Invalid="#555555")


def draw_diagnostics(figure, state, continuous=False):
    result=state.result
    figure.clear(); map_ax,hist_ax,box_ax=figure.subplots(1,3)
    rows=np.flatnonzero(np.isfinite(state.coordinates).all(axis=1))
    colors=np.ma.masked_invalid(state.values[rows]) if continuous else [LISA_COLORS[k] for k in result["lisa"][rows]]
    dense=len(rows)>10000
    scatter=map_ax.scatter(state.coordinates[rows,0],state.coordinates[rows,1],c=colors,s=4 if dense else 18,
                           marker="." if dense else "o",rasterized=dense,picker=5,cmap="viridis" if continuous else None)
    map_ax.set_aspect("equal")
    map_ax.set(xlabel="X (CRS units)",ylabel="Y (CRS units)",title="Target values" if continuous else "Anselin Local Moran (LISA)")
    if continuous: figure.colorbar(scatter,ax=map_ax,shrink=.75)
    else:
        for token in ("HH","LL","HL","LH","NS"):
            map_ax.scatter([],[],color=LISA_COLORS[token],label=token,s=16)
        map_ax.legend(fontsize=6,loc="best")
    valid=result["valid"]; bins=np.array([]); patches=[]
    if np.any(valid):
        _,bins,patches=hist_ax.hist(state.values[valid],bins="auto",color=COLORS["primary"],alpha=.7)
        for patch in patches: patch.set_picker(True)
        box_ax.boxplot(state.values[valid],vert=False)
    hist_ax.set(title="Histogram",xlabel=state.field_name,ylabel="Count")
    box_ax.set(title="Boxplot click a value",xlabel=state.field_name)
    figure.tight_layout(); style_figure(figure)
    return (map_ax,hist_ax,box_ax),scatter,rows,bins,list(patches)
