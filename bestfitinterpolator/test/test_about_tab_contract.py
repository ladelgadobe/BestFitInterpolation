"""Contract tests for the metadata-driven About tab."""

import ast
import configparser
from pathlib import Path


PLUGIN_DIR = Path(__file__).resolve().parents[1]
MAIN_SOURCE = PLUGIN_DIR / "BestFitInterpolator.py"
METADATA_PATH = PLUGIN_DIR / "metadata.txt"


def _class_node(tree, class_name):
    return next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == class_name
    )


def _method_node(class_node, method_name):
    return next(
        node
        for node in class_node.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == method_name
    )


def test_about_tab_is_built_from_plugin_metadata():
    source = MAIN_SOURCE.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    dialog = _class_node(tree, "BestFitInterpolatorDialog")
    _method_node(dialog, "_add_about_tab")
    method_source = source[
        source.index("    def _add_about_tab"):
        source.index("    def _open_external_url")
    ]

    assert 'metadata.get("version"' in method_source
    assert 'metadata.get("author"' in method_source
    assert 'metadata.get("email"' in method_source
    assert 'metadata.get("linkedin_laura"' in method_source
    assert 'metadata.get("linkedin_lucas"' in method_source
    assert 'metadata.get("repository"' in method_source
    assert 'metadata.get("tracker"' in method_source
    assert 'metadata.get("manual"' in method_source
    assert 'metadata.get("article"' in method_source
    assert '"article_title"' in method_source
    assert '"article_citation"' in method_source
    assert 'tabs.addTab(about_tab, "About")' in method_source
    assert "root_layout.setAlignment(Qt.AlignTop)" in method_source
    assert "heading_layout.addStretch()" not in method_source
    assert (
        "If you use this plugin in academic work, please cite the "
        in method_source
    )
    assert '"Message Laura"' not in method_source
    assert '"Message Lucas"' not in method_source
    assert '"Laura Delgado Bejarano"' in method_source
    assert '"Lucas Rios do Amaral"' in method_source
    assert "1.0.2" not in method_source


def test_about_links_open_externally_and_manual_is_configured():
    source = MAIN_SOURCE.read_text(encoding="utf-8-sig")
    assert "QDesktopServices.openUrl(QUrl(url))" in source

    parser = configparser.ConfigParser(interpolation=None)
    parser.read(METADATA_PATH, encoding="utf-8-sig")
    general = parser["general"]

    assert general["manual"] == (
        "https://github.com/ladelgadobe/BestFitInterpolation/"
        "blob/main/BestFitInterpolation_PluginV1.1.pdf"
    )
    assert general["repository"].startswith("https://github.com/")
    assert general["tracker"].endswith("/issues")
    assert general["article"] == (
        "https://link.springer.com/article/10.1007/s11119-025-10311-8"
    )
    assert general["article_title"]
    assert general["article_citation"]
    for author in (
        "Laura Delgado Bejarano",
        "Agda Loureiro Gonçalves Oliveira",
        "João Vitor Fiolo Pozzuto",
        "Dario Castañeda Sánchez",
        "Lucas Rios do Amaral",
    ):
        assert author in general["article_citation"]
    assert general["linkedin_laura"] == (
        "https://www.linkedin.com/in/laura-delgado-bejarano-09b6681a2/"
    )
    assert general["linkedin_lucas"] == (
        "https://www.linkedin.com/in/lucas-rios-do-amaral-bb302449/"
    )
