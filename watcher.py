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
    FileMovedEvent,
)


class _Handler(FileSystemEventHandler):
    def __init__(self, target_path: str, on_change: Callable[[], None], on_delete: Callable[[], None]):
        self._target = os.path.realpath(target_path)
        self._on_change = on_change
        self._on_delete = on_delete
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def dispatch(self, event):
        # We override dispatch() entirely to skip on_any_event and on_<type> base
        # class calls — we only care about our specific target path.
        if isinstance(event, FileMovedEvent):
            # vim/emacs atomic-save: target appears as the rename destination
            if os.path.realpath(event.dest_path) == self._target:
                self._debounce()
        elif isinstance(event, (FileModifiedEvent, FileCreatedEvent)):
            if os.path.realpath(event.src_path) == self._target:
                self._debounce()
        elif isinstance(event, FileDeletedEvent):
            if os.path.realpath(event.src_path) == self._target:
                self._on_delete()

    def _debounce(self):
        def _fire():
            with self._lock:
                self._timer = None
            self._on_change()

        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(0.5, _fire)
            self._timer.start()

    def cancel_timer(self):
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None


class Watcher:
    def __init__(self, path: str, on_change: Callable[[], None]):
        self._path = path
        self._observer = FSEventsObserver()
        # _deleted is set on the observer thread; read only after join() to ensure
        # visibility (threading.join() establishes a happens-before edge).
        self._deleted = False

        def handle_delete():
            logger.warning("Watched file deleted: %s", path)
            self._deleted = True
            self._observer.stop()

        self._handler = _Handler(path, on_change, handle_delete)
        watch_dir = os.path.realpath(str(Path(path).parent))
        self._observer.schedule(self._handler, watch_dir, recursive=False)

    def start(self) -> None:
        self._observer.start()
        if not self._observer.is_alive():
            raise RuntimeError(f"FSEventsObserver failed to start for {self._path}")
        logger.debug("Watching %s", self._path)

    def stop(self) -> None:
        self._handler.cancel_timer()
        self._observer.stop()

    def join(self) -> None:
        self._observer.join()

    def was_deleted(self) -> bool:
        # Safe to call only after join() has returned.
        return self._deleted
