#!/usr/bin/env python3
"""Generate a podcast RSS feed from audio files stored in a Google Drive folder."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

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
    include_subfolders: bool = False,
    mime_type_filters: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    files: List[Dict[str, Any]] = []
    pending: List[str] = [folder_id]
    seen: Set[str] = set()
    audio_fields = (
        "nextPageToken, files(id,name,mimeType,size,modifiedTime,createdTime," "md5Checksum)"
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

        if not include_subfolders:
            continue

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


def build_episode_entry(
    file_entry: Dict[str, Any],
    feed_config: Dict[str, Any],
    overrides: Dict[str, Any],
    public_link_template: str,
) -> Dict[str, Any]:
    meta = item_metadata(overrides, file_entry) or {}
    base_title = file_entry["name"].rsplit(".", 1)[0]
    pubdate_source = meta.get("published_at") or file_entry.get("modifiedTime")
    published_at = parse_datetime(pubdate_source)

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
        ET.SubElement(channel, "itunes:image", attrib={"href": feed_config["image"]})

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
    include_subfolders = bool(config.get("include_subfolders", False))
    skip_permission_updates = bool(config.get("skip_permission_updates", False))
    allowed_mime_types = config.get("allowed_mime_types")
    if isinstance(allowed_mime_types, str):
        allowed_mime_types = [allowed_mime_types]

    drive_files = list_audio_files(
        drive_service,
        folder_id,
        drive_id=shared_drive_id,
        supports_all_drives=supports_all_drives,
        include_subfolders=include_subfolders,
        mime_type_filters=allowed_mime_types,
    )

    episodes: List[Dict[str, Any]] = []
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
        episodes.append(
            build_episode_entry(
                drive_file,
                feed_cfg,
                overrides,
                public_link_template=public_template,
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
