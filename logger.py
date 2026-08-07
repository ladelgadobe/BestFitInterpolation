# -*- coding: utf-8 -*-
"""Package logging with a QgsMessageLog bridge.

Three notification tiers across the plugin:
  * ``logging.getLogger(__name__)`` — diagnostics; DEBUG stays in the Python
    console, WARNING+ is forwarded to the QGIS "Log Messages" panel by the
    handler installed here.
  * ``QgsMessageLog`` — reached through this bridge, never called directly.
  * ``notify.Notifier`` — user-facing popups / message bar.
"""
import logging

LOG_TAG = "Best Fit Interpolator"
_ROOT_NAME = "bestfitinterpolator"

_configured = False


class _QgsLogHandler(logging.Handler):
    """Forward WARNING+ records to the QGIS message log panel."""

    def emit(self, record):
        try:
            from qgis.core import Qgis, QgsMessageLog

            level = Qgis.Warning if record.levelno < logging.ERROR else Qgis.Critical
            QgsMessageLog.logMessage(self.format(record), LOG_TAG, level)
        except Exception:  # pragma: no cover - never let logging raise
            pass


def setup():
    """Install the QGIS bridge once. Safe to call repeatedly. Never hijacks
    the root logger — only the plugin's own namespace is configured."""
    global _configured
    if _configured:
        return
    root = logging.getLogger(_ROOT_NAME)
    root.setLevel(logging.DEBUG)
    handler = _QgsLogHandler(level=logging.WARNING)
    handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
    root.addHandler(handler)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Logger namespaced under the plugin root (``name`` is ``__name__``)."""
    if name.startswith(_ROOT_NAME):
        return logging.getLogger(name)
    return logging.getLogger(f"{_ROOT_NAME}.{name}")
