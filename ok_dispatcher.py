# -*- coding: utf-8 -*-
"""
Dispatcher that selects between MoM and REML Ordinary Kriging controllers.
All code comments are in English.
"""

from __future__ import annotations

from typing import Optional

from .ok_base_utils import OKStrategySelector, count_valid_samples, same_layer
from .ok_mom_integration import OKMoMController
from .ok_reml_integration import OKREMLController


class OKDispatcherController:
    """Facade with the same public surface expected by BestFitInterpolator.

    The dispatcher keeps only one active controller instance at a time to avoid
    double-connecting signals and duplicated side effects.
    """

    def __init__(self, iface, dlg, plugin_dir=None, r_folder_path=None, strategy_selector: Optional[OKStrategySelector] = None):
        self.iface = iface
        self.dlg = dlg
        self.plugin_dir = plugin_dir
        self.r_folder_path = r_folder_path
        self.selector = strategy_selector or OKStrategySelector()

        self._active = None
        self._active_mode = None
        self._layer_id = None
        self._field_name = None
        self.run_ok_cv_function = None

    @property
    def strategy_name(self) -> str:
        return self._active_mode or "MoM"

    def _build_controller(self, mode: str):
        controller_cls = OKREMLController if mode == "REML" else OKMoMController
        ctrl = controller_cls(self.iface, self.dlg, plugin_dir=self.plugin_dir, r_folder_path=self.r_folder_path)
        ctrl.run_ok_cv_function = self.run_ok_cv_function
        return ctrl

    def _ensure_controller(self, layer, field_name: str):
        n = count_valid_samples(layer, field_name)
        decision = self.selector.choose(n)

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
