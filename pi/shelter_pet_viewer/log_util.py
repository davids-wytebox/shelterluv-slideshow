from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from .paths import app_data_dir, log_path

_configured = False


def configure_logging() -> None:
    global _configured
    if _configured:
        return

    app_data_dir().mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_path(),
        maxBytes=512 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    root.addHandler(logging.StreamHandler())

    _configured = True
