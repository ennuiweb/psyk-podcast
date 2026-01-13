#!/usr/bin/env python3
"""Upload audio listed in a manifest TSV to Drive and write episode metadata."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import mimetypes
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive"]
DEFAULT_MAX_STEM = 140
SOURCE_HASH_LEN = 12


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))


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


def parse_manifest(path: Path) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            entry = {key.strip(): (value or "").strip() for key, value in row.items()}
            if not any(entry.values()):
                continue
            entries.append(entry)
    return entries


def normalize_published_at(value: str) -> str:
    if not value:
        return ""
    token = value.strip()
    if token.endswith("Z"):
        token = token[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(token)
    except ValueError:
        print(f"Warning: could not parse published_at '{value}'", file=sys.stderr)
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.isoformat()


def slugify(value: str) -> str:
    if not value:
        return "audio"
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_value = ascii_value.replace("'", "")
    ascii_value = re.sub(r"[^A-Za-z0-9]+", "_", ascii_value)
    ascii_value = re.sub(r"_+", "_", ascii_value).strip("_")
    return ascii_value or "audio"


def resolve_audio_path(downloads_dir: Path, file_name: str) -> Optional[Path]:
    if not file_name:
        return None
    direct = downloads_dir / file_name
    if direct.is_file():
        return direct
    stem, ext = (file_name.rsplit(".", 1) + [""])[:2]
    if ext:
        return None
    for suffix in (".mp3", ".m4a", ".wav"):
        candidate = downloads_dir / f"{file_name}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def build_drive_name(
    *,
    published_at: str,
    title: str,
    source_hash: str,
    extension: str,
    max_stem_len: int,
) -> str:
    date_prefix = ""
    if published_at:
        date_prefix = published_at.split("T", 1)[0]
    base = slugify(title)
    stem = f"{date_prefix}_{base}" if date_prefix else base
    suffix = f"_{source_hash[:6]}"
    available = max(max_stem_len - len(suffix), 1)
    if len(stem) > available:
        stem = stem[:available].rstrip("_")
    if not stem:
        stem = f"audio{suffix}"
    else:
        stem = f"{stem}{suffix}"
    ext = extension if extension.startswith(".") else f".{extension}"
    return f"{stem}{ext}"


def source_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:SOURCE_HASH_LEN]


def find_existing_by_hash(
    service,
    *,
    folder_id: str,
    src_hash: str,
    drive_id: Optional[str],
    supports_all_drives: bool,
) -> Optional[Dict[str, Any]]:
    query = (
        f"'{folder_id}' in parents and appProperties has {{ key='source_hash' and "
        f"value='{src_hash}' }} and trashed = false"
    )
    files = _drive_list(
        service,
        query=query,
        fields="files(id,name,appProperties)",
        drive_id=drive_id,
        supports_all_drives=supports_all_drives,
    )
    return files[0] if files else None


def upload_file(
    service,
    *,
    folder_id: str,
    source_path: Path,
    drive_name: str,
    mime_type: str,
    app_properties: Dict[str, str],
    supports_all_drives: bool,
) -> Dict[str, Any]:
    metadata = {
        "name": drive_name,
        "parents": [folder_id],
        "appProperties": app_properties,
    }
    media = MediaFileUpload(str(source_path), mimetype=mime_type, resumable=True)
    params = {"body": metadata, "media_body": media, "fields": "id,name"}
    if supports_all_drives:
        params["supportsAllDrives"] = True
    return service.files().create(**params).execute()


def merge_metadata(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged.get(key, {}), **value}
        else:
            merged[key] = value
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path, help="Path to manifest.tsv")
    parser.add_argument(
        "--downloads-dir",
        required=True,
        type=Path,
        help="Directory that contains the downloaded audio files",
    )
    parser.add_argument("--config", required=True, type=Path, help="Show config JSON")
    parser.add_argument(
        "--output-metadata",
        type=Path,
        help="Optional metadata output path (defaults to config episode_metadata)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List planned uploads without modifying Drive",
    )
    parser.add_argument(
        "--metadata-by-name",
        action="store_true",
        help="Write metadata keyed by Drive filename instead of Drive file ID",
    )
    parser.add_argument(
        "--max-stem-length",
        type=int,
        default=DEFAULT_MAX_STEM,
        help="Maximum length of the generated file name stem",
    )
    args = parser.parse_args()

    config = load_json(args.config)
    metadata_path = args.output_metadata or Path(config.get("episode_metadata", ""))
    if not metadata_path:
        raise SystemExit("Missing episode_metadata path; pass --output-metadata or set in config.")
    if not metadata_path.is_absolute():
        metadata_path = args.config.parent / metadata_path

    service_account_path = Path(config["service_account_file"])
    if not service_account_path.is_absolute():
        service_account_path = args.config.parent / service_account_path
    if not service_account_path.exists():
        raise SystemExit(f"Service account file not found: {service_account_path}")

    drive_folder_id = str(config.get("drive_folder_id") or "").strip()
    if not drive_folder_id or drive_folder_id == "__DRIVE_FOLDER_ID__":
        raise SystemExit("Drive folder ID not configured in the show config.")

    shared_drive_id = config.get("shared_drive_id") or None
    supports_all_drives = bool(config.get("include_items_from_all_drives", shared_drive_id is not None))

    manifest_entries = parse_manifest(args.manifest)
    if not manifest_entries:
        raise SystemExit("Manifest is empty or could not be parsed.")

    drive_service = build_drive_service(service_account_path)

    existing_metadata: Dict[str, Any] = {}
    if metadata_path.exists():
        existing_metadata = load_json(metadata_path)

    by_id_updates: Dict[str, Any] = {}
    by_name_updates: Dict[str, Any] = {}
    seen_hashes: set[str] = set()
    uploaded = 0
    reused = 0
    skipped = 0

    for entry in manifest_entries:
        title = entry.get("title", "").strip()
        src = entry.get("src", "").strip()
        file_name = entry.get("filename", "").strip()
        raw_date = entry.get("date", "").strip()

        if not file_name or not src:
            skipped += 1
            continue

        src_hash = source_hash(src)
        if src_hash in seen_hashes:
            continue
        seen_hashes.add(src_hash)

        source_path = resolve_audio_path(args.downloads_dir, file_name)
        if not source_path:
            print(f"Warning: file not found for manifest entry: {file_name}", file=sys.stderr)
            skipped += 1
            continue

        published_at = normalize_published_at(raw_date)
        extension = source_path.suffix or ".mp3"
        drive_name = build_drive_name(
            published_at=published_at,
            title=title or source_path.stem,
            source_hash=src_hash,
            extension=extension,
            max_stem_len=args.max_stem_length,
        )

        existing = find_existing_by_hash(
            drive_service,
            folder_id=drive_folder_id,
            src_hash=src_hash,
            drive_id=shared_drive_id,
            supports_all_drives=supports_all_drives,
        )

        file_id: Optional[str] = None
        final_name = drive_name
        if existing:
            file_id = existing.get("id")
            final_name = existing.get("name") or drive_name
            reused += 1
        elif args.dry_run:
            print(f"Dry run: would upload {source_path.name} as {drive_name}")
        else:
            mime_type = mimetypes.guess_type(source_path.name)[0] or "audio/mpeg"
            app_properties = {
                "source_hash": src_hash,
                "source_date": published_at,
                "source_title": (title or source_path.stem)[:120],
            }
            created = upload_file(
                drive_service,
                folder_id=drive_folder_id,
                source_path=source_path,
                drive_name=drive_name,
                mime_type=mime_type,
                app_properties=app_properties,
                supports_all_drives=supports_all_drives,
            )
            file_id = created.get("id")
            final_name = created.get("name") or drive_name
            uploaded += 1

        meta = {
            "title": title or source_path.stem,
            "published_at": published_at,
            "link": src,
            "guid": src,
        }

        if args.metadata_by_name or (args.dry_run and not file_id):
            by_name_updates[final_name] = meta
        elif file_id:
            by_id_updates[file_id] = meta
        else:
            skipped += 1

    merged = existing_metadata or {}
    updates: Dict[str, Any] = {}
    if by_id_updates:
        updates["by_id"] = by_id_updates
    if by_name_updates:
        updates["by_name"] = by_name_updates
    if updates:
        merged = merge_metadata(merged, updates)
        save_json(metadata_path, merged)

    print(
        f"Done. Uploaded: {uploaded}, reused: {reused}, skipped: {skipped}, "
        f"metadata entries: {len(by_id_updates) + len(by_name_updates)}"
    )


if __name__ == "__main__":
    main()
