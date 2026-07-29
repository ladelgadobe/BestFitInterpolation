from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_visible_sources_have_no_mojibake_markers():
    markers = tuple(chr(codepoint) for codepoint in (0x00C3, 0x00C2, 0x00CE, 0x00CF, 0x00E2, 0xFFFD))
    offenders = []

    for pattern in ("*.py", "*.ui"):
        for path in ROOT.rglob(pattern):
            relative = path.relative_to(ROOT)
            if any(part in {"_deps", "help", "__pycache__"} for part in relative.parts):
                continue
            if path.name in {"resources.py", "resources_rc.py"}:
                continue
            text = path.read_text(encoding="utf-8-sig")
            found = sorted({marker for marker in markers if marker in text})
            if found:
                offenders.append(f"{relative}: {found}")

    assert not offenders, "Mojibake found:\n" + "\n".join(offenders)


def test_tps_title_and_graph_menu_are_encoding_safe():
    source = (ROOT / "BestFitInterpolator.py").read_text(encoding="utf-8-sig")

    assert 'menu.addAction("Save graph...")' in source
    assert 'r"$\\epsilon=0.0001$"' in source
