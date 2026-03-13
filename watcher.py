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
        self._target = os.path.realpath(target_path)
        self._on_change = on_change
        self._on_delete = on_delete
        self._timer: threading.Timer | None = None

    def dispatch(self, event):
        if os.path.realpath(event.src_path) != self._target:
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
