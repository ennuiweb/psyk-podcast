#!/usr/bin/env python3
"""Shared storage backends for podcast media inventory."""

from __future__ import annotations

import json
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence, Tuple
from urllib.parse import quote

try:
    import boto3
    from botocore.client import BaseClient
except ModuleNotFoundError:  # pragma: no cover - optional until R2 is enabled
    boto3 = None  # type: ignore[assignment]
    BaseClient = Any  # type: ignore[assignment]

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ModuleNotFoundError:  # pragma: no cover - optional for R2-only environments
    service_account = None  # type: ignore[assignment]
    build = None  # type: ignore[assignment]
    HttpError = None  # type: ignore[assignment]


DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]
GOOGLE_API_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
GOOGLE_API_RETRY_REASONS = {
    "internalError",
    "backendError",
    "rateLimitExceeded",
    "userRateLimitExceeded",
}


class StorageBackend(Protocol):
    provider: str

    def list_media_files(
        self,
        *,
        mime_type_filters: Optional[Iterable[str]] = None,
    ) -> List[Dict[str, Any]]: ...

    def build_folder_path(self, file_entry: Dict[str, Any]) -> List[str]: ...

    def ensure_public_access(self, file_entry: Dict[str, Any], *, dry_run: bool = False) -> bool: ...

    def build_public_url(
        self,
        file_entry: Dict[str, Any],
        *,
        public_link_template: Optional[str] = None,
    ) -> str: ...


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_storage_provider(config: Dict[str, Any]) -> str:
    storage_cfg = config.get("storage")
    if isinstance(storage_cfg, dict):
        provider = str(storage_cfg.get("provider") or "").strip().lower()
        if provider:
            return provider
    return "drive"


def build_storage_backend(config: Dict[str, Any]) -> StorageBackend:
    provider = resolve_storage_provider(config)
    if provider == "drive":
        return DriveStorageBackend(config)
    if provider == "r2":
        return R2StorageBackend(config)
    raise ValueError(f"Unsupported storage provider: {provider}")


def _resolve_relative_path(path_value: Any, *, config: Dict[str, Any]) -> Optional[Path]:
    raw_path = str(path_value or "").strip()
    if not raw_path:
        return None
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path

    candidates = [path]
    config_path_raw = str(config.get("__config_path__") or "").strip()
    if config_path_raw:
        config_path = Path(config_path_raw)
        candidates.insert(0, (config_path.parent / path).resolve())
    if raw_path.startswith("shows/"):
        candidates.append(path.resolve())

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return candidates[0]


def _normalize_posix_parts(value: Any) -> Tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(part).strip() for part in value if str(part).strip())
    text = str(value or "").strip().replace("\\", "/").strip("/")
    if not text:
        return ()
    return tuple(part for part in text.split("/") if part)


def _guess_mime_type(name: str, fallback: str = "application/octet-stream") -> str:
    guessed, _ = mimetypes.guess_type(name)
    return guessed or fallback


def _matches_mime_type(mime_type: str, filters: Optional[Iterable[str]]) -> bool:
    rules = [str(rule).strip() for rule in (filters or []) if str(rule).strip()]
    if not rules:
        return True
    normalized = mime_type.casefold()
    for rule in rules:
        candidate = rule.casefold()
        if candidate.endswith("/"):
            if normalized.startswith(candidate):
                return True
        elif normalized == candidate:
            return True
    return False


