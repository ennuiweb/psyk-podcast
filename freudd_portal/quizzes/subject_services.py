"""Subject catalog + reading-key parsing utilities for freudd portal."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

SUBJECT_SLUG_RE = re.compile(r"^[a-z0-9-]+$")
LECTURE_HEADING_RE = re.compile(r"^\*\*(?P<key>W\d{2}L\d+)\s+(?P<title>.+?)\*\*$")
MISSING_READING_RE = re.compile(r"^MISSING:\s*(?P<title>.+)$", re.IGNORECASE)
BRIEF_SUFFIX_RE = re.compile(r"\s*\([^)]*\bbrief\b[^)]*\)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class SubjectDefinition:
    slug: str
    title: str
    description: str
    active: bool


@dataclass(frozen=True)
class SubjectCatalog:
    subjects: tuple[SubjectDefinition, ...]
    error: str | None = None

    def active_subject_by_slug(self, slug: str) -> SubjectDefinition | None:
        candidate = (slug or "").strip().lower()
        for subject in self.subjects:
            if subject.active and subject.slug == candidate:
                return subject
        return None

    @property
    def active_subjects(self) -> tuple[SubjectDefinition, ...]:
        return tuple(subject for subject in self.subjects if subject.active)


@dataclass(frozen=True)
class ReadingItem:
    title: str
    is_missing: bool
    source_filename: str | None


@dataclass(frozen=True)
class ReadingLecture:
    key: str
    heading: str
    readings: tuple[ReadingItem, ...]


@dataclass(frozen=True)
class ReadingParseResult:
    lectures: tuple[ReadingLecture, ...]
    error: str | None = None


_SUBJECT_CATALOG_CACHE: dict[str, Any] = {"path": None, "mtime": None, "data": None}
_READING_PARSE_CACHE: dict[str, Any] = {"path": None, "mtime": None, "data": None}


def clear_subject_service_caches() -> None:
    _SUBJECT_CATALOG_CACHE["path"] = None
    _SUBJECT_CATALOG_CACHE["mtime"] = None
    _SUBJECT_CATALOG_CACHE["data"] = None
    _READING_PARSE_CACHE["path"] = None
    _READING_PARSE_CACHE["mtime"] = None
    _READING_PARSE_CACHE["data"] = None


def _default_catalog(error: str | None = None) -> SubjectCatalog:
    return SubjectCatalog(subjects=tuple(), error=error)


def _normalize_subjects(raw_values: Any) -> tuple[SubjectDefinition, ...]:
    if not isinstance(raw_values, list):
        return tuple()

    subjects: list[SubjectDefinition] = []
    seen_slugs: set[str] = set()
    for entry in raw_values:
        if not isinstance(entry, dict):
            continue

        raw_slug = entry.get("slug")
        if not isinstance(raw_slug, str):
            continue
        slug = raw_slug.strip().lower()
        if not SUBJECT_SLUG_RE.match(slug):
            logger.warning("Skipping subject with invalid slug: %r", raw_slug)
            continue
        if slug in seen_slugs:
            logger.warning("Skipping duplicate subject slug: %s", slug)
            continue

        raw_title = entry.get("title")
        title = raw_title.strip() if isinstance(raw_title, str) and raw_title.strip() else slug

        raw_description = entry.get("description")
        description = raw_description.strip() if isinstance(raw_description, str) else ""
        active = bool(entry.get("active", True))

        subjects.append(
            SubjectDefinition(
                slug=slug,
                title=title,
                description=description,
                active=active,
            )
        )
        seen_slugs.add(slug)

    return tuple(subjects)


def load_subject_catalog() -> SubjectCatalog:
    path = Path(settings.FREUDD_SUBJECTS_JSON_PATH)
    if not path.exists():
        return _default_catalog(error="Fagkataloget kunne ikke indlæses.")

    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        logger.warning("Unable to stat subject catalog: %s", path, exc_info=True)
        return _default_catalog(error="Fagkataloget kunne ikke indlæses.")

    cache_hit = (
        _SUBJECT_CATALOG_CACHE.get("path") == str(path)
        and _SUBJECT_CATALOG_CACHE.get("mtime") == mtime
        and isinstance(_SUBJECT_CATALOG_CACHE.get("data"), SubjectCatalog)
    )
    if cache_hit:
        return _SUBJECT_CATALOG_CACHE["data"]

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("catalog root must be an object")
        if payload.get("version") != 1:
            raise ValueError("unsupported catalog version")

        catalog = SubjectCatalog(
            subjects=_normalize_subjects(payload.get("subjects")),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        logger.warning("Unable to parse subject catalog: %s", path, exc_info=True)
        catalog = _default_catalog(error="Fagkataloget kunne ikke indlæses.")

    _SUBJECT_CATALOG_CACHE["path"] = str(path)
    _SUBJECT_CATALOG_CACHE["mtime"] = mtime
    _SUBJECT_CATALOG_CACHE["data"] = catalog
    return catalog


def _reading_title_from_bullet(bullet_body: str) -> str:
    if "→" in bullet_body:
        return bullet_body.split("→", 1)[0].strip()
    return bullet_body.strip()


def _source_filename_from_bullet(bullet_body: str) -> str | None:
    if "→" not in bullet_body:
        return None
    right = bullet_body.split("→", 1)[1].strip()
    if not right:
        return None
    cleaned = BRIEF_SUFFIX_RE.sub("", right).strip()
    return cleaned or None


def parse_master_readings(path: str | Path) -> ReadingParseResult:
    source = Path(path)
    if not source.exists():
        return ReadingParseResult(lectures=tuple(), error="Reading-nøglen kunne ikke indlæses.")

    try:
        mtime = source.stat().st_mtime_ns
    except OSError:
        logger.warning("Unable to stat reading key path: %s", source, exc_info=True)
        return ReadingParseResult(lectures=tuple(), error="Reading-nøglen kunne ikke indlæses.")

    cache_hit = (
        _READING_PARSE_CACHE.get("path") == str(source)
        and _READING_PARSE_CACHE.get("mtime") == mtime
        and isinstance(_READING_PARSE_CACHE.get("data"), ReadingParseResult)
    )
    if cache_hit:
        return _READING_PARSE_CACHE["data"]

    try:
        raw_text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        logger.warning("Unable to read reading key path: %s", source, exc_info=True)
        return ReadingParseResult(lectures=tuple(), error="Reading-nøglen kunne ikke indlæses.")

    parsed_lectures: list[dict[str, Any]] = []
    current_lecture: dict[str, Any] | None = None

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        lecture_match = LECTURE_HEADING_RE.match(line)
        if lecture_match:
            lecture_key = lecture_match.group("key")
            lecture_title = lecture_match.group("title").strip()
            current_lecture = {
                "key": lecture_key,
                "heading": f"{lecture_key} {lecture_title}",
                "readings": [],
            }
            parsed_lectures.append(current_lecture)
            continue

        if current_lecture is None or not line.startswith("- "):
            continue

        bullet_body = line[2:].strip()
        if not bullet_body:
            continue

        missing_match = MISSING_READING_RE.match(bullet_body)
        if missing_match:
            missing_title = missing_match.group("title").strip()
            if missing_title:
                current_lecture["readings"].append(
                    ReadingItem(
                        title=missing_title,
                        is_missing=True,
                        source_filename=None,
                    )
                )
            continue

        reading_title = _reading_title_from_bullet(bullet_body)
        if not reading_title:
            continue
        current_lecture["readings"].append(
            ReadingItem(
                title=reading_title,
                is_missing=False,
                source_filename=_source_filename_from_bullet(bullet_body),
            )
        )

    lectures = tuple(
        ReadingLecture(
            key=str(entry["key"]),
            heading=str(entry["heading"]),
            readings=tuple(entry["readings"]),
        )
        for entry in parsed_lectures
    )
    result = ReadingParseResult(lectures=lectures)
    _READING_PARSE_CACHE["path"] = str(source)
    _READING_PARSE_CACHE["mtime"] = mtime
    _READING_PARSE_CACHE["data"] = result
    return result
