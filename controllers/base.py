# -*- coding: utf-8 -*-
"""TabController base + WorkerHandle (button-as-cancel).

WorkerHandle binds one live worker to its run button: while the worker runs
the button reads "Cancel" and clicking it cancels; teardown disconnects
first, then cancels, then waits bounded — so no slot ever fires into a dead
dialog (farm_tools mzones_ctrl idioms)."""

from __future__ import annotations

from ..logger import get_logger
from ..notify import Notifier

logger = get_logger(__name__)


class WorkerHandle:
    def __init__(self, button):
        self._button = button
        self._worker = None
        self._original_text = None

    @property
    def worker(self):
        return self._worker

    def is_running(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def launch(self, worker, *, on_result, on_failed, on_cancelled=None,
               on_dep_missing=None, on_progress=None, on_status=None):
        """Start ``worker``; the run button becomes Cancel until it ends."""
        if self.is_running():
            return False
        self._worker = worker
        if self._button is not None:
            self._original_text = self._button.text()
            self._button.setText("Cancel")
            try:
                self._button.clicked.disconnect()
            except TypeError:
                pass
            self._button.clicked.connect(self._on_cancel_clicked)

        worker.result_ready.connect(lambda result: self._finish(on_result, result))
        worker.failed.connect(lambda msg: self._finish(on_failed, msg))
        worker.cancelled.connect(lambda: self._finish(on_cancelled))
        worker.dep_missing.connect(lambda msg: self._finish(on_dep_missing or on_failed, msg))
        if on_progress is not None:
            worker.progress.connect(on_progress)
        if on_status is not None:
            worker.status.connect(on_status)
        worker.start()
        return True

    def _on_cancel_clicked(self):
        if self._worker is not None:
            self._worker.cancel()
            if self._button is not None:
                self._button.setText("Cancelling…")
                self._button.setEnabled(False)

    def _finish(self, callback, *args):
        worker = self._worker
        self._restore_button()
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        if callback is not None:
            try:
                callback(*args)
            except Exception:
                logger.exception("Worker completion callback failed")

    def _restore_button(self):
        if self._button is None:
            return
        try:
            self._button.clicked.disconnect()
        except TypeError:
            pass
        if self._original_text is not None:
            self._button.setText(self._original_text)
        self._button.setEnabled(True)

    def shutdown(self, wait_ms=10000):
        """Disconnect FIRST, then cancel, then bounded wait."""
        worker = self._worker
        self._worker = None
        if worker is None:
            return
        for sig in (worker.result_ready, worker.failed, worker.cancelled,
                    worker.dep_missing, worker.progress, worker.status):
            try:
                sig.disconnect()
            except TypeError:
                pass
        worker.cancel()
        if not worker.wait(wait_ms):
            logger.warning("Worker %s did not stop within %d ms", type(worker).__name__, wait_ms)
        worker.deleteLater()
        self._restore_button()


class TabController:
    """Base for per-tab controllers: (iface, dialog, session, notifier, plots).

    Subclasses implement wire() (connect THIS tab's signals only, bound
    methods so unwire can disconnect symmetrically)."""

    def __init__(self, iface, dialog, session, notifier: Notifier, plots):
        self.iface = iface
        self.dialog = dialog
        self.session = session
        self.notifier = notifier
        self.plots = plots
        self._handles = []
        self._connections = []       # (signal, slot) pairs made by wire()

    # -- wiring ---------------------------------------------------------------
    def wire(self):
        raise NotImplementedError

    def _connect(self, signal, slot):
        signal.connect(slot)
        self._connections.append((signal, slot))

    def unwire(self):
        for signal, slot in self._connections:
            try:
                signal.disconnect(slot)
            except TypeError:
                pass
        self._connections = []

    def shutdown(self):
        for handle in self._handles:
            handle.shutdown()
        self._handles = []
        self.unwire()

    # -- workers ---------------------------------------------------------------
    def handle_for(self, button) -> WorkerHandle:
        handle = WorkerHandle(button)
        self._handles.append(handle)
        return handle

    # -- shared plumbing --------------------------------------------------------
    def _wire_figure_buttons(self, panel, name):
        """Connect a FigurePanel's Copy/Save buttons to PlotService."""
        if panel.btn_copy is not None:
            self._connect(panel.btn_copy.clicked,
                          lambda _=False: self.plots.copy_to_clipboard(panel.figure))
        if panel.btn_save is not None:
            self._connect(panel.btn_save.clicked,
                          lambda _=False: self.plots.save_dialog(panel.figure, self.dialog, name))

    def notify_error(self, title, msg):
        logger.error("%s: %s", title, msg)
        self.notifier.critical(self.dialog, title, msg)

    def notify_warning(self, title, msg):
        logger.warning("%s: %s", title, msg)
        self.notifier.warning(self.dialog, title, msg)

    def notify_status(self, title, msg, level=None):
        self.notifier.status(title, msg, level=Notifier.INFO if level is None else level)
