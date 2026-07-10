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

**Review:** CodeRabbit flagged 9 findings across 3 files.
**Result:** 8 fixed (findings 1–8); 1 nitpick logged and skipped (finding 9 — SHA pinning not worthwhile for OSS).

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

8. **iwd startup not verified before WiFi polling** (`install_steps.sh` lines 82-83)
   - If `iwd` fails to start, the script waits the full ~30s and then reports a generic "WiFi did not connect" message rather than "iwd failed to start". CR suggested capturing `$!` and checking with `kill -0`.
   - Fixed: implemented `IWD_PID=$!` capture and `kill -0 $IWD_PID` check after `sleep 8`.

9. **GitHub Actions not pinned to commit SHAs** (`.github/workflows/build-lite.yml` lines 21-25) — *logged, not implemented*
   - CodeRabbit flagged `actions/checkout@v4` as a supply-chain risk; recommended pinning to commit SHA. CR itself rated this a "Poor tradeoff" for OSS projects.
   - Decision: skipped — this is an open-source project and version-tag references are standard practice here. The risk/maintenance tradeoff does not justify pinning.

## 2026-07-10 — PR #38 `build-lite.yml`, `.claude/CLAUDE.md` (CR follow-up: artifact name drift + pagination)

**Review:** CR flagged 4 issues across 2 files in subsequent review runs.
**Result:** 2 fixed; 2 logged (CLAUDE.md edit requires user authorization per system policy).

### Findings

1. **Artifact name hardcoded in JS script** (`.github/workflows/build-lite.yml` line 156)
   - `artifactName` was rebuilt in JavaScript from PR number + SHA rather than reading `steps.artifact.outputs.name`. A future rename of the upload step's naming pattern would desync the posted comment from the actual artifact.
   - Fixed: added `env: ARTIFACT_NAME: ${{ steps.artifact.outputs.name }}` and changed JS to `process.env.ARTIFACT_NAME`.

2. **`listComments` only fetches first page** (`.github/workflows/build-lite.yml` lines 167-171)
   - The default `github.rest.issues.listComments` call returns page 1 only (~30 comments). On a PR with many comments the marker check could miss an existing bot comment and post a duplicate.
   - Fixed: replaced with `github.paginate(github.rest.issues.listComments, ...)` to retrieve all pages before searching for the marker.

3. **Code fence missing language tag** (`.claude/CLAUDE.md` line 61) — *logged, requires user action*
   - The commit-message format example fence has no language identifier, causing markdownlint to warn. Should be ` ```text `.
   - Blocked: self-modification policy prevents editing `.claude/CLAUDE.md` without explicit user authorization.

4. **Outdated CI statement** (`.claude/CLAUDE.md` line 99) — *fixed by user*
   - "This project has no automated CI build pipeline" was false; PR #38 added `build-lite.yml`.
   - Fixed by user after self-modification policy blocked the automated edit.

## 2026-07-10 — PR #38 `show_ip.c`, `gen_wifi_data.py` (CR review: C binary safety + assertion)

**Review:** CodeRabbit flagged 4 actionable issues and 1 S&P housekeeping note.
**Result:** All 5 fixed.

### Findings

1. **`fscanf` return values unchecked in `fb_init`** (`show_ip.c` lines 77-88)
   - Both `fscanf` calls (virtual_size and bits_per_pixel) discarded their return values. A parse failure would leave `fb_w`/`fb_h`/`fb_bpp` uninitialised, causing silent garbage output or a divide-by-zero in `fb_stride`.
   - Fixed: wrapped each call — `if (fscanf(...) != N) { fclose(f); return -1; }`.

2. **Stack buffer overflow in `draw_text`** (`show_ip.c` lines 135-166)
   - `line[15 * 8 * SCALE * 4]` holds exactly 15 chars, but `len = strlen(text)` was used unclamped. A string longer than 15 would overflow.
   - Fixed: `if (len > 15) len = 15;` immediately after the `strlen` call.

3. **Stack buffer overflow in `fill_row`** (`show_ip.c` lines 107-117)
   - `buf[800 * 4]` assumes `n ≤ 800`, but callers pass `fb_w` which could exceed 800 on a wider display. No bounds check existed.
   - Fixed: `if (n > 800) n = 800;` after declaring the buffer.

4. **`assert` disabled by `-O` in `gen_wifi_data.py`** (`gen_wifi_data.py` lines 35-40)
   - `assert img.size == (SIZE, SIZE)` is silently skipped when Python is run with optimisation flags, letting a wrong-size PNG produce corrupt icon data with no error.
   - Fixed: replaced with `if img.size != (SIZE, SIZE): raise ValueError(...)`.

5. **S&P finding-count summary incorrect** (`.claude/S&P.md` lines 21-22)
   - Entry claimed "5 actionable issues and 4 nitpicks" but listed 9 findings without distinguishing fixed/skipped status.
   - Fixed: updated summary to "9 findings: 8 fixed, 1 skipped (SHA pinning)".
