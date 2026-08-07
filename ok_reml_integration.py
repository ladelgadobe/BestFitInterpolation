# -*- coding: utf-8 -*-
"""
REML-focused integration for the Ordinary Kriging tab.
All code comments are in English.
"""

from __future__ import annotations

from .ok_r_integration_reml import OKTabController as _REMLBaseController


class OKREMLController(_REMLBaseController):
    """Thin wrapper around the REML-specific controller."""

    strategy_name = "REML"

    def __init__(self, iface, dlg, plugin_dir=None, r_folder_path=None):
        super().__init__(iface, dlg, plugin_dir=plugin_dir, r_folder_path=r_folder_path)
        self._ok_fit_method = "REML"
        self._use_reml = True
