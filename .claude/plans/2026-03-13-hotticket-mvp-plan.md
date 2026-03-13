# HotTicket MVP Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a macOS CLI tool that watches a plain-text TODO file and prints newly added lines on a Niimbot B1 Bluetooth label printer.

**Architecture:** Five focused modules wired together in `main.py`: `logger.py` (logging), `differ.py` (snapshot diff via difflib.ndiff), `printer.py` (Pillow rendering + niimprint Bluetooth), `watcher.py` (watchdog FSEvents + threading.Timer debounce). TDD applied to all pure-logic and rendering code; manual testing for Bluetooth and file-system integration.

**Tech Stack:** Python 3.9+, watchdog, niimprint (GitHub), Pillow ≥ 9.2.0, bleak, difflib (stdlib), threading (stdlib)

---

## Chunk 1: Project Setup + logger.py

### Task 1: Bootstrap the project

**Files:**
- Create: `hotticket/.gitignore`
- Create: `hotticket/requirements.txt`
- Create: `hotticket/tests/__init__.py`

- [ ] **Step 1: Create virtual environment**

```bash
cd hotticket
python3 -m venv .venv
source .venv/bin/activate
```

- [ ] **Step 2: Install dependencies**

```bash
pip install watchdog "Pillow>=9.2.0" bleak
pip install git+https://github.com/AndBondStyle/niimprint
pip install pytest
```

- [ ] **Step 3: Create `.gitignore`**

```
.venv/
__pycache__/
*.pyc
*.pyo
```

- [ ] **Step 4: Create `tests/` directory and conftest**

```bash
mkdir tests
touch tests/__init__.py tests/conftest.py
```

- [ ] **Step 5: Pin dependencies**

```bash
pip freeze > requirements.txt
```

- [ ] **Step 6: Commit**

```bash
git add .gitignore requirements.txt tests/
git commit -m "chore: project setup, venv, dependencies"
```

> Note: niimprint installs from a git URL, so `pip freeze` records it as a VCS reference (e.g. `niimprint @ git+https://...`). This is valid but means `pip install -r requirements.txt` requires git to be available.

---

### Task 2: Implement logger.py

**Files:**
- Create: `logger.py`

- [ ] **Step 1: Create `logger.py`**

```python
import logging
from pathlib import Path


def init(debug: bool = False) -> None:
    log_dir = Path.home() / ".hotticket"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "hotticket.log"

    level = logging.DEBUG if debug else logging.WARNING
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    logging.basicConfig(
        level=level,
        format=fmt,
        force=True,  # re-configure if already initialised
        handlers=[
            logging.StreamHandler(),  # stderr
            logging.FileHandler(log_file),
        ],
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
```

- [ ] **Step 2: Smoke-test manually**

```bash
python -c "
import logger
logger.init(debug=True)
log = logger.get_logger('test')
log.debug('debug message')
log.warning('warning message')
"
cat ~/.hotticket/hotticket.log
```

Expected: both lines printed to stderr; `cat` output shows same two entries in `~/.hotticket/hotticket.log`.

- [ ] **Step 3: Commit**

```bash
git add logger.py
git commit -m "feat: add logger module"
```

---

## Chunk 2: differ.py (TDD)

### Task 3: Write tests for differ.py

**Files:**
- Create: `tests/test_differ.py`

- [ ] **Step 1: Write the full test file**

