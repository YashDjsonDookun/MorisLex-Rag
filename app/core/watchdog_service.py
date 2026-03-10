"""Optional watchdog: detect new files in data dir, notify or auto-reindex."""

from __future__ import annotations

import threading
from pathlib import Path
from app.core.config import get_config

_observer = None
_callback = None  # callable() -> None for "new data detected"


def start_watchdog(on_new_data: callable | None = None) -> None:
    """Start watching configured data directory. Off by default."""
    global _observer, _callback
    config = get_config()
    if not config.watchdog.enabled:
        return
    data_dir = config.get_data_directory()
    if not data_dir or not Path(data_dir).exists():
        return
    _callback = on_new_data

    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class Handler(FileSystemEventHandler):
            def on_created(self, ev):
                if ev.is_directory:
                    return
                if _callback:
                    _callback()

            def on_modified(self, ev):
                if ev.is_directory:
                    return
                if _callback:
                    _callback()

        _observer = Observer()
        _observer.schedule(Handler(), data_dir, recursive=True)
        _observer.start()
    except Exception:
        _observer = None


def stop_watchdog() -> None:
    global _observer
    if _observer:
        try:
            _observer.stop()
        except Exception:
            pass
        _observer = None
