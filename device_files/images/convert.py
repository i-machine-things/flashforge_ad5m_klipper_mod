#!/usr/bin/env python3
"""Convert all PNG files in this directory to raw BGRA framebuffer images and
compress them with xz.  Drop-in replacement for convert.sh that works on any
platform where Pillow is installed (pip install Pillow).

Output: ./fb/<name>.img.xz  — 800×960 BGRA, xz-compressed.
The 800×960 canvas matches the double-height virtual framebuffer used by the
AD5M driver for page-flipping; the physical display shows the first 800×480
half.
"""

import lzma
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow not found — run: pip install Pillow")

FB_W, FB_H = 800, 960   # virtual framebuffer (double-buffered)

def png_to_fb_xz(src: Path, dst: Path) -> None:
    img = Image.open(src).convert("RGBA")
    canvas = Image.new("RGBA", (FB_W, FB_H), (0, 0, 0, 0))
    canvas.paste(img, (0, 0))

    # PIL RGBA → BGRA: split channels and re-merge
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
