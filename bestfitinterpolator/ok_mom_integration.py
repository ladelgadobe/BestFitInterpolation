# -*- coding: utf-8 -*-
"""
MoM-only integration for the Ordinary Kriging tab.
All code comments are in English.
"""

from __future__ import annotations

from .ok_r_integration_MoM import OKTabController as _MoMBaseController


class OKMoMController(_MoMBaseController):
    """Thin wrapper around the stable MoM controller."""

    strategy_name = "MoM"

    def __init__(self, iface, dlg, plugin_dir=None, r_folder_path=None):
        super().__init__(iface, dlg, plugin_dir=plugin_dir, r_folder_path=r_folder_path)
        self._ok_fit_method = "MoM"
        self._use_reml = False
        self._reml_fitted = False
