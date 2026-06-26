# -*- coding: utf-8 -*-
"""
framework_decision_tree_view.py

Dynamic vector decision-tree view for the Framework tab.

The widget draws the article-inspired univariate and full frameworks with
QGraphicsView/QGraphicsScene. It highlights the active path from the current
Framework diagnostics and uses the existing recommended method list as the
source of truth for final method highlighting.
"""

from __future__ import annotations

import math
import os
import tempfile
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

try:
    from qgis.PyQt.QtCore import QPointF, QRectF, Qt
    from qgis.PyQt.QtGui import (
        QBrush,
        QColor,
        QFont,
        QImage,
        QPainter,
        QPainterPath,
        QPen,
        QPolygonF,
    )
    from qgis.PyQt.QtWidgets import (
        QFileDialog,
        QGraphicsDropShadowEffect,
        QGraphicsItem,
        QGraphicsPathItem,
        QGraphicsPolygonItem,
        QGraphicsRectItem,
        QGraphicsScene,
        QGraphicsTextItem,
        QGraphicsView,
        QMenu,
        QMessageBox,
        QDialog,
        QVBoxLayout,
    )
except Exception:  # pragma: no cover
    from PyQt5.QtCore import QPointF, QRectF, Qt
    from PyQt5.QtGui import (
        QBrush,
        QColor,
        QFont,
        QImage,
        QPainter,
        QPainterPath,
        QPen,
        QPolygonF,
    )
    from PyQt5.QtWidgets import (
        QFileDialog,
        QGraphicsDropShadowEffect,
        QGraphicsItem,
        QGraphicsPathItem,
        QGraphicsPolygonItem,
        QGraphicsRectItem,
        QGraphicsScene,
        QGraphicsTextItem,
        QGraphicsView,
        QMenu,
        QMessageBox,
        QDialog,
        QVBoxLayout,
    )


Node = Dict[str, Any]
Edge = Dict[str, Any]
ActivePath = Tuple[Set[str], Set[str]]


class FlowchartNodeItem(QGraphicsItem):
    """Single painted node with clipped, centered text."""

    COLORS = {
        "start": ("#f8fafc", "#94a3b8", "#ecfdf5"),
        "process": ("#f8fafc", "#94a3b8", "#ecfdf5"),
        "sample": ("#f0ebff", "#a78bfa", "#ede9fe"),
        "decision": ("#ffe8f0", "#f9a8d4", "#fce7f3"),
        "method": ("#dcfce7", "#86efac", "#bbf7d0"),
        "validation": ("#dbeafe", "#93c5fd", "#bfdbfe"),
        "note": ("#fff7ed", "#fdba74", "#ffedd5"),
    }

    def __init__(self, rect: QRectF, label: str, node_type: str, active: bool = False, parent=None):
        super().__init__(parent)
        self.rect = QRectF(rect)
        self.label = str(label or "")
        self.node_type = str(node_type or "process")
        self.active = bool(active)
        self.setZValue(10)

    def boundingRect(self) -> QRectF:
        return self.rect.adjusted(-5, -5, 5, 5)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        fill_hex, border_hex, active_fill_hex = self.COLORS.get(self.node_type, self.COLORS["process"])
        fill = QColor(active_fill_hex if self.active else fill_hex)
        border = QColor("#16a34a" if self.active else border_hex)
        pen = QPen(border, 3.0 if self.active else 1.25)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(QBrush(fill))

        shape_path = QPainterPath()
        if self.node_type in {"sample", "decision"}:
            poly = QPolygonF([
                QPointF(self.rect.center().x(), self.rect.top()),
                QPointF(self.rect.right(), self.rect.center().y()),
                QPointF(self.rect.center().x(), self.rect.bottom()),
                QPointF(self.rect.left(), self.rect.center().y()),
            ])
            shape_path.addPolygon(poly)
            painter.drawPolygon(poly)
            text_rect = self.rect.adjusted(
                self.rect.width() * 0.20,
                self.rect.height() * 0.24,
                -self.rect.width() * 0.20,
                -self.rect.height() * 0.24,
            )
        else:
            shape_path.addRoundedRect(self.rect, 8, 8)
            painter.drawRoundedRect(self.rect, 8, 8)
            text_rect = self.rect.adjusted(10, 6, -10, -6)

        font_size = 14
        if self.node_type in {"start", "process", "note", "validation"}:
            font_size = 14
        if self.node_type == "method":
            font_size = 14
        font = QFont("Segoe UI", font_size)
        if self.active or self.node_type in {"method", "validation"}:
            font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#1f2937"))
        painter.setClipPath(shape_path)
        painter.drawText(text_rect, Qt.AlignCenter | Qt.TextWordWrap, self.label)
        painter.restore()


class SummaryStripItem(QGraphicsItem):
    """Bottom panel that carries live diagnostic values outside the tree nodes."""

    def __init__(self, rect: QRectF, text: str, parent=None):
        super().__init__(parent)
        self.rect = QRectF(rect)
        self.text = str(text or "")
        self.setZValue(20)

    def boundingRect(self) -> QRectF:
        return self.rect.adjusted(-3, -3, 3, 3)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setBrush(QBrush(QColor("#f8fafc")))
        painter.setPen(QPen(QColor("#cbd5e1"), 1.1))
        painter.drawRoundedRect(self.rect, 8, 8)
        font = QFont("Segoe UI", 12)
        painter.setFont(font)
        painter.setPen(QColor("#334155"))
        painter.drawText(self.rect.adjusted(14, 6, -14, -6), Qt.AlignCenter | Qt.TextWordWrap, self.text)
        painter.restore()


