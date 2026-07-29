"""Release contract for the QGIS plugin version 1.1 package."""

import configparser
from pathlib import Path


PLUGIN_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_DIR = PLUGIN_DIR.parent


def _metadata():
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(PLUGIN_DIR / "metadata.txt", encoding="utf-8-sig")
    return parser["general"]


def test_release_version_and_changelog_are_consistent():
    metadata = _metadata()
    assert metadata["version"] == "1.1"
    assert metadata["changelog"].startswith("Version 1.1:")


def test_release_documentation_has_no_legacy_r_squared_encoding():
    legacy_r_squared = "R" + chr(194) + "²"
    for path in (
        REPOSITORY_DIR / "README.md",
        PLUGIN_DIR / "README.md",
        PLUGIN_DIR / "README.txt",
        PLUGIN_DIR / "README.html",
    ):
        text = path.read_text(encoding="utf-8-sig")
        assert legacy_r_squared not in text


def test_qgis_required_files_and_public_links_are_present():
    metadata = _metadata()
    for name in ("__init__.py", "metadata.txt", "LICENSE", "README.md", "icon.png"):
        assert (PLUGIN_DIR / name).is_file()
    for key in ("homepage", "repository", "tracker"):
        assert metadata[key].startswith("https://")
