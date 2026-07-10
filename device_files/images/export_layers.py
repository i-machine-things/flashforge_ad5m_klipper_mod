#!/usr/bin/env python3
"""Build tool for AD5M framebuffer images.

Commands
--------
(none)   Export SVG layers -> PNG, then convert to .img.xz  [default]
export   Export SVG layers -> PNG only
convert  Convert existing PNGs -> .img.xz  (no Inkscape needed)
preview  Render show_ip preview PNGs

Requirements
------------
  Inkscape 1.x at C:\\Program Files\\Inkscape\\bin\\inkscape.exe  (export / default)
  Pillow: pip install Pillow                                       (convert / preview)
"""

import argparse
import lzma
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow not found — run: pip install Pillow")

HERE     = Path(__file__).parent
SVG      = HERE / "template.svg"
FB_DIR   = HERE / "fb"
INKSCAPE = Path(r"C:\Program Files\Inkscape\bin\inkscape.exe")

# Framebuffer geometry
FB_W, FB_H = 800, 960   # virtual (double-buffered)
PHYS_H     = 480        # physical display height

# Icon / text layout — must mirror show_ip.py
ICON_SIZE     = 25
ICON_GAP      = 4
CORNER_MARGIN = 8
SCALE         = 3

# 8×8 bitmap font shared with show_ip.py
GLYPHS = {
    ' ': [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
    '.': [0x00, 0x00, 0x00, 0x00, 0x00, 0x18, 0x18, 0x00],
    ':': [0x00, 0x18, 0x18, 0x00, 0x18, 0x18, 0x00, 0x00],
    '0': [0x3C, 0x66, 0x6E, 0x76, 0x66, 0x66, 0x3C, 0x00],
    '1': [0x18, 0x38, 0x18, 0x18, 0x18, 0x18, 0x3C, 0x00],
    '2': [0x3C, 0x66, 0x06, 0x0C, 0x18, 0x30, 0x7E, 0x00],
    '3': [0x3C, 0x66, 0x06, 0x1C, 0x06, 0x66, 0x3C, 0x00],
    '4': [0x0C, 0x1C, 0x3C, 0x6C, 0x7E, 0x0C, 0x0C, 0x00],
    '5': [0x7E, 0x60, 0x7C, 0x06, 0x06, 0x66, 0x3C, 0x00],
    '6': [0x3C, 0x66, 0x60, 0x7C, 0x66, 0x66, 0x3C, 0x00],
    '7': [0x7E, 0x06, 0x0C, 0x18, 0x30, 0x30, 0x30, 0x00],
    '8': [0x3C, 0x66, 0x66, 0x3C, 0x66, 0x66, 0x3C, 0x00],
    '9': [0x3C, 0x66, 0x66, 0x3E, 0x06, 0x66, 0x3C, 0x00],
}


# ── SVG -> PNG ─────────────────────────────────────────────────────────────────

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

ALWAYS_VISIBLE = {"Background", "Logos"}
_INK_NS = "http://www.inkscape.org/namespaces/inkscape"


def _register_ns(svg_text: str) -> None:
    for prefix, uri in re.findall(r'xmlns(?::(\w+))?="([^"]+)"', svg_text):
        ET.register_namespace(prefix or "", uri)


def _set_display(style: str, visible: bool) -> str:
    value = "inline" if visible else "none"
    if re.search(r"display\s*:", style):
        return re.sub(r"display\s*:[^;]*", f"display:{value}", style)
    return f"display:{value};{style}" if style else f"display:{value}"


def _export_layer(label: str, out_png: Path) -> None:
    svg_text = SVG.read_text(encoding="utf-8")
    _register_ns(svg_text)
    tree = ET.parse(SVG)
    for g in tree.getroot():
        if g.get(f"{{{_INK_NS}}}groupmode") != "layer":
            continue
        lbl = g.get(f"{{{_INK_NS}}}label", "")
        g.set("style", _set_display(g.get("style", ""), lbl in ALWAYS_VISIBLE or lbl == label))

    tmp = HERE / f"_tmp_{label}.svg"
    try:
        tree.write(tmp, encoding="utf-8", xml_declaration=True)
        r = subprocess.run(
            [str(INKSCAPE), "--export-type=png", f"--export-filename={out_png}",
             "--export-area-page", str(tmp)],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            print(f"  [warn] {label}:\n{r.stderr.strip()}")
            r.check_returncode()
        print(f"  {label:30s} -> {out_png.name}")
    finally:
        tmp.unlink(missing_ok=True)


def cmd_export() -> None:
    if not INKSCAPE.exists():
        sys.exit(f"Inkscape not found at {INKSCAPE}")
    if not SVG.exists():
        sys.exit(f"SVG not found: {SVG}")
    print(f"Exporting {len(LAYER_MAP)} layers from {SVG.name} ...")
    for label, png_name in LAYER_MAP.items():
        _export_layer(label, HERE / png_name)


# ── PNG -> .img.xz ─────────────────────────────────────────────────────────────

# Skip runtime icon assets and dev preview PNGs
_SKIP_PREFIXES = ("wifi_", "ethernet", "preview_")


def _png_to_fb_xz(src: Path) -> None:
    img = Image.open(src).convert("RGBA")
    canvas = Image.new("RGBA", (FB_W, FB_H), (0, 0, 0, 0))
    canvas.paste(img, (0, 0))
    r, g, b, a = canvas.split()
    bgra = Image.merge("RGBA", (b, g, r, a))
    dst = FB_DIR / (src.stem + ".img.xz")
    dst.parent.mkdir(parents=True, exist_ok=True)
    with lzma.open(dst, "wb") as f:
        f.write(bgra.tobytes())
    print(f"  {src.name} -> {dst.name}  ({dst.stat().st_size // 1024} KB)")


def cmd_convert() -> None:
    pngs = sorted(p for p in HERE.glob("*.png") if not p.name.startswith(_SKIP_PREFIXES))
    if not pngs:
        sys.exit("No PNG files found in " + str(HERE))
    print(f"Converting {len(pngs)} PNG(s) -> {FB_DIR}/")
    for png in pngs:
        _png_to_fb_xz(png)


# ── Preview renderer ───────────────────────────────────────────────────────────

_WHITE = (255, 255, 255, 255)
_BLACK = (0, 0, 0, 255)

_PREVIEWS = [
    ("192.168.1.100", "wifi_3bar",        "ethernet",              "preview_both_connected.png"),
    ("192.168.1.101", "wifi_disconnected", "ethernet",              "preview_eth_only.png"),
    ("192.168.1.102", "wifi_2bar",         "ethernet_disconnected", "preview_wifi_only.png"),
    ("0.0.0.0",       "wifi_disconnected", "ethernet_disconnected", "preview_disconnected.png"),
]


def _draw_text(px, text: str, x0: int, y0: int, fg, clip_h: int) -> None:
    cw, ch = 8 * SCALE, 8 * SCALE
    for row in range(ch):
        g_row = row // SCALE
        for ci, char in enumerate(text):
            bits = GLYPHS.get(char, GLYPHS[' '])[g_row]
            for col in range(8):
                if (bits >> (7 - col)) & 1:
                    for sx in range(SCALE):
                        x = x0 + ci * cw + col * SCALE + sx
                        y = y0 + row
                        if y < clip_h:
                            px[x, y] = fg


def _paste_icon(img: Image.Image, name: str, x0: int, y0: int) -> None:
    src = Image.open(HERE / f"{name}.png").convert("RGBA")
    bg = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), _BLACK)
    bg.paste(src, mask=src.split()[3])
    img.paste(bg, (x0, y0))


