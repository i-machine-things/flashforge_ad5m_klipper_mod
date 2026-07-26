# Coding Best Practices & Reminders

> **Style rule:** Notes must be clear and concise — 300 characters or less each. Group by topic, not by date. Whenever a PR review (CodeRabbit or human) catches a mistake, add or amend a note here right away so it isn't repeated.

## Resource Cleanup & Temporary Files

**Close sockets in try/finally.** In retry loops (e.g. `get_ip()`), wrap socket ops in try/finally so `s.close()` always runs even if `connect()`/`getsockname()` raises — otherwise failed attempts leak file descriptors.

**IMPORTANT**: Always add proper cleanup code in programs to prevent lingering temp files after closing.

### Best Practices:

1. **GUI Applications (PyQt, Tkinter, etc.)**
   - Implement `closeEvent()` handler to cleanup resources on window close
   - Call `deleteLater()` on widgets to ensure proper Qt object cleanup
   - Process pending events with `app.processEvents()` before exit

2. **File Handling**
   - Use context managers (`with` statements) for file operations
   - Explicitly close file handles when not using context managers
   - Release file locks before program exit
   - Clean up temporary files in temp directories

3. **Background Threads & Workers**
   - Stop and join all background threads before exit
   - Cancel any pending operations
   - Clean up thread-specific resources

4. **Testing Cleanup**
   - After closing the program, verify the executable can be:
     - Deleted immediately
     - Moved to another location
     - Replaced with a new version
   - If the file is locked, cleanup code is missing or incomplete

### Example Implementation (PyQt6):

```python
def closeEvent(self, event):
    """Handle window close event - ensure proper cleanup"""
    # Cleanup modules/components
    for module in self.modules:
        try:
            module.cleanup()
        except Exception as e:
            print(f"Error cleaning up module: {e}")

    # Save state
    self.save_settings()

    # Accept close event
    event.accept()
    QApplication.quit()

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()

    exit_code = app.exec()

    # Final cleanup
    window.deleteLater()
    app.processEvents()

    sys.exit(exit_code)
```

### PyInstaller Specific:

In `.spec` file, add:
```python
exe = EXE(
    ...
    bootloader_ignore_signals=True,  # Better cleanup handling
    ...
)
```

## Date: 2025-12-16
This note was created based on issues encountered with PyInstaller executables remaining locked after closing.

## Input Validation & Fail-Fast Checks

**Validate enum-like parameters explicitly.** Functions like `encode_pixel(bpp)` should raise `ValueError` for unsupported values instead of silently falling through to a default path, which can corrupt output.

**Don't rely on `assert` for runtime checks.** `assert img.size == (SIZE, SIZE)` is stripped when Python runs with `-O`. Use `if cond: raise ValueError(...)` for checks that must always run.

**Match fallback strings to available glyph/char sets.** A text fallback (e.g. "No network") must only use characters present in the rendering table, or it silently renders blank.

## C Buffer Safety

**Check `fscanf` return values.** Unchecked `fscanf` calls can leave output variables uninitialized on parse failure, causing garbage output or a divide-by-zero later.

**Clamp lengths before fixed-size buffer writes.** `draw_text`/`fill_row`-style functions must clamp `len`/`n` to the buffer's actual capacity before writing — don't assume caller-provided sizes are in bounds.

## Shell Scripting

**Quote command substitutions.** `kill $(pidof proc)` is subject to word splitting; use `kill "$(pidof proc)"`.

**Verify background daemons actually started.** After launching a service in the background (e.g. `iwd &`), capture `$!` and check with `kill -0 $PID` rather than assuming success and waiting out a fixed timeout.

## CI/CD Workflows

**Apply the same path filters to `push` and `pull_request` triggers.** Missing filters on one trigger causes expensive builds (e.g. multi-hour buildroot builds) to run on every PR regardless of changed files.

**Don't include commit SHA in cache keys meant for reuse.** A per-commit key defeats caching entirely; key on config hash instead and rely on `restore-keys` for partial matches.

**Read generated names from step outputs, not by reconstructing them.** Rebuilding a name (e.g. an artifact name from PR number + SHA) in a later step can drift from the actual value; read `steps.<id>.outputs.<name>` instead.

**Paginate GitHub API list calls before searching results.** `listComments` and similar default to one page (~30 items); use `github.paginate(...)` so marker/dedup checks see all comments, not just the first page.

**Actions pinned by version tag, not SHA — intentional for this OSS project.** The maintenance overhead of SHA-pinning was judged not worth the marginal supply-chain benefit here; don't re-flag this as a finding.

## Documentation Hygiene

**Tag code fences with a language.** A fenced code block without a language identifier (plain ``` instead of ```text) triggers markdownlint warnings.

**Keep CLAUDE.md's CI/process claims in sync with reality.** Statements like "no automated CI pipeline" go stale the moment CI is added — update process docs in the same PR that changes the process.
