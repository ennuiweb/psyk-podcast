#!/usr/bin/env python3
"""Generate a podcast RSS feed from audio files stored in a Google Drive folder."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple
from urllib.parse import parse_qs, quote, urlencode, urlparse
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from regeneration_identity import logical_episode_id  # noqa: E402
from storage_backends import build_storage_backend, resolve_storage_provider

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ModuleNotFoundError:  # pragma: no cover - optional for pure-metadata/unit tests
    service_account = None  # type: ignore[assignment]
    build = None  # type: ignore[assignment]
    HttpError = None  # type: ignore[assignment]

SCOPES = ["https://www.googleapis.com/auth/drive"]
ATOM_NS = "http://www.w3.org/2005/Atom"
ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
TEXT_PREFIX = "[Tekst]"
HIGHLIGHTED_TEXT_PREFIX = "[Gul tekst]"
LANGUAGE_TAG_PATTERN = re.compile(
    r"(?:\[\s*(?:en|da|dk|tts)\s*\]|\(\s*(?:en|da|dk|tts)\s*\))",
    re.IGNORECASE,
)
CROSS_LANGUAGE_TAG_PATTERN = re.compile(
    r"(?:\[\s*(?:en|da|dk)\s*\]|\(\s*(?:en|da|dk)\s*\))",
    re.IGNORECASE,
)
TTS_TAG_PATTERN = re.compile(r"(?:\[\s*tts\s*\]|\(\s*tts\s*\))", re.IGNORECASE)
SHORT_TAG_PATTERN = re.compile(r"\[\s*(?:short|brief)\s*\]", re.IGNORECASE)
BRIEF_TAG_PATTERN = SHORT_TAG_PATTERN
DEEP_DIVE_TAG_PATTERN = re.compile(r"\[\s*deep-dive\s*\]", re.IGNORECASE)
CFG_TTS_TYPE_PATTERN = re.compile(r"\{[^{}]*\btype=tts\b[^{}]*\}", re.IGNORECASE)
CFG_AUDIO_TYPE_PATTERN = re.compile(r"\{[^{}]*\btype=audio\b[^{}]*\}", re.IGNORECASE)
CFG_AUDIO_SHORT_PATTERN = re.compile(
    r"\{[^{}]*\btype=audio\b[^{}]*\bformat=(?:short|brief)\b[^{}]*\}",
    re.IGNORECASE,
)
CFG_AUDIO_BRIEF_PATTERN = CFG_AUDIO_SHORT_PATTERN
CFG_AUDIO_DEEP_DIVE_PATTERN = re.compile(
    r"\{[^{}]*\btype=audio\b[^{}]*\bformat=deep-dive\b[^{}]*\}",
    re.IGNORECASE,
)
AUDIO_FILE_EXTENSIONS = {".mp3", ".m4a", ".wav", ".aac", ".flac"}
PREFERRED_AUDIO_EXTENSIONS = (".mp3", ".m4a", ".aac", ".wav", ".flac")
AUDIO_COPY_SUFFIX_PATTERN = re.compile(r"(?<=[}\]])\s+\d+$")
AUDIO_CATEGORY_PREFIXES = {
    "lydbog": "[Lydbog]",
    "kort_podcast": "[Kort podcast]",
    "podcast": "[Podcast]",
}
AUDIO_CATEGORY_PREFIX_POSITIONS = {"leading", "after_first_block"}
DEFAULT_AUDIO_CATEGORY_PREFIX_POSITION = "leading"
TITLE_BLOCK_SEPARATOR = " · "
CATEGORY_PREFIX_HEAD_PATTERN = re.compile(
    r"^\s*(?:Oplæst\b|\[\s*(?:short|brief)\s*\]|\[\s*deep-dive\s*\]|\[\s*podcast\s*\]|\[\s*lydbog\s*\]|\[\s*kort(?:\s+podcast)?\s*\])\s*(?:[·:\-]\s*)?",
    re.IGNORECASE,
)
READING_PREFIX_PATTERN = re.compile(r"(^|[·\n]\s*)reading:\s*", re.IGNORECASE)
LECTURE_SEMESTER_PAIR_PATTERN = re.compile(
    r"\b(?:forelæsning\s+\d+\s*·\s*semesteruge\s+\d+|semesteruge\s+\d+\s*·\s*forelæsning\s+\d+)\b",
    re.IGNORECASE,
)
WEEK_LECTURE_LABEL_PATTERN = re.compile(
    r"\b(?:uge|semesteruge|week)\s+(\d+)\s*,\s*(?:forelæsning|lecture)\s+(\d+)\b",
    re.IGNORECASE,
)
CFG_TAG_PATTERN = re.compile(
    r"(?:\s+\{[a-z0-9._:+-]+=[^{}\s]+(?:\s+[a-z0-9._:+-]+=[^{}\s]+)*\})+"
    r"(?:\s+\[[^\[\]]+\])?$",
    re.IGNORECASE,
)
CFG_TAG_ANYWHERE_PATTERN = re.compile(
    r"\s+\{[a-z0-9._:+-]+=[^{}\s]+(?:\s+[a-z0-9._:+-]+=[^{}\s]+)*\}"
    r"(?:\s+\[[^\[\]]+\])?",
    re.IGNORECASE,
)
QUIZ_DIFFICULTY_RE = re.compile(
    r"\{[^{}]*\bdifficulty=(?P<difficulty>[a-z0-9._:+-]+)\b[^{}]*\}",
    re.IGNORECASE,
)
QUIZ_DIFFICULTY_SORT_ORDER = {"easy": 0, "medium": 1, "hard": 2}
QUIZ_PRIMARY_DIFFICULTY_SORT_ORDER = {"medium": 0, "easy": 1, "hard": 2}
QUIZ_DIFFICULTY_LABELS = {"easy": "Easy", "medium": "Medium", "hard": "Hard"}
IMPORTANT_TRUTHY_STRINGS = {
    "1",
    "true",
    "yes",
    "y",
    "ja",
    "j",
    "on",
}
IMPORTANT_FALSE_STRINGS = {
    "0",
    "false",
    "no",
    "nej",
    "off",
}
IMPORTANT_MARKER_TOKENS = {
    "important",
    "priority",
    "prioritet",
    "prioriteret",
    "highlight",
    "highlighted",
    "gul",
    "gule",
    "gult",
    "yellow",
    "vigtig",
    "vigtige",
    "vigtigt",
    "high",
    "hoj",
    "hojt",
    "hoje",
}
LOW_PRIORITY_TOKENS = {
    "low",
    "lav",
    "lavt",
    "lavere",
    "medium",
    "mellem",
    "sekundaer",
    "sekundar",
    "sekundare",
    "sekundart",
}
NEGATION_TOKENS = {
    "not",
    "ikke",
    "ej",
}
DOC_IMPORTANT_SYMBOLS = {"⭐", "🔥", "‼", "❗"}
DOC_IMPORTANT_PREFIX_MARKERS = (
    "[!important",
    "[!warning",
    "[!attention",
    "[!prioritet",
    "[!priority",
    "[!vigtig",
)
DOC_IMPORTANT_INLINE_MARKERS = (
    "(!",
    "[important]",
    "[vigtig]",
    "[priority]",
    "(important)",
    "(vigtig)",
    "(priority)",
)
DOC_CALLOUT_PATTERN = re.compile(
    r"\[!\s*(important|warning|attention|prioritet|priority|vigtig)\b", re.IGNORECASE
)
WEEK_X_PREFIX_PATTERN = re.compile(r"^w\d+(?:l\d+)?\s+x\b", re.IGNORECASE)
OVELSESHOLD_MARKER_PATTERN = re.compile(r"\btekst\s+for\s+(?:ø|oe)velseshold\b", re.IGNORECASE)
GOOGLE_API_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
GOOGLE_API_RETRY_REASONS = {"internalError", "backendError", "rateLimitExceeded", "userRateLimitExceeded"}
GOOGLE_API_MAX_RETRIES = 4
GOOGLE_API_RETRY_BASE_DELAY_SECONDS = 1.0


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_feed(root, destination: Path) -> None:
    from xml.etree import ElementTree as ET

    tree = ET.ElementTree(root)
    try:
        ET.indent(tree)  # type: ignore[attr-defined]
    except AttributeError:
        pass
    destination.parent.mkdir(parents=True, exist_ok=True)
    tree.write(destination, encoding="utf-8", xml_declaration=True)


def save_json(payload: Dict[str, Any], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_drive_service(credentials_path: Path):
    if service_account is None or build is None:
        raise SystemExit(
            "Missing Google API dependencies. Install requirements (google-auth, google-api-python-client) "
            "or run in an environment that has them available."
        )
    credentials = service_account.Credentials.from_service_account_file(
        str(credentials_path), scopes=SCOPES
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def _podcast_kind_from_audio_category(value: Any) -> str:
    token = str(value or "").strip().lower()
    if token == "kort_podcast":
        return "short_podcast"
    if token == "lydbog":
        return "lydbog"
    return "podcast"


def _default_inventory_path(output_feed: Path) -> Path:
    if output_feed.parent.name == "feeds":
        return output_feed.parent.parent / "episode_inventory.json"
    return output_feed.with_name("episode_inventory.json")


def _output_inventory_path(config: Dict[str, Any]) -> Optional[Path]:
    raw_path = str(config.get("output_inventory") or "").strip()
    if raw_path:
        return Path(raw_path)
    return None


def _inventory_show_slug(config: Dict[str, Any]) -> Optional[str]:
    output_feed = Path(str(config.get("output_feed") or "")).expanduser()
    if output_feed.parent.name == "feeds":
        show_slug = output_feed.parent.parent.name.strip()
        if show_slug:
            return show_slug
    return None


def build_episode_inventory_payload(
    *,
    episodes: Sequence[Dict[str, Any]],
    config: Dict[str, Any],
    last_build: dt.datetime,
) -> Dict[str, Any]:
    quiz_cfg = config.get("quiz") if isinstance(config.get("quiz"), dict) else {}
    subject_slug = str(
        config.get("subject_slug")
        or quiz_cfg.get("subject_slug")
        or ""
    ).strip().lower() or None
    show_slug = _inventory_show_slug(config)
    output_feed = Path(str(config.get("output_feed") or "")).expanduser()

    serialized_episodes: List[Dict[str, Any]] = []
    for episode in episodes:
        if not isinstance(episode, dict):
            continue
        serialized_episodes.append(
            {
                "episode_key": str(episode.get("episode_key") or episode.get("guid") or "").strip(),
                "guid": str(episode.get("guid") or "").strip(),
                "title": str(episode.get("title") or "").strip(),
                "description": str(episode.get("description") or "").strip(),
                "link": str(episode.get("link") or "").strip(),
                "pub_date": str(episode.get("pubDate") or "").strip(),
                "published_at": (
                    episode["published_at"].isoformat()
                    if isinstance(episode.get("published_at"), dt.datetime)
                    else str(episode.get("published_at") or "").strip()
                ),
                "mime_type": str(episode.get("mimeType") or "").strip(),
                "size": episode.get("size"),
                "duration": str(episode.get("duration") or "").strip(),
                "image": str(episode.get("image") or "").strip(),
                "audio_url": str(episode.get("audio_url") or "").strip(),
                "lecture_key": str(episode.get("lecture_key") or "").strip(),
                "episode_kind": str(episode.get("episode_kind") or "").strip(),
                "podcast_kind": str(episode.get("podcast_kind") or "").strip(),
                "source_name": str(episode.get("source_name") or "").strip(),
                "source_drive_file_id": str(episode.get("source_drive_file_id") or "").strip(),
                "source_storage_provider": str(episode.get("source_storage_provider") or "").strip(),
                "source_storage_key": str(episode.get("source_storage_key") or "").strip(),
                "source_path": str(episode.get("source_path") or "").strip(),
                "sort_week": episode.get("sort_week"),
                "sort_lecture": episode.get("sort_lecture"),
                "sort_tail": bool(episode.get("sort_tail")),
                "sort_tail_index": episode.get("sort_tail_index"),
            }
        )

    return {
        "version": 2,
        "storage_provider": resolve_storage_provider(config),
        "show_slug": show_slug,
        "subject_slug": subject_slug,
        "generated_at": last_build.isoformat(),
        "feed_path": str(output_feed),
        "episodes": serialized_episodes,
    }


def _load_existing_inventory_identity_map(config: Dict[str, Any]) -> Dict[str, str]:
    inventory_path = _output_inventory_path(config) or _default_inventory_path(
        Path(str(config.get("output_feed") or "")).expanduser()
    )
    identity_map: Dict[str, str] = {}
    if not inventory_path.exists():
        return _load_existing_feed_identity_map(config)
    try:
        payload = load_json(inventory_path)
    except Exception as exc:  # noqa: BLE001
        print(
            f"Warning: failed to load existing inventory identity map from {inventory_path}: {exc}",
            file=sys.stderr,
        )
        return _load_existing_feed_identity_map(config)

    raw_episodes = payload.get("episodes")
    if not isinstance(raw_episodes, list):
        return _load_existing_feed_identity_map(config)

    for raw_episode in raw_episodes:
        if not isinstance(raw_episode, dict):
            continue
        guid = str(raw_episode.get("guid") or raw_episode.get("episode_key") or "").strip()
        if not guid:
            continue
        for key_name in (
            "source_storage_key",
            "source_path",
            "source_drive_file_id",
            "source_name",
            "title",
        ):
            raw_key = str(raw_episode.get(key_name) or "").strip()
            if raw_key and raw_key not in identity_map:
                identity_map[raw_key] = guid
    feed_identity_map = _load_existing_feed_identity_map(config)
    for raw_key, guid in feed_identity_map.items():
        if raw_key and raw_key not in identity_map:
            identity_map[raw_key] = guid
    return identity_map


def _load_existing_inventory_publication_state_map(config: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    inventory_path = _output_inventory_path(config) or _default_inventory_path(
        Path(str(config.get("output_feed") or "")).expanduser()
    )
    if not inventory_path.exists():
        return _load_existing_feed_publication_state_map(config)

    try:
        payload = load_json(inventory_path)
    except Exception as exc:  # noqa: BLE001
        print(
            f"Warning: failed to load existing inventory publication state from {inventory_path}: {exc}",
            file=sys.stderr,
        )
        return _load_existing_feed_publication_state_map(config)

    raw_episodes = payload.get("episodes")
    if not isinstance(raw_episodes, list):
        return _load_existing_feed_publication_state_map(config)

    state_map: Dict[str, Dict[str, str]] = {}
    for raw_episode in raw_episodes:
        if not isinstance(raw_episode, dict):
            continue
        state = _publication_state_from_episode(raw_episode)
        if not state:
            continue
        for key_name in (
            "guid",
            "episode_key",
            "source_storage_key",
            "source_path",
            "source_drive_file_id",
            "source_name",
            "title",
        ):
            raw_key = str(raw_episode.get(key_name) or "").strip()
            if raw_key and raw_key not in state_map:
                state_map[raw_key] = state
        source_name = str(raw_episode.get("source_name") or "").strip()
        if source_name:
            logical_id = logical_episode_id(source_name)
            if logical_id and logical_id not in state_map:
                state_map[logical_id] = state

    feed_state_map = _load_existing_feed_publication_state_map(config)
    for raw_key, state in feed_state_map.items():
        if raw_key and raw_key not in state_map:
            state_map[raw_key] = state
    return state_map


def _load_existing_feed_identity_map(config: Dict[str, Any]) -> Dict[str, str]:
    output_feed = Path(str(config.get("output_feed") or "")).expanduser()
    if not output_feed.exists():
        return {}

    try:
        from xml.etree import ElementTree as ET

        root = ET.fromstring(output_feed.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(
            f"Warning: failed to load existing feed identity map from {output_feed}: {exc}",
            file=sys.stderr,
        )
        return {}

    identity_map: Dict[str, str] = {}
    channel = root.find("channel")
    if channel is None:
        return identity_map

    for item in channel.findall("item"):
        guid = str(item.findtext("guid") or "").strip()
        if not guid:
            continue
        title = str(item.findtext("title") or "").strip()
        if title and title not in identity_map:
            identity_map[title] = guid
        enclosure = item.find("enclosure")
        if enclosure is None:
            continue
        enclosure_url = str(enclosure.get("url") or "").strip()
        if not enclosure_url:
            continue
        file_id = _extract_public_file_id(enclosure_url)
        if file_id and file_id not in identity_map:
            identity_map[file_id] = guid
    return identity_map


def _load_existing_feed_publication_state_map(config: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    output_feed = Path(str(config.get("output_feed") or "")).expanduser()
    if not output_feed.exists():
        return {}

    try:
        from xml.etree import ElementTree as ET

        root = ET.fromstring(output_feed.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(
            f"Warning: failed to load existing feed publication state from {output_feed}: {exc}",
            file=sys.stderr,
        )
        return {}

    state_map: Dict[str, Dict[str, str]] = {}
    channel = root.find("channel")
    if channel is None:
        return state_map

    for item in channel.findall("item"):
        state = _publication_state_from_feed_item(item)
        if not state:
            continue
        title = str(item.findtext("title") or "").strip()
        if title and title not in state_map:
            state_map[title] = state
        enclosure = item.find("enclosure")
        if enclosure is None:
            continue
        enclosure_url = str(enclosure.get("url") or "").strip()
        if not enclosure_url:
            continue
        file_id = _extract_public_file_id(enclosure_url)
        if file_id and file_id not in state_map:
            state_map[file_id] = state
    return state_map


def _extract_public_file_id(url: str) -> str:
    parsed = urlparse(url)
    query_id = parse_qs(parsed.query).get("id", [])
    if query_id:
        return str(query_id[0] or "").strip()
    return ""


def _apply_existing_identity(file_entry: Dict[str, Any], identity_map: Dict[str, str]) -> None:
    if str(file_entry.get("stable_guid") or "").strip():
        return
    for candidate in (
        file_entry.get("source_storage_key"),
        file_entry.get("source_path"),
        file_entry.get("source_drive_file_id"),
        file_entry.get("id"),
        file_entry.get("name"),
    ):
        key = str(candidate or "").strip()
        if not key:
            continue
        existing_guid = identity_map.get(key)
        if existing_guid:
            file_entry["stable_guid"] = existing_guid
            return


def _publication_state_from_episode(raw_episode: Dict[str, Any]) -> Dict[str, str]:
    guid = str(raw_episode.get("guid") or raw_episode.get("episode_key") or "").strip()
    published_at = str(raw_episode.get("published_at") or "").strip()
    pub_date = str(raw_episode.get("pub_date") or raw_episode.get("pubDate") or "").strip()
    if not published_at and pub_date:
        try:
            published_at = parsedate_to_datetime(pub_date).isoformat()
        except Exception:  # noqa: BLE001
            published_at = ""
    state: Dict[str, str] = {}
    if guid:
        state["guid"] = guid
    if published_at:
        state["published_at"] = published_at
    if pub_date:
        state["pub_date"] = pub_date
    return state


def _publication_state_from_feed_item(item: Any) -> Dict[str, str]:
    guid = str(item.findtext("guid") or "").strip()
    pub_date = str(item.findtext("pubDate") or "").strip()
    published_at = ""
    if pub_date:
        try:
            published_at = parsedate_to_datetime(pub_date).isoformat()
        except Exception:  # noqa: BLE001
            published_at = ""
    state: Dict[str, str] = {}
    if guid:
        state["guid"] = guid
    if published_at:
        state["published_at"] = published_at
    if pub_date:
        state["pub_date"] = pub_date
    return state


def _apply_existing_publication_state(
    file_entry: Dict[str, Any],
    publication_state_map: Dict[str, Dict[str, str]],
) -> None:
    logical_id = logical_episode_id(str(file_entry.get("name") or file_entry.get("source_name") or "").strip())
    for candidate in (
        file_entry.get("stable_guid"),
        file_entry.get("source_storage_key"),
        file_entry.get("source_path"),
        file_entry.get("source_drive_file_id"),
        file_entry.get("id"),
        file_entry.get("name"),
        logical_id,
    ):
        key = str(candidate or "").strip()
        if not key:
            continue
        state = publication_state_map.get(key)
        if not state:
            continue
        if not str(file_entry.get("stable_guid") or "").strip():
            guid = str(state.get("guid") or "").strip()
            if guid:
                file_entry["stable_guid"] = guid
        if not str(file_entry.get("stable_published_at") or "").strip():
            published_at = str(state.get("published_at") or "").strip()
            if published_at:
                file_entry["stable_published_at"] = published_at
        if str(file_entry.get("stable_guid") or "").strip() and str(file_entry.get("stable_published_at") or "").strip():
            return


def _registry_baseline_published_at(entry: Dict[str, Any]) -> Optional[str]:
    variants = entry.get("variants") if isinstance(entry.get("variants"), dict) else {}
    baseline_variant = variants.get("A") if isinstance(variants.get("A"), dict) else {}
    active_slot = str(entry.get("active_variant") or "A").strip().upper()
    if active_slot not in {"A", "B"}:
        active_slot = "A"
    active_variant = variants.get(active_slot) if isinstance(variants.get(active_slot), dict) else {}
    for variant in (baseline_variant, active_variant):
        published_at = str(variant.get("published_at") or "").strip()
        if published_at:
            return published_at
    return None


def _load_regeneration_registry(path: Path) -> Dict[str, Any]:
    try:
        payload = load_json(path)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"failed to load regeneration registry from {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"regeneration registry at {path} must be a JSON object")
    return payload


def _normalize_registry_entry_map(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return {}
    mapped: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        logical_id = str(entry.get("logical_episode_id") or "").strip()
        if logical_id and logical_id not in mapped:
            mapped[logical_id] = entry
    return mapped


def _variant_matches_file_entry(variant: Dict[str, Any], file_entry: Dict[str, Any]) -> bool:
    file_id = str(file_entry.get("id") or "").strip()
    file_name = str(file_entry.get("name") or "").strip()
    source_path = str(file_entry.get("source_path") or "").strip()
    source_storage_key = str(file_entry.get("source_storage_key") or "").strip()
    candidates = {
        str(variant.get("episode_key") or "").strip(),
        str(variant.get("source_name") or "").strip(),
        str(variant.get("canonical_source_name") or "").strip(),
    }
    values = {file_id, file_name, source_path, source_storage_key}
    values.discard("")
    candidates.discard("")
    return bool(candidates & values)


def _apply_regeneration_marker(title_value: str, marker: str, position: str) -> str:
    title = str(title_value or "").strip()
    resolved_marker = str(marker or "").strip()
    if not title or not resolved_marker:
        return title
    if title.startswith(f"{resolved_marker} ") or title == resolved_marker:
        return title
    if title.endswith(f" {resolved_marker}"):
        title = title[: -len(resolved_marker)].rstrip()
    normalized_position = str(position or "").strip().lower()
    if normalized_position in {"prefix", "prepend", "leading"}:
        return f"{resolved_marker} {title}"
    return f"{title} {resolved_marker}"


def _registry_selection_for_file(
    file_entry: Dict[str, Any],
    registry_entries_by_lid: Dict[str, Dict[str, Any]],
) -> Optional[Tuple[bool, Optional[str], Optional[str]]]:
    source_name = str(file_entry.get("name") or file_entry.get("source_name") or "").strip()
    if not source_name:
        return None
    logical_id = logical_episode_id(source_name)
    entry = registry_entries_by_lid.get(logical_id)
    if entry is None:
        return None

    variants = entry.get("variants") if isinstance(entry.get("variants"), dict) else {}
    active_slot = str(entry.get("active_variant") or "A").strip().upper()
    if active_slot not in {"A", "B"}:
        active_slot = "A"
    matched_slots: List[str] = []
    for slot in ("A", "B"):
        variant = variants.get(slot) if isinstance(variants.get(slot), dict) else {}
        if variant and _variant_matches_file_entry(variant, file_entry):
            matched_slots.append(slot)
    if not matched_slots:
        return (False, logical_id, active_slot)
    matched_slot = active_slot if active_slot in matched_slots else matched_slots[0]
    return (matched_slot == active_slot, logical_id, matched_slot)


def _render_public_media_url(file_entry: Dict[str, Any], public_link_template: str) -> str:
    storage_key = str(
        file_entry.get("source_storage_key")
        or file_entry.get("id")
        or file_entry.get("source_path")
        or ""
    ).strip()
    source_path = str(file_entry.get("source_path") or storage_key).strip()
    return public_link_template.format(
        file_id=str(file_entry.get("id") or "").strip(),
        file_name=str(file_entry.get("name") or "").strip(),
        file_path=quote(storage_key, safe="/:@"),
        source_path=quote(source_path, safe="/:@"),
        raw_file_path=source_path,
        raw_storage_key=storage_key,
        storage_key=storage_key,
    )


def resolve_public_link_template(config: Dict[str, Any]) -> str:
    provider = resolve_storage_provider(config)
    storage_cfg = config.get("storage") if isinstance(config.get("storage"), dict) else {}
    default_drive_template = "https://drive.google.com/uc?export=download&id={file_id}"

    if provider != "drive":
        storage_public_template = str(storage_cfg.get("public_link_template") or "").strip()
        if storage_public_template:
            return storage_public_template

        public_base_url = str(storage_cfg.get("public_base_url") or "").strip().rstrip("/")
        if public_base_url:
            return f"{public_base_url}/{{file_path}}"

    return str(config.get("public_link_template") or default_drive_template)


def _is_retryable_http_error(exc: BaseException) -> bool:
    if HttpError is None or not isinstance(exc, HttpError):
        return False

    status_code = getattr(getattr(exc, "resp", None), "status", None)
    if status_code in GOOGLE_API_RETRY_STATUS_CODES:
        return True

    content = getattr(exc, "content", b"")
    if isinstance(content, bytes):
        try:
            payload = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {}
        errors = payload.get("error", {}).get("errors", []) if isinstance(payload, dict) else []
        if isinstance(errors, list):
            for entry in errors:
                reason = str((entry or {}).get("reason") or "").strip()
                if reason in GOOGLE_API_RETRY_REASONS:
                    return True
    return False


def _execute_with_retry(request):
    for attempt in range(GOOGLE_API_MAX_RETRIES + 1):
        try:
            return request.execute()
        except Exception as exc:  # pragma: no cover - network failure path
            if not _is_retryable_http_error(exc) or attempt >= GOOGLE_API_MAX_RETRIES:
                raise
            delay = GOOGLE_API_RETRY_BASE_DELAY_SECONDS * (2**attempt) + random.uniform(0.0, 0.35)
            time.sleep(delay)


def _drive_list(
    service,
    *,
    query: str,
    fields: str,
    drive_id: Optional[str],
    supports_all_drives: bool,
) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    page_token: Optional[str] = None
    while True:
        params: Dict[str, Any] = {
            "q": query,
            "spaces": "drive",
            "pageToken": page_token,
            "pageSize": 100,
            "fields": fields,
            "orderBy": "createdTime desc",
        }
        if supports_all_drives or drive_id:
            params.update(
                {
                    "supportsAllDrives": True,
                    "includeItemsFromAllDrives": True,
                }
            )
        if drive_id:
            params.update({"driveId": drive_id, "corpora": "drive"})
        response = _execute_with_retry(service.files().list(**params))
        entries.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return entries


def _build_mime_query(filters: Optional[Iterable[str]]) -> str:
    terms = [term for term in (filters or ["audio/"]) if term]
    clauses: List[str] = []
    for term in terms:
        sanitized = term.replace("'", "\\'")
        if term.endswith("/"):
            clauses.append(f"mimeType contains '{sanitized}'")
        else:
            clauses.append(f"mimeType = '{sanitized}'")
    if not clauses:
        clauses.append("mimeType contains 'audio/'")
    return "(" + " or ".join(clauses) + ")"


def list_drive_files(
    service,
    folder_id: str,
    *,
    drive_id: Optional[str] = None,
    supports_all_drives: bool = False,
    mime_type_filters: Optional[Iterable[str]] = None,
    fields: Optional[str] = None,
) -> List[Dict[str, Any]]:
    files: List[Dict[str, Any]] = []
    pending: List[str] = [folder_id]
    seen: Set[str] = set()
    file_fields = fields or (
        "nextPageToken, files(id,name,mimeType,size,modifiedTime,createdTime,md5Checksum,parents,starred,properties,appProperties)"
    )
    folder_fields = "nextPageToken, files(id,name)"

    mime_filter_clause = _build_mime_query(mime_type_filters)

    while pending:
        current_folder = pending.pop(0)
        if current_folder in seen:
            continue
        seen.add(current_folder)

        query = f"'{current_folder}' in parents and {mime_filter_clause} and trashed = false"
        files.extend(
            _drive_list(
                service,
                query=query,
                fields=file_fields,
                drive_id=drive_id,
                supports_all_drives=supports_all_drives,
            )
        )

        folder_query = (
            f"'{current_folder}' in parents and mimeType = 'application/vnd.google-apps.folder' "
            "and trashed = false"
        )
        subfolders = _drive_list(
            service,
            query=folder_query,
            fields=folder_fields,
            drive_id=drive_id,
            supports_all_drives=supports_all_drives,
        )
        for folder in subfolders:
            folder_id_value = folder.get("id")
            if folder_id_value and folder_id_value not in seen:
                pending.append(folder_id_value)

    return files


def list_audio_files(
    service,
    folder_id: str,
    *,
    drive_id: Optional[str] = None,
    supports_all_drives: bool = False,
    mime_type_filters: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    return list_drive_files(
        service,
        folder_id,
        drive_id=drive_id,
        supports_all_drives=supports_all_drives,
        mime_type_filters=mime_type_filters,
    )


def _listify(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _strip_cfg_tag_suffix(value: str) -> str:
    if not value:
        return value
    return CFG_TAG_PATTERN.sub("", value).strip()


def _strip_cfg_tags(value: str) -> str:
    if not value:
        return value
    return CFG_TAG_ANYWHERE_PATTERN.sub("", value).strip()


def _strip_cfg_tag_from_filename(name: str) -> str:
    if not name:
        return name
    path = Path(name)
    suffix = path.suffix
    stem = name[: -len(suffix)] if suffix else name
    return f"{_strip_cfg_tag_suffix(stem)}{suffix}"


WEEK_X_IN_STEM_PATTERN = re.compile(r"^(W\d{1,2}L\d+)\s*(?:-\s*)?X\s+", re.IGNORECASE)
LEADING_EXERCISE_X_PATTERN = re.compile(r"^x\b[\s._\-–:]*", re.IGNORECASE)
LOOKUP_LECTURE_KEY_PATTERN = re.compile(r"\bW0*(\d{1,2})L0*(\d{1,2})\b", re.IGNORECASE)
LOOKUP_PAGENUM_PATTERN = re.compile(r"\b(?:s\.|pp?\.)\s*[\d, \-–]+", re.IGNORECASE)


def _normalize_name_for_lookup(name: str) -> str:
    stripped = _strip_cfg_tags(name)
    path = Path(stripped)
    suffix = path.suffix
    stem = stripped[: -len(suffix)] if suffix else stripped
    lecture_match = LOOKUP_LECTURE_KEY_PATTERN.search(stem)
    lecture_key = (
        f"W{int(lecture_match.group(1))}L{int(lecture_match.group(2))}" if lecture_match else ""
    )
    stem = re.sub(r"\s+\[(?:en|da|dk|tts|short|brief)\]\s*$", "", stem, flags=re.IGNORECASE)
    stem = LANGUAGE_TAG_PATTERN.sub("", stem)
    stem = BRIEF_TAG_PATTERN.sub("", stem)
    if WEEKLY_OVERVIEW_SUBJECT_PATTERN.search(stem):
        return f"{lecture_key}|weekly{suffix}".casefold()
    stem = strip_week_prefix(stem)
    stem = LEADING_EXERCISE_X_PATTERN.sub("", stem).strip()
    stem = re.sub(r"\s+", " ", stem).strip()
    stem = WEEK_X_IN_STEM_PATTERN.sub(r"\1 ", stem).strip()
    stem = re.sub(r"\s+", " ", stem).strip()
    page_match = LOOKUP_PAGENUM_PATTERN.search(stem)
    author_year_match = re.match(r"^(.*?\(\d{4}(?:[-–]\d{4})?\))", stem)
    if author_year_match:
        subject = author_year_match.group(1).strip(" .")
        if page_match:
            pages = re.sub(r"\s+", " ", page_match.group(0).lower()).strip()
            stem = f"{subject} {pages}"
        elif len(stem) > len(subject) + 24:
            stem = subject
    normalized = f"{lecture_key}|{stem}" if lecture_key else stem
    return f"{normalized}{suffix}".casefold()


def _normalize_name_for_lookup_without_lecture(name: str) -> str:
    normalized = _normalize_name_for_lookup(name)
    if "|" not in normalized:
        return normalized
    return normalized.split("|", 1)[1]


def _lookup_by_name_with_cfg_fallback(mapping: Dict[str, Any], name: str) -> Any:
    if name in mapping:
        return mapping[name]
    stripped = _strip_cfg_tag_from_filename(name)
    if stripped in mapping:
        return mapping[stripped]
    normalized = _normalize_name_for_lookup(name)
    for key, value in mapping.items():
        if isinstance(key, str) and _normalize_name_for_lookup(key) == normalized:
            return value
    relaxed_normalized = _normalize_name_for_lookup_without_lecture(name)
    for key, value in mapping.items():
        if (
            isinstance(key, str)
            and _normalize_name_for_lookup_without_lecture(key) == relaxed_normalized
        ):
            return value
    for key, value in mapping.items():
        if isinstance(key, str) and _strip_cfg_tag_from_filename(key) == stripped:
            return value
    return None


def _lookup_key_with_cfg_fallback(mapping: Dict[str, Any], name: str) -> Optional[str]:
    if name in mapping:
        return name
    stripped = _strip_cfg_tag_from_filename(name)
    if stripped in mapping:
        return stripped
    normalized = _normalize_name_for_lookup(name)
    for key in mapping:
        if isinstance(key, str) and _normalize_name_for_lookup(key) == normalized:
            return key
    relaxed_normalized = _normalize_name_for_lookup_without_lecture(name)
    for key in mapping:
        if (
            isinstance(key, str)
            and _normalize_name_for_lookup_without_lecture(key) == relaxed_normalized
        ):
            return key
    for key in mapping:
        if isinstance(key, str) and _strip_cfg_tag_from_filename(key) == stripped:
            return key
    return None


def _normalize_quiz_difficulty(value: Any, *, relative_path: Optional[str] = None) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip().lower()
    if isinstance(relative_path, str) and relative_path.strip():
        match = QUIZ_DIFFICULTY_RE.search(relative_path)
        if match:
            difficulty = match.group("difficulty").strip().lower()
            if difficulty:
                return difficulty
    return "medium"


def _quiz_link_sort_key(link: Dict[str, str]) -> Tuple[int, str, str]:
    difficulty = _normalize_quiz_difficulty(link.get("difficulty"), relative_path=link.get("relative_path"))
    rel_path = str(link.get("relative_path") or "")
    return (QUIZ_DIFFICULTY_SORT_ORDER.get(difficulty, 99), difficulty, rel_path)


def _quiz_primary_sort_key(link: Dict[str, str]) -> Tuple[int, Tuple[int, str, str]]:
    difficulty = _normalize_quiz_difficulty(link.get("difficulty"), relative_path=link.get("relative_path"))
    return (QUIZ_PRIMARY_DIFFICULTY_SORT_ORDER.get(difficulty, 99), _quiz_link_sort_key(link))


def _normalize_quiz_link_entry(raw_entry: Any) -> Optional[Dict[str, str]]:
    if not isinstance(raw_entry, dict):
        return None
    relative_path = raw_entry.get("relative_path")
    if not isinstance(relative_path, str) or not relative_path.strip():
        return None
    normalized_path = relative_path.strip()
    difficulty = _normalize_quiz_difficulty(
        raw_entry.get("difficulty"),
        relative_path=normalized_path,
    )
    return {
        "relative_path": normalized_path,
        "format": str(raw_entry.get("format") or "html"),
        "difficulty": difficulty,
    }


def _extract_quiz_links(raw_entry: Any) -> List[Dict[str, str]]:
    candidates: List[Dict[str, str]] = []
    if isinstance(raw_entry, dict):
        direct = _normalize_quiz_link_entry(raw_entry)
        if direct:
            candidates.append(direct)
        nested = raw_entry.get("links")
        if isinstance(nested, list):
            for item in nested:
                normalized = _normalize_quiz_link_entry(item)
                if normalized:
                    candidates.append(normalized)
    elif isinstance(raw_entry, list):
        for item in raw_entry:
            normalized = _normalize_quiz_link_entry(item)
            if normalized:
                candidates.append(normalized)
    if not candidates:
        return []
    deduped: Dict[str, Dict[str, str]] = {}
    for candidate in sorted(candidates, key=_quiz_link_sort_key):
        difficulty = candidate["difficulty"]
        if difficulty in deduped:
            continue
        deduped[difficulty] = candidate
    return list(deduped.values())


def _build_quiz_url(base_url: Any, relative_path: str) -> Optional[str]:
    if not isinstance(base_url, str) or not base_url.strip():
        return None
    base = base_url
    if not base.endswith("/"):
        base += "/"
    return base + quote(relative_path.lstrip("/"), safe="/")


def _resolve_quiz_link_payloads(base_url: Any, raw_entry: Any) -> List[Dict[str, str]]:
    links = _extract_quiz_links(raw_entry)
    if not links:
        return []
    resolved: List[Dict[str, str]] = []
    for link in links:
        url = _build_quiz_url(base_url, link["relative_path"])
        if not url:
            continue
        resolved.append(
            {
                "url": url,
                "difficulty": _normalize_quiz_difficulty(
                    link.get("difficulty"),
                    relative_path=link.get("relative_path"),
                ),
            }
        )
    return resolved


def _resolve_quiz_display_labels(
    quiz_cfg: Optional[Dict[str, Any]],
) -> Tuple[str, str, Dict[str, str]]:
    singular_label = "Quiz"
    plural_label = "Quizzes"
    difficulty_labels = dict(QUIZ_DIFFICULTY_LABELS)
    if not isinstance(quiz_cfg, dict):
        return singular_label, plural_label, difficulty_labels

    labels = quiz_cfg.get("labels")
    if not isinstance(labels, dict):
        return singular_label, plural_label, difficulty_labels

    single_raw = labels.get("single")
    if isinstance(single_raw, str) and single_raw.strip():
        singular_label = single_raw.strip()

    multiple_raw = labels.get("multiple")
    if isinstance(multiple_raw, str) and multiple_raw.strip():
        plural_label = multiple_raw.strip()

    difficulty_raw = labels.get("difficulty")
    if isinstance(difficulty_raw, dict):
        for key, value in difficulty_raw.items():
            if not isinstance(key, str):
                continue
            if not isinstance(value, str) or not value.strip():
                continue
            difficulty_labels[key.strip().lower()] = value.strip()

    return singular_label, plural_label, difficulty_labels


def _render_quiz_block(
    quiz_links: Sequence[Dict[str, str]],
    *,
    singular_label: str = "Quiz",
    plural_label: str = "Quizzes",
    difficulty_labels: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    if not quiz_links:
        return None
    labels = difficulty_labels or QUIZ_DIFFICULTY_LABELS
    if len(quiz_links) == 1:
        return f"\n\n{singular_label}:\n{quiz_links[0]['url']}"
    lines = [f"\n\n{plural_label}:"]
    for link in quiz_links:
        difficulty = _normalize_quiz_difficulty(link.get("difficulty"))
        label = labels.get(difficulty, difficulty.capitalize())
        lines.append(f"- {label}: {link['url']}")
    return "\n".join(lines)

CANONICAL_WEEK_LECTURE_PREFIX_PATTERN = re.compile(
    r"^(?P<full>w0*(?P<week>\d{1,2})l0*(?P<lecture>\d+))\b[\s._-]*",
    re.IGNORECASE,
)


def _normalize_stem(name: str) -> str:
    stem = AUDIO_COPY_SUFFIX_PATTERN.sub("", Path(name).stem).strip()
    return _strip_cfg_tag_suffix(stem).casefold().strip()


def _canonicalize_episode_stem(name: str) -> str:
    stem = AUDIO_COPY_SUFFIX_PATTERN.sub("", Path(name).stem).strip()
    stem = _strip_cfg_tag_suffix(stem)
    if not stem:
        return ""
    stem = stem.replace("–", "-").replace("—", "-")
    stem = re.sub(r"\.{2,}", ".", stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    match = CANONICAL_WEEK_LECTURE_PREFIX_PATTERN.match(stem)
    if not match:
        return stem.casefold()
    week = int(match.group("week"))
    lesson = int(match.group("lecture"))
    remainder = stem[match.end() :].strip()
    if remainder:
        dup = CANONICAL_WEEK_LECTURE_PREFIX_PATTERN.match(remainder)
        if dup and int(dup.group("week")) == week and int(dup.group("lecture")) == lesson:
            remainder = remainder[dup.end() :].strip()
    canonical_week = f"W{week:02d}L{lesson}"
    remainder = WEEK_X_IN_STEM_PATTERN.sub(r"\1 ", f"{canonical_week} {remainder}".strip())
    remainder = re.sub(rf"^{re.escape(canonical_week)}\s+", "", remainder, flags=re.IGNORECASE).strip()
    if remainder:
        stem = f"{canonical_week} - {remainder}"
    else:
        stem = canonical_week
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem.casefold()


def _drive_file_size_bytes(file_entry: Dict[str, Any]) -> int:
    raw_value = file_entry.get("size")
    if isinstance(raw_value, bool):
        return 0
    try:
        return max(0, int(raw_value))
    except (TypeError, ValueError):
        return 0


def _drive_file_extension_rank(file_entry: Dict[str, Any]) -> int:
    ext = Path(str(file_entry.get("name") or "")).suffix.casefold()
    try:
        return PREFERRED_AUDIO_EXTENSIONS.index(ext)
    except ValueError:
        return len(PREFERRED_AUDIO_EXTENSIONS)


def _looks_like_copy_suffix(file_entry: Dict[str, Any]) -> bool:
    stem = Path(str(file_entry.get("name") or "")).stem
    return bool(AUDIO_COPY_SUFFIX_PATTERN.search(stem))


def _drive_file_preference_key(file_entry: Dict[str, Any]) -> Tuple[int, int, int, str, str, str]:
    size_bytes = _drive_file_size_bytes(file_entry)
    mime_type = str(file_entry.get("mimeType") or "").casefold()
    ext_rank = _drive_file_extension_rank(file_entry)
    modified = str(file_entry.get("modifiedTime") or file_entry.get("createdTime") or "")
    name = str(file_entry.get("name") or "")
    file_id = str(file_entry.get("id") or "")
    return (
        1 if size_bytes > 0 else 0,
        1 if mime_type == "audio/mpeg" else 0,
        -ext_rank,
        0 if _looks_like_copy_suffix(file_entry) else 1,
        modified,
        name,
        file_id,
    )


def _collapse_duplicate_drive_files(files: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[Tuple[str, ...], str], List[Tuple[int, Dict[str, Any]]]] = {}
    passthrough: Dict[int, Dict[str, Any]] = {}

    for index, file_entry in enumerate(files):
        parents = tuple(str(parent) for parent in (file_entry.get("parents") or []) if parent)
        canonical_stem = _canonicalize_episode_stem(str(file_entry.get("name") or ""))
        if not parents or not canonical_stem:
            passthrough[index] = file_entry
            continue
        grouped.setdefault((parents, canonical_stem), []).append((index, file_entry))

    chosen_by_key: Dict[Tuple[Tuple[str, ...], str], Dict[str, Any]] = {}
    for key, entries in grouped.items():
        if len(entries) == 1:
            chosen_by_key[key] = entries[0][1]
            continue
        choice = max((entry for _, entry in entries), key=_drive_file_preference_key)
        chosen_by_key[key] = choice
        choice_size = _drive_file_size_bytes(choice)
        candidate_labels = ", ".join(
            f"{entry.get('name', '')} ({entry.get('id', '')}, {_drive_file_size_bytes(entry)} bytes)"
            for _, entry in entries
        )
        print(
            "Warning: collapsed duplicate Drive audio sources for "
            f"'{choice.get('name', '')}' using {choice.get('id', '')} ({choice_size} bytes). "
            f"Candidates: {candidate_labels}",
            file=sys.stderr,
        )

    collapsed: List[Dict[str, Any]] = []
    emitted_keys: Set[Tuple[Tuple[str, ...], str]] = set()
    for index, file_entry in enumerate(files):
        passthrough_entry = passthrough.get(index)
        if passthrough_entry is not None:
            collapsed.append(passthrough_entry)
            continue
        parents = tuple(str(parent) for parent in (file_entry.get("parents") or []) if parent)
        canonical_stem = _canonicalize_episode_stem(str(file_entry.get("name") or ""))
        key = (parents, canonical_stem)
        if key in emitted_keys:
            continue
        collapsed.append(chosen_by_key[key])
        emitted_keys.add(key)

    return collapsed


def _folder_key(folder_names: List[str]) -> Tuple[str, ...]:
    return tuple(part.casefold() for part in folder_names if part is not None)


def _extension_rank(name: str, preferred_exts: Sequence[str]) -> int:
    ext = Path(name).suffix.casefold()
    for index, preferred in enumerate(preferred_exts):
        if ext == preferred:
            return index
    return len(preferred_exts)


def _select_preferred_image(
    current: Optional[Dict[str, Any]],
    candidate: Dict[str, Any],
    preferred_exts: Sequence[str],
) -> Dict[str, Any]:
    if current is None:
        return candidate
    if _extension_rank(candidate.get("name", ""), preferred_exts) < _extension_rank(
        current.get("name", ""), preferred_exts
    ):
        return candidate
    return current


def _is_folder_prefix(prefix: Tuple[str, ...], value: Tuple[str, ...]) -> bool:
    if len(prefix) > len(value):
        return False
    return value[: len(prefix)] == prefix


def _select_unique_best_candidate(
    candidates: Sequence[Dict[str, Any]],
    preferred_exts: Sequence[str],
) -> Optional[Dict[str, Any]]:
    best: Optional[Dict[str, Any]] = None
    best_rank: Optional[int] = None
    ties = 0
    for candidate in candidates:
        rank = _extension_rank(candidate["file"].get("name", ""), preferred_exts)
        if best_rank is None or rank < best_rank:
            best_rank = rank
            best = candidate
            ties = 1
        elif rank == best_rank:
            ties += 1
    if ties == 1:
        return best["file"] if best else None
    return None


def _resolve_image_for_stem(
    *,
    lookup: Dict[Tuple[Tuple[str, ...], str], Dict[str, Any]],
    candidates_by_stem: Dict[str, List[Dict[str, Any]]],
    folder_key: Tuple[str, ...],
    stem: str,
    preferred_exts: Sequence[str],
) -> Tuple[Optional[Dict[str, Any]], str]:
    if not stem:
        return None, "missing"
    image_file = lookup.get((folder_key, stem))
    if image_file:
        return image_file, "exact"
    candidates = candidates_by_stem.get(stem, [])
    if not candidates:
        return None, "missing"
    filtered: List[Dict[str, Any]] = []
    if folder_key:
        filtered = [
            candidate
            for candidate in candidates
            if _is_folder_prefix(folder_key, candidate["folder_key"])
            or _is_folder_prefix(candidate["folder_key"], folder_key)
        ]
    if filtered:
        selected = _select_unique_best_candidate(filtered, preferred_exts)
        if selected:
            return selected, "exact"
        return None, "ambiguous"
    if not folder_key and len(candidates) == 1:
        return candidates[0]["file"], "fallback"
    return None, "ambiguous"


def _compile_regex_list(values: Any) -> List[re.Pattern]:
    patterns = _listify(values)
    compiled: List[re.Pattern] = []
    for pattern in patterns:
        try:
            compiled.append(re.compile(pattern, re.IGNORECASE))
        except re.error:
            print(f"Warning: invalid regex in filters: {pattern}", file=sys.stderr)
    return compiled


def _normalize_filter_rules(raw_rules: Any) -> List[Dict[str, Any]]:
    if not raw_rules:
        return []
    if isinstance(raw_rules, dict):
        candidates = [raw_rules]
    elif isinstance(raw_rules, list):
        candidates = raw_rules
    else:
        return []

    normalized: List[Dict[str, Any]] = []
    for entry in candidates:
        if not isinstance(entry, dict):
            continue
        rule = {
            "name_contains": _listify(entry.get("name_contains")),
            "name_regex": _compile_regex_list(entry.get("name_regex")),
            "folder_contains": _listify(entry.get("folder_contains")),
            "folder_regex": _compile_regex_list(entry.get("folder_regex")),
        }
        if any(rule.values()):
            normalized.append(rule)
    return normalized


def parse_filters(raw_filters: Any) -> Dict[str, List[Dict[str, Any]]]:
    if not raw_filters or not isinstance(raw_filters, dict):
        return {"include": [], "exclude": []}
    return {
        "include": _normalize_filter_rules(raw_filters.get("include")),
        "exclude": _normalize_filter_rules(raw_filters.get("exclude")),
    }


def _rule_matches(
    rule: Dict[str, Any],
    *,
    file_name: str,
    folder_names: List[str],
    folder_path: str,
) -> bool:
    name_lower = file_name.casefold()
    folder_lower = [name.casefold() for name in folder_names]

    name_contains = rule.get("name_contains") or []
    if name_contains and not any(token.casefold() in name_lower for token in name_contains):
        return False

    name_regex = rule.get("name_regex") or []
    if name_regex and not any(pattern.search(file_name) for pattern in name_regex):
        return False

    folder_contains = rule.get("folder_contains") or []
    if folder_contains:
        if not folder_lower:
            return False
        if not any(
            token.casefold() in folder
            for token in folder_contains
            for folder in folder_lower
        ):
            return False

    folder_regex = rule.get("folder_regex") or []
    if folder_regex:
        if not folder_path:
            return False
        if not any(pattern.search(folder_path) for pattern in folder_regex):
            return False

    return True


def matches_filters(
    file_entry: Dict[str, Any],
    folder_names: List[str],
    filters: Dict[str, List[Dict[str, Any]]],
) -> bool:
    if not filters:
        return True
    file_name = file_entry.get("name") or ""
    folder_path = "/".join(folder_names or [])

    include_rules = filters.get("include") or []
    exclude_rules = filters.get("exclude") or []

    if include_rules:
        if not any(
            _rule_matches(
                rule,
                file_name=file_name,
                folder_names=folder_names,
                folder_path=folder_path,
            )
            for rule in include_rules
        ):
            return False

    if any(
        _rule_matches(
            rule,
            file_name=file_name,
            folder_names=folder_names,
            folder_path=folder_path,
        )
        for rule in exclude_rules
    ):
        return False

    return True


def ensure_public_permission(
    service,
    file_id: str,
    *,
    dry_run: bool = False,
    supports_all_drives: bool = False,
    skip_permission_updates: bool = False,
) -> bool:
    if skip_permission_updates:
        return False
    params: Dict[str, Any] = {
        "fileId": file_id,
        "fields": "permissions(id,type,role)",
        "pageSize": 50,
    }
    if supports_all_drives:
        params["supportsAllDrives"] = True
    permissions = _execute_with_retry(service.permissions().list(**params))
    for permission in permissions.get("permissions", []):
        if permission.get("type") == "anyone" and permission.get("role") in {"reader", "commenter"}:
            return False
    if dry_run:
        return True
    create_params: Dict[str, Any] = {
        "fileId": file_id,
        "body": {"type": "anyone", "role": "reader", "allowFileDiscovery": False},
        "fields": "id",
    }
    if supports_all_drives:
        create_params["supportsAllDrives"] = True
    _execute_with_retry(service.permissions().create(**create_params))
    return True


def parse_datetime(value: str) -> dt.datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return dt.datetime.fromisoformat(value)


def format_rfc2822(value: dt.datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value.strftime("%a, %d %b %Y %H:%M:%S %z")


def item_metadata(overrides: Dict[str, Any], file_entry: Dict[str, Any]) -> Dict[str, Any]:
    by_id = overrides.get("by_id", {})
    if isinstance(by_id, dict):
        by_id_match = by_id.get(file_entry["id"])
        if isinstance(by_id_match, dict):
            return by_id_match

    by_name = overrides.get("by_name", {})
    if isinstance(by_name, dict):
        by_name_match = _lookup_by_name_with_cfg_fallback(by_name, file_entry["name"])
        if isinstance(by_name_match, dict):
            return by_name_match

    top_level_match = _lookup_by_name_with_cfg_fallback(overrides, file_entry["name"])
    if isinstance(top_level_match, dict):
        return top_level_match
    return {}


class AutoSpec:
    """Assign episode metadata based on Drive folder placement."""

    def __init__(self, spec: Dict[str, Any], *, source: Optional[Path] = None) -> None:
        self.source = source
        try:
            self.year = int(spec["year"])
        except (KeyError, TypeError, ValueError) as exc:  # pragma: no cover - defensive
            raise ValueError(f"Auto spec missing valid 'year' ({source})") from exc

        try:
            week_year = spec.get("week_reference_year", self.year)
            self.week_reference_year = int(week_year)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
            raise ValueError(
                f"Auto spec has invalid 'week_reference_year' ({source})"
            ) from exc

        tz_name = spec.get("timezone", "UTC")
        try:
            self.timezone = ZoneInfo(tz_name)
        except Exception as exc:  # pragma: no cover - invalid timezone
            raise ValueError(f"Invalid timezone '{tz_name}' in auto spec ({source})") from exc

        default_release = spec.get("default_release", {}) or {}
        self.default_weekday = int(default_release.get("weekday", 1))
        self.default_time = default_release.get("time", "08:00")

        try:
            default_increment_minutes = int(spec.get("increment_minutes", 5) or 5)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
            raise ValueError(f"Auto spec has invalid 'increment_minutes' ({source})") from exc
        self._default_increment_minutes = max(default_increment_minutes, 1)

        self.rules: List[Dict[str, Any]] = []
        self._earliest_rule_datetime: Optional[dt.datetime] = None
        for index, entry in enumerate(spec.get("rules", [])):
            try:
                iso_week = int(entry["iso_week"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Rule #{index} missing valid 'iso_week' ({source})") from exc

            release = entry.get("release", {}) or {}
            weekday = int(release.get("weekday", self.default_weekday))
            time_token = release.get("time", self.default_time)
            hour, minute, second = self._parse_time_token(time_token)
            base_datetime = (
                dt.datetime.fromisocalendar(self.year, iso_week, weekday)
                .replace(hour=hour, minute=minute, second=second, tzinfo=self.timezone)
            )

            matches: List[str] = []
            for field in ("match", "folder_labels", "labels", "aliases"):
                tokens = entry.get(field)
                if not tokens:
                    continue
                if isinstance(tokens, str):
                    matches.append(tokens.lower())
                else:
                    matches.extend(str(token).lower() for token in tokens if token)

            course_week = entry.get("course_week")

            # Helpful default aliases: "week 36" and "w36" for iso week 36.
            # Include a zero-padded variant ("w06") since folder naming often uses padding.
            matches.extend(
                {
                    f"w{iso_week}",
                    f"w{iso_week:02d}",
                    f"w {iso_week}",
                    f"w {iso_week:02d}",
                    f"week {iso_week}",
                    f"week {iso_week:02d}",
                    f"week{iso_week}",
                    f"week{iso_week:02d}",
                    str(iso_week),
                    f"{iso_week:02d}",
                }
            )

            try:
                increment_value = entry.get("increment_minutes", self._default_increment_minutes)
                increment = int(increment_value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Rule #{index} has invalid 'increment_minutes' ({source})") from exc

            self.rules.append(
                {
                    "index": index,
                    "iso_week": iso_week,
                    "course_week": course_week,
                    "topic": entry.get("topic"),
                    "match": [token.strip() for token in matches if token and token.strip()],
                    "base_datetime": base_datetime,
                    "increment_minutes": max(increment, 0),
                }
            )
            if self._earliest_rule_datetime is None or base_datetime < self._earliest_rule_datetime:
                self._earliest_rule_datetime = base_datetime

        if self._earliest_rule_datetime is None:
            self._earliest_rule_datetime = dt.datetime(self.year, 1, 1, tzinfo=self.timezone)

        self._allocations: Dict[Tuple[int, Tuple[str, ...]], int] = {}
        self._unassigned_allocations: Dict[str, dt.datetime] = {}
        self._unassigned_counter: int = 0
        self._unassigned_sequence_allocations: Dict[Tuple[int, Optional[str]], dt.datetime] = {}
        self._unassigned_sequence_counts: Dict[int, int] = {}
        self._unassigned_sequence_slot_span: int = 4
        # Place unassigned tail episodes in late summer so they sort after semester weeks
        # in clients that rely on pubDate chronology.
        self._unassigned_tail_anchor_datetime = dt.datetime(
            self.year, 8, 1, 8, 0, 0, tzinfo=self.timezone
        )

    @staticmethod
    def _parse_time_token(token: str) -> Tuple[int, int, int]:
        parts = token.split(":") if token else []
        if len(parts) == 1:
            hour = int(parts[0])
            return hour, 0, 0
        if len(parts) == 2:
            hour, minute = (int(parts[0]), int(parts[1]))
            return hour, minute, 0
        if len(parts) >= 3:
            hour, minute, second = (int(parts[0]), int(parts[1]), int(parts[2]))
            return hour, minute, second
        return 8, 0, 0

    @classmethod
    def from_path(cls, path: Path) -> "AutoSpec":
        data = load_json(path)
        return cls(data, source=path)

    def metadata_for(
        self,
        file_entry: Dict[str, Any],
        folder_names: List[str],
    ) -> Optional[Dict[str, Any]]:
        if not self.rules:
            return None

        search_candidates = [name.lower() for name in folder_names]
        if folder_names:
            search_candidates.append("/".join(name.lower() for name in folder_names))
        file_name = (file_entry.get("name") or "").lower()
        if file_name:
            search_candidates.append(file_name)

        for rule in self.rules:
            if not rule["match"]:
                continue
            if self._matches(rule["match"], search_candidates):
                scheduled = self._allocate_datetime(rule, folder_names or [file_entry.get("id", "")])
                meta: Dict[str, Any] = {
                    "published_at": scheduled.isoformat(),
                    "week_reference_year": self.week_reference_year,
                }
                voice = self._extract_voice(file_entry.get("name"))
                if voice:
                    meta.setdefault("narrator", voice)
                if rule.get("course_week") is not None:
                    meta["course_week"] = rule["course_week"]
                if rule.get("topic"):
                    topic = str(rule["topic"])
                    meta.setdefault("topic", topic)
                    summary = f"Emne for ugen: {topic}"
                    meta.setdefault("summary", summary)
                return meta
        if self._should_fallback_to_unassigned(folder_names):
            return self._fallback_unassigned_metadata(file_entry)
        return None

    @staticmethod
    def _matches(tokens: List[str], candidates: List[str]) -> bool:
        def contains_bounded(candidate: str, needle: str) -> bool:
            start = candidate.find(needle)
            while start != -1:
                end = start + len(needle)
                before_char = candidate[start - 1] if start > 0 else ""
                after_char = candidate[end] if end < len(candidate) else ""
                # Treat tokens as "word-like": require non-word boundaries around them.
                # This avoids matching week-only tokens like "w6" inside lecture tokens
                # like "w6l1", and avoids matching "6" inside "2026".
                before_is_word = bool(before_char) and (before_char.isalnum() or before_char == "_")
                after_is_word = bool(after_char) and (after_char.isalnum() or after_char == "_")
                if not before_is_word and not after_is_word:
                    return True
                start = candidate.find(needle, start + 1)
            return False

        def is_week_only_token(token: str) -> bool:
            token = token.strip().casefold()
            if not token:
                return False
            return bool(
                re.fullmatch(r"w\s*\d+", token)
                or re.fullmatch(r"week\s*\d+", token)
                or re.fullmatch(r"\d+", token)
            )

        has_lecture_token = any(
            bool(re.search(r"\bw\s*\d+\s*l\s*\d+\b", candidate, flags=re.IGNORECASE))
            for candidate in candidates
        )
        week_context_pattern = re.compile(r"\bw\s*\d+\b|\bweek\s*\d+\b", re.IGNORECASE)

        for token in tokens:
            if not token:
                continue
            needle = token.lower()
            week_only = is_week_only_token(needle)
            if has_lecture_token and is_week_only_token(needle):
                # When a lecture token is present (e.g. "W06L1"), ignore ambiguous
                # week-only tokens ("w6", "week 6", "6") that can misclassify.
                continue
            for candidate in candidates:
                if week_only:
                    candidate_compact = re.sub(r"\s+", " ", candidate.strip().casefold())
                    has_week_context = bool(week_context_pattern.search(candidate))
                    if candidate_compact != needle and not has_week_context:
                        continue
                if contains_bounded(candidate, needle):
                    return True
        return False

    @staticmethod
    def _has_week_token(folder_names: List[str]) -> bool:
        for name in folder_names:
            lowered = name.lower()
            if re.search(r"\bw\s*\d+\b", lowered) or re.search(r"\bweek\s*\d+\b", lowered):
                return True
        return False

    def _should_fallback_to_unassigned(self, folder_names: List[str]) -> bool:
        return not self._has_week_token(folder_names or [])

    def _allocate_datetime(self, rule: Dict[str, Any], folder_names: List[str]) -> dt.datetime:
        key = (rule["index"], tuple(folder_names))
        occurrence = self._allocations.get(key, 0)
        self._allocations[key] = occurrence + 1
        if occurrence == 0 or rule["increment_minutes"] == 0:
            return rule["base_datetime"]
        return rule["base_datetime"] + dt.timedelta(minutes=occurrence * rule["increment_minutes"])

    def _fallback_unassigned_metadata(self, file_entry: Dict[str, Any]) -> Dict[str, Any]:
        fallback_key = file_entry.get("id") or file_entry.get("name")
        scheduled = self._unassigned_allocations.get(fallback_key)
        if scheduled is None:
            base_datetime = self._unassigned_tail_anchor_datetime
            voice = self._extract_voice(file_entry.get("name"))
            sequence_number = self._extract_sequence_number(file_entry.get("name"))
            if sequence_number is not None and sequence_number > 0:
                seq_key = (sequence_number, voice)
                scheduled = self._unassigned_sequence_allocations.get(seq_key)
                if scheduled is None:
                    base_slot = max(sequence_number - 1, 0) * self._unassigned_sequence_slot_span
                    duplicate_index = self._unassigned_sequence_counts.get(sequence_number, 0)
                    offset_units = base_slot + duplicate_index
                    offset_minutes = offset_units * self._default_increment_minutes
                    # Keep all unassigned sequence items before the first scheduled course week.
                    # This guarantees they stay at the tail of feeds sorted by recency.
                    scheduled = base_datetime - dt.timedelta(minutes=offset_minutes)
                    self._unassigned_sequence_counts[sequence_number] = duplicate_index + 1
                    self._unassigned_sequence_allocations[seq_key] = scheduled
            if scheduled is None:
                offset_minutes = self._unassigned_counter * self._default_increment_minutes
                scheduled = base_datetime + dt.timedelta(minutes=offset_minutes)
                self._unassigned_counter += 1
            self._unassigned_allocations[fallback_key] = scheduled
        return {
            "published_at": scheduled.isoformat(),
            "suppress_week_prefix": True,
            "unassigned_tail": True,
            "week_reference_year": self.week_reference_year,
        }

    @staticmethod
    def _extract_sequence_number(file_name: Optional[str]) -> Optional[int]:
        if not file_name:
            return None
        stem = _strip_cfg_tags(file_name.rsplit(".", 1)[0]).strip()
        if not stem:
            return None
        chapter_match = re.search(r"\b(?:kapitel|chapter)\s*0*(\d{1,3})\b", stem, re.IGNORECASE)
        if chapter_match:
            match = chapter_match
        else:
            # Generic fallback for files that lead with an ordering token like "01 Foo".
            match = re.match(r"^\D*?(\d{1,3})\b", stem)
            if not match:
                return None
        try:
            return int(match.group(1))
        except ValueError:  # pragma: no cover - defensive
            return None

    @staticmethod
    def _extract_voice(file_name: Optional[str]) -> Optional[str]:
        if not file_name:
            return None
        stem = file_name.rsplit(".", 1)[0]
        head, sep, tail = stem.rpartition(" - ")
        if not sep:
            return None
        candidate = tail.strip()
        if not candidate:
            return None
        known_voices = {
            "helen": "Helen",
            "george": "George",
        }
        return known_voices.get(candidate.lower())


def get_folder_metadata(
    service,
    folder_id: str,
    cache: Dict[str, Dict[str, Any]],
    *,
    supports_all_drives: bool,
) -> Dict[str, Any]:
    if folder_id in cache:
        return cache[folder_id]
    params: Dict[str, Any] = {"fileId": folder_id, "fields": "id,name,parents"}
    if supports_all_drives:
        params["supportsAllDrives"] = True
    metadata = _execute_with_retry(service.files().get(**params))
    cache[folder_id] = metadata
    return metadata


def build_folder_path(
    service,
    folder_id: str,
    cache: Dict[str, Dict[str, Any]],
    path_cache: Dict[str, List[str]],
    *,
    root_folder_id: str,
    supports_all_drives: bool,
) -> List[str]:
    if folder_id == root_folder_id:
        return []
    if folder_id in path_cache:
        return path_cache[folder_id]

    metadata = get_folder_metadata(
        service,
        folder_id,
        cache,
        supports_all_drives=supports_all_drives,
    )
    parents = metadata.get("parents") or []
    if parents:
        parent_id = parents[0]
        if parent_id == root_folder_id:
            path = [metadata["name"]]
        else:
            parent_path = build_folder_path(
                service,
                parent_id,
                cache,
                path_cache,
                root_folder_id=root_folder_id,
                supports_all_drives=supports_all_drives,
            )
            path = parent_path + [metadata["name"]]
    else:
        path = [metadata["name"]]

    path_cache[folder_id] = path
    return path


def week_label_from_folders(folder_names: List[str]) -> Optional[str]:
    patterns = (
        re.compile(r"^w\s*(\d+)", re.IGNORECASE),
        re.compile(r"^week\s*(\d+)", re.IGNORECASE),
    )
    for name in folder_names:
        stripped = name.strip()
        for pattern in patterns:
            match = pattern.match(stripped)
            if match:
                return f"Week {int(match.group(1))}"
    return None


def format_week_range(
    published_at: Optional[dt.datetime],
    week_reference_year: Optional[int] = None,
) -> Optional[str]:
    if not published_at:
        return None
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=dt.timezone.utc)
    iso_calendar = published_at.isocalendar()
    if isinstance(iso_calendar, tuple):
        iso_year, week_number, _ = iso_calendar
    else:  # Python 3.11+ returns datetime.IsoCalendarDate
        iso_year = iso_calendar.year
        week_number = iso_calendar.week
    reference_year = week_reference_year or iso_year
    try:
        week_start_date = dt.date.fromisocalendar(reference_year, week_number, 1)
    except ValueError:
        week_start_dt = published_at - dt.timedelta(days=published_at.weekday())
        week_start_date = week_start_dt.date()
    week_end_date = week_start_date + dt.timedelta(days=6)
    return f"Uge {week_number} {week_start_date:%d/%m} - {week_end_date:%d/%m}"


def format_week_date_range(
    published_at: Optional[dt.datetime],
    week_reference_year: Optional[int] = None,
) -> Optional[str]:
    if not published_at:
        return None
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=dt.timezone.utc)
    iso_calendar = published_at.isocalendar()
    if isinstance(iso_calendar, tuple):
        iso_year, week_number, _ = iso_calendar
    else:  # Python 3.11+ returns datetime.IsoCalendarDate
        iso_year = iso_calendar.year
        week_number = iso_calendar.week
    reference_year = week_reference_year or iso_year
    try:
        week_start_date = dt.date.fromisocalendar(reference_year, week_number, 1)
    except ValueError:
        week_start_dt = published_at - dt.timedelta(days=published_at.weekday())
        week_start_date = week_start_dt.date()
    week_end_date = week_start_date + dt.timedelta(days=6)
    return f"{week_start_date:%d/%m} - {week_end_date:%d/%m}"


def format_semester_week_range(
    published_at: Optional[dt.datetime],
    semester_start: Optional[str],
) -> Optional[str]:
    if not published_at or not semester_start:
        return None
    try:
        start_date = dt.date.fromisoformat(semester_start)
    except ValueError:
        return None
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=dt.timezone.utc)
    published_date = published_at.astimezone(published_at.tzinfo).date()
    delta_days = (published_date - start_date).days
    if delta_days < 0:
        return None
    week_number = delta_days // 7 + 1
    week_start_date = start_date + dt.timedelta(days=(week_number - 1) * 7)
    week_end_date = week_start_date + dt.timedelta(days=6)
    return f"Uge {week_number} {week_start_date:%d/%m} - {week_end_date:%d/%m}"


def semester_week_info(
    published_at: Optional[dt.datetime],
    semester_start: Optional[str],
) -> Optional[Tuple[int, dt.date, dt.date]]:
    if not published_at or not semester_start:
        return None
    try:
        start_date = dt.date.fromisoformat(semester_start)
    except ValueError:
        return None
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=dt.timezone.utc)
    published_date = published_at.astimezone(published_at.tzinfo).date()
    delta_days = (published_date - start_date).days
    if delta_days < 0:
        return None
    week_number = delta_days // 7 + 1
    week_start_date = start_date + dt.timedelta(days=(week_number - 1) * 7)
    week_end_date = week_start_date + dt.timedelta(days=6)
    return week_number, week_start_date, week_end_date


def derive_semester_week_label(
    published_at: Optional[dt.datetime],
    semester_start: Optional[str],
) -> Optional[str]:
    info = semester_week_info(published_at, semester_start)
    if not info:
        return None
    week_number, _, _ = info
    return f"Week {week_number}"


def derive_week_label(
    folder_names: List[str],
    course_week: Optional[Any],
) -> Optional[str]:
    label = week_label_from_folders(folder_names)
    if label:
        return label
    if course_week is None:
        return None
    try:
        week_number = int(course_week)
    except (TypeError, ValueError):
        return None
    return f"Week {week_number}"


def _coerce_week_number(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        week_number = int(value)
    except (TypeError, ValueError):
        return None
    if week_number < 1:
        return None
    return week_number


def _resolve_semester_week_number_source(feed_config: Dict[str, Any]) -> str:
    raw_source = feed_config.get("semester_week_number_source")
    if raw_source is None:
        return DEFAULT_SEMESTER_WEEK_NUMBER_SOURCE
    if not isinstance(raw_source, str) or not raw_source.strip():
        raise ValueError("feed.semester_week_number_source must be a non-empty string.")
    source = raw_source.strip().lower()
    if source not in SEMESTER_WEEK_NUMBER_SOURCES:
        allowed = ", ".join(sorted(SEMESTER_WEEK_NUMBER_SOURCES))
        raise ValueError(
            f"feed.semester_week_number_source has unknown source '{raw_source}'. "
            f"Allowed sources: {allowed}"
        )
    return source


def _resolve_semester_week_number(
    semester_week_number_source: str,
    lecture_key_week_number: Optional[int],
    course_week_number: Optional[int],
    published_week_number: Optional[int],
) -> Optional[int]:
    if semester_week_number_source == "lecture_key":
        return lecture_key_week_number or course_week_number or published_week_number
    if semester_week_number_source == "course_week":
        return course_week_number or lecture_key_week_number or published_week_number
    if semester_week_number_source == "published_at":
        return published_week_number or lecture_key_week_number or course_week_number
    return lecture_key_week_number or course_week_number or published_week_number


def _extract_week_lecture_pair(value: Any) -> Optional[Tuple[int, int]]:
    if not isinstance(value, str) or not value.strip():
        return None
    first_line = value.splitlines()[0].strip()
    match = WEEK_LECTURE_LABEL_PATTERN.search(first_line)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _extract_source_folder(value: Any) -> Optional[str]:
    if not isinstance(value, dict):
        return None
    direct = value.get("source_folder")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    nested_meta = value.get("meta")
    if not isinstance(nested_meta, dict):
        return None
    nested = nested_meta.get("source_folder")
    if isinstance(nested, str) and nested.strip():
        return nested.strip()
    return None


def _tokenize_words(value: str) -> List[str]:
    if not value:
        return []
    return [token for token in re.split(r"[^\w]+", value.casefold()) if token]


def _string_signals_importance(value: str) -> bool:
    if not value:
        return False
    lowered = value.strip().casefold()
    if not lowered:
        return False
    if lowered in IMPORTANT_FALSE_STRINGS:
        return False
    if lowered in IMPORTANT_TRUTHY_STRINGS:
        return True
    tokens = _tokenize_words(lowered)
    if not tokens:
        return False
    if any(token in NEGATION_TOKENS for token in tokens):
        return False
    if any(token in LOW_PRIORITY_TOKENS for token in tokens):
        return False
    return any(token in IMPORTANT_MARKER_TOKENS for token in tokens)


def _strip_text_prefix(value: str) -> str:
    if not value:
        return ""
    for prefix in (TEXT_PREFIX, HIGHLIGHTED_TEXT_PREFIX):
        if value.startswith(prefix):
            return value[len(prefix) :].lstrip()
    return value


def _strip_language_tags(
    value: str,
    *,
    preserve_newlines: bool = False,
    strip_brief: bool = True,
) -> str:
    if not value:
        return value
    cleaned = _strip_cfg_tags(value)
    cleaned = LANGUAGE_TAG_PATTERN.sub("", cleaned)
    if strip_brief:
        cleaned = BRIEF_TAG_PATTERN.sub("", cleaned)
    cleaned = READING_PREFIX_PATTERN.sub(r"\1", cleaned)
    cleaned = LECTURE_SEMESTER_PAIR_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"\s*·\s*", " · ", cleaned)
    cleaned = re.sub(r"(?:\s*·\s*){2,}", " · ", cleaned)
    cleaned = re.sub(r"(^|\n)\s*·\s*", r"\1", cleaned)
    cleaned = re.sub(r"\s*·\s*($|\n)", r"\1", cleaned)
    if preserve_newlines:
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r" *\n *", "\n", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    else:
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned.strip(" -–:")


def _normalize_title_for_matching(value: str) -> str:
    if not value:
        return ""
    cleaned = _strip_text_prefix(value.strip())
    cleaned = _strip_cfg_tags(cleaned)
    cleaned = cleaned.replace("’", "'").replace("“", '"').replace("”", '"')
    cleaned = cleaned.replace("–", "-").replace("—", "-")
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\.\s*\([^)]+\)$", "", cleaned)  # remove .(pdf/epub) style suffix
    cleaned = re.sub(
        r"\.(mp3|m4a|wav|mp4|pdf|epub|mobi|aac|flac|txt|docx|mkv)$", "", cleaned, flags=re.IGNORECASE
    )
    cleaned = cleaned.rstrip(" .-_/")
    cleaned = re.sub(r"^[\[\](){}<>-]+", "", cleaned)
    cleaned = cleaned.strip()
    if not cleaned:
        return ""
    return re.sub(r"[^\w]+", "", cleaned.casefold())


def _line_has_doc_marker(line: str) -> bool:
    if not line:
        return False
    if any(symbol in line for symbol in DOC_IMPORTANT_SYMBOLS):
        return True
    lowered = line.casefold()
    if any(prefix in lowered for prefix in DOC_IMPORTANT_PREFIX_MARKERS):
        return True
    if any(marker in lowered for marker in DOC_IMPORTANT_INLINE_MARKERS):
        return True
    return _string_signals_importance(line)


def _candidate_name_signals_importance(candidate: str) -> bool:
    if not candidate:
        return False
    if re.search(r"\bX\b", candidate):
        return True
    stripped = candidate.strip()
    if re.fullmatch(r"\d+", stripped):
        return False
    return _string_signals_importance(candidate)


def _candidate_is_week_x(candidate: str) -> bool:
    if not candidate:
        return False
    stripped = candidate.strip()
    stripped = stripped.lstrip("-• ")
    if WEEK_X_PREFIX_PATTERN.match(stripped):
        return True
    return bool(OVELSESHOLD_MARKER_PATTERN.search(stripped))


def _extract_doc_candidates(line: str) -> List[str]:
    candidates: List[str] = []
    working = line.strip()
    if not working:
        return candidates
    arrow_variants = ("→", "->", "⇒")
    for arrow in arrow_variants:
        if arrow in working:
            segment = working.split(arrow, 1)[1].strip()
            if segment:
                segment = re.split(r"\s+\(source\b", segment, 1, flags=re.IGNORECASE)[0]
                segment = re.split(r"\s+\[source\b", segment, 1, flags=re.IGNORECASE)[0]
                segment = re.split(r"\s+-\s*source\b", segment, 1, flags=re.IGNORECASE)[0]
                segment = segment.strip()
                if segment:
                    candidates.append(segment)
            break
    if "`" in working:
        for match in re.findall(r"`([^`]+)`", working):
            cleaned = match.strip()
            if cleaned:
                candidates.append(cleaned)
    if "[" in working and "]" in working:
        link_match = re.findall(r"\[([^\]]+)\]\([^)]+\)", working)
        for match in link_match:
            cleaned = match.strip()
            if cleaned:
                candidates.append(cleaned)
    # Remove duplicates while preserving order
    seen: Set[str] = set()
    unique_candidates: List[str] = []
    for item in candidates:
        if item not in seen:
            seen.add(item)
            unique_candidates.append(item)
    return unique_candidates


def _slug_matches(candidate_slug: str, reference_slug: str) -> bool:
    if not candidate_slug or not reference_slug:
        return False
    if candidate_slug == reference_slug:
        return True
    min_length = 8
    if len(candidate_slug) >= min_length and candidate_slug in reference_slug:
        return True
    if len(reference_slug) >= min_length and reference_slug in candidate_slug:
        return True
    return False


def _doc_markers_include(slugs: Set[str], value: str) -> bool:
    normalized = _normalize_title_for_matching(value)
    if not normalized:
        return False
    if normalized in slugs:
        return True
    for doc_slug in slugs:
        if _slug_matches(normalized, doc_slug):
            return True
    return False


def collect_doc_marked_titles(doc_paths: Iterable[Path], *, mode: str = "all_markers") -> Set[str]:
    if mode not in {"all_markers", "week_x_only"}:
        mode = "all_markers"
    important_slugs: Set[str] = set()
    for doc_path in doc_paths:
        try:
            content = doc_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            print(f"Warning: importance doc not found: {doc_path}", file=sys.stderr)
            continue
        in_callout = False
        for raw_line in content.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                if not raw_line.lstrip().startswith(">"):
                    in_callout = False
                continue
            is_block_line = stripped.startswith(">")
            bare_line = stripped.lstrip("> ").strip()
            if mode != "week_x_only" and is_block_line and DOC_CALLOUT_PATTERN.search(bare_line):
                in_callout = True
                continue
            if not is_block_line:
                in_callout = False
            line_marked = False
            if mode == "all_markers":
                line_marked = in_callout or _line_has_doc_marker(bare_line)
            candidates = _extract_doc_candidates(bare_line)
            if not candidates:
                continue
            for candidate in candidates:
                if not candidate:
                    continue
                if mode == "week_x_only":
                    if not _candidate_is_week_x(candidate):
                        continue
                    candidate_marked = True
                else:
                    candidate_marked = line_marked or _candidate_name_signals_importance(candidate)
                if not candidate_marked:
                    continue
                slug = _normalize_title_for_matching(candidate)
                if slug:
                    important_slugs.add(slug)
    return important_slugs


def is_marked_important(
    file_entry: Dict[str, Any],
    doc_marked_titles: Optional[Set[str]] = None,
) -> bool:
    if doc_marked_titles and _doc_markers_include(doc_marked_titles, file_entry.get("name", "")):
        return True
    return False


def _replace_text_prefix(value: str, *, require_start: bool) -> Tuple[str, bool]:
    if not value:
        return value, False
    if require_start:
        if not value.startswith(TEXT_PREFIX):
            return value, False
        if len(value) > len(TEXT_PREFIX) and not value[len(TEXT_PREFIX)].isspace():
            return value, False
        return f"{HIGHLIGHTED_TEXT_PREFIX}{value[len(TEXT_PREFIX):]}", True

    index = value.find(TEXT_PREFIX)
    if index == -1:
        return value, False
    if index > 0:
        before_char = value[index - 1]
        if not before_char.isspace() and before_char not in {":", "-", "/", "("}:
            return value, False
    end_index = index + len(TEXT_PREFIX)
    if end_index < len(value):
        after_char = value[end_index]
        if not after_char.isspace():
            return value, False
    updated = f"{value[:index]}{HIGHLIGHTED_TEXT_PREFIX}{value[end_index:]}"
    return updated, True


WEEK_LECTURE_PATTERN = re.compile(r"\bw\s*(\d{1,2})\s*l\s*(\d+)\b", re.IGNORECASE)
SHORT_PREFIX_PATTERN = re.compile(r"^\[\s*(?:short|brief)\s*\]\s*", re.IGNORECASE)
BRIEF_PREFIX_PATTERN = SHORT_PREFIX_PATTERN
WEEK_PREFIX_TOKEN_PATTERN = re.compile(r"^w\s*\d{1,2}(?:\s*l\s*\d+)?\b", re.IGNORECASE)
WEEK_PREFIX_SEPARATOR_PATTERN = re.compile(r"^[\s._\-–:]+")
SLIDE_DESCRIPTOR_PATTERN = re.compile(
    r"^slide\s+(?:lecture|seminar|exercise)\s*:\s*(?P<title>.+)$",
    re.IGNORECASE,
)
SLIDE_LEADING_NUMBER_PATTERN = re.compile(r"^\s*\d+\s*\.\s*")
SLIDE_LEADING_LABEL_PATTERN = re.compile(
    r"^\s*gang\b(?:\s+\d+)?\s*",
    re.IGNORECASE,
)
SLIDE_DISPLAY_LABEL = "Forelæsningsslides"
EPISODE_KINDS = {"reading", "short", "brief", "weekly_overview", "slide"}
WEEKLY_OVERVIEW_LABEL = "Alle kilder (undtagen slides)"
DEFAULT_SLIDE_SUBJECT_SEPARATOR = " - "
WEEKLY_OVERVIEW_SUBJECT_PATTERN = re.compile(
    r"\b(?:alle kilder|all sources)\b(?:\s*\((?:undtagen slides|excluding slides)\))?",
    re.IGNORECASE,
)
TITLE_BLOCKS_ALLOWED = {
    "semester_week_lecture",
    "course_week_lecture",
    "course_week_lecture_long",
    "semester_week",
    "lecture",
    "subject",
    "type_label",
    "subject_or_type",
    "week_range",
    "week_date_range",
}
DESCRIPTION_BLOCKS_ALLOWED = {
    "descriptor_subject",
    "descriptor",
    "subject",
    "topic",
    "lecture",
    "semester_week",
    "text_link",
    "quiz",
    "quiz_url",
    "reading_summary",
    "reading_key_points",
    "weekly_overview_summary",
    "weekly_overview_key_points",
}
DEFAULT_TITLE_BLOCKS = ["semester_week_lecture", "subject_or_type", "week_range"]
DEFAULT_DESCRIPTION_BLOCKS = ["descriptor_subject", "topic", "lecture", "semester_week", "quiz"]
ALTERNATE_EPISODE_URL_SOURCES = {"spotify", "audio_url", "link"}
DEFAULT_ALTERNATE_EPISODE_URL_PRIORITY = ["spotify", "audio_url", "link"]
FEED_SORT_MODES = {
    "published_at_desc",
    "wxlx_kind_priority",
    "wxlx_source_pair_priority",
}
DEFAULT_FEED_SORT_MODE = "published_at_desc"
SEMESTER_WEEK_NUMBER_SOURCES = {"published_at", "lecture_key", "course_week", "auto"}
DEFAULT_SEMESTER_WEEK_NUMBER_SOURCE = "published_at"
TAIL_GRUNDBOG_GUID_PREFIX = "#tail-grundbog-"
GRUNDBOG_PATTERN = re.compile(r"\bgrundbog\b", re.IGNORECASE)
GRUNDBOG_FORORD_PATTERN = re.compile(r"\bforord\b", re.IGNORECASE)
GRUNDBOG_CHAPTER_PATTERN = re.compile(r"\b(?:kapitel|chapter)\s*0*(\d{1,3})\b", re.IGNORECASE)
GRUNDBOG_SORT_CHAPTER_PATTERN = re.compile(
    r"\bgrundbog\s*(?:kapitel\s*)?0*(\d{1,3})\b",
    re.IGNORECASE,
)
GRUNDBOG_SUBJECT_PATTERN = re.compile(r"\bgrundbog\b.*", re.IGNORECASE)
GRUNDBOG_TITLE_PATTERN = re.compile(
    r"^grundbog\s+kapitel\s*0*(\d{1,3})\s*[-–:]\s*(.+)$",
    re.IGNORECASE,
)
TRAILING_WEEK_RANGE_PATTERN = re.compile(
    r"(?:\s*·\s*)?\((?:uge|week)\s+[^)]*\)\s*$",
    re.IGNORECASE,
)


def _normalize_slide_subject(value: str) -> str:
    subject = value.strip()
    subject = SLIDE_LEADING_NUMBER_PATTERN.sub("", subject)
    subject = SLIDE_LEADING_LABEL_PATTERN.sub("", subject)
    subject = re.sub(r"^[\s._\-–:]+", "", subject)
    subject = re.sub(r"\s+", " ", subject).strip()
    return subject


def _extract_slide_subject(value: str) -> Optional[str]:
    match = SLIDE_DESCRIPTOR_PATTERN.match(value.strip())
    if not match:
        return None
    raw_subject = match.group("title").strip()
    normalized = _normalize_slide_subject(raw_subject)
    return normalized or raw_subject


def extract_week_lecture_from_candidates(
    candidates: Iterable[Any],
) -> Tuple[Optional[int], Optional[int]]:
    for candidate in candidates:
        if not isinstance(candidate, str) or not candidate.strip():
            continue
        match = WEEK_LECTURE_PATTERN.search(candidate)
        if match:
            return int(match.group(1)), int(match.group(2))
    return None, None


def extract_week_lecture(
    folder_names: Optional[List[str]],
    file_name: Optional[str],
) -> Tuple[Optional[int], Optional[int]]:
    candidates: List[str] = []
    if folder_names:
        candidates.extend(folder_names)
    if file_name:
        candidates.append(file_name)
    return extract_week_lecture_from_candidates(candidates)


def strip_week_prefix(value: str) -> str:
    if not value:
        return value
    cleaned = value.strip()
    while cleaned:
        token_match = WEEK_PREFIX_TOKEN_PATTERN.match(cleaned)
        if not token_match:
            break
        cleaned = cleaned[token_match.end() :]
        cleaned = WEEK_PREFIX_SEPARATOR_PATTERN.sub("", cleaned)
    return cleaned.strip()


def strip_brief_prefix(value: str) -> str:
    if not value:
        return value
    return SHORT_PREFIX_PATTERN.sub("", value).strip()


def _classify_audio_category(file_entry: Dict[str, Any], source_title: str) -> Optional[str]:
    source_value = source_title if isinstance(source_title, str) else ""
    file_name = file_entry.get("name", "")
    if not isinstance(file_name, str):
        file_name = str(file_name)

    has_tts_cfg = bool(CFG_TTS_TYPE_PATTERN.search(source_value))
    has_audio_cfg = bool(CFG_AUDIO_TYPE_PATTERN.search(source_value))
    has_tts_marker = bool(TTS_TAG_PATTERN.search(source_value))
    has_short_cfg = bool(CFG_AUDIO_SHORT_PATTERN.search(source_value))
    has_short_marker = bool(SHORT_TAG_PATTERN.search(source_value))
    has_deep_dive_cfg = bool(CFG_AUDIO_DEEP_DIVE_PATTERN.search(source_value))
    has_deep_dive_marker = bool(DEEP_DIVE_TAG_PATTERN.search(source_value))

    is_audio = has_audio_cfg or has_tts_cfg
    if not is_audio:
        mime_type = file_entry.get("mimeType")
        if isinstance(mime_type, str) and mime_type.casefold().startswith("audio/"):
            is_audio = True
    if not is_audio and Path(file_name).suffix.casefold() in AUDIO_FILE_EXTENSIONS:
        is_audio = True
    if not is_audio:
        return None

    if has_tts_cfg or has_tts_marker:
        return "lydbog"
    if has_short_cfg or has_short_marker:
        return "kort_podcast"
    if has_deep_dive_cfg or has_deep_dive_marker:
        return "podcast"
    return "podcast"


def _normalize_category_prefix(title_value: str) -> str:
    normalized = title_value.strip() if isinstance(title_value, str) else ""
    while normalized:
        updated = CATEGORY_PREFIX_HEAD_PATTERN.sub("", normalized, count=1).strip()
        if updated == normalized:
            break
        normalized = updated
    return normalized


def _resolve_audio_category_prefix_position(feed_config: Dict[str, Any]) -> str:
    raw_value = feed_config.get(
        "audio_category_prefix_position", DEFAULT_AUDIO_CATEGORY_PREFIX_POSITION
    )
    if not isinstance(raw_value, str) or not raw_value.strip():
        return DEFAULT_AUDIO_CATEGORY_PREFIX_POSITION
    value = raw_value.strip().lower()
    if value not in AUDIO_CATEGORY_PREFIX_POSITIONS:
        allowed = ", ".join(sorted(AUDIO_CATEGORY_PREFIX_POSITIONS))
        raise ValueError(
            "feed.audio_category_prefix_position has unknown value "
            f"'{raw_value}'. Allowed values: {allowed}"
        )
    return value


def _resolve_audio_category_prefixes(feed_config: Dict[str, Any]) -> Dict[str, str]:
    defaults = dict(AUDIO_CATEGORY_PREFIXES)
    raw_value = feed_config.get("audio_category_prefixes")
    if raw_value is None:
        return defaults
    if not isinstance(raw_value, dict):
        raise ValueError(
            "feed.audio_category_prefixes must be an object with keys "
            "'lydbog', 'kort_podcast', and 'podcast'."
        )

    resolved = dict(defaults)
    for key, value in raw_value.items():
        if key not in AUDIO_CATEGORY_PREFIXES:
            allowed = ", ".join(sorted(AUDIO_CATEGORY_PREFIXES))
            raise ValueError(
                f"feed.audio_category_prefixes has unknown key '{key}'. Allowed keys: {allowed}"
            )
        if not isinstance(value, str):
            raise ValueError(f"feed.audio_category_prefixes.{key} must be a string.")
        resolved[key] = value.strip()
    return resolved


def _resolve_weekly_overview_label(feed_config: Dict[str, Any]) -> str:
    raw_value = feed_config.get("weekly_overview_label")
    if raw_value is None:
        return WEEKLY_OVERVIEW_LABEL
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ValueError("feed.weekly_overview_label must be a non-empty string.")
    return raw_value.strip()


def _resolve_slide_display_label(feed_config: Dict[str, Any]) -> str:
    raw_value = feed_config.get("slide_display_label")
    if raw_value is None:
        return SLIDE_DISPLAY_LABEL
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ValueError("feed.slide_display_label must be a non-empty string.")
    return raw_value.strip()


def _resolve_slide_subject_separator(feed_config: Dict[str, Any]) -> str:
    raw_value = feed_config.get("slide_subject_separator")
    if raw_value is None:
        return DEFAULT_SLIDE_SUBJECT_SEPARATOR
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ValueError("feed.slide_subject_separator must be a non-empty string.")
    if "\n" in raw_value or "\r" in raw_value:
        raise ValueError("feed.slide_subject_separator must be a single-line string.")
    return raw_value.strip()


def _resolve_title_subject_aliases(feed_config: Dict[str, Any]) -> Dict[str, str]:
    raw_value = feed_config.get("title_subject_aliases")
    if raw_value is None:
        return {}
    if not isinstance(raw_value, dict):
        raise ValueError("feed.title_subject_aliases must be an object.")
    resolved: Dict[str, str] = {}
    for key, value in raw_value.items():
        if not isinstance(key, str) or not key.strip():
            raise ValueError("feed.title_subject_aliases keys must be non-empty strings.")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("feed.title_subject_aliases values must be non-empty strings.")
        resolved[re.sub(r"\s+", " ", key).strip()] = re.sub(r"\s+", " ", value).strip()
    return resolved


def _resolve_compact_grundbog_subjects(feed_config: Dict[str, Any]) -> bool:
    raw_value = feed_config.get("compact_grundbog_subjects")
    if raw_value is None:
        return False
    if not isinstance(raw_value, bool):
        raise ValueError("feed.compact_grundbog_subjects must be a boolean.")
    return raw_value


def _apply_audio_category_prefix(
    title_value: str,
    title_prefix: str,
    *,
    position: str,
) -> str:
    normalized = _normalize_category_prefix(title_value)
    if not title_prefix:
        return normalized
    if position == "after_first_block" and TITLE_BLOCK_SEPARATOR in normalized:
        first, rest = normalized.split(TITLE_BLOCK_SEPARATOR, 1)
        first = first.strip()
        rest = rest.strip()
        if first and rest:
            return f"{first}{TITLE_BLOCK_SEPARATOR}{title_prefix}{TITLE_BLOCK_SEPARATOR}{rest}"
    return f"{title_prefix} {normalized}".strip()


def extract_topic(meta: Dict[str, Any]) -> Optional[str]:
    topic = meta.get("topic")
    if isinstance(topic, str) and topic.strip():
        return topic.strip()
    summary = meta.get("summary")
    if isinstance(summary, str):
        lowered = summary.lower()
        if lowered.startswith("topic of the week:"):
            return summary.split(":", 1)[1].strip()
        if lowered.startswith("emne for ugen:"):
            return summary.split(":", 1)[1].strip()
        if lowered.startswith("ugens emne:"):
            return summary.split(":", 1)[1].strip()
    return None


def _validate_block_list(
    value: Any,
    *,
    path: str,
    allowed_blocks: Set[str],
) -> List[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{path} must be a non-empty list of block names.")
    blocks: List[str] = []
    for idx, token in enumerate(value):
        if not isinstance(token, str) or not token.strip():
            raise ValueError(f"{path}[{idx}] must be a non-empty string.")
        block = token.strip()
        if block not in allowed_blocks:
            allowed = ", ".join(sorted(allowed_blocks))
            raise ValueError(f"{path}[{idx}] has unknown block '{block}'. Allowed: {allowed}")
        blocks.append(block)
    return blocks


def _validate_alternate_episode_links_config(feed_config: Dict[str, Any]) -> None:
    raw_specs = feed_config.get("alternate_episode_links")
    if raw_specs is None:
        return
    if not isinstance(raw_specs, list):
        raise ValueError("feed.alternate_episode_links must be a list when provided.")
    for idx, raw_spec in enumerate(raw_specs):
        path = f"feed.alternate_episode_links[{idx}]"
        if not isinstance(raw_spec, dict):
            raise ValueError(f"{path} must be an object.")
        label = raw_spec.get("label")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"{path}.label must be a non-empty string.")
        inventory = raw_spec.get("inventory")
        if not isinstance(inventory, str) or not inventory.strip():
            raise ValueError(f"{path}.inventory must be a non-empty string path.")
        spotify_map = raw_spec.get("spotify_map")
        if spotify_map is not None and (not isinstance(spotify_map, str) or not spotify_map.strip()):
            raise ValueError(f"{path}.spotify_map must be a non-empty string path when provided.")
        url_priority = raw_spec.get("url_priority")
        if url_priority is None:
            continue
        if not isinstance(url_priority, list) or not url_priority:
            raise ValueError(f"{path}.url_priority must be a non-empty list when provided.")
        for source_idx, raw_source in enumerate(url_priority):
            source = str(raw_source or "").strip()
            if source not in ALTERNATE_EPISODE_URL_SOURCES:
                allowed = ", ".join(sorted(ALTERNATE_EPISODE_URL_SOURCES))
                raise ValueError(
                    f"{path}.url_priority[{source_idx}] has unknown source '{source}'. "
                    f"Allowed: {allowed}"
                )


def _resolve_pubdate_year_rewrite(feed_config: Dict[str, Any]) -> Optional[Tuple[int, int]]:
    raw_value = feed_config.get("pubdate_year_rewrite")
    if raw_value is None:
        return None
    if not isinstance(raw_value, dict):
        raise ValueError(
            "feed.pubdate_year_rewrite must be an object with integer 'from' and 'to' fields."
        )
    try:
        from_year = int(raw_value["from"])
        to_year = int(raw_value["to"])
    except KeyError as exc:
        raise ValueError(
            "feed.pubdate_year_rewrite must include both 'from' and 'to' fields."
        ) from exc
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "feed.pubdate_year_rewrite 'from' and 'to' must be integers."
        ) from exc
    if from_year < 1 or to_year < 1:
        raise ValueError("feed.pubdate_year_rewrite values must be positive integers.")
    return from_year, to_year


def _rewrite_pubdate_year(pubdate_value: str, rewrite: Optional[Tuple[int, int]]) -> str:
    if not rewrite:
        return pubdate_value
    from_year, to_year = rewrite
    return re.sub(rf"\b{from_year}\b", str(to_year), pubdate_value, count=1)


def _resolve_tail_grundbog_lydbog_config(feed_config: Dict[str, Any]) -> Dict[str, Any]:
    defaults = {
        "enabled": False,
        "include_forord": True,
        "chapter_start": 1,
        "chapter_end": 14,
        "drop_source_lydbog_items": False,
    }
    raw_value = feed_config.get("tail_grundbog_lydbog")
    if raw_value is None:
        return dict(defaults)
    if not isinstance(raw_value, dict):
        raise ValueError(
            "feed.tail_grundbog_lydbog must be an object with "
            "'enabled', 'include_forord', 'chapter_start', 'chapter_end', "
            "and 'drop_source_lydbog_items'."
        )

    resolved = dict(defaults)
    bool_fields = ("enabled", "include_forord", "drop_source_lydbog_items")
    for key in bool_fields:
        if key not in raw_value:
            continue
        value = raw_value.get(key)
        if not isinstance(value, bool):
            raise ValueError(f"feed.tail_grundbog_lydbog.{key} must be a boolean.")
        resolved[key] = value

    int_fields = ("chapter_start", "chapter_end")
    for key in int_fields:
        if key not in raw_value:
            continue
        value = raw_value.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"feed.tail_grundbog_lydbog.{key} must be an integer.")
        resolved[key] = value

    chapter_start = resolved["chapter_start"]
    chapter_end = resolved["chapter_end"]
    if chapter_start < 1 or chapter_end < 1:
        raise ValueError(
            "feed.tail_grundbog_lydbog.chapter_start and chapter_end must be positive integers."
        )
    if chapter_start > chapter_end:
        raise ValueError(
            "feed.tail_grundbog_lydbog.chapter_start must be less than or equal to chapter_end."
        )
    return resolved


def validate_feed_block_config(feed_config: Dict[str, Any]) -> None:
    if not isinstance(feed_config, dict):
        raise ValueError("feed must be a JSON object.")
    _resolve_audio_category_prefix_position(feed_config)
    _resolve_audio_category_prefixes(feed_config)
    _resolve_weekly_overview_label(feed_config)
    _resolve_slide_display_label(feed_config)
    _resolve_slide_subject_separator(feed_config)
    _resolve_title_subject_aliases(feed_config)
    _resolve_compact_grundbog_subjects(feed_config)
    _resolve_semester_week_number_source(feed_config)
    _resolve_pubdate_year_rewrite(feed_config)
    _resolve_tail_grundbog_lydbog_config(feed_config)
    if "reading_description_mode" in feed_config:
        raise ValueError(
            "feed.reading_description_mode is deprecated. "
            "Remove it and use feed.description_blocks or feed.description_blocks_by_kind.reading."
        )
    raw_sort_mode = feed_config.get("sort_mode", DEFAULT_FEED_SORT_MODE)
    if not isinstance(raw_sort_mode, str) or not raw_sort_mode.strip():
        raise ValueError("feed.sort_mode must be a non-empty string.")
    sort_mode = raw_sort_mode.strip().lower()
    if sort_mode not in FEED_SORT_MODES:
        allowed_modes = ", ".join(sorted(FEED_SORT_MODES))
        raise ValueError(
            f"feed.sort_mode has unknown mode '{raw_sort_mode}'. Allowed modes: {allowed_modes}"
        )

    if "title_blocks" in feed_config:
        _validate_block_list(
            feed_config.get("title_blocks"),
            path="feed.title_blocks",
            allowed_blocks=TITLE_BLOCKS_ALLOWED,
        )
    if "description_blocks" in feed_config:
        _validate_block_list(
            feed_config.get("description_blocks"),
            path="feed.description_blocks",
            allowed_blocks=DESCRIPTION_BLOCKS_ALLOWED,
        )
    if "description_prepend_semester_week_lecture" in feed_config and not isinstance(
        feed_config.get("description_prepend_semester_week_lecture"),
        bool,
    ):
        raise ValueError("feed.description_prepend_semester_week_lecture must be a boolean.")
    if "enforce_week_label_consistency" in feed_config and not isinstance(
        feed_config.get("enforce_week_label_consistency"),
        bool,
    ):
        raise ValueError("feed.enforce_week_label_consistency must be a boolean.")
    if "description_blank_line_marker" in feed_config:
        raw_blank_line_marker = feed_config.get("description_blank_line_marker")
        if not isinstance(raw_blank_line_marker, str) or not raw_blank_line_marker.strip():
            raise ValueError("feed.description_blank_line_marker must be a non-empty string.")
        if "\n" in raw_blank_line_marker or "\r" in raw_blank_line_marker:
            raise ValueError("feed.description_blank_line_marker must be a single-line string.")
    if "description_footer" in feed_config:
        raw_description_footer = feed_config.get("description_footer")
        if not isinstance(raw_description_footer, str) or not raw_description_footer.strip():
            raise ValueError("feed.description_footer must be a non-empty string.")
    _validate_alternate_episode_links_config(feed_config)

    mapping_specs = (
        ("title_blocks_by_kind", TITLE_BLOCKS_ALLOWED),
        ("description_blocks_by_kind", DESCRIPTION_BLOCKS_ALLOWED),
    )
    for key, allowed_blocks in mapping_specs:
        raw_mapping = feed_config.get(key)
        if raw_mapping is None:
            continue
        if not isinstance(raw_mapping, dict):
            raise ValueError(f"feed.{key} must be an object keyed by episode kind.")
        if not raw_mapping:
            raise ValueError(f"feed.{key} must not be empty when provided.")
        for kind, blocks_value in raw_mapping.items():
            if kind not in EPISODE_KINDS:
                allowed_kinds = ", ".join(sorted(EPISODE_KINDS))
                raise ValueError(
                    f"feed.{key} has unknown kind '{kind}'. Allowed kinds: {allowed_kinds}"
                )
            _validate_block_list(
                blocks_value,
                path=f"feed.{key}.{kind}",
                allowed_blocks=allowed_blocks,
            )


def _resolve_blocks_for_kind(
    feed_config: Dict[str, Any],
    *,
    global_key: str,
    by_kind_key: str,
    kind: str,
    defaults: Sequence[str],
    allowed_blocks: Set[str],
) -> List[str]:
    if kind not in EPISODE_KINDS:
        allowed_kinds = ", ".join(sorted(EPISODE_KINDS))
        raise ValueError(f"Unknown episode kind '{kind}'. Allowed kinds: {allowed_kinds}")

    by_kind = feed_config.get(by_kind_key)
    lookup_kind = kind
    if isinstance(by_kind, dict) and lookup_kind not in by_kind and kind == "short":
        lookup_kind = "brief"
    if isinstance(by_kind, dict) and lookup_kind in by_kind:
        return _validate_block_list(
            by_kind.get(lookup_kind),
            path=f"feed.{by_kind_key}.{lookup_kind}",
            allowed_blocks=allowed_blocks,
        )

    global_blocks = feed_config.get(global_key)
    if global_blocks is not None:
        return _validate_block_list(
            global_blocks,
            path=f"feed.{global_key}",
            allowed_blocks=allowed_blocks,
        )
    return list(defaults)


def _render_blocks(
    blocks: Sequence[str],
    block_values: Dict[str, Optional[str]],
    *,
    separator: str,
) -> str:
    rendered = ""
    for block in blocks:
        value = block_values.get(block)
        if not value:
            continue
        if value.startswith("\n"):
            if rendered:
                rendered = f"{rendered}{value}"
            else:
                rendered = value.lstrip("\n")
            continue
        if not rendered:
            rendered = value
            continue
        joiner = separator
        if separator == " · " and ("\n" in rendered or "\n" in value):
            joiner = "\n\n"
        rendered = f"{rendered}{joiner}{value}"
    return rendered


def _resolve_repo_relative_path(config: Dict[str, Any], raw_path: str) -> Path:
    path = Path(str(raw_path or "").strip()).expanduser()
    if path.is_absolute():
        return path
    if str(raw_path).startswith("shows/"):
        return REPO_ROOT / path
    config_path = str(config.get("__config_path__") or "").strip()
    if config_path:
        return Path(config_path).resolve().parent / path
    return REPO_ROOT / path


def _cross_language_episode_id_from_source_name(source_name: str) -> Optional[str]:
    value = str(source_name or "").strip()
    if not value:
        return None
    filename = Path(value).name
    cleaned = _strip_cfg_tag_from_filename(filename)
    cleaned = CROSS_LANGUAGE_TAG_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return None
    return logical_episode_id(cleaned)


def _cross_language_episode_id_for_inventory_episode(episode: Dict[str, Any]) -> Optional[str]:
    candidates = [
        episode.get("source_name"),
        episode.get("source_path"),
        episode.get("episode_key"),
        episode.get("guid"),
    ]
    for candidate in candidates:
        logical_id = _cross_language_episode_id_from_source_name(str(candidate or ""))
        if logical_id:
            return logical_id
    return None


def _cross_language_episode_fallback_ids(logical_id: Optional[str]) -> List[str]:
    if not logical_id:
        return []
    if logical_id.startswith("short__"):
        return [f"single_reading__{logical_id.removeprefix('short__')}"]
    if logical_id.startswith("single_reading__"):
        return [f"short__{logical_id.removeprefix('single_reading__')}"]
    return []


def _load_spotify_map(path: Optional[Path]) -> Dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        payload = load_json(path)
    except Exception as exc:  # noqa: BLE001 - feed generation should degrade for stale sidecar maps.
        print(f"Warning: could not load alternate Spotify map {path}: {exc}", file=sys.stderr)
        return {}
    return payload if isinstance(payload, dict) else {}


def _spotify_url_for_inventory_episode(episode: Dict[str, Any], spotify_map: Dict[str, Any]) -> Optional[str]:
    by_episode_key = spotify_map.get("by_episode_key")
    if isinstance(by_episode_key, dict):
        for key_field in ("episode_key", "guid"):
            episode_key = str(episode.get(key_field) or "").strip()
            if not episode_key:
                continue
            url = by_episode_key.get(episode_key)
            if isinstance(url, str) and url.strip():
                return url.strip()
    by_rss_title = spotify_map.get("by_rss_title")
    title = str(episode.get("title") or "").strip()
    if title and isinstance(by_rss_title, dict):
        url = by_rss_title.get(title)
        if isinstance(url, str) and url.strip():
            return url.strip()
    return None


def _alternate_episode_url(
    episode: Dict[str, Any],
    *,
    spotify_map: Dict[str, Any],
    url_priority: Sequence[str],
) -> Optional[str]:
    for source in url_priority:
        if source == "spotify":
            url = _spotify_url_for_inventory_episode(episode, spotify_map)
        elif source == "audio_url":
            url = str(episode.get("audio_url") or "").strip()
        elif source == "link":
            url = str(episode.get("link") or "").strip()
        else:
            url = ""
        if url:
            return url
    return None


def load_alternate_episode_link_indexes(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    feed_config = config.get("feed") if isinstance(config.get("feed"), dict) else {}
    raw_specs = feed_config.get("alternate_episode_links")
    if not isinstance(raw_specs, list):
        return []

    indexes: List[Dict[str, Any]] = []
    for raw_spec in raw_specs:
        if not isinstance(raw_spec, dict):
            continue
        label = str(raw_spec.get("label") or "").strip()
        inventory_value = str(raw_spec.get("inventory") or "").strip()
        if not label or not inventory_value:
            continue
        inventory_path = _resolve_repo_relative_path(config, inventory_value)
        if not inventory_path.exists():
            print(f"Warning: alternate episode inventory not found: {inventory_path}", file=sys.stderr)
            continue
        try:
            inventory_payload = load_json(inventory_path)
        except Exception as exc:  # noqa: BLE001 - an alternate link index should not break the feed.
            print(f"Warning: could not load alternate episode inventory {inventory_path}: {exc}", file=sys.stderr)
            continue
        raw_episodes = inventory_payload.get("episodes") if isinstance(inventory_payload, dict) else None
        if not isinstance(raw_episodes, list):
            print(f"Warning: alternate episode inventory has no episodes list: {inventory_path}", file=sys.stderr)
            continue

        spotify_map_value = str(raw_spec.get("spotify_map") or "").strip()
        spotify_map_path = _resolve_repo_relative_path(config, spotify_map_value) if spotify_map_value else None
        spotify_map = _load_spotify_map(spotify_map_path)
        url_priority = [
            str(source).strip()
            for source in raw_spec.get("url_priority", DEFAULT_ALTERNATE_EPISODE_URL_PRIORITY)
            if str(source).strip() in ALTERNATE_EPISODE_URL_SOURCES
        ] or list(DEFAULT_ALTERNATE_EPISODE_URL_PRIORITY)

        index: Dict[str, Dict[str, str]] = {}
        for raw_episode in raw_episodes:
            if not isinstance(raw_episode, dict):
                continue
            logical_id = _cross_language_episode_id_for_inventory_episode(raw_episode)
            if not logical_id or logical_id in index:
                continue
            url = _alternate_episode_url(
                raw_episode,
                spotify_map=spotify_map,
                url_priority=url_priority,
            )
            if not url:
                continue
            index[logical_id] = {
                "url": url,
                "title": str(raw_episode.get("title") or "").strip(),
            }
        indexes.append(
            {
                "label": label,
                "index": index,
                "inventory": str(inventory_path),
                "spotify_map": str(spotify_map_path) if spotify_map_path else "",
            }
        )
    return indexes


def _render_alternate_episode_links(
    *,
    source_name: str,
    alternate_episode_link_indexes: Optional[Sequence[Dict[str, Any]]],
) -> Optional[str]:
    logical_id = _cross_language_episode_id_from_source_name(source_name)
    if not logical_id or not alternate_episode_link_indexes:
        return None
    lines: List[str] = []
    seen_urls: Set[str] = set()
    for spec in alternate_episode_link_indexes:
        if not isinstance(spec, dict):
            continue
        label = str(spec.get("label") or "").strip()
        index = spec.get("index")
        if not label or not isinstance(index, dict):
            continue
        match: Optional[Dict[str, Any]] = None
        for candidate_id in [logical_id, *_cross_language_episode_fallback_ids(logical_id)]:
            candidate = index.get(candidate_id)
            if isinstance(candidate, dict):
                match = candidate
                break
        if match is None:
            continue
        url = str(match.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        lines.append(f"{label}: {url}")
    if not lines:
        return None
    return "\n".join(lines)


def _apply_description_blank_line_marker(text: str, marker: str) -> str:
    if not marker:
        return text
    resolved_marker = marker.strip()
    if not resolved_marker:
        return text
    return re.sub(r"\n[ \t]*\n+", f"\n{resolved_marker}\n", text)


def _render_description_text_link(
    *,
    feed_config: Dict[str, Any],
    week_number: Optional[int],
    lecture_number: Optional[int],
) -> Optional[str]:
    if not week_number or not lecture_number:
        return None
    raw_cfg = feed_config.get("lecture_preview_link")
    if not isinstance(raw_cfg, dict):
        return None
    base_url = str(raw_cfg.get("base_url") or "").strip()
    if not base_url:
        return None
    label = str(raw_cfg.get("label") or "").strip() or "Link til teksten"
    include_preview_param = bool(raw_cfg.get("preview", True))
    lecture_key = f"W{int(week_number):02d}L{int(lecture_number)}"
    query_params = {"lecture": lecture_key}
    if include_preview_param:
        query_params["preview"] = "true"
    query_text = urlencode(query_params)
    if "?" in base_url:
        joiner = "" if base_url.endswith("?") or base_url.endswith("&") else "&"
    else:
        joiner = "?"
    return f"{label}: {base_url}{joiner}{query_text}"


def _resolve_feed_sort_mode(feed_config: Dict[str, Any]) -> str:
    raw_sort_mode = feed_config.get("sort_mode", DEFAULT_FEED_SORT_MODE)
    if not isinstance(raw_sort_mode, str):
        return DEFAULT_FEED_SORT_MODE
    normalized = raw_sort_mode.strip().lower()
    if not normalized:
        return DEFAULT_FEED_SORT_MODE
    if normalized in FEED_SORT_MODES:
        return normalized
    return DEFAULT_FEED_SORT_MODE


def _published_sort_value(item: Dict[str, Any]) -> float:
    published = item.get("published_at")
    if not isinstance(published, dt.datetime):
        return float("-inf")
    if published.tzinfo is None:
        published = published.replace(tzinfo=dt.timezone.utc)
    return published.timestamp()


def _wxlx_kind_priority(item: Dict[str, Any]) -> int:
    kind = str(item.get("episode_kind") or "").strip()
    is_tts = bool(item.get("is_tts"))
    if kind in {"short", "brief"}:
        return 0
    if kind == "weekly_overview":
        return 1
    if kind == "reading" and is_tts:
        return 2
    return 3


def _wxlx_oldest_sort_priority(item: Dict[str, Any]) -> int:
    kind = str(item.get("episode_kind") or "").strip()
    is_tts = bool(item.get("is_tts"))
    if kind == "weekly_overview":
        return 0
    if kind in {"short", "brief"}:
        return 1
    if kind == "reading" and is_tts:
        return 2
    return 3


def _normalize_sort_subject_key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def _wxlx_source_pair_category_rank(item: Dict[str, Any]) -> int:
    source_kind = str(item.get("sort_source_kind") or "").strip().lower()
    if source_kind == "weekly_overview":
        return 0
    if bool(item.get("is_tts")):
        return 3
    if source_kind == "reading":
        return 1
    if source_kind == "slide":
        return 2
    return 4


def _wxlx_source_pair_variant_rank(item: Dict[str, Any]) -> int:
    episode_kind = str(item.get("episode_kind") or "").strip().lower()
    podcast_kind = str(item.get("podcast_kind") or "").strip().lower()
    if episode_kind in {"short", "brief"} or podcast_kind in {"kort_podcast", "short_podcast"}:
        return 0
    if bool(item.get("is_tts")) or podcast_kind == "lydbog":
        return 2
    return 1


def _wxlx_source_pair_subject_sort_key(item: Dict[str, Any]) -> Tuple[int, int, str]:
    subject_key = _normalize_sort_subject_key(item.get("sort_subject_key") or item.get("title"))
    if not subject_key:
        return (2, sys.maxsize, "")
    match = GRUNDBOG_SORT_CHAPTER_PATTERN.search(subject_key)
    if match:
        try:
            chapter_number = int(match.group(1))
        except ValueError:  # pragma: no cover - defensive
            chapter_number = sys.maxsize
        return (1, chapter_number, subject_key)
    return (0, sys.maxsize, subject_key)


def _order_wxlx_block_pairs(
    values: List[Tuple[int, Dict[str, Any]]],
    *,
    sort_mode: str,
) -> List[Tuple[int, Dict[str, Any]]]:
    if sort_mode != "wxlx_source_pair_priority":
        return sorted(
            values,
            key=lambda pair: (
                _wxlx_kind_priority(pair[1]),
                -_published_sort_value(pair[1]),
                pair[0],
            ),
        )

    grouped_pairs: Dict[Tuple[int, str], List[Tuple[int, Dict[str, Any]]]] = {}
    for index, item in values:
        group_key = (
            _wxlx_source_pair_category_rank(item),
            _normalize_sort_subject_key(item.get("sort_subject_key") or item.get("title")),
        )
        grouped_pairs.setdefault(group_key, []).append((index, item))

    ordered_groups: List[
        Tuple[int, Tuple[int, int, str], float, int, Tuple[int, str], List[Tuple[int, Dict[str, Any]]]]
    ] = []
    for group_key, grouped_values in grouped_pairs.items():
        anchor = max(_published_sort_value(item) for _, item in grouped_values)
        subject_sort_key = min(_wxlx_source_pair_subject_sort_key(item) for _, item in grouped_values)
        first_seen_index = min(index for index, _ in grouped_values)
        ordered_groups.append((group_key[0], subject_sort_key, -anchor, first_seen_index, group_key, grouped_values))
    ordered_groups.sort()

    ordered_values: List[Tuple[int, Dict[str, Any]]] = []
    for _, _, _, _, _, grouped_values in ordered_groups:
        grouped_values.sort(
            key=lambda pair: (
                _wxlx_source_pair_variant_rank(pair[1]),
                -_published_sort_value(pair[1]),
                pair[0],
            )
        )
        ordered_values.extend(grouped_values)
    return ordered_values


def _resequence_wxlx_block_pubdates_for_oldest_clients(
    values: List[Tuple[int, Dict[str, Any]]],
    feed_config: Dict[str, Any],
    *,
    sort_mode: str,
) -> Optional[List[Tuple[int, Dict[str, Any]]]]:
    if len(values) <= 1:
        return None

    published_values: List[dt.datetime] = []
    for _, item in values:
        published = item.get("published_at")
        if isinstance(published, dt.datetime):
            if published.tzinfo is None:
                published = published.replace(tzinfo=dt.timezone.utc)
            published_values.append(published)
            continue
        return None

    published_values.sort()
    rewrite_config = _resolve_pubdate_year_rewrite(feed_config)
    if sort_mode == "wxlx_source_pair_priority":
        oldest_order = _order_wxlx_block_pairs(values, sort_mode=sort_mode)
    else:
        oldest_order = sorted(
            values,
            key=lambda pair: (
                _wxlx_oldest_sort_priority(pair[1]),
                _published_sort_value(pair[1]),
                pair[0],
            ),
        )
    for position, (_, item) in enumerate(oldest_order):
        reassigned = published_values[position]
        item["published_at"] = reassigned
        item["pubDate"] = _rewrite_pubdate_year(
            format_rfc2822(reassigned),
            rewrite_config,
        )
    return oldest_order if sort_mode == "wxlx_source_pair_priority" else None


def _extract_grundbog_subject_from_text(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value.strip():
        return None
    cleaned = _strip_language_tags(value)
    if not cleaned:
        return None
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    match = GRUNDBOG_SUBJECT_PATTERN.search(cleaned)
    if not match:
        return None
    subject = match.group(0).strip()
    subject = TRAILING_WEEK_RANGE_PATTERN.sub("", subject).strip()
    subject = subject.strip(" -–:·")
    if not subject:
        return None
    subject = re.sub(r"\s+", " ", subject).strip()
    return re.sub(r"(?i)^grundbog\b", "Grundbog", subject)


def _compact_grundbog_subject(value: str) -> str:
    subject = re.sub(r"\s+", " ", str(value or "")).strip()
    match = GRUNDBOG_TITLE_PATTERN.match(subject)
    if not match:
        return subject
    chapter_number = int(match.group(1))
    chapter_subject = re.sub(r"\s+", " ", match.group(2)).strip(" -–:")
    if not chapter_subject:
        return f"Grundbog {chapter_number}"
    return f"Grundbog {chapter_number}: {chapter_subject}"


def _apply_title_subject_alias(
    value: str,
    aliases: Dict[str, str],
    *,
    compact_grundbog_subjects: bool = False,
) -> str:
    normalized = re.sub(r"\s+", " ", str(value or "")).strip()
    if not normalized:
        return normalized
    compacted = (
        _compact_grundbog_subject(normalized) if compact_grundbog_subjects else normalized
    )
    return aliases.get(normalized, aliases.get(compacted, compacted))


def _extract_tail_grundbog_lydbog_key(item: Dict[str, Any]) -> Optional[str]:
    if not bool(item.get("is_tts")):
        return None
    for key in ("title", "description"):
        subject = _extract_grundbog_subject_from_text(item.get(key))
        if not subject:
            continue
        if not GRUNDBOG_PATTERN.search(subject):
            continue
        if GRUNDBOG_FORORD_PATTERN.search(subject):
            return "forord"
        chapter_match = GRUNDBOG_CHAPTER_PATTERN.search(subject)
        if not chapter_match:
            continue
        try:
            chapter_number = int(chapter_match.group(1))
        except ValueError:  # pragma: no cover - defensive
            continue
        if chapter_number > 0:
            return f"chapter:{chapter_number}"
    return None


def _tail_grundbog_guid(base_guid: Any, key: str) -> str:
    key_suffix = key.replace(":", "-")
    guid = str(base_guid or "").strip()
    if TAIL_GRUNDBOG_GUID_PREFIX in guid:
        guid = guid.split(TAIL_GRUNDBOG_GUID_PREFIX, 1)[0]
    if not guid:
        guid = f"tail-grundbog-{key_suffix}"
    return f"{guid}{TAIL_GRUNDBOG_GUID_PREFIX}{key_suffix}"


def _tail_grundbog_subject(item: Dict[str, Any], key: str) -> str:
    for field in ("title", "description"):
        subject = _extract_grundbog_subject_from_text(item.get(field))
        if subject:
            return subject
    if key == "forord":
        return "Grundbog forord og resumé"
    chapter_match = re.fullmatch(r"chapter:(\d+)", key)
    if chapter_match:
        return f"Grundbog kapitel {int(chapter_match.group(1)):02d}"
    return "Grundbog"


def _build_tail_grundbog_episode(
    source_item: Dict[str, Any],
    *,
    key: str,
    tail_index: int,
) -> Dict[str, Any]:
    subject = _tail_grundbog_subject(source_item, key)
    generated = dict(source_item)
    generated["guid"] = _tail_grundbog_guid(source_item.get("guid"), key)
    generated["title"] = f"[Lydbog] · {subject}"
    generated["description"] = subject
    generated["sort_tail"] = True
    generated["sort_tail_index"] = tail_index
    generated["sort_week"] = None
    generated["sort_lecture"] = None
    generated["lecture_key"] = None
    generated["is_tts"] = True
    generated["podcast_kind"] = "lydbog"
    return generated


def _synthesize_tail_grundbog_lydbog_block(
    episodes: Iterable[Dict[str, Any]],
    feed_config: Dict[str, Any],
) -> List[Dict[str, Any]]:
    items = list(episodes)
    tail_cfg = _resolve_tail_grundbog_lydbog_config(feed_config)
    if not tail_cfg.get("enabled"):
        return items
    drop_source_lydbog_items = bool(tail_cfg.get("drop_source_lydbog_items"))

    required_keys: List[str] = []
    if tail_cfg.get("include_forord"):
        required_keys.append("forord")
    required_keys.extend(
        f"chapter:{chapter_number}"
        for chapter_number in range(
            int(tail_cfg["chapter_start"]),
            int(tail_cfg["chapter_end"]) + 1,
        )
    )

    candidates_by_key: Dict[str, Dict[str, List[Tuple[int, Dict[str, Any]]]]] = {}
    passthrough_candidates: List[Tuple[Dict[str, Any], Optional[str]]] = []

    for index, item in enumerate(items):
        key = _extract_tail_grundbog_lydbog_key(item)
        if key:
            bucket = candidates_by_key.setdefault(key, {"tail": [], "other": []})
            source_bucket = "tail" if bool(item.get("sort_tail")) else "other"
            bucket[source_bucket].append((index, item))
        if bool(item.get("sort_tail")) and key:
            # Replace all existing Grundbog tail items with a canonical rebuilt block.
            continue
        passthrough_candidates.append((item, key))

    tail_block: List[Dict[str, Any]] = []
    missing_keys: List[str] = []
    resolved_keys: Set[str] = set()
    for tail_index, key in enumerate(required_keys):
        buckets = candidates_by_key.get(key) or {"tail": [], "other": []}
        tail_candidates = buckets.get("tail") or []
        other_candidates = buckets.get("other") or []
        preferred_candidates = tail_candidates if tail_candidates else other_candidates

        if not preferred_candidates:
            missing_keys.append(key)
            continue

        if len(tail_candidates) + len(other_candidates) > 1:
            choice_label = "existing tail source" if tail_candidates else "newest non-tail source"
            print(
                f"Warning: multiple Grundbog lydbog sources for '{key}'; using {choice_label}.",
                file=sys.stderr,
            )

        _, source_item = max(
            preferred_candidates,
            key=lambda pair: (_published_sort_value(pair[1]), -pair[0]),
        )
        tail_block.append(_build_tail_grundbog_episode(source_item, key=key, tail_index=tail_index))
        resolved_keys.add(key)

    if missing_keys:
        print(
            "Warning: missing Grundbog lydbog tail source(s): " + ", ".join(missing_keys),
            file=sys.stderr,
        )

    passthrough_items: List[Dict[str, Any]] = []
    for item, key in passthrough_candidates:
        if (
            drop_source_lydbog_items
            and key in resolved_keys
            and bool(item.get("is_tts"))
        ):
            continue
        passthrough_items.append(item)

    return passthrough_items + tail_block


def _tail_sort_index_value(item: Dict[str, Any]) -> int:
    sort_tail_index = item.get("sort_tail_index")
    if isinstance(sort_tail_index, bool) or not isinstance(sort_tail_index, int):
        return sys.maxsize
    return sort_tail_index


def _sort_feed_episodes(
    episodes: Iterable[Dict[str, Any]],
    feed_config: Dict[str, Any],
) -> List[Dict[str, Any]]:
    items = list(episodes)
    sort_mode = _resolve_feed_sort_mode(feed_config)
    if sort_mode == DEFAULT_FEED_SORT_MODE:
        return sorted(items, key=lambda item: item["published_at"], reverse=True)

    grouped: Dict[Tuple[Any, ...], List[Tuple[int, Dict[str, Any]]]] = {}
    for index, item in enumerate(items):
        if bool(item.get("sort_tail")):
            group_key = ("tail",)
            grouped.setdefault(group_key, []).append((index, item))
            continue
        sort_week = item.get("sort_week")
        sort_lecture = item.get("sort_lecture")
        if (
            isinstance(sort_week, int)
            and sort_week > 0
            and isinstance(sort_lecture, int)
            and sort_lecture > 0
        ):
            group_key: Tuple[Any, ...] = ("block", sort_week, sort_lecture)
        else:
            group_key = ("single", index)
        grouped.setdefault(group_key, []).append((index, item))

    grouped_entries: List[
        Tuple[int, float, int, Tuple[Any, ...], List[Tuple[int, Dict[str, Any]]]]
    ] = []
    for group_key, values in grouped.items():
        anchor = max(_published_sort_value(item) for _, item in values)
        first_seen_index = min(index for index, _ in values)
        group_rank = 1 if group_key[0] == "tail" else 0
        grouped_entries.append((group_rank, anchor, first_seen_index, group_key, values))
    grouped_entries.sort(key=lambda entry: (entry[0], -entry[1], entry[2]))

    ordered: List[Dict[str, Any]] = []
    for _, _, _, group_key, values in grouped_entries:
        if group_key[0] == "block":
            resequenced_order = _resequence_wxlx_block_pubdates_for_oldest_clients(
                values,
                feed_config,
                sort_mode=sort_mode,
            )
            if resequenced_order is not None:
                values[:] = resequenced_order
            else:
                values[:] = _order_wxlx_block_pairs(values, sort_mode=sort_mode)
        elif group_key[0] == "tail":
            values.sort(
                key=lambda pair: (
                    _tail_sort_index_value(pair[1]),
                    -_published_sort_value(pair[1]),
                    pair[0],
                )
            )
        else:
            values.sort(key=lambda pair: (-_published_sort_value(pair[1]), pair[0]))
        ordered.extend(item for _, item in values)
    return ordered


def load_reading_summaries(path: Path) -> Dict[str, Any]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError("reading_summaries file must be a JSON object.")

    raw_by_name = payload.get("by_name")
    if raw_by_name is None:
        return {"by_name": {}}
    if not isinstance(raw_by_name, dict):
        raise ValueError("reading_summaries.by_name must be an object.")

    normalized: Dict[str, Dict[str, Any]] = {}
    for raw_name, raw_entry in raw_by_name.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            print("Warning: skipping invalid reading_summaries.by_name key.", file=sys.stderr)
            continue
        if not isinstance(raw_entry, dict):
            print(
                f"Warning: reading_summaries entry for '{raw_name}' must be an object; skipping.",
                file=sys.stderr,
            )
            continue

        summary_lines: List[str] = []
        raw_summary_lines = raw_entry.get("summary_lines")
        if isinstance(raw_summary_lines, list):
            for value in raw_summary_lines:
                if not isinstance(value, str):
                    continue
                cleaned = value.strip()
                if cleaned:
                    summary_lines.append(cleaned)

        key_points: List[str] = []
        raw_key_points = raw_entry.get("key_points")
        if isinstance(raw_key_points, list):
            for value in raw_key_points:
                if not isinstance(value, str):
                    continue
                cleaned = value.strip()
                if cleaned:
                    key_points.append(cleaned)

        normalized_entry: Dict[str, Any] = {}
        if summary_lines:
            normalized_entry["summary_lines"] = summary_lines
        if key_points:
            normalized_entry["key_points"] = key_points
        meta = raw_entry.get("meta")
        if isinstance(meta, dict):
            normalized_entry["meta"] = meta

        if normalized_entry:
            normalized[raw_name.strip()] = normalized_entry

    return {"by_name": normalized}


def load_weekly_overview_summaries(path: Path) -> Dict[str, Any]:
    payload = load_json(path)
    if not isinstance(payload, dict):
        raise ValueError("weekly_overview_summaries file must be a JSON object.")

    raw_by_name = payload.get("by_name")
    if raw_by_name is None:
        return {"by_name": {}}
    if not isinstance(raw_by_name, dict):
        raise ValueError("weekly_overview_summaries.by_name must be an object.")

    normalized: Dict[str, Dict[str, Any]] = {}
    for raw_name, raw_entry in raw_by_name.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            print("Warning: skipping invalid weekly_overview_summaries.by_name key.", file=sys.stderr)
            continue
        if not isinstance(raw_entry, dict):
            print(
                f"Warning: weekly_overview_summaries entry for '{raw_name}' must be an object; skipping.",
                file=sys.stderr,
            )
            continue

        summary_lines: List[str] = []
        raw_summary_lines = raw_entry.get("summary_lines")
        if isinstance(raw_summary_lines, list):
            for value in raw_summary_lines:
                if not isinstance(value, str):
                    continue
                cleaned = value.strip()
                if cleaned:
                    summary_lines.append(cleaned)

        key_points: List[str] = []
        raw_key_points = raw_entry.get("key_points")
        if isinstance(raw_key_points, list):
            for value in raw_key_points:
                if not isinstance(value, str):
                    continue
                cleaned = value.strip()
                if cleaned:
                    key_points.append(cleaned)

        normalized_entry: Dict[str, Any] = {}
        if summary_lines:
            normalized_entry["summary_lines"] = summary_lines
        if key_points:
            normalized_entry["key_points"] = key_points
        meta = raw_entry.get("meta")
        if isinstance(meta, dict):
            normalized_entry["meta"] = meta

        if normalized_entry:
            normalized[raw_name.strip()] = normalized_entry

    return {"by_name": normalized}


def build_episode_entry(
    file_entry: Dict[str, Any],
    feed_config: Dict[str, Any],
    overrides: Dict[str, Any],
    public_link_template: str,
    auto_meta: Optional[Dict[str, Any]] = None,
    folder_names: Optional[List[str]] = None,
    doc_marked_titles: Optional[Set[str]] = None,
    episode_image_url: Optional[str] = None,
    quiz_cfg: Optional[Dict[str, Any]] = None,
    quiz_links: Optional[Dict[str, Any]] = None,
    reading_summaries_cfg: Optional[Dict[str, Any]] = None,
    reading_summaries: Optional[Dict[str, Any]] = None,
    weekly_overview_summaries_cfg: Optional[Dict[str, Any]] = None,
    weekly_overview_summaries: Optional[Dict[str, Any]] = None,
    active_b_variant_file_ids: Optional[Set[str]] = None,
    regeneration_variant_slot: Optional[str] = None,
    regen_marker: Optional[str] = None,
    regen_marker_position: str = "suffix",
    alternate_episode_link_indexes: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    if auto_meta:
        meta.update(auto_meta)
    manual_meta = item_metadata(overrides, file_entry) or {}
    meta.update(manual_meta)
    if episode_image_url and not meta.get("image"):
        meta["image"] = episode_image_url
    suppress_week_prefix = bool(meta.get("suppress_week_prefix"))
    narrator = meta.get("narrator")
    if not narrator:
        narrator = AutoSpec._extract_voice(file_entry.get("name"))
        if narrator:
            meta.setdefault("narrator", narrator)
    source_title = file_entry["name"].rsplit(".", 1)[0]
    audio_category = _classify_audio_category(file_entry, source_title)
    base_title = source_title
    if narrator:
        suffix = f" - {narrator}"
        if base_title.lower().endswith(suffix.lower()):
            base_title = base_title[: -len(suffix)].rstrip()
    quiz_links_map = quiz_links.get("by_name") if isinstance(quiz_links, dict) else None
    matched_quiz_entry: Any = None
    matched_quiz_key: Optional[str] = None
    if quiz_cfg and isinstance(quiz_links_map, dict) and file_entry.get("name"):
        matched_quiz_key = _lookup_key_with_cfg_fallback(quiz_links_map, file_entry["name"])
        if matched_quiz_key is not None:
            matched_quiz_entry = quiz_links_map.get(matched_quiz_key)
    important = is_marked_important(
        file_entry,
        doc_marked_titles,
    )
    prefix_replaced = False
    if important:
        base_title, prefix_replaced = _replace_text_prefix(base_title, require_start=True)
    pubdate_source = (
        file_entry.get("stable_published_at")
        or meta.get("published_at")
        or file_entry.get("createdTime")
        or file_entry.get("modifiedTime")
    )
    if not pubdate_source:
        raise ValueError(
            f"Missing publish timestamp for media item '{file_entry.get('id')}'"
        )
    published_at = parse_datetime(pubdate_source)

    week_lecture_candidates: List[str] = []
    if folder_names:
        week_lecture_candidates.extend(folder_names)
    file_name = file_entry.get("name")
    if isinstance(file_name, str) and file_name.strip():
        week_lecture_candidates.append(file_name)
    if matched_quiz_key:
        week_lecture_candidates.append(matched_quiz_key)
    manual_source_folder = _extract_source_folder(manual_meta)
    if manual_source_folder:
        week_lecture_candidates.append(manual_source_folder)
    sort_week_number, lecture_number = extract_week_lecture_from_candidates(week_lecture_candidates)
    semester_start = feed_config.get("semester_week_start_date")
    semester_info = semester_week_info(published_at, semester_start)
    published_week_number = None
    if semester_info:
        published_week_number, _, _ = semester_info
    week_year_token = meta.get("week_reference_year")
    try:
        week_year = int(week_year_token) if week_year_token is not None else None
    except (TypeError, ValueError):
        week_year = None
    week_range_label = format_week_range(published_at, week_year)
    week_date_range = format_week_date_range(published_at, week_year)
    if week_range_label and published_week_number is None:
        match = re.search(r"Uge\s+(\d+)", week_range_label)
        if match:
            published_week_number = int(match.group(1))
    course_week_number = _coerce_week_number(meta.get("course_week"))
    semester_week_number_source = _resolve_semester_week_number_source(feed_config)
    week_number = _resolve_semester_week_number(
        semester_week_number_source=semester_week_number_source,
        lecture_key_week_number=sort_week_number,
        course_week_number=course_week_number,
        published_week_number=published_week_number,
    )
    is_unassigned_tail = bool(meta.get("unassigned_tail"))
    if is_unassigned_tail:
        week_number = None
        published_week_number = None
        week_range_label = None
        week_date_range = None

    semester_week_label = feed_config.get("semester_week_label")
    if not isinstance(semester_week_label, str) or not semester_week_label.strip():
        semester_week_label = "Week"
    semester_week_title_label = feed_config.get("semester_week_title_label")
    if not isinstance(semester_week_title_label, str) or not semester_week_title_label.strip():
        semester_week_title_label = semester_week_label
    semester_week_description_label = feed_config.get("semester_week_description_label")
    if (
        not isinstance(semester_week_description_label, str)
        or not semester_week_description_label.strip()
    ):
        semester_week_description_label = "Semester week"
    raw_description_prepend = feed_config.get("description_prepend_semester_week_lecture", False)
    description_prepend_semester_week_lecture = (
        raw_description_prepend if isinstance(raw_description_prepend, bool) else False
    )
    raw_enforce_week_label_consistency = feed_config.get("enforce_week_label_consistency", False)
    enforce_week_label_consistency = (
        raw_enforce_week_label_consistency
        if isinstance(raw_enforce_week_label_consistency, bool)
        else False
    )
    raw_description_blank_line_marker = feed_config.get("description_blank_line_marker")
    description_blank_line_marker = (
        raw_description_blank_line_marker.strip()
        if isinstance(raw_description_blank_line_marker, str)
        and raw_description_blank_line_marker.strip()
        else None
    )
    raw_description_footer = feed_config.get("description_footer")
    description_footer = (
        raw_description_footer.rstrip("\r\n")
        if isinstance(raw_description_footer, str) and raw_description_footer.strip()
        else None
    )
    audio_category_prefixes = _resolve_audio_category_prefixes(feed_config)
    weekly_overview_label = _resolve_weekly_overview_label(feed_config)
    slide_display_label = _resolve_slide_display_label(feed_config)
    slide_subject_separator = _resolve_slide_subject_separator(feed_config)
    title_subject_aliases = _resolve_title_subject_aliases(feed_config)
    compact_grundbog_subjects = _resolve_compact_grundbog_subjects(feed_config)

    semester_week_lecture_title = None
    if week_number and lecture_number:
        semester_week_lecture_title = (
            f"{semester_week_title_label} {week_number}, Forelæsning {lecture_number}"
        )
    elif lecture_number:
        semester_week_lecture_title = f"Forelæsning {lecture_number}"
    elif week_number:
        semester_week_lecture_title = f"{semester_week_title_label} {week_number}"

    semester_week_lecture_description = None
    if week_number and lecture_number:
        semester_week_lecture_description = (
            f"{semester_week_description_label} {week_number}, Forelæsning {lecture_number}"
        )
    elif lecture_number:
        semester_week_lecture_description = f"Forelæsning {lecture_number}"
    elif week_number:
        semester_week_lecture_description = f"{semester_week_description_label} {week_number}"

    compact_week_number = sort_week_number if sort_week_number else week_number
    compact_lecture_number = lecture_number
    description_text_link = _render_description_text_link(
        feed_config=feed_config,
        week_number=compact_week_number,
        lecture_number=lecture_number,
    )
    course_week_lecture = None
    if compact_week_number and compact_lecture_number:
        course_week_lecture = f"U{compact_week_number}F{compact_lecture_number}"
    elif compact_week_number:
        course_week_lecture = f"U{compact_week_number}"
    elif compact_lecture_number:
        course_week_lecture = f"F{compact_lecture_number}"

    raw_title_with_tags = _strip_cfg_tags(base_title)
    raw_title = re.sub(r"\s+", " ", LANGUAGE_TAG_PATTERN.sub("", raw_title_with_tags)).strip()
    raw_lower = raw_title.casefold()
    is_short = bool(SHORT_TAG_PATTERN.search(raw_title) or CFG_AUDIO_SHORT_PATTERN.search(source_title))
    is_weekly_overview = "alle kilder" in raw_lower or "all sources" in raw_lower
    cleaned_title = _strip_text_prefix(raw_title)
    cleaned_title = strip_brief_prefix(cleaned_title)
    cleaned_title = SHORT_TAG_PATTERN.sub("", cleaned_title).strip()
    cleaned_title = DEEP_DIVE_TAG_PATTERN.sub("", cleaned_title).strip()
    cleaned_title = strip_week_prefix(cleaned_title)
    cleaned_title = LEADING_EXERCISE_X_PATTERN.sub("", cleaned_title).strip()
    cleaned_title = cleaned_title.strip()
    slide_subject = _extract_slide_subject(cleaned_title)
    is_slide = slide_subject is not None

    if is_weekly_overview:
        cleaned_subject = WEEKLY_OVERVIEW_SUBJECT_PATTERN.sub("", cleaned_title)
        cleaned_subject = cleaned_subject.strip(" -–:")
    elif is_slide:
        cleaned_subject = slide_subject or cleaned_title
    else:
        cleaned_subject = cleaned_title
    cleaned_subject = _apply_title_subject_alias(
        cleaned_subject,
        title_subject_aliases,
        compact_grundbog_subjects=compact_grundbog_subjects,
    )

    topic = extract_topic(meta)
    if is_weekly_overview:
        display_subject = topic or cleaned_subject or cleaned_title or raw_title
    elif is_slide:
        if cleaned_subject:
            display_subject = f"{slide_display_label}{slide_subject_separator}{cleaned_subject}"
        else:
            display_subject = slide_display_label
    else:
        display_subject = cleaned_subject or cleaned_title or raw_title

    if is_short:
        type_label = "Short"
    elif is_weekly_overview:
        type_label = weekly_overview_label
    elif is_slide:
        type_label = slide_display_label
    else:
        type_label = "Reading"
    episode_kind = (
        "short"
        if is_short
        else ("weekly_overview" if is_weekly_overview else ("slide" if is_slide else "reading"))
    )
    skip_audio_category_prefix = False

    quiz_link_payloads: List[Dict[str, str]] = []
    quiz_url = None
    quiz_singular_label, quiz_plural_label, quiz_difficulty_labels = _resolve_quiz_display_labels(
        quiz_cfg
    )
    if quiz_cfg and matched_quiz_entry is not None:
        base_url = quiz_cfg.get("base_url")
        quiz_link_payloads = _resolve_quiz_link_payloads(base_url, matched_quiz_entry)
        if quiz_link_payloads:
            quiz_url = sorted(quiz_link_payloads, key=_quiz_primary_sort_key)[0]["url"]

    if is_unassigned_tail and not meta.get("title"):
        subject = (display_subject or cleaned_title or raw_title).strip()
        title_prefix = audio_category_prefixes.get(audio_category) if audio_category else None
        if title_prefix and subject:
            meta["title"] = f"{title_prefix} · {subject}"
            skip_audio_category_prefix = True
        elif title_prefix:
            meta["title"] = title_prefix
            skip_audio_category_prefix = True
        else:
            meta["title"] = subject or raw_title

    if not meta.get("title"):
        subject = display_subject or cleaned_title or raw_title
        if is_weekly_overview and type_label:
            subject_or_type = type_label
        else:
            subject_or_type = subject or type_label

        title_block_values = {
            "semester_week_lecture": semester_week_lecture_title,
            "course_week_lecture": course_week_lecture,
            "course_week_lecture_long": (
                f"{semester_week_title_label} {compact_week_number}, Forelæsning {compact_lecture_number}"
                if compact_week_number and compact_lecture_number
                else (
                    f"{semester_week_title_label} {compact_week_number}"
                    if compact_week_number
                    else (
                        f"Forelæsning {compact_lecture_number}"
                        if compact_lecture_number
                        else None
                    )
                )
            ),
            "semester_week": (
                f"{semester_week_title_label} {week_number}" if week_number else None
            ),
            "lecture": f"Forelæsning {lecture_number}" if lecture_number else None,
            "subject": subject,
            "type_label": type_label,
            "subject_or_type": subject_or_type,
            "week_range": f"({week_range_label})" if week_range_label else None,
            "week_date_range": week_date_range,
        }
        title_blocks = _resolve_blocks_for_kind(
            feed_config,
            global_key="title_blocks",
            by_kind_key="title_blocks_by_kind",
            kind=episode_kind,
            defaults=DEFAULT_TITLE_BLOCKS,
            allowed_blocks=TITLE_BLOCKS_ALLOWED,
        )
        title_value = _render_blocks(title_blocks, title_block_values, separator=" · ")
        meta["title"] = title_value or (display_subject or raw_title)
    title_value = meta.get("title") or base_title
    if important and prefix_replaced:
        updated_title, title_changed = _replace_text_prefix(title_value, require_start=False)
        if title_changed:
            title_value = updated_title
    if narrator:
        prefix = narrator.upper()
        if not title_value.upper().startswith(f"{prefix} "):
            title_value = f"{prefix} {title_value}"
    title_value = _strip_language_tags(title_value, strip_brief=not is_short)
    audio_category_prefix_position = _resolve_audio_category_prefix_position(feed_config)
    if audio_category and not skip_audio_category_prefix:
        title_prefix = audio_category_prefixes.get(audio_category)
        if title_prefix:
            title_value = _apply_audio_category_prefix(
                title_value,
                title_prefix,
                position=audio_category_prefix_position,
            )
        else:
            title_value = _normalize_category_prefix(title_value)
    active_regenerated_variant = False
    if isinstance(regeneration_variant_slot, str) and regeneration_variant_slot.strip().upper() == "B":
        active_regenerated_variant = True
    elif (
        active_b_variant_file_ids
        and str(file_entry.get("id") or "").strip() in active_b_variant_file_ids
    ):
        active_regenerated_variant = True
    if regen_marker and active_regenerated_variant:
        title_value = _apply_regeneration_marker(title_value, regen_marker, regen_marker_position)
    meta["title"] = title_value
    if suppress_week_prefix:
        meta.pop("suppress_week_prefix", None)

    description = meta.get("description")
    summary = meta.get("summary")
    if not description:
        if is_slide:
            text_label = cleaned_subject or cleaned_title or raw_title
        else:
            text_label = display_subject or cleaned_title or raw_title
        if is_short:
            descriptor = "Kort podcast"
        elif is_weekly_overview:
            descriptor = weekly_overview_label
        elif is_slide:
            descriptor = slide_display_label
        else:
            descriptor = "Reading"
        descriptor_subject = f"{descriptor}: {text_label}" if text_label else descriptor
        enabled_kinds_raw = (
            reading_summaries_cfg.get("enabled_kinds")
            if isinstance(reading_summaries_cfg, dict)
            else None
        )
        enabled_kinds = (
            enabled_kinds_raw
            if isinstance(enabled_kinds_raw, set)
            else {"reading", "short", "brief"}
        )
        summaries_enabled_for_kind = episode_kind in enabled_kinds or (
            episode_kind == "short" and "brief" in enabled_kinds
        )
        reading_summary_value: Optional[str] = None
        reading_key_points_value: Optional[str] = None
        weekly_overview_summary_value: Optional[str] = None
        weekly_overview_key_points_value: Optional[str] = None
        if summaries_enabled_for_kind and isinstance(reading_summaries, dict) and file_entry.get("name"):
            by_name = reading_summaries.get("by_name")
            if isinstance(by_name, dict):
                entry = _lookup_by_name_with_cfg_fallback(by_name, file_entry["name"])
                if isinstance(entry, dict):
                    summary_lines = entry.get("summary_lines")
                    if isinstance(summary_lines, list):
                        lines = [line.strip() for line in summary_lines if isinstance(line, str) and line.strip()]
                        if lines:
                            reading_summary_value = "\n".join(lines)
                    key_points = entry.get("key_points")
                    if isinstance(key_points, list):
                        points = [point.strip() for point in key_points if isinstance(point, str) and point.strip()]
                        if points:
                            key_points_label = "Key points"
                            if isinstance(reading_summaries_cfg, dict):
                                raw_label = reading_summaries_cfg.get("key_points_label")
                                if isinstance(raw_label, str) and raw_label.strip():
                                    key_points_label = raw_label.strip()
                            bullets = "\n".join(f"- {point}" for point in points)
                            reading_key_points_value = f"\n\n{key_points_label}:\n{bullets}"
        if episode_kind == "weekly_overview" and isinstance(weekly_overview_summaries, dict) and file_entry.get("name"):
            by_name = weekly_overview_summaries.get("by_name")
            if isinstance(by_name, dict):
                entry = _lookup_by_name_with_cfg_fallback(by_name, file_entry["name"])
                if isinstance(entry, dict):
                    summary_lines = entry.get("summary_lines")
                    if isinstance(summary_lines, list):
                        lines = [line.strip() for line in summary_lines if isinstance(line, str) and line.strip()]
                        if lines:
                            weekly_overview_summary_value = "\n".join(lines)
                    key_points = entry.get("key_points")
                    if isinstance(key_points, list):
                        points = [point.strip() for point in key_points if isinstance(point, str) and point.strip()]
                        if points:
                            key_points_label = "Key points"
                            if isinstance(reading_summaries_cfg, dict):
                                raw_label = reading_summaries_cfg.get("key_points_label")
                                if isinstance(raw_label, str) and raw_label.strip():
                                    key_points_label = raw_label.strip()
                            bullets = "\n".join(f"- {point}" for point in points)
                            weekly_overview_key_points_value = f"\n\n{key_points_label}:\n{bullets}"
                    if isinstance(weekly_overview_summaries_cfg, dict) and weekly_overview_summaries_cfg.get(
                        "warn_on_incomplete_sources", True
                    ):
                        meta_block = entry.get("meta")
                        if isinstance(meta_block, dict):
                            expected = meta_block.get("source_count_expected")
                            covered = meta_block.get("source_count_covered")
                            if (
                                isinstance(expected, int)
                                and isinstance(covered, int)
                                and expected > 0
                                and covered < expected
                            ):
                                print(
                                    f"Warning: weekly_overview_summaries coverage gap for "
                                    f"'{file_entry.get('name', '')}': covered {covered}/{expected}.",
                                    file=sys.stderr,
                                )
        description_block_values = {
            "descriptor_subject": descriptor_subject,
            "descriptor": descriptor,
            "subject": text_label,
            "topic": f"Emne: {topic}" if topic else None,
            "lecture": f"Forelæsning {lecture_number}" if lecture_number else None,
            "semester_week": (
                f"{semester_week_description_label} {week_number}" if week_number else None
            ),
            "text_link": description_text_link,
            "quiz": _render_quiz_block(
                quiz_link_payloads,
                singular_label=quiz_singular_label,
                plural_label=quiz_plural_label,
                difficulty_labels=quiz_difficulty_labels,
            ),
            "quiz_url": quiz_url,
            "reading_summary": (
                reading_summary_value or descriptor_subject
                if summaries_enabled_for_kind
                else None
            ),
            "reading_key_points": reading_key_points_value if summaries_enabled_for_kind else None,
            "weekly_overview_summary": (
                weekly_overview_summary_value or descriptor_subject
                if episode_kind == "weekly_overview"
                else None
            ),
            "weekly_overview_key_points": (
                weekly_overview_key_points_value if episode_kind == "weekly_overview" else None
            ),
        }
        description_blocks = _resolve_blocks_for_kind(
            feed_config,
            global_key="description_blocks",
            by_kind_key="description_blocks_by_kind",
            kind=episode_kind,
            defaults=DEFAULT_DESCRIPTION_BLOCKS,
            allowed_blocks=DESCRIPTION_BLOCKS_ALLOWED,
        )
        description = _render_blocks(
            description_blocks,
            description_block_values,
            separator=" · ",
        )
        if not description:
            description = descriptor_subject or summary or base_title
        meta["description"] = description

    if (
        description_prepend_semester_week_lecture
        and semester_week_lecture_description
        and isinstance(meta.get("description"), str)
    ):
        prefix_single = f"{semester_week_lecture_description}\n"
        prefix_double = f"{semester_week_lecture_description}\n\n"
        if meta["description"].startswith(prefix_double):
            pass
        elif meta["description"].startswith(prefix_single):
            tail = meta["description"][len(prefix_single) :]
            meta["description"] = f"{prefix_double}{tail}"
        else:
            meta["description"] = f"{prefix_double}{meta['description']}"

    if quiz_url:
        if not meta.get("link"):
            meta["link"] = quiz_url
    if summary:
        meta["summary"] = _strip_language_tags(summary)
    if meta.get("description"):
        alternate_episode_links = _render_alternate_episode_links(
            source_name=str(file_entry.get("name") or ""),
            alternate_episode_link_indexes=alternate_episode_link_indexes,
        )
        if alternate_episode_links and alternate_episode_links not in meta["description"]:
            meta["description"] = f"{meta['description'].rstrip()}\n\n{alternate_episode_links}"
        meta["description"] = _strip_language_tags(meta["description"], preserve_newlines=True)
        if description_blank_line_marker:
            meta["description"] = _apply_description_blank_line_marker(
                meta["description"],
                description_blank_line_marker,
            )
        if description_footer and not meta["description"].endswith(description_footer):
            meta["description"] = f"{meta['description']}{description_footer}"
    if (
        description_prepend_semester_week_lecture
        and isinstance(meta.get("title"), str)
        and isinstance(meta.get("description"), str)
    ):
        title_pair = _extract_week_lecture_pair(meta["title"])
        description_pair = _extract_week_lecture_pair(meta["description"])
        if title_pair and description_pair and title_pair != description_pair:
            mismatch_message = (
                f"Week label mismatch for '{file_entry.get('name', '')}': "
                f"title has week/lecture {title_pair[0]}/{title_pair[1]} but "
                f"description has {description_pair[0]}/{description_pair[1]}."
            )
            if enforce_week_label_consistency:
                raise ValueError(mismatch_message)
            print(f"Warning: {mismatch_message}", file=sys.stderr)

    explicit_default = feed_config.get("default_explicit", False)
    duration = meta.get("duration")
    pubdate_value = _rewrite_pubdate_year(
        format_rfc2822(published_at),
        _resolve_pubdate_year_rewrite(feed_config),
    )

    stable_guid = (
        str(meta.get("guid") or "").strip()
        or str(file_entry.get("stable_guid") or "").strip()
        or str(file_entry.get("id") or "").strip()
    )

    return {
        "episode_key": stable_guid,
        "guid": stable_guid,
        "title": meta.get("title") or base_title,
        "description": meta.get("description") or meta.get("summary") or base_title,
        "link": meta.get("link") or feed_config.get("link"),
        "published_at": published_at,
        "pubDate": pubdate_value,
        "mimeType": file_entry.get("mimeType", "audio/mpeg"),
        "size": file_entry.get("size"),
        "duration": duration,
        "explicit": str(meta.get("explicit", explicit_default)).lower(),
        "image": meta.get("image") or feed_config.get("image"),
        "episode_kind": episode_kind,
        "podcast_kind": _podcast_kind_from_audio_category(audio_category),
        "is_tts": audio_category == "lydbog",
        "lecture_key": (
            f"W{int(sort_week_number):02d}L{int(lecture_number)}"
            if sort_week_number and lecture_number
            else None
        ),
        "source_name": str(file_entry.get("name") or "").strip(),
        "source_drive_file_id": str(file_entry.get("source_drive_file_id") or file_entry.get("id") or "").strip(),
        "source_storage_provider": str(file_entry.get("source_storage_provider") or "drive").strip(),
        "source_storage_key": str(
            file_entry.get("source_storage_key")
            or file_entry.get("id")
            or ""
        ).strip(),
        "source_path": str(file_entry.get("source_path") or file_entry.get("name") or "").strip(),
        "sort_source_kind": (
            "weekly_overview" if is_weekly_overview else ("slide" if is_slide else "reading")
        ),
        "sort_subject_key": cleaned_subject or cleaned_title or raw_title,
        "sort_week": sort_week_number,
        "sort_lecture": lecture_number,
        "sort_tail": is_unassigned_tail,
        "audio_url": _render_public_media_url(file_entry, public_link_template),
    }


def build_feed_document(
    episodes: Iterable[Dict[str, Any]],
    feed_config: Dict[str, Any],
    last_build: dt.datetime,
) -> Any:
    from xml.etree import ElementTree as ET

    rss = ET.Element(
        "rss",
        attrib={
            "version": "2.0",
            f"xmlns:atom": ATOM_NS,
            f"xmlns:itunes": ITUNES_NS,
        },
    )
    channel = ET.SubElement(rss, "channel")

    def _set(name: str, value: Optional[str]) -> None:
        if value:
            ET.SubElement(channel, name).text = value

    feed_title = _strip_language_tags(feed_config.get("title"))
    _set("title", feed_title)
    _set("link", feed_config.get("link"))
    _set("description", feed_config.get("description"))
    _set("language", feed_config.get("language"))
    _set("generator", "gdrive_podcast_feed.py")
    _set("lastBuildDate", format_rfc2822(last_build))
    if feed_config.get("ttl"):
        _set("ttl", str(feed_config["ttl"]))

    if feed_config.get("self_link"):
        ET.SubElement(
            channel,
            f"{{{ATOM_NS}}}link",
            attrib={
                "href": feed_config["self_link"],
                "rel": "self",
                "type": "application/rss+xml",
            },
        )

    if feed_config.get("author"):
        _set("itunes:author", feed_config["author"])

    owner = feed_config.get("owner", {})
    if owner.get("name") or owner.get("email"):
        owner_el = ET.SubElement(channel, "itunes:owner")
        if owner.get("name"):
            ET.SubElement(owner_el, "itunes:name").text = owner["name"]
        if owner.get("email"):
            ET.SubElement(owner_el, "itunes:email").text = owner["email"]

    if feed_config.get("image"):
        image_url = feed_config["image"]
        ET.SubElement(channel, "itunes:image", attrib={"href": image_url})
        standard_image = ET.SubElement(channel, "image")
        ET.SubElement(standard_image, "url").text = image_url
        if feed_title:
            ET.SubElement(standard_image, "title").text = feed_title
        if feed_config.get("link"):
            ET.SubElement(standard_image, "link").text = feed_config["link"]

    category = feed_config.get("category")
    if isinstance(category, dict):
        parent_text = category.get("name")
        sub_text = category.get("sub")
        if parent_text:
            category_el = ET.SubElement(channel, "itunes:category", attrib={"text": parent_text})
            if sub_text:
                ET.SubElement(category_el, "itunes:category", attrib={"text": sub_text})
    elif category:
        ET.SubElement(channel, "itunes:category", attrib={"text": category})

    new_items = _sort_feed_episodes(episodes, feed_config)
    for item in new_items:
        entry = ET.SubElement(channel, "item")
        for tag, key in ("title", "title"), ("description", "description"), ("guid", "guid"), ("link", "link"), ("pubDate", "pubDate"):
            value = item.get(key)
            if value:
                el = ET.SubElement(entry, tag)
                el.text = value
                if tag == "guid" and not item.get("guid", "").startswith("http"):
                    el.set("isPermaLink", "false")

        enclosure = ET.SubElement(entry, "enclosure")
        enclosure.set("url", item["audio_url"])
        if item.get("size"):
            enclosure.set("length", str(item["size"]))
        enclosure.set("type", item.get("mimeType", "audio/mpeg"))

        if item.get("duration"):
            ET.SubElement(entry, "itunes:duration").text = str(item["duration"])
        ET.SubElement(entry, "itunes:explicit").text = "true" if item["explicit"] == "true" else "false"
        if item.get("image"):
            ET.SubElement(entry, "itunes:image", attrib={"href": item["image"]})

    return rss


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="Path to JSON config file")
    parser.add_argument(
        "--metadata",
        type=Path,
        help="Optional JSON metadata overrides for individual episodes",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build feed/inventory in memory without writing files or modifying Google Drive permissions",
    )
    args = parser.parse_args()

    config = load_json(args.config)
    config["__config_path__"] = str(args.config.resolve())
    feed_cfg = config.get("feed", {})
    try:
        validate_feed_block_config(feed_cfg)
    except ValueError as exc:
        raise SystemExit(f"Invalid feed block config: {exc}") from exc
    alternate_episode_link_indexes = load_alternate_episode_link_indexes(config)
    overrides_path = args.metadata or (Path(config.get("episode_metadata", "")) if config.get("episode_metadata") else None)
    overrides = load_json(overrides_path) if overrides_path and overrides_path.exists() else {}
    reading_summaries_cfg_raw = config.get("reading_summaries")
    reading_summaries_cfg: Dict[str, Any] = {}
    reading_summaries: Optional[Dict[str, Any]] = None
    if reading_summaries_cfg_raw is not None and not isinstance(reading_summaries_cfg_raw, dict):
        print("Warning: reading_summaries must be a JSON object; ignoring.", file=sys.stderr)
    elif isinstance(reading_summaries_cfg_raw, dict):
        key_points_label = reading_summaries_cfg_raw.get("key_points_label")
        if not isinstance(key_points_label, str) or not key_points_label.strip():
            key_points_label = "Key points"

        enabled_kinds_raw = reading_summaries_cfg_raw.get("enabled_kinds")
        enabled_kinds: Set[str] = {"reading", "short", "brief"}
        if isinstance(enabled_kinds_raw, list):
            parsed_enabled = {
                str(kind).strip()
                for kind in enabled_kinds_raw
                if str(kind).strip() in EPISODE_KINDS
            }
            if parsed_enabled:
                enabled_kinds = parsed_enabled
            else:
                print(
                    "Warning: reading_summaries.enabled_kinds had no valid kinds; "
                    "defaulting to reading+short.",
                    file=sys.stderr,
                )
        elif enabled_kinds_raw is not None:
            print(
                "Warning: reading_summaries.enabled_kinds must be a list; "
                "defaulting to reading+short.",
                file=sys.stderr,
            )

        reading_summaries_cfg = {
            "key_points_label": key_points_label.strip(),
            "enabled_kinds": enabled_kinds,
        }

        summaries_file = reading_summaries_cfg_raw.get("file")
        if summaries_file:
            summaries_path = Path(str(summaries_file)).expanduser()
            if not summaries_path.is_absolute():
                candidates = [summaries_path, args.config.parent / summaries_path]
                resolved = next((path for path in candidates if path.exists()), None)
                if resolved is not None:
                    summaries_path = resolved.resolve()
                elif str(summaries_path).startswith("shows/"):
                    summaries_path = summaries_path.resolve()
                else:
                    summaries_path = (args.config.parent / summaries_path).resolve()
            if summaries_path.exists():
                try:
                    reading_summaries = load_reading_summaries(summaries_path)
                except Exception as exc:
                    print(
                        f"Warning: failed to load reading summaries from {summaries_path}: {exc}",
                        file=sys.stderr,
                    )
            else:
                print(
                    f"Warning: reading summaries file not found: {summaries_path}",
                    file=sys.stderr,
                )
        else:
            print(
                "Warning: reading_summaries.file not configured; summary injection disabled.",
                file=sys.stderr,
            )

    weekly_overview_summaries_cfg_raw = config.get("weekly_overview_summaries")
    weekly_overview_summaries_cfg: Dict[str, Any] = {}
    weekly_overview_summaries: Optional[Dict[str, Any]] = None
    if weekly_overview_summaries_cfg_raw is not None and not isinstance(
        weekly_overview_summaries_cfg_raw, dict
    ):
        print("Warning: weekly_overview_summaries must be a JSON object; ignoring.", file=sys.stderr)
    elif isinstance(weekly_overview_summaries_cfg_raw, dict):
        warn_on_incomplete_sources_raw = weekly_overview_summaries_cfg_raw.get("warn_on_incomplete_sources", True)
        warn_on_incomplete_sources = (
            warn_on_incomplete_sources_raw
            if isinstance(warn_on_incomplete_sources_raw, bool)
            else True
        )
        language = weekly_overview_summaries_cfg_raw.get("language")
        if not isinstance(language, str) or not language.strip():
            language = "da"
        mode = weekly_overview_summaries_cfg_raw.get("mode")
        if not isinstance(mode, str) or not mode.strip():
            mode = "manual_cache_from_reading_summaries"
        weekly_overview_summaries_cfg = {
            "warn_on_incomplete_sources": warn_on_incomplete_sources,
            "language": language.strip(),
            "mode": mode.strip(),
        }

        weekly_summaries_file = weekly_overview_summaries_cfg_raw.get("file")
        if weekly_summaries_file:
            weekly_summaries_path = Path(str(weekly_summaries_file)).expanduser()
            if not weekly_summaries_path.is_absolute():
                candidates = [weekly_summaries_path, args.config.parent / weekly_summaries_path]
                resolved = next((path for path in candidates if path.exists()), None)
                if resolved is not None:
                    weekly_summaries_path = resolved.resolve()
                elif str(weekly_summaries_path).startswith("shows/"):
                    weekly_summaries_path = weekly_summaries_path.resolve()
                else:
                    weekly_summaries_path = (args.config.parent / weekly_summaries_path).resolve()
            if weekly_summaries_path.exists():
                try:
                    weekly_overview_summaries = load_weekly_overview_summaries(weekly_summaries_path)
                except Exception as exc:
                    print(
                        f"Warning: failed to load weekly overview summaries from {weekly_summaries_path}: {exc}",
                        file=sys.stderr,
                    )
            else:
                print(
                    f"Warning: weekly overview summaries file not found: {weekly_summaries_path}",
                    file=sys.stderr,
                )
        else:
            print(
                "Warning: weekly_overview_summaries.file not configured; weekly summary injection disabled.",
                file=sys.stderr,
            )

    quiz_cfg = config.get("quiz") if isinstance(config.get("quiz"), dict) else None
    quiz_links: Optional[Dict[str, Any]] = None
    if quiz_cfg:
        links_file = quiz_cfg.get("links_file")
        if links_file:
            links_path = Path(str(links_file)).expanduser()
            if not links_path.is_absolute():
                candidates = [links_path, args.config.parent / links_path]
                resolved = next((path for path in candidates if path.exists()), None)
                if resolved is not None:
                    links_path = resolved.resolve()
                elif str(links_path).startswith("shows/"):
                    # Most show configs store repo-root-prefixed paths (e.g. shows/<slug>/quiz_links.json).
                    links_path = links_path.resolve()
                else:
                    links_path = (args.config.parent / links_path).resolve()
            if links_path.exists():
                try:
                    quiz_links = load_json(links_path)
                except Exception as exc:
                    print(
                        f"Warning: failed to load quiz links from {links_path}: {exc}",
                        file=sys.stderr,
                    )
            else:
                print(
                    f"Warning: quiz links file not found: {links_path}",
                    file=sys.stderr,
                )

    # Regeneration registry — selects the active A/B variant per logical episode
    # and optionally marks active B variants in the title.
    active_b_variant_file_ids: Optional[Set[str]] = None
    regen_marker: Optional[str] = None
    regen_marker_position = "suffix"
    registry_entries_by_lid: Dict[str, Dict[str, Any]] = {}
    regen_marker_cfg = config.get("regeneration_marker")
    if isinstance(regen_marker_cfg, dict) and regen_marker_cfg.get("enabled", True):
        regen_marker = str(regen_marker_cfg.get("marker") or "✦").strip() or "✦"
        regen_marker_position = str(regen_marker_cfg.get("position") or "suffix").strip().lower()
        regen_file = regen_marker_cfg.get("file")
        if regen_file:
            regen_path = Path(str(regen_file)).expanduser()
            if not regen_path.is_absolute():
                candidates = [regen_path, args.config.parent / regen_path]
                regen_path = next((p for p in candidates if p.exists()), args.config.parent / regen_path)
            if regen_path.exists():
                try:
                    regen_registry = _load_regeneration_registry(regen_path)
                    registry_entries_by_lid = _normalize_registry_entry_map(regen_registry)
                    active_b_variant_file_ids = {
                        str((e.get("variants") or {}).get("B", {}).get("episode_key") or "").strip()
                        for e in registry_entries_by_lid.values()
                        if str(e.get("active_variant") or "").strip().upper() == "B"
                    }
                    active_b_variant_file_ids.discard("")
                except Exception as exc:
                    print(f"Warning: failed to load regeneration registry from {regen_path}: {exc}", file=sys.stderr)
            else:
                print(f"Warning: regeneration_marker.file not found: {regen_path}", file=sys.stderr)

    storage = build_storage_backend(config)
    provider = resolve_storage_provider(config)
    public_template = resolve_public_link_template(config)
    allowed_mime_types = config.get("allowed_mime_types")
    if isinstance(allowed_mime_types, str):
        allowed_mime_types = [allowed_mime_types]
    filters = parse_filters(config.get("filters"))
    existing_identity_map = _load_existing_inventory_identity_map(config)
    existing_publication_state_map = _load_existing_inventory_publication_state_map(config)

    auto_spec: Optional[AutoSpec] = None
    auto_spec_path_value = config.get("auto_spec")
    if auto_spec_path_value:
        auto_spec_path = Path(auto_spec_path_value)
        if not auto_spec_path.exists():
            candidate = args.config.parent / auto_spec_path_value
            if candidate.exists():
                auto_spec_path = candidate
        if not auto_spec_path.exists():
            raise SystemExit(f"Auto spec file not found: {auto_spec_path_value}")
        auto_spec = AutoSpec.from_path(auto_spec_path)

    doc_marked_titles_mode = str(config.get("important_text_mode", "all_markers")).lower()
    doc_marked_titles: Set[str] = set()
    doc_sources_config = config.get("important_text_docs")
    if doc_sources_config:
        if isinstance(doc_sources_config, (str, Path)):
            doc_sources_iterable = [doc_sources_config]
        else:
            doc_sources_iterable = list(doc_sources_config)
        resolved_docs: List[Path] = []
        for entry in doc_sources_iterable:
            if not entry:
                continue
            entry_path = Path(str(entry))
            search_candidates = [entry_path]
            if not entry_path.is_absolute():
                search_candidates.insert(0, args.config.parent / entry_path)
            found_path: Optional[Path] = None
            for candidate in search_candidates:
                if candidate.exists():
                    found_path = candidate
                    break
            if not found_path:
                print(f"Warning: importance doc not found: {entry_path}", file=sys.stderr)
                continue
            resolved_docs.append(found_path)
        if resolved_docs:
            doc_marked_titles = collect_doc_marked_titles(
                resolved_docs, mode=doc_marked_titles_mode
            )

    artwork_enabled = bool(config.get("episode_image_from_infographics", False))
    image_lookup: Dict[Tuple[Tuple[str, ...], str], Dict[str, Any]] = {}
    image_lookup_canonical: Dict[Tuple[Tuple[str, ...], str], Dict[str, Any]] = {}
    image_candidates_by_stem: Dict[str, List[Dict[str, Any]]] = {}
    image_candidates_by_canonical: Dict[str, List[Dict[str, Any]]] = {}
    if artwork_enabled:
        image_mime_types = config.get("episode_image_mime_types") or ["image/png"]
        if isinstance(image_mime_types, str):
            image_mime_types = [image_mime_types]
        preferred_exts = config.get("episode_image_prefer_exts") or [".png"]
        if isinstance(preferred_exts, str):
            preferred_exts = [preferred_exts]
        preferred_exts = [
            ext if ext.startswith(".") else f".{ext}"
            for ext in (str(ext).lower() for ext in preferred_exts)
        ]
        image_files = storage.list_media_files(mime_type_filters=image_mime_types)
        for image_file in image_files:
            folder_names = storage.build_folder_path(image_file)
            raw_stem = _normalize_stem(image_file.get("name", ""))
            canonical_stem = _canonicalize_episode_stem(image_file.get("name", ""))
            if not raw_stem and not canonical_stem:
                continue
            folder_key = _folder_key(folder_names)
            if raw_stem:
                key = (folder_key, raw_stem)
                image_lookup[key] = _select_preferred_image(
                    image_lookup.get(key), image_file, preferred_exts
                )
                image_candidates_by_stem.setdefault(raw_stem, []).append(
                    {"file": image_file, "folder_key": folder_key}
                )
            if canonical_stem:
                key = (folder_key, canonical_stem)
                image_lookup_canonical[key] = _select_preferred_image(
                    image_lookup_canonical.get(key), image_file, preferred_exts
                )
                image_candidates_by_canonical.setdefault(canonical_stem, []).append(
                    {"file": image_file, "folder_key": folder_key}
                )

    media_files = storage.list_media_files(mime_type_filters=allowed_mime_types)
    if provider == "drive":
        media_files = _collapse_duplicate_drive_files(media_files)

    artwork_stats = {"matched": 0, "missing": 0, "ambiguous": 0}
    artwork_unmatched: List[str] = []
    artwork_ambiguous: List[str] = []
    registry_skipped: List[str] = []
    registry_unmatched_active: List[str] = []

    episodes: List[Dict[str, Any]] = []
    for media_file in media_files:
        _apply_existing_identity(media_file, existing_identity_map)
        _apply_existing_publication_state(media_file, existing_publication_state_map)
        folder_names = storage.build_folder_path(media_file)
        matched_slot: Optional[str] = None
        logical_id: Optional[str] = None
        registry_decision = _registry_selection_for_file(media_file, registry_entries_by_lid)
        if registry_decision is None:
            if not matches_filters(media_file, folder_names, filters):
                continue
        else:
            include_by_registry, logical_id, matched_slot = registry_decision
            if not include_by_registry:
                if matched_slot is None:
                    registry_unmatched_active.append(f"{logical_id}: {media_file.get('name', '')}")
                else:
                    registry_skipped.append(
                        f"{logical_id}: slot {matched_slot} skipped for {media_file.get('name', '')}"
                    )
                continue
            registry_entry = registry_entries_by_lid.get(logical_id) if logical_id else None
            if registry_entry is not None:
                baseline_published_at = _registry_baseline_published_at(registry_entry)
                if baseline_published_at:
                    media_file["stable_published_at"] = baseline_published_at

        permission_added = storage.ensure_public_access(
            media_file,
            dry_run=args.dry_run,
        )
        if permission_added:
            print(f"Enabled link sharing for {media_file['name']} ({media_file['id']})")

        episode_image_url: Optional[str] = None
        if artwork_enabled:
            folder_key = _folder_key(folder_names)
            raw_stem = _normalize_stem(media_file.get("name", ""))
            canonical_stem = _canonicalize_episode_stem(media_file.get("name", ""))
            image_file: Optional[Dict[str, Any]] = None
            status = "missing"
            if image_lookup or image_candidates_by_stem:
                image_file, status = _resolve_image_for_stem(
                    lookup=image_lookup,
                    candidates_by_stem=image_candidates_by_stem,
                    folder_key=folder_key,
                    stem=raw_stem,
                    preferred_exts=preferred_exts,
                )
            if not image_file and canonical_stem and canonical_stem != raw_stem:
                image_file, status = _resolve_image_for_stem(
                    lookup=image_lookup_canonical,
                    candidates_by_stem=image_candidates_by_canonical,
                    folder_key=folder_key,
                    stem=canonical_stem,
                    preferred_exts=preferred_exts,
                )
            if image_file:
                artwork_permission_added = storage.ensure_public_access(
                    image_file,
                    dry_run=args.dry_run,
                )
                if artwork_permission_added:
                    print(
                        "Enabled link sharing for artwork "
                        f"{image_file['name']} ({image_file['id']})"
                    )
                episode_image_url = storage.build_public_url(
                    image_file,
                    public_link_template=public_template,
                )
                artwork_stats["matched"] += 1
            else:
                folder_path = "/".join(folder_names) if folder_names else "—"
                if status == "ambiguous":
                    artwork_stats["ambiguous"] += 1
                    artwork_ambiguous.append(
                        f"{media_file.get('name', '')} (folder: {folder_path})"
                    )
                else:
                    artwork_stats["missing"] += 1
                    artwork_unmatched.append(
                        f"{media_file.get('name', '')} (folder: {folder_path})"
                    )

        auto_meta = auto_spec.metadata_for(media_file, folder_names) if auto_spec else None
        episodes.append(
            build_episode_entry(
                media_file,
                feed_cfg,
                overrides,
                public_link_template=public_template,
                auto_meta=auto_meta,
                folder_names=folder_names,
                doc_marked_titles=doc_marked_titles,
                episode_image_url=episode_image_url,
                quiz_cfg=quiz_cfg,
                quiz_links=quiz_links,
                reading_summaries_cfg=reading_summaries_cfg,
                reading_summaries=reading_summaries,
                weekly_overview_summaries_cfg=weekly_overview_summaries_cfg,
                weekly_overview_summaries=weekly_overview_summaries,
                active_b_variant_file_ids=active_b_variant_file_ids,
                regeneration_variant_slot=matched_slot,
                regen_marker=regen_marker,
                regen_marker_position=regen_marker_position,
                alternate_episode_link_indexes=alternate_episode_link_indexes,
            )
        )

    if registry_skipped:
        print(
            f"Registry selection skipped {len(registry_skipped)} non-active variant file(s).",
            file=sys.stderr,
        )
    if registry_unmatched_active:
        print(
            "Warning: tracked registry episode(s) had media files that did not match a declared A/B variant:",
            file=sys.stderr,
        )
        for item in registry_unmatched_active[:20]:
            print(f"  - {item}", file=sys.stderr)
        if len(registry_unmatched_active) > 20:
            print(f"  ... and {len(registry_unmatched_active) - 20} more", file=sys.stderr)

    if artwork_enabled:
        if not (image_lookup or image_lookup_canonical):
            print(
                "Warning: episode_image_from_infographics enabled but no image files found.",
                file=sys.stderr,
            )
        if artwork_stats["missing"] or artwork_stats["ambiguous"]:
            print(
                "Artwork summary: matched "
                f"{artwork_stats['matched']}, missing {artwork_stats['missing']}, "
                f"ambiguous {artwork_stats['ambiguous']}.",
                file=sys.stderr,
            )
            if artwork_unmatched:
                print("Missing artwork for:", file=sys.stderr)
                for entry in artwork_unmatched[:20]:
                    print(f"  - {entry}", file=sys.stderr)
                if len(artwork_unmatched) > 20:
                    remaining = len(artwork_unmatched) - 20
                    print(f"  ... and {remaining} more", file=sys.stderr)
            if artwork_ambiguous:
                print("Ambiguous artwork matches for:", file=sys.stderr)
                for entry in artwork_ambiguous[:20]:
                    print(f"  - {entry}", file=sys.stderr)
                if len(artwork_ambiguous) > 20:
                    remaining = len(artwork_ambiguous) - 20
                    print(f"  ... and {remaining} more", file=sys.stderr)

    episodes = _synthesize_tail_grundbog_lydbog_block(episodes, feed_cfg)

    if not episodes:
        if media_files:
            raise SystemExit(
                "No audio files matched the configured filters, registry selection, or naming rules."
            )
        raise SystemExit(f"No audio files found in the configured {provider} media source.")

    last_build = max(item["published_at"] for item in episodes)
    feed_document = build_feed_document(episodes, feed_cfg, last_build)
    output_path = Path(config["output_feed"])
    inventory_output_path = _output_inventory_path(config)
    inventory_payload = None
    if inventory_output_path is not None:
        inventory_payload = build_episode_inventory_payload(
            episodes=episodes,
            config=config,
            last_build=last_build,
        )
    if args.dry_run:
        print(f"Dry run: would write feed to {output_path}")
        if inventory_output_path is not None:
            print(f"Dry run: would write episode inventory to {inventory_output_path}")
        return
    save_feed(feed_document, output_path)
    print(f"Feed written to {output_path}")
    if inventory_output_path is not None and inventory_payload is not None:
        save_json(inventory_payload, inventory_output_path)
        print(f"Episode inventory written to {inventory_output_path}")


if __name__ == "__main__":
    main()
