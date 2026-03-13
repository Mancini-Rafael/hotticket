# HotTicket MVP — Design Spec

**Date:** 2026-03-13
**Status:** Approved

---

## Overview

HotTicket is a CLI tool that watches a plain-text TODO file for changes. When a new task line is added, it automatically prints the task description on a Niimbot B1 label printer via Bluetooth.

---

## Architecture

```
hotticket/
├── main.py          # CLI entry point: python main.py <file> [--debug] [--dry-run]
├── watcher.py       # watchdog-based file watcher
├── differ.py        # snapshot diff → extract new lines
├── printer.py       # Bluetooth connection + print via niimprint
├── logger.py        # structured logging (file + console, debug flag)
└── requirements.txt
```

Each module has a single responsibility and communicates through well-defined interfaces.

---

## Components

### `main.py`
- Parses CLI arguments: `<file>`, `--debug`, `--dry-run`
- Validates that the target file exists (exits with a clear message if not)
- Initializes the logger, printer, and watcher
- Wires components together and starts the watch loop

### `watcher.py`
- Uses the `watchdog` library to listen for OS-native file modification events (FSEvents on macOS)
- On each event, reads the current file content and passes it to the differ
- Handles file deletion gracefully (logs warning, stops cleanly)

### `differ.py`
- Maintains an in-memory snapshot of the last known file lines
- On each change, computes a unified diff against the new content
- Returns only genuinely added lines (ignores edits and deletions)
- Skips blank or whitespace-only lines
- Pure logic module — fully unit testable without I/O

### `printer.py`
- Wraps the `niimprint` library for Bluetooth communication with the Niimbot B1
- Exposes a single `print_label(text: str)` method
- In `--dry-run` mode, logs the label content instead of printing
- Handles connection errors without crashing the watcher loop

### `logger.py`
- Thin wrapper around Python's `logging` module
- Outputs to both console and a log file (`hotticket.log`)
- Debug mode (enabled via `--debug`) logs each step verbosely
- Normal mode logs only warnings and errors

---

## Data Flow

1. User runs: `python main.py tasks.txt [--debug] [--dry-run]`
2. File is read into memory as the initial snapshot
3. `watchdog` watches the file for modification events
4. On change: diff new content against snapshot → extract added lines
5. Skip empty/whitespace-only lines
6. For each new line: send to printer via Bluetooth (or log if `--dry-run`)
7. Update snapshot to new content
8. Repeat from step 3

---

## Error Handling

| Scenario | Behavior |
|---|---|
| File not found on startup | Exit with clear error message |
| Printer not found / Bluetooth unavailable | Log error, skip print, keep watching |
| File deleted while watching | Log warning, stop gracefully |
| Empty or whitespace-only lines | Skip silently |
| Print failure | Log error, continue watching |

---

## Testing

- **`differ.py`**: Unit tests covering add, edit, delete, blank line cases — pure logic, no I/O
- **End-to-end**: `--dry-run` flag enables full pipeline testing without hardware
- **File watcher**: Manual testing (watchdog integration is not worth unit testing for MVP)

---

## Dependencies

- [`watchdog`](https://github.com/gorakhargosh/watchdog) — cross-platform file system events
- [`niimprint`](https://github.com/AndBondStyle/niimprint) — Niimbot printer Bluetooth communication

---

## Out of Scope (MVP)

- Daemon / autostart on login
- Task deletion or edit detection
- Label formatting (font size, borders, QR codes)
- Multiple file watching
- Remote/network printer support
