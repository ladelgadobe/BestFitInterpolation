"""Real task-manager transport, failure and cancellation tests."""
import time
from qgis.PyQt.QtWidgets import QWidget
from qgis.PyQt.QtCore import QCoreApplication
from bestfitinterpolator.async_jobs import submit


def wait(owner):
    deadline=time.monotonic()+10
    while owner._bfi_jobs:
        QCoreApplication.processEvents();time.sleep(.005)
        assert time.monotonic()<deadline


def test_empty_result_and_failed_task_complete_and_release_job():
    owner=QWidget();results=[]
    submit(owner,"Empty transport",lambda cancelled:[],lambda error,result:results.append((error,result)))
    wait(owner);assert results==[(None,[])]
    def fail(cancelled): raise ValueError("Expected failure")
    submit(owner,"Failure transport",fail,lambda error,result:results.append((error,result)))
    wait(owner);assert isinstance(results[-1][0],ValueError) and results[-1][1] is None
    owner.deleteLater()


def test_cancellation_never_applies_worker_result():
    owner=QWidget();results=[]
    def work(cancelled):
        while not cancelled(): time.sleep(.005)
        raise InterruptedError("Expected cancellation")
    task=submit(owner,"Cancel transport",work,lambda error,result:results.append((error,result)))
    QCoreApplication.processEvents();task.cancel();wait(owner)
    assert results and results[0][0] is not None and results[0][1] is None
    owner.deleteLater()
