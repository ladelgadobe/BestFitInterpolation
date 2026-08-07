# -*- coding: utf-8 -*-
"""Plugin metadata access shared by the About page and tests."""

from __future__ import annotations

import configparser
import os


def read_plugin_metadata(plugin_dir) -> dict:
    """Public plugin information from metadata.txt ([general] section)."""
    parser = configparser.ConfigParser(interpolation=None)
    metadata_path = os.path.join(plugin_dir, "metadata.txt")
    try:
        with open(metadata_path, "r", encoding="utf-8-sig") as metadata_file:
            parser.read_file(metadata_file)
        if parser.has_section("general"):
            return dict(parser.items("general"))
    except (OSError, configparser.Error):
        pass
    return {}
