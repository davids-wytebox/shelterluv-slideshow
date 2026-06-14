from __future__ import annotations

import json
import logging
import sys

import pygame

from .cache_loader import load_cached_animals
from .gpio_buttons import ButtonInput
from .kiosk import KioskDisplay
from .log_util import configure_logging
from .menu import MenuController
from .paths import app_data_dir, cache_root, pi_config_path
from .settings import AppSettings
from .slideshow_session import SlideshowSession
from .sync_scheduler import SyncScheduler

log = logging.getLogger(__name__)


def _load_pi_config() -> dict:
    path = pi_config_path()
    if not path.exists():
        example = path.parent / "config.example.json"
        if example.exists():
            return json.loads(example.read_text(encoding="utf-8"))
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    configure_logging()
    app_data_dir().mkdir(parents=True, exist_ok=True)
    config = _load_pi_config()
    gpio_cfg = config.get("gpio", {})
    pins = {
        "forward": int(gpio_cfg.get("forward", 17)),
        "back": int(gpio_cfg.get("back", 27)),
        "menu": int(gpio_cfg.get("menu", 22)),
        "return": int(gpio_cfg.get("return", 23)),
    }
    sync_hours = float(config.get("sync_interval_hours", 2))
    fullscreen = bool(config.get("fullscreen", True))
    hide_cursor = bool(config.get("hide_cursor", True))

    settings = AppSettings.load()
    display = KioskDisplay(fullscreen=fullscreen, hide_cursor=hide_cursor)
    clock = pygame.time.Clock()

    session_holder: dict[str, SlideshowSession | None] = {"session": None}

    def reload_slideshow() -> None:
        animals = load_cached_animals(settings.mode, cache_root())
        session = session_holder["session"]
        if session is None:
            session_holder["session"] = SlideshowSession(
                animals,
                settings.auto_advance_seconds,
                settings.history_size,
                on_change=display.show_animal,
            )
            session_holder["session"].show_random_next()
        else:
            session.auto_advance_seconds = settings.auto_advance_seconds
            session.reload(animals)

    def on_settings_changed(updated: AppSettings) -> None:
        nonlocal settings
        settings = updated
        session = session_holder["session"]
        if session is not None:
            session.auto_advance_seconds = settings.auto_advance_seconds
        reload_slideshow()
        menu.set_status(f"Saved: {settings.mode.value}, {settings.auto_advance_seconds}s")

    scheduler = SyncScheduler(interval_hours=sync_hours, on_complete=reload_slideshow)
    menu = MenuController(settings, on_settings_changed, on_sync_requested=scheduler.request_sync)

    def handle_forward() -> None:
        if menu.state.visible:
            menu.move(1)
        else:
            session = session_holder["session"]
            if session is not None:
                session.show_next()

    def handle_back() -> None:
        if menu.state.visible:
            menu.move(-1)
        else:
            session = session_holder["session"]
            if session is not None:
                session.show_previous()

    def handle_menu() -> None:
        if menu.state.visible:
            menu.activate()
        else:
            menu.open_root()
            menu.set_status(scheduler.status.last_message)

    def handle_return() -> None:
        menu.go_up()

    buttons = ButtonInput(pins, handle_forward, handle_back, handle_menu, handle_return)

    reload_slideshow()
    scheduler.start()

    running = True
    while running:
        delta = clock.tick(60)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                    running = False
                else:
                    buttons.handle_key(event.key)

        session = session_holder["session"]
        if session is not None and not menu.state.visible:
            session.tick(delta)

        sync_status = scheduler.status.last_message
        if scheduler.status.running:
            sync_status = "Syncing cache..."
        display.draw(menu.state, sync_status)

    scheduler.stop()
    buttons.close()
    display.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
