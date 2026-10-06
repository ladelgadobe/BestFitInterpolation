"""Numerical background jobs; QgsTask completion runs on the GUI thread."""
from qgis.core import QgsApplication, QgsTask
from .compat import is_alive, log_exception


def submit(owner, title, calculate, complete):
    jobs = owner.__dict__.setdefault("_bfi_jobs", set())
    def run(task):
        if task.isCanceled(): raise InterruptedError(title+" cancelled")
        result=calculate(task.isCanceled)
        if task.isCanceled(): raise InterruptedError(title+" cancelled")
        # A nonempty tuple also transports empty or false-valued results safely.
        return (result,)
    def finished(exception, result=None):
        jobs.discard(task)
        if not is_alive(owner):
            return
        if exception is not None and task.isCanceled():
            exception = InterruptedError(title + " cancelled")
        if exception is not None:
            if isinstance(exception, InterruptedError):
                complete(exception, None)
                return
            try:
                raise exception
            except Exception:
                log_exception(title)
        try:
            complete(exception,result[0] if result is not None else None)
        except Exception:
            log_exception(title+" completion handler failed")
    task = QgsTask.fromFunction(title, run, on_finished=finished)
    jobs.add(task)
    QgsApplication.taskManager().addTask(task)
    return task