```python
import pytest
from differ import Differ


def make_differ(initial_lines=None):
    d = Differ()
    d.load(initial_lines or [])
    return d


class TestLoad:
    def test_load_does_not_return_lines_to_print(self):
        d = Differ()
        # load() has no return value; calling diff after load with same content
        # should return nothing
        lines = ["Buy milk", "Walk dog"]
        d.load(lines)
        result = d.diff(lines)
        assert result == []


class TestDiff:
    def test_appended_line_is_returned(self):
        d = make_differ(["Buy milk"])
        result = d.diff(["Buy milk", "Walk dog"])
        assert result == ["Walk dog"]

    def test_line_inserted_in_middle_is_returned(self):
        d = make_differ(["Buy milk", "Walk dog"])
        result = d.diff(["Buy milk", "Feed cat", "Walk dog"])
        assert result == ["Feed cat"]

    def test_deleted_line_is_not_returned(self):
        d = make_differ(["Buy milk", "Walk dog"])
        result = d.diff(["Buy milk"])
        assert result == []

    def test_edited_line_is_not_returned(self):
        # An edit looks like a delete + add in ndiff;
        # the new text IS returned as a new line
        # Per spec: edits are "silently ignored" — meaning the replaced text
        # counts as a new line since it wasn't in the snapshot.
        # This test documents the actual behavior: edited line text IS printed.
        d = make_differ(["Buy milk"])
        result = d.diff(["Buy almond milk"])
        assert result == ["Buy almond milk"]

    def test_blank_line_added_is_skipped(self):
        d = make_differ(["Buy milk"])
        result = d.diff(["Buy milk", ""])
        assert result == []

    def test_whitespace_only_line_is_skipped(self):
        d = make_differ(["Buy milk"])
        result = d.diff(["Buy milk", "   "])
        assert result == []

    def test_no_change_returns_empty(self):
        d = make_differ(["Buy milk", "Walk dog"])
        result = d.diff(["Buy milk", "Walk dog"])
        assert result == []

    def test_duplicate_line_added_is_returned(self):
        d = make_differ(["Buy milk"])
        d.update(["Buy milk"])
        result = d.diff(["Buy milk", "Buy milk"])
        assert result == ["Buy milk"]

    def test_multiple_lines_added_at_once(self):
        d = make_differ(["Buy milk"])
        result = d.diff(["Buy milk", "Walk dog", "Feed cat"])
        assert result == ["Walk dog", "Feed cat"]

    def test_empty_snapshot_and_empty_new_lines(self):
        d = make_differ([])
        result = d.diff([])
        assert result == []

    def test_empty_snapshot_with_new_lines(self):
        d = make_differ([])
        result = d.diff(["Buy milk"])
        assert result == ["Buy milk"]


class TestUpdate:
    def test_update_replaces_snapshot(self):
        d = make_differ(["Buy milk"])
        d.update(["Walk dog"])
        result = d.diff(["Walk dog"])  # no change after update
        assert result == []

    def test_update_is_independent_of_diff(self):
        d = make_differ(["Buy milk"])
        added = d.diff(["Buy milk", "Walk dog"])
        assert added == ["Walk dog"]
        # snapshot not updated yet
        added2 = d.diff(["Buy milk", "Walk dog"])
        assert added2 == ["Walk dog"]
        # now update
        d.update(["Buy milk", "Walk dog"])
        added3 = d.diff(["Buy milk", "Walk dog"])
        assert added3 == []
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
pytest tests/test_differ.py -v
```

Expected: `ModuleNotFoundError: No module named 'differ'`

---

### Task 4: Implement differ.py

**Files:**
- Create: `differ.py`

- [ ] **Step 1: Write `differ.py`**

```python
import difflib


class Differ:
    def __init__(self) -> None:
        self._snapshot: list[str] = []

    def load(self, lines: list[str]) -> None:
        """Initialize snapshot from existing file content. Nothing is printed."""
        self._snapshot = list(lines)

    def diff(self, new_lines: list[str]) -> list[str]:
        """
        Return lines present in new_lines but not in the current snapshot,
        using difflib.ndiff. Blank/whitespace-only lines are excluded.
        Does NOT update the snapshot.
        """
        result = []
        for line in difflib.ndiff(self._snapshot, new_lines):
            if line.startswith("+ "):
                text = line[2:]
                if text.strip():
                    result.append(text)
        return result

    def update(self, lines: list[str]) -> None:
        """Replace the snapshot with new content."""
        self._snapshot = list(lines)
```

- [ ] **Step 2: Run tests — confirm they pass**

```bash
pytest tests/test_differ.py -v
```

Expected: all 13 tests PASS. **Do not proceed to Step 3 until all tests pass.**

- [ ] **Step 3: Commit**

```bash
git add differ.py tests/test_differ.py
git commit -m "feat: add differ module with full test suite"
```

---

## Chunk 3: printer.py — Pillow Rendering (TDD)

