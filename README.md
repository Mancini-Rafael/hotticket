# HotTicket

Watch a plain-text todo file and print each new line on a **Niimbot B1** label printer over Bluetooth — as soon as you save the file.

Add a line to your file → label prints within half a second.

---

## Requirements

- macOS (uses FSEvents for file watching)
- Python 3.11+
- [blueutil](https://github.com/toy/blueutil) — `brew install blueutil`
- Niimbot B1 printer, paired via macOS Bluetooth settings at least once

---

## Setup

```sh
git clone <this repo>
cd hotticket
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Usage

### Auto-connect (recommended)

Scans for paired Niimbot devices and lets you pick one interactively:

```sh
python main.py tasks.txt --connect
```

On first run (and every subsequent run) macOS will prompt for a pairing code — this is intentional. The device is unpaired on exit to ensure a clean RFCOMM channel on the next session.

### Manual device

If you already know the serial port:

```sh
python main.py tasks.txt --device /dev/cu.B1-XXXXXXXXXX
```

### Discover devices

```sh
python main.py --discover
```

### All options

| Flag | Description |
|------|-------------|
| `--connect` | Auto-discover and connect to the first Niimbot found |
| `--device PORT` | Serial port path (e.g. `/dev/cu.B1-XXXXXXXXXX`) |
| `--discover` | Scan for nearby Niimbot devices and show connect commands |
| `--density 1-5` | Print density, 1 (lightest) to 5 (darkest). Default: 3 |
| `--dry-run` | Log labels instead of printing (no printer needed) |
| `--debug` | Enable verbose debug logging |

---

## Typical workflow

```sh
source .venv/bin/activate
python main.py tasks.txt --connect
# → select your printer when prompted
# → enter the pairing code when macOS asks
# → add lines to tasks.txt and save — each new line prints immediately
# → Ctrl+C to stop (device is unpaired automatically)
```

---

## How it works

1. On start, the current file contents are loaded as a baseline (nothing is printed)
2. FSEvents watches the file for changes with a 500ms debounce
3. On each save, a diff finds lines added since the last snapshot
4. Each new line is rendered as a centered monochrome bitmap and sent to the printer via serial

Blank lines, edits to existing lines, and deletions are all ignored.

---

## Label configuration

Paper size and font are set at the top of `printer.py`:

```python
DPI             = 203
PAPER_WIDTH_MM  = 30   # change to match your label stock
PAPER_HEIGHT_MM = 20
FONT_SIZE       = 24   # pixels
```

Text is automatically centered (horizontally and vertically) within the paper bounds and word-wrapped to fit the width.

---

## Project structure

```
main.py       — CLI entry point, argument parsing, Bluetooth connect/disconnect flow
printer.py    — Label rendering (Pillow), Bluetooth helpers (blueutil), niimprint wrapper
watcher.py    — FSEvents file watcher with debounce
differ.py     — Snapshot diff to detect newly added lines
logger.py     — Logging setup
```
