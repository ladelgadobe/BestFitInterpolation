# -*- coding: utf-8 -*-
"""PlotService — the single implementation of every matplotlib rendering the
tabs share, plus the clipboard/save utilities that were cloned seven times.

Renderer methods draw INTO a Figure from plain data and never call
canvas.draw() — the controller calls panel.canvas.draw_idle() afterwards, so
renderers stay headless-testable under the Agg backend."""

from __future__ import annotations

import os

import numpy as np

from ..logger import get_logger

logger = get_logger(__name__)


class PlotService:
    # ------------------------------ renderers -------------------------------

    def obs_vs_pred(self, fig, observed, predicted, metrics=None, title=None):
        fig.clear()
        ax = fig.add_subplot(111)
        o = np.asarray(observed, dtype=float)
        p = np.asarray(predicted, dtype=float)
        mask = np.isfinite(o) & np.isfinite(p)
        ax.scatter(o[mask], p[mask], s=28, alpha=0.8, edgecolor="k", linewidths=0.4)
        if mask.any():
            lo = float(min(o[mask].min(), p[mask].min()))
            hi = float(max(o[mask].max(), p[mask].max()))
            ax.plot([lo, hi], [lo, hi], "k--", lw=1, label="1:1")
            ax.legend(loc="best", fontsize=8)
        ax.set_xlabel("Observed")
        ax.set_ylabel("Predicted")
        if title:
            ax.set_title(title)
        if metrics is not None:
            text = (
                f"RMSE: {metrics.rmse:.3f}\n"
                f"R²: {metrics.r2:.3f}\n"
                f"LCCC: {metrics.lccc:.3f}"
            )
            ax.text(
                0.03, 0.97, text, transform=ax.transAxes, va="top", ha="left",
                fontsize=8, bbox=dict(boxstyle="round", fc="white", alpha=0.75),
            )

    def variogram(self, fig, lags, gamma, model=None, title=None):
        """Empirical points + optional fitted VariogramModel curve."""
        from ..core.variogram import model_gamma

        fig.clear()
        ax = fig.add_subplot(111)
        lags = np.asarray(lags, dtype=float)
        gamma = np.asarray(gamma, dtype=float)
        ax.plot(lags, gamma, "o", ms=5, label="Experimental")
        if model is not None and lags.size:
            h = np.linspace(0, float(np.nanmax(lags)) * 1.05, 200)
            curve = model_gamma(h, model.model, model.nugget, model.psill, model.range_)
            ax.plot(h, curve, "-", lw=1.5,
                    label=f"{model.model.capitalize()} ({model.strategy.upper()})")
        ax.set_xlabel("Distance (h)")
        ax.set_ylabel("Semivariance γ(h)")
        ax.legend(loc="best", fontsize=8)
        if title:
            ax.set_title(title)

    def point_map(self, fig, xy, values, boundary_rings=None, variable_name="",
                  cmap="viridis"):
        fig.clear()
        ax = fig.add_subplot(111)
        ax.set_aspect("equal")
        if boundary_rings:
            for ring in boundary_rings:
                ring = np.asarray(ring, dtype=float)
                ax.plot(ring[:, 0], ring[:, 1], lw=1, color="tab:blue")
        xy = np.asarray(xy, dtype=float)
        sc = ax.scatter(xy[:, 0], xy[:, 1], c=np.asarray(values, dtype=float),
                        cmap=cmap, s=40, edgecolor="k", alpha=1)
        cbar = fig.colorbar(sc, ax=ax, orientation="vertical")
        if variable_name:
            cbar.set_label(f"'{variable_name}'")

    def raster_preview(self, fig, array2d, grid, title=None, cmap="viridis"):
        """Masked-array imshow over the grid extent."""
        fig.clear()
        ax = fig.add_subplot(111)
        arr = np.asarray(array2d, dtype=float)
        gt = grid.geotransform
        extent = (
            gt[0],
            gt[0] + gt[1] * grid.n_cols,
            gt[3] + gt[5] * grid.n_rows,
            gt[3],
        )
        masked = np.ma.masked_invalid(arr)
        im = ax.imshow(masked, extent=extent, origin="upper", cmap=cmap)
        fig.colorbar(im, ax=ax, orientation="vertical")
        ax.set_aspect("equal")
        if title:
            ax.set_title(title)

    def importance_bars(self, fig, names, importances, title="Variable importance"):
        fig.clear()
        ax = fig.add_subplot(111)
        names = list(names)
        vals = np.asarray(importances, dtype=float)
        order = np.argsort(vals)
        ax.barh(np.array(names, dtype=object)[order], vals[order])
        ax.set_xlabel("Importance")
        if title:
            ax.set_title(title)

    def correlation_matrix(self, fig, matrix, labels):
        fig.clear()
        ax = fig.add_subplot(111)
        m = np.asarray(matrix, dtype=float)
        im = ax.imshow(m, vmin=-1, vmax=1, cmap="RdBu_r")
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels, fontsize=8)
        for i in range(m.shape[0]):
            for j in range(m.shape[1]):
                if np.isfinite(m[i, j]):
                    ax.text(j, i, f"{m[i, j]:.2f}", ha="center", va="center", fontsize=7)
        fig.colorbar(im, ax=ax)

    # --------------------------- Qt-side utilities --------------------------

    def copy_to_clipboard(self, fig):
        """Copy a figure to the system clipboard as an image (the single
        implementation of the seven legacy clones)."""
        try:
            from qgis.PyQt.QtGui import QImage
            from qgis.PyQt.QtWidgets import QApplication

            import io

            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=200, bbox_inches="tight")
            buf.seek(0)
            image = QImage.fromData(buf.getvalue(), "PNG")
            QApplication.clipboard().setImage(image)
        except Exception:
            logger.exception("Could not copy figure to clipboard")

    def save_dialog(self, fig, parent, suggested_name):
        from qgis.PyQt.QtWidgets import QFileDialog

        suggested = os.path.join(os.path.expanduser("~"), f"{suggested_name}.png")
        path, _ = QFileDialog.getSaveFileName(
            parent, "Save graph", suggested, "PNG Images (*.png)"
        )
        if path:
            fig.savefig(path, dpi=300, bbox_inches="tight")
        return path
