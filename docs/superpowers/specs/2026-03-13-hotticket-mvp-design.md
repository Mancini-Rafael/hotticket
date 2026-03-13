# HotTicket MVP — Design Spec

**Date:** 2026-03-13
**Status:** Approved
**Python:** 3.9+
**Platform:** macOS only (MVP)

---

## Overview

HotTicket is a CLI tool that watches a plain-text TODO file for changes. When a new task line is added, it automatically prints the task description on a Niimbot B1 label printer via Bluetooth.

---

## Project Structure

```
hotticket/           # project root
├── main.py
├── watcher.py
├── differ.py
├── printer.py
├── logger.py
└── requirements.txt
```

Flat directory. All modules imported directly. No package/install step required for MVP.

---

## CLI Interface

```
# Watch a file and print new tasks
python main.py <file> --device <MAC> [--debug] [--dry-run]

# Scan for nearby Niimbot devices and list their MAC addresses
python main.py --discover
```

- `<file>`: path to the TODO file to watch
- `--device <MAC>`: Bluetooth MAC address of the Niimbot B1 (required for watch mode)
- `--discover`: scan for nearby Niimbot Bluetooth devices, print `name — address` for each, then exit 0
- `--debug`: enable verbose DEBUG-level logging
- `--dry-run`: log what would be printed instead of sending to the printer

**Argument validation:** `argparse` parses args. `main.py` performs a post-parse check: if `--discover` is not set, both `<file>` and `--device` must be present; if either is missing, print a clear usage message and exit 1.

---

## Components

### `main.py`

- Parses CLI arguments; runs post-parse validation
- If `--discover`: calls `printer.discover()`, prints results, exits 0
- Otherwise:
  1. Reads `<file>` into a `list[str]` of lines (if not found, print error and exit 1)
  2. Initializes logger via `logger.init(debug=...)`
  3. Creates `Printer(dry_run=...)`; calls `printer.connect(mac)` (on failure: log error, exit 1)
  4. Creates `Differ`; calls `differ.load(lines)` with the file's initial content
  5. Creates `Watcher(path, differ, printer)`; calls `watcher.start()`
- Registers `SIGINT` handler: calls `watcher.stop()`, `printer.close()`, exits 0
- Wraps the blocking `watcher.join()` call in `try/except Exception`: on unhandled error, logs and exits 1

### `watcher.py`

- Uses `watchdog.observers.fsevents.FSEventsObserver` (macOS-native)
- On import, checks the platform; if not macOS, raises `RuntimeError("HotTicket requires macOS")` caught in `main.py`
- Watches the parent directory of the target file; filters all events to the target filename only
- Handles two event types for the target file:
  - `FileModifiedEvent`: normal save
  - `FileCreatedEvent`: atomic-save editors (e.g., vim `:w`) delete and recreate the file; treat identically to a modification — read new content, diff against preserved snapshot (snapshot is **not** reset)
- **Debounce:** on each relevant event, cancel any pending `threading.Timer` and start a new one for 0.5s. When the timer fires, run: read file → diff → print → update snapshot.
- Watchdog's event handler runs in a single background thread. The timer callback also runs in that thread via `threading.Timer`. Snapshot reads/writes are serialized — no locking needed.
- On `FileDeletedEvent` for the target file: log warning, set `self._deleted = True`, call `observer.stop()`
- `start()`: starts the observer; `stop()`: stops the observer and cancels any pending timer; `join()`: blocks until observer stops; `was_deleted() -> bool`: returns `self._deleted`
- After `watcher.join()` returns in `main.py`, if `watcher.was_deleted()` is True → exit 0 (file gone, clean stop); otherwise the join returned due to an unhandled error → fall through to the `except` block → exit 1

### `differ.py`

- Internal state: `_snapshot: list[str]`
- `load(lines: list[str])`: stores `lines` as initial snapshot; **does not return anything to print**
- `diff(new_lines: list[str]) -> list[str]`:
  - Runs `difflib.ndiff(_snapshot, new_lines)`
  - Collects lines from the output that start with `'+ '` (added lines), strips the `'+ '` prefix
  - Filters out blank/whitespace-only results
  - Returns collected lines in order; duplicates preserved (adding the same task twice will print twice)
  - Does **not** update the snapshot (caller must call `update()`)
- `update(lines: list[str])`: replaces `_snapshot` with `lines`
- Pure logic — no file I/O, no logging; fully unit testable

### `printer.py`

**Label dimensions:**
The Niimbot B1 prints on 14mm tape at 203 DPI. Printable width = `round(14 / 25.4 * 203)` = **112px**. This value is defined as `LABEL_WIDTH_PX = 112` at module level. If the user has different label stock, they can adjust this constant.

**Class: `Printer(dry_run: bool = False)`**

- `connect(mac: str)`:
  - Creates a `niimprint.PrinterClient("bluetooth", mac)` and calls `client.heartbeat()` to verify connectivity
  - Stores client as `self._client`
  - On failure, raises `PrinterConnectionError(str(e))`

