"""Small feature-based adapters for QGIS 3.14+, Qt5 and Qt6."""
import logging
import inspect
from qgis.PyQt import QtCore, QtGui, QtWidgets

LOG = logging.getLogger("BestFitInterpolator")
try:
    from qgis.PyQt import sip
except ImportError:
    import sip

QAction = getattr(QtGui, "QAction", None) or QtWidgets.QAction


def enum_value(owner, scope, name):
    group = getattr(owner, scope, None)
    if group is not None and hasattr(group, name):
        return getattr(group, name)
    return getattr(owner, name)


def qt_exec(obj, *args):
    method = getattr(obj, "exec", None) or getattr(obj, "exec_", None)
    return method(*args)


def print_document(document, printer):
    method = getattr(document, "print", None) or document.print_
    return method(printer)


def is_alive(obj):
    if obj is None:
        return False
    try:
        return not sip.isdeleted(obj)
    except TypeError:
        return True


def log_exception(context):
    LOG.exception(context)
    try:
        from qgis.core import QgsMessageLog, Qgis
        QgsMessageLog.logMessage(context, "Best Fit Interpolator", enum_value(Qgis, "MessageLevel", "Warning"))
    except (ImportError, AttributeError):
        LOG.warning(context)


def geometry_type(name):
    from qgis import core
    modern = getattr(core.Qgis, "GeometryType", None)
    if modern is not None:
        return getattr(modern, name)
    return getattr(core.QgsWkbTypes, name + "Geometry")


def is_meter_unit(unit):
    from qgis import core
    modern = getattr(core.Qgis, "DistanceUnit", None)
    if modern is not None:
        return unit == modern.Meters
    return unit == core.QgsUnitTypes.DistanceMeters


def arrays_equal_with_nan(a, b):
    """Compare snapshots on NumPy releases predating array_equal(equal_nan=...)."""
    import numpy as np
    a, b = np.asarray(a), np.asarray(b)
    return a.shape == b.shape and bool(np.all((a == b) | (np.isnan(a) & np.isnan(b))))


def ml_dependency_requirements(python_version):
    """Choose installable dependency bounds for the QGIS Python interpreter."""
    version=tuple(python_version[:2])
    if version < (3,8):
        return ["joblib>=1.1,<1.3","threadpoolctl>=3.1,<3.2","scipy>=1.7,<1.8","scikit-learn>=1.0,<1.1"]
    if version < (3,9):
        return ["joblib>=1.3,<1.5","threadpoolctl>=3.1,<3.6","scipy>=1.9,<1.11","scikit-learn>=1.1,<1.4"]
    return ["joblib>=1.3","threadpoolctl>=3.1","scipy>=1.11","scikit-learn>=1.4"]


class ControllerConnections:
    """Own each Qt connection and disconnect only this controller's slots."""
    def _connect(self, signal, slot):
        connections = self.__dict__.setdefault("_connections", [])
        signature=inspect.signature(slot)
        variadic=any(p.kind==inspect.Parameter.VAR_POSITIONAL for p in signature.parameters.values())
        count=sum(p.kind in (inspect.Parameter.POSITIONAL_ONLY,inspect.Parameter.POSITIONAL_OR_KEYWORD) for p in signature.parameters.values())
        def guarded(*args):
            if self.is_dispatcher_active() and is_alive(self.dlg):
                try:
                    return slot(*(args if variadic else args[:count]))
                except Exception:
                    log_exception("Geostatistics signal handler failed: " + getattr(slot,"__name__","callback"))
        signal.connect(guarded)
        connections.append((signal, guarded))

    def dispose(self):
        self._dispatcher_active = False
        advanced=self.__dict__.get("_advanced_dialog")
        if is_alive(advanced):
            for task in tuple(getattr(advanced,"_bfi_jobs",())): task.cancel()
            advanced.close()
        timer = self.__dict__.get("_rebin_timer")
        if is_alive(timer):
            timer.stop()
        for signal, slot in self.__dict__.get("_connections", []):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                LOG.debug("Signal already disconnected during controller disposal")
        self._connections = []
        for name in ("_krig_vario_canvas", "_krig_map_canvas"):
            canvas = self.__dict__.get(name)
            if is_alive(canvas):
                canvas.setParent(None)
                canvas.deleteLater()
            setattr(self, name, None)

    def _schedule_rebin(self, *args):
        if not self.is_dispatcher_active() or self._programmatic_variogram_update:
            return
        self._exp_lags = self._exp_gamma = None
        self._model_validation_results = []
        self._semivariogram_stale = True
        if self._krig_vario_fig is not None:
            self._krig_vario_fig.clear()
            self._krig_vario_canvas.draw_idle()
        timer = self.__dict__.get("_rebin_timer")
        if timer is None:
            timer = QtCore.QTimer(self.dlg)
            timer.setSingleShot(True)
            self._connect(timer.timeout, self._recalculate_stale)
            self._rebin_timer = timer
        timer.start(250)

    def _recalculate_stale(self):
        try:
            self.calculate_and_plot_experimental(initial_load=False, reseed_params=False)
        except Exception:
            log_exception("Could not recalculate the semivariogram")

