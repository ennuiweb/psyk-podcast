"""Content manifest services for lecture-first subject tracking."""

from __future__ import annotations

from email.utils import parsedate_to_datetime
import hashlib
import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from .subject_services import parse_master_readings, resolve_subject_paths

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
SLIDE_DESCRIPTOR_RE = re.compile(
    r"^slide\s+(?P<subcategory>lecture|seminar|exercise)\s*:\s*(?P<title>.+?)\s*$",
    re.IGNORECASE,
)
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
MULTISPACE_RE = re.compile(r"\s+")
OVELSESHOLD_NOTE_RE = re.compile(r"\(\s*tekst\s+for\s+øvelseshold\s*\)", re.IGNORECASE)
OVELSESHOLD_SHORT_NOTE = "(Øvelseshold)"
SINGLE_LETTER_TOKEN_RE = re.compile(r"\b[a-z]\b")
YEAR_SUFFIX_PAIR_RE = re.compile(r"\b(\d{4})([a-z])\s+(?:og|and)\s+([a-z])\b")
SPOTIFY_EPISODE_URL_RE = re.compile(
    r"^https://open\.spotify\.com/episode/[A-Za-z0-9]+(?:[/?#].*)?$",
    re.IGNORECASE,
)
HUMAN_MINUTES_RE = re.compile(r"(?P<minutes>\d+)\s*(?:min(?:ute)?s?|minutter)\b", re.IGNORECASE)
ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
MANIFEST_VERSION = 2
REPO_ROOT = Path(__file__).resolve().parents[2]

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


def _set_manifest_cache(
    *,
    path: Path | None,
    mtime_ns: int | None,
    subject_slug: str,
    data: SubjectContentManifest,
) -> SubjectContentManifest:
    _MANIFEST_CACHE["path"] = str(path) if path is not None else None
    _MANIFEST_CACHE["mtime"] = mtime_ns
    _MANIFEST_CACHE["subject_slug"] = subject_slug
    _MANIFEST_CACHE["data"] = data
    return data


def _manifest_source_paths(
    subject_slug: str,
    payload: SubjectContentManifest | None = None,
) -> tuple[Path, ...]:
    subject_paths = resolve_subject_paths(subject_slug)
    candidates: list[Path] = [
        subject_paths.reading_master_path,
        subject_paths.reading_fallback_path,
        subject_paths.quiz_links_path,
        subject_paths.feed_rss_path,
        subject_paths.spotify_map_path,
        subject_paths.slides_catalog_path,
    ]
    if subject_paths.reading_summaries_path is not None:
        candidates.append(subject_paths.reading_summaries_path)
    if subject_paths.weekly_overview_summaries_path is not None:
        candidates.append(subject_paths.weekly_overview_summaries_path)
    if isinstance(payload, dict):
        source_meta = payload.get("source_meta")
        if isinstance(source_meta, dict):
            reading_source_used = _source_meta_path_to_path(source_meta.get("reading_source_used"))
            if reading_source_used is not None:
                candidates.append(reading_source_used)

    unique_paths: list[Path] = []
    seen_paths: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen_paths:
            continue
        seen_paths.add(key)
        unique_paths.append(candidate)
    return tuple(unique_paths)


def _stale_manifest_sources(
    *,
    manifest_mtime_ns: int,
    subject_slug: str,
    payload: SubjectContentManifest | None = None,
) -> list[str]:
    stale_sources: list[str] = []
    for source_path in _manifest_source_paths(subject_slug, payload):
        try:
            source_mtime_ns = source_path.stat().st_mtime_ns
        except OSError:
            continue
        if source_mtime_ns > manifest_mtime_ns:
            stale_sources.append(str(source_path))
    return stale_sources


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
    text = str(value or "")
    suffix = Path(text).suffix
    if not suffix or not re.fullmatch(r"\.[a-z0-9]{2,5}", suffix, re.IGNORECASE):
        return value
    return text[: -len(suffix)]


