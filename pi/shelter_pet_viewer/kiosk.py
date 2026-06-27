from __future__ import annotations

import io
import logging
import math
import queue
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pygame
import qrcode
from PIL import Image

from .cache_loader import CachedAnimal, format_card_text, parse_display_name, title_case
from .menu import MenuController, MenuState

log = logging.getLogger(__name__)

BG_COLOR = (242, 242, 240)
NAVY = (30, 58, 95)
WHITE = (255, 255, 255)
CARD_BG = (250, 250, 248)
TEXT_MUTED = (68, 68, 68)


@dataclass(frozen=True)
class PhotoPlacement:
    center_x: float
    center_y: float
    scale: float
    rotation: float
    z_index: int


PLACEMENTS = {
    2: [
        PhotoPlacement(0.35, 0.50, 0.44, -4, 1),
        PhotoPlacement(0.65, 0.52, 0.44, 4, 2),
    ],
    3: [
        PhotoPlacement(0.24, 0.50, 0.34, -6, 2),
        PhotoPlacement(0.50, 0.50, 0.52, 0, 0),
        PhotoPlacement(0.76, 0.50, 0.34, 6, 3),
    ],
    4: [
        PhotoPlacement(0.26, 0.28, 0.32, -8, 2),
        PhotoPlacement(0.74, 0.26, 0.34, 7, 3),
        PhotoPlacement(0.50, 0.50, 0.50, 0, 0),
        PhotoPlacement(0.26, 0.72, 0.30, -5, 4),
    ],
    5: [
        PhotoPlacement(0.27, 0.26, 0.32, -8, 2),
        PhotoPlacement(0.73, 0.24, 0.32, 8, 3),
        PhotoPlacement(0.50, 0.50, 0.48, 0, 0),
        PhotoPlacement(0.27, 0.68, 0.30, -6, 4),
        PhotoPlacement(0.73, 0.70, 0.32, 5, 5),
    ],
}


