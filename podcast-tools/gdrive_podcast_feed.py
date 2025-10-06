#!/usr/bin/env python3
"""Generate a podcast RSS feed from audio files stored in a Google Drive folder."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/drive"]
ATOM_NS = "http://www.w3.org/2005/Atom"
ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"


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
        "nextPageToken, files(id,name,mimeType,size,modifiedTime,createdTime,md5Checksum,parents)"
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

        tz_name = spec.get("timezone", "UTC")
        try:
            self.timezone = ZoneInfo(tz_name)
        except Exception as exc:  # pragma: no cover - invalid timezone
            raise ValueError(f"Invalid timezone '{tz_name}' in auto spec ({source})") from exc

        default_release = spec.get("default_release", {}) or {}
        self.default_weekday = int(default_release.get("weekday", 1))
        self.default_time = default_release.get("time", "08:00")

        self.rules: List[Dict[str, Any]] = []
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

            increment = int(entry.get("increment_minutes", spec.get("increment_minutes", 5) or 5))

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

        self._allocations: Dict[Tuple[int, Tuple[str, ...]], int] = {}

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
                meta: Dict[str, Any] = {"published_at": scheduled.isoformat()}
                if rule.get("course_week") is not None:
                    meta["course_week"] = rule["course_week"]
                if rule.get("topic"):
                    topic = str(rule["topic"])
                    summary = f"Topic of the week: {topic}"
                    voice = self._extract_voice(file_entry.get("name"))
                    if voice:
                        summary = f"{summary}. Read by {voice}"
                    meta.setdefault("summary", summary)
                return meta
        return None

    @staticmethod
    def _matches(tokens: List[str], candidates: List[str]) -> bool:
        for token in tokens:
            if not token:
                continue
            lower_token = token.lower()
            for candidate in candidates:
                if lower_token in candidate:
                    return True
        return False

    def _allocate_datetime(self, rule: Dict[str, Any], folder_names: List[str]) -> dt.datetime:
        key = (rule["index"], tuple(folder_names))
        occurrence = self._allocations.get(key, 0)
        self._allocations[key] = occurrence + 1
        if occurrence == 0 or rule["increment_minutes"] == 0:
            return rule["base_datetime"]
        return rule["base_datetime"] + dt.timedelta(minutes=occurrence * rule["increment_minutes"])

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


def format_week_range(published_at: Optional[dt.datetime]) -> Optional[str]:
    if not published_at:
        return None
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=dt.timezone.utc)
    week_start = published_at - dt.timedelta(days=published_at.weekday())
    week_end = week_start + dt.timedelta(days=6)
    return f"{week_start.date():%d/%m} - {week_end.date():%d/%m}"


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


def build_episode_entry(
    file_entry: Dict[str, Any],
    feed_config: Dict[str, Any],
    overrides: Dict[str, Any],
    public_link_template: str,
    auto_meta: Optional[Dict[str, Any]] = None,
    folder_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    meta: Dict[str, Any] = {}
    if auto_meta:
        meta.update(auto_meta)
    manual_meta = item_metadata(overrides, file_entry) or {}
    meta.update(manual_meta)
    base_title = file_entry["name"].rsplit(".", 1)[0]
    pubdate_source = meta.get("published_at") or file_entry.get("modifiedTime")
    if not pubdate_source:
        raise ValueError(
            f"Missing publish timestamp for Drive file '{file_entry.get('id')}'"
        )
    published_at = parse_datetime(pubdate_source)
    if not meta.get("title"):
        week_label = derive_week_label(folder_names or [], meta.get("course_week"))
        if week_label and not base_title.lower().startswith("week"):
            week_dates = format_week_range(published_at)
            if week_dates:
                week_label = f"{week_label} ({week_dates})"
            meta["title"] = f"{week_label}: {base_title}"

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
        permission_added = ensure_public_permission(
            drive_service,
            drive_file["id"],
            dry_run=args.dry_run,
            supports_all_drives=supports_all_drives,
            skip_permission_updates=skip_permission_updates,
        )
        if permission_added:
            print(f"Enabled link sharing for {drive_file['name']} ({drive_file['id']})")

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

        auto_meta = auto_spec.metadata_for(drive_file, folder_names) if auto_spec else None
        episodes.append(
            build_episode_entry(
                drive_file,
                feed_cfg,
                overrides,
                public_link_template=public_template,
                auto_meta=auto_meta,
                folder_names=folder_names,
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
