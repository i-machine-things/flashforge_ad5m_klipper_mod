/* show_ip.c — network status overlay for the AD5M framebuffer
 *
 * Draws WiFi + Ethernet icons and the printer's IPv4 address onto /dev/fb0,
 * then blocks on NETLINK_ROUTE and redraws whenever the network changes.
 *
 * No external dependencies — POSIX + Linux headers only.
 * RSS at idle: ~200 KB vs ~15 MB for the Python equivalent.
 *
 * Layout (mirrors show_ip.py — must stay in sync):
 *   Upper-right: WiFi icon | gap | Ethernet icon  (both 25×25 px)
 *   Bottom-centre: primary IPv4 address in scaled 8×8 bitmap font
 */

#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include <arpa/inet.h>
#include <net/if.h>
#include <netinet/in.h>
#include <sys/ioctl.h>
#include <sys/select.h>
#include <sys/socket.h>

#include <linux/rtnetlink.h>

#include "icons.h"   /* ICON_WIFI_*, ICON_ETH*, ICON_SIZE */

/* ── Layout constants — must mirror show_ip.py ─────────────────────────── */
#define CORNER_MARGIN 8
#define ICON_GAP      4
#define SCALE         3   /* 8×8 glyph → 24×24 px */

/* ── Framebuffer geometry (filled by fb_init) ───────────────────────────── */
static int fb_w, fb_h, fb_bpp, fb_stride;

/* ── 8×8 bitmap font indexed by ASCII value ─────────────────────────────── */
static const uint8_t GLYPHS[128][8] = {
    [' '] = { 0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00 },
    ['.'] = { 0x00,0x00,0x00,0x00,0x00,0x18,0x18,0x00 },
    [':'] = { 0x00,0x18,0x18,0x00,0x18,0x18,0x00,0x00 },
    ['0'] = { 0x3C,0x66,0x6E,0x76,0x66,0x66,0x3C,0x00 },
    ['1'] = { 0x18,0x38,0x18,0x18,0x18,0x18,0x3C,0x00 },
    ['2'] = { 0x3C,0x66,0x06,0x0C,0x18,0x30,0x7E,0x00 },
    ['3'] = { 0x3C,0x66,0x06,0x1C,0x06,0x66,0x3C,0x00 },
    ['4'] = { 0x0C,0x1C,0x3C,0x6C,0x7E,0x0C,0x0C,0x00 },
    ['5'] = { 0x7E,0x60,0x7C,0x06,0x06,0x66,0x3C,0x00 },
    ['6'] = { 0x3C,0x66,0x60,0x7C,0x66,0x66,0x3C,0x00 },
    ['7'] = { 0x7E,0x06,0x0C,0x18,0x30,0x30,0x30,0x00 },
    ['8'] = { 0x3C,0x66,0x66,0x3C,0x66,0x66,0x3C,0x00 },
    ['9'] = { 0x3C,0x66,0x66,0x3E,0x06,0x66,0x3C,0x00 },
};

/* ── FB helpers ─────────────────────────────────────────────────────────── */

static int fb_init(void)
{
    /* Physical size from the active mode string, e.g. "U:480x272p-0". */
    FILE *f = fopen("/sys/class/graphics/fb0/modes", "r");
    if (f) {
        char mode[64] = {0};
        if (fgets(mode, sizeof mode, f)) {
            char *colon = strchr(mode, ':');
            if (colon && sscanf(colon + 1, "%dx%d", &fb_w, &fb_h) == 2) {
                fclose(f);
                goto got_size;
            }
        }
        fclose(f);
    }
    /* Fallback: virtual_size (may be 2× physical on page-flip drivers). */
    f = fopen("/sys/class/graphics/fb0/virtual_size", "r");
    if (!f) return -1;
    if (fscanf(f, "%d,%d", &fb_w, &fb_h) != 2) { fclose(f); return -1; }
    fclose(f);

got_size:
    f = fopen("/sys/class/graphics/fb0/bits_per_pixel", "r");
    if (!f) return -1;
    if (fscanf(f, "%d", &fb_bpp) != 1) { fclose(f); return -1; }
    fclose(f);

    fb_stride = fb_w * (fb_bpp / 8);
    return 0;
}

