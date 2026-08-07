# -*- coding: utf-8 -*-
"""BaseWorker — the uniform QThread contract every heavy operation uses.

Template method: subclasses implement _work(progress, should_stop) and the
except ladder here maps typed exceptions onto signals. The result signal is
deliberately named ``result_ready`` (NOT ``finished``) so it never shadows
QThread.finished.
"""

from __future__ import annotations

from qgis.PyQt.QtCore import QThread, pyqtSignal

from ..core.exceptions import (
    BFIError,
    DependencyMissing,
    InsufficientSamples,
    InvalidDataError,
    OperationCancelled,
)
from ..logger import get_logger

logger = get_logger(__name__)


class BaseWorker(QThread):
    progress = pyqtSignal(int, int)      # done, total
    status = pyqtSignal(str)             # phase label ("Fitting variogram…")
    result_ready = pyqtSignal(object)    # typed result dataclass
    cancelled = pyqtSignal()
    dep_missing = pyqtSignal(str)        # DependencyMissing.user_message()
    failed = pyqtSignal(str)             # user-facing error text

    def cancel(self):
        self.requestInterruption()

    def run(self):
        try:
            result = self._work(
                progress=self.progress.emit,
                status=self.status.emit,
                should_stop=self.isInterruptionRequested,
            )
            if self.isInterruptionRequested():
                self._cleanup_partial()
                self.cancelled.emit()
                return
            self.result_ready.emit(result)
        except OperationCancelled:
            self._cleanup_partial()
            self.cancelled.emit()
        except DependencyMissing as exc:
            self.dep_missing.emit(exc.user_message())
        except (InsufficientSamples, InvalidDataError) as exc:
            self.failed.emit(str(exc))
        except BFIError as exc:
            logger.exception("Worker %s failed", type(self).__name__)
            self.failed.emit(str(exc))
        except Exception as exc:
            logger.exception("Worker %s failed unexpectedly", type(self).__name__)
            self.failed.emit(f"{type(exc).__name__}: {exc}")

    def _work(self, *, progress, status, should_stop):
        raise NotImplementedError

    def _cleanup_partial(self):
        """Hook for subclasses to remove partial outputs after a cancel."""
