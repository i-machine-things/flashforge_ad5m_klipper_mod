#!/usr/bin/env python3
"""Export each SVG layer as a PNG, then run convert.py to build framebuffer images.

Usage:
    python export_layers.py              # export all layers + convert to .img.xz
    python export_layers.py --no-convert # export PNGs only, skip convert step

Requires:
  - Inkscape 1.x at C:\\Program Files\\Inkscape\\bin\\inkscape.exe
  - Pillow (pip install Pillow) -- only needed for the convert step
"""

import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

INKSCAPE = Path(r"C:\Program Files\Inkscape\bin\inkscape.exe")
HERE     = Path(__file__).parent
SVG      = HERE / "template.svg"

# Maps each SVG layer label to its output PNG filename.
# Layers not listed here are ignored (e.g. Background, Logos, WiFi icons).
LAYER_MAP = {
    "install_start":          "install_start.png",
    "install_ok":             "install_ok.png",
    "uninstall_ok":           "uninstall_ok.png",
    "install_fail_mem":       "install_fail_mem.png",
    "install_fail_version":   "install_fail_vers.png",
    "install_fail_generic":   "install_fail_error.png",
    "uninstall_fail_generic": "uninstall_fail_error.png",
    "mod_start":              "mod_start.png",
    "mod_shutdown":           "mod_shutdown.png",
    "mcu_update":             "mcu_update.png",
    "mcu_update_error":       "mcu_update_error.png",
    "mcu_update_ok":          "mcu_update_ok.png",
    "mcu_update_stock":       "mcu_update_stock.png",
}

# These layers stay visible in every export (shared background/logos).
ALWAYS_VISIBLE = {"Background", "Logos"}

INK_NS = "http://www.inkscape.org/namespaces/inkscape"


def _register_namespaces(svg_text: str) -> None:
    """Register every xmlns: declaration so ElementTree preserves prefixes."""
    for prefix, uri in re.findall(r'xmlns(?::(\w+))?="([^"]+)"', svg_text):
        ET.register_namespace(prefix or "", uri)


def _set_display(style: str, visible: bool) -> str:
    """Replace or insert a display:inline/none declaration in a CSS style string."""
    value = "inline" if visible else "none"
    if re.search(r"display\s*:", style):
        return re.sub(r"display\s*:[^;]*", f"display:{value}", style)
    return f"display:{value};{style}" if style else f"display:{value}"


def export_layer(layer_label: str, out_png: Path) -> None:
    """Write a temp SVG showing only the target layer, export it via Inkscape."""
    svg_text = SVG.read_text(encoding="utf-8")
    _register_namespaces(svg_text)
    tree = ET.parse(SVG)
    root = tree.getroot()

    for g in root:
        if g.get(f"{{{INK_NS}}}groupmode") != "layer":
            continue
        label   = g.get(f"{{{INK_NS}}}label", "")
        visible = label in ALWAYS_VISIBLE or label == layer_label
        g.set("style", _set_display(g.get("style", ""), visible))

    tmp_path = HERE / f"_tmp_{layer_label}.svg"
    try:
        tree.write(tmp_path, encoding="utf-8", xml_declaration=True)
        result = subprocess.run(
            [
                str(INKSCAPE),
                "--export-type=png",
                f"--export-filename={out_png}",
                "--export-area-page",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"  [warn] Inkscape stderr for {layer_label}:\n{result.stderr.strip()}")
            result.check_returncode()
        print(f"  {layer_label:30s} -> {out_png.name}")
    finally:
        tmp_path.unlink(missing_ok=True)


def main() -> None:
    no_convert = "--no-convert" in sys.argv

    if not INKSCAPE.exists():
        sys.exit(f"Inkscape not found at {INKSCAPE}")
    if not SVG.exists():
        sys.exit(f"SVG not found: {SVG}")

    print(f"Exporting {len(LAYER_MAP)} layers from {SVG.name} ...")
    for label, png_name in LAYER_MAP.items():
        export_layer(label, HERE / png_name)

    if no_convert:
        print("\nDone (skipped convert step).")
        return

    print("\nRunning convert.py ...")
    subprocess.run([sys.executable, str(HERE / "convert.py")], check=True)
    print("Done.")


if __name__ == "__main__":
    main()
