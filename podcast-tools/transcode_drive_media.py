#!/usr/bin/env python3
"""Transcode Google Drive video files to audio and remove the originals."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive"]
SOURCE_MARKER = "psyk_video_transcoded"
AUDIO_SOURCE_PROPERTY = "psyk_source_video_id"


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_drive_service(credentials_path: Path):
    credentials = service_account.Credentials.from_service_account_file(
        str(credentials_path), scopes=SCOPES
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def ensure_public_permission(
    service,
    file_id: str,
    *,
    supports_all_drives: bool = False,
) -> None:
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
            return

    create_params: Dict[str, Any] = {
        "fileId": file_id,
        "body": {"type": "anyone", "role": "reader", "allowFileDiscovery": False},
        "fields": "id",
    }
    if supports_all_drives:
        create_params["supportsAllDrives"] = True
    service.permissions().create(**create_params).execute()


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
    terms = [term for term in (filters or ["video/"]) if term]
    clauses: List[str] = []
    for term in terms:
        sanitized = term.replace("'", "\\'")
        if term.endswith("/"):
            clauses.append(f"mimeType contains '{sanitized}'")
        else:
            clauses.append(f"mimeType = '{sanitized}'")
    if not clauses:
        clauses.append("mimeType contains 'video/'")
    return "(" + " or ".join(clauses) + ")"


def list_media_files(
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
    seen: set[str] = set()
    file_fields = (
        "nextPageToken, files(id,name,mimeType,size,parents,appProperties,modifiedTime,createdTime)"
    )
    folder_fields = "nextPageToken, files(id,name)"
    mime_clause = _build_mime_query(mime_type_filters)

    while pending:
        current_folder = pending.pop(0)
        if current_folder in seen:
            continue
        seen.add(current_folder)

        query = f"'{current_folder}' in parents and {mime_clause} and trashed = false"
        files.extend(
            _drive_list(
                service,
                query=query,
                fields=file_fields,
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


def download_drive_file(service, file_id: str, destination: Path, *, supports_all_drives: bool) -> None:
    request = service.files().get_media(fileId=file_id, supportsAllDrives=supports_all_drives)
    with destination.open("wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()


def upload_audio_file(
    service,
    source_path: Path,
    *,
    name: str,
    parent_id: str,
    mime_type: str,
    supports_all_drives: bool,
    source_video_id: str,
) -> str:
    metadata: Dict[str, Any] = {
        "name": name,
        "parents": [parent_id],
        "mimeType": mime_type,
        "appProperties": {AUDIO_SOURCE_PROPERTY: source_video_id},
    }
    media = MediaFileUpload(str(source_path), mimetype=mime_type, resumable=True)
    params: Dict[str, Any] = {"body": metadata, "media_body": media, "fields": "id"}
    if supports_all_drives:
        params["supportsAllDrives"] = True
    created = service.files().create(**params).execute()
    return created["id"]


def format_target_name(original: str, extension: str) -> str:
    base = original.rsplit(".", 1)[0]
    return f"{base}.{extension.lstrip('.')}"


def existing_audio_for_video(
    service,
    *,
    folder_id: str,
    video_id: str,
    drive_id: Optional[str],
    supports_all_drives: bool,
) -> Optional[Dict[str, Any]]:
    escaped = video_id.replace("'", "\\'")
    query = (
        f"'{folder_id}' in parents and appProperties has "
        f"{{ key='{AUDIO_SOURCE_PROPERTY}' and value='{escaped}' }} and trashed = false"
    )
    fields = "nextPageToken, files(id,name,mimeType,parents)"
    matches = _drive_list(
        service,
        query=query,
        fields=fields,
        drive_id=drive_id,
        supports_all_drives=supports_all_drives,
    )
    return matches[0] if matches else None


def run_ffmpeg(
    source: Path,
    destination: Path,
    *,
    codec: str,
    bitrate: str,
    extra_args: Optional[List[str]] = None,
) -> None:
    command = [
        os.environ.get("FFMPEG_BIN", "ffmpeg"),
        "-y",
        "-i",
        str(source),
        "-vn",
        "-acodec",
        codec,
        "-b:a",
        bitrate,
    ]
    if extra_args:
        command.extend(extra_args)
    command.append(str(destination))
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode != 0:
        sys.stderr.write(result.stderr.decode("utf-8", errors="ignore"))
        raise RuntimeError(f"ffmpeg failed with exit code {result.returncode}")


def delete_drive_file(service, file_id: str, *, supports_all_drives: bool) -> None:
    params: Dict[str, Any] = {"fileId": file_id}
    if supports_all_drives:
        params["supportsAllDrives"] = True
    service.files().delete(**params).execute()


def update_video_marker(service, file_id: str, *, supports_all_drives: bool) -> None:
    params: Dict[str, Any] = {
        "fileId": file_id,
        "body": {"appProperties": {SOURCE_MARKER: "true"}},
        "fields": "id",
    }
    if supports_all_drives:
        params["supportsAllDrives"] = True
    service.files().update(**params).execute()


def parse_transcode_config(config: Dict[str, Any]) -> Dict[str, Any]:
    settings = config.get("transcode") or {}
    if not settings or not settings.get("enabled", True):
        raise SystemExit("Transcode settings missing or disabled in config.")
    return {
        "source_mime_types": settings.get("source_mime_types", ["video/"]),
        "target_extension": settings.get("target_extension", "mp3"),
        "target_mime_type": settings.get("target_mime_type", "audio/mpeg"),
        "codec": settings.get("codec", "libmp3lame"),
        "bitrate": settings.get("bitrate", "160k"),
        "delete_source": settings.get("delete_source", True),
        "extra_args": settings.get("extra_ffmpeg_args", []),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="Path to JSON config file")
    args = parser.parse_args()

    config = load_json(args.config)
    transcode_cfg = parse_transcode_config(config)

    service_account_path = Path(config["service_account_file"])
    drive_service = build_drive_service(service_account_path)
    folder_id = config["drive_folder_id"]
    shared_drive_id = config.get("shared_drive_id") or None
    supports_all_drives = bool(config.get("include_items_from_all_drives", shared_drive_id is not None))
    include_subfolders = bool(config.get("include_subfolders", False))

    print("Scanning Drive for source media…")
    source_files = list_media_files(
        drive_service,
        folder_id,
        drive_id=shared_drive_id,
        supports_all_drives=supports_all_drives,
        include_subfolders=include_subfolders,
        mime_type_filters=transcode_cfg["source_mime_types"],
    )

    if not source_files:
        print("No matching media found; nothing to transcode.")
        return

    failures = 0
    for video in source_files:
        video_id = video["id"]
        video_name = video["name"]
        if video.get("appProperties", {}).get(SOURCE_MARKER) == "true":
            print(f"Skipping {video_name}: already marked transcoded.")
            continue

        parents = video.get("parents") or []
        if not parents:
            print(f"Skipping {video_name}: no parent folder information.")
            continue
        parent_id = parents[0]

        existing_audio = existing_audio_for_video(
            drive_service,
            folder_id=parent_id,
            video_id=video_id,
            drive_id=shared_drive_id,
            supports_all_drives=supports_all_drives,
        )
        if existing_audio:
            print(f"Audio already exists for {video_name} (file {existing_audio['id']}); removing source video.")
            if transcode_cfg["delete_source"]:
                delete_drive_file(drive_service, video_id, supports_all_drives=supports_all_drives)
            continue

        target_name = format_target_name(video_name, transcode_cfg["target_extension"])

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            video_path = tmpdir_path / video_name
            audio_path = tmpdir_path / target_name

            try:
                print(f"Downloading {video_name} ({video_id})…")
                download_drive_file(
                    drive_service,
                    video_id,
                    video_path,
                    supports_all_drives=supports_all_drives,
                )

                print(f"Transcoding {video_name} -> {target_name}…")
                run_ffmpeg(
                    video_path,
                    audio_path,
                    codec=transcode_cfg["codec"],
                    bitrate=transcode_cfg["bitrate"],
                    extra_args=transcode_cfg["extra_args"],
                )

                print(f"Uploading {target_name} to Drive…")
                audio_id = upload_audio_file(
                    drive_service,
                    audio_path,
                    name=target_name,
                    parent_id=parent_id,
                    mime_type=transcode_cfg["target_mime_type"],
                    supports_all_drives=supports_all_drives,
                    source_video_id=video_id,
                )

                ensure_public_permission(
                    drive_service,
                    audio_id,
                    supports_all_drives=supports_all_drives,
                )

                update_video_marker(
                    drive_service,
                    video_id,
                    supports_all_drives=supports_all_drives,
                )

                if transcode_cfg["delete_source"]:
                    print(f"Deleting original video {video_name}…")
                    delete_drive_file(
                        drive_service,
                        video_id,
                        supports_all_drives=supports_all_drives,
                    )

                print(f"Completed {video_name} -> {target_name} (audio id {audio_id}).")

            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"Failed to transcode {video_name}: {exc}", file=sys.stderr)

    if failures:
        raise SystemExit(f"Encountered {failures} transcode failure(s).")


if __name__ == "__main__":
    main()
