#!/usr/bin/env python3
"""Migrate a Drive-backed show's media catalog to R2 and emit a manifest."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import socket
import ssl
import sys
import tempfile
import time
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qs, quote, urlparse

import boto3
from boto3.exceptions import S3UploadFailedError
from boto3.s3.transfer import TransferConfig
from botocore.exceptions import ClientError

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
PODCAST_TOOLS_DIR = REPO_ROOT / "podcast-tools"
if str(PODCAST_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(PODCAST_TOOLS_DIR))

from storage_backends import DriveStorageBackend, build_drive_service  # noqa: E402

try:
    from googleapiclient.http import MediaIoBaseDownload
except ModuleNotFoundError as exc:  # pragma: no cover - environment guard
    raise SystemExit(
        "Missing Google API dependencies. Install requirements before running this script."
    ) from exc

RSS_DRIVE_ID_RE = re.compile(r"/d/([A-Za-z0-9_-]+)")
RETRYABLE_HTTP_STATUS_CODES = {408, 429, 500, 502, 503, 504}
RETRYABLE_OS_ERROR_NUMBERS = {51, 54, 60, 65}
SINGLE_STREAM_TRANSFER_CONFIG = TransferConfig(max_concurrency=1, use_threads=False)


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_existing_manifest_index(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    payload = load_json(path)
    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        return {}
    manifest_index: Dict[str, Dict[str, Any]] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        object_key = str(item.get("object_key") or "").strip()
        if object_key:
            manifest_index[object_key] = item
    return manifest_index


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Path to the show config JSON.")
    parser.add_argument(
        "--source-config",
        help="Optional source Drive config JSON. Defaults to --config when omitted.",
    )
    parser.add_argument("--manifest-path", help="Output path for the generated R2 manifest.")
    parser.add_argument("--bucket", required=True, help="R2 bucket name.")
    parser.add_argument("--endpoint", required=True, help="R2 S3 endpoint URL.")
    parser.add_argument("--prefix", required=True, help="Object-key prefix, e.g. shows/personal.")
    parser.add_argument("--public-base-url", required=True, help="Public base URL for enclosure links.")
    parser.add_argument("--region", default="auto")
    parser.add_argument("--access-key-env", default="R2_ACCESS_KEY_ID")
    parser.add_argument("--secret-key-env", default="R2_SECRET_ACCESS_KEY")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force-upload", action="store_true")
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--retry-delay-seconds", type=float, default=2.0)
    return parser.parse_args(argv)


def resolve_inventory_path(config: Dict[str, Any], config_path: Path) -> Path:
    raw = str(config.get("output_inventory") or "").strip()
    if raw:
        path = Path(raw)
    else:
        output_feed = Path(str(config.get("output_feed") or "")).expanduser()
        if output_feed.parent.name == "feeds":
            path = output_feed.parent.parent / "episode_inventory.json"
        else:
            path = output_feed.with_name("episode_inventory.json")
    return resolve_repo_path(path, config_path)


def resolve_feed_path(config: Dict[str, Any], config_path: Path) -> Path:
    return resolve_repo_path(Path(str(config.get("output_feed") or "")), config_path)


def resolve_manifest_path(config: Dict[str, Any], config_path: Path, override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    storage = config.get("storage")
    if isinstance(storage, dict) and str(storage.get("manifest_file") or "").strip():
        return resolve_repo_path(Path(str(storage["manifest_file"])), config_path)
    show_dir = config_path.parent
    return (show_dir / "media_manifest.r2.json").resolve()


def resolve_repo_path(path: Path, config_path: Path) -> Path:
    expanded = path.expanduser()
    if expanded.is_absolute():
        return expanded.resolve()
    repo_candidate = (REPO_ROOT / expanded).resolve()
    if str(expanded).startswith("shows/") or repo_candidate.exists():
        return repo_candidate
    return (config_path.parent / expanded).resolve()


def normalize_prefix(value: str) -> str:
    return "/".join(part for part in PurePosixPath(str(value).strip().strip("/")).parts if part and part != "/")


def build_r2_client(*, endpoint: str, region: str, access_key_env: str, secret_key_env: str):
    access_key_id = str(os.environ.get(access_key_env) or "").strip()
    secret_access_key = str(os.environ.get(secret_key_env) or "").strip()
    if not access_key_id or not secret_access_key:
        raise SystemExit(
            f"Missing R2 credentials. Set {access_key_env} and {secret_key_env} in the environment."
        )
    session = boto3.session.Session(
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
    )
    return session.client("s3", endpoint_url=endpoint, region_name=region)


def extract_drive_file_id(url: str) -> Optional[str]:
    if not url:
        return None
    parsed = urlparse(url)
    query_id = parse_qs(parsed.query).get("id")
    if query_id:
        return str(query_id[0]).strip() or None
    match = RSS_DRIVE_ID_RE.search(url)
    if match:
        return match.group(1).strip()
    return None


def load_guid_maps(*, inventory_path: Path, feed_path: Path) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    if inventory_path.exists():
        payload = load_json(inventory_path)
        episodes = payload.get("episodes") if isinstance(payload, dict) else None
        if isinstance(episodes, list):
            for episode in episodes:
                if not isinstance(episode, dict):
                    continue
                guid = str(episode.get("guid") or episode.get("episode_key") or "").strip()
                if not guid:
                    continue
                for key_name in (
                    "source_drive_file_id",
                    "source_storage_key",
                    "source_path",
                    "source_name",
                    "title",
                ):
                    raw_key = str(episode.get(key_name) or "").strip()
                    if raw_key and raw_key not in mapping:
                        mapping[raw_key] = guid
    if feed_path.exists():
        import xml.etree.ElementTree as ET

        root = ET.parse(feed_path).getroot()
        channel = root.find("channel")
        if channel is not None:
            for item in channel.findall("item"):
                guid = str(item.findtext("guid") or "").strip()
                title = str(item.findtext("title") or "").strip()
                enclosure = item.find("enclosure")
                drive_file_id = extract_drive_file_id(str(enclosure.attrib.get("url") if enclosure is not None else ""))
                if guid and drive_file_id and drive_file_id not in mapping:
                    mapping[drive_file_id] = guid
                if guid and title and title not in mapping:
                    mapping[title] = guid
    return mapping


def download_drive_file(service, file_id: str, destination: Path, *, supports_all_drives: bool) -> None:
    if destination.exists():
        destination.unlink()
    request = service.files().get_media(fileId=file_id, supportsAllDrives=supports_all_drives)
    with destination.open("wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def object_exists_with_size(client, *, bucket: str, object_key: str, size: int) -> bool:
    try:
        response = client.head_object(Bucket=bucket, Key=object_key)
    except ClientError as exc:
        status = int(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") or 0)
        error_code = str(exc.response.get("Error", {}).get("Code") or "").strip()
        if status == 404 or error_code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise
    return int(response.get("ContentLength") or -1) == int(size)


def upload_file(client, *, bucket: str, object_key: str, source: Path, mime_type: str) -> None:
    client.upload_file(
        str(source),
        bucket,
        object_key,
        Config=SINGLE_STREAM_TRANSFER_CONFIG,
        ExtraArgs={"ContentType": mime_type},
    )


def build_public_url(base_url: str, object_key: str) -> str:
    return f"{base_url.rstrip('/')}/{quote(object_key, safe='/:@')}"


def build_manifest_item(
    *,
    bucket: str,
    object_key: str,
    source_name: str,
    source_path: str,
    path_parts: Iterable[str],
    mime_type: str,
    size: int,
    sha256: str,
    published_at: str,
    public_url: str,
    stable_guid: str,
) -> Dict[str, Any]:
    return {
        "object_key": object_key,
        "source_name": source_name,
        "source_path": source_path,
        "path_parts": list(path_parts),
        "mime_type": mime_type,
        "size": size,
        "sha256": sha256,
        "artifact_type": "audio",
        "published_at": published_at,
        "bucket": bucket,
        "public_url": public_url,
        "stable_guid": stable_guid,
    }


def sort_manifest_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def key(item: Dict[str, Any]) -> tuple[str, str]:
        return (str(item.get("published_at") or ""), str(item.get("object_key") or ""))

    return sorted(items, key=key, reverse=True)


def resolve_stable_guid(file_entry: Dict[str, Any], guid_map: Dict[str, str]) -> str:
    candidates = (
        str(file_entry.get("id") or "").strip(),
        str(file_entry.get("name") or "").strip(),
    )
    for candidate in candidates:
        if candidate and candidate in guid_map:
            return guid_map[candidate]
    return str(file_entry.get("id") or "").strip()


def is_retryable_exception(exc: BaseException) -> bool:
    if isinstance(
        exc,
        (
            TimeoutError,
            ConnectionError,
            socket.timeout,
            ssl.SSLError,
        ),
    ):
        return True
    if isinstance(exc, S3UploadFailedError):
        message = str(exc)
        return "NoSuchUpload" in message or "timed out" in message.lower()
    if isinstance(exc, ClientError):
        status = int(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") or 0)
        error_code = str(exc.response.get("Error", {}).get("Code") or "").strip()
        return status in RETRYABLE_HTTP_STATUS_CODES or error_code in {
            "RequestTimeout",
            "SlowDown",
            "Throttling",
            "InternalError",
        }
    if isinstance(exc, OSError):
        return exc.errno in RETRYABLE_OS_ERROR_NUMBERS
    return False


def run_with_retries(
    action,
    *,
    label: str,
    max_attempts: int,
    initial_delay_seconds: float,
):
    delay = max(float(initial_delay_seconds), 0.0)
    for attempt in range(1, max_attempts + 1):
        try:
            return action()
        except Exception as exc:
            if attempt >= max_attempts or not is_retryable_exception(exc):
                raise
            print(
                f"Retrying {label} after {exc.__class__.__name__}: {exc} "
                f"(attempt {attempt + 1}/{max_attempts})",
                file=sys.stderr,
                flush=True,
            )
            if delay > 0:
                time.sleep(delay)
                delay *= 2


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    config_path = Path(args.config).expanduser().resolve()
    config = load_json(config_path)
    source_config_path = Path(args.source_config).expanduser().resolve() if args.source_config else config_path
    source_config = load_json(source_config_path)
    inventory_path = resolve_inventory_path(config, config_path)
    feed_path = resolve_feed_path(config, config_path)
    manifest_path = resolve_manifest_path(config, config_path, args.manifest_path)
    prefix = normalize_prefix(args.prefix)
    client = None
    if not args.dry_run:
        client = build_r2_client(
            endpoint=args.endpoint,
            region=args.region,
            access_key_env=args.access_key_env,
            secret_key_env=args.secret_key_env,
        )

    backend = DriveStorageBackend(source_config)
    files = run_with_retries(
        lambda: backend.list_media_files(
            mime_type_filters=source_config.get("allowed_mime_types") or config.get("allowed_mime_types") or ["audio/"]
        ),
        label="list-drive-files",
        max_attempts=args.max_attempts,
        initial_delay_seconds=args.retry_delay_seconds,
    )
    files.sort(key=lambda item: (str(item.get("createdTime") or ""), str(item.get("name") or "")))
    if args.limit:
        files = files[: max(int(args.limit), 0)]
    guid_map = load_guid_maps(inventory_path=inventory_path, feed_path=feed_path)
    existing_manifest_index = load_existing_manifest_index(manifest_path)

    manifest_items: List[Dict[str, Any]] = []
    uploaded_count = 0
    skipped_count = 0
    with tempfile.TemporaryDirectory(prefix="drive-show-r2-migrate-") as tmpdir:
        tmp_root = Path(tmpdir)
        for index, file_entry in enumerate(files, start=1):
            file_id = str(file_entry.get("id") or "").strip()
            name = str(file_entry.get("name") or "").strip()
            mime_type = str(file_entry.get("mimeType") or "audio/mpeg").strip()
            size = int(file_entry.get("size") or 0)
            folder_parts = backend.build_folder_path(file_entry)
            relative_parts = [part for part in folder_parts if part]
            source_path = "/".join([*relative_parts, name]) if relative_parts else name
            object_key = "/".join([part for part in (prefix, source_path) if part])
            published_at = str(file_entry.get("createdTime") or file_entry.get("modifiedTime") or "").strip()
            stable_guid = resolve_stable_guid(file_entry, guid_map)
            public_url = build_public_url(args.public_base_url, object_key)
            existing_manifest_item = existing_manifest_index.get(object_key) or {}

            print(f"[{index}/{len(files)}] {name} -> {object_key}", flush=True)
            if args.dry_run:
                manifest_items.append(
                    build_manifest_item(
                        bucket=args.bucket,
                        object_key=object_key,
                        source_name=name,
                        source_path=source_path,
                        path_parts=relative_parts,
                        mime_type=mime_type,
                        size=size,
                        sha256="",
                        published_at=published_at,
                        public_url=public_url,
                        stable_guid=stable_guid,
                    )
                )
                continue

            already_uploaded = False
            if not args.force_upload:
                already_uploaded = run_with_retries(
                    lambda: object_exists_with_size(
                        client,
                        bucket=args.bucket,
                        object_key=object_key,
                        size=size,
                    ),
                    label=f"head-object {object_key}",
                    max_attempts=args.max_attempts,
                    initial_delay_seconds=args.retry_delay_seconds,
                )

            if already_uploaded:
                skipped_count += 1
                sha256 = str(existing_manifest_item.get("sha256") or "").strip()
            else:
                tmp_file = tmp_root / file_id
                run_with_retries(
                    lambda: download_drive_file(
                        backend._service,  # noqa: SLF001 - service is already constructed and scoped to this script
                        file_id,
                        tmp_file,
                        supports_all_drives=backend._supports_all_drives,  # noqa: SLF001
                    ),
                    label=f"download {file_id}",
                    max_attempts=args.max_attempts,
                    initial_delay_seconds=args.retry_delay_seconds,
                )
                sha256 = sha256_file(tmp_file)
                run_with_retries(
                    lambda: upload_file(
                        client,
                        bucket=args.bucket,
                        object_key=object_key,
                        source=tmp_file,
                        mime_type=mime_type,
                    ),
                    label=f"upload {object_key}",
                    max_attempts=args.max_attempts,
                    initial_delay_seconds=args.retry_delay_seconds,
                )
                uploaded_count += 1

            manifest_items.append(
                build_manifest_item(
                    bucket=args.bucket,
                    object_key=object_key,
                    source_name=name,
                    source_path=source_path,
                    path_parts=relative_parts,
                    mime_type=mime_type,
                    size=size,
                    sha256=sha256,
                    published_at=published_at,
                    public_url=public_url,
                    stable_guid=stable_guid,
                )
            )

    manifest_payload = {
        "version": 1,
        "provider": "r2",
        "bucket": args.bucket,
        "prefix": prefix,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "items": sort_manifest_items(manifest_items),
    }
    if not args.dry_run:
        save_json(manifest_path, manifest_payload)

    print(
        json.dumps(
            {
                "dry_run": bool(args.dry_run),
                "file_count": len(files),
                "uploaded_count": uploaded_count,
                "skipped_existing_count": skipped_count,
                "manifest_path": str(manifest_path),
                "inventory_path": str(inventory_path),
                "feed_path": str(feed_path),
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