def _resolve_public_url_template(
    *,
    template: Optional[str],
    file_entry: Dict[str, Any],
    default_base_url: Optional[str] = None,
) -> str:
    existing_url = str(file_entry.get("public_url") or "").strip()
    if existing_url and not template:
        return existing_url

    storage_key = str(
        file_entry.get("source_storage_key")
        or file_entry.get("key")
        or file_entry.get("id")
        or ""
    ).strip()
    source_path = str(file_entry.get("source_path") or storage_key).strip()
    quoted_storage_key = quote(storage_key, safe="/:@")
    if template:
        return template.format(
            file_id=str(file_entry.get("id") or "").strip(),
            file_name=str(file_entry.get("name") or "").strip(),
            file_path=quoted_storage_key,
            source_path=quote(source_path, safe="/:@"),
            raw_file_path=source_path,
            raw_storage_key=storage_key,
            storage_key=storage_key,
        )
    if existing_url:
        return existing_url
    if default_base_url:
        base = default_base_url.rstrip("/")
        if storage_key:
            return f"{base}/{quoted_storage_key}"
        return base
    raise ValueError(
        "Missing public media URL configuration. "
        "Set public_link_template, storage.public_base_url, or public_url on manifest items."
    )


@dataclass
class DriveStorageBackend:
    config: Dict[str, Any]
    provider: str = "drive"

    def __post_init__(self) -> None:
        service_account_path = Path(str(self.config["service_account_file"])).expanduser()
        self._service = build_drive_service(service_account_path)
        self._folder_id = str(self.config["drive_folder_id"])
        self._shared_drive_id = self.config.get("shared_drive_id") or None
        self._supports_all_drives = bool(
            self.config.get("include_items_from_all_drives", self._shared_drive_id is not None)
        )
        self._skip_permission_updates = bool(self.config.get("skip_permission_updates", False))
        self._folder_metadata_cache: Dict[str, Dict[str, Any]] = {}
        self._folder_path_cache: Dict[str, List[str]] = {}

    def list_media_files(
        self,
        *,
        mime_type_filters: Optional[Iterable[str]] = None,
    ) -> List[Dict[str, Any]]:
        return list_drive_files(
            self._service,
            self._folder_id,
            drive_id=self._shared_drive_id,
            supports_all_drives=self._supports_all_drives,
            mime_type_filters=mime_type_filters,
        )

    def build_folder_path(self, file_entry: Dict[str, Any]) -> List[str]:
        parents = file_entry.get("parents") or []
        if not parents:
            return []
        return build_drive_folder_path(
            self._service,
            parents[0],
            self._folder_metadata_cache,
            self._folder_path_cache,
            root_folder_id=self._folder_id,
            supports_all_drives=self._supports_all_drives,
        )

    def ensure_public_access(self, file_entry: Dict[str, Any], *, dry_run: bool = False) -> bool:
        return ensure_drive_public_permission(
            self._service,
            str(file_entry["id"]),
            dry_run=dry_run,
            supports_all_drives=self._supports_all_drives,
            skip_permission_updates=self._skip_permission_updates,
        )

    def build_public_url(
        self,
        file_entry: Dict[str, Any],
        *,
        public_link_template: Optional[str] = None,
    ) -> str:
        template = public_link_template or str(
            self.config.get("public_link_template") or "https://drive.google.com/uc?export=download&id={file_id}"
        )
        return _resolve_public_url_template(template=template, file_entry=file_entry)


