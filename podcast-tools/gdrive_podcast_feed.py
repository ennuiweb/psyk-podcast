#!/usr/bin/env python3
"""Generate a podcast RSS feed from audio files stored in a Google Drive folder."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/drive"]
ATOM_NS = "http://www.w3.org/2005/Atom"
ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
TEXT_PREFIX = "[Tekst]"
HIGHLIGHTED_TEXT_PREFIX = "[Gul tekst]"
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


def build_drive_service(credentials_path: Path):
    credentials = service_account.Credentials.from_service_account_file(
        str(credentials_path), scopes=SCOPES
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


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
        response = service.files().list(**params).execute()
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


def list_audio_files(
    service,
    folder_id: str,
    *,
    drive_id: Optional[str] = None,
    supports_all_drives: bool = False,
    mime_type_filters: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    files: List[Dict[str, Any]] = []
    pending: List[str] = [folder_id]
    seen: Set[str] = set()
    audio_fields = (
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
                fields=audio_fields,
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


def _listify(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item is not None]
    return [str(value)]


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
    permissions = service.permissions().list(**params).execute()
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
    service.permissions().create(**create_params).execute()
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
    return overrides.get("by_id", {}).get(
        file_entry["id"],
        overrides.get("by_name", {}).get(file_entry["name"], overrides.get(file_entry["name"], {})),
    )


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
            matches.extend(
                {
                    f"w{iso_week}",
                    f"week {iso_week}",
                    str(iso_week),
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
                    summary = f"Topic of the week: {topic}"
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
                before_ok = True
                after_ok = True
                if needle and needle[0].isdigit() and before_char.isdigit():
                    before_ok = False
                if needle and needle[-1].isdigit() and after_char.isdigit():
                    after_ok = False
                if before_ok and before_char and before_char.isalnum() and needle and needle[0].isalpha():
                    # Avoid matching alphabetic prefixes like 'w1' in 'bw12'
                    before_ok = False
                if after_ok and after_char and after_char.isalnum() and needle and needle[-1].isalpha():
                    after_ok = False
                if before_ok and after_ok:
                    return True
                start = candidate.find(needle, start + 1)
            return False

        for token in tokens:
            if not token:
                continue
            needle = token.lower()
            for candidate in candidates:
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
            base_datetime = self._earliest_rule_datetime - dt.timedelta(days=7)
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
                    scheduled = base_datetime + dt.timedelta(minutes=offset_minutes)
                    self._unassigned_sequence_counts[sequence_number] = duplicate_index + 1
                    self._unassigned_sequence_allocations[seq_key] = scheduled
            if scheduled is None:
                offset_minutes = self._unassigned_counter * self._default_increment_minutes
                scheduled = base_datetime - dt.timedelta(minutes=offset_minutes)
                self._unassigned_counter += 1
                modified_token = file_entry.get("modifiedTime")
                if modified_token:
                    try:
                        candidate = parse_datetime(modified_token)
                    except Exception:  # pragma: no cover - defensive
                        candidate = None
                    if candidate:
                        if candidate.tzinfo is None:
                            candidate = candidate.replace(tzinfo=self.timezone)
                        if candidate < scheduled:
                            scheduled = candidate
            self._unassigned_allocations[fallback_key] = scheduled
        return {
            "published_at": scheduled.isoformat(),
            "suppress_week_prefix": True,
            "week_reference_year": self.week_reference_year,
        }

    @staticmethod
    def _extract_sequence_number(file_name: Optional[str]) -> Optional[int]:
        if not file_name:
            return None
        stem = file_name.rsplit(".", 1)[0]
        stem = stem.rsplit(" - ", 1)[0]
        match = re.match(r"\D*(\d+)", stem.strip())
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
    metadata = service.files().get(**params).execute()
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


def _normalize_title_for_matching(value: str) -> str:
    if not value:
        return ""
    cleaned = _strip_text_prefix(value.strip())
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
    return bool(WEEK_X_PREFIX_PATTERN.match(stripped))


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


WEEK_LECTURE_PATTERN = re.compile(r"\bw(\d{2})l(\d+)\b", re.IGNORECASE)
BRIEF_PREFIX_PATTERN = re.compile(r"^\[brief\]\s*", re.IGNORECASE)
WEEK_PREFIX_PATTERN = re.compile(r"^w\d{2}l\d+\s*[-–:]\s*", re.IGNORECASE)
WEEK_ONLY_PREFIX_PATTERN = re.compile(r"^w\d{2}\s*[-–:]\s*", re.IGNORECASE)


def extract_week_lecture(
    folder_names: Optional[List[str]],
    file_name: Optional[str],
) -> Tuple[Optional[int], Optional[int]]:
    candidates = []
    if folder_names:
        candidates.extend(folder_names)
    if file_name:
        candidates.append(file_name)
    for candidate in candidates:
        match = WEEK_LECTURE_PATTERN.search(candidate)
        if match:
            return int(match.group(1)), int(match.group(2))
    return None, None


def strip_week_prefix(value: str) -> str:
    if not value:
        return value
    cleaned = WEEK_PREFIX_PATTERN.sub("", value)
    cleaned = WEEK_ONLY_PREFIX_PATTERN.sub("", cleaned)
    return cleaned.strip()


def strip_brief_prefix(value: str) -> str:
    if not value:
        return value
    return BRIEF_PREFIX_PATTERN.sub("", value).strip()


def extract_topic(meta: Dict[str, Any]) -> Optional[str]:
    topic = meta.get("topic")
    if isinstance(topic, str) and topic.strip():
        return topic.strip()
    summary = meta.get("summary")
    if isinstance(summary, str):
        lowered = summary.lower()
        if lowered.startswith("topic of the week:"):
            return summary.split(":", 1)[1].strip()
    return None


def build_episode_entry(
    file_entry: Dict[str, Any],
    feed_config: Dict[str, Any],
    overrides: Dict[str, Any],
    public_link_template: str,
    auto_meta: Optional[Dict[str, Any]] = None,
    folder_names: Optional[List[str]] = None,
    doc_marked_titles: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    if auto_meta:
        meta.update(auto_meta)
    manual_meta = item_metadata(overrides, file_entry) or {}
    meta.update(manual_meta)
    suppress_week_prefix = bool(meta.get("suppress_week_prefix"))
    narrator = meta.get("narrator")
    if not narrator:
        narrator = AutoSpec._extract_voice(file_entry.get("name"))
        if narrator:
            meta.setdefault("narrator", narrator)
    base_title = file_entry["name"].rsplit(".", 1)[0]
    if narrator:
        suffix = f" - {narrator}"
        if base_title.lower().endswith(suffix.lower()):
            base_title = base_title[: -len(suffix)].rstrip()
    important = is_marked_important(
        file_entry,
        doc_marked_titles,
    )
    prefix_replaced = False
    if important:
        base_title, prefix_replaced = _replace_text_prefix(base_title, require_start=True)
    pubdate_source = (
        meta.get("published_at")
        or file_entry.get("createdTime")
        or file_entry.get("modifiedTime")
    )
    if not pubdate_source:
        raise ValueError(
            f"Missing publish timestamp for Drive file '{file_entry.get('id')}'"
        )
    published_at = parse_datetime(pubdate_source)

    language = str(feed_config.get("language", "")).lower()
    is_english = language.startswith("en")
    en_suffix = " [EN]" if is_english else ""
    has_en_suffix = "[en]" in base_title.casefold()
    _, lecture_number = extract_week_lecture(folder_names, file_entry.get("name"))
    semester_start = feed_config.get("semester_week_start_date")
    semester_info = semester_week_info(published_at, semester_start)
    week_label = None
    week_number = None
    if semester_info:
        week_number, week_start, week_end = semester_info
        week_label = f"Week {week_number} (Uge {week_number} {week_start:%d/%m} - {week_end:%d/%m})"
    if not week_label:
        week_label = derive_week_label(folder_names or [], meta.get("course_week"))
        if week_label:
            week_year_token = meta.get("week_reference_year")
            try:
                week_year = int(week_year_token) if week_year_token is not None else None
            except (TypeError, ValueError):
                week_year = None
            week_dates = format_week_range(published_at, week_year)
            if week_dates:
                week_label = f"{week_label} ({week_dates})"

    raw_title = base_title
    raw_lower = raw_title.casefold()
    is_brief = "[brief]" in raw_lower
    is_weekly_overview = "alle kilder" in raw_lower or "all sources" in raw_lower
    cleaned_title = _strip_text_prefix(raw_title)
    cleaned_title = strip_brief_prefix(cleaned_title)
    cleaned_title = strip_week_prefix(cleaned_title)
    cleaned_title = cleaned_title.strip()

    if is_weekly_overview:
        cleaned_subject = re.sub(r"\b(alle kilder|all sources)\b", "", cleaned_title, flags=re.IGNORECASE)
        cleaned_subject = cleaned_subject.strip(" -–:")
    else:
        cleaned_subject = cleaned_title

    topic = extract_topic(meta)
    if is_weekly_overview:
        display_subject = topic or cleaned_subject or cleaned_title or raw_title
    else:
        display_subject = cleaned_subject or cleaned_title or raw_title

    if is_brief:
        type_label = "Brief"
    elif is_weekly_overview:
        type_label = "All sources" if is_english else "Alle kilder"
    else:
        type_label = "Reading" if is_english else "Læsning"

    important_label = "IMPORTANT" if is_english else "VIGTIG"
    important_tag = f" · {important_label}" if important else ""

    if not meta.get("title"):
        if suppress_week_prefix:
            meta["title"] = display_subject or raw_title
        else:
            segments = []
            if week_label:
                segments.append(week_label)
            if lecture_number:
                segments.append(f"L{lecture_number}")
            segments.append(type_label)
            if display_subject:
                segments.append(display_subject)
            title_value = " · ".join(segment for segment in segments if segment)
            if important:
                title_value = f"{title_value}{important_tag}"
            if is_english and not has_en_suffix and not title_value.endswith(en_suffix):
                title_value = f"{title_value}{en_suffix}"
            meta["title"] = title_value
    title_value = meta.get("title") or base_title
    if important and prefix_replaced:
        updated_title, title_changed = _replace_text_prefix(title_value, require_start=False)
        if title_changed:
            title_value = updated_title
    if narrator:
        prefix = narrator.upper()
        if not title_value.upper().startswith(f"{prefix} "):
            title_value = f"{prefix} {title_value}"
    meta["title"] = title_value
    if suppress_week_prefix:
        meta.pop("suppress_week_prefix", None)

    description = meta.get("description")
    summary = meta.get("summary")
    if not description:
        format_label = "brief" if is_brief else "deep-dive"
        language_label = "EN" if is_english else "DA"
        text_label = (type_label if is_weekly_overview else (display_subject or cleaned_title or raw_title))
        if is_english:
            parts = []
            if week_number:
                parts.append(f"Semester week {week_number}")
            if lecture_number:
                parts.append(f"Lecture {lecture_number}")
            if narrator:
                parts.append(f"Narrator: {narrator}")
            if topic:
                parts.append(f"Topic: {topic}")
            parts.append(f"Type: {type_label}")
            if text_label:
                parts.append(f"Text: {text_label}")
            parts.append(f"Important: {'yes' if important else 'no'}")
            parts.append(f"Format: {format_label}")
            parts.append(f"Language: {language_label}")
        else:
            parts = []
            if week_number:
                parts.append(f"Semesteruge {week_number}")
            if lecture_number:
                parts.append(f"Forelæsning {lecture_number}")
            if narrator:
                parts.append(f"Narrator: {narrator}")
            if topic:
                parts.append(f"Emne: {topic}")
            parts.append(f"Type: {type_label}")
            if text_label:
                parts.append(f"Tekst: {text_label}")
            parts.append(f"Vigtigt: {'ja' if important else 'nej'}")
            parts.append(f"Format: {format_label}")
            parts.append(f"Sprog: {language_label}")
        description = " · ".join(part for part in parts if part)
        meta["description"] = description

    explicit_default = feed_config.get("default_explicit", False)
    duration = meta.get("duration")

    return {
        "guid": meta.get("guid") or file_entry["id"],
        "title": meta.get("title") or base_title,
        "description": meta.get("description") or meta.get("summary") or base_title,
        "link": meta.get("link") or feed_config.get("link"),
        "published_at": published_at,
        "pubDate": format_rfc2822(published_at),
        "mimeType": file_entry.get("mimeType", "audio/mpeg"),
        "size": file_entry.get("size"),
        "duration": duration,
        "explicit": str(meta.get("explicit", explicit_default)).lower(),
        "image": meta.get("image") or feed_config.get("image"),
        "audio_url": public_link_template.format(file_id=file_entry["id"], file_name=file_entry["name"]),
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

    _set("title", feed_config.get("title"))
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
        if feed_config.get("title"):
            ET.SubElement(standard_image, "title").text = feed_config["title"]
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

    new_items = list(sorted(episodes, key=lambda item: item["published_at"], reverse=True))
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
        help="Validate permissions without modifying Google Drive permissions",
    )
    args = parser.parse_args()

    config = load_json(args.config)
    feed_cfg = config.get("feed", {})
    overrides_path = args.metadata or (Path(config.get("episode_metadata", "")) if config.get("episode_metadata") else None)
    overrides = load_json(overrides_path) if overrides_path and overrides_path.exists() else {}

    service_account_path = Path(config["service_account_file"])
    drive_service = build_drive_service(service_account_path)
    folder_id = config["drive_folder_id"]
    public_template = config.get(
        "public_link_template", "https://drive.google.com/uc?export=download&id={file_id}"
    )
    shared_drive_id = config.get("shared_drive_id") or None
    supports_all_drives = bool(config.get("include_items_from_all_drives", shared_drive_id is not None))
    skip_permission_updates = bool(config.get("skip_permission_updates", False))
    allowed_mime_types = config.get("allowed_mime_types")
    if isinstance(allowed_mime_types, str):
        allowed_mime_types = [allowed_mime_types]
    filters = parse_filters(config.get("filters"))

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

    drive_files = list_audio_files(
        drive_service,
        folder_id,
        drive_id=shared_drive_id,
        supports_all_drives=supports_all_drives,
        mime_type_filters=allowed_mime_types,
    )

    episodes: List[Dict[str, Any]] = []
    folder_metadata_cache: Dict[str, Dict[str, Any]] = {}
    folder_path_cache: Dict[str, List[str]] = {}
    for drive_file in drive_files:
        parents = drive_file.get("parents") or []
        folder_names: List[str] = []
        if parents:
            folder_names = build_folder_path(
                drive_service,
                parents[0],
                folder_metadata_cache,
                folder_path_cache,
                root_folder_id=folder_id,
                supports_all_drives=supports_all_drives,
            )
        if not matches_filters(drive_file, folder_names, filters):
            continue

        permission_added = ensure_public_permission(
            drive_service,
            drive_file["id"],
            dry_run=args.dry_run,
            supports_all_drives=supports_all_drives,
            skip_permission_updates=skip_permission_updates,
        )
        if permission_added:
            print(f"Enabled link sharing for {drive_file['name']} ({drive_file['id']})")

        auto_meta = auto_spec.metadata_for(drive_file, folder_names) if auto_spec else None
        episodes.append(
            build_episode_entry(
                drive_file,
                feed_cfg,
                overrides,
                public_link_template=public_template,
                auto_meta=auto_meta,
                folder_names=folder_names,
                doc_marked_titles=doc_marked_titles,
            )
        )

    if not episodes:
        raise SystemExit("No audio files found in the configured Google Drive folder.")

    last_build = max(item["published_at"] for item in episodes)
    feed_document = build_feed_document(episodes, feed_cfg, last_build)
    output_path = Path(config["output_feed"])
    save_feed(feed_document, output_path)
    print(f"Feed written to {output_path}")


if __name__ == "__main__":
    main()
