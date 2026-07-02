from __future__ import annotations

import logging
import time
from logging.handlers import RotatingFileHandler

from .paths import app_data_dir, log_path

_configured = False
_nav_last_mono: float | None = None

LOG_FORMAT = "%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"


def _make_formatter() -> logging.Formatter:
    return logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT)


def nav_info(message: str, *args: object) -> None:
    """Log a navigation event with wall-clock timestamp and gap since the last nav event."""
    global _nav_last_mono
    now = time.monotonic()
    gap_s = 0.0 if _nav_last_mono is None else now - _nav_last_mono
    _nav_last_mono = now
    text = message % args if args else message
    logging.getLogger().info("[nav] +%.1fs %s", gap_s, text)


def nav_warning(message: str, *args: object) -> None:
    global _nav_last_mono
    now = time.monotonic()
    gap_s = 0.0 if _nav_last_mono is None else now - _nav_last_mono
    _nav_last_mono = now
    text = message % args if args else message
    logging.getLogger().warning("[nav] +%.1fs %s", gap_s, text)


def configure_logging() -> None:
    global _configured
    if _configured:
        return

    app_data_dir().mkdir(parents=True, exist_ok=True)
    formatter = _make_formatter()

    file_handler = RotatingFileHandler(
        log_path(),
        maxBytes=512 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(stream_handler)

    _configured = True
