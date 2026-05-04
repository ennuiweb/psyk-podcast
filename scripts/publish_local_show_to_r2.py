#!/usr/bin/env python3
"""Publish local audio files for an R2-backed show and refresh its manifest."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import mimetypes
import os
import socket
import ssl
import sys
import tempfile
import time
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote

import boto3
from boto3.exceptions import S3UploadFailedError
from boto3.s3.transfer import TransferConfig
from botocore.exceptions import ClientError

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
PODCAST_TOOLS_DIR = REPO_ROOT / "podcast-tools"
if str(PODCAST_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(PODCAST_TOOLS_DIR))

from transcode_drive_media import format_target_name, parse_transcode_config, run_ffmpeg  # noqa: E402

RETRYABLE_HTTP_STATUS_CODES = {408, 429, 500, 502, 503, 504}
RETRYABLE_OS_ERROR_NUMBERS = {51, 54, 60, 65}
SINGLE_STREAM_TRANSFER_CONFIG = TransferConfig(max_concurrency=1, use_threads=False)
SPECIAL_MIME_TYPES = {
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".mp4": "video/mp4",
    ".wav": "audio/x-wav",
}


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


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Path to the show config JSON.")
    parser.add_argument("--source-dir", required=True, help="Local directory containing publishable source audio.")
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
                if guid and title and title not in mapping:
                    mapping[title] = guid
    return mapping


def load_optional_transcode_config(config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    settings = config.get("transcode") or {}
    if not isinstance(settings, dict) or not settings or not settings.get("enabled", True):
        return None
    return parse_transcode_config(config)


def mime_type_matches_filters(mime_type: str, filters: Optional[Iterable[str]]) -> bool:
    normalized = str(mime_type or "").strip().casefold()
    if not normalized:
        return False
    rules = [str(rule).strip().casefold() for rule in (filters or []) if str(rule).strip()]
    if not rules:
        return False
    for rule in rules:
        if rule.endswith("/"):
            if normalized.startswith(rule):
                return True
        elif normalized == rule:
            return True
    return False


def guess_source_mime_type(path: Path) -> str:
    suffix = path.suffix.casefold()
    if suffix in SPECIAL_MIME_TYPES:
        return SPECIAL_MIME_TYPES[suffix]
    guessed, _ = mimetypes.guess_type(str(path))
    return str(guessed or "application/octet-stream")


def iter_local_source_files(
    *,
    source_dir: Path,
    allowed_mime_filters: Iterable[str],
    transcode_cfg: Optional[Dict[str, Any]],
) -> List[Path]:
    candidate_filters = list(allowed_mime_filters)
    if transcode_cfg:
        candidate_filters.extend(str(item) for item in transcode_cfg.get("source_mime_types") or [])
    files: List[Path] = []
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        mime_type = guess_source_mime_type(path)
        if not mime_type_matches_filters(mime_type, candidate_filters):
            continue
        files.append(path)
    return files


def build_output_media_plan(
    *,
    source_name: str,
    source_mime_type: str,
    folder_parts: Iterable[str],
    prefix: str,
    transcode_cfg: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    transcode_applied = bool(transcode_cfg) and mime_type_matches_filters(
        source_mime_type,
        transcode_cfg.get("source_mime_types"),
    )
    published_name = (
        format_target_name(source_name, str(transcode_cfg["target_extension"]))
        if transcode_applied and transcode_cfg is not None
        else source_name
    )
    path_parts = [part for part in folder_parts if part]
    published_path = "/".join([*path_parts, published_name]) if path_parts else published_name
    object_key = "/".join([part for part in (prefix, published_path) if part])
    return {
        "transcode_applied": transcode_applied,
        "published_name": published_name,
        "published_path": published_path,
        "path_parts": path_parts,
        "object_key": object_key,
        "published_mime_type": (
            str(transcode_cfg["target_mime_type"]).strip()
            if transcode_applied and transcode_cfg is not None
            else source_mime_type
        ),
    }


def prepare_artifact_file(
    *,
    source_file: Path,
    source_mime_type: str,
    tmp_root: Path,
    transcode_cfg: Optional[Dict[str, Any]],
) -> Path:
    if not transcode_cfg or not mime_type_matches_filters(source_mime_type, transcode_cfg.get("source_mime_types")):
        return source_file
    artifact_file = tmp_root / format_target_name(source_file.name, str(transcode_cfg["target_extension"]))
    run_ffmpeg(
        source_file,
        artifact_file,
        codec=str(transcode_cfg["codec"]),
        bitrate=str(transcode_cfg["bitrate"]),
        extra_args=list(transcode_cfg.get("extra_args") or []),
    )
    return artifact_file


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def head_object_size(client, *, bucket: str, object_key: str) -> Optional[int]:
    try:
        response = client.head_object(Bucket=bucket, Key=object_key)
    except ClientError as exc:
        status = int(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") or 0)
        error_code = str(exc.response.get("Error", {}).get("Code") or "").strip()
        if status == 404 or error_code in {"404", "NoSuchKey", "NotFound"}:
            return None
        raise
    return int(response.get("ContentLength") or 0)


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


def resolve_stable_guid(
    *,
    object_key: str,
    source_path: str,
    source_name: str,
    guid_map: Dict[str, str],
    existing_manifest_item: Dict[str, Any],
) -> str:
    existing = str(existing_manifest_item.get("stable_guid") or "").strip()
    if existing:
        return existing
    for candidate in (object_key, source_path, source_name):
        if candidate and candidate in guid_map:
            return guid_map[candidate]
    return object_key


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
        "source_storage_key": object_key,
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


def validate_manifest_items(items: Iterable[Dict[str, Any]]) -> None:
    missing_sha = [str(item.get("object_key") or "").strip() for item in items if not str(item.get("sha256") or "").strip()]
    if missing_sha:
        preview = ", ".join(missing_sha[:5])
        if len(missing_sha) > 5:
            preview = f"{preview}, ..."
        raise SystemExit(
            f"Generated manifest contains {len(missing_sha)} item(s) with blank sha256; aborting. "
            f"Examples: {preview}"
        )


def sort_manifest_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    def key(item: Dict[str, Any]) -> tuple[str, str]:
        return (str(item.get("published_at") or ""), str(item.get("object_key") or ""))

    return sorted(items, key=key, reverse=True)


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
    source_dir = Path(args.source_dir).expanduser().resolve()
    if not source_dir.exists() or not source_dir.is_dir():
        raise SystemExit(f"Local source directory not found or not a directory: {source_dir}")

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

    transcode_cfg = load_optional_transcode_config(config)
    files = iter_local_source_files(
        source_dir=source_dir,
        allowed_mime_filters=config.get("allowed_mime_types") or ["audio/"],
        transcode_cfg=transcode_cfg,
    )
    if args.limit:
        files = files[: max(int(args.limit), 0)]

    guid_map = load_guid_maps(inventory_path=inventory_path, feed_path=feed_path)
    existing_manifest_index = load_existing_manifest_index(manifest_path)
    manifest_items: List[Dict[str, Any]] = []
    uploaded_count = 0
    skipped_count = 0

    with tempfile.TemporaryDirectory(prefix="local-show-r2-publish-") as tmpdir:
        tmp_root = Path(tmpdir)
        for index, source_file in enumerate(files, start=1):
            relative_source = source_file.relative_to(source_dir)
            source_mime_type = guess_source_mime_type(source_file)
            media_plan = build_output_media_plan(
                source_name=source_file.name,
                source_mime_type=source_mime_type,
                folder_parts=relative_source.parent.parts,
                prefix=prefix,
                transcode_cfg=transcode_cfg,
            )
            relative_parts = list(media_plan["path_parts"])
            source_path = str(media_plan["published_path"])
            object_key = str(media_plan["object_key"])
            published_mime_type = str(media_plan["published_mime_type"])
            published_at = dt.datetime.fromtimestamp(source_file.stat().st_mtime, tz=dt.UTC).isoformat()
            existing_manifest_item = existing_manifest_index.get(object_key) or {}
            stable_guid = resolve_stable_guid(
                object_key=object_key,
                source_path=source_path,
                source_name=str(media_plan["published_name"]),
                guid_map=guid_map,
                existing_manifest_item=existing_manifest_item,
            )
            public_url = build_public_url(args.public_base_url, object_key)

            print(f"[{index}/{len(files)}] {relative_source.as_posix()} -> {object_key}", flush=True)

            artifact_file = prepare_artifact_file(
                source_file=source_file,
                source_mime_type=source_mime_type,
                tmp_root=tmp_root,
                transcode_cfg=transcode_cfg,
            )
            local_size = int(artifact_file.stat().st_size)

            if args.dry_run:
                manifest_items.append(
                    build_manifest_item(
                        bucket=args.bucket,
                        object_key=object_key,
                        source_name=str(media_plan["published_name"]),
                        source_path=source_path,
                        path_parts=relative_parts,
                        mime_type=published_mime_type,
                        size=local_size,
                        sha256="",
                        published_at=published_at,
                        public_url=public_url,
                        stable_guid=stable_guid,
                    )
                )
                continue

            already_uploaded = False
            remote_size: Optional[int] = None
            if not args.force_upload:
                remote_size = run_with_retries(
                    lambda: head_object_size(client, bucket=args.bucket, object_key=object_key),
                    label=f"head-object {object_key}",
                    max_attempts=args.max_attempts,
                    initial_delay_seconds=args.retry_delay_seconds,
                )
                expected_size_raw = existing_manifest_item.get("size")
                expected_size = int(expected_size_raw) if expected_size_raw not in (None, "", False) else local_size
                already_uploaded = remote_size is not None and int(remote_size) == int(expected_size)

            if already_uploaded:
                skipped_count += 1
                sha256 = str(existing_manifest_item.get("sha256") or "").strip()
                size = int(existing_manifest_item.get("size") or remote_size or local_size)
                if not sha256:
                    sha256 = sha256_file(artifact_file)
                    size = local_size
            else:
                size = local_size
                sha256 = sha256_file(artifact_file)
                run_with_retries(
                    lambda: upload_file(
                        client,
                        bucket=args.bucket,
                        object_key=object_key,
                        source=artifact_file,
                        mime_type=published_mime_type,
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
                    source_name=str(media_plan["published_name"]),
                    source_path=source_path,
                    path_parts=relative_parts,
                    mime_type=published_mime_type,
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
        validate_manifest_items(manifest_items)
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