def _render_preview(ip: str, wifi: str, eth: str, out: str) -> None:
    img = Image.open(HERE / "mod_start.png").convert("RGBA")
    W, H = img.size
    px = img.load()

    x0_eth  = W - ICON_SIZE - CORNER_MARGIN
    x0_wifi = x0_eth - ICON_GAP - ICON_SIZE
    y0_icons = CORNER_MARGIN

    for y in range(y0_icons, y0_icons + ICON_SIZE):
        for x in range(x0_wifi, x0_wifi + ICON_SIZE * 2 + ICON_GAP):
            px[x, y] = _BLACK
    _paste_icon(img, wifi, x0_wifi, y0_icons)
    _paste_icon(img, eth,  x0_eth,  y0_icons)

    cw, ch = 8 * SCALE, 8 * SCALE
    x0_ip = max(0, (W - len(ip) * cw) // 2)
    y0_ip = H - ch - 12
    px = img.load()
    for y in range(y0_ip - 9, H):
        for x in range(W):
            px[x, y] = _BLACK
    _draw_text(px, ip, x0_ip, y0_ip, _WHITE, H)

    img.save(HERE / out)
    print(f"  {out}  ({W}x{H})")


def cmd_preview() -> None:
    if not (HERE / "mod_start.png").exists():
        sys.exit("mod_start.png not found — run export first")
    print("Rendering previews ...")
    for args in _PREVIEWS:
        _render_preview(*args)


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "command", nargs="?", choices=["export", "convert", "preview"],
        help="default (no arg): export + convert",
    )
    cmd = ap.parse_args().command
    if cmd == "export":
        cmd_export()
    elif cmd == "convert":
        cmd_convert()
    elif cmd == "preview":
        cmd_preview()
    else:
        cmd_export()
        print()
        cmd_convert()


if __name__ == "__main__":
    main()
