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
    from PIL import Image, ImageDraw
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
_SCALE = 3                  # matches show_ip.py SCALE
_PLACEHOLDER = "0.0.0.0"   # IP text shown in placeholder
_FG = (72, 72, 72, 255)    # dim gray so it reads as "placeholder"
_IND_COLOR = (55, 55, 55, 255)  # dim grey indicator square (matches separator)


def _draw_ip_placeholder(img: Image.Image) -> None:
    """Burn a dim status-square + '0.0.0.0' onto the image at show_ip.py's render position."""
    w = img.width
    cw = ch = 8 * _SCALE
    ind_w = cw          # indicator square: same width as one character
    gap_w = cw // 2     # half-char gap between indicator and text
    text_w = len(_PLACEHOLDER) * cw
    total_w = ind_w + gap_w + text_w
    x0 = max(0, (w - total_w) // 2)    # left edge of indicator
    y0 = PHYS_H - ch - 12              # mirrors: fb_h - ch - 12 in show_ip.py

    draw = ImageDraw.Draw(img)
    # Separator line a few pixels above the placeholder
    draw.line([(40, y0 - 8), (w - 40, y0 - 8)], fill=(55, 55, 55, 255), width=1)

    # Dim grey indicator square (matches shape of runtime WiFi status square)
    draw.rectangle([x0, y0, x0 + ind_w - 1, y0 + ch - 1], fill=_IND_COLOR)

    # Bitmap glyph text to the right of the indicator
    text_x0 = x0 + ind_w + gap_w
    px = img.load()
    for row in range(ch):
        glyph_row = row // _SCALE
        for ci, char in enumerate(_PLACEHOLDER):
            bits = _GLYPHS.get(char, _GLYPHS[' '])[glyph_row]
            for col in range(8):
                if (bits >> (7 - col)) & 1:
                    for sx in range(_SCALE):
                        px_x = text_x0 + ci * cw + col * _SCALE + sx
                        px_y = y0 + row
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

pngs = sorted(here.glob("*.png"))
if not pngs:
    sys.exit("No PNG files found in " + str(here))

print(f"Converting {len(pngs)} PNG(s) -> {fb_dir}/")
for png in pngs:
    png_to_fb_xz(png, fb_dir / (png.stem + ".img.xz"))
print("Done.")
