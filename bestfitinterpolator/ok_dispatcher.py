# -*- coding: utf-8 -*-
"""
Dispatcher that selects between MoM and REML Ordinary Kriging controllers.
All code comments are in English.
"""

from __future__ import annotations

from typing import Optional

from .ok_base_utils import OKStrategySelector, count_valid_samples
from .ok_mom_integration import OKMoMController
from .ok_reml_integration import OKREMLController


class OKDispatcherController:
    """Facade with the same public surface expected by BestFitInterpolator.

    The dispatcher keeps only one active controller instance at a time to avoid
    double-connecting signals and duplicated side effects.
    """

    def __init__(self, iface, dlg, plugin_dir=None, r_folder_path=None, strategy_selector: Optional[OKStrategySelector] = None, plugin=None):
        self.iface = iface
        self.dlg = dlg
        self.plugin_dir = plugin_dir
        self.r_folder_path = r_folder_path
        self.plugin = plugin
        self.selector = strategy_selector or OKStrategySelector()

        self._active = None
        self._active_mode = None
        self._layer = None
        self._layer_id = None
        self._field_name = None
        self.run_ok_cv_function = None
        self._last_decision_warning = None
        self._wire_fit_method_selector()

    @property
    def strategy_name(self) -> str:
        return self._active_mode or "MoM"

    def _build_controller(self, mode: str):
        controller_cls = OKREMLController if mode == "REML" else OKMoMController
        ctrl = controller_cls(self.iface, self.dlg, plugin_dir=self.plugin_dir, r_folder_path=self.r_folder_path)
        ctrl.parent_plugin = self.plugin
        ctrl.run_ok_cv_function = self.run_ok_cv_function
        return ctrl

    def _wire_fit_method_selector(self):
        combo = getattr(self.dlg, "cmbOKFitMethod", None)
        if combo is None:
            return
        try:
            if hasattr(combo, "count") and combo.count() == 0:
                combo.addItems(["Automatic", "MoM", "REML"])
            if hasattr(combo, "setCurrentIndex") and combo.currentIndex() < 0:
                combo.setCurrentIndex(0)
            combo.currentIndexChanged.connect(self._on_fit_method_changed)
        except Exception:
            pass

    def _selected_fit_method(self) -> str:
        combo = getattr(self.dlg, "cmbOKFitMethod", None)
        try:
            if combo is not None and hasattr(combo, "currentText"):
                text = str(combo.currentText() or "").strip()
                if text:
                    return text
        except Exception:
            pass
        return "Automatic"

    def _on_fit_method_changed(self, *args):
        self._last_decision_warning = None
        if self._layer is None or not self._field_name:
            return
        try:
            self.set_points_layer_and_field(self._layer, self._field_name)
        except Exception:
            pass

    def _warn_if_reml_not_possible(self, decision):
        requested = self._selected_fit_method().strip().upper()
        if requested != "REML" or decision.mode == "REML":
            return
        key = (requested, decision.sample_count, decision.reason)
        if key == self._last_decision_warning:
            return
        self._last_decision_warning = key
        try:
            self.iface.messageBar().pushWarning(
                "Kriging",
                f"REML is not available for this dataset ({decision.reason}). MoM will be used instead.",
            )
        except Exception:
            pass

    def _ensure_controller(self, layer, field_name: str):
        n = count_valid_samples(layer, field_name)
        decision = self.selector.choose(n, self._selected_fit_method())
        self._warn_if_reml_not_possible(decision)

        target_mode = decision.mode
        target_layer_id = None
        try:
            target_layer_id = layer.id() if layer is not None else None
        except Exception:
            target_layer_id = id(layer) if layer is not None else None

        must_rebuild = (
            self._active is None
            or self._active_mode != target_mode
            or self._layer_id != target_layer_id
            or self._field_name != field_name
        )
        if must_rebuild:
            if self._active is not None and hasattr(self._active, "set_dispatcher_active"):
                try:
                    self._active.set_dispatcher_active(False)
                except Exception:
                    pass
            self._active = self._build_controller(target_mode)
            if hasattr(self._active, "set_dispatcher_active"):
                try:
                    self._active.set_dispatcher_active(True)
                except Exception:
                    pass
            self._active_mode = target_mode
            self._layer_id = target_layer_id
            self._field_name = field_name
        else:
            if self._active is not None and hasattr(self._active, "set_dispatcher_active"):
                try:
                    self._active.set_dispatcher_active(True)
                except Exception:
                    pass
        return self._active

    def set_points_layer_and_field(self, layer, field_name: str):
        self._layer = layer
        ctrl = self._ensure_controller(layer, field_name)
        ctrl.set_points_layer_and_field(layer, field_name)

    def clear_plots(self):
        if self._active is not None and hasattr(self._active, 'clear_plots'):
            self._active.clear_plots()

    def __getattr__(self, item):
        if item.startswith('__'):
            raise AttributeError(item)
        if self._active is None:
            raise AttributeError(item)
        return getattr(self._active, item)