class FrameworkDecisionTreeView(QGraphicsView):
    """Vector flowchart for the Framework Decision section."""

    NODE_COLORS = {
        "start": ("#f5f7fb", "#6b7280"),
        "process": ("#f5f7fb", "#94a3b8"),
        "sample": ("#eee8ff", "#8b5cf6"),
        "decision": ("#fde8ef", "#f472b6"),
        "method": ("#dcfce7", "#22c55e"),
        "validation": ("#dbeafe", "#3b82f6"),
        "note": ("#fff7ed", "#fb923c"),
    }
    ACTIVE_GREEN = QColor("#16a34a")
    EDGE_GRAY = QColor("#cbd5e1")
    TEXT_COLOR = QColor("#1f2937")

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing, True)
        self.setRenderHint(QPainter.TextAntialiasing, True)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setToolTip("Use the mouse wheel to zoom. Drag to pan. Right-click for zoom, export, and larger view.")
        self.customContextMenuRequested.connect(self._show_context_menu)

        self._nodes: List[Node] = []
        self._edges: List[Edge] = []
        self._node_by_id: Dict[str, Node] = {}
        self._active_nodes: Set[str] = set()
        self._active_edges: Set[str] = set()
        self._framework_type = "univariate"
        self._data_characteristics: Dict[str, Any] = {}
        self._auto_fit = True

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def update_tree(
        self,
        framework_type: str,
        data_characteristics: Dict[str, Any],
        active_path: Optional[Any] = None,
    ) -> None:
        """Rebuild and redraw the selected framework tree."""
        self._framework_type = self._normalise_framework_type(framework_type)
        self._data_characteristics = dict(data_characteristics or {})

        if self._framework_type == "full":
            nodes, edges = self.build_full_tree()
        else:
            nodes, edges = self.build_univariate_tree()

        self._nodes = self._inject_live_labels(nodes, self._data_characteristics)
        self._edges = edges
        self._node_by_id = {node["id"]: node for node in self._nodes}

        if active_path is None:
            self._active_nodes, self._active_edges = self.evaluate_active_path(
                self._framework_type,
                self._data_characteristics,
            )
        else:
            self._active_nodes, self._active_edges = self._coerce_active_path(active_path)

        self.draw_tree(self._nodes, self._edges, self._active_nodes, self._active_edges)

    def build_univariate_tree(self) -> Tuple[List[Node], List[Edge]]:
        """Return the compact univariate framework layout."""
        PROCESS_W, PROCESS_H = 220, 68
        DECISION_W, DECISION_H = 230, 114
        METHOD_W, METHOD_H = 132, 58
        VALIDATION_W, VALIDATION_H = 210, 68

        def n(node_id, label, node_type, cx, y, width=None, height=None):
            if node_type in {"sample", "decision"}:
                width = width or DECISION_W
                height = height or DECISION_H
            elif node_type == "method":
                width = width or METHOD_W
                height = height or METHOD_H
            elif node_type == "validation":
                width = width or VALIDATION_W
                height = height or VALIDATION_H
            else:
                width = width or PROCESS_W
                height = height or PROCESS_H
            return self._node(node_id, label, node_type, cx - width / 2.0, y, width, height)

        nodes = [
            n("soil", "Soil samples", "start", 820, 35),
            n("n_lt_100", "n < 100?", "sample", 820, 155),
            n("n_ge_50", "n >= 50?", "sample", 500, 300),
            n("spatial_50_99", "MI p < 0.05?", "decision", 500, 445),
            n("sdi_50_99_cluster", "SDI >= 80%?", "decision", 300, 600),
            n("sdi_50_99_random", "SDI < 60%?", "decision", 700, 600),
            n("spatial_100", "MI p < 0.05?", "decision", 1140, 300),
            n("sdi_100_low", "SDI < 60%?", "decision", 1140, 445),
            n("sdi_100_high", "SDI >= 80%?", "decision", 1140, 600),
            n("m_idw", "IDW", "method", 340, 820),
            n("m_tps", "TPS", "method", 520, 820),
            n("m_ok", "OK", "method", 700, 820),
            n("m_reml", "REML", "method", 610, 930, width=126, height=54),
            n("m_mom", "MoM", "method", 790, 930, width=126, height=54),
            n("validation", "LOOCV / LCCC", "validation", 700, 1050),
        ]
        edges = [
            self._edge("soil", "n_lt_100"),
            self._edge("n_lt_100", "n_ge_50", "Yes"),
            self._edge("n_lt_100", "spatial_100", "No"),
            self._edge("n_ge_50", "m_idw", "No"),
            self._edge("n_ge_50", "m_tps", "No"),
            self._edge("n_ge_50", "spatial_50_99", "Yes"),
            self._edge("spatial_50_99", "sdi_50_99_cluster", "Yes"),
            self._edge("spatial_50_99", "sdi_50_99_random", "No"),
            self._edge("sdi_50_99_cluster", "m_ok", "Yes"),
            self._edge("sdi_50_99_cluster", "m_ok", "No", "e_sdi_50_99_cluster_no_ok"),
            self._edge("sdi_50_99_cluster", "m_tps", "No"),
            self._edge("sdi_50_99_cluster", "m_idw", "No"),
            self._edge("sdi_50_99_random", "m_tps", "Yes"),
            self._edge("sdi_50_99_random", "m_tps", "No", "e_sdi_50_99_random_no_tps"),
            self._edge("sdi_50_99_random", "m_ok", "No"),
            self._edge("spatial_100", "sdi_100_low", "Yes"),
            self._edge("spatial_100", "m_idw", "No"),
            self._edge("spatial_100", "m_tps", "No"),
            self._edge("sdi_100_low", "m_tps", "Yes"),
            self._edge("sdi_100_low", "sdi_100_high", "No"),
            self._edge("sdi_100_high", "m_tps", "Yes"),
            self._edge("sdi_100_high", "m_ok", "Yes"),
            self._edge("sdi_100_high", "m_tps", "No", "e_sdi_100_high_no_tps"),
            self._edge("sdi_100_high", "m_idw", "No", "e_sdi_100_high_no_idw"),
            self._edge("sdi_100_high", "m_ok", "No", "e_sdi_100_high_no_ok"),
            self._edge("m_ok", "m_reml", "n < 100"),
            self._edge("m_ok", "m_mom", "n >= 100"),
            self._edge("m_idw", "validation"),
            self._edge("m_tps", "validation"),
            self._edge("m_ok", "validation"),
            self._edge("m_reml", "validation"),
            self._edge("m_mom", "validation"),
        ]
        return nodes, edges

    def build_full_tree(self) -> Tuple[List[Node], List[Edge]]:
        """Return the complete framework layout with covariate-aware branches."""
        PROCESS_W, PROCESS_H = 220, 68
        DECISION_W, DECISION_H = 230, 114
        METHOD_W, METHOD_H = 132, 58
        VALIDATION_W, VALIDATION_H = 210, 68

        def n(node_id, label, node_type, cx, y, width=None, height=None):
            if node_type in {"sample", "decision"}:
                width = width or DECISION_W
                height = height or DECISION_H
            elif node_type == "method":
                width = width or METHOD_W
                height = height or METHOD_H
            elif node_type == "validation":
                width = width or VALIDATION_W
                height = height or VALIDATION_H
            elif node_type == "note":
                width = width or 230
                height = height or PROCESS_H
            else:
                width = width or PROCESS_W
                height = height or PROCESS_H
            return self._node(node_id, label, node_type, cx - width / 2.0, y, width, height)

        nodes = [
            n("soil", "Soil samples", "start", 1100, 35),
            n("covariates", "Covariates available?", "decision", 1100, 155, width=250, height=122),
            n("univariate_fallback", "Use univariate path", "note", 1460, 175),
            n("n_lt_100", "n < 100?", "sample", 1100, 315),
            n("n_ge_50", "n >= 50?", "sample", 760, 470),
            n("spatial_lt_50", "MI p < 0.05?", "decision", 420, 625),
            n("spatial_50_99", "MI p < 0.05?", "decision", 760, 625),
            n("sdi_50_99_cluster", "SDI >= 80%?", "decision", 590, 780),
            n("sdi_50_99_random", "SDI < 60%?", "decision", 930, 780),
            n("spatial_100", "MI p < 0.05?", "decision", 1440, 470),
            n("sdi_100_low", "SDI < 60%?", "decision", 1440, 625),
            n("sdi_100_40", "SDI < 40%?", "decision", 1280, 780),
            n("sdi_100_high", "SDI >= 80%?", "decision", 1600, 780),
            n("m_idw", "IDW", "method", 420, 1010),
            n("m_tps", "TPS", "method", 600, 1010),
            n("m_ok", "OK", "method", 780, 1010),
            n("m_rk", "RK", "method", 1000, 1010),
            n("m_rfe", "RFE", "method", 1180, 1010),
            n("m_svm", "SVM", "method", 1360, 1010),
            n("m_reml", "REML", "method", 690, 1125, width=126, height=54),
            n("m_mom", "MoM", "method", 870, 1125, width=126, height=54),
            n("validation", "LOOCV / LCCC", "validation", 940, 1245),
        ]
        edges = [
            self._edge("soil", "covariates"),
            self._edge("covariates", "n_lt_100", "Yes"),
            self._edge("covariates", "univariate_fallback", "No"),
            self._edge("univariate_fallback", "validation"),
            self._edge("n_lt_100", "n_ge_50", "Yes"),
            self._edge("n_lt_100", "spatial_100", "No"),
            self._edge("n_ge_50", "spatial_lt_50", "No"),
            self._edge("n_ge_50", "spatial_50_99", "Yes"),
            self._edge("spatial_lt_50", "m_rk", "Yes"),
            self._edge("spatial_lt_50", "m_idw", "Yes"),
            self._edge("spatial_lt_50", "m_tps", "Yes"),
            self._edge("spatial_lt_50", "m_idw", "No", "e_spatial_lt_50_no_idw"),
            self._edge("spatial_lt_50", "m_tps", "No", "e_spatial_lt_50_no_tps"),
            self._edge("spatial_50_99", "sdi_50_99_cluster", "Yes"),
            self._edge("spatial_50_99", "sdi_50_99_random", "No"),
            self._edge("sdi_50_99_cluster", "m_svm", "Yes"),
            self._edge("sdi_50_99_cluster", "m_rfe", "Yes"),
            self._edge("sdi_50_99_cluster", "m_rk", "Yes"),
            self._edge("sdi_50_99_cluster", "m_ok", "Yes"),
            self._edge("sdi_50_99_cluster", "m_ok", "No", "e_sdi_50_99_cluster_no_ok"),
            self._edge("sdi_50_99_cluster", "m_tps", "No"),
            self._edge("sdi_50_99_cluster", "m_idw", "No"),
            self._edge("sdi_50_99_random", "m_tps", "Yes"),
            self._edge("sdi_50_99_random", "m_svm", "No"),
            self._edge("spatial_100", "sdi_100_low", "Yes"),
            self._edge("spatial_100", "m_tps", "No"),
            self._edge("spatial_100", "m_svm", "No"),
            self._edge("sdi_100_low", "sdi_100_40", "Yes"),
            self._edge("sdi_100_low", "sdi_100_high", "No"),
            self._edge("sdi_100_40", "m_tps", "Yes"),
            self._edge("sdi_100_40", "m_tps", "No", "e_sdi_100_40_no_tps"),
            self._edge("sdi_100_40", "m_svm", "No"),
            self._edge("sdi_100_high", "m_svm", "Yes"),
            self._edge("sdi_100_high", "m_rk", "Yes"),
            self._edge("sdi_100_high", "m_rfe", "Yes"),
            self._edge("sdi_100_high", "m_ok", "Yes"),
            self._edge("sdi_100_high", "m_tps", "No"),
            self._edge("sdi_100_high", "m_rk", "No", "e_sdi_100_high_no_rk"),
            self._edge("sdi_100_high", "m_rfe", "No", "e_sdi_100_high_no_rfe"),
            self._edge("sdi_100_high", "m_idw", "No"),
            self._edge("sdi_100_high", "m_ok", "No", "e_sdi_100_high_no_ok"),
            self._edge("m_ok", "m_reml", "n < 100"),
            self._edge("m_ok", "m_mom", "n >= 100"),
            self._edge("m_idw", "validation"),
            self._edge("m_tps", "validation"),
            self._edge("m_ok", "validation"),
            self._edge("m_rk", "validation"),
            self._edge("m_rfe", "validation"),
            self._edge("m_svm", "validation"),
            self._edge("m_reml", "validation"),
            self._edge("m_mom", "validation"),
        ]
        return nodes, edges

    def evaluate_active_path(
        self,
        framework_type: str,
        data_characteristics: Dict[str, Any],
    ) -> ActivePath:
        """Return active nodes and edges for the current diagnostics."""
        framework_type = self._normalise_framework_type(framework_type)
        n = self._safe_int(data_characteristics.get("n_samples"))
        sdi = self._safe_float(data_characteristics.get("sdi_value"))
        clustered = self._is_clustered(data_characteristics)
        methods = self._normalise_methods(data_characteristics.get("recommended_methods"))
        ok_fit = self._normalise_fit_method(data_characteristics, n)
        covariates = bool(data_characteristics.get("covariates_available"))

        active_nodes: Set[str] = {"soil", "validation"}
        active_edges: Set[str] = {"e_soil_n_lt_100"} if framework_type == "univariate" else {"e_soil_covariates"}

        if framework_type == "full":
            active_nodes.add("covariates")
            if not covariates:
                active_nodes.add("univariate_fallback")
                active_edges.update({"e_covariates_univariate_fallback", "e_univariate_fallback_validation"})
                self._activate_methods(methods, ok_fit, active_nodes, active_edges)
                self._sync_terminal_edges_to_methods(active_nodes, active_edges)
                return active_nodes, active_edges
            active_edges.add("e_covariates_n_lt_100")

        active_nodes.add("n_lt_100")
        if n is None:
            self._activate_methods(methods, ok_fit, active_nodes, active_edges)
            return active_nodes, active_edges

        if framework_type == "full":
            self._evaluate_full_path(n, sdi, clustered, active_nodes, active_edges)
        else:
            self._evaluate_univariate_path(n, sdi, clustered, active_nodes, active_edges)

        self._activate_methods(methods, ok_fit, active_nodes, active_edges)
        self._sync_terminal_edges_to_methods(active_nodes, active_edges)
        return active_nodes, active_edges

    def draw_tree(
        self,
        nodes: Sequence[Node],
        edges: Sequence[Edge],
        active_nodes: Iterable[str],
        active_edges: Iterable[str],
    ) -> None:
        """Draw all edges and nodes."""
        self._scene.clear()
        self._scene.setBackgroundBrush(QBrush(QColor("#ffffff")))
        active_node_set = set(active_nodes)
        active_edge_set = set(active_edges)

        for edge in edges:
            self.draw_edge(edge, edge["id"] in active_edge_set)
        for node in nodes:
            self.draw_node(node, node["id"] in active_node_set)
        self.draw_summary_strip(self._data_characteristics)

        bounds = self._scene.itemsBoundingRect().adjusted(-35, -35, 35, 35)
        self._scene.setSceneRect(bounds)
        self._fit_to_view()

    def draw_node(self, node: Node, active: bool = False):
        """Draw one node with robust clipped text."""
        rect = QRectF(float(node["x"]), float(node["y"]), float(node["width"]), float(node["height"]))
        item = FlowchartNodeItem(rect, str(node.get("label", "")), str(node.get("type", "process")), active)
        self._scene.addItem(item)

        if active:
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(8)
            shadow.setOffset(0, 1)
            shadow.setColor(QColor(22, 163, 74, 45))
            item.setGraphicsEffect(shadow)

        return item

    def draw_edge(self, edge: Edge, active: bool = False):
        """Draw one connector with an arrowhead and optional branch label."""
        source = self._node_by_id.get(edge["source"])
        target = self._node_by_id.get(edge["target"])
        if not source or not target:
            return None

        source_rect = self._rect_for(source)
        target_rect = self._rect_for(target)
        waypoint_values = edge.get("waypoints") or []
        waypoints = [QPointF(float(x), float(y)) for x, y in waypoint_values]

        if waypoints:
            start = self._anchor_point(source_rect, waypoints[0])
            end = self._anchor_point(target_rect, waypoints[-1])
            points = [start] + waypoints + [end]
        else:
            start, end = self._default_edge_anchors(source_rect, target_rect)
            if abs(start.x() - end.x()) < 1.0:
                points = [start, end]
            else:
                mid_y = start.y() + (end.y() - start.y()) * 0.52
                points = [start, QPointF(start.x(), mid_y), QPointF(end.x(), mid_y), end]

        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)

        edge_color = QColor(self.ACTIVE_GREEN) if active else QColor(self.EDGE_GRAY)
        if not active:
            edge_color.setAlpha(150)
        pen = QPen(edge_color, 3.0 if active else 0.9)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        if not active:
            pen.setStyle(Qt.DashLine)

        item = QGraphicsPathItem(path)
        item.setPen(pen)
        item.setZValue(1)
        self._scene.addItem(item)
        self._draw_arrowhead(points[-2], points[-1], active)

        label = str(edge.get("condition_label", "") or edge.get("label", "") or "")
        if label:
            label_pos = self._edge_label_position(points)
            self._draw_edge_label(label, label_pos, active)
        return item

    def draw_summary_strip(self, data_characteristics: Dict[str, Any]) -> None:
        """Draw the live dataset diagnostics below the flowchart."""
        rect = self._scene.itemsBoundingRect()
        if rect.isEmpty():
            return
        width = max(760.0, rect.width() - 60.0)
        x = rect.left() + (rect.width() - width) / 2.0
        y = rect.bottom() + 36.0
        item = SummaryStripItem(QRectF(x, y, width, 54), self._summary_text(data_characteristics))
        self._scene.addItem(item)

    def export_png(self, output_path: str) -> bool:
        """Export the current vector scene to a PNG file."""
        if not output_path:
            return False
        image = self._render_scene_image()
        if image is None:
            return False
        return bool(image.save(output_path, "PNG"))

    def _render_scene_image(self) -> Optional[QImage]:
        """Render the current vector scene to a QImage."""
        rect = self._scene.itemsBoundingRect().adjusted(-30, -30, 30, 30)
        if rect.isEmpty():
            return None
        scale = 2.0
        image = QImage(
            max(1, int(rect.width() * scale)),
            max(1, int(rect.height() * scale)),
            QImage.Format_ARGB32,
        )
        image.fill(QColor("white"))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        self._scene.render(painter, QRectF(image.rect()), rect)
        painter.end()
        return image

    def copy_graph_to_clipboard(self) -> None:
        """Copy the current vector scene to the system clipboard as an image."""
        image = self._render_scene_image()
        if image is None:
            QMessageBox.warning(self, "Copy graph", "Could not copy the decision tree image.")
            return
        try:
            from qgis.PyQt.QtWidgets import QApplication
        except Exception:  # pragma: no cover
            from PyQt5.QtWidgets import QApplication
        QApplication.clipboard().setImage(image)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._auto_fit:
            self._fit_to_view()

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return
        self._zoom_by(1.18 if delta > 0 else 1.0 / 1.18)
        event.accept()

    # ------------------------------------------------------------------
    # Active path helpers
    # ------------------------------------------------------------------
    def _evaluate_univariate_path(
        self,
        n: int,
        sdi: Optional[float],
        clustered: bool,
        active_nodes: Set[str],
        active_edges: Set[str],
    ) -> None:
        active_edges.add("e_soil_n_lt_100")
        if n < 100:
            active_edges.add("e_n_lt_100_n_ge_50")
            active_nodes.add("n_ge_50")
            if n < 50:
                active_edges.update({"e_n_ge_50_m_idw", "e_n_ge_50_m_tps"})
                return
            active_edges.add("e_n_ge_50_spatial_50_99")
            active_nodes.add("spatial_50_99")
            if clustered:
                active_edges.add("e_spatial_50_99_sdi_50_99_cluster")
                active_nodes.add("sdi_50_99_cluster")
                if sdi is not None and sdi >= 80.0:
                    active_edges.add("e_sdi_50_99_cluster_m_ok")
                else:
                    active_edges.update({
                        "e_sdi_50_99_cluster_no_ok",
                        "e_sdi_50_99_cluster_m_tps",
                        "e_sdi_50_99_cluster_m_idw",
                    })
            else:
                active_edges.add("e_spatial_50_99_sdi_50_99_random")
                active_nodes.add("sdi_50_99_random")
                if sdi is not None and sdi < 60.0:
                    active_edges.add("e_sdi_50_99_random_m_tps")
                else:
                    active_edges.update({"e_sdi_50_99_random_no_tps", "e_sdi_50_99_random_m_ok"})
        else:
            active_edges.add("e_n_lt_100_spatial_100")
            active_nodes.add("spatial_100")
            if clustered:
                active_edges.add("e_spatial_100_sdi_100_low")
                active_nodes.add("sdi_100_low")
                if sdi is not None and sdi < 60.0:
                    active_edges.add("e_sdi_100_low_m_tps")
                else:
                    active_edges.add("e_sdi_100_low_sdi_100_high")
                    active_nodes.add("sdi_100_high")
                    if sdi is not None and sdi >= 80.0:
                        active_edges.update({"e_sdi_100_high_m_tps", "e_sdi_100_high_m_ok"})
                    else:
                        active_edges.update({
                            "e_sdi_100_high_no_tps",
                            "e_sdi_100_high_no_idw",
                            "e_sdi_100_high_no_ok",
                        })
            else:
                active_edges.update({"e_spatial_100_m_idw", "e_spatial_100_m_tps"})

    def _evaluate_full_path(
        self,
        n: int,
        sdi: Optional[float],
        clustered: bool,
        active_nodes: Set[str],
        active_edges: Set[str],
    ) -> None:
        if n < 100:
            active_edges.add("e_n_lt_100_n_ge_50")
            active_nodes.add("n_ge_50")
            if n < 50:
                active_edges.add("e_n_ge_50_spatial_lt_50")
                active_nodes.add("spatial_lt_50")
                if clustered:
                    active_edges.update({
                        "e_spatial_lt_50_m_rk",
                        "e_spatial_lt_50_m_idw",
                        "e_spatial_lt_50_m_tps",
                    })
                else:
                    active_edges.update({"e_spatial_lt_50_no_idw", "e_spatial_lt_50_no_tps"})
                return
            active_edges.add("e_n_ge_50_spatial_50_99")
            active_nodes.add("spatial_50_99")
            if clustered:
                active_edges.add("e_spatial_50_99_sdi_50_99_cluster")
                active_nodes.add("sdi_50_99_cluster")
                if sdi is not None and sdi >= 80.0:
                    active_edges.update({
                        "e_sdi_50_99_cluster_m_svm",
                        "e_sdi_50_99_cluster_m_rfe",
                        "e_sdi_50_99_cluster_m_rk",
                        "e_sdi_50_99_cluster_m_ok",
                    })
                else:
                    active_edges.update({
                        "e_sdi_50_99_cluster_no_ok",
                        "e_sdi_50_99_cluster_m_tps",
                        "e_sdi_50_99_cluster_m_idw",
                    })
            else:
                active_edges.add("e_spatial_50_99_sdi_50_99_random")
                active_nodes.add("sdi_50_99_random")
                if sdi is not None and sdi < 60.0:
                    active_edges.add("e_sdi_50_99_random_m_tps")
                else:
                    active_edges.add("e_sdi_50_99_random_m_svm")
        else:
            active_edges.add("e_n_lt_100_spatial_100")
            active_nodes.add("spatial_100")
            if clustered:
                active_edges.add("e_spatial_100_sdi_100_low")
                active_nodes.add("sdi_100_low")
                if sdi is not None and sdi < 60.0:
                    active_edges.add("e_sdi_100_low_sdi_100_40")
                    active_nodes.add("sdi_100_40")
                    if sdi is not None and sdi < 40.0:
                        active_edges.add("e_sdi_100_40_m_tps")
                    else:
                        active_edges.update({"e_sdi_100_40_no_tps", "e_sdi_100_40_m_svm"})
                else:
                    active_edges.add("e_sdi_100_low_sdi_100_high")
                    active_nodes.add("sdi_100_high")
                    if sdi is not None and sdi >= 80.0:
                        active_edges.update({
                            "e_sdi_100_high_m_svm",
                            "e_sdi_100_high_m_rk",
                            "e_sdi_100_high_m_rfe",
                            "e_sdi_100_high_m_ok",
                        })
                    else:
                        active_edges.update({
                            "e_sdi_100_high_m_tps",
                            "e_sdi_100_high_no_rk",
                            "e_sdi_100_high_no_rfe",
                            "e_sdi_100_high_m_idw",
                            "e_sdi_100_high_no_ok",
                        })
            else:
                active_edges.update({"e_spatial_100_m_tps", "e_spatial_100_m_svm"})

    def _activate_methods(
        self,
        methods: Set[str],
        ok_fit: str,
        active_nodes: Set[str],
        active_edges: Set[str],
    ) -> None:
        method_map = {
            "IDW": "m_idw",
            "TPS": "m_tps",
            "OK": "m_ok",
            "RK": "m_rk",
            "RFE": "m_rfe",
            "SVM": "m_svm",
        }
        for method, node_id in method_map.items():
            if method in methods and node_id in self._node_by_id:
                active_nodes.add(node_id)
                active_edges.add(f"e_{node_id}_validation")

        if "OK" in methods and "m_ok" in self._node_by_id:
            if ok_fit == "REML" and "m_reml" in self._node_by_id:
                active_nodes.add("m_reml")
                active_edges.update({"e_m_ok_m_reml", "e_m_reml_validation"})
            elif ok_fit == "MoM" and "m_mom" in self._node_by_id:
                active_nodes.add("m_mom")
                active_edges.update({"e_m_ok_m_mom", "e_m_mom_validation"})

    def _sync_terminal_edges_to_methods(self, active_nodes: Set[str], active_edges: Set[str]) -> None:
        """Keep terminal method edges aligned with the recommended method boxes."""
        edge_by_id = {edge["id"]: edge for edge in self._edges}
        for edge_id in list(active_edges):
            edge = edge_by_id.get(edge_id)
            if not edge:
                continue
            source = self._node_by_id.get(edge.get("source"))
            target = self._node_by_id.get(edge.get("target"))
            source_is_method = bool(source and str(source.get("id", "")).startswith("m_"))
            target_is_method = bool(target and str(target.get("id", "")).startswith("m_"))
            if target_is_method and target["id"] not in active_nodes:
                active_edges.discard(edge_id)
            elif source_is_method and source["id"] not in active_nodes:
                active_edges.discard(edge_id)

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _default_edge_anchors(source_rect: QRectF, target_rect: QRectF) -> Tuple[QPointF, QPointF]:
        source_center = source_rect.center()
        target_center = target_rect.center()
        if target_center.y() >= source_center.y():
            return (
                QPointF(source_center.x(), source_rect.bottom()),
                QPointF(target_center.x(), target_rect.top()),
            )
        return (
            QPointF(source_center.x(), source_rect.top()),
            QPointF(target_center.x(), target_rect.bottom()),
        )

    @staticmethod
    def _anchor_point(rect: QRectF, toward: QPointF) -> QPointF:
        center = rect.center()
        dx = toward.x() - center.x()
        dy = toward.y() - center.y()
        if abs(dx) > abs(dy) * 1.15:
            return QPointF(rect.right() if dx > 0 else rect.left(), center.y())
        return QPointF(center.x(), rect.bottom() if dy > 0 else rect.top())

    @staticmethod
    def _edge_label_position(points: Sequence[QPointF]) -> QPointF:
        if len(points) < 2:
            return QPointF(0, 0)
        start = points[0]
        next_point = points[1]
        if abs(start.x() - next_point.x()) < 1.0:
            y = start.y() + (22.0 if next_point.y() >= start.y() else -34.0)
            x = start.x() + 10.0
        else:
            x = (start.x() + next_point.x()) / 2.0 - 12.0
            y = start.y() - 22.0
        return QPointF(x, y)

    def _draw_arrowhead(self, start: QPointF, end: QPointF, active: bool) -> None:
        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        size = 7.5 if active else 6.0
        p1 = QPointF(
            end.x() - size * math.cos(angle - math.pi / 6.0),
            end.y() - size * math.sin(angle - math.pi / 6.0),
        )
        p2 = QPointF(
            end.x() - size * math.cos(angle + math.pi / 6.0),
            end.y() - size * math.sin(angle + math.pi / 6.0),
        )
        arrow = QGraphicsPolygonItem(QPolygonF([end, p1, p2]))
        color = QColor(self.ACTIVE_GREEN) if active else QColor(self.EDGE_GRAY)
        if not active:
            color.setAlpha(150)
        arrow.setBrush(QBrush(color))
        arrow.setPen(QPen(color, 1.0))
        arrow.setZValue(2)
        self._scene.addItem(arrow)

    def _draw_edge_label(self, label: str, pos: QPointF, active: bool) -> None:
        text = QGraphicsTextItem(label)
        label_color = QColor(self.ACTIVE_GREEN) if active else QColor("#94a3b8")
        if not active:
            label_color.setAlpha(170)
        text.setDefaultTextColor(label_color)
        font = QFont("Segoe UI", 8)
        font.setBold(active)
        text.setFont(font)
        rect = text.boundingRect()
        bg_rect = QRectF(pos.x() - 5, pos.y() + 2, rect.width() + 10, rect.height() - 2)
        bg_path = QPainterPath()
        bg_path.addRoundedRect(bg_rect, 5, 5)
        bg = QGraphicsPathItem(bg_path)
        bg_fill = QColor("#ffffff")
        bg_fill.setAlpha(235 if active else 205)
        bg_border = QColor("#d1d5db")
        bg_border.setAlpha(220 if active else 120)
        bg.setBrush(QBrush(bg_fill))
        bg.setPen(QPen(bg_border, 0.6))
        bg.setZValue(3)
        text.setPos(pos)
        text.setZValue(4)
        self._scene.addItem(bg)
        self._scene.addItem(text)

    def _summary_text(self, data: Dict[str, Any]) -> str:
        n = self._safe_int(data.get("n_samples"))
        p_value = self._safe_float(data.get("moran_pvalue"))
        sdi = self._safe_float(data.get("sdi_value"))
        pattern = str(data.get("spatial_pattern") or "Pending").strip() or "Pending"
        sdi_class = str(data.get("sdi_class") or "").strip()
        methods = sorted(self._normalise_methods(data.get("recommended_methods")))

        n_text = str(n) if n is not None else "Pending"
        p_text = f"{p_value:.3f}" if p_value is not None else "Pending"
        if sdi is None:
            sdi_text = "Pending"
        else:
            sdi_text = f"{sdi:.1f}%"
            if sdi_class:
                sdi_text = f"{sdi_text} {sdi_class}"
        methods_text = ", ".join(methods) if methods else "Pending"
        return (
            "Based on your data: "
            f"n = {n_text} | MI p = {p_text} | Pattern = {pattern} | "
            f"SDI = {sdi_text} | Recommended: {methods_text}"
        )

    def _fit_to_view(self) -> None:
        rect = self._scene.sceneRect()
        if rect.isEmpty() or self.viewport().width() <= 0:
            return
        self.resetTransform()
        self.fitInView(rect, Qt.KeepAspectRatio)

    def _zoom_by(self, factor: float) -> None:
        self.scale(float(factor), float(factor))
        self._auto_fit = False

    def zoom_in(self) -> None:
        self._zoom_by(1.25)

    def zoom_out(self) -> None:
        self._zoom_by(1.0 / 1.25)

    def _show_context_menu(self, pos) -> None:
        menu = QMenu(self)
        act_zoom_in = menu.addAction("Zoom in")
        act_zoom_out = menu.addAction("Zoom out")
        act_fit = menu.addAction("Fit to view")
        menu.addSeparator()
        act_zoom = menu.addAction("Open larger view")
        act_copy = menu.addAction("Copy graph")
        act_export = menu.addAction("Save graph")
        chosen = menu.exec_(self.mapToGlobal(pos))
        if chosen == act_zoom_in:
            self.zoom_in()
        elif chosen == act_zoom_out:
            self.zoom_out()
        elif chosen == act_fit:
            self._auto_fit = True
            self._fit_to_view()
        elif chosen == act_export:
            suggested = os.path.join(tempfile.gettempdir(), "framework_decision_tree.png")
            path, _ = QFileDialog.getSaveFileName(self, "Save graph", suggested, "PNG Images (*.png)")
            if path and not self.export_png(path):
                QMessageBox.warning(self, "Save graph", "Could not export the decision tree PNG.")
        elif chosen == act_copy:
            self.copy_graph_to_clipboard()
        elif chosen == act_zoom:
            self._open_larger_view()

    def _open_larger_view(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Framework Decision - larger view")
        layout = QVBoxLayout(dlg)
        view = FrameworkDecisionTreeView(dlg)
        layout.addWidget(view)
        view.update_tree(self._framework_type, self._data_characteristics)
        dlg.resize(1250, 780)
        dlg.exec_()

    # ------------------------------------------------------------------
    # Data helpers
    # ------------------------------------------------------------------
    def _inject_live_labels(self, nodes: Sequence[Node], data: Dict[str, Any]) -> List[Node]:
        """Keep node labels compact; live values are drawn in the summary strip."""
        labels = {
            "soil": "Soil samples",
            "n_lt_100": "n < 100?",
            "n_ge_50": "n >= 50?",
            "spatial_lt_50": "MI p < 0.05?",
            "spatial_50_99": "MI p < 0.05?",
            "spatial_100": "MI p < 0.05?",
            "sdi_50_99_cluster": "SDI >= 80%?",
            "sdi_50_99_random": "SDI < 60%?",
            "sdi_100_low": "SDI < 60%?",
            "sdi_100_40": "SDI < 40%?",
            "sdi_100_high": "SDI >= 80%?",
        }
        updated = []
        for node in nodes:
            copy = dict(node)
            if copy["id"] in labels:
                copy["label"] = labels[copy["id"]]
            updated.append(copy)
        return updated

    @staticmethod
    def _sdi_suffix(sdi: Optional[float], sdi_class: str) -> str:
        if sdi is None:
            return ""
        class_text = f" ({sdi_class})" if sdi_class else ""
        return f"\nSDI = {sdi:.1f}%{class_text}"

    @staticmethod
    def _node(node_id: str, label: str, node_type: str, x: float, y: float, width: float, height: float) -> Node:
        return {
            "id": node_id,
            "label": label,
            "type": node_type,
            "x": x,
            "y": y,
            "width": width,
            "height": height,
        }

    @staticmethod
    def _edge(
        source: str,
        target: str,
        condition_label: str = "",
        edge_id: Optional[str] = None,
        waypoints: Optional[Sequence[Tuple[float, float]]] = None,
    ) -> Edge:
        edge = {
            "id": edge_id or f"e_{source}_{target}",
            "source": source,
            "target": target,
            "condition_label": condition_label,
        }
        if waypoints:
            edge["waypoints"] = list(waypoints)
        return edge

    @staticmethod
    def _rect_for(node: Node) -> QRectF:
        return QRectF(float(node["x"]), float(node["y"]), float(node["width"]), float(node["height"]))

    @staticmethod
    def _normalise_framework_type(framework_type: str) -> str:
        text = str(framework_type or "").strip().lower()
        return "full" if text.startswith("full") else "univariate"

    @staticmethod
    def _safe_float(value: Any) -> Optional[float]:
        try:
            if value in (None, ""):
                return None
            out = float(value)
            return out if math.isfinite(out) else None
        except Exception:
            return None

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        try:
            if value in (None, ""):
                return None
            return int(value)
        except Exception:
            return None

    @staticmethod
    def _is_clustered(data: Dict[str, Any]) -> bool:
        p_value = FrameworkDecisionTreeView._safe_float(data.get("moran_pvalue"))
        if p_value is not None:
            return p_value < 0.05
        pattern = str(data.get("spatial_pattern") or "").strip().lower()
        return "cluster" in pattern or "spatial" in pattern or "structure" in pattern

    @staticmethod
    def _normalise_methods(value: Any) -> Set[str]:
        if value is None:
            return set()
        if isinstance(value, str):
            parts = value.replace(";", ",").replace("/", ",").split(",")
        else:
            try:
                parts = list(value)
            except Exception:
                parts = [value]
        return {str(part).strip().upper() for part in parts if str(part).strip()}

    @staticmethod
    def _normalise_fit_method(data: Dict[str, Any], n: Optional[int]) -> str:
        value = (
            data.get("variogram_fitting_method")
            or data.get("ok_fit_method")
            or data.get("fit_method")
            or ""
        )
        text = str(value).strip().upper()
        if "REML" in text:
            return "REML"
        if "MOM" in text or "MO M" in text:
            return "MoM"
        if n is not None:
            return "MoM" if n >= 100 else "REML"
        return ""

    @staticmethod
    def _coerce_active_path(active_path: Any) -> ActivePath:
        if isinstance(active_path, dict):
            return set(active_path.get("nodes", [])), set(active_path.get("edges", []))
        if isinstance(active_path, (tuple, list)) and len(active_path) == 2:
            return set(active_path[0]), set(active_path[1])
        return set(), set()