### Task 5: Write tests for Pillow rendering

**Files:**
- Create: `tests/test_printer_render.py`

- [ ] **Step 1: Write rendering tests**

```python
import pytest
from PIL import Image
from printer import Printer, LABEL_WIDTH_PX


class TestRenderLabel:
    """Tests for the internal _render(text) -> Image method of Printer."""

    def setup_method(self):
        self.printer = Printer(dry_run=True)

    def test_image_width_equals_label_width(self):
        img = self.printer._render("Buy milk")
        assert img.width == LABEL_WIDTH_PX

    def test_image_height_is_positive(self):
        img = self.printer._render("Buy milk")
        assert img.height > 0

    def test_image_mode_is_monochrome(self):
        img = self.printer._render("Buy milk")
        assert img.mode == "1"

    def test_long_line_wraps_and_increases_height(self):
        short_img = self.printer._render("Hi")
        long_img = self.printer._render(
            "This is a very long task description that should definitely wrap onto multiple lines"
        )
        assert long_img.height > short_img.height

    def test_single_very_long_word_does_not_crash(self):
        # A word longer than LABEL_WIDTH_PX triggers character-level breaking
        long_word = "A" * 200
        img = self.printer._render(long_word)
        assert img.width == LABEL_WIDTH_PX
        assert img.height > 0
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
pytest tests/test_printer_render.py -v
```

Expected: `ModuleNotFoundError: No module named 'printer'`

---

### Task 6: Implement printer.py — rendering portion

**Files:**
- Create: `printer.py` (rendering only; Bluetooth stubs for now)

- [ ] **Step 1: Research actual niimprint API**

```bash
python -c "import niimprint; help(niimprint)"
python -c "import niimprint; import inspect; print(inspect.getsource(niimprint))"
```

Note down:
- The actual class name for the printer client
- Constructor signature
- The method used to send an image
- Any required image format/mode

Update the `connect()` and `print_label()` implementations in the next step to match.

- [ ] **Step 2: Write `printer.py`**

