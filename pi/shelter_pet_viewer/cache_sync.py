from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

import requests

from .shelter_api import (
    ShelterLuvClient,
    format_age,
    format_weight,
    image_extension,
    is_allowed_photo_url,
    sanitize_id,
    select_photos,
)
from .settings import ViewMode

log = logging.getLogger(__name__)


@dataclass
class CacheSyncResult:
    total: int
    added: int
    updated: int
    removed: int
    skipped: int = 0


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def _build_info_content(name: str, species: str, sex: str, weight: str, breed: str, age: str) -> str:
    return "\n".join([name, species, sex, weight, breed, age]) + "\n"


def _mode_dir(cache_root: Path, mode: ViewMode) -> Path:
    return cache_root / mode.value.lower()


def _resolve_animal_dir(cache_root: Path, mode: ViewMode, animal_id: str) -> Path | None:
    mode_dir = _mode_dir(cache_root, mode)
    candidate = (mode_dir / animal_id).resolve()
    root = cache_root.resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _cached_photo_paths(animal_dir: Path) -> list[Path]:
    paths: list[tuple[int, Path]] = []
    for path in animal_dir.iterdir():
        if not path.is_file():
            continue
        lower = path.name.lower()
        if lower.endswith((".jpg", ".jpeg", ".png")) and ".downloading" not in lower:
            order = int(path.stem) if path.stem.isdigit() else 10_000
            paths.append((order, path))
    paths.sort(key=lambda item: item[0])
    return [path for _, path in paths]


def _photo_file_exists(animal_dir: Path, index: int) -> bool:
    return (animal_dir / f"{index + 1}.jpg").exists() or (animal_dir / f"{index + 1}.png").exists()


def _photos_are_current(animal_dir: Path, photos: list) -> bool:
    manifest_path = animal_dir / "photos.json"
    if not photos or not manifest_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(manifest, list) or len(manifest) != len(photos):
        return False
    for index, photo in enumerate(photos):
        entry_url = manifest[index].get("Url") or manifest[index].get("url")
        if entry_url != photo.url:
            return False
        if not _photo_file_exists(animal_dir, index):
            return False
    return True


def _delete_cached_photos(animal_dir: Path) -> None:
    for path in _cached_photo_paths(animal_dir):
        path.unlink(missing_ok=True)


def _download_photos(session: requests.Session, animal_dir: Path, photos: list) -> bool:
    temp_files: list[tuple[Path, str]] = []
    try:
        for index, photo in enumerate(photos):
            if not is_allowed_photo_url(photo.url):
                log.error("Rejected photo URL: %s", photo.url)
                continue
            temp_path = animal_dir / f"{index + 1}.tmp.downloading"
            try:
                response = session.get(photo.url, timeout=120)
                response.raise_for_status()
                data = response.content
                if not data or len(data) > 20 * 1024 * 1024:
                    log.error("Rejected photo size from %s", photo.url)
                    continue
                ext = image_extension(data)
                if not ext:
                    log.error("Rejected unsupported image from %s", photo.url)
                    continue
                _atomic_write_bytes(temp_path, data)
                temp_files.append((temp_path, ext))
            except requests.RequestException as exc:
                log.error("Failed downloading photo from %s: %s", photo.url, exc)
                temp_path.unlink(missing_ok=True)

        if not temp_files:
            return _cached_photo_paths(animal_dir) != []

        _delete_cached_photos(animal_dir)
        for index, (temp_path, ext) in enumerate(temp_files):
            final_path = animal_dir / f"{index + 1}.{ext}"
            temp_path.replace(final_path)

        manifest = [{"Url": photo.url} for photo in photos[: len(temp_files)]]
        _atomic_write_text(animal_dir / "photos.json", json.dumps(manifest))
        return True
    finally:
        for temp_path, _ in temp_files:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)


def sync_mode(
    cache_root: Path,
    mode: ViewMode,
    client: ShelterLuvClient,
    session: requests.Session,
) -> CacheSyncResult:
    cache_root.mkdir(parents=True, exist_ok=True)
    mode_dir = _mode_dir(cache_root, mode)
    mode_dir.mkdir(parents=True, exist_ok=True)

    remote_animals = client.fetch_animals(mode)
    remote_ids = set()
    for animal in remote_animals:
        unique_id = animal.get("uniqueId") or animal.get("UniqueId")
        sanitized = sanitize_id(str(unique_id) if unique_id else None)
        if sanitized:
            remote_ids.add(sanitized)

    removed = 0
    for existing in list(mode_dir.iterdir()):
        if existing.is_dir() and existing.name not in remote_ids:
            shutil.rmtree(existing, ignore_errors=True)
            removed += 1

    added = updated = skipped = 0
    for animal in remote_animals:
        unique_id = str(animal.get("uniqueId") or animal.get("UniqueId") or "")
        animal_id = sanitize_id(unique_id)
        if not animal_id:
            skipped += 1
            continue

        animal_dir = _resolve_animal_dir(cache_root, mode, animal_id)
        if animal_dir is None:
            skipped += 1
            continue

        is_new = not animal_dir.exists()
        animal_dir.mkdir(parents=True, exist_ok=True)

        detail = client.fetch_detail(unique_id)
        raw_photos = client.photos_from_animal(detail or animal)
        photos = select_photos(raw_photos)

        name = str((detail or {}).get("name") or (detail or {}).get("Name") or animal.get("name") or animal.get("Name") or "")
        species = str((detail or {}).get("species") or (detail or {}).get("Species") or animal.get("species") or animal.get("Species") or "")
        sex = str((detail or {}).get("sex") or (detail or {}).get("Sex") or animal.get("sex") or animal.get("Sex") or "")
        breed = str((detail or {}).get("breed") or (detail or {}).get("Breed") or animal.get("breed") or animal.get("Breed") or "")
        weight = format_weight(animal, detail)
        age = format_age(animal, detail)
        info_content = _build_info_content(name, species, sex, weight, breed, age)

        photos_changed = False if _photos_are_current(animal_dir, photos) else _download_photos(session, animal_dir, photos)

        if is_new and not photos_changed:
            skipped += 1
            if not any(animal_dir.iterdir()):
                shutil.rmtree(animal_dir, ignore_errors=True)
            continue

        if not photos_changed and animal_dir.joinpath("info.txt").exists():
            if animal_dir.joinpath("info.txt").read_text(encoding="utf-8") == info_content:
                continue

        _atomic_write_text(animal_dir / "info.txt", info_content)
        if is_new:
            added += 1
        else:
            updated += 1

    return CacheSyncResult(total=len(remote_animals), added=added, updated=updated, removed=removed, skipped=skipped)


def sync_all(cache_root: Path) -> tuple[CacheSyncResult, CacheSyncResult]:
    session = requests.Session()
    session.headers.setdefault("User-Agent", "ShelterPetViewer-Pi/1.2.0")
    client = ShelterLuvClient(session)
    adoption = sync_mode(cache_root, ViewMode.ADOPTION, client, session)
    foster = sync_mode(cache_root, ViewMode.FOSTER, client, session)
    return adoption, foster
