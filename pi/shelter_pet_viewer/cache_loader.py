from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .settings import SpeciesFilter, ViewMode


@dataclass(frozen=True)
class CachedAnimal:
    id: str
    name: str
    species: str
    sex: str
    weight: str
    breed: str
    age: str
    photo_paths: list[Path]


_ID_SUFFIX = re.compile(
    r"\s+\*{0,2}\s*([A-Z]\d{4,6})\*{0,2}(?:\s+\((?P<note>[^)]+)\))?\s*$",
    re.IGNORECASE,
)


def parse_display_name(full_name: str) -> str:
    trimmed = full_name.strip()
    match = _ID_SUFFIX.search(trimmed)
    if not match:
        return trimmed.strip("*").strip()
    return trimmed[: match.start()].strip().strip("*").strip()


def title_case(value: str) -> str:
    if not value.strip():
        return value
    return value.title()


def format_card_text(animal: CachedAnimal) -> str:
    lines: list[str] = []
    if animal.sex.strip():
        lines.append(animal.sex.strip())
    if animal.age.strip():
        lines.append(animal.age.strip())
    if animal.weight.strip():
        weight = animal.weight.strip()
        if weight.lower().endswith(" lbs"):
            weight = weight[:-1]
        lines.append(weight)
    return "\n".join(lines)


def _is_bio_format(lines: list[str]) -> bool:
    if len(lines) < 6:
        return False
    sex = lines[2].strip().lower()
    return sex in {"male", "female", "unknown"}


def _parse_info_file(info_path: Path) -> CachedAnimal | None:
    try:
        lines = info_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    if len(lines) < 2:
        return None

    name, species = lines[0], lines[1]
    if len(lines) >= 6 and _is_bio_format(lines):
        sex, weight, breed, age = lines[2], lines[3], lines[4], lines[5]
    else:
        sex = weight = breed = age = ""

    animal_dir = info_path.parent
    photos = _photo_paths(animal_dir)
    if not photos:
        return None

    return CachedAnimal(
        id=animal_dir.name,
        name=name,
        species=species,
        sex=sex,
        weight=weight,
        breed=breed,
        age=age,
        photo_paths=photos,
    )


def _photo_paths(animal_dir: Path) -> list[Path]:
    paths: list[tuple[int, Path]] = []
    for path in animal_dir.iterdir():
        if not path.is_file():
            continue
        if ".downloading" in path.name.lower():
            continue
        lower = path.name.lower()
        if not (lower.endswith(".jpg") or lower.endswith(".jpeg") or lower.endswith(".png")):
            continue
        stem = path.stem
        order = int(stem) if stem.isdigit() else 10_000
        paths.append((order, path))
    paths.sort(key=lambda item: item[0])
    return [path for _, path in paths[:5]]


def matches_species_filter(species: str, species_filter: SpeciesFilter) -> bool:
    if species_filter == SpeciesFilter.ALL:
        return True
    normalized = species.strip().lower()
    if species_filter == SpeciesFilter.DOGS:
        return normalized in {"dog", "dogs"}
    if species_filter == SpeciesFilter.CATS:
        return normalized in {"cat", "cats"}
    return True


def load_cached_animals(
    mode: ViewMode,
    cache_root: Path,
    species_filter: SpeciesFilter = SpeciesFilter.ALL,
) -> list[CachedAnimal]:
    mode_dir = cache_root / mode.value.lower()
    if not mode_dir.is_dir():
        return []

    animals: list[CachedAnimal] = []
    for animal_dir in sorted(mode_dir.iterdir()):
        if not animal_dir.is_dir():
            continue
        info_path = animal_dir / "info.txt"
        if not info_path.is_file():
            continue
        animal = _parse_info_file(info_path)
        if animal is not None and matches_species_filter(animal.species, species_filter):
            animals.append(animal)
    return animals
