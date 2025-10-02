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


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


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


def format_target_name(original: str, extension: str) -> str:
    base = original.rsplit(".", 1)[0]
    return f"{base}.{extension.lstrip('.')}"


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
        "extra_args": settings.get("extra_ffmpeg_args", []),
    }


def write_github_output(path: Optional[Path], needs_transcode: bool) -> None:
    """Append the probe result to a GitHub Actions output file."""

    if not path:
        return
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"needs_transcode={'true' if needs_transcode else 'false'}\n")
    except OSError as exc:  # pragma: no cover - logging best effort only
        print(f"Failed to write GitHub output: {exc}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="Path to JSON config file")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Skip transcoding and only report whether matching media exists",
    )
    parser.add_argument(
        "--github-output",
        type=Path,
        help="Append needs_transcode flag to the provided GitHub Actions output file",
    )
    args = parser.parse_args()

    config = load_json(args.config)
    try:
        transcode_cfg = parse_transcode_config(config)
    except SystemExit:
        if args.check_only:
            write_github_output(args.github_output, False)
            print("Transcode settings disabled; skipping Drive scan.")
            return
        raise

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

    needs_transcode = bool(source_files)
    write_github_output(args.github_output, needs_transcode)

    if not needs_transcode:
        print("No matching media found; nothing to transcode.")
        return

    if args.check_only:
        print(f"Found {len(source_files)} matching media file(s); transcode required.")
        return

    failures = 0
    for video in source_files:
        video_id = video["id"]
        video_name = video["name"]

        parents = video.get("parents") or []
        if not parents:
            print(f"Skipping {video_name}: no parent folder information.")
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

                print(f"Replacing Drive content with {target_name}…")
                media = MediaFileUpload(
                    str(audio_path), mimetype=transcode_cfg["target_mime_type"], resumable=True
                )
                update_body: Dict[str, Any] = {
                    "name": target_name,
                    "mimeType": transcode_cfg["target_mime_type"],
                    "appProperties": {SOURCE_MARKER: "true"},
                }
                params: Dict[str, Any] = {
                    "fileId": video_id,
                    "body": update_body,
                    "media_body": media,
                    "fields": "id,mimeType,name",
                }
                if supports_all_drives:
                    params["supportsAllDrives"] = True
                drive_service.files().update(**params).execute()

                print(f"Completed {video_name} -> {target_name} in-place.")

            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"Failed to transcode {video_name}: {exc}", file=sys.stderr)

    if failures:
        raise SystemExit(f"Encountered {failures} transcode failure(s).")


if __name__ == "__main__":
    main()