class KioskDisplay:
    def __init__(self, fullscreen: bool = True, hide_cursor: bool = True) -> None:
        pygame.init()
        pygame.font.init()
        flags = pygame.FULLSCREEN if fullscreen else 0
        self.screen = pygame.display.set_mode((0, 0), flags) if fullscreen else pygame.display.set_mode((1280, 720))
        self.width, self.height = self.screen.get_size()
        pygame.display.set_caption("Shelter Pet Viewer")
        if hide_cursor:
            pygame.mouse.set_visible(False)

        self.title_font = pygame.font.SysFont("DejaVu Sans", 72, bold=True)
        self.bio_font = pygame.font.SysFont("DejaVu Sans", 22)
        self.menu_font = pygame.font.SysFont("DejaVu Sans", 28)
        self.menu_title_font = pygame.font.SysFont("DejaVu Sans", 36, bold=True)
        self.hint_font = pygame.font.SysFont("DejaVu Sans", 18)

        self._photo_cache: dict[str, pygame.Surface] = {}
        self._qr_cache: dict[str, pygame.Surface] = {}
        self._layout_cache: dict[str, list[tuple[pygame.Surface, PhotoPlacement]]] = {}
        self._layout_lock = threading.Lock()
        self._display_target: CachedAnimal | None = None
        self._display_target_since = 0.0
        self._prefetch_queue: list[CachedAnimal] = []
        self._loader_lock = threading.Lock()
        self._loader_notify = threading.Condition(self._loader_lock)
        self._loader_stop = False
        self._ready_queue: queue.Queue[str] = queue.Queue()
        self._current_animal_id: str | None = None
        self._current_surfaces: list[tuple[pygame.Surface, PhotoPlacement]] = []
        self._current_name = ""
        self._current_bio = ""
        self._current_qr: pygame.Surface | None = None
        self._empty_message: str | None = None
        self._status_anim_ms = 0

        threading.Thread(target=self._loader_loop, name="layout-loader", daemon=True).start()

    def close(self) -> None:
        self._loader_stop = True
        with self._loader_notify:
            self._loader_notify.notify_all()
        pygame.quit()

    def set_empty(self, message: str) -> None:
        self._empty_message = message
        self._current_surfaces.clear()
        self._current_name = "No cached animals"
        self._current_bio = message
        self._current_qr = None
        self._current_animal_id = None

    def clear_layout_cache(self) -> None:
        with self._layout_lock:
            self._layout_cache.clear()
        with self._loader_lock:
            self._display_target = None
            self._display_target_since = 0.0
            self._prefetch_queue.clear()
        self._photo_cache.clear()
        self._drain_ready_queue()

    def prewarm_animals(self, animals: list[CachedAnimal]) -> None:
        for animal in animals:
            self.prefetch_animal(animal)

    def prefetch_animal(self, animal: CachedAnimal | None) -> None:
        if animal is None:
            return
        if self._is_layout_cached(animal.id):
            return
        with self._loader_lock:
            if self._display_target is not None and self._display_target.id == animal.id:
                return
            if any(item.id == animal.id for item in self._prefetch_queue):
                return
            self._prefetch_queue.append(animal)
            self._loader_notify.notify()

    def show_animal(self, animal: CachedAnimal | None) -> bool:
        """Show animal immediately if cached, otherwise keep current slide and load in background."""
        if animal is None:
            self.set_empty("Use Update Cache in the menu while online.")
            with self._loader_lock:
                self._display_target = None
                self._display_target_since = 0.0
            return True

        if self._is_layout_cached(animal.id):
            surfaces = self._get_cached_layout(animal.id)
            self._apply_animal(animal, surfaces, source="show_animal")
            self._clear_display_target_if_matches(animal.id)
            return True

        log.info("[nav] show_animal deferred: %s (layout not cached, was showing %s)", animal.id, self._current_animal_id)
        with self._loader_lock:
            self._display_target = animal
            self._display_target_since = time.monotonic()
            self._loader_notify.notify()
        return False

    def try_apply_animal(self, animal: CachedAnimal, *, source: str = "try_apply") -> bool:
        if not self._is_layout_cached(animal.id):
            return False
        surfaces = self._get_cached_layout(animal.id)
        self._apply_animal(animal, surfaces, source=source)
        self._clear_display_target_if_matches(animal.id)
        return True

    def drain_ready_layout_ids(self) -> list[str]:
        ready: list[str] = []
        while True:
            try:
                ready.append(self._ready_queue.get_nowait())
            except queue.Empty:
                break
        return ready

    def recover_stuck_loading(self, timeout_seconds: float = 12.0) -> None:
        with self._loader_lock:
            if self._display_target is None:
                return
            if time.monotonic() - self._display_target_since < timeout_seconds:
                return
            log.warning(
                "Clearing stuck display load for %s after %.0fs",
                self._display_target.id,
                timeout_seconds,
            )
            self._display_target = None
            self._display_target_since = 0.0

    def is_loading(self) -> bool:
        with self._loader_lock:
            return self._display_target is not None

    def needs_apply(self, animal: CachedAnimal) -> bool:
        return self._current_animal_id != animal.id and self._is_layout_cached(animal.id)

    def _clear_display_target_if_matches(self, animal_id: str) -> None:
        with self._loader_lock:
            if self._display_target is not None and self._display_target.id == animal_id:
                self._display_target = None
                self._display_target_since = 0.0

    def _drain_ready_queue(self) -> None:
        while True:
            try:
                self._ready_queue.get_nowait()
            except queue.Empty:
                break

    def _signal_layout_ready(self, animal_id: str) -> None:
        log.info("[nav] layout ready for %s (display_target=%s)", animal_id, self._display_target_id())
        try:
            self._ready_queue.put_nowait(animal_id)
        except queue.Full:
            pass

    def _display_target_id(self) -> str | None:
        with self._loader_lock:
            return self._display_target.id if self._display_target else None

    def _complete_display_job(self, animal: CachedAnimal, built: bool) -> None:
        with self._loader_lock:
            still_target = (
                self._display_target is not None and self._display_target.id == animal.id
            )
            if still_target:
                self._display_target = None
                self._display_target_since = 0.0
        if still_target and built and self._is_layout_cached(animal.id):
            self._signal_layout_ready(animal.id)

    def _is_layout_cached(self, animal_id: str) -> bool:
        with self._layout_lock:
            return self._layout_key(animal_id) in self._layout_cache

    def _get_cached_layout(self, animal_id: str) -> list[tuple[pygame.Surface, PhotoPlacement]]:
        with self._layout_lock:
            return self._layout_cache[self._layout_key(animal_id)]

    def _loader_loop(self) -> None:
        while not self._loader_stop:
            with self._loader_lock:
                while not self._loader_stop and self._display_target is None and not self._prefetch_queue:
                    self._loader_notify.wait(timeout=0.5)
                if self._loader_stop:
                    return

                if self._display_target is not None:
                    animal = self._display_target
                    for_display = True
                else:
                    animal = self._prefetch_queue.pop(0)
                    for_display = False

            if self._is_layout_cached(animal.id):
                if for_display:
                    self._complete_display_job(animal, built=True)
                continue

            built = False
            try:
                built = self._prewarm_animal(animal)
            except Exception:
                log.exception("Failed building layout for %s", animal.id)

            if for_display:
                self._complete_display_job(animal, built=built)

    def _layout_key(self, animal_id: str) -> str:
        return f"{animal_id}:{self.width}x{self.height}"

    def _prewarm_animal(self, animal: CachedAnimal) -> bool:
        cache_key = self._layout_key(animal.id)
        with self._layout_lock:
            if cache_key in self._layout_cache:
                return True
        surfaces = self._build_surfaces(animal)
        with self._layout_lock:
            if cache_key not in self._layout_cache:
                self._layout_cache[cache_key] = surfaces
        return True

    def _apply_animal(
        self,
        animal: CachedAnimal,
        surfaces: list[tuple[pygame.Surface, PhotoPlacement]],
        *,
        source: str = "apply",
    ) -> None:
        log.info(
            "[nav] image shown: %s (%s) via %s (was %s)",
            animal.id,
            title_case(parse_display_name(animal.name)),
            source,
            self._current_animal_id,
        )
        self._empty_message = None
        self._current_animal_id = animal.id
        self._current_name = title_case(parse_display_name(animal.name))
        self._current_bio = format_card_text(animal)
        self._current_qr = self._load_qr(animal.id)
        self._current_surfaces = surfaces

    def _build_surfaces(self, animal: CachedAnimal) -> list[tuple[pygame.Surface, PhotoPlacement]]:
        layout_random = random.Random(hash(animal.id.lower()) & 0xFFFFFFFF)
        surfaces: list[tuple[pygame.Surface, PhotoPlacement]] = []

        photos = [self._load_photo(path) for path in animal.photo_paths[:5]]
        photos = [photo for photo in photos if photo is not None]
        if not photos:
            return []

        if len(photos) == 1:
            placement = PhotoPlacement(0.50, 0.52, 0.78, -2, 1)
            jitter = (layout_random.random() - 0.5) * 4
            surfaces.append((self._compose_photo(photos[0], placement, jitter), placement))
        else:
            placements = PLACEMENTS.get(len(photos), PLACEMENTS[5])
            for index, photo in enumerate(photos):
                placement_index = _placement_index(len(photos), index)
                placement = placements[placement_index]
                jitter = (layout_random.random() - 0.5) * 4
                rotation = placement.rotation + jitter
                surfaces.append((self._compose_photo(photo, placement, rotation), placement))

        surfaces.sort(key=lambda item: item[1].z_index)
        return surfaces

    def draw(
        self,
        menu: MenuState,
        sync_status: str,
        *,
        syncing: bool = False,
        delta_ms: int = 0,
    ) -> None:
        self._status_anim_ms = (self._status_anim_ms + delta_ms) % 360_000
        self.screen.fill(BG_COLOR)

        if self._empty_message is not None:
            self._draw_empty_state()
        else:
            self._draw_photos()
            self._draw_name()
            self._draw_bio_card()
            self._draw_qr()

        if menu.visible:
            self._draw_menu(menu, sync_status)

        self._draw_status_indicators(syncing=syncing)

        pygame.display.flip()

    def _draw_photos(self) -> None:
        for surface, placement in self._current_surfaces:
            rect = surface.get_rect(
                center=(
                    int(placement.center_x * self.width),
                    int(placement.center_y * self.height),
                )
            )
            self.screen.blit(surface, rect)

    def _compose_photo(self, photo: pygame.Surface, placement: PhotoPlacement, rotation: float) -> pygame.Surface:
        max_side = min(self.width, self.height) * placement.scale
        scale = min(max_side / photo.get_width(), max_side / photo.get_height())
        target = (
            max(1, int(photo.get_width() * scale)),
            max(1, int(photo.get_height() * scale)),
        )

        padding = 12
        border = 2
        pil = Image.frombytes("RGB", photo.get_size(), pygame.image.tobytes(photo, "RGB"))
        pil = pil.resize(target, Image.Resampling.LANCZOS).convert("RGBA")

        frame_w = target[0] + padding * 2 + border * 2
        frame_h = target[1] + padding * 2 + border * 2
        framed = Image.new("RGBA", (frame_w, frame_h), (30, 30, 30, 255))
        inner = Image.new("RGBA", (frame_w - border * 2, frame_h - border * 2), (*WHITE, 255))
        inner.paste(pil, (padding, padding))
        framed.paste(inner, (border, border))

        rotated = framed.rotate(
            rotation,
            resample=Image.Resampling.BICUBIC,
            expand=True,
            fillcolor=(0, 0, 0, 0),
        )
        return pygame.image.frombytes(rotated.tobytes(), rotated.size, "RGBA").convert_alpha()

    def _name_y(self) -> int:
        return max(120, int(self.height * 0.10))

    def _draw_name(self) -> None:
        if not self._current_name:
            return
        font_size = 98 if len(self._current_name) <= 6 else 86 if len(self._current_name) <= 10 else 74
        font = pygame.font.SysFont("DejaVu Sans", font_size, bold=True)
        name_y = self._name_y()
        for dx, dy in ((0, -2), (0, 2), (-2, 0), (2, 0)):
            outline = font.render(self._current_name, True, WHITE)
            rect = outline.get_rect(center=(self.width // 2 + dx, name_y + dy))
            self.screen.blit(outline, rect)
        text = font.render(self._current_name, True, NAVY)
        rect = text.get_rect(center=(self.width // 2, name_y))
        self.screen.blit(text, rect)

    def _draw_bio_card(self) -> None:
        if not self._current_bio.strip():
            return
        lines = self._current_bio.splitlines()
        rendered = [self.bio_font.render(line, True, TEXT_MUTED) for line in lines]
        width = max(surface.get_width() for surface in rendered) + 28
        height = sum(surface.get_height() for surface in rendered) + 16 * (len(rendered) - 1) + 28
        card = pygame.Surface((width, height), pygame.SRCALPHA)
        card.fill(CARD_BG)
        y = 14
        for surface in rendered:
            card.blit(surface, (14, y))
            y += surface.get_height() + 16
        self.screen.blit(card, (36, self.height // 2 - height // 2))

    def _draw_qr(self) -> None:
        if self._current_qr is None:
            return
        qr_size = 175
        scaled = pygame.transform.smoothscale(self._current_qr, (qr_size, qr_size))
        label = self.hint_font.render("Scan to learn more", True, TEXT_MUTED)
        card_w = qr_size + 24
        card_h = qr_size + 24 + label.get_height() + 8
        card = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
        card.fill(CARD_BG)
        card.blit(scaled, (12, 12))
        card.blit(label, (card_w // 2 - label.get_width() // 2, qr_size + 20))
        self.screen.blit(card, (self.width - card_w - 36, self.height - card_h - 36))

    def _draw_status_indicators(self, syncing: bool) -> None:
        loading = self.is_loading()
        if not loading and not syncing:
            return

        badge = 44
        gap = 8
        margin = 18
        x = self.width - margin - badge
        y = margin
        indicators: list[tuple[str, Callable[[pygame.Surface, tuple[int, int], int], None]]] = []
        if syncing:
            indicators.append(("sync", self._draw_sync_icon))
        if loading:
            indicators.append(("loading", self._draw_loading_icon))

        for kind, drawer in indicators:
            self._draw_status_badge(x, y, badge, kind, drawer)
            y += badge + gap

    def _draw_status_badge(
        self,
        x: int,
        y: int,
        size: int,
        kind: str,
        drawer: Callable[[pygame.Surface, tuple[int, int], int], None],
    ) -> None:
        badge = pygame.Surface((size, size), pygame.SRCALPHA)
        badge.fill((250, 250, 248, 220))
        pygame.draw.rect(badge, (210, 218, 228), badge.get_rect(), 1, border_radius=10)
        center = (size // 2, size // 2)
        drawer(badge, center, size - 14)
        self.screen.blit(badge, (x, y))

    def _draw_loading_icon(self, surface: pygame.Surface, center: tuple[int, int], diameter: int) -> None:
        radius = diameter // 2
        angle = (self._status_anim_ms / 1000) * 360
        for tick in range(12):
            tick_angle = math.radians(angle + tick * 30)
            brightness = 70 + int(185 * (tick + 1) / 12)
            color = (brightness, brightness, min(255, brightness + 25))
            inner = radius - 5
            outer = radius
            start = (
                center[0] + inner * math.cos(tick_angle),
                center[1] + inner * math.sin(tick_angle),
            )
            end = (
                center[0] + outer * math.cos(tick_angle),
                center[1] + outer * math.sin(tick_angle),
            )
            pygame.draw.line(surface, color, start, end, 2)

    def _draw_sync_icon(self, surface: pygame.Surface, center: tuple[int, int], diameter: int) -> None:
        radius = diameter // 2
        pulse = 0.65 + 0.35 * math.sin(self._status_anim_ms / 220)
        color = (int(30 + 40 * pulse), int(90 + 50 * pulse), int(150 + 40 * pulse))
        rect = pygame.Rect(center[0] - radius, center[1] - radius, radius * 2, radius * 2)
        start_a = math.radians((self._status_anim_ms / 12) % 360)
        end_a = start_a + math.radians(220)
        pygame.draw.arc(surface, color, rect, start_a, end_a, 3)
        arrow_a = end_a
        tip = (
            center[0] + radius * math.cos(arrow_a),
            center[1] + radius * math.sin(arrow_a),
        )
        wing_a1 = arrow_a + math.radians(150)
        wing_a2 = arrow_a - math.radians(150)
        wing_len = 6
        pygame.draw.polygon(
            surface,
            color,
            [
                tip,
                (tip[0] + wing_len * math.cos(wing_a1), tip[1] + wing_len * math.sin(wing_a1)),
                (tip[0] + wing_len * math.cos(wing_a2), tip[1] + wing_len * math.sin(wing_a2)),
            ],
        )

        inner_rect = pygame.Rect(
            center[0] - radius + 6,
            center[1] - radius + 6,
            (radius - 6) * 2,
            (radius - 6) * 2,
        )
        start_b = math.radians((self._status_anim_ms / 12 + 180) % 360)
        end_b = start_b + math.radians(220)
        pygame.draw.arc(surface, color, inner_rect, start_b, end_b, 3)
        arrow_b = end_b
        tip_b = (
            center[0] + (radius - 6) * math.cos(arrow_b),
            center[1] + (radius - 6) * math.sin(arrow_b),
        )
        wing_b1 = arrow_b + math.radians(150)
        wing_b2 = arrow_b - math.radians(150)
        pygame.draw.polygon(
            surface,
            color,
            [
                tip_b,
                (tip_b[0] + wing_len * math.cos(wing_b1), tip_b[1] + wing_len * math.sin(wing_b1)),
                (tip_b[0] + wing_len * math.cos(wing_b2), tip_b[1] + wing_len * math.sin(wing_b2)),
            ],
        )

    def _draw_empty_state(self) -> None:
        title = self.title_font.render(self._current_name, True, NAVY)
        body = self.bio_font.render(self._current_bio, True, TEXT_MUTED)
        self.screen.blit(title, title.get_rect(center=(self.width // 2, self.height // 2 - 30)))
        self.screen.blit(body, body.get_rect(center=(self.width // 2, self.height // 2 + 30)))

    def _draw_menu(self, menu: MenuState, sync_status: str) -> None:
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))

        panel_w = min(640, self.width - 80)
        panel_h = min(520, self.height - 80)
        panel_x = (self.width - panel_w) // 2
        panel_y = (self.height - panel_h) // 2
        panel = pygame.Surface((panel_w, panel_h))
        panel.fill(CARD_BG)
        self.screen.blit(panel, (panel_x, panel_y))

        title = self.menu_title_font.render("Shelter Pet Viewer", True, NAVY)
        self.screen.blit(title, (panel_x + 24, panel_y + 20))

        y = panel_y + 80
        for index, item in enumerate(menu.current_items):
            selected = index == menu.index
            prefix = "> " if selected else "  "
            check = "[x] " if item.checked else ("[ ] " if item.action.name.startswith("SET_") else "")
            suffix = "  >" if item.submenu else ""
            label = f"{prefix}{check}{item.label}{suffix}"
            color = NAVY if selected else TEXT_MUTED
            if selected:
                highlight = pygame.Surface((panel_w - 48, 36))
                highlight.fill((225, 232, 242))
                self.screen.blit(highlight, (panel_x + 24, y - 4))
            text = self.menu_font.render(label, True, color)
            self.screen.blit(text, (panel_x + 32, y))
            y += 42

        footer_lines = [
            "Back/Forward: move   Menu: select/open   Return: back/close",
        ]
        if menu.status_line:
            footer_lines.insert(0, menu.status_line)
        if sync_status:
            footer_lines.append(sync_status)

        footer_y = panel_y + panel_h - 24 - 20 * len(footer_lines)
        for line in footer_lines:
            text = self.hint_font.render(line, True, TEXT_MUTED)
            self.screen.blit(text, (panel_x + 24, footer_y))
            footer_y += 20

    def _load_photo(self, path: Path) -> pygame.Surface | None:
        key = str(path.resolve())
        try:
            mtime = path.stat().st_mtime_ns
        except OSError:
            return None
        cache_key = f"{key}:{mtime}"
        if cache_key in self._photo_cache:
            return self._photo_cache[cache_key]
        try:
            image = Image.open(path).convert("RGB")
            data = image.tobytes()
            surface = pygame.image.frombytes(data, image.size, "RGB")
            self._photo_cache[cache_key] = surface
            return surface
        except (OSError, pygame.error) as exc:
            log.error("Failed loading image %s: %s", path, exc)
            return None

    def _load_qr(self, animal_id: str) -> pygame.Surface | None:
        if animal_id in self._qr_cache:
            return self._qr_cache[animal_id]
        try:
            url = f"https://new.shelterluv.com/embed/animal/{animal_id}"
            qr = qrcode.make(url)
            buffer = io.BytesIO()
            qr.save(buffer, format="PNG")
            buffer.seek(0)
            image = Image.open(buffer).convert("RGB")
            surface = pygame.image.frombytes(image.tobytes(), image.size, "RGB")
            self._qr_cache[animal_id] = surface
            return surface
        except Exception as exc:
            log.error("Failed creating QR for %s: %s", animal_id, exc)
            return None


def _placement_index(count: int, photo_index: int) -> int:
    if count == 3:
        return {0: 1, 1: 0}.get(photo_index, 2)
    if count == 4:
        return {0: 2, 1: 0, 2: 1}.get(photo_index, 3)
    if count == 5:
        return {0: 2, 1: 0, 2: 1, 3: 3}.get(photo_index, 4)
    return photo_index