/* Pack one RGB triplet into the framebuffer's native pixel format. */
static void encode_pixel(uint8_t *dst, uint8_t r, uint8_t g, uint8_t b)
{
    if (fb_bpp == 16) {
        uint16_t px = (uint16_t)(((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3));
        dst[0] = (uint8_t)(px & 0xFF);
        dst[1] = (uint8_t)(px >> 8);
    } else if (fb_bpp == 24) {
        dst[0] = b; dst[1] = g; dst[2] = r;
    } else {        /* 32-bit BGRA */
        dst[0] = b; dst[1] = g; dst[2] = r; dst[3] = 0xFF;
    }
}

/* Write a horizontal run of identical pixels. */
static void fill_row(int fd, int y, int x0, int n, uint8_t r, uint8_t g, uint8_t b)
{
    int ppb = fb_bpp / 8;
    /* Stack buffer: 800 px × 4 bytes = 3200 B. Clamp n to buffer capacity. */
    uint8_t buf[800 * 4];
    if (n > 800) n = 800;
    uint8_t px[4];
    encode_pixel(px, r, g, b);
    for (int i = 0; i < n; i++)
        memcpy(buf + i * ppb, px, (size_t)ppb);
    pwrite(fd, buf, (size_t)n * ppb, (off_t)(y * fb_stride + x0 * ppb));
}

/* Blit a 25×25 RGB icon from icons.h onto the framebuffer. */
static void draw_icon(int fd, const uint8_t *rgb, int x0, int y0)
{
    int ppb = fb_bpp / 8;
    uint8_t line[ICON_SIZE * 4];
    for (int row = 0; row < ICON_SIZE; row++) {
        for (int col = 0; col < ICON_SIZE; col++) {
            int idx = (row * ICON_SIZE + col) * 3;
            encode_pixel(line + col * ppb, rgb[idx], rgb[idx+1], rgb[idx+2]);
        }
        pwrite(fd, line, (size_t)ICON_SIZE * ppb,
               (off_t)((y0 + row) * fb_stride + x0 * ppb));
    }
}

/* Draw scaled bitmap text centred at (x0, y0). */
static void draw_text(int fd, const char *text, int x0, int y0)
{
    int ppb = fb_bpp / 8;
    int cw  = 8 * SCALE;
    int ch  = 8 * SCALE;
    int len = (int)strlen(text);
    if (len > 15) len = 15;   /* buffer holds "255.255.255.255" (15 chars) max */

    /* 15 chars × 24 px × 4 B = 1440 B max per row */
    uint8_t line[15 * 8 * SCALE * 4];

    uint8_t fg[4], bg[4];
    encode_pixel(fg, 255, 255, 255);
    encode_pixel(bg,   0,   0,   0);

    for (int row = 0; row < ch; row++) {
        int glyph_row = row / SCALE;
        uint8_t *p = line;
        for (int ci = 0; ci < len; ci++) {
            unsigned char c = (unsigned char)text[ci];
            uint8_t bits = (c < 128) ? GLYPHS[c][glyph_row] : 0;
            for (int col = 0; col < 8; col++) {
                int lit = (bits >> (7 - col)) & 1;
                for (int sx = 0; sx < SCALE; sx++) {
                    memcpy(p, lit ? fg : bg, (size_t)ppb);
                    p += ppb;
                }
            }
        }
        pwrite(fd, line, (size_t)len * cw * ppb,
               (off_t)((y0 + row) * fb_stride + x0 * ppb));
    }
}

/* ── Network queries ────────────────────────────────────────────────────── */

/* Read wlan0 level from /proc/net/wireless.
 * Returns 1/2/3 (signal bars) or 0 if disconnected / not found. */
static int wifi_signal_bars(void)
{
    FILE *f = fopen("/proc/net/wireless", "r");
    if (!f) return 0;

    char line[256];
    while (fgets(line, sizeof line, f)) {
        if (!strstr(line, "wlan0")) continue;

        /* Fields: "wlan0: status link level. noise. ..." */
        char iface[16], s0[16], s1[16], level_s[16];
        if (sscanf(line, "%15s %15s %15s %15s", iface, s0, s1, level_s) != 4)
            continue;

        /* Strip trailing '.' that the kernel sometimes appends. */
        size_t l = strlen(level_s);
        if (l > 0 && level_s[l - 1] == '.') level_s[l - 1] = '\0';

        int level = atoi(level_s);
        fclose(f);
        if (level >= -55) return 3;
        if (level >= -70) return 2;
        return 1;
    }
    fclose(f);
    return 0;
}

/* Return 1 if the named interface has a bound IPv4 address. */
static int iface_has_ip(const char *name)
{
    struct ifreq req;
    memset(&req, 0, sizeof req);
    strncpy(req.ifr_name, name, IFNAMSIZ - 1);
    int s = socket(AF_INET, SOCK_DGRAM, 0);
    if (s < 0) return 0;
    int ok = (ioctl(s, SIOCGIFADDR, &req) == 0);
    close(s);
    return ok;
}

/* Find the primary outbound IPv4 address via a connected UDP socket.
 * Returns 1 and fills buf, or 0 if offline. */
static int primary_ip(char *buf, size_t bufsz)
{
    struct sockaddr_in dst = {0};
    dst.sin_family = AF_INET;
    dst.sin_port   = htons(80);
    inet_pton(AF_INET, "8.8.8.8", &dst.sin_addr);

    int s = socket(AF_INET, SOCK_DGRAM, 0);
    if (s < 0) return 0;

    int ok = 0;
    if (connect(s, (struct sockaddr *)&dst, sizeof dst) == 0) {
        struct sockaddr_in src = {0};
        socklen_t len = sizeof src;
        if (getsockname(s, (struct sockaddr *)&src, &len) == 0) {
            inet_ntop(AF_INET, &src.sin_addr, buf, (socklen_t)bufsz);
            ok = 1;
        }
    }
    close(s);
    return ok;
}

/* ── Draw cycle ─────────────────────────────────────────────────────────── */

static void update(int fb)
{
    char ip[INET_ADDRSTRLEN] = "0.0.0.0";
    primary_ip(ip, sizeof ip);

    int bars = wifi_signal_bars();
    int eth  = iface_has_ip("eth0");

    const uint8_t *wifi_rgb;
    switch (bars) {
        case 3:  wifi_rgb = ICON_WIFI_3BAR;        break;
        case 2:  wifi_rgb = ICON_WIFI_2BAR;        break;
        case 1:  wifi_rgb = ICON_WIFI_1BAR;        break;
        default: wifi_rgb = ICON_WIFI_DISCONNECTED; break;
    }
    const uint8_t *eth_rgb = eth ? ICON_ETH : ICON_ETH_DISCONNECTED;

    int x0_eth  = fb_w - ICON_SIZE - CORNER_MARGIN;
    int x0_wifi = x0_eth - ICON_GAP - ICON_SIZE;

    /* Clear icon strip. */
    for (int y = CORNER_MARGIN; y < CORNER_MARGIN + ICON_SIZE; y++)
        fill_row(fb, y, x0_wifi, ICON_SIZE * 2 + ICON_GAP, 0, 0, 0);

    draw_icon(fb, wifi_rgb, x0_wifi, CORNER_MARGIN);
    draw_icon(fb, eth_rgb,  x0_eth,  CORNER_MARGIN);

    /* Clear + draw IP text at bottom centre. */
    int cw    = 8 * SCALE;
    int ch    = 8 * SCALE;
    int len   = (int)strlen(ip);
    int x0_ip = (fb_w - len * cw) / 2;
    if (x0_ip < 0) x0_ip = 0;
    int y0_ip = fb_h - ch - 12;

    for (int y = y0_ip - 9; y < fb_h; y++)
        fill_row(fb, y, 0, fb_w, 0, 0, 0);

    draw_text(fb, ip, x0_ip, y0_ip);
}

/* ── Netlink event loop ─────────────────────────────────────────────────── */

static int open_netlink(void)
{
    int nl = socket(AF_NETLINK, SOCK_RAW, NETLINK_ROUTE);
    if (nl < 0) return -1;
    struct sockaddr_nl sa = {0};
    sa.nl_family = AF_NETLINK;
    sa.nl_groups = RTMGRP_IPV4_IFADDR;
    if (bind(nl, (struct sockaddr *)&sa, sizeof sa) < 0) {
        close(nl);
        return -1;
    }
    return nl;
}

int main(void)
{
    if (fb_init() < 0)
        return 0;   /* no framebuffer — nothing to do */

    int fb = open("/dev/fb0", O_RDWR);
    if (fb < 0) return 0;

    /* Wait up to 30 s for the initial network assignment. */
    char ip[INET_ADDRSTRLEN];
    for (int i = 0; i < 30 && !primary_ip(ip, sizeof ip); i++)
        sleep(1);

    update(fb);

    /* Block on netlink, redrawing on each IPv4 address-change burst. */
    int nl = open_netlink();
    if (nl < 0) {
        close(fb);
        return 0;   /* no netlink — one-shot mode */
    }

    char buf[4096];
    for (;;) {
        if (recv(nl, buf, sizeof buf, 0) <= 0) break;

        /* Drain burst within a 2-second window (coalesces addr-del + addr-add). */
        struct timeval tv;
        fd_set rd;
        do {
            tv.tv_sec = 2; tv.tv_usec = 0;
            FD_ZERO(&rd); FD_SET(nl, &rd);
        } while (select(nl + 1, &rd, NULL, NULL, &tv) > 0
                 && recv(nl, buf, sizeof buf, 0) > 0);

        update(fb);
    }

    close(nl);
    close(fb);
    return 0;
}
