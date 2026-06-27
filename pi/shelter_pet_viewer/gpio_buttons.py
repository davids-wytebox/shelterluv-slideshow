from __future__ import annotations

import logging
import time
from collections.abc import Callable

log = logging.getLogger(__name__)

try:
    from gpiozero import Button

    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    Button = None  # type: ignore[assignment,misc]


class ButtonInput:
    """GPIO buttons with keyboard fallback for development."""

    def __init__(
        self,
        pins: dict[str, int],
        on_forward: Callable[[], None],
        on_back: Callable[[], None],
        on_menu: Callable[[], None],
        on_return: Callable[[], None],
        debounce_seconds: float = 0.25,
        back_debounce_seconds: float = 0.35,
    ) -> None:
        self._handlers = {
            "forward": on_forward,
            "back": on_back,
            "menu": on_menu,
            "return": on_return,
        }
        self._buttons: list[object] = []
        self._use_gpio = GPIO_AVAILABLE
        self._debounce_seconds = debounce_seconds
        self._back_debounce_seconds = back_debounce_seconds
        self._last_press: dict[str, float] = {}

        if self._use_gpio:
            try:
                for name, pin in pins.items():
                    bounce = 0.2 if name == "back" else 0.15
                    button = Button(pin, pull_up=True, bounce_time=bounce)
                    debounce = back_debounce_seconds if name == "back" else debounce_seconds
                    button.when_pressed = self._debounced(self._handlers[name], name, debounce)
                    self._buttons.append(button)
                log.info(
                    "GPIO buttons enabled: forward=%s back=%s menu=%s return=%s",
                    pins.get("forward"),
                    pins.get("back"),
                    pins.get("menu"),
                    pins.get("return"),
                )
            except Exception as exc:
                log.warning(
                    "GPIO setup failed (%s); using keyboard only. "
                    "On Raspberry Pi OS run: sudo apt install python3-lgpio && rm -rf pi/.venv && ./setup.sh",
                    exc,
                )
                self._use_gpio = False
                self._buttons.clear()
        else:
            log.info("gpiozero unavailable; using keyboard controls only.")

    def _debounced(
        self,
        handler: Callable[[], None],
        name: str,
        debounce_seconds: float | None = None,
    ) -> Callable[[], None]:
        interval = debounce_seconds if debounce_seconds is not None else self._debounce_seconds

        def wrapped() -> None:
            now = time.monotonic()
            last = self._last_press.get(name, 0.0)
            if now - last < interval:
                return
            self._last_press[name] = now
            handler()

        return wrapped

    def handle_key(self, key: int) -> bool:
        import pygame

        mapping = {
            pygame.K_RIGHT: "forward",
            pygame.K_LEFT: "back",
            pygame.K_m: "menu",
            pygame.K_ESCAPE: "return",
            pygame.K_BACKSPACE: "return",
        }
        action = mapping.get(key)
        if action is None:
            return False
        self._handlers[action]()
        return True

    def close(self) -> None:
        for button in self._buttons:
            try:
                button.close()  # type: ignore[attr-defined]
            except Exception:
                pass
        self._buttons.clear()