def _descriptor_from_episode_name(value: str) -> str:
    cleaned = _strip_cfg_tag_suffix(_strip_episode_extension(value))
    cleaned = LANGUAGE_TAG_RE.sub("", cleaned).strip()
    cleaned = READING_PREFIX_RE.sub("", cleaned).strip()
    cleaned = re.sub(r"^x\s+", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"^(?:missing)\s+", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned


def _normalize_title(value: str) -> str:
    value_text = OVELSESHOLD_NOTE_RE.sub("", str(value or ""))
    normalized = unicodedata.normalize("NFKD", value_text)
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


def _matching_key_from_normalized(normalized_value: str) -> str:
    normalized = str(normalized_value or "").strip()
    if not normalized:
        return ""
    normalized = YEAR_SUFFIX_PAIR_RE.sub(r"\1\2 \1\3", normalized)
    normalized = SINGLE_LETTER_TOKEN_RE.sub(" ", normalized)
    return MULTISPACE_RE.sub(" ", normalized).strip()


def _append_lookup_index(lookup: dict[str, list[int]], key: str, reading_index: int) -> None:
    if not key:
        return
    indexes = lookup.setdefault(key, [])
    if reading_index not in indexes:
        indexes.append(reading_index)


def _display_reading_title(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if not OVELSESHOLD_NOTE_RE.search(raw):
        return raw
    shortened = OVELSESHOLD_NOTE_RE.sub(OVELSESHOLD_SHORT_NOTE, raw)
    return MULTISPACE_RE.sub(" ", shortened).strip()


def _reading_key(lecture_key: str, reading_title: str) -> str:
    normalized = _normalize_title(reading_title)
    slug = NON_ALNUM_RE.sub("-", normalized).strip("-")[:48] or "reading"
    digest = hashlib.sha1(f"{lecture_key}|{normalized}".encode("utf-8")).hexdigest()[:8]
    return f"{lecture_key.lower()}-{slug}-{digest}"


def _dedupe_reading_key(base_key: str, *, seen_counts: dict[str, int]) -> str:
    count = seen_counts.get(base_key, 0) + 1
    seen_counts[base_key] = count
    if count == 1:
        return base_key
    return f"{base_key}-{count}"


def _lecture_title_from_heading(lecture_key: str, heading: str) -> str:
    value = str(heading or "").strip()
    if value.upper().startswith(lecture_key.upper()):
        value = value[len(lecture_key) :].strip()
    return value.lstrip("-").strip() or lecture_key


def _reading_source_with_fallback(subject_slug: str) -> tuple[Any, Path | None, bool]:
    subject_paths = resolve_subject_paths(subject_slug)
    primary = subject_paths.reading_master_path
    fallback = subject_paths.reading_fallback_path

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


def _stable_manifest_path_value(path: Path | None) -> str | None:
    if path is None:
        return None
    candidate = Path(path)
    try:
        return candidate.resolve().relative_to(REPO_ROOT).as_posix()
    except (OSError, ValueError):
        return str(candidate)


def _source_meta_path_to_path(value: object) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidate = Path(text)
    if candidate.is_absolute():
        return candidate
    return REPO_ROOT / candidate


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


def _quiz_id_from_value(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    candidate = text
    if "://" in text:
        candidate = Path(text.split("?", 1)[0]).name
    match = QUIZ_ID_RE.search(candidate)
    if match:
        return match.group("id").lower()
    match = QUIZ_ID_RE.search(text.split("?", 1)[0])
    if match:
        return match.group("id").lower()
    return None


def _build_quiz_asset_location_lookup(
    lectures: list[dict[str, Any]],
) -> dict[str, tuple[int, int | None] | None]:
    lookup: dict[str, tuple[int, int | None] | None] = {}

    def _index_asset(
        quiz_asset: dict[str, Any],
        *,
        lecture_position: int,
        reading_position: int | None,
    ) -> None:
        quiz_id = _quiz_id_from_value(quiz_asset.get("quiz_id")) or _quiz_id_from_value(
            quiz_asset.get("quiz_url")
        )
        if not quiz_id:
            return
        location = (lecture_position, reading_position)
        if quiz_id not in lookup:
            lookup[quiz_id] = location
            return
        existing = lookup[quiz_id]
        if existing != location:
            lookup[quiz_id] = None

    for lecture_position, lecture_state in enumerate(lectures):
        lecture_assets = lecture_state.get("lecture_assets")
        if isinstance(lecture_assets, dict):
            for quiz_asset in lecture_assets.get("quizzes") or []:
                if isinstance(quiz_asset, dict):
                    _index_asset(
                        quiz_asset,
                        lecture_position=lecture_position,
                        reading_position=None,
                    )
        for reading_position, reading in enumerate(lecture_state.get("readings") or []):
            if not isinstance(reading, dict):
                continue
            assets = reading.get("assets")
            if not isinstance(assets, dict):
                continue
            for quiz_asset in assets.get("quizzes") or []:
                if isinstance(quiz_asset, dict):
                    _index_asset(
                        quiz_asset,
                        lecture_position=lecture_position,
                        reading_position=reading_position,
                    )
    return lookup


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


def _podcast_dedupe_descriptor(*, descriptor: str, lecture_level: bool) -> str:
    if lecture_level:
        return "all-sources"
    normalized = _normalize_title(descriptor)
    return _matching_key_from_normalized(normalized) or normalized


def _podcast_pubdate_timestamp(value: object) -> float:
    text = str(value or "").strip()
    if not text:
        return float("-inf")
    try:
        return parsedate_to_datetime(text).timestamp()
    except (TypeError, ValueError, OverflowError):
        return float("-inf")


def _should_replace_podcast_asset(
    *,
    existing_asset: dict[str, Any],
    incoming_asset: dict[str, Any],
) -> bool:
    return _podcast_pubdate_timestamp(incoming_asset.get("pub_date")) > _podcast_pubdate_timestamp(
        existing_asset.get("pub_date")
    )


def _append_deduped_podcast_asset(
    *,
    target_assets: list[dict[str, Any]],
    seen_assets: dict[tuple[Any, ...], dict[str, Any]],
    dedupe_key: tuple[Any, ...],
    lecture_state: dict[str, Any],
    podcast_asset: dict[str, Any],
) -> None:
    existing_asset = seen_assets.get(dedupe_key)
    if existing_asset is None:
        target_assets.append(podcast_asset)
        seen_assets[dedupe_key] = podcast_asset
        return

    duplicate_title = str(podcast_asset.get("title") or "").strip() or "Podcast episode"
    if _should_replace_podcast_asset(existing_asset=existing_asset, incoming_asset=podcast_asset):
        existing_asset.clear()
        existing_asset.update(podcast_asset)
        lecture_state["warnings"].append(
            f"Duplicate podcast asset detected; kept newest RSS item for: {duplicate_title}"
        )
        return

    lecture_state["warnings"].append(
        f"Duplicate podcast asset detected; ignored older RSS item for: {duplicate_title}"
    )


def _is_lecture_level_descriptor(value: str) -> bool:
    return bool(ALL_SOURCES_RE.search(value or ""))


def _find_reading_index(lecture_state: dict[str, Any], descriptor: str) -> int | None:
    normalized_descriptor = _normalize_title(descriptor)
    if not normalized_descriptor:
        return None

    def _resolve_lookup(
        lookup: dict[str, list[int]],
        normalized_needle: str,
    ) -> int | None:
        if not normalized_needle:
            return None

        exact_matches = lookup.get(normalized_needle, [])
        if len(exact_matches) == 1:
            return exact_matches[0]
        if len(exact_matches) > 1:
            return None

        fuzzy_matches: list[int] = []
        for normalized_title, indexes in lookup.items():
            if normalized_needle in normalized_title or normalized_title in normalized_needle:
                fuzzy_matches.extend(indexes)
        fuzzy_matches = sorted(set(fuzzy_matches))
        if len(fuzzy_matches) == 1:
            return fuzzy_matches[0]
        return None

    lookup: dict[str, list[int]] = lecture_state["reading_lookup"]
    resolved = _resolve_lookup(lookup, normalized_descriptor)
    if resolved is not None:
        return resolved

    matching_lookup = lecture_state.get("reading_match_lookup")
    if not isinstance(matching_lookup, dict):
        return None
    matching_descriptor = _matching_key_from_normalized(normalized_descriptor)
    return _resolve_lookup(matching_lookup, matching_descriptor)


def _load_slide_catalog_entries(subject_slug: str) -> list[dict[str, Any]]:
    path = resolve_subject_paths(subject_slug).slides_catalog_path
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("Unable to parse slide catalog for manifest build: %s", path, exc_info=True)
        return []
    raw_slides = payload.get("slides")
    if not isinstance(raw_slides, list):
        return []
    return [item for item in raw_slides if isinstance(item, dict)]


def _build_slide_lookup(
    slide_items: list[dict[str, Any]],
) -> dict[str, int | None]:
    lookup: dict[str, int | None] = {}
    for index, slide in enumerate(slide_items):
        subcategory = str(slide.get("subcategory") or "").strip().lower()
        title = str(slide.get("title") or "").strip()
        if not subcategory or not title:
            continue
        key = f"{subcategory}|{_normalize_title(title)}"
        existing = lookup.get(key)
        if existing is None and key in lookup:
            continue
        if existing is not None:
            lookup[key] = None
            continue
        lookup[key] = index
    return lookup


def _find_slide_index(lecture_state: dict[str, Any], descriptor: str) -> int | None:
    match = SLIDE_DESCRIPTOR_RE.match(str(descriptor or "").strip())
    if not match:
        return None
    subcategory = str(match.group("subcategory") or "").strip().lower()
    title = str(match.group("title") or "").strip()
    if not subcategory or not title:
        return None
    slide_lookup = lecture_state.get("slide_lookup")
    if not isinstance(slide_lookup, dict):
        return None
    lookup_key = f"{subcategory}|{_normalize_title(title)}"
    resolved = slide_lookup.get(lookup_key)
    return resolved if isinstance(resolved, int) else None


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


def _load_summary_entries(
    *,
    path: Path | None,
    label: str,
    manifest_warnings: list[str],
) -> dict[str, Any]:
    if path is None:
        return {}
    if not path.exists():
        manifest_warnings.append(f"{label} source missing: {path}")
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("Unable to parse %s for manifest build: %s", label, path, exc_info=True)
        manifest_warnings.append(f"{label} source could not be parsed: {path}")
        return {}
    if not isinstance(payload, dict):
        manifest_warnings.append(f"{label} source must be a JSON object: {path}")
        return {}
    by_name = payload.get("by_name")
    if not isinstance(by_name, dict):
        manifest_warnings.append(f"{label} source missing by_name object: {path}")
        return {}
    return by_name


def _summary_payload_from_entry(entry_name: str, raw_entry: Any) -> dict[str, Any] | None:
    if not isinstance(raw_entry, dict):
        return None

    summary_lines: list[str] = []
    raw_summary_lines = raw_entry.get("summary_lines")
    if isinstance(raw_summary_lines, list):
        for value in raw_summary_lines:
            cleaned = str(value or "").strip()
            if cleaned:
                summary_lines.append(cleaned)

    key_points: list[str] = []
    raw_key_points = raw_entry.get("key_points")
    if isinstance(raw_key_points, list):
        for value in raw_key_points:
            cleaned = str(value or "").strip()
            if cleaned:
                key_points.append(cleaned)

    if not summary_lines and not key_points:
        return None

    raw_meta = raw_entry.get("meta")
    meta = raw_meta if isinstance(raw_meta, dict) else {}
    source_file = str(meta.get("source_file") or "").strip() or None
    lecture_key = (
        _lecture_key_from_text(str(meta.get("lecture_key") or ""))
        or str(meta.get("lecture_key") or "").strip().upper()
        or None
    )
    return {
        "summary_lines": summary_lines,
        "key_points": key_points,
        "cache_key": entry_name,
        "source_file": source_file,
        "lecture_key": lecture_key,
        "status": str(meta.get("status") or "").strip() or None,
        "language": str(meta.get("language") or "").strip() or None,
    }


def _summary_candidate_score(entry_name: str, payload: dict[str, Any]) -> tuple[int, int, int]:
    cleaned_name = str(entry_name or "").strip()
    upper_name = cleaned_name.upper()
    standard_variant = 0 if upper_name.startswith("[BRIEF]") or upper_name.startswith("[TTS]") else 1
    richness = len(payload.get("summary_lines") or []) + len(payload.get("key_points") or [])
    text_weight = sum(len(str(value)) for value in (payload.get("summary_lines") or [])) + sum(
        len(str(value)) for value in (payload.get("key_points") or [])
    )
    return (standard_variant, richness, text_weight)


def _attach_summaries(
    *,
    lectures: list[dict[str, Any]],
    lecture_index: dict[str, int],
    subject_slug: str,
    manifest_warnings: list[str],
) -> None:
    subject_paths = resolve_subject_paths(subject_slug)
    lecture_scores: dict[int, tuple[int, int, int]] = {}
    reading_scores: dict[tuple[int, int], tuple[int, int, int]] = {}

    weekly_entries = _load_summary_entries(
        path=subject_paths.weekly_overview_summaries_path,
        label="Weekly overview summaries",
        manifest_warnings=manifest_warnings,
    )
    for entry_name, raw_entry in weekly_entries.items():
        if not isinstance(entry_name, str):
            continue
        payload = _summary_payload_from_entry(entry_name, raw_entry)
        if payload is None:
            continue
        lecture_key = payload.get("lecture_key") or _lecture_key_from_text(entry_name)
        if not lecture_key or lecture_key not in lecture_index:
            manifest_warnings.append(f"Weekly overview summary has unknown lecture mapping: {entry_name}")
            continue
        lecture_position = lecture_index[lecture_key]
        score = _summary_candidate_score(entry_name, payload)
        if score <= lecture_scores.get(lecture_position, (-1, -1, -1)):
            continue
        lectures[lecture_position]["summary"] = {
            "summary_lines": list(payload.get("summary_lines") or []),
            "key_points": list(payload.get("key_points") or []),
        }
        lecture_scores[lecture_position] = score

    reading_entries = _load_summary_entries(
        path=subject_paths.reading_summaries_path,
        label="Reading summaries",
        manifest_warnings=manifest_warnings,
    )
    for entry_name, raw_entry in reading_entries.items():
        if not isinstance(entry_name, str):
            continue
        payload = _summary_payload_from_entry(entry_name, raw_entry)
        if payload is None:
            continue
        lecture_key = (
            _lecture_key_from_text(str(payload.get("source_file") or ""))
            or payload.get("lecture_key")
            or _lecture_key_from_text(entry_name)
        )
        if not lecture_key or lecture_key not in lecture_index:
            manifest_warnings.append(f"Reading summary has unknown lecture mapping: {entry_name}")
            continue
        lecture_position = lecture_index[lecture_key]
        lecture_state = lectures[lecture_position]
        descriptor_candidates: list[str] = []
        source_file = str(payload.get("source_file") or "").strip()
        if source_file:
            descriptor_candidates.append(Path(source_file).stem)
        descriptor = _descriptor_from_episode_name(entry_name)
        if descriptor:
            descriptor_candidates.append(descriptor)

        reading_index: int | None = None
        seen_descriptors: set[str] = set()
        for candidate in descriptor_candidates:
            candidate_text = str(candidate or "").strip()
            if not candidate_text or candidate_text in seen_descriptors:
                continue
            seen_descriptors.add(candidate_text)
            if _is_lecture_level_descriptor(candidate_text):
                continue
            reading_index = _find_reading_index(lecture_state, candidate_text)
            if reading_index is not None:
                break

        if reading_index is None:
            lecture_state["warnings"].append(
                f"Reading summary could not map to reading: {entry_name}"
            )
            continue

        score = _summary_candidate_score(entry_name, payload)
        reading_score_key = (lecture_position, reading_index)
        if score <= reading_scores.get(reading_score_key, (-1, -1, -1)):
            continue
        lecture_state["readings"][reading_index]["summary"] = {
            "summary_lines": list(payload.get("summary_lines") or []),
            "key_points": list(payload.get("key_points") or []),
        }
        reading_scores[reading_score_key] = score


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

        slide_index = _find_slide_index(lecture_state, descriptor)
        if slide_index is not None:
            lecture_state["slides"][slide_index]["assets"]["quizzes"].extend(quiz_assets)
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


def _duration_seconds_from_text(value: object) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None

    if text.isdigit():
        seconds = int(text)
        return seconds if seconds > 0 else None

    clock_parts = [part.strip() for part in text.split(":")]
    if len(clock_parts) in {2, 3} and all(part.isdigit() for part in clock_parts):
        try:
            numbers = [int(part) for part in clock_parts]
        except ValueError:
            return None
        if len(numbers) == 2:
            minutes, seconds = numbers
            total_seconds = minutes * 60 + seconds
        else:
            hours, minutes, seconds = numbers
            total_seconds = hours * 3600 + minutes * 60 + seconds
        return total_seconds if total_seconds > 0 else None

    minutes_match = HUMAN_MINUTES_RE.search(text)
    if minutes_match:
        minutes = int(minutes_match.group("minutes"))
        total_seconds = minutes * 60
        return total_seconds if total_seconds > 0 else None
    return None


def _duration_label_from_seconds(seconds: int | None) -> str:
    if not seconds:
        return ""
    minutes = int(round(seconds / 60))
    if minutes <= 0:
        minutes = 1
    return f"{minutes} min"


def _duration_payload_from_item(item_node: ElementTree.Element) -> tuple[int | None, str]:
    duration_candidates = [
        item_node.findtext(f"{{{ITUNES_NS}}}duration"),
        item_node.findtext("duration"),
    ]
    for raw_duration in duration_candidates:
        duration_seconds = _duration_seconds_from_text(raw_duration)
        if duration_seconds is None:
            continue
        return duration_seconds, _duration_label_from_seconds(duration_seconds)
    return None, ""


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
    quiz_asset_locations: dict[str, tuple[int, int | None] | None],
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

    seen_assets: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in channel.findall("item"):
        title_text = str(item.findtext("title") or "").strip()
        if not title_text:
            continue
        title_parts = [part.strip() for part in title_text.split("·") if part.strip()]
        lecture_hint = title_parts[0] if title_parts else title_text
        descriptor = title_parts[2] if len(title_parts) >= 3 else title_text
        kind_hint = title_parts[1] if len(title_parts) >= 2 else ""
        item_link = str(item.findtext("link") or "").strip()
        quiz_location = quiz_asset_locations.get(_quiz_id_from_value(item_link) or "")
        lecture_key = _lecture_key_from_text(lecture_hint)
        lecture_position = lecture_index.get(lecture_key) if lecture_key else None
        if lecture_position is None and quiz_location is not None:
            lecture_position = quiz_location[0]
        if lecture_position is None:
            manifest_warnings.append(f"RSS item has unknown lecture mapping: {title_text}")
            continue

        lecture_state = lectures[lecture_position]
        spotify_url = spotify_by_title.get(_normalize_rss_title_key(title_text))
        source_audio_url = _find_enclosure_url(item)
        if not spotify_url:
            lecture_state["warnings"].append(
                f"Spotify episode mapping missing for RSS item; skipping podcast asset: {title_text}"
            )
            continue
        if not SPOTIFY_EPISODE_URL_RE.match(spotify_url):
            lecture_state["warnings"].append(
                f"Spotify mapping is not an episode URL; skipping podcast asset: {title_text}"
            )
            manifest_warnings.append(f"Spotify mapping is not an episode URL for RSS item: {title_text}")
            continue
        duration_seconds, duration_label = _duration_payload_from_item(item)
        podcast_asset = {
            "kind": _podcast_kind_from_token(kind_hint),
            "title": title_text,
            "url": spotify_url,
            "platform": "spotify",
            "pub_date": str(item.findtext("pubDate") or "").strip(),
            "source_audio_url": source_audio_url,
            "duration_seconds": duration_seconds,
            "duration_label": duration_label,
        }
        lecture_level = _is_lecture_level_descriptor(descriptor)
        descriptor_key = _podcast_dedupe_descriptor(descriptor=descriptor, lecture_level=lecture_level)
        podcast_kind = str(podcast_asset.get("kind") or "").strip().lower()
        if lecture_level:
            _append_deduped_podcast_asset(
                target_assets=lecture_state["lecture_assets"]["podcasts"],
                seen_assets=seen_assets,
                dedupe_key=(lecture_position, "lecture", None, podcast_kind, descriptor_key),
                lecture_state=lecture_state,
                podcast_asset=podcast_asset,
            )
            continue
        slide_index = _find_slide_index(lecture_state, descriptor)
        if slide_index is not None:
            _append_deduped_podcast_asset(
                target_assets=lecture_state["slides"][slide_index]["assets"]["podcasts"],
                seen_assets=seen_assets,
                dedupe_key=(lecture_position, "slide", slide_index, podcast_kind, descriptor_key),
                lecture_state=lecture_state,
                podcast_asset=podcast_asset,
            )
            continue
        reading_index = _find_reading_index(lecture_state, descriptor)
        if reading_index is None and quiz_location is not None and quiz_location[0] == lecture_position:
            reading_index = quiz_location[1]
        if reading_index is None:
            lecture_state["warnings"].append(
                f"RSS item could not map to reading; attached to lecture assets: {title_text}"
            )
            _append_deduped_podcast_asset(
                target_assets=lecture_state["lecture_assets"]["podcasts"],
                seen_assets=seen_assets,
                dedupe_key=(lecture_position, "lecture", None, podcast_kind, descriptor_key),
                lecture_state=lecture_state,
                podcast_asset=podcast_asset,
            )
            continue
        _append_deduped_podcast_asset(
            target_assets=lecture_state["readings"][reading_index]["assets"]["podcasts"],
            seen_assets=seen_assets,
            dedupe_key=(lecture_position, "reading", reading_index, podcast_kind, descriptor_key),
            lecture_state=lecture_state,
            podcast_asset=podcast_asset,
        )


def build_subject_content_manifest(subject_slug: str) -> SubjectContentManifest:
    slug = str(subject_slug or "").strip().lower()
    if not slug:
        raise ValueError("subject_slug is required")

    subject_paths = resolve_subject_paths(slug)
    parse_result, reading_source_path, used_fallback = _reading_source_with_fallback(slug)
    manifest_warnings: list[str] = []
    slide_catalog_entries = _load_slide_catalog_entries(slug)

    lectures: list[dict[str, Any]] = []
    lecture_index: dict[str, int] = {}
    for sequence_index, lecture in enumerate(parse_result.lectures, start=1):
        lecture_key = str(lecture.key).upper()
        lecture_title = _lecture_title_from_heading(lecture_key, lecture.heading)
        readings: list[dict[str, Any]] = []
        reading_lookup: dict[str, list[int]] = {}
        reading_match_lookup: dict[str, list[int]] = {}
        reading_key_counts: dict[str, int] = {}
        for reading_position, reading in enumerate(lecture.readings):
            normalized_title = _normalize_title(reading.title)
            source_filename = (
                str(reading.source_filename).strip()
                if isinstance(reading.source_filename, str) and reading.source_filename.strip()
                else None
            )
            base_reading_key = _reading_key(lecture_key, reading.title)
            reading_item = {
                "reading_key": _dedupe_reading_key(
                    base_reading_key,
                    seen_counts=reading_key_counts,
                ),
                "reading_title": _display_reading_title(reading.title),
                "is_missing": bool(reading.is_missing),
                "source_filename": source_filename,
                "sequence_index": reading_position + 1,
                "summary": None,
                "assets": {
                    "quizzes": [],
                    "podcasts": [],
                },
            }
            readings.append(reading_item)
            if normalized_title:
                _append_lookup_index(reading_lookup, normalized_title, reading_position)
                _append_lookup_index(
                    reading_match_lookup,
                    _matching_key_from_normalized(normalized_title),
                    reading_position,
                )
            if source_filename:
                source_stem_normalized = _normalize_title(Path(source_filename).stem)
                if source_stem_normalized:
                    _append_lookup_index(reading_lookup, source_stem_normalized, reading_position)
                    _append_lookup_index(
                        reading_match_lookup,
                        _matching_key_from_normalized(source_stem_normalized),
                        reading_position,
                )

        slide_items: list[dict[str, Any]] = []
        for raw_slide in slide_catalog_entries:
            raw_lecture_key = str(raw_slide.get("lecture_key") or "").strip().upper()
            if raw_lecture_key != lecture_key:
                continue
            source_filename = (
                str(raw_slide.get("source_filename") or "").strip()
                if isinstance(raw_slide.get("source_filename"), str) and str(raw_slide.get("source_filename") or "").strip()
                else None
            )
            slide_items.append(
                {
                    "slide_key": str(raw_slide.get("slide_key") or "").strip().lower(),
                    "subcategory": str(raw_slide.get("subcategory") or "").strip().lower(),
                    "title": str(raw_slide.get("title") or "").strip() or (source_filename or "Slides"),
                    "source_filename": source_filename,
                    "relative_path": str(raw_slide.get("relative_path") or "").strip() or None,
                    "assets": {
                        "quizzes": [],
                        "podcasts": [],
                    },
                }
            )

        lectures.append(
            {
                "lecture_key": lecture_key,
                "lecture_title": lecture_title,
                "sequence_index": sequence_index,
                "summary": None,
                "readings": readings,
                "slides": slide_items,
                "reading_lookup": reading_lookup,
                "reading_match_lookup": reading_match_lookup,
                "slide_lookup": _build_slide_lookup(slide_items),
                "lecture_assets": {
                    "quizzes": [],
                    "podcasts": [],
                },
                "warnings": [],
            }
        )
        lecture_index[lecture_key] = len(lectures) - 1

    quiz_links_path = subject_paths.quiz_links_path
    rss_path = subject_paths.feed_rss_path
    spotify_map_path = subject_paths.spotify_map_path
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
    quiz_asset_locations = _build_quiz_asset_location_lookup(lectures)
    _attach_podcasts(
        lectures=lectures,
        lecture_index=lecture_index,
        rss_path=rss_path,
        spotify_by_title=spotify_by_title,
        quiz_asset_locations=quiz_asset_locations,
        manifest_warnings=manifest_warnings,
    )
    _attach_summaries(
        lectures=lectures,
        lecture_index=lecture_index,
        subject_slug=slug,
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
        for slide in lecture_state.get("slides") or []:
            if not isinstance(slide, dict):
                continue
            slide_assets = slide.get("assets") if isinstance(slide.get("assets"), dict) else {}
            slide_assets.setdefault("quizzes", [])
            slide_assets.setdefault("podcasts", [])
            slide_assets["quizzes"].sort(
                key=lambda item: (str(item.get("difficulty") or "medium"), str(item.get("quiz_id") or ""))
            )
            slide_assets["podcasts"].sort(
                key=lambda item: str(item.get("title") or "").casefold()
            )
        lecture_state.pop("reading_lookup", None)
        lecture_state.pop("reading_match_lookup", None)
        lecture_state.pop("slide_lookup", None)

    reading_error = parse_result.error
    source_meta = {
        "version": MANIFEST_VERSION,
        "reading_master_path": _stable_manifest_path_value(subject_paths.reading_master_path),
        "reading_fallback_path": _stable_manifest_path_value(subject_paths.reading_fallback_path),
        "reading_source_used": _stable_manifest_path_value(reading_source_path),
        "reading_fallback_used": used_fallback,
        "reading_error": reading_error,
        "reading_summaries_path": _stable_manifest_path_value(subject_paths.reading_summaries_path),
        "weekly_overview_summaries_path": _stable_manifest_path_value(
            subject_paths.weekly_overview_summaries_path
        ),
        "quiz_links_path": _stable_manifest_path_value(quiz_links_path),
        "rss_path": _stable_manifest_path_value(rss_path),
        "spotify_map_path": _stable_manifest_path_value(spotify_map_path),
        "slides_catalog_path": _stable_manifest_path_value(subject_paths.slides_catalog_path),
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
    if path is not None:
        destination = Path(path)
    else:
        subject_slug = str(manifest.get("subject_slug") or "").strip().lower()
        destination = resolve_subject_paths(subject_slug).content_manifest_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_suffix(destination.suffix + ".tmp")
    temp_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(destination)
    clear_content_service_caches()
    return destination


def load_subject_content_manifest(subject_slug: str) -> SubjectContentManifest:
    slug = str(subject_slug or "").strip().lower()
    path = resolve_subject_paths(slug).content_manifest_path
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
                    if payload.get("version") != MANIFEST_VERSION:
                        logger.info(
                            "Detected outdated content manifest schema; rebuilding from source files.",
                            extra={
                                "subject_slug": slug,
                                "manifest_path": str(path),
                                "manifest_version": payload.get("version"),
                                "expected_version": MANIFEST_VERSION,
                            },
                        )
                        refreshed_manifest = build_subject_content_manifest(slug)
                        try:
                            write_subject_content_manifest(refreshed_manifest, path=path)
                        except Exception:
                            logger.exception(
                                "Failed to persist rebuilt manifest after schema update.",
                                extra={
                                    "subject_slug": slug,
                                    "manifest_path": str(path),
                                },
                            )
                        try:
                            refreshed_mtime = path.stat().st_mtime_ns
                        except OSError:
                            refreshed_mtime = None
                        return _set_manifest_cache(
                            path=path,
                            mtime_ns=refreshed_mtime,
                            subject_slug=slug,
                            data=refreshed_manifest,
                        )
                    stale_sources = _stale_manifest_sources(
                        manifest_mtime_ns=mtime,
                        subject_slug=slug,
                        payload=payload,
                    )
                    if not stale_sources:
                        return _set_manifest_cache(
                            path=path,
                            mtime_ns=mtime,
                            subject_slug=slug,
                            data=payload,
                        )
                    logger.info(
                        "Detected stale content manifest; rebuilding from source files.",
                        extra={
                            "subject_slug": slug,
                            "manifest_path": str(path),
                            "stale_sources": stale_sources,
                        },
                    )
                    try:
                        refreshed_manifest = build_subject_content_manifest(slug)
                    except Exception:
                        logger.exception(
                            "Failed to rebuild stale content manifest; keeping existing payload.",
                            extra={
                                "subject_slug": slug,
                                "manifest_path": str(path),
                                "stale_sources": stale_sources,
                            },
                        )
                        return _set_manifest_cache(
                            path=path,
                            mtime_ns=mtime,
                            subject_slug=slug,
                            data=payload,
                        )
                    try:
                        write_subject_content_manifest(refreshed_manifest, path=path)
                    except OSError:
                        logger.warning(
                            "Unable to write refreshed content manifest path: %s",
                            path,
                            exc_info=True,
                        )
                        return _set_manifest_cache(
                            path=None,
                            mtime_ns=None,
                            subject_slug=slug,
                            data=refreshed_manifest,
                        )
                    try:
                        refreshed_mtime = path.stat().st_mtime_ns
                    except OSError:
                        refreshed_mtime = None
                    return _set_manifest_cache(
                        path=path,
                        mtime_ns=refreshed_mtime,
                        subject_slug=slug,
                        data=refreshed_manifest,
                    )

    manifest = build_subject_content_manifest(slug)
    return _set_manifest_cache(
        path=None,
        mtime_ns=None,
        subject_slug=slug,
        data=manifest,
    )
