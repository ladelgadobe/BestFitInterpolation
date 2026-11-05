"""Actual workers, GUI callbacks, cancellation and hidden CPU probes."""
import time
import threading
from types import SimpleNamespace
import numpy as np
import pytest
from qgis.PyQt.QtCore import QTimer, QThread
from qgis.PyQt.QtWidgets import QApplication
from bestfitinterpolator.numerical_runtime import responsive_numerical
from bestfitinterpolator.windows_process import _QuietCPUProbe, hidden_process_options


def test_numerical_worker_keeps_gui_timer_and_callbacks_on_main_thread():
    app = QApplication.instance()
    beats, callbacks = [], []
    timer = QTimer(); timer.setInterval(5)
    timer.timeout.connect(lambda: beats.append(time.monotonic()))
    timer.start()

    @responsive_numerical
    def calculation(progress_fn=None):
        assert QThread.currentThread() != app.thread()
        for i in range(6):
            time.sleep(.02)
            progress_fn(i, 6)
        return np.arange(4)

    result = calculation(progress_fn=lambda *args: callbacks.append(QThread.currentThread() == app.thread()))
    timer.stop()
    np.testing.assert_array_equal(result, np.arange(4))
    assert len(beats) >= 5 and len(callbacks) == 6 and all(callbacks)
    assert not getattr(app, '_bfi_jobs', ())


def test_worker_exception_is_propagated_without_losing_gui_or_thread_limits():
    from threadpoolctl import threadpool_info
    before = [(p['filepath'], p['num_threads']) for p in threadpool_info()]

    @responsive_numerical
    def broken():
        raise ValueError('expected numeric failure')

    with pytest.raises(ValueError, match='expected numeric failure'):
        broken()
    @responsive_numerical
    def interrupted():
        time.sleep(.1)
    app = QApplication.instance()
    owner = app.activeModalWidget() or app.activeWindow() or app
    QTimer.singleShot(20, lambda: [task.cancel() for task in tuple(getattr(owner, '_bfi_jobs', ()))])
    with pytest.raises(InterruptedError, match='cancelled'):
        interrupted()
    assert [(p['filepath'], p['num_threads']) for p in threadpool_info()] == before


def test_gui_cancel_callback_stops_worker_and_releases_job():
    calls = []

    @responsive_numerical
    def calculation(progress_fn=None):
        for i in range(100):
            time.sleep(.005)
            progress_fn(i, 100)
        return 'must not apply'

    def cancel(*args):
        calls.append(args)
        raise KeyboardInterrupt('requested cancellation')

    with pytest.raises(KeyboardInterrupt, match='requested cancellation'):
        calculation(progress_fn=cancel)
    assert calls


def test_nested_numerical_calls_stay_on_the_same_worker():
    threads = []

    @responsive_numerical
    def inner():
        threads.append(threading.get_ident())
        return 7

    @responsive_numerical
    def outer():
        threads.append(threading.get_ident())
        return inner()

    assert outer() == 7 and threads[0] == threads[1]


def test_cpu_probe_hides_child_only_and_preserves_subprocess_module():
    import os, subprocess
    calls = []
    original = subprocess.run
    proxy = _QuietCPUProbe(SimpleNamespace(run=lambda *a, **k: calls.append(k)))
    proxy.run(['powershell.exe', '-NoProfile'], capture_output=True, creationflags=0)
    assert subprocess.run is original and calls[0]['capture_output']
    if os.name == 'nt':
        assert calls[0]['creationflags'] & subprocess.CREATE_NO_WINDOW
        assert calls[0]['startupinfo'].wShowWindow == subprocess.SW_HIDE
    else:
        assert hidden_process_options() == {}


def test_reml_cholesky_solve_matches_general_solve():
    from bestfitinterpolator.kriging_reml import _cholesky_solve
    rng = np.random.default_rng(41)
    matrix = rng.normal(size=(37, 37))
    covariance = matrix @ matrix.T + np.eye(37) * .2
    factor = np.linalg.cholesky(covariance)
    for rhs in (rng.normal(size=37), rng.normal(size=(37, 9))):
        np.testing.assert_allclose(_cholesky_solve(factor, rhs), np.linalg.solve(covariance, rhs), rtol=1e-11, atol=1e-11)


def test_framework_cancel_discards_partial_work_and_prevents_reentry():
    from qgis.PyQt.QtWidgets import QWidget
    from bestfitinterpolator.numerical_runtime import responsive_validation, check_validation_cancelled

    @responsive_numerical
    def calculation():
        time.sleep(.1)
        return 10

    class Controller:
        def __init__(self):
            self.dlg = QWidget()
            self.applied, self.runs = [], 0

        @responsive_validation
        def validate(self):
            self.runs += 1
            try:
                value = calculation()
            except KeyboardInterrupt:
                value = -1  # Legacy preparation controllers consume cancellation.
            check_validation_cancelled()
            self.applied.append(value)

    controller = Controller()
    QTimer.singleShot(10, controller.validate)
    QTimer.singleShot(30, lambda: [task.cancel() for task in tuple(getattr(controller.dlg, '_bfi_jobs', ()))])
    controller.validate()
    assert controller.runs == 1 and controller.applied == []
    assert not controller._bfi_validation_running and not controller.dlg._bfi_jobs
    controller.dlg.deleteLater()
