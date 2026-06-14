from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .paths import settings_path


class ViewMode(str, Enum):
    ADOPTION = "Adoption"
    FOSTER = "Foster"


AUTO_ADVANCE_OPTIONS = [10, 15, 20, 30, 45, 60]


@dataclass
class AppSettings:
    mode: ViewMode = ViewMode.ADOPTION
    auto_advance_seconds: int = 45
    history_size: int = 20

    @classmethod
    def load(cls) -> AppSettings:
        path = settings_path()
        if not path.exists():
            return cls()

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()

        mode_raw = data.get("Mode", "Adoption")
        try:
            mode = ViewMode(mode_raw)
        except ValueError:
            mode = ViewMode.ADOPTION

        seconds = int(data.get("AutoAdvanceSeconds", 45))
        if seconds not in AUTO_ADVANCE_OPTIONS:
            seconds = 45

        history = int(data.get("HistorySize", 20))
        if history < 1:
            history = 20

        return cls(mode=mode, auto_advance_seconds=seconds, history_size=history)

    def save(self) -> None:
        path = settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        existing: dict[str, Any] = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                existing = {}

        existing["Mode"] = self.mode.value
        existing["AutoAdvanceSeconds"] = self.auto_advance_seconds
        existing["HistorySize"] = self.history_size

        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        tmp.replace(path)
