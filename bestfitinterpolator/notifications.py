# -*- coding: utf-8 -*-
"""Central notification routing for the plugin."""

from qgis.PyQt.QtWidgets import QApplication, QMessageBox


class PopupMessageBar:
    """Use popups for alerts and the native QGIS bar for information."""

    def __init__(self, iface):
        self._iface = iface

    def _parent(self):
        try:
            app = QApplication.instance()
            if app is not None:
                parent = app.activeModalWidget() or app.activeWindow()
                if parent is not None:
                    return parent
        # If no active widget exists, fall back to the QGIS main window.
        except Exception:  # nosec B110
            pass
        try:
            return self._iface.mainWindow()
        except Exception:
            return None

    def _native_message_bar(self):
        try:
            return self._iface.messageBar()
        except Exception:
            return None

    def _push_native(self, method_name, title, message, duration, kwargs, level=None):
        """Forward an informational message without opening a modal window."""
        message_bar = self._native_message_bar()
        if message_bar is None:
            return None

        method = getattr(message_bar, method_name, None)
        if method is None and method_name == "pushSuccess":
            method = getattr(message_bar, "pushMessage", None)
        if method is None:
            return None

        call_kwargs = dict(kwargs)
        if duration is not None:
            call_kwargs["duration"] = duration
        if level is not None:
            call_kwargs["level"] = level
        args = (title,) if message in (None, "") else (title, message)
        return method(*args, **call_kwargs)

    @staticmethod
    def _title_and_text(title, message):
        title = str(title or "").strip()
        if message in (None, ""):
            return "Best Fit Interpolator", title or "Operation completed."
        return title or "Best Fit Interpolator", str(message)

    def pushMessage(self, title, message=None, level=0, duration=None, **kwargs):
        """Display alerts as popups and informational messages in the QGIS bar."""
        window_title, text = self._title_and_text(title, message)
        try:
            numeric_level = int(level)
        except Exception:
            numeric_level = 0

        title_token = window_title.strip().lower()
        if numeric_level >= 3 or title_token in {"error", "critical", "fatal error"}:
            return QMessageBox.critical(self._parent(), window_title, text)
        if numeric_level >= 1 or title_token in {"warning", "alert"}:
            return QMessageBox.warning(self._parent(), window_title, text)
        return self._push_native(
            "pushMessage",
            title,
            message,
            duration,
            kwargs,
            level=level,
        )

    def pushWarning(self, title, message=None, duration=None, **kwargs):
        del duration, kwargs
        window_title, text = self._title_and_text(title, message)
        return QMessageBox.warning(self._parent(), window_title, text)

    def pushCritical(self, title, message=None, duration=None, **kwargs):
        del duration, kwargs
        window_title, text = self._title_and_text(title, message)
        return QMessageBox.critical(self._parent(), window_title, text)

    def pushSuccess(self, title, message=None, duration=None, **kwargs):
        return self._push_native(
            "pushSuccess",
            title,
            message,
            duration,
            kwargs,
        )


class PopupIfaceProxy:
    """Delegate QGIS interface calls while replacing only its message bar."""

    def __init__(self, iface):
        self._wrapped_iface = iface
        self._popup_message_bar = PopupMessageBar(iface)

    def messageBar(self):
        return self._popup_message_bar

    def __getattr__(self, name):
        return getattr(self._wrapped_iface, name)
