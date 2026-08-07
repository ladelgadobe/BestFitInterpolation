# -*- coding: utf-8 -*-
"""One-off reference extractor for the legacy Qt Designer .ui file.

Walks BestFitInterpolator_dialog_base.ui and prints every widget with its
class, object name, and behavioral properties (labels, ranges, defaults,
tooltips). The output (dev/ui_inventory.md) is the contract the code-built
view/ pages must reproduce. Not shipped in the plugin zip.

Usage:  python dev/ui_inventory.py > dev/ui_inventory.md
"""
import pathlib
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
UI_FILE = ROOT / "BestFitInterpolator_dialog_base.ui"

KEEP = (
    "text", "title", "toolTip", "minimum", "maximum", "value", "singleStep",
    "decimals", "checked", "currentIndex", "placeholderText", "html",
)


def props(w):
    out = {}
    for p in w.findall("property"):
        name = p.get("name")
        if name in KEEP:
            out[name] = " ".join("".join(p.itertext()).split())
    # combo box entries
    items = [
        " ".join("".join(i.itertext()).split())
        for i in w.findall("item/property[@name='text']")
    ]
    if items:
        out["items"] = " | ".join(items)
    return out


def child_widgets(w):
    """Direct child widgets, looking through layout/item nesting but never
    across another widget boundary (avoids double-walking nested widgets)."""
    found = []
    stack = [c for c in list(w) if c.tag != "widget"]
    found.extend(c for c in list(w) if c.tag == "widget")
    while stack:
        node = stack.pop()
        for c in list(node):
            if c.tag == "widget":
                found.append(c)
            else:
                stack.append(c)
    return found


def walk(w, path, out):
    name = w.get("name") or "?"
    cls = w.get("class") or "?"
    p = props(w)
    prop_str = "; ".join(f"{k}={v}" for k, v in p.items())
    out.append(f"| `{path}/{name}` | {cls} | {prop_str} |")
    for child in child_widgets(w):
        walk(child, f"{path}/{name}", out)


def main():
    tree = ET.parse(UI_FILE)
    root_widget = tree.getroot().find("widget")
    out = ["# UI inventory — BestFitInterpolator_dialog_base.ui", "",
           "| path | class | properties |", "|---|---|---|"]
    walk(root_widget, "", out)
    sys.stdout.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
