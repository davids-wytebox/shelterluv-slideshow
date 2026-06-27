from __future__ import annotations

import json
import logging
import sys
import threading

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

MAX_NAV_STEPS_PER_FRAME = 2


class ActionQueue:
    """Thread-safe input queue for GPIO (never post pygame events from other threads)."""

    def __init__(self, max_size: int = 64) -> None:
        self._items: list[str] = []
        self._lock = threading.Lock()

    def put(self, action: str) -> None:
        with self._lock:
            if len(self._items) >= 64:
                self._items.pop(0)
            self._items.append(action)

    def drain(self) -> list[str]:
        with self._lock:
            items = self._items
            self._items = []
            return items


def _load_pi_config() -> dict:
    path = pi_config_path()
    if not path.exists():
        example = path.parent / "config.example.json"
        if example.exists():
            return json.loads(example.read_text(encoding="utf-8"))
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


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
    action_queue = ActionQueue()

    session_holder: dict[str, SlideshowSession | None] = {"session": None}

    def prefetch_neighbors() -> None:
        session = session_holder["session"]
        if session is None:
            return
        display.prefetch_animal(session.peek_next())
        display.prefetch_animal(session.peek_previous())

    def apply_current_if_ready() -> None:
        session = session_holder["session"]
        if session is None:
            return
        current = session.current_animal()
        if current is None:
            return
        if display.needs_apply(current) and display.try_apply_animal(current):
            prefetch_neighbors()

    def on_animal_changed(animal) -> None:
        if display.show_animal(animal):
            prefetch_neighbors()

    reload_requested = threading.Event()

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

    def request_reload() -> None:
        reload_requested.set()

    def on_settings_changed(updated: AppSettings) -> None:
        nonlocal settings
        settings = updated
        session = session_holder["session"]
        if session is not None:
            session.auto_advance_seconds = settings.auto_advance_seconds
        reload_slideshow()
        menu.set_status(f"Saved: {settings.mode.value}, {settings.auto_advance_seconds}s")

    scheduler = SyncScheduler(interval_hours=sync_hours, on_complete=request_reload)
    menu = MenuController(settings, on_settings_changed, on_sync_requested=scheduler.request_sync)

    def process_menu_action(action: str) -> None:
        if action == "forward":
            menu.move(1)
        elif action == "back":
            menu.move(-1)
        elif action == "menu":
            menu.activate()
        elif action == "return":
            menu.go_up()

    def process_pending_nav() -> None:
        nonlocal pending_nav
        session = session_holder["session"]
        if session is None or pending_nav == 0:
            return

        steps = min(abs(pending_nav), MAX_NAV_STEPS_PER_FRAME)
        if pending_nav > 0:
            for _ in range(steps):
                session.show_next()
            pending_nav -= steps
        else:
            for _ in range(steps):
                session.show_previous()
            pending_nav += steps

    def process_slideshow_action(action: str) -> None:
        if action == "menu":
            menu.open_root()
            menu.set_status(scheduler.status.last_message)
        elif action == "return":
            menu.go_up()

    buttons = ButtonInput(
        pins,
        lambda: action_queue.put("forward"),
        lambda: action_queue.put("back"),
        lambda: action_queue.put("menu"),
        lambda: action_queue.put("return"),
    )

    reload_slideshow()
    scheduler.start()

    pending_nav = 0

    running = True
    while running:
        delta = clock.tick(60)
        events = pygame.event.get()

        if reload_requested.is_set():
            reload_requested.clear()
            pending_nav = 0
            reload_slideshow()

        forward_steps = 0
        back_steps = 0
        menu_actions: list[str] = []
        slideshow_actions: list[str] = []
        sync_in_progress = scheduler.status.running

        for action in action_queue.drain():
            if menu.state.visible:
                menu_actions.append(action)
            elif sync_in_progress:
                if action in ("menu", "return"):
                    slideshow_actions.append(action)
            elif action == "forward":
                forward_steps += 1
            elif action == "back":
                back_steps += 1
            else:
                slideshow_actions.append(action)

        for event in events:
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                    running = False
                else:
                    action = _key_action(event.key)
                    if action is None:
                        continue
                    if menu.state.visible:
                        menu_actions.append(action)
                    elif sync_in_progress:
                        if action in ("menu", "return"):
                            slideshow_actions.append(action)
                    elif action == "forward":
                        forward_steps += 1
                    elif action == "back":
                        back_steps += 1
                    else:
                        slideshow_actions.append(action)

        if not sync_in_progress:
            pending_nav = max(-20, min(20, pending_nav + forward_steps - back_steps))

        display.recover_stuck_loading()

        for action in menu_actions:
            process_menu_action(action)

        if not menu.state.visible:
            process_pending_nav()

        for action in slideshow_actions:
            process_slideshow_action(action)

        for animal_id in display.drain_ready_layout_ids():
            session = session_holder["session"]
            if session is None:
                continue
            current = session.current_animal()
            if current is not None and current.id == animal_id:
                if display.try_apply_animal(current):
                    prefetch_neighbors()

        apply_current_if_ready()

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
