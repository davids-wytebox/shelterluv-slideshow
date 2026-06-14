from __future__ import annotations

import random
from typing import Callable

from .cache_loader import CachedAnimal


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

    def show_previous(self) -> None:
        if not self._can_go_back():
            return
        self._history_position -= 1
        self._show_at(self._history[self._history_position])

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

    def _show_at(self, index: int) -> None:
        self._current_index = index
        self.reset_timer()
        self._notify(self._animals[index])

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