- `print_label(text: str)`:
  - If `dry_run`: logs `[DRY RUN] Would print: <text>` and returns
  - Creates a blank white monochrome `PIL.Image` (mode `"1"`)
  - Uses `PIL.ImageDraw` and `PIL.ImageFont.load_default()` for text rendering
  - **Word wrap:** iterates words, measures cumulative line width with `ImageDraw.textlength()`. When adding the next word would exceed `LABEL_WIDTH_PX`, start a new line. If a single word exceeds `LABEL_WIDTH_PX`, break it character-by-character.
  - Image height = `line_count × line_height` where `line_height` is derived from `font.getbbox("A")[3]` + 2px padding. Label height grows dynamically; no maximum.
  - Calls `self._client.print_image(image)`
  - Any exception is caught, logged, and not re-raised

- `discover() -> list[dict]`:
  - Uses `bleak.BleakScanner.discover()` to scan for nearby BLE devices for 5 seconds
  - Filters to devices whose name contains "Niimbot" (case-insensitive)
  - Returns `[{"name": str, "address": str}, ...]`

- `close()`:
  - Calls disconnect on `self._client` if connected; ignores errors

**Note on `niimprint`:** Install directly from GitHub (`pip install git+https://github.com/AndBondStyle/niimprint`). **The exact class names and method signatures must be verified against the installed library during implementation** — the library is not formally versioned and its API is not guaranteed stable. Before writing `printer.py`, run `import niimprint; help(niimprint)` and inspect the source to confirm constructor signature and print method name. Use those actual signatures, not the ones shown here as placeholders (`PrinterClient("bluetooth", mac)` and `client.print_image(image)`).

### `logger.py`

- `init(debug: bool)`: configures the root logger
  - Level: `DEBUG` if `debug=True`, else `WARNING`
  - Console handler: logs to `stderr`
  - File handler: logs to `~/.hotticket/hotticket.log` (directory created if not exists). Using a fixed path avoids surprises from CWD changes.
  - Format: `%(asctime)s [%(levelname)s] %(name)s: %(message)s`
- `get_logger(name: str) -> logging.Logger`: returns `logging.getLogger(name)`; all modules call this

---

## Data Flow

1. User runs: `python main.py tasks.txt --device AA:BB:CC:DD:EE:FF [--debug] [--dry-run]`
2. `main.py` reads file content → `list[str]` of lines (exits 1 if not found)
3. Logger initialized
4. `Printer.connect(mac)` — establishes Bluetooth session (exits 1 on failure)
5. `Differ.load(lines)` — snapshot set, nothing printed
6. `Watcher.start()` — begins watching
7. On file change event (modified or created):
   a. `threading.Timer` debounce resets to 0.5s
   b. Timer fires → read current file as `list[str]`
   c. `Differ.diff(new_lines)` → `added: list[str]`
   d. For each line in `added`: `Printer.print_label(line)` (errors logged, loop continues)
   e. `Differ.update(new_lines)` — snapshot updated regardless of print errors, to prevent re-printing on next change
8. On Ctrl+C: `Watcher.stop()`, `Printer.close()`, exit 0

---

## Error Handling

| Scenario | Behavior |
|---|---|
| File not found on startup | Exit 1 with clear message |
| `--device` not provided in watch mode | Exit 1 with usage message |
| Printer connection fails on startup | Log error, exit 1 |
| Printer unreachable during print | Log error, skip that label, continue watching |
| Print failure (niimprint/Pillow error) | Log error, continue to next line |
| File deleted while watching | Log warning, stop watcher, exit 0 |
| Empty/whitespace lines | Skip silently |
| Unhandled exception in watch loop | Log error, exit 1 |
| Ctrl+C | Clean shutdown, exit 0 |
| Non-macOS platform | Exit 1 with "macOS only" message |

---

## Testing

- **`differ.py`**: unit tests — line appended, line inserted in middle, line deleted (not printed), line edited (not printed), blank line added (skipped), no change, duplicate line added (prints again), multiple lines added at once
- **`printer.py`**: `--dry-run` enables full pipeline testing without hardware; Pillow rendering tested by asserting output `Image` width = 112 and height > 0
- **`--discover`**: manual test (requires BLE hardware)
- **Watcher / debounce**: manual testing

---

## Dependencies

```
watchdog
niimprint   # install from GitHub: pip install git+https://github.com/AndBondStyle/niimprint
Pillow>=9.2.0  # required for ImageDraw.textlength()
bleak
```

Pin all to exact versions in `requirements.txt` after initial install (`pip freeze`).

---

## Out of Scope (MVP)

- Daemon / autostart on login
- Task deletion or edit detection (edits silently ignored)
- Label formatting (custom fonts, borders, QR codes)
- Multiple file watching
- Remote / network printer support
- Config file for storing device MAC
- Linux / Windows support
