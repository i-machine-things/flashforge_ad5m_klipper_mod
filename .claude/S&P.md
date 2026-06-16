# Standards & Practices — CodeRabbit Review Log

<!--
Add entries here each time a CodeRabbit or human review surfaces a new finding.
Format:

## YYYY-MM-DD — `path/to/file` (short description)

**Review:** WHAT WAS FLAGGED
**Result:** outcome / resolution

### Findings

1. **Title**
   - Detail
   - Fix applied
-->

## 2026-06-16 — PR #38 `show_ip.py`, `build-lite.yml`, `install_steps.sh` (CR review: lite IP display + CI)

**Review:** CodeRabbit flagged 5 actionable issues and 4 nitpicks across 3 files.
**Result:** All actionable issues fixed; nitpicks addressed or logged.

### Findings

1. **Socket resource leak in `get_ip()`** (`show_ip.py` lines 32-44)
   - If `connect()` or `getsockname()` raised `OSError` after `socket.socket()`, the socket was never closed — up to 30 leaked FDs across retry iterations.
   - Fixed: wrapped socket ops in `try/finally` so `s.close()` always runs.

2. **Missing bpp validation in `encode_pixel()`** (`show_ip.py` lines 55-60)
   - Function silently fell through to 32-bit path for unsupported bpp values (e.g. 8-bit), causing silent data corruption.
   - Fixed: added `if bpp not in (16, 24, 32): raise ValueError(...)` guard at the top.

3. **Fallback message uses glyphs not in GLYPHS dict** (`show_ip.py` lines 10-25 / 98)
   - `"No network"` contains letters (`N`, `o`, `e`, etc.) absent from GLYPHS (only digits, `.`, `:`, `space` defined). Those chars fell back to spaces, rendering an entirely blank message.
   - Fixed: changed fallback to `"0.0.0.0"` — all characters are in the glyph table.

4. **Unused variables `sub_row` and `ci`** (`show_ip.py` lines 79-86)
   - `sub_row = row % SCALE` was calculated but never referenced. `ci` from `enumerate(text)` was also unused.
   - Fixed: removed `sub_row` line; changed `for ci, ch_char in enumerate(text):` → `for ch_char in text:`.

5. **`pull_request` trigger lacks path filters** (`.github/workflows/build-lite.yml` line 11)
   - `push` had path filters but `pull_request` did not, causing the 6-hour CI build to run on every PR regardless of changed files.
   - Fixed: added matching `paths:` filter to `pull_request` trigger.

6. **Buildroot download cache key included `github.sha`** (`.github/workflows/build-lite.yml` line 42)
   - The `${{ github.sha }}` suffix created a unique cache key per commit, preventing any cache reuse across builds and defeating the purpose of caching.
   - Fixed: removed `- ${{ github.sha }}` suffix; key is now config-hash only. `restore-keys` fallback already handled partial matches.

7. **Unquoted command substitution in `kill`** (`install_steps.sh` line 100)
   - `kill $(pidof iwd)` is subject to word splitting if `pidof` returns multiple PIDs or whitespace. ShellCheck flags this.
   - Fixed: changed to `kill "$(pidof iwd)"`.

8. **iwd startup not verified before WiFi polling** (`install_steps.sh` lines 82-83) — *logged, not implemented*
   - If `iwd` fails to start, the script waits the full ~30s and then reports a generic "WiFi did not connect" message rather than "iwd failed to start". CR suggested capturing `$!` and checking with `kill -0`.
   - Decision: skipped for now — the install context is a one-shot operation with `set -x` logging active, so the failure would be visible in the log output. Consider implementing if users report confusion.

9. **GitHub Actions not pinned to commit SHAs** (`.github/workflows/build-lite.yml` lines 21-25) — *logged, not implemented*
   - CodeRabbit flagged `actions/checkout@v4` as a supply-chain risk; recommended pinning to commit SHA. CR itself rated this a "Poor tradeoff" for OSS projects.
   - Decision: skipped — this is an open-source project and version-tag references are standard practice here. The risk/maintenance tradeoff does not justify pinning.
