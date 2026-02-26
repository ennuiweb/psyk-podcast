"""Content manifest services for lecture-first subject tracking."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from django.conf import settings
from django.utils import timezone

from .subject_services import parse_master_readings

logger = logging.getLogger(__name__)

SubjectContentManifest = dict[str, Any]

LECTURE_KEY_RE = re.compile(r"\bW(?P<week>\d{1,2})L(?P<lecture>\d+)\b", re.IGNORECASE)
SEMESTER_LECTURE_RE = re.compile(r"^\s*U(?P<week>\d{1,2})F(?P<lecture>\d+)\s*$", re.IGNORECASE)
DANISH_LECTURE_RE = re.compile(
    r"^\s*uge\s*(?P<week>\d{1,2})\s*,?\s*forel(?:æ|ae)sning\s*(?P<lecture>\d+)\s*$",
    re.IGNORECASE,
)
QUIZ_ID_RE = re.compile(r"(?P<id>[0-9a-f]{8})\.html$", re.IGNORECASE)
CFG_TAG_RE = re.compile(
    r"(?:\s+\{[a-z0-9._:+-]+=[^{}\s]+(?:\s+[a-z0-9._:+-]+=[^{}\s]+)*\})+"
    r"(?:\s+\[[^\[\]]+\])?$",
    re.IGNORECASE,
)
READING_PREFIX_RE = re.compile(r"^(?:W\d{1,2}L\d+\s*(?:-|X)?\s*)", re.IGNORECASE)
LANGUAGE_TAG_RE = re.compile(r"\[[^\]]+\]")
ALL_SOURCES_RE = re.compile(r"\b(?:alle kilder|all sources)\b", re.IGNORECASE)
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
MULTISPACE_RE = re.compile(r"\s+")
SPOTIFY_EPISODE_URL_RE = re.compile(
    r"^https://open\.spotify\.com/episode/[A-Za-z0-9]+(?:[/?#].*)?$",
    re.IGNORECASE,
)
MANIFEST_VERSION = 1

_MANIFEST_CACHE: dict[str, Any] = {
    "path": None,
    "mtime": None,
    "subject_slug": None,
    "data": None,
}


def clear_content_service_caches() -> None:
    _MANIFEST_CACHE["path"] = None
    _MANIFEST_CACHE["mtime"] = None
    _MANIFEST_CACHE["subject_slug"] = None
    _MANIFEST_CACHE["data"] = None


def _lecture_key_from_text(value: str) -> str | None:
    match = LECTURE_KEY_RE.search(value or "")
    if match:
        week = int(match.group("week"))
        lecture = int(match.group("lecture"))
        return f"W{week:02d}L{lecture}"
    compact_match = SEMESTER_LECTURE_RE.match((value or "").strip())
    if compact_match:
        week = int(compact_match.group("week"))
        lecture = int(compact_match.group("lecture"))
        return f"W{week:02d}L{lecture}"
    danish_match = DANISH_LECTURE_RE.match((value or "").strip())
    if danish_match:
        week = int(danish_match.group("week"))
        lecture = int(danish_match.group("lecture"))
        return f"W{week:02d}L{lecture}"
    return None


def _strip_cfg_tag_suffix(value: str) -> str:
    return CFG_TAG_RE.sub("", value or "").strip()


def _strip_episode_extension(value: str) -> str:
    path = Path(value or "")
    suffix = "".join(path.suffixes)
    if not suffix:
        return value
    return value[: -len(suffix)]


def _descriptor_from_episode_name(value: str) -> str:
    cleaned = _strip_cfg_tag_suffix(_strip_episode_extension(value))
    cleaned = LANGUAGE_TAG_RE.sub("", cleaned).strip()
    cleaned = READING_PREFIX_RE.sub("", cleaned).strip()
    cleaned = re.sub(r"^(?:missing)\s+", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned


def _normalize_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.lower().replace("&", " and ")
    normalized = _strip_cfg_tag_suffix(normalized)
    normalized = LANGUAGE_TAG_RE.sub(" ", normalized)
    normalized = normalized.replace("–", "-").replace("—", "-").replace("/", " ").replace("_", " ")
    normalized = re.sub(r"\bgrundbog\s+kapitel\s+0*(\d+)\b", r"grundbog kapitel \1", normalized)
    normalized = NON_ALNUM_RE.sub(" ", normalized)
    normalized = MULTISPACE_RE.sub(" ", normalized).strip()
    for token in ("missing ", "x "):
        if normalized.startswith(token):
            normalized = normalized[len(token) :].strip()
    normalized = re.sub(r"^w\d{1,2}l\d+\s*", "", normalized)
    return normalized.strip()


def _reading_key(lecture_key: str, reading_title: str) -> str:
    normalized = _normalize_title(reading_title)
    slug = NON_ALNUM_RE.sub("-", normalized).strip("-")[:48] or "reading"
    digest = hashlib.sha1(f"{lecture_key}|{normalized}".encode("utf-8")).hexdigest()[:8]
    return f"{lecture_key.lower()}-{slug}-{digest}"


def _lecture_title_from_heading(lecture_key: str, heading: str) -> str:
    value = str(heading or "").strip()
    if value.upper().startswith(lecture_key.upper()):
        value = value[len(lecture_key) :].strip()
    return value.lstrip("-").strip() or lecture_key


def _reading_source_with_fallback() -> tuple[Any, Path | None, bool]:
    primary = Path(settings.FREUDD_READING_MASTER_KEY_PATH)
    fallback = Path(settings.FREUDD_READING_MASTER_KEY_FALLBACK_PATH)

    primary_result = parse_master_readings(primary)
    if not primary_result.error:
        return primary_result, primary, False

    if fallback != primary and fallback.exists():
        fallback_result = parse_master_readings(fallback)
        if not fallback_result.error:
            logger.warning(
                "Using fallback reading key source because primary failed: %s", primary
            )
            return fallback_result, fallback, True

    return primary_result, primary if primary.exists() else None, False


def _quiz_asset_from_link(entry_name: str, link: dict[str, Any]) -> dict[str, Any] | None:
    relative_path = str(link.get("relative_path") or "").strip()
    match = QUIZ_ID_RE.search(relative_path)
    if not match:
        return None
    quiz_id = match.group("id").lower()
    return {
        "quiz_id": quiz_id,
        "difficulty": str(link.get("difficulty") or "medium").strip().lower() or "medium",
        "quiz_url": f"/q/{quiz_id}.html",
        "episode_title": entry_name,
    }


def _podcast_kind_from_token(value: str) -> str:
    token = str(value or "").strip().lower()
    token = token.strip("[]() ")
    if "kort podcast" in token:
        return "short_podcast"
    if "lydbog" in token:
        return "lydbog"
    if "podcast" in token:
        return "podcast"
    return "audio"


def _is_lecture_level_descriptor(value: str) -> bool:
    return bool(ALL_SOURCES_RE.search(value or ""))


def _find_reading_index(lecture_state: dict[str, Any], descriptor: str) -> int | None:
    normalized_descriptor = _normalize_title(descriptor)
    if not normalized_descriptor:
        return None

    lookup: dict[str, list[int]] = lecture_state["reading_lookup"]
    exact_matches = lookup.get(normalized_descriptor, [])
    if len(exact_matches) == 1:
        return exact_matches[0]
    if len(exact_matches) > 1:
        return None

    fuzzy_matches: list[int] = []
    for normalized_title, indexes in lookup.items():
        if normalized_descriptor in normalized_title or normalized_title in normalized_descriptor:
            fuzzy_matches.extend(indexes)
    fuzzy_matches = sorted(set(fuzzy_matches))
    if len(fuzzy_matches) == 1:
        return fuzzy_matches[0]
    return None


def _load_quiz_links_by_name(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("Unable to parse quiz links for manifest build: %s", path, exc_info=True)
        return {}
    if not isinstance(payload, dict):
        return {}
    by_name = payload.get("by_name")
    if not isinstance(by_name, dict):
        return {}
    return by_name


def _attach_quizzes(
    *,
    lectures: list[dict[str, Any]],
    lecture_index: dict[str, int],
    subject_slug: str,
    quiz_links_path: Path,
    manifest_warnings: list[str],
) -> None:
    by_name = _load_quiz_links_by_name(quiz_links_path)
    for entry_name, entry in by_name.items():
        if not isinstance(entry_name, str) or not isinstance(entry, dict):
            continue

        entry_subject_slug = str(entry.get("subject_slug") or "").strip().lower()
        if entry_subject_slug and entry_subject_slug != subject_slug:
            continue

        lecture_key = _lecture_key_from_text(entry_name)
        if not lecture_key or lecture_key not in lecture_index:
            manifest_warnings.append(f"Quiz entry has unknown lecture mapping: {entry_name}")
            continue

        lecture_state = lectures[lecture_index[lecture_key]]
        descriptor = _descriptor_from_episode_name(entry_name)
        if not descriptor:
            lecture_state["warnings"].append(f"Quiz entry missing descriptor: {entry_name}")
            continue

        raw_links = entry.get("links") if isinstance(entry.get("links"), list) else [entry]
        quiz_assets: list[dict[str, Any]] = []
        for raw_link in raw_links:
            if not isinstance(raw_link, dict):
                continue
            quiz_asset = _quiz_asset_from_link(entry_name, raw_link)
            if quiz_asset is not None:
                quiz_assets.append(quiz_asset)

        if not quiz_assets:
            lecture_state["warnings"].append(f"Quiz entry has no valid quiz links: {entry_name}")
            continue

        if _is_lecture_level_descriptor(descriptor):
            lecture_state["lecture_assets"]["quizzes"].extend(quiz_assets)
            continue

        reading_index = _find_reading_index(lecture_state, descriptor)
        if reading_index is None:
            lecture_state["warnings"].append(
                f"Quiz entry could not map to reading; attached to lecture assets: {entry_name}"
            )
            lecture_state["lecture_assets"]["quizzes"].extend(quiz_assets)
            continue
        lecture_state["readings"][reading_index]["assets"]["quizzes"].extend(quiz_assets)


def _find_enclosure_url(item_node: ElementTree.Element) -> str:
    enclosure = item_node.find("enclosure")
    if enclosure is not None:
        url = str(enclosure.attrib.get("url") or "").strip()
        if url:
            return url
    link_text = str(item_node.findtext("link") or "").strip()
    return link_text


def _normalize_rss_title_key(value: str) -> str:
    return MULTISPACE_RE.sub(" ", str(value or "")).strip()


def _load_spotify_map(
    *,
    path: Path,
    subject_slug: str,
    manifest_warnings: list[str],
) -> dict[str, str]:
    if not path.exists():
        manifest_warnings.append(f"Spotify map source missing: {path}")
        return {}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("Unable to parse Spotify map for manifest build: %s", path, exc_info=True)
        manifest_warnings.append(f"Spotify map source could not be parsed: {path}")
        return {}

    if not isinstance(payload, dict):
        manifest_warnings.append(f"Spotify map source must be a JSON object: {path}")
        return {}

    raw_version = payload.get("version")
    if raw_version != 1:
        manifest_warnings.append(f"Spotify map has unsupported version ({raw_version!r}): {path}")

    map_subject_slug = str(payload.get("subject_slug") or "").strip().lower()
    if map_subject_slug and map_subject_slug != subject_slug:
        manifest_warnings.append(
            f"Spotify map subject_slug mismatch: expected {subject_slug}, got {map_subject_slug}"
        )

    raw_by_title = payload.get("by_rss_title")
    if not isinstance(raw_by_title, dict):
        manifest_warnings.append(f"Spotify map missing by_rss_title object: {path}")
        return {}

    by_title: dict[str, str] = {}
    for raw_title, raw_url in raw_by_title.items():
        if not isinstance(raw_title, str):
            manifest_warnings.append("Spotify map contains non-string RSS title key.")
            continue
        normalized_title = _normalize_rss_title_key(raw_title)
        if not normalized_title:
            manifest_warnings.append("Spotify map contains empty RSS title key.")
            continue
        if normalized_title in by_title:
            manifest_warnings.append(f"Spotify map contains duplicate normalized RSS title: {normalized_title}")
            continue
        if not isinstance(raw_url, str):
            manifest_warnings.append(f"Spotify map URL must be a string for title: {raw_title}")
            continue
        spotify_url = raw_url.strip()
        if not SPOTIFY_EPISODE_URL_RE.match(spotify_url):
            manifest_warnings.append(f"Spotify map URL must be an episode URL for title: {raw_title}")
            continue
        by_title[normalized_title] = spotify_url
    return by_title


def _attach_podcasts(
    *,
    lectures: list[dict[str, Any]],
    lecture_index: dict[str, int],
    rss_path: Path,
    spotify_by_title: dict[str, str],
    manifest_warnings: list[str],
) -> None:
    if not rss_path.exists():
        manifest_warnings.append(f"RSS source missing: {rss_path}")
        return

    try:
        root = ElementTree.fromstring(rss_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ElementTree.ParseError):
        logger.warning("Unable to parse RSS for manifest build: %s", rss_path, exc_info=True)
        manifest_warnings.append(f"RSS source could not be parsed: {rss_path}")
        return

    channel = root.find("channel")
    if channel is None:
        manifest_warnings.append(f"RSS source missing channel node: {rss_path}")
        return

    for item in channel.findall("item"):
        title_text = str(item.findtext("title") or "").strip()
        if not title_text:
            continue
        title_parts = [part.strip() for part in title_text.split("·") if part.strip()]
        lecture_hint = title_parts[0] if title_parts else title_text
        descriptor = title_parts[2] if len(title_parts) >= 3 else title_text
        kind_hint = title_parts[1] if len(title_parts) >= 2 else ""
        lecture_key = _lecture_key_from_text(lecture_hint)
        if not lecture_key or lecture_key not in lecture_index:
            manifest_warnings.append(f"RSS item has unknown lecture mapping: {title_text}")
            continue

        lecture_state = lectures[lecture_index[lecture_key]]
        spotify_url = spotify_by_title.get(_normalize_rss_title_key(title_text))
        if not spotify_url:
            lecture_state["warnings"].append(f"Spotify mapping missing for RSS item: {title_text}")
            continue
        source_audio_url = _find_enclosure_url(item)
        podcast_asset = {
            "kind": _podcast_kind_from_token(kind_hint),
            "title": title_text,
            "url": spotify_url,
            "platform": "spotify",
            "pub_date": str(item.findtext("pubDate") or "").strip(),
            "source_audio_url": source_audio_url,
        }
        if _is_lecture_level_descriptor(descriptor):
            lecture_state["lecture_assets"]["podcasts"].append(podcast_asset)
            continue
        reading_index = _find_reading_index(lecture_state, descriptor)
        if reading_index is None:
            lecture_state["warnings"].append(
                f"RSS item could not map to reading; attached to lecture assets: {title_text}"
            )
            lecture_state["lecture_assets"]["podcasts"].append(podcast_asset)
            continue
        lecture_state["readings"][reading_index]["assets"]["podcasts"].append(podcast_asset)


def build_subject_content_manifest(subject_slug: str) -> SubjectContentManifest:
    slug = str(subject_slug or "").strip().lower()
    if not slug:
        raise ValueError("subject_slug is required")

    parse_result, reading_source_path, used_fallback = _reading_source_with_fallback()
    manifest_warnings: list[str] = []

    lectures: list[dict[str, Any]] = []
    lecture_index: dict[str, int] = {}
    for sequence_index, lecture in enumerate(parse_result.lectures, start=1):
        lecture_key = str(lecture.key).upper()
        lecture_title = _lecture_title_from_heading(lecture_key, lecture.heading)
        readings: list[dict[str, Any]] = []
        reading_lookup: dict[str, list[int]] = {}
        for reading_position, reading in enumerate(lecture.readings):
            normalized_title = _normalize_title(reading.title)
            reading_item = {
                "reading_key": _reading_key(lecture_key, reading.title),
                "reading_title": str(reading.title),
                "is_missing": bool(reading.is_missing),
                "sequence_index": reading_position + 1,
                "assets": {
                    "quizzes": [],
                    "podcasts": [],
                },
            }
            readings.append(reading_item)
            if normalized_title:
                reading_lookup.setdefault(normalized_title, []).append(reading_position)

        lectures.append(
            {
                "lecture_key": lecture_key,
                "lecture_title": lecture_title,
                "sequence_index": sequence_index,
                "readings": readings,
                "reading_lookup": reading_lookup,
                "lecture_assets": {
                    "quizzes": [],
                    "podcasts": [],
                },
                "warnings": [],
            }
        )
        lecture_index[lecture_key] = len(lectures) - 1

    quiz_links_path = Path(settings.QUIZ_LINKS_JSON_PATH)
    rss_path = Path(settings.FREUDD_SUBJECT_FEED_RSS_PATH)
    spotify_map_path = Path(settings.FREUDD_SUBJECT_SPOTIFY_MAP_PATH)
    spotify_by_title = _load_spotify_map(
        path=spotify_map_path,
        subject_slug=slug,
        manifest_warnings=manifest_warnings,
    )
    _attach_quizzes(
        lectures=lectures,
        lecture_index=lecture_index,
        subject_slug=slug,
        quiz_links_path=quiz_links_path,
        manifest_warnings=manifest_warnings,
    )
    _attach_podcasts(
        lectures=lectures,
        lecture_index=lecture_index,
        rss_path=rss_path,
        spotify_by_title=spotify_by_title,
        manifest_warnings=manifest_warnings,
    )

    for lecture_state in lectures:
        lecture_state["lecture_assets"]["quizzes"].sort(
            key=lambda item: (str(item.get("difficulty") or "medium"), str(item.get("quiz_id") or ""))
        )
        lecture_state["lecture_assets"]["podcasts"].sort(
            key=lambda item: str(item.get("title") or "").casefold()
        )
        for reading in lecture_state["readings"]:
            reading["assets"]["quizzes"].sort(
                key=lambda item: (str(item.get("difficulty") or "medium"), str(item.get("quiz_id") or ""))
            )
            reading["assets"]["podcasts"].sort(
                key=lambda item: str(item.get("title") or "").casefold()
            )
        lecture_state.pop("reading_lookup", None)

    reading_error = parse_result.error
    source_meta = {
        "version": MANIFEST_VERSION,
        "generated_at": timezone.now().isoformat(),
        "reading_master_path": str(settings.FREUDD_READING_MASTER_KEY_PATH),
        "reading_fallback_path": str(settings.FREUDD_READING_MASTER_KEY_FALLBACK_PATH),
        "reading_source_used": str(reading_source_path) if reading_source_path else None,
        "reading_fallback_used": used_fallback,
        "reading_error": reading_error,
        "quiz_links_path": str(quiz_links_path),
        "rss_path": str(rss_path),
        "spotify_map_path": str(spotify_map_path),
    }

    return {
        "version": MANIFEST_VERSION,
        "subject_slug": slug,
        "source_meta": source_meta,
        "lectures": lectures,
        "warnings": manifest_warnings,
    }


def write_subject_content_manifest(
    manifest: SubjectContentManifest,
    *,
    path: str | Path | None = None,
) -> Path:
    destination = Path(path or settings.FREUDD_SUBJECT_CONTENT_MANIFEST_PATH)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_suffix(destination.suffix + ".tmp")
    temp_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(destination)
    clear_content_service_caches()
    return destination


def load_subject_content_manifest(subject_slug: str) -> SubjectContentManifest:
    slug = str(subject_slug or "").strip().lower()
    path = Path(settings.FREUDD_SUBJECT_CONTENT_MANIFEST_PATH)
    if path.exists():
        try:
            mtime = path.stat().st_mtime_ns
        except OSError:
            logger.warning("Unable to stat content manifest path: %s", path, exc_info=True)
        else:
            cache_hit = (
                _MANIFEST_CACHE.get("path") == str(path)
                and _MANIFEST_CACHE.get("mtime") == mtime
                and _MANIFEST_CACHE.get("subject_slug") == slug
                and isinstance(_MANIFEST_CACHE.get("data"), dict)
            )
            if cache_hit:
                return _MANIFEST_CACHE["data"]
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                logger.warning("Unable to read content manifest path: %s", path, exc_info=True)
            else:
                if (
                    isinstance(payload, dict)
                    and payload.get("subject_slug") == slug
                    and isinstance(payload.get("lectures"), list)
                ):
                    _MANIFEST_CACHE["path"] = str(path)
                    _MANIFEST_CACHE["mtime"] = mtime
                    _MANIFEST_CACHE["subject_slug"] = slug
                    _MANIFEST_CACHE["data"] = payload
                    return payload

    manifest = build_subject_content_manifest(slug)
    _MANIFEST_CACHE["path"] = None
    _MANIFEST_CACHE["mtime"] = None
    _MANIFEST_CACHE["subject_slug"] = slug
    _MANIFEST_CACHE["data"] = manifest
    return manifest
