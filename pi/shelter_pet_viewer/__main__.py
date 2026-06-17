from __future__ import annotations

import json
import logging
import sys

import pygame

from .cache_loader import load_cached_animals
from .gpio_buttons import ButtonInput
from .kiosk import KioskDisplay, LAYOUT_READY_EVENT
from .log_util import configure_logging
from .menu import MenuController
from .paths import app_data_dir, cache_root, pi_config_path
from .settings import AppSettings
from .slideshow_session import SlideshowSession
from .sync_scheduler import SyncScheduler

log = logging.getLogger(__name__)

ACTION_EVENT = pygame.USEREVENT + 1


def _load_pi_config() -> dict:
    path = pi_config_path()
    if not path.exists():
        example = path.parent / "config.example.json"
        if example.exists():
            return json.loads(example.read_text(encoding="utf-8"))
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _post_action(action: str) -> None:
    pygame.event.post(pygame.event.Event(ACTION_EVENT, action=action))


def _key_action(key: int) -> str | None:
    mapping = {
        pygame.K_RIGHT: "forward",
        pygame.K_LEFT: "back",
        pygame.K_m: "menu",
        pygame.K_ESCAPE: "return",
        pygame.K_BACKSPACE: "return",
    }
    return mapping.get(key)


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

    def prefetch_neighbors() -> None:
        session = session_holder["session"]
        if session is None:
            return
        display.prefetch_animal(session.peek_next())
        display.prefetch_animal(session.peek_previous())

    def on_animal_changed(animal) -> None:
        if display.show_animal(animal):
            prefetch_neighbors()

    def reload_slideshow() -> None:
        animals = load_cached_animals(settings.mode, cache_root())
        display.clear_layout_cache()
        session = session_holder["session"]
        if session is None:
            session_holder["session"] = SlideshowSession(
                animals,
                settings.auto_advance_seconds,
                settings.history_size,
                on_change=on_animal_changed,
            )
            session_holder["session"].show_random_next()
        else:
            session.auto_advance_seconds = settings.auto_advance_seconds
            session.reload(animals)
        display.prewarm_animals(animals)

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

    def process_action(action: str) -> None:
        if action == "forward":
            if menu.state.visible:
                menu.move(1)
            else:
                session = session_holder["session"]
                if session is not None:
                    session.show_next()
        elif action == "back":
            if menu.state.visible:
                menu.move(-1)
            else:
                session = session_holder["session"]
                if session is not None:
                    session.show_previous()
        elif action == "menu":
            if menu.state.visible:
                menu.activate()
            else:
                menu.open_root()
                menu.set_status(scheduler.status.last_message)
        elif action == "return":
            menu.go_up()

    buttons = ButtonInput(
        pins,
        lambda: _post_action("forward"),
        lambda: _post_action("back"),
        lambda: _post_action("menu"),
        lambda: _post_action("return"),
    )

    reload_slideshow()
    scheduler.start()

    running = True
    while running:
        delta = clock.tick(60)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == ACTION_EVENT:
                process_action(event.action)
            elif event.type == LAYOUT_READY_EVENT:
                session = session_holder["session"]
                if session is None:
                    continue
                current = session.current_animal()
                if current is not None and current.id == event.animal_id:
                    if display.try_apply_animal(current):
                        prefetch_neighbors()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                    running = False
                else:
                    action = _key_action(event.key)
                    if action is not None:
                        process_action(action)

        session = session_holder["session"]
        if session is not None and not menu.state.visible and not display.is_loading():
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
