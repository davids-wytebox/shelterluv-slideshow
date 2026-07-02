from __future__ import annotations

import random
from typing import Any, Callable

from .cache_loader import CachedAnimal
from .log_util import nav_info


class SlideshowSession:
    def __init__(
        self,
        animals: list[CachedAnimal],
        auto_advance_seconds: int,
        history_size: int,
        on_change: Callable[[CachedAnimal | None], None] | None = None,
    ) -> None:
        self._animals = list(animals)
        self._history_size = history_size
        self._auto_advance_seconds = auto_advance_seconds
        self._history: list[int] = []
        self._history_position = -1
        self._current_index = -1
        self._on_change = on_change
        self._timer_ms = 0

    @property
    def auto_advance_seconds(self) -> int:
        return self._auto_advance_seconds

    @auto_advance_seconds.setter
    def auto_advance_seconds(self, value: int) -> None:
        self._auto_advance_seconds = value
        self.reset_timer()

    @property
    def timer_ms(self) -> int:
        return self._timer_ms

    def reload(self, animals: list[CachedAnimal]) -> None:
        self._animals = list(animals)
        self._history.clear()
        self._history_position = -1
        self._current_index = -1
        self.show_random_next()

    def tick(self, delta_ms: int) -> None:
        if not self._animals:
            return
        self._timer_ms += delta_ms
        if self._timer_ms >= self._auto_advance_seconds * 1000:
            self.show_random_next()

    def reset_timer(self) -> None:
        self._timer_ms = 0

    def show_next(self) -> None:
        if self._can_go_forward():
            self._history_position += 1
            self._show_at(self._history[self._history_position])
            return
        self.show_random_next()

    def show_previous(self) -> bool:
        if not self._can_go_back():
            nav_info(
                "show_previous blocked: history_pos=%s history_len=%s animal=%s",
                self._history_position,
                len(self._history),
                self._animal_id(),
            )
            return False
        self._history_position -= 1
        index = self._history[self._history_position]
        nav_info(
            "show_previous: history_pos=%s/%s -> animal_index=%s id=%s",
            self._history_position,
            len(self._history) - 1,
            index,
            self._animals[index].id if 0 <= index < len(self._animals) else "?",
        )
        self._show_at(index)
        return True

    def nav_snapshot(self) -> dict[str, Any]:
        animal = self.current_animal()
        return {
            "history_pos": self._history_position,
            "history_len": len(self._history),
            "can_back": self._can_go_back(),
            "can_forward": self._can_go_forward(),
            "animal_id": animal.id if animal else None,
        }

    def show_random_next(self) -> None:
        self.reset_timer()
        if not self._animals:
            self._notify(None)
            return

        if len(self._animals) == 1:
            index = 0
        else:
            index = random.randrange(len(self._animals))
            while index == self._current_index:
                index = random.randrange(len(self._animals))

        self._truncate_forward_history()
        self._append_history(index)
        self._show_at(index)

    def _can_go_back(self) -> bool:
        return self._history_position > 0

    def _can_go_forward(self) -> bool:
        return 0 <= self._history_position < len(self._history) - 1

    def current_animal(self) -> CachedAnimal | None:
        if self._current_index < 0 or self._current_index >= len(self._animals):
            return None
        return self._animals[self._current_index]

    def peek_next(self) -> CachedAnimal | None:
        if not self._can_go_forward():
            return None
        return self._animals[self._history[self._history_position + 1]]

    def peek_previous(self) -> CachedAnimal | None:
        if not self._can_go_back():
            return None
        return self._animals[self._history[self._history_position - 1]]

    def _show_at(self, index: int) -> None:
        self._current_index = index
        self.reset_timer()
        self._notify(self._animals[index])

    def _animal_id(self) -> str | None:
        animal = self.current_animal()
        return animal.id if animal else None

    def _notify(self, animal: CachedAnimal | None) -> None:
        if self._on_change is not None:
            self._on_change(animal)

    def _truncate_forward_history(self) -> None:
        if self._history_position < len(self._history) - 1:
            del self._history[self._history_position + 1 :]

    def _append_history(self, index: int) -> None:
        if self._history_position >= 0 and self._history and self._history[self._history_position] == index:
            return
        self._history.append(index)
        self._history_position = len(self._history) - 1
        while len(self._history) > self._history_size:
            self._history.pop(0)
            self._history_position -= 1