@dataclass
class R2StorageBackend:
    config: Dict[str, Any]
    provider: str = "r2"

    def __post_init__(self) -> None:
        storage_cfg = self._storage_config
        self._bucket = str(storage_cfg.get("bucket") or "").strip()
        if not self._bucket:
            raise ValueError("storage.bucket is required when storage.provider is 'r2'.")
        self._prefix = _normalize_posix_parts(storage_cfg.get("prefix"))
        self._public_base_url = str(storage_cfg.get("public_base_url") or "").strip() or None
        self._manifest_path = _resolve_relative_path(storage_cfg.get("manifest_file"), config=self.config)
        self._client: Optional[BaseClient] = None
        self._manifest_entries: Optional[List[Dict[str, Any]]] = None

    @property
    def _storage_config(self) -> Dict[str, Any]:
        storage_cfg = self.config.get("storage")
        if not isinstance(storage_cfg, dict):
            raise ValueError("storage config must be an object for R2-backed shows.")
        return storage_cfg

    def list_media_files(
        self,
        *,
        mime_type_filters: Optional[Iterable[str]] = None,
    ) -> List[Dict[str, Any]]:
        if self._manifest_path and self._manifest_path.exists():
            if self._manifest_entries is None:
                self._manifest_entries = self._load_manifest_entries()
            return [
                entry
                for entry in self._manifest_entries
                if _matches_mime_type(str(entry.get("mimeType") or ""), mime_type_filters)
            ]

        client = self._ensure_client()
        prefix = "/".join(self._prefix)
        params: Dict[str, Any] = {"Bucket": self._bucket}
        if prefix:
            params["Prefix"] = f"{prefix}/"
        paginator = client.get_paginator("list_objects_v2")
        items: List[Dict[str, Any]] = []
        for page in paginator.paginate(**params):
            for obj in page.get("Contents", []):
                key = str(obj.get("Key") or "").strip()
                if not key or key.endswith("/"):
                    continue
                entry = self._build_entry_from_object(obj)
                if _matches_mime_type(str(entry.get("mimeType") or ""), mime_type_filters):
                    items.append(entry)
        return items

    def build_folder_path(self, file_entry: Dict[str, Any]) -> List[str]:
        if isinstance(file_entry.get("folder_parts"), list):
            return [str(part) for part in file_entry["folder_parts"] if str(part).strip()]
        source_path = str(file_entry.get("source_path") or "").strip().replace("\\", "/").strip("/")
        if not source_path:
            return []
        parts = [part for part in PurePosixPath(source_path).parts[:-1] if part]
        return parts

    def ensure_public_access(self, file_entry: Dict[str, Any], *, dry_run: bool = False) -> bool:
        return False

    def build_public_url(
        self,
        file_entry: Dict[str, Any],
        *,
        public_link_template: Optional[str] = None,
    ) -> str:
        return _resolve_public_url_template(
            template=public_link_template or None,
            file_entry=file_entry,
            default_base_url=self._public_base_url,
        )

    def _load_manifest_entries(self) -> List[Dict[str, Any]]:
        payload = load_json(self._manifest_path)
        raw_items = payload.get("items")
        if not isinstance(raw_items, list):
            raise ValueError(f"Manifest items list missing in {self._manifest_path}")
        normalized: List[Dict[str, Any]] = []
        for raw_entry in raw_items:
            if not isinstance(raw_entry, dict):
                continue
            key = str(
                raw_entry.get("object_key")
                or raw_entry.get("key")
                or raw_entry.get("source_storage_key")
                or ""
            ).strip()
            if not key:
                continue
            normalized.append(self._normalize_manifest_entry(raw_entry, key))
        return normalized

    def _normalize_manifest_entry(self, raw_entry: Dict[str, Any], key: str) -> Dict[str, Any]:
        path_parts = _normalize_posix_parts(raw_entry.get("path_parts"))
        key_parts = self._relative_key_parts(key)
        name = str(raw_entry.get("source_name") or raw_entry.get("name") or key_parts[-1]).strip()
        if not path_parts:
            if len(key_parts) > 1:
                path_parts = tuple(key_parts[:-1])
            else:
                path_parts = ()
        source_path = str(raw_entry.get("source_path") or "/".join((*path_parts, name))).strip("/")
        mime_type = str(raw_entry.get("mime_type") or raw_entry.get("mimeType") or _guess_mime_type(name)).strip()
        published_at = str(
            raw_entry.get("published_at")
            or raw_entry.get("createdTime")
            or raw_entry.get("modified_at")
            or raw_entry.get("modifiedTime")
            or ""
        ).strip()
        size = raw_entry.get("size")
        return {
            **raw_entry,
            "id": str(raw_entry.get("id") or key),
            "key": key,
            "name": name,
            "mimeType": mime_type,
            "size": size,
            "createdTime": published_at or raw_entry.get("createdTime"),
            "modifiedTime": str(raw_entry.get("modified_at") or raw_entry.get("modifiedTime") or published_at).strip(),
            "folder_parts": list(path_parts),
            "source_path": source_path,
            "source_drive_file_id": str(raw_entry.get("source_drive_file_id") or "").strip(),
            "source_storage_key": str(raw_entry.get("source_storage_key") or key).strip(),
            "source_storage_provider": self.provider,
            "stable_guid": str(raw_entry.get("stable_guid") or "").strip() or None,
            "public_url": str(raw_entry.get("public_url") or "").strip() or None,
        }

    def _ensure_client(self) -> BaseClient:
        if self._client is not None:
            return self._client
        if boto3 is None:
            raise SystemExit(
                "Missing boto3 dependency for R2 access. Install requirements or provide a manifest_file."
            )
        storage_cfg = self._storage_config
        endpoint = str(storage_cfg.get("endpoint") or "").strip()
        if not endpoint:
            raise ValueError("storage.endpoint is required when listing R2 directly.")
        access_key_id = str(storage_cfg.get("access_key_id") or "").strip()
        secret_access_key = str(storage_cfg.get("secret_access_key") or "").strip()
        access_key_env = str(storage_cfg.get("access_key_id_env") or "R2_ACCESS_KEY_ID").strip()
        secret_key_env = str(storage_cfg.get("secret_access_key_env") or "R2_SECRET_ACCESS_KEY").strip()
        if not access_key_id and access_key_env:
            access_key_id = str(os.environ.get(access_key_env) or "").strip()
        if not secret_access_key and secret_key_env:
            secret_access_key = str(os.environ.get(secret_key_env) or "").strip()
        if not access_key_id or not secret_access_key:
            raise ValueError(
                "Missing R2 credentials. Set storage.access_key_id/storage.secret_access_key "
                "or expose them via the configured env vars."
            )
        session_kwargs: Dict[str, Any] = {}
        if access_key_id:
            session_kwargs["aws_access_key_id"] = access_key_id
        if secret_access_key:
            session_kwargs["aws_secret_access_key"] = secret_access_key
        session = boto3.session.Session(**session_kwargs)
        self._client = session.client(
            "s3",
            endpoint_url=endpoint,
            region_name=str(storage_cfg.get("region") or "auto"),
        )
        return self._client

    def _build_entry_from_object(self, obj: Dict[str, Any]) -> Dict[str, Any]:
        key = str(obj.get("Key") or "").strip()
        key_parts = self._relative_key_parts(key)
        name = key_parts[-1]
        folder_parts = list(key_parts[:-1])
        source_path = "/".join(key_parts)
        modified = obj.get("LastModified")
        modified_value = modified.isoformat() if modified is not None else ""
        mime_type = _guess_mime_type(name)
        return {
            "id": key,
            "key": key,
            "name": name,
            "mimeType": mime_type,
            "size": obj.get("Size"),
            "createdTime": modified_value,
            "modifiedTime": modified_value,
            "folder_parts": folder_parts,
            "source_path": source_path,
            "source_storage_key": key,
            "source_storage_provider": self.provider,
            "public_url": None,
            "stable_guid": None,
        }

    def _relative_key_parts(self, key: str) -> Tuple[str, ...]:
        parts = PurePosixPath(key).parts
        prefix_parts = self._prefix
        if prefix_parts and parts[: len(prefix_parts)] == prefix_parts:
            trimmed = parts[len(prefix_parts) :]
            if trimmed:
                return trimmed
        return parts


