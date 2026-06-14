from __future__ import annotations

import html
import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any
from urllib.parse import urlparse

import requests

from .settings import ViewMode

log = logging.getLogger(__name__)

SHELTER_ID = 38131
USER_AGENT = "ShelterPetViewer-Pi/1.2.0"
ALLOWED_HOST_SUFFIX = ".shelterluv.com"
ALLOWED_HOSTS = {
    "cdn.shelterluv.com",
    "shelterluv.com",
    "new.shelterluv.com",
    "new-s3.shelterluv.com",
    "www.shelterluv.com",
}
MAX_PHOTO_BYTES = 20 * 1024 * 1024
PROMO_TERMS = ("sponsored", "template", "adoption fee")
ANIMAL_JSON_RE = re.compile(r':animal="([^"]+)"', re.DOTALL)


@dataclass
class ShelterPhoto:
    url: str
    name: str = ""
    order_column: int = 0


def is_allowed_photo_url(url: str | None) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    if not host or host == "localhost" or host.startswith("127.") or host.startswith("10.") or host.startswith("192.168."):
        return False
    return host in ALLOWED_HOSTS or host.endswith(ALLOWED_HOST_SUFFIX)


def image_extension(data: bytes) -> str | None:
    if len(data) >= 3 and data[0:3] == b"\xff\xd8\xff":
        return "jpg"
    if len(data) >= 8 and data[0:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    return None


def sanitize_id(unique_id: str | None) -> str | None:
    if not unique_id or not unique_id.strip():
        return None
    cleaned = "".join(ch for ch in unique_id if ch not in '<>:"/\\|?*')
    cleaned = cleaned.strip()
    if not cleaned or cleaned in {".", ".."}:
        return None
    return cleaned


def select_photos(raw_photos: list[dict[str, Any]], max_photos: int = 5) -> list[ShelterPhoto]:
    photos: list[ShelterPhoto] = []
    for item in raw_photos:
        name = str(item.get("name") or item.get("Name") or "")
        lower = name.lower()
        if any(term in lower for term in PROMO_TERMS):
            continue
        url = str(item.get("url") or item.get("Url") or "")
        order = int(item.get("order_column") or item.get("OrderColumn") or 0)
        if url:
            photos.append(ShelterPhoto(url=url, name=name, order_column=order))
    photos.sort(key=lambda p: p.order_column)
    return photos[:max_photos]


def format_weight(summary: dict[str, Any], detail: dict[str, Any] | None) -> str:
    weight = detail.get("weight") if detail else None
    if isinstance(weight, (int, float)) and weight > 0:
        units = str(detail.get("weightUnits") or detail.get("WeightUnits") or "lb").strip() or "lb"
        value = str(int(weight)) if float(weight).is_integer() else f"{float(weight):.1f}".rstrip("0").rstrip(".")
        return f"{value} {units}"
    for key in ("weightGroup", "WeightGroup"):
        if detail and detail.get(key):
            return str(detail[key])
        if summary.get(key):
            return str(summary[key])
    return ""


def format_age(summary: dict[str, Any], detail: dict[str, Any] | None) -> str:
    birthday = None
    if detail:
        birthday = detail.get("birthday") or detail.get("Birthday")
    from_birthday = _format_age_from_birthday(str(birthday) if birthday else "")
    if from_birthday:
        return from_birthday

    age_group = None
    if detail:
        age_group = detail.get("ageGroup") or detail.get("AgeGroup")
    if not age_group:
        age_group = summary.get("ageGroup") or summary.get("AgeGroup")
    if not age_group:
        return ""
    return _format_age_group(age_group if isinstance(age_group, dict) else {})


def _format_age_from_birthday(birthday: str) -> str:
    if not birthday.isdigit():
        return ""
    birth_date = datetime.fromtimestamp(int(birthday), tz=timezone.utc).date()
    today = date.today()
    if birth_date > today:
        return ""

    years = today.year - birth_date.year
    months = today.month - birth_date.month
    if today.day < birth_date.day:
        months -= 1
    if months < 0:
        years -= 1
        months += 12

    if years >= 2:
        return f"{years} years"
    if years == 1:
        return "1 year"
    if months >= 2:
        return f"{months} months"
    if months == 1:
        return "1 month"

    days = (today - birth_date).days
    if days >= 14:
        weeks = days // 7
        return "1 week" if weeks == 1 else f"{weeks} weeks"
    return "1 day" if days <= 1 else f"{days} days"


def _format_age_group(age_group: dict[str, Any]) -> str:
    duration = str(age_group.get("duration") or age_group.get("Duration") or "").strip().strip("()")
    name = str(age_group.get("name") or age_group.get("Name") or "").strip()
    if duration and name:
        return f"{name} {duration}"
    name_with = str(age_group.get("nameWithDuration") or age_group.get("NameWithDuration") or "").strip()
    if name_with:
        return name_with.replace(" (", " ").rstrip(")")
    return name


class ShelterLuvClient:
    def __init__(self, session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()
        self._session.headers.setdefault("User-Agent", USER_AGENT)

    def fetch_animals(self, mode: ViewMode) -> list[dict[str, Any]]:
        queries = (
            ["?animalType=Dog", "?animalType=Cat"]
            if mode == ViewMode.ADOPTION
            else ["?saved_query=5398", "?saved_query=5397"]
        )
        by_id: dict[str, dict[str, Any]] = {}
        for query in queries:
            url = f"https://new.shelterluv.com/api/v3/available-animals/{SHELTER_ID}{query}"
            log.info("Fetching %s", url)
            response = self._session.get(url, timeout=120)
            response.raise_for_status()
            payload = response.json()
            animals = payload.get("animals") or payload.get("Animals") or []
            log.info("Received %d animals for %s", len(animals), query)
            for animal in animals:
                unique_id = animal.get("uniqueId") or animal.get("UniqueId")
                if unique_id:
                    by_id[str(unique_id)] = animal
        return list(by_id.values())

    def fetch_detail(self, unique_id: str) -> dict[str, Any] | None:
        url = f"https://new.shelterluv.com/embed/animal/{requests.utils.quote(unique_id, safe='')}"
        try:
            response = self._session.get(url, timeout=120)
            response.raise_for_status()
            match = ANIMAL_JSON_RE.search(response.text)
            if not match:
                log.error("Could not find animal JSON in embed page for %s", unique_id)
                return None
            return json.loads(html.unescape(match.group(1)))
        except (requests.RequestException, json.JSONDecodeError) as exc:
            log.error("Failed to fetch details for %s: %s", unique_id, exc)
            return None

    @staticmethod
    def photos_from_animal(animal: dict[str, Any]) -> list[dict[str, Any]]:
        photos = animal.get("photos") or animal.get("Photos") or []
        if isinstance(photos, dict):
            return list(photos.values())
        return photos if isinstance(photos, list) else []


def has_internet(session: requests.Session | None = None) -> bool:
    client = session or requests.Session()
    try:
        response = client.get("https://new.shelterluv.com/", timeout=8)
        return response.status_code < 500
    except requests.RequestException:
        return False