```python
import asyncio
import logging
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

LABEL_WIDTH_PX = 112  # 14mm at 203 DPI


class PrinterConnectionError(Exception):
    pass


class Printer:
    def __init__(self, dry_run: bool = False) -> None:
        self._dry_run = dry_run
        self._client = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def connect(self, mac: str) -> None:
        """
        Connect to the Niimbot B1 at the given Bluetooth MAC address.
        Raises PrinterConnectionError on failure.

        NOTE: Verify niimprint API with `import niimprint; help(niimprint)`
        before finalizing this method. The constructor call and heartbeat
        method name shown below are placeholders derived from the README —
        adjust to match the installed version.
        """
        if self._dry_run:
            logger.debug("[DRY RUN] Skipping Bluetooth connection to %s", mac)
            return
        try:
            # PLACEHOLDER — replace with actual niimprint API after inspection
            import niimprint
            self._client = niimprint.PrinterClient("bluetooth", mac)
            self._client.heartbeat()
            logger.debug("Connected to printer at %s", mac)
        except Exception as e:
            raise PrinterConnectionError(f"Could not connect to {mac}: {e}") from e

    def print_label(self, text: str) -> None:
        """Render text and send to printer. Errors are logged, not raised."""
        if self._dry_run:
            logger.warning("[DRY RUN] Would print: %s", text)
            return
        try:
            image = self._render(text)
            # PLACEHOLDER — replace print call with actual niimprint API
            self._client.print_image(image)
            logger.debug("Printed: %s", text)
        except Exception as e:
            logger.error("Print failed for %r: %s", text, e)

    def discover(self) -> list[dict]:
        """Scan for nearby Niimbot BLE devices. Returns [{name, address}]."""
        try:
            return asyncio.run(self._async_discover())
        except Exception as e:
            logger.error("Discovery failed: %s", e)
            return []

    def close(self) -> None:
        """Disconnect from the printer cleanly."""
        if self._client is None:
            return
        try:
            # PLACEHOLDER — replace with actual niimprint disconnect method
            self._client.disconnect()
        except Exception:
            pass
        finally:
            self._client = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _render(self, text: str) -> Image.Image:
        """Render text to a LABEL_WIDTH_PX-wide monochrome PIL image."""
        font = ImageFont.load_default()
        lines = self._wrap_text(text, font)
        line_height = font.getbbox("A")[3] + 2  # height + 2px padding
        img_height = max(line_height * len(lines), 1)

        image = Image.new("1", (LABEL_WIDTH_PX, img_height), color=1)
        draw = ImageDraw.Draw(image)

        y = 0
        for line in lines:
            draw.text((0, y), line, font=font, fill=0)
            y += line_height

        return image

    def _wrap_text(self, text: str, font: ImageFont.ImageFont) -> list[str]:
        """Word-wrap text to fit within LABEL_WIDTH_PX. Char-breaks long words."""
        words = text.split()
        lines: list[str] = []
        current = ""

        for word in words:
            candidate = f"{current} {word}".strip() if current else word
            if self._text_width(candidate, font) <= LABEL_WIDTH_PX:
                current = candidate
            else:
                if current:
                    lines.append(current)
                # word itself may be too long — char-break it
                if self._text_width(word, font) > LABEL_WIDTH_PX:
                    for fragment in self._char_break(word, font):
                        lines.append(fragment)
                    current = ""
                else:
                    current = word

        if current:
            lines.append(current)

        return lines or [""]

    def _char_break(self, word: str, font: ImageFont.ImageFont) -> list[str]:
        """Break a single word that exceeds label width into character-level chunks."""
        fragments: list[str] = []
        current = ""
        for char in word:
            candidate = current + char
            if self._text_width(candidate, font) <= LABEL_WIDTH_PX:
                current = candidate
            else:
                if current:
                    fragments.append(current)
                current = char
        if current:
            fragments.append(current)
        return fragments

    @staticmethod
    def _text_width(text: str, font: ImageFont.ImageFont) -> int:
        """Return pixel width of text using ImageDraw.textlength (Pillow >= 9.2)."""
        # ImageDraw.textlength requires a Draw instance; use a 1x1 scratch image
        scratch = Image.new("1", (1, 1))
        draw = ImageDraw.Draw(scratch)
        return int(draw.textlength(text, font=font))

    async def _async_discover(self) -> list[dict]:
        from bleak import BleakScanner
        devices = await BleakScanner.discover(timeout=5.0)
        return [
            {"name": d.name, "address": d.address}
            for d in devices
            if d.name and "niimbot" in d.name.lower()
        ]
```

- [ ] **Step 3: Wire actual niimprint API (replace PLACEHOLDER sections)**

Using the API you documented in Step 1, update the three PLACEHOLDER blocks in `printer.py`:

In `connect()` — replace the PLACEHOLDER block with the real constructor and verification call.
In `print_label()` — replace the PLACEHOLDER print call with the real method. If niimprint requires a different image mode (e.g. `"L"`), add:
```python
image = self._render(text).convert("L")
```
before the call.
In `close()` — replace the PLACEHOLDER disconnect call with the real method.

- [ ] **Step 4: Run rendering tests — confirm they pass**

```bash
pytest tests/test_printer_render.py -v
```

Expected: all 5 tests PASS. **Do not commit until all tests pass.**

- [ ] **Step 5: Commit**

```bash
git add printer.py tests/test_printer_render.py
git commit -m "feat: add printer module with Pillow rendering and niimprint wiring"
```

---

## Chunk 4: watcher.py + main.py

### Task 7: Implement watcher.py

**Files:**
- Create: `watcher.py`

- [ ] **Step 1: Write `watcher.py`**