def build_drive_service(credentials_path: Path):
    if service_account is None or build is None:
        raise SystemExit(
            "Missing Google API dependencies. Install requirements (google-auth, google-api-python-client) "
            "or run in an environment that has them available."
        )
    credentials = service_account.Credentials.from_service_account_file(
        str(credentials_path), scopes=DRIVE_SCOPES
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def _should_retry_drive_http_error(exc: HttpError) -> bool:
    status = getattr(exc.resp, "status", None)
    if status in GOOGLE_API_RETRY_STATUS_CODES:
        return True
    try:
        if isinstance(exc.content, bytes):
            content = exc.content.decode("utf-8", errors="ignore")
        else:
            content = exc.content or ""
        payload = json.loads(content)
    except (TypeError, ValueError, UnicodeDecodeError):
        return False

    details = payload.get("error") or {}
    if details.get("code") in GOOGLE_API_RETRY_STATUS_CODES:
        return True
    for error in details.get("errors", []):
        if error.get("reason") in GOOGLE_API_RETRY_REASONS:
            return True
    return False


def _execute_drive_request_with_retry(
    request,
    *,
    max_attempts: int = 5,
) -> Any:
    import time

    for attempt in range(1, max_attempts + 1):
        try:
            return request.execute()
        except HttpError as exc:
            if attempt == max_attempts or not _should_retry_drive_http_error(exc):
                raise
            time.sleep(min(1.0 * (2 ** (attempt - 1)), 30.0))


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
        response = _execute_drive_request_with_retry(service.files().list(**params))
        entries.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return entries


def _build_drive_mime_query(filters: Optional[Iterable[str]]) -> str:
    terms = [term for term in (filters or ["audio/"]) if term]
    clauses: List[str] = []
    for term in terms:
        sanitized = str(term).replace("'", "\\'")
        if str(term).endswith("/"):
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
) -> List[Dict[str, Any]]:
    files: List[Dict[str, Any]] = []
    pending: List[str] = [folder_id]
    seen: set[str] = set()
    file_fields = "nextPageToken, files(id,name,mimeType,size,parents,modifiedTime,createdTime)"
    folder_fields = "nextPageToken, files(id,name)"
    mime_clause = _build_drive_mime_query(mime_type_filters)

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


