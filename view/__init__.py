# -*- coding: utf-8 -*-
"""Code-built PyQt pages.

Discipline (farm_tools view/ rules): ``setup_<x>_page(dialog, page)`` are pure
widget-builder functions — interactive widgets are attached as
``dialog.<prefix>_*`` attributes, defaults come from the legacy .ui inventory
(dev/ui_inventory.md), and no business logic or signal wiring lives here
(controllers wire everything).
"""