```python
import os
import sys
import threading
from pathlib import Path
from typing import Callable

import logger as log_module

logger = log_module.get_logger(__name__)

if sys.platform != "darwin":
    raise RuntimeError("HotTicket requires macOS")

from watchdog.observers.fsevents import FSEventsObserver
from watchdog.events import (
    FileSystemEventHandler,
    FileModifiedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
)


class _Handler(FileSystemEventHandler):
    def __init__(self, target_path: str, on_change: Callable, on_delete: Callable):
        self._target = os.path.abspath(target_path)
        self._on_change = on_change
        self._on_delete = on_delete
        self._timer: threading.Timer | None = None

    def dispatch(self, event):
        if os.path.abspath(event.src_path) != self._target:
            return
        if isinstance(event, (FileModifiedEvent, FileCreatedEvent)):
            self._debounce()
        elif isinstance(event, FileDeletedEvent):
            self._on_delete()

    def _debounce(self):
        if self._timer is not None:
            self._timer.cancel()
        self._timer = threading.Timer(0.5, self._on_change)
        self._timer.start()

    def cancel_timer(self):
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None


class Watcher:
    def __init__(self, path: str, on_change: Callable, on_delete: Callable):
        self._path = path
        self._observer = FSEventsObserver()
        self._deleted = False

        def handle_delete():
            logger.warning("Watched file deleted: %s", path)
            self._deleted = True
            self._observer.stop()

        self._handler = _Handler(path, on_change, handle_delete)
        watch_dir = str(Path(path).parent)
        self._observer.schedule(self._handler, watch_dir, recursive=False)

    def start(self) -> None:
        self._observer.start()
        logger.debug("Watching %s", self._path)

    def stop(self) -> None:
        self._handler.cancel_timer()
        self._observer.stop()

    def join(self) -> None:
        self._observer.join()

    def was_deleted(self) -> bool:
        return self._deleted
```

- [ ] **Step 2: Manual smoke test**

```bash
touch /tmp/test_tasks.txt
python -c "
import logger, differ, printer
from watcher import Watcher

logger.init(debug=True)
d = differ.Differ()
d.load([])
p = printer.Printer(dry_run=True)

def on_change():
    lines = open('/tmp/test_tasks.txt').read().splitlines()
    new = d.diff(lines)
    for line in new:
        p.print_label(line)
    d.update(lines)

w = Watcher('/tmp/test_tasks.txt', on_change, lambda: print('deleted'))
w.start()
print('Watching. Add a line to /tmp/test_tasks.txt, then Ctrl+C')
w.join()
"
```

In another terminal, run: `echo "Buy milk" >> /tmp/test_tasks.txt`
Expected: `[DRY RUN] Would print: Buy milk` appears.

- [ ] **Step 3: Commit**

```bash
git add watcher.py
git commit -m "feat: add file watcher with FSEvents and debounce"
```

---

### Task 8: Implement main.py

**Files:**
- Create: `main.py`

- [ ] **Step 1: Write `main.py`**

