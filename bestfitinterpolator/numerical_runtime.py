"""Keep numerical kernels off the GUI thread without changing their results.

Controllers retain their synchronous API and update widgets on the GUI thread.
Only array calculations run in QgsTask workers. The local Qt event loop keeps
painting and cancellation alive while the controller waits for its result.
"""
from contextlib import contextmanager
from functools import wraps
import inspect
import threading

_NUMERICAL_LOCK = threading.RLock()
_SESSION = None


def responsive_validation(function):
    """One cancellable Framework run; reject re-entry during nested Qt events."""
    @wraps(function)
    def run(controller, *args, **kwargs):
        global _SESSION
        if getattr(controller, '_bfi_validation_running', False):
            return
        from qgis.PyQt.QtWidgets import QProgressDialog
        from qgis.PyQt.QtCore import Qt
        from .compat import enum_value
        from .localization import _new, _ui
        controller._bfi_validation_running = True
        progress = _new(QProgressDialog, 'Validating interpolation methods', 'Cancel', 0, 0, controller.dlg)
        _ui(progress, 'setWindowTitle', 'Framework validation')
        progress.setWindowModality(enum_value(Qt, 'WindowModality', 'WindowModal'))
        progress.setMinimumDuration(0)
        previous = _SESSION
        session = dict(owner=controller.dlg, progress=progress, cancelled=False)
        _SESSION = session

        def cancel():
            session['cancelled'] = True
            for task in tuple(getattr(controller.dlg, '_bfi_jobs', ())):
                task.cancel()

        progress.canceled.connect(cancel)
        progress.show()
        try:
            return function(controller, *args, **kwargs)
        except (KeyboardInterrupt, InterruptedError):
            return
        finally:
            _SESSION = previous
            controller._bfi_validation_running = False
            progress.close()
            progress.deleteLater()
    return run


def check_validation_cancelled():
    if _SESSION is not None and _SESSION['cancelled']:
        raise KeyboardInterrupt('Validation cancelled')


@contextmanager
def numerical_limits():
    # threadpoolctl changes process-wide native limits. Serialize our numerical
    # scopes so concurrent plugin tasks cannot restore them in the wrong order.
    with _NUMERICAL_LOCK:
        try:
            from threadpoolctl import threadpool_limits
        except ImportError:
            yield
        else:
            with threadpool_limits(limits=1):
                yield


def responsive_numerical(function):
    signature = inspect.signature(function)

    @wraps(function)
    def call(*args, **kwargs):
        try:
            from qgis.core import QgsApplication, QgsTask
            from qgis.PyQt.QtCore import QObject, QThread, QEventLoop, pyqtSignal, pyqtSlot
            from qgis.PyQt.QtWidgets import QApplication
        except ImportError:
            with numerical_limits():
                return function(*args, **kwargs)
        app = QApplication.instance()
        if app is None or not hasattr(app, 'thread') or QThread.currentThread() != app.thread():
            with numerical_limits():
                return function(*args, **kwargs)

        check_validation_cancelled()
        session = _SESSION

        bound = signature.bind(*args, **kwargs)
        callback = bound.arguments.get('progress_fn')
        callback_error = []
        try:
            callback_signature = inspect.signature(callback) if callback is not None else None
        except (ValueError, TypeError):
            callback_signature = None

        class ProgressBridge(QObject):
            progress = pyqtSignal(object)

            @pyqtSlot(object)
            def deliver(self, values):
                if outcome:
                    return
                try:
                    callback(*values)
                except BaseException as error:
                    callback_error.append(error)
                    task.cancel()

        bridge = ProgressBridge()
        bridge.progress.connect(bridge.deliver)
        loop = QEventLoop()
        outcome = []
        owner = session['owner'] if session else (app.activeModalWidget() or app.activeWindow() or app)
        if session:
            labels = dict(optimize_idw='Optimizing IDW parameters',
                          tps_interpolation='Validating thin plate spline',
                          ordinary_kriging_interpolation='Validating kriging',
                          fit_variogram_reml='Fitting REML semivariogram',
                          kfold_cv_ok_reml='Validating REML kriging',
                          _tune_random_forest='Fitting Random Forest', _tune_svm='Fitting SVM')
            from .localization import _ui
            _ui(session['progress'], 'setLabelText', labels.get(function.__name__, 'Validating interpolation methods'))
        jobs = owner.__dict__.setdefault('_bfi_jobs', set())

        def progress(*values):
            if task.isCanceled():
                raise InterruptedError('Calculation cancelled')
            # Existing tuners support both (done, total) and
            # (done, total, label). Validate before queuing, so their fallback
            # still sees a signature mismatch on the calculating thread.
            if callback_signature is not None:
                callback_signature.bind(*values)
            bridge.progress.emit(values)

        if callback is not None:
            bound.arguments['progress_fn'] = progress
        if 'cancelled' in signature.parameters and 'cancelled' not in bound.arguments:
            bound.arguments['cancelled'] = lambda: task.isCanceled()

        def calculate(task):
            try:
                with numerical_limits():
                    if task.isCanceled():
                        raise InterruptedError('Calculation cancelled')
                    return (None, function(*bound.args, **bound.kwargs))
            except BaseException as error:
                # QgsTask catches Exception, whereas existing progress callbacks
                # also use KeyboardInterrupt to request cancellation.
                return (error, None)

        def finished(exception, result=None):
            jobs.discard(task)
            outcome.append((exception, result, task.isCanceled()))
            loop.quit()

        task = QgsTask.fromFunction(function.__name__.replace('_', ' ').strip(),
                                    calculate, on_finished=finished)
        jobs.add(task)
        QgsApplication.taskManager().addTask(task)
        (getattr(loop, 'exec', None) or loop.exec_)()
        if callback_error:
            if session and isinstance(callback_error[0], (KeyboardInterrupt, InterruptedError)):
                session['cancelled'] = True
            raise callback_error[0]
        check_validation_cancelled()
        exception, result, was_cancelled = outcome[0]
        if was_cancelled:
            if session:
                session['cancelled'] = True
                raise KeyboardInterrupt('Calculation cancelled')
            raise InterruptedError('Calculation cancelled')
        error, value = result if result is not None else (exception, None)
        if exception is not None:
            raise exception
        if error is not None:
            raise error
        return value

    return call
