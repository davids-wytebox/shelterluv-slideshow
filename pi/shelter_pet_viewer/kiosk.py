from __future__ import annotations

import io
import logging
import random
import threading
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
        self._current_surfaces: list[tuple[pygame.Surface, PhotoPlacement]] = []
        self._current_name = ""
        self._current_bio = ""
        self._current_qr: pygame.Surface | None = None
        self._empty_message: str | None = None

    def close(self) -> None:
        pygame.quit()

    def set_empty(self, message: str) -> None:
        self._empty_message = message
        self._current_surfaces.clear()
        self._current_name = "No cached animals"
        self._current_bio = message
        self._current_qr = None

    def clear_layout_cache(self) -> None:
        with self._layout_lock:
            self._layout_cache.clear()
        self._photo_cache.clear()

    def prewarm_animals(self, animals: list[CachedAnimal]) -> None:
        def run() -> None:
            warmed = 0
            for animal in animals:
                if self._prewarm_animal(animal):
                    warmed += 1
            log.info("Prewarmed slide layouts for %d/%d animals.", warmed, len(animals))

        threading.Thread(target=run, name="layout-prewarm", daemon=True).start()

    def show_animal(self, animal: CachedAnimal | None) -> None:
        if animal is None:
            self.set_empty("Use Update Cache in the menu while online.")
            return

        cache_key = self._layout_key(animal.id)
        with self._layout_lock:
            surfaces = self._layout_cache.get(cache_key)

        if surfaces is None:
            surfaces = self._build_surfaces(animal)
            with self._layout_lock:
                self._layout_cache[cache_key] = surfaces

        self._apply_animal(animal, surfaces)

    def _layout_key(self, animal_id: str) -> str:
        return f"{animal_id}:{self.width}x{self.height}"

    def _prewarm_animal(self, animal: CachedAnimal) -> bool:
        cache_key = self._layout_key(animal.id)
        with self._layout_lock:
            if cache_key in self._layout_cache:
                return False
        try:
            surfaces = self._build_surfaces(animal)
        except Exception:
            log.exception("Failed prewarming layout for %s", animal.id)
            return False
        with self._layout_lock:
            if cache_key not in self._layout_cache:
                self._layout_cache[cache_key] = surfaces
        return True

    def _apply_animal(
        self,
        animal: CachedAnimal,
        surfaces: list[tuple[pygame.Surface, PhotoPlacement]],
    ) -> None:
        self._empty_message = None
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

    def draw(self, menu: MenuState, sync_status: str) -> None:
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
