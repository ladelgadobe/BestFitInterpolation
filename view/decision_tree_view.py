# -*- coding: utf-8 -*-
"""DecisionTreeView — paints the framework's method-recommendation decision
path as a vertical chain of question boxes ending in the recommendation.

Pure presentation: the controller computes the analysis and calls
``set_state``; this widget only maps state values to Yes/No/— badges and
draws them. Colors come from ``self.palette()`` so the widget follows the
active QGIS theme."""

from __future__ import annotations

from qgis.PyQt.QtCore import QPointF, QRectF, QSize, Qt
from qgis.PyQt.QtGui import QPainter, QPen, QPolygonF
from qgis.PyQt.QtWidgets import QSizePolicy, QWidget

from .common import tr

_MARGIN = 12
_BOX_HEIGHT = 48
_GAP = 26
_FINAL_HEIGHT = 58
_BADGE_WIDTH = 48
_BADGE_HEIGHT = 24
_QUESTION_COUNT = 4


class DecisionTreeView(QWidget):
    """Vertical decision path: four framework questions + recommendation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state = {}
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    # ------------------------------------------------------------------ API
    def set_state(self, state):
        """state keys: n, moran_pattern, sdi_pct, has_covariates,
        recommended_label. Missing/None keys render as "—"."""
        self._state = dict(state or {})
        self.update()

    # ------------------------------------------------------------- sizing
    def minimumSizeHint(self):
        height = (2 * _MARGIN
                  + _QUESTION_COUNT * (_BOX_HEIGHT + _GAP)
                  + _FINAL_HEIGHT)
        return QSize(340, height)

    def sizeHint(self):
        return QSize(480, self.minimumSizeHint().height())

    # ------------------------------------------------------------ answers
    def _rows(self):
        """[(question, answer)] with answer in {"Yes", "No", "—"}."""
        state = self._state

        def yes_no(condition):
            return tr("Yes") if condition else tr("No")

        n = state.get("n")
        n_answer = "—" if n is None else yes_no(int(n) >= 30)

        pattern = state.get("moran_pattern")
        if pattern is None:
            moran_answer = "—"
        else:
            moran_answer = yes_no(str(pattern) in ("Clustered", "Dispersed"))

        sdi = state.get("sdi_pct")
        sdi_answer = "—" if sdi is None else yes_no(float(sdi) >= 40.0)

        covariates = state.get("has_covariates")
        cov_answer = "—" if covariates is None else yes_no(bool(covariates))

        return [
            (tr("n ≥ 30?"), n_answer),
            (tr("Spatial structure (Moran's I significant)?"), moran_answer),
            (tr("Strong spatial dependence (SDI ≥ 40%)?"), sdi_answer),
            (tr("Covariates available?"), cov_answer),
        ]

    # ------------------------------------------------------------ painting
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        palette = self.palette()

        box_width = min(max(self.width() - 2 * _MARGIN, 220), 540)
        x = (self.width() - box_width) / 2.0
        y = float(_MARGIN)

        for question, answer in self._rows():
            rect = QRectF(x, y, box_width, _BOX_HEIGHT)
            answered = answer != "—"
            self._draw_question_box(painter, palette, rect, question,
                                    answer, answered)
            self._draw_arrow(painter, palette,
                             rect.center().x(), rect.bottom() + 2,
                             rect.bottom() + _GAP - 2, answered)
            y += _BOX_HEIGHT + _GAP

        self._draw_final_box(painter, palette,
                             QRectF(x, y, box_width, _FINAL_HEIGHT))
        painter.end()

    def _draw_question_box(self, painter, palette, rect, question, answer,
                           answered):
        border = palette.highlight().color() if answered else palette.mid().color()
        painter.setPen(QPen(border, 2.0 if answered else 1.2))
        painter.setBrush(palette.alternateBase() if answered else palette.base())
        painter.drawRoundedRect(rect, 8, 8)

        font = painter.font()
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QPen(palette.windowText().color()))
        text_rect = rect.adjusted(10, 4, -(_BADGE_WIDTH + 18), -4)
        painter.drawText(text_rect,
                         Qt.AlignVCenter | Qt.AlignLeft | Qt.TextWordWrap,
                         question)

        badge = QRectF(rect.right() - _BADGE_WIDTH - 10,
                       rect.top() + (rect.height() - _BADGE_HEIGHT) / 2.0,
                       _BADGE_WIDTH, _BADGE_HEIGHT)
        painter.setBrush(palette.highlight() if answered else palette.window())
        painter.setPen(QPen(border, 1.0))
        painter.drawRoundedRect(badge, _BADGE_HEIGHT / 2.0, _BADGE_HEIGHT / 2.0)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(palette.highlightedText().color() if answered
                            else palette.windowText().color()))
        painter.drawText(badge, Qt.AlignCenter, answer)
        font.setBold(False)
        painter.setFont(font)

    def _draw_arrow(self, painter, palette, x, y_top, y_bottom, active):
        color = palette.highlight().color() if active else palette.mid().color()
        painter.setPen(QPen(color, 2.0 if active else 1.2))
        head = 6.0
        painter.drawLine(QPointF(x, y_top), QPointF(x, y_bottom - head))
        painter.setBrush(color)
        painter.drawPolygon(QPolygonF([
            QPointF(x, y_bottom),
            QPointF(x - head / 1.5, y_bottom - head),
            QPointF(x + head / 1.5, y_bottom - head),
        ]))

    def _draw_final_box(self, painter, palette, rect):
        label = self._state.get("recommended_label")
        font = painter.font()
        if label:
            painter.setBrush(palette.highlight())
            painter.setPen(QPen(palette.highlight().color().darker(130), 2.0))
            text_color = palette.highlightedText().color()
            text = tr("Recommended:") + " " + str(label)
        else:
            painter.setBrush(palette.base())
            painter.setPen(QPen(palette.mid().color(), 1.2))
            text_color = palette.windowText().color()
            text = tr("Run the analysis to see a recommendation.")
        painter.drawRoundedRect(rect, 8, 8)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(text_color))
        painter.drawText(rect.adjusted(10, 4, -10, -4),
                         Qt.AlignCenter | Qt.TextWordWrap, text)
        font.setBold(False)
        painter.setFont(font)