def build_drive_folder_path(
    service,
    folder_id: str,
    folder_cache: Dict[str, Dict[str, Any]],
    path_cache: Dict[str, List[str]],
    *,
    root_folder_id: Optional[str] = None,
    supports_all_drives: bool = False,
) -> List[str]:
    if folder_id in path_cache:
        return path_cache[folder_id]

    parts: List[str] = []
    current_id = folder_id
    visited: set[str] = set()
    while current_id and current_id not in visited:
        if root_folder_id and current_id == root_folder_id:
            break
        visited.add(current_id)
        metadata = folder_cache.get(current_id)
        if metadata is None:
            params: Dict[str, Any] = {
                "fileId": current_id,
                "fields": "id,name,parents",
            }
            if supports_all_drives:
                params["supportsAllDrives"] = True
            metadata = _execute_drive_request_with_retry(service.files().get(**params))
            folder_cache[current_id] = metadata
        name = str(metadata.get("name") or "").strip()
        if name:
            parts.append(name)
        parents = metadata.get("parents") or []
        current_id = str(parents[0]) if parents else ""

    parts.reverse()
    path_cache[folder_id] = parts
    return parts


def ensure_drive_public_permission(
    service,
    file_id: str,
    *,
    dry_run: bool = False,
    supports_all_drives: bool = False,
    skip_permission_updates: bool = False,
) -> bool:
    if skip_permission_updates:
        return False

    permissions_params: Dict[str, Any] = {
        "fileId": file_id,
        "fields": "permissions(id,type,role)",
    }
    if supports_all_drives:
        permissions_params["supportsAllDrives"] = True
    permissions = _execute_drive_request_with_retry(service.permissions().list(**permissions_params))
    for permission in permissions.get("permissions", []):
        if permission.get("type") == "anyone" and permission.get("role") == "reader":
            return False

    if dry_run:
        return True

    create_params: Dict[str, Any] = {
        "fileId": file_id,
        "body": {"role": "reader", "type": "anyone"},
    }
    if supports_all_drives:
        create_params["supportsAllDrives"] = True
    _execute_drive_request_with_retry(service.permissions().create(**create_params))
    return True
