#!/usr/bin/env python3
"""Convert all PNG files in this directory to raw BGRA framebuffer images and
compress them with xz.  Drop-in replacement for convert.sh that works on any
platform where Pillow is installed (pip install Pillow).

Output: ./fb/<name>.img.xz  -- 800x960 BGRA, xz-compressed.
The 800x960 canvas matches the double-height virtual framebuffer used by the
AD5M driver for page-flipping; the physical display shows the first 800x480
half.

A static placeholder (dim grey WiFi square + "0.0.0.0") is baked into the
bottom of every image at the same position and scale as show_ip.py uses.
When show_ip.py runs at runtime it clears the strip and draws the live
status indicator and address on top.
"""

import lzma
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow not found -- run: pip install Pillow")

FB_W, FB_H = 800, 960   # virtual framebuffer (double-buffered)
PHYS_H = 480            # physical display height (first half of virtual)

# ── same 8x8 bitmap font as show_ip.py ──────────────────────────────────────
_GLYPHS = {
    ' ': [0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00],
    '.': [0x00, 0x00, 0x00, 0x00, 0x00, 0x18, 0x18, 0x00],
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
_SCALE       = 3                  # matches show_ip.py SCALE
_ICON_SIZE   = 25                 # matches show_ip.py ICON_SIZE
_PLACEHOLDER = "0.0.0.0"
_FG          = (72, 72, 72, 255)  # dim gray for placeholder IP text


_CORNER_MARGIN = 8   # pixels from screen edge — mirrors show_ip.py CORNER_MARGIN
_ICON_GAP      = 4   # gap between the two corner icons — mirrors show_ip.py ICON_GAP


def _dim_icon(path):
    """Load a PNG icon, dim it to 30%, return RGBA Image."""
    icon = Image.open(path).convert("RGBA")
    if icon.size != (_ICON_SIZE, _ICON_SIZE):
        icon = icon.resize((_ICON_SIZE, _ICON_SIZE), Image.LANCZOS)
    r, g, b, a = icon.split()
    r = r.point(lambda v: v * 30 // 100)
    g = g.point(lambda v: v * 30 // 100)
    b = b.point(lambda v: v * 30 // 100)
    return Image.merge("RGBA", (r, g, b, a))


def _draw_ip_placeholder(img: Image.Image) -> None:
    """Burn placeholders matching show_ip.py's layout:
    WiFi-disconnected + Ethernet-disconnected icons (upper right, side by side)
    and '0.0.0.0' text (bottom centre)."""
    w  = img.width
    cw = 8 * _SCALE
    ch = 8 * _SCALE

    # Two icons — upper right, WiFi left / Ethernet right (mirrors show_ip.py)
    x0_eth  = w - _ICON_SIZE - _CORNER_MARGIN
    x0_wifi = x0_eth - _ICON_GAP - _ICON_SIZE
    y0_icons = _CORNER_MARGIN

    # IP text — bottom centre (mirrors show_ip.py)
    x0_ip = max(0, (w - len(_PLACEHOLDER) * cw) // 2)
    y0_ip = PHYS_H - ch - 12

    # Dimmed disconnected icons
    wifi_path = here / "wifi_disconnected.png"
    eth_path  = here / "ethernet_disconnected.png"
    if wifi_path.exists():
        img.paste(_dim_icon(wifi_path), (x0_wifi, y0_icons), mask=_dim_icon(wifi_path).split()[3])
    if eth_path.exists():
        img.paste(_dim_icon(eth_path),  (x0_eth,  y0_icons), mask=_dim_icon(eth_path).split()[3])

    # IP address placeholder text (bottom centre)
    px = img.load()
    for row in range(ch):
        glyph_row = row // _SCALE
        for ci, char in enumerate(_PLACEHOLDER):
            bits = _GLYPHS.get(char, _GLYPHS[' '])[glyph_row]
            for col in range(8):
                if (bits >> (7 - col)) & 1:
                    for sx in range(_SCALE):
                        px_x = x0_ip + ci * cw + col * _SCALE + sx
                        px_y = y0_ip + row
                        if 0 <= px_x < w and 0 <= px_y < PHYS_H:
                            px[px_x, px_y] = _FG


def png_to_fb_xz(src: Path, dst: Path) -> None:
    img = Image.open(src).convert("RGBA")

    canvas = Image.new("RGBA", (FB_W, FB_H), (0, 0, 0, 0))
    canvas.paste(img, (0, 0))

    # PIL RGBA -> BGRA: split channels and re-merge
    r, g, b, a = canvas.split()
    bgra = Image.merge("RGBA", (b, g, r, a))

    dst.parent.mkdir(parents=True, exist_ok=True)
    with lzma.open(dst, "wb") as f:
        f.write(bgra.tobytes())
    kb = dst.stat().st_size // 1024
    print(f"  {src.name} -> {dst.name}  ({kb} KB)")


here = Path(__file__).parent
fb_dir = here / "fb"

if __name__ == "__main__":
    # Exclude icon assets (wifi_*.png, ethernet*.png) — used by show_ip.py, not screen images
    _ICON_PREFIXES = ("wifi_", "ethernet")
    pngs = sorted(p for p in here.glob("*.png") if not p.name.startswith(_ICON_PREFIXES))
    if not pngs:
        sys.exit("No PNG files found in " + str(here))

    print(f"Converting {len(pngs)} PNG(s) -> {fb_dir}/")
    for png in pngs:
        png_to_fb_xz(png, fb_dir / (png.stem + ".img.xz"))
    print("Done.")
