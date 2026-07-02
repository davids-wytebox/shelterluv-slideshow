from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable

from .settings import AUTO_ADVANCE_OPTIONS, AppSettings, SpeciesFilter, ViewMode


class MenuAction(Enum):
    NONE = auto()
    OPEN_ANIMAL_SET = auto()
    OPEN_SPECIES_FILTER = auto()
    OPEN_INTERVAL = auto()
    SYNC_NOW = auto()
    SET_MODE = auto()
    SET_SPECIES_FILTER = auto()
    SET_INTERVAL = auto()


@dataclass
class MenuItem:
    label: str
    action: MenuAction = MenuAction.NONE
    value: str | int | None = None
    checked: bool = False
    submenu: list[MenuItem] | None = None


@dataclass
class MenuState:
    visible: bool = False
    stack: list[list[MenuItem]] = field(default_factory=list)
    index: int = 0
    status_line: str = ""

    @property
    def current_items(self) -> list[MenuItem]:
        if not self.stack:
            return []
        return self.stack[-1]


class MenuController:
    def __init__(
        self,
        settings: AppSettings,
        on_settings_changed: Callable[[AppSettings], None],
        on_sync_requested: Callable[[], None],
    ) -> None:
        self._settings = settings
        self._on_settings_changed = on_settings_changed
        self._on_sync_requested = on_sync_requested
        self.state = MenuState()

    def set_status(self, text: str) -> None:
        self.state.status_line = text

    def open_root(self) -> None:
        self.state.visible = True
        self.state.stack = [self._root_items()]
        self.state.index = 0

    def close(self) -> None:
        self.state.visible = False
        self.state.stack.clear()
        self.state.index = 0

    def go_up(self) -> None:
        if not self.state.visible:
            return
        if len(self.state.stack) > 1:
            self.state.stack.pop()
            self.state.index = 0
        else:
            self.close()

    def move(self, delta: int) -> None:
        if not self.state.visible or not self.state.current_items:
            return
        count = len(self.state.current_items)
        self.state.index = (self.state.index + delta) % count

    def activate(self) -> None:
        if not self.state.visible or not self.state.current_items:
            return
        item = self.state.current_items[self.state.index]
        if item.submenu is not None:
            self.state.stack.append(item.submenu)
            self.state.index = 0
            return

        if item.action == MenuAction.SYNC_NOW:
            self.state.status_line = "Updating cache..."
            self._on_sync_requested()
            return

        if item.action == MenuAction.SET_MODE and isinstance(item.value, str):
            self._settings.mode = ViewMode(item.value)
            self._settings.save()
            self._on_settings_changed(self._settings)
            self.state.stack = [self._root_items(), self._animal_set_items()]
            return

        if item.action == MenuAction.SET_SPECIES_FILTER and isinstance(item.value, str):
            self._settings.species_filter = SpeciesFilter(item.value)
            self._settings.save()
            self._on_settings_changed(self._settings)
            self.state.stack = [self._root_items(), self._species_filter_items()]
            return

        if item.action == MenuAction.SET_INTERVAL and isinstance(item.value, int):
            self._settings.auto_advance_seconds = item.value
            self._settings.save()
            self._on_settings_changed(self._settings)
            self.state.stack = [self._root_items(), self._interval_items()]
            return

    def _root_items(self) -> list[MenuItem]:
        mode_label = self._settings.mode.value
        species_label = self._species_filter_label(self._settings.species_filter)
        interval_label = f"{self._settings.auto_advance_seconds} seconds"
        return [
            MenuItem("Animal Set", action=MenuAction.OPEN_ANIMAL_SET, submenu=self._animal_set_items()),
            MenuItem(
                "Animals Shown",
                action=MenuAction.OPEN_SPECIES_FILTER,
                submenu=self._species_filter_items(),
            ),
            MenuItem("Slide Interval", action=MenuAction.OPEN_INTERVAL, submenu=self._interval_items()),
            MenuItem("Update Cache Now", action=MenuAction.SYNC_NOW),
            MenuItem(f"Current: {mode_label}, {species_label}, {interval_label}"),
        ]

    def _animal_set_items(self) -> list[MenuItem]:
        return [
            MenuItem(
                "Adoption",
                action=MenuAction.SET_MODE,
                value=ViewMode.ADOPTION.value,
                checked=self._settings.mode == ViewMode.ADOPTION,
            ),
            MenuItem(
                "Foster",
                action=MenuAction.SET_MODE,
                value=ViewMode.FOSTER.value,
                checked=self._settings.mode == ViewMode.FOSTER,
            ),
        ]

    def _species_filter_items(self) -> list[MenuItem]:
        return [
            MenuItem(
                "Dogs and Cats",
                action=MenuAction.SET_SPECIES_FILTER,
                value=SpeciesFilter.ALL.value,
                checked=self._settings.species_filter == SpeciesFilter.ALL,
            ),
            MenuItem(
                "Dogs only",
                action=MenuAction.SET_SPECIES_FILTER,
                value=SpeciesFilter.DOGS.value,
                checked=self._settings.species_filter == SpeciesFilter.DOGS,
            ),
            MenuItem(
                "Cats only",
                action=MenuAction.SET_SPECIES_FILTER,
                value=SpeciesFilter.CATS.value,
                checked=self._settings.species_filter == SpeciesFilter.CATS,
            ),
        ]

    @staticmethod
    def _species_filter_label(species_filter: SpeciesFilter) -> str:
        if species_filter == SpeciesFilter.DOGS:
            return "Dogs only"
        if species_filter == SpeciesFilter.CATS:
            return "Cats only"
        return "Dogs and Cats"

    def _interval_items(self) -> list[MenuItem]:
        return [
            MenuItem(
                f"{seconds} seconds",
                action=MenuAction.SET_INTERVAL,
                value=seconds,
                checked=self._settings.auto_advance_seconds == seconds,
            )
            for seconds in AUTO_ADVANCE_OPTIONS
        ]
