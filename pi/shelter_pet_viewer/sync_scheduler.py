from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from .cache_sync import sync_all
from .paths import cache_root
from .shelter_api import has_internet

log = logging.getLogger(__name__)


@dataclass
class SyncStatus:
    last_attempt: datetime | None = None
    last_success: datetime | None = None
    last_message: str = "Not synced yet"
    running: bool = False


class SyncScheduler:
    def __init__(self, interval_hours: float = 2.0, on_complete: Callable[[], None] | None = None) -> None:
        self._interval_seconds = max(interval_hours, 0.25) * 3600
        self._on_complete = on_complete
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.status = SyncStatus()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="sync-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def request_sync(self) -> None:
        threading.Thread(target=self._sync_once, name="sync-manual", daemon=True).start()

    def _run(self) -> None:
        self._sync_once()
        while not self._stop.wait(self._interval_seconds):
            self._sync_once()

    def _sync_once(self) -> None:
        if self.status.running:
            log.info("Sync already running; skipping.")
            return

        self.status.running = True
        self.status.last_attempt = datetime.now()
        self.status.last_message = "Checking internet..."

        if not has_internet():
            self.status.last_message = "Offline — will retry in 2 hours"
            log.info("No internet; skipping cache sync.")
            self.status.running = False
            return

        try:
            self.status.last_message = "Syncing adoption and foster..."
            log.info("Starting cache update for adoption and foster.")
            adoption, foster = sync_all(cache_root())
            total = adoption.total + foster.total
            added = adoption.added + foster.added
            updated = adoption.updated + foster.updated
            removed = adoption.removed + foster.removed
            message = (
                f"Synced {total} animals "
                f"({added} new, {updated} updated, {removed} removed)"
            )
            self.status.last_success = datetime.now()
            self.status.last_message = message
            log.info(
                "Cache update finished: %s total (adoption %s, foster %s), %s added, %s updated, %s removed.",
                total,
                adoption.total,
                foster.total,
                added,
                updated,
                removed,
            )
            if self._on_complete is not None:
                self._on_complete()
        except Exception as exc:
            self.status.last_message = f"Sync failed: {exc}"
            log.exception("Cache update failed")
        finally:
            self.status.running = False