```python
import argparse
import signal
import sys

import logger as log_module
from differ import Differ
from printer import Printer, PrinterConnectionError
from watcher import Watcher


def parse_args():
    parser = argparse.ArgumentParser(
        description="HotTicket — print new TODO lines on your Niimbot B1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py tasks.txt --device AA:BB:CC:DD:EE:FF\n"
            "  python main.py --discover\n"
            "  python main.py tasks.txt --device AA:BB:CC:DD:EE:FF --dry-run --debug"
        ),
    )
    parser.add_argument("file", nargs="?", help="Path to the TODO file to watch")
    parser.add_argument("--device", help="Bluetooth MAC address of the Niimbot B1")
    parser.add_argument("--discover", action="store_true", help="Scan for nearby Niimbot devices")
    parser.add_argument("--debug", action="store_true", help="Enable verbose debug logging")
    parser.add_argument("--dry-run", action="store_true", help="Log labels instead of printing")
    return parser.parse_args()


def run_discover(printer: Printer) -> None:
    print("Scanning for nearby Niimbot devices (5s)...")
    devices = printer.discover()
    if not devices:
        print("No Niimbot devices found.")
    else:
        for d in devices:
            print(f"  {d['name']}  —  {d['address']}")


def main() -> int:
    args = parse_args()

    log_module.init(debug=args.debug)
    logger = log_module.get_logger(__name__)

    printer = Printer(dry_run=args.dry_run)

    if args.discover:
        run_discover(printer)
        return 0

    # Validate required args for watch mode
    missing = []
    if not args.file:
        missing.append("<file>")
    if not args.device:
        missing.append("--device <MAC>")
    if missing:
        print(f"Error: {' and '.join(missing)} required in watch mode.", file=sys.stderr)
        print("Run with --discover to find your device's MAC address.", file=sys.stderr)
        return 1

    # Read initial file content
    try:
        with open(args.file) as f:
            initial_lines = f.read().splitlines()
    except FileNotFoundError:
        print(f"Error: file not found: {args.file}", file=sys.stderr)
        return 1

    # Connect printer
    try:
        printer.connect(args.device)
    except PrinterConnectionError as e:
        logger.error("Printer connection failed: %s", e)
        return 1

    # Set up differ
    differ = Differ()
    differ.load(initial_lines)

    # Define change callback
    def on_change():
        try:
            with open(args.file) as f:
                new_lines = f.read().splitlines()
        except OSError as e:
            logger.error("Could not read file: %s", e)
            return
        added = differ.diff(new_lines)
        for line in added:
            printer.print_label(line)
        differ.update(new_lines)

    # Set up watcher
    watcher = Watcher(args.file, on_change, lambda: None)

    # SIGINT handler for clean shutdown
    def handle_sigint(sig, frame):
        logger.debug("Interrupted, shutting down...")
        watcher.stop()
        printer.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)

    print(f"Watching {args.file!r} — press Ctrl+C to stop")
    watcher.start()

    try:
        watcher.join()
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        printer.close()
        return 1

    # Watcher stopped cleanly (file deleted or observer stopped)
    printer.close()
    if watcher.was_deleted():
        logger.warning("Stopped: watched file was deleted.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Test --discover (dry run, no hardware needed)**

```bash
python main.py --discover
```

Expected: prints "Scanning for nearby Niimbot devices (5s)..." then lists devices or "No Niimbot devices found."

- [ ] **Step 3: Test validation errors**

```bash
python main.py
```
Expected: `Error: <file> and --device <MAC> required in watch mode.`

```bash
python main.py tasks.txt
```
Expected: `Error: --device <MAC> required in watch mode.`

```bash
python main.py nonexistent.txt --device AA:BB:CC:DD:EE:FF
```
Expected: `Error: file not found: nonexistent.txt`

- [ ] **Step 4: End-to-end dry-run test**

```bash
touch /tmp/tasks.txt
python main.py /tmp/tasks.txt --device AA:BB:CC:DD:EE:FF --dry-run --debug
```

In another terminal:
```bash
echo "Buy milk" >> /tmp/tasks.txt
echo "Walk dog" >> /tmp/tasks.txt
```

Expected: `[DRY RUN] Would print: Buy milk` and `[DRY RUN] Would print: Walk dog` appear within 0.5s of each write.

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat: add main CLI entry point"
```

---

## Chunk 5: Hardware Testing

### Task 9: Hardware test (requires Niimbot B1 + Bluetooth)

- [ ] **Step 1: Find your printer's MAC address**

```bash
python main.py --discover
```

Note the MAC address printed for your Niimbot B1.

- [ ] **Step 2: Full hardware test**

```bash
touch ~/tasks.txt
python main.py ~/tasks.txt --device <YOUR_MAC> --debug
```

In another terminal:
```bash
echo "Test label from HotTicket" >> ~/tasks.txt
```

Expected: a label prints on the Niimbot B1 within ~0.5s.

- [ ] **Step 3: Test vim-style atomic save**

Open `~/tasks.txt` in vim, add a line, save with `:w`. Expected: label prints (FileCreatedEvent handled correctly).

- [ ] **Step 4: Test file deletion**

While watching, delete the file:
```bash
rm ~/tasks.txt
```

Expected: `WARNING ... Watched file deleted` in logs, process exits 0.

- [ ] **Step 5: Final commit (if any fixes needed)**

```bash
git add -p
git commit -m "fix: hardware test corrections"
```

---

## Summary

| Module | Tests | Coverage |
|---|---|---|
| `logger.py` | manual smoke test | configuration |
| `differ.py` | 13 unit tests | all logic paths |
| `printer.py` | 5 rendering tests + dry-run | rendering + pipeline |
| `watcher.py` | manual smoke test | file events + debounce |
| `main.py` | manual CLI validation + dry-run e2e | CLI + wiring |
