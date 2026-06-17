from __future__ import annotations

import logging
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
    ) -> None:
        self._handlers = {
            "forward": on_forward,
            "back": on_back,
            "menu": on_menu,
            "return": on_return,
        }
        self._buttons: list[object] = []
        self._use_gpio = GPIO_AVAILABLE

        if self._use_gpio:
            try:
                for name, pin in pins.items():
                    button = Button(pin, pull_up=True, bounce_time=0.08)
                    button.when_pressed = self._handlers[name]
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
