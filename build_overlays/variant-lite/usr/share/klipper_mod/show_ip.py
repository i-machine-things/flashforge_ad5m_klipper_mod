#!/usr/bin/env python3
"""Overlay the IP address onto the framebuffer once, then exit.
Only stdlib is used to keep the memory footprint small."""

import os
import socket
import struct
import time

# 8x8 bitmap font — digits, dot, space, and slash for CIDR (unused but kept)
GLYPHS = {
    ' ': [0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00],
    '.': [0x00,0x00,0x00,0x00,0x00,0x18,0x18,0x00],
    ':': [0x00,0x18,0x18,0x00,0x18,0x18,0x00,0x00],
    '0': [0x3C,0x66,0x6E,0x76,0x66,0x66,0x3C,0x00],
    '1': [0x18,0x38,0x18,0x18,0x18,0x18,0x3C,0x00],
    '2': [0x3C,0x66,0x06,0x0C,0x18,0x30,0x7E,0x00],
    '3': [0x3C,0x66,0x06,0x1C,0x06,0x66,0x3C,0x00],
    '4': [0x0C,0x1C,0x3C,0x6C,0x7E,0x0C,0x0C,0x00],
    '5': [0x7E,0x60,0x7C,0x06,0x06,0x66,0x3C,0x00],
    '6': [0x3C,0x66,0x60,0x7C,0x66,0x66,0x3C,0x00],
    '7': [0x7E,0x06,0x0C,0x18,0x30,0x30,0x30,0x00],
    '8': [0x3C,0x66,0x66,0x3C,0x66,0x66,0x3C,0x00],
    '9': [0x3C,0x66,0x66,0x3E,0x06,0x66,0x3C,0x00],
}

SCALE = 3           # 8x8 → 24x24 px per char; readable on the 480x272 panel
FG = (255, 255, 255)
BG = (0, 0, 0)


def get_ip(timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
            finally:
                s.close()
            return ip
        except OSError:
            pass
        time.sleep(1)
    return None


def get_fb_info():
    # Read physical size from the active mode string (e.g. "U:480x272p-0").
    # virtual_size can be double the physical height when the driver uses
    # page-flipping, which would push the overlay text off-screen.
    try:
        with open('/sys/class/graphics/fb0/modes') as f:
            first_mode = f.read().strip().split('\n')[0]
        res = first_mode.split(':')[-1].split('p')[0]   # "480x272"
        w, h = map(int, res.split('x'))
    except Exception:
        with open('/sys/class/graphics/fb0/virtual_size') as f:
            w, h = map(int, f.read().strip().split(','))
    with open('/sys/class/graphics/fb0/bits_per_pixel') as f:
        bpp = int(f.read().strip())
    return w, h, bpp, w * (bpp // 8)


def encode_pixel(r, g, b, bpp):
    if bpp not in (16, 24, 32):
        raise ValueError(f"Unsupported bits-per-pixel: {bpp}")
    if bpp == 16:
        return struct.pack('<H', ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3))
    if bpp == 24:
        return struct.pack('BBB', b, g, r)
    return struct.pack('BBBB', b, g, r, 0xFF)   # 32-bit BGRA


def draw(text, fb_w, fb_h, bpp, stride):
    ppb = bpp // 8
    cw = 8 * SCALE
    ch = 8 * SCALE
    text_w = len(text) * cw

    # Centre horizontally, place near bottom with a small margin
    x0 = max(0, (fb_w - text_w) // 2)
    y0 = fb_h - ch - 12

    fg_px = encode_pixel(*FG, bpp)
    bg_px = encode_pixel(*BG, bpp)
    blank_row = bg_px * fb_w

    with open('/dev/fb0', 'r+b') as fb:
        # Clear the whole strip (separator + text height + margin) so the
        # static placeholder baked into the img.xz is fully overwritten,
        # regardless of whether this IP is longer or shorter than 0.0.0.0.
        for row in range(y0 - 9, fb_h):
            fb.seek(row * stride)
            fb.write(blank_row)

        for row in range(ch):
            glyph_row = row // SCALE          # which of the 8 bitmap rows
            line = bytearray()
            for ch_char in text:
                bits = GLYPHS.get(ch_char, GLYPHS[' '])[glyph_row]
                for col in range(8):
                    px = fg_px if (bits >> (7 - col)) & 1 else bg_px
                    line += px * SCALE        # horizontal scale
            fb.seek((y0 + row) * stride + x0 * ppb)
            fb.write(bytes(line))


def main():
    try:
        fb_w, fb_h, bpp, stride = get_fb_info()
    except OSError:
        return  # no framebuffer device — nothing to do

    ip = get_ip()
    text = "IP  " + (ip if ip else "0.0.0.0")

    try:
        draw(text, fb_w, fb_h, bpp, stride)
    except OSError:
        pass


if __name__ == '__main__':
    main()
