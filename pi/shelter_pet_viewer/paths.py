from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "ShelterPetViewer"


def app_data_dir() -> Path:
    override = os.environ.get("SHELTER_PET_VIEWER_DATA")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".local" / "share" / APP_NAME


def cache_root() -> Path:
    return app_data_dir() / "cache"


def settings_path() -> Path:
    return app_data_dir() / "settings.json"


def log_path() -> Path:
    return app_data_dir() / "log.txt"


def pi_config_path() -> Path:
    env = os.environ.get("SHELTER_PET_VIEWER_CONFIG")
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parent.parent / "config.json"
