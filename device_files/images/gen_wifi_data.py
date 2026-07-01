#!/usr/bin/env python3
"""One-shot helper: print the WIFI_ICONS block to paste into show_ip.py."""
import base64, os
from PIL import Image

here = os.path.dirname(os.path.abspath(__file__))
icons = [
    ('disconnected', 'wifi_disconnected.png'),
    ('1bar',         'wifi_1bar.png'),
    ('2bar',         'wifi_2bar.png'),
    ('3bar',         'wifi_3bar.png'),
    ('ethernet',     'ethernet.png'),
]

print("WIFI_ICONS = {")
for key, fname in icons:
    img = Image.open(os.path.join(here, fname)).convert('RGBA')
    assert img.size == (24, 24), f"unexpected size {img.size} for {fname}"
    bg = Image.new('RGBA', (24, 24), (0, 0, 0, 255))
    bg.paste(img, mask=img.split()[3])
    rgb = bg.convert('RGB').tobytes()
    b64 = base64.b64encode(rgb).decode()
    # Split into 76-char chunks using implicit string concatenation
    chunks = [b64[i:i+76] for i in range(0, len(b64), 76)]
    print(f"    '{key}': (")
    for chunk in chunks:
        print(f"        '{chunk}'")
    print("    ),")
print("}")
