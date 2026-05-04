"""Prepare and validate publish bundles for queue-owned NotebookLM jobs."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

try:
    import boto3
    from botocore.client import BaseClient
except ModuleNotFoundError:  # pragma: no cover - optional until R2 publishing is enabled
    boto3 = None  # type: ignore[assignment]
    BaseClient = Any  # type: ignore[assignment]

from .adapters import get_show_adapter
from .constants import (
    STATE_BLOCKED_CONFIG_ERROR,
    STATE_APPROVED_FOR_PUBLISH,
    STATE_AWAITING_PUBLISH,
    STATE_FAILED_RETRYABLE,
    STATE_OBJECTS_UPLOADED,
    STATE_UPLOADING_OBJECTS,
    STATE_VALIDATING_GENERATED_ARTIFACTS,
)
from .show_config import (
    ShowConfigSelectionError,
    load_show_config,
    resolve_manifest_bound_show_config_path,
    resolve_show_config_path,
    serialize_show_config_path,
)
from .store import QueueStore, utc_now_iso

AUDIO_SUFFIXES = {".mp3", ".m4a", ".wav"}
INFOGRAPHIC_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
MEDIA_ARTIFACT_TYPES = {"audio", "infographic"}


@dataclass(frozen=True, slots=True)
class PublishOptions:
    repo_root: Path
    actor: str = "system"
    show_config_path: Path | None = None


@dataclass(frozen=True, slots=True)
class UploadOptions:
    repo_root: Path
    actor: str = "system"
    show_config_path: Path | None = None


@dataclass(frozen=True, slots=True)
class R2PublishTarget:
    bucket: str
    endpoint: str
    region: str
    prefix_parts: tuple[str, ...]
    manifest_path: Path
    public_base_url: str | None
    access_key_id: str
    secret_access_key: str


def prepare_publish_bundle(
    *,
    store: QueueStore,
    show_slug: str,
    options: PublishOptions,
    job_id: str | None = None,
) -> dict[str, Any]:
    adapter = get_show_adapter(show_slug)
    with store.acquire_show_lock(show_slug):
        job = _claim_or_resume_job(store=store, show_slug=show_slug, job_id=job_id, actor=options.actor)
        bundle_id = utc_now_iso().replace(":", "").replace("-", "")
        manifest: dict[str, Any] = {
            "version": 1,
            "bundle_id": bundle_id,
            "job_id": str(job.get("job_id") or ""),
            "show_slug": show_slug,
            "subject_slug": adapter.subject_slug,
            "lecture_key": str(job.get("lecture_key") or ""),
            "content_types": list(job.get("content_types") or []),
            "started_at": utc_now_iso(),
            "status": "running",
        }
        try:
            resolved_show_config_path = _resolve_prepare_show_config_path(
                repo_root=options.repo_root,
                adapter=adapter,
                job=job,
                requested_show_config_path=options.show_config_path,
            )
            bundle = _build_publish_bundle(
                repo_root=options.repo_root,
                show_slug=show_slug,
                lecture_key=str(job.get("lecture_key") or ""),
                requested_types=tuple(str(item) for item in (job.get("content_types") or []) if str(item).strip()),
                show_config_path=resolved_show_config_path,
            )
        except PublishValidationError as exc:
            return _finalize_failure(
                store=store,
                job=job,
                manifest=manifest,
                bundle_id=bundle_id,
                actor=options.actor,
                error_message=str(exc),
            )

        manifest["status"] = "completed"
        manifest["completed_at"] = utc_now_iso()
        manifest["storage_provider"] = bundle["storage_provider"]
        manifest["show_config"] = {
            "path": serialize_show_config_path(repo_root=options.repo_root, path=resolved_show_config_path),
        }
        manifest["bundle"] = bundle
        manifest_path = store.save_publish_manifest(
            show_slug=show_slug,
            job_id=str(job["job_id"]),
            payload=manifest,
            bundle_id=bundle_id,
        )
        updated = store.transition_job(
            show_slug=show_slug,
            job_id=str(job["job_id"]),
            state=STATE_APPROVED_FOR_PUBLISH,
            actor=options.actor,
            note="Prepared and validated publish bundle.",
            details={
                "bundle_id": bundle_id,
                "manifest_path": manifest_path,
                "artifact_count": bundle["artifact_count"],
                "bundle_hash": bundle["bundle_hash"],
            },
        )
        updated = _persist_publish_artifacts(
            store=store,
            job=updated,
            manifest_path=manifest_path,
            bundle=bundle,
            bundle_id=bundle_id,
        )
        return {
            "bundle_id": bundle_id,
            "job_id": str(updated["job_id"]),
            "show_slug": show_slug,
            "final_state": str(updated.get("state") or ""),
            "manifest_path": manifest_path,
            "artifact_count": bundle["artifact_count"],
            "bundle_hash": bundle["bundle_hash"],
        }


class PublishValidationError(RuntimeError):
    """Raised when local generated artifacts do not satisfy publish requirements."""


class PublishConfigError(RuntimeError):
    """Raised when a show's publish configuration is invalid for queue-managed upload."""


class PublishExecutionError(RuntimeError):
    """Raised when uploading or manifest writing fails."""


def upload_publish_bundle(
    *,
    store: QueueStore,
    show_slug: str,
    options: UploadOptions,
    job_id: str | None = None,
) -> dict[str, Any]:
    adapter = get_show_adapter(show_slug)
    with store.acquire_show_lock(show_slug):
        job = _claim_or_resume_upload_job(store=store, show_slug=show_slug, job_id=job_id, actor=options.actor)
        manifest_path = _latest_publish_manifest_path(store=store, job=job)
        manifest = _load_publish_manifest(path=manifest_path)
        bundle_id = str(manifest.get("bundle_id") or job.get("artifacts", {}).get("publish", {}).get("latest_bundle_id") or "")
        if not bundle_id:
            raise PublishExecutionError(f"Missing bundle_id for job {job['job_id']}")
        try:
            upload_result = _upload_media_objects(
                repo_root=options.repo_root,
                adapter=adapter,
                job=job,
                manifest=manifest,
                requested_show_config_path=options.show_config_path,
            )
        except ShowConfigSelectionError as exc:
            return _finalize_upload_failure(
                store=store,
                job=job,
                manifest=manifest,
                bundle_id=bundle_id,
                actor=options.actor,
                error_message=str(exc),
                failure_state=STATE_BLOCKED_CONFIG_ERROR,
                status="upload_blocked",
            )
        except PublishConfigError as exc:
            return _finalize_upload_failure(
                store=store,
                job=job,
                manifest=manifest,
                bundle_id=bundle_id,
                actor=options.actor,
                error_message=str(exc),
                failure_state=STATE_BLOCKED_CONFIG_ERROR,
                status="upload_blocked",
            )
        except PublishExecutionError as exc:
            return _finalize_upload_failure(
                store=store,
                job=job,
                manifest=manifest,
                bundle_id=bundle_id,
                actor=options.actor,
                error_message=str(exc),
                failure_state=STATE_FAILED_RETRYABLE,
                status="upload_failed",
            )

        manifest["status"] = "objects_uploaded"
        manifest["completed_at"] = utc_now_iso()
        manifest["upload"] = upload_result
        manifest_path_rel = store.save_publish_manifest(
            show_slug=show_slug,
            job_id=str(job["job_id"]),
            payload=manifest,
            bundle_id=bundle_id,
        )
        updated = store.transition_job(
            show_slug=show_slug,
            job_id=str(job["job_id"]),
            state=STATE_OBJECTS_UPLOADED,
            actor=options.actor,
            note="Uploaded media artifacts to R2 and refreshed the media manifest.",
            details={
                "bundle_id": bundle_id,
                "manifest_path": manifest_path_rel,
                "media_manifest_path": upload_result["media_manifest_path"],
                "uploaded_object_count": upload_result["uploaded_object_count"],
            },
        )
        updated = _persist_upload_artifacts(
            store=store,
            job=updated,
            manifest_path=manifest_path_rel,
            media_manifest_path=upload_result["media_manifest_path"],
            uploaded_object_count=upload_result["uploaded_object_count"],
        )
        return {
            "bundle_id": bundle_id,
            "job_id": str(updated["job_id"]),
            "show_slug": show_slug,
            "final_state": str(updated.get("state") or ""),
            "manifest_path": manifest_path_rel,
            "media_manifest_path": upload_result["media_manifest_path"],
            "uploaded_object_count": upload_result["uploaded_object_count"],
        }


def _claim_or_resume_job(
    *,
    store: QueueStore,
    show_slug: str,
    job_id: str | None,
    actor: str,
) -> dict[str, Any]:
    if job_id:
        job = store.load_job(show_slug=show_slug, job_id=job_id)
        if not job:
            raise FileNotFoundError(f"Unknown job: {show_slug}/{job_id}")
        state = str(job.get("state") or "")
        if state == STATE_AWAITING_PUBLISH:
            return store.transition_job(
                show_slug=show_slug,
                job_id=job_id,
                state=STATE_VALIDATING_GENERATED_ARTIFACTS,
                actor=actor,
                note="Preparing publish bundle for explicitly selected job.",
                expected_states={STATE_AWAITING_PUBLISH},
            )
        if state != STATE_VALIDATING_GENERATED_ARTIFACTS:
            raise ValueError(
                f"Job {job_id} is in state {state}, expected {STATE_AWAITING_PUBLISH} "
                f"or {STATE_VALIDATING_GENERATED_ARTIFACTS}."
            )
        return job

    resumable = [
        entry
        for entry in store.list_jobs(show_slug=show_slug)
        if str(entry.get("state") or "") == STATE_VALIDATING_GENERATED_ARTIFACTS
    ]
    if resumable:
        resumable.sort(
            key=lambda item: (
                int(item.get("priority") or 100),
                str(item.get("created_at") or ""),
                str(item.get("job_id") or ""),
            )
        )
        return store.load_job(show_slug=show_slug, job_id=str(resumable[0]["job_id"]))

    candidates = [
        entry
        for entry in store.list_jobs(show_slug=show_slug)
        if str(entry.get("state") or "") == STATE_AWAITING_PUBLISH
    ]
    if not candidates:
        raise FileNotFoundError(f"No publishable job found for show: {show_slug}")
    candidates.sort(
        key=lambda item: (
            int(item.get("priority") or 100),
            str(item.get("created_at") or ""),
            str(item.get("job_id") or ""),
        )
    )
    winner = candidates[0]
    return store.transition_job(
        show_slug=show_slug,
        job_id=str(winner["job_id"]),
        state=STATE_VALIDATING_GENERATED_ARTIFACTS,
        actor=actor,
        note="Claimed next awaiting_publish job for bundle preparation.",
        expected_states={STATE_AWAITING_PUBLISH},
    )


def _claim_or_resume_upload_job(
    *,
    store: QueueStore,
    show_slug: str,
    job_id: str | None,
    actor: str,
) -> dict[str, Any]:
    if job_id:
        job = store.load_job(show_slug=show_slug, job_id=job_id)
        if not job:
            raise FileNotFoundError(f"Unknown job: {show_slug}/{job_id}")
        state = str(job.get("state") or "")
        if state == STATE_APPROVED_FOR_PUBLISH:
            return store.transition_job(
                show_slug=show_slug,
                job_id=job_id,
                state=STATE_UPLOADING_OBJECTS,
                actor=actor,
                note="Uploading approved media bundle to R2 for explicitly selected job.",
                expected_states={STATE_APPROVED_FOR_PUBLISH},
            )
        if state != STATE_UPLOADING_OBJECTS:
            raise ValueError(
                f"Job {job_id} is in state {state}, expected {STATE_APPROVED_FOR_PUBLISH} "
                f"or {STATE_UPLOADING_OBJECTS}."
            )
        return job

    resumable = [
        entry
        for entry in store.list_jobs(show_slug=show_slug)
        if str(entry.get("state") or "") == STATE_UPLOADING_OBJECTS
    ]
    if resumable:
        resumable.sort(
            key=lambda item: (
                int(item.get("priority") or 100),
                str(item.get("created_at") or ""),
                str(item.get("job_id") or ""),
            )
        )
        return store.load_job(show_slug=show_slug, job_id=str(resumable[0]["job_id"]))

    candidates = [
        entry
        for entry in store.list_jobs(show_slug=show_slug)
        if str(entry.get("state") or "") == STATE_APPROVED_FOR_PUBLISH
    ]
    if not candidates:
        raise FileNotFoundError(f"No approved publish job found for show: {show_slug}")
    candidates.sort(
        key=lambda item: (
            int(item.get("priority") or 100),
            str(item.get("created_at") or ""),
            str(item.get("job_id") or ""),
        )
    )
    winner = candidates[0]
    return store.transition_job(
        show_slug=show_slug,
        job_id=str(winner["job_id"]),
        state=STATE_UPLOADING_OBJECTS,
        actor=actor,
        note="Claimed next approved_for_publish job for R2 upload.",
        expected_states={STATE_APPROVED_FOR_PUBLISH},
    )


def _build_publish_bundle(
    *,
    repo_root: Path,
    show_slug: str,
    lecture_key: str,
    requested_types: tuple[str, ...],
    show_config_path: Path | None = None,
) -> dict[str, Any]:
    adapter = get_show_adapter(show_slug)
    config = adapter.load_show_config(repo_root, show_config_path=show_config_path)
    storage_provider = _resolve_storage_provider(config)
    week_dirs = _find_week_dirs(adapter.output_root_path(repo_root), lecture_key)
    if not week_dirs:
        raise PublishValidationError(
            f"No week output directory found for {lecture_key} under {adapter.output_root}."
        )

    request_logs = sorted(path for week_dir in week_dirs for path in week_dir.glob("*.request*.json"))
    if request_logs:
        relative_logs = [str(path.relative_to(repo_root)) for path in request_logs]
        raise PublishValidationError(
            f"Pending request logs remain for {lecture_key}: {', '.join(relative_logs[:5])}"
        )

    artifacts: list[dict[str, Any]] = []
    counts: dict[str, int] = {"audio": 0, "quiz": 0, "infographic": 0}
    for week_dir in week_dirs:
        for path in sorted(week_dir.iterdir(), key=lambda current: current.name):
            if not path.is_file() or path.name.startswith("."):
                continue
            artifact_type = _classify_artifact(path)
            if artifact_type is None:
                continue
            artifact = _build_artifact_entry(repo_root=repo_root, week_dir=week_dir, path=path, artifact_type=artifact_type)
            artifacts.append(artifact)
            counts[artifact_type] = counts.get(artifact_type, 0) + 1

    if not artifacts:
        raise PublishValidationError(f"No publishable artifacts found for {lecture_key}.")

    missing_types = [artifact_type for artifact_type in requested_types if counts.get(artifact_type, 0) < 1]
    if missing_types:
        raise PublishValidationError(
            f"Missing required artifact types for {lecture_key}: {', '.join(sorted(missing_types))}"
        )

    bundle_hash = hashlib.sha256(
        json.dumps(
            [
                {
                    "relative_path": artifact["relative_path"],
                    "sha256": artifact["sha256"],
                    "size": artifact["size"],
                    "artifact_type": artifact["artifact_type"],
                }
                for artifact in artifacts
            ],
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    return {
        "lecture_key": lecture_key,
        "storage_provider": storage_provider,
        "week_directories": [str(path.relative_to(repo_root)) for path in week_dirs],
        "requested_types": list(requested_types),
        "artifact_count": len(artifacts),
        "artifact_counts": dict(sorted(counts.items())),
        "bundle_hash": bundle_hash,
        "artifacts": artifacts,
    }


def _finalize_failure(
    *,
    store: QueueStore,
    job: dict[str, Any],
    manifest: dict[str, Any],
    bundle_id: str,
    actor: str,
    error_message: str,
) -> dict[str, Any]:
    manifest["status"] = "failed"
    manifest["completed_at"] = utc_now_iso()
    manifest["last_error"] = error_message
    manifest_path = store.save_publish_manifest(
        show_slug=str(job["show_slug"]),
        job_id=str(job["job_id"]),
        payload=manifest,
        bundle_id=bundle_id,
    )
    updated = store.transition_job(
        show_slug=str(job["show_slug"]),
        job_id=str(job["job_id"]),
        state=STATE_FAILED_RETRYABLE,
        actor=actor,
        note="Publish bundle validation failed.",
        error=error_message,
        details={"bundle_id": bundle_id, "manifest_path": manifest_path},
    )
    _persist_publish_artifacts(
        store=store,
        job=updated,
        manifest_path=manifest_path,
        bundle=None,
        bundle_id=bundle_id,
    )
    return {
        "bundle_id": bundle_id,
        "job_id": str(updated["job_id"]),
        "show_slug": str(updated["show_slug"]),
        "final_state": str(updated.get("state") or ""),
        "manifest_path": manifest_path,
        "error": error_message,
    }


def _persist_publish_artifacts(
    *,
    store: QueueStore,
    job: dict[str, Any],
    manifest_path: str,
    bundle: dict[str, Any] | None,
    bundle_id: str,
) -> dict[str, Any]:
    artifacts = dict(job.get("artifacts") or {})
    publish = dict(artifacts.get("publish") or {})
    publish.update(
        {
            "latest_bundle_manifest": manifest_path,
            "latest_bundle_id": bundle_id,
            "last_validated_at": utc_now_iso(),
        }
    )
    if bundle is not None:
        publish["latest_bundle_hash"] = bundle["bundle_hash"]
        publish["latest_artifact_count"] = bundle["artifact_count"]
        publish["storage_provider"] = bundle["storage_provider"]
    artifacts["publish"] = publish
    job["artifacts"] = artifacts
    store.save_job(job)
    return job


def _persist_upload_artifacts(
    *,
    store: QueueStore,
    job: dict[str, Any],
    manifest_path: str,
    media_manifest_path: str,
    uploaded_object_count: int,
) -> dict[str, Any]:
    artifacts = dict(job.get("artifacts") or {})
    publish = dict(artifacts.get("publish") or {})
    publish.update(
        {
            "latest_bundle_manifest": manifest_path,
            "latest_media_manifest": media_manifest_path,
            "last_uploaded_at": utc_now_iso(),
            "uploaded_object_count": int(uploaded_object_count),
        }
    )
    artifacts["publish"] = publish
    job["artifacts"] = artifacts
    store.save_job(job)
    return job


def _latest_publish_manifest_path(*, store: QueueStore, job: dict[str, Any]) -> Path:
    publish = dict((job.get("artifacts") or {}).get("publish") or {})
    relative = str(publish.get("latest_bundle_manifest") or "").strip()
    if not relative:
        raise PublishExecutionError(f"No publish manifest recorded for job {job['job_id']}")
    path = store.root / relative
    if not path.exists():
        raise PublishExecutionError(f"Publish manifest missing for job {job['job_id']}: {path}")
    return path


def _load_publish_manifest(*, path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublishExecutionError(f"Failed to load publish manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise PublishExecutionError(f"Publish manifest must be a JSON object: {path}")
    return payload


def _upload_media_objects(
    *,
    repo_root: Path,
    adapter,
    job: dict[str, Any],
    manifest: dict[str, Any],
    requested_show_config_path: Path | None = None,
) -> dict[str, Any]:
    bundle = manifest.get("bundle")
    if not isinstance(bundle, dict):
        raise PublishExecutionError(f"Publish manifest is missing bundle payload for job {job['job_id']}")

    resolved_show_config_path = resolve_manifest_bound_show_config_path(
        repo_root=repo_root,
        default_path=adapter.show_config_path,
        manifest=manifest,
        override_path=requested_show_config_path,
    )
    config = load_show_config(
        repo_root=repo_root,
        default_path=adapter.show_config_path,
        override_path=resolved_show_config_path,
    )
    target = _resolve_r2_publish_target(config=config, repo_root=repo_root)
    client = _build_r2_client(target)
    artifacts = bundle.get("artifacts")
    if not isinstance(artifacts, list):
        raise PublishExecutionError("Publish bundle artifacts must be a list.")

    uploadable = [
        artifact
        for artifact in artifacts
        if isinstance(artifact, dict) and str(artifact.get("artifact_type") or "") in MEDIA_ARTIFACT_TYPES
    ]
    if not uploadable:
        raise PublishExecutionError(f"No media artifacts available for R2 upload in job {job['job_id']}")

    existing_items = _load_media_manifest_items(target.manifest_path)
    uploaded_items: list[dict[str, Any]] = []
    uploaded_at = utc_now_iso()
    for artifact in uploadable:
        source_path = repo_root / str(artifact["relative_path"])
        _validate_artifact_source(source_path=source_path, artifact=artifact)
        object_key = _artifact_object_key(repo_root=repo_root, adapter=adapter, artifact=artifact, prefix_parts=target.prefix_parts)
        metadata = {
            "sha256": str(artifact["sha256"]),
            "jobid": str(job["job_id"]),
            "bundleid": str(manifest.get("bundle_id") or ""),
            "showslug": str(job["show_slug"]),
            "lecturekey": str(job["lecture_key"]),
            "artifacttype": str(artifact["artifact_type"]),
        }
        with source_path.open("rb") as handle:
            client.put_object(
                Bucket=target.bucket,
                Key=object_key,
                Body=handle,
                ContentType=str(artifact["mime_type"]),
                Metadata=metadata,
            )
        head = client.head_object(Bucket=target.bucket, Key=object_key)
        _verify_uploaded_object(head=head, artifact=artifact, metadata=metadata, object_key=object_key)
        uploaded_items.append(
            _build_media_manifest_item(
                repo_root=repo_root,
                adapter=adapter,
                artifact=artifact,
                object_key=object_key,
                uploaded_at=uploaded_at,
                bucket=target.bucket,
                public_base_url=target.public_base_url,
            )
        )

    merged_items = _merge_media_manifest_items(existing_items=existing_items, uploaded_items=uploaded_items)
    _write_media_manifest(
        path=target.manifest_path,
        payload={
            "version": 1,
            "provider": "r2",
            "bucket": target.bucket,
            "prefix": "/".join(target.prefix_parts),
            "generated_at": utc_now_iso(),
            "items": merged_items,
        },
    )
    return {
        "status": "completed",
        "completed_at": utc_now_iso(),
        "bucket": target.bucket,
        "prefix": "/".join(target.prefix_parts),
        "media_manifest_path": str(target.manifest_path.relative_to(repo_root)),
        "uploaded_object_count": len(uploaded_items),
        "uploaded_items": uploaded_items,
    }


def _resolve_prepare_show_config_path(
    *,
    repo_root: Path,
    adapter,
    job: dict[str, Any],
    requested_show_config_path: Path | None,
) -> Path:
    metadata = job.get("metadata") if isinstance(job.get("metadata"), dict) else {}
    metadata_show_config = str(metadata.get("show_config_path") or "").strip() or None
    if requested_show_config_path is not None and metadata_show_config:
        explicit_path = resolve_show_config_path(
            repo_root=repo_root,
            default_path=adapter.show_config_path,
            override_path=requested_show_config_path,
        )
        metadata_path = resolve_show_config_path(
            repo_root=repo_root,
            default_path=adapter.show_config_path,
            override_path=metadata_show_config,
        )
        if explicit_path != metadata_path:
            raise PublishValidationError(
                f"Explicit show config {explicit_path} does not match the queued job show config {metadata_path}."
            )
    return resolve_show_config_path(
        repo_root=repo_root,
        default_path=adapter.show_config_path,
        override_path=requested_show_config_path or metadata_show_config,
    )


def _resolve_r2_publish_target(*, config: dict[str, object], repo_root: Path) -> R2PublishTarget:
    storage = config.get("storage")
    if not isinstance(storage, dict):
        raise PublishConfigError("Queue R2 upload requires a storage object in the show config.")
    provider = str(storage.get("provider") or "").strip().lower()
    if provider != "r2":
        raise PublishConfigError(
            f"Queue R2 upload only supports storage.provider='r2'; found {provider or 'drive'}."
        )
    bucket = str(storage.get("bucket") or "").strip()
    endpoint = str(storage.get("endpoint") or "").strip()
    prefix_parts = _normalize_posix_parts(storage.get("prefix"))
    manifest_path = _resolve_relative_config_path(storage.get("manifest_file"), config=config, repo_root=repo_root)
    if not bucket:
        raise PublishConfigError("storage.bucket is required for queue-managed R2 upload.")
    if not endpoint:
        raise PublishConfigError("storage.endpoint is required for queue-managed R2 upload.")
    if not prefix_parts:
        raise PublishConfigError("storage.prefix is required for deterministic queue-managed R2 object keys.")
    if manifest_path is None:
        raise PublishConfigError("storage.manifest_file is required for queue-managed R2 upload.")
    access_key_id = str(storage.get("access_key_id") or "").strip()
    secret_access_key = str(storage.get("secret_access_key") or "").strip()
    access_key_env = str(storage.get("access_key_id_env") or "R2_ACCESS_KEY_ID").strip()
    secret_key_env = str(storage.get("secret_access_key_env") or "R2_SECRET_ACCESS_KEY").strip()
    if not access_key_id and access_key_env:
        access_key_id = str(os.environ.get(access_key_env) or "").strip()
    if not secret_access_key and secret_key_env:
        secret_access_key = str(os.environ.get(secret_key_env) or "").strip()
    if not access_key_id or not secret_access_key:
        raise PublishConfigError(
            "Missing R2 credentials. Set storage.access_key_id/storage.secret_access_key "
            "or expose them via the configured env vars."
        )
    return R2PublishTarget(
        bucket=bucket,
        endpoint=endpoint,
        region=str(storage.get("region") or "auto").strip() or "auto",
        prefix_parts=prefix_parts,
        manifest_path=manifest_path,
        public_base_url=str(storage.get("public_base_url") or "").strip() or None,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
    )


def _build_r2_client(target: R2PublishTarget) -> BaseClient:
    if boto3 is None:
        raise PublishConfigError("Missing boto3 dependency for queue-managed R2 upload.")
    session = boto3.session.Session(
        aws_access_key_id=target.access_key_id,
        aws_secret_access_key=target.secret_access_key,
    )
    return session.client("s3", endpoint_url=target.endpoint, region_name=target.region)


def _normalize_posix_parts(value: object) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(part).strip().strip("/") for part in value if str(part).strip().strip("/"))
    text = str(value or "").strip().replace("\\", "/").strip("/")
    if not text:
        return ()
    return tuple(part for part in text.split("/") if part)


def _resolve_relative_config_path(
    value: object,
    *,
    config: dict[str, object],
    repo_root: Path,
) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path.resolve()
    if raw.startswith("shows/"):
        return (repo_root / path).resolve()
    config_path_raw = str(config.get("__config_path__") or "").strip()
    if config_path_raw:
        return (Path(config_path_raw).resolve().parent / path).resolve()
    return (repo_root / path).resolve()


def _load_media_manifest_items(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublishExecutionError(f"Failed to load media manifest {path}: {exc}") from exc
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise PublishExecutionError(f"Media manifest items list missing in {path}")
    return [item for item in items if isinstance(item, dict)]


def _validate_artifact_source(*, source_path: Path, artifact: dict[str, Any]) -> None:
    if not source_path.exists() or not source_path.is_file():
        raise PublishExecutionError(f"Artifact disappeared before upload: {source_path}")
    size = source_path.stat().st_size
    if size != int(artifact.get("size") or -1):
        raise PublishExecutionError(
            f"Artifact size changed before upload for {source_path}: expected {artifact.get('size')}, got {size}"
        )
    digest = _sha256_file(source_path)
    if digest != str(artifact.get("sha256") or ""):
        raise PublishExecutionError(f"Artifact hash changed before upload for {source_path}")


def _artifact_object_key(
    *,
    repo_root: Path,
    adapter,
    artifact: dict[str, Any],
    prefix_parts: tuple[str, ...],
) -> str:
    full_path = (repo_root / str(artifact["relative_path"])).resolve()
    output_root = adapter.output_root_path(repo_root).resolve()
    try:
        relative_output_path = full_path.relative_to(output_root)
    except ValueError as exc:
        raise PublishExecutionError(
            f"Artifact path is outside the expected output root: {artifact['relative_path']}"
        ) from exc
    return PurePosixPath(*prefix_parts, *relative_output_path.parts).as_posix()


def _verify_uploaded_object(
    *,
    head: dict[str, Any],
    artifact: dict[str, Any],
    metadata: dict[str, str],
    object_key: str,
) -> None:
    size = int(head.get("ContentLength") or -1)
    if size != int(artifact["size"]):
        raise PublishExecutionError(
            f"Uploaded object size mismatch for {object_key}: expected {artifact['size']}, got {size}"
        )
    content_type = str(head.get("ContentType") or "").strip()
    if content_type and content_type != str(artifact["mime_type"]):
        raise PublishExecutionError(
            f"Uploaded object content type mismatch for {object_key}: "
            f"expected {artifact['mime_type']}, got {content_type}"
        )
    returned_metadata = {
        str(key).lower(): str(value)
        for key, value in dict(head.get("Metadata") or {}).items()
    }
    for key, value in metadata.items():
        if returned_metadata.get(key.lower()) != value:
            raise PublishExecutionError(
                f"Uploaded object metadata mismatch for {object_key}: key {key} did not round-trip."
            )


def _build_media_manifest_item(
    *,
    repo_root: Path,
    adapter,
    artifact: dict[str, Any],
    object_key: str,
    uploaded_at: str,
    bucket: str,
    public_base_url: str | None,
) -> dict[str, Any]:
    full_path = (repo_root / str(artifact["relative_path"])).resolve()
    output_root = adapter.output_root_path(repo_root).resolve()
    relative_output_path = full_path.relative_to(output_root)
    source_path = PurePosixPath(*relative_output_path.parts).as_posix()
    public_url = None
    if public_base_url:
        public_url = f"{public_base_url.rstrip('/')}/{quote(object_key, safe='/:@')}"
    return {
        "object_key": object_key,
        "source_name": str(artifact["name"]),
        "source_path": source_path,
        "path_parts": list(PurePosixPath(source_path).parts[:-1]),
        "mime_type": str(artifact["mime_type"]),
        "size": int(artifact["size"]),
        "sha256": str(artifact["sha256"]),
        "artifact_type": str(artifact["artifact_type"]),
        "published_at": uploaded_at,
        "bucket": bucket,
        "public_url": public_url,
    }


def _merge_media_manifest_items(
    *,
    existing_items: list[dict[str, Any]],
    uploaded_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in existing_items:
        object_key = str(item.get("object_key") or item.get("key") or item.get("source_storage_key") or "").strip()
        if not object_key:
            continue
        if object_key not in by_key:
            order.append(object_key)
        by_key[object_key] = dict(item)
    for item in uploaded_items:
        object_key = str(item["object_key"])
        existing = dict(by_key.get(object_key) or {})
        merged = dict(existing)
        merged.update(item)
        if existing.get("stable_guid") and not merged.get("stable_guid"):
            merged["stable_guid"] = existing.get("stable_guid")
        if existing.get("public_url") and not merged.get("public_url"):
            merged["public_url"] = existing.get("public_url")
        if object_key not in by_key:
            order.append(object_key)
        by_key[object_key] = merged
    return [by_key[key] for key in sorted(order)]


def _write_media_manifest(*, path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp_path.replace(path)


def _finalize_upload_failure(
    *,
    store: QueueStore,
    job: dict[str, Any],
    manifest: dict[str, Any],
    bundle_id: str,
    actor: str,
    error_message: str,
    failure_state: str,
    status: str,
) -> dict[str, Any]:
    upload = dict(manifest.get("upload") or {})
    upload.update(
        {
            "status": "failed",
            "completed_at": utc_now_iso(),
            "last_error": error_message,
        }
    )
    manifest["status"] = status
    manifest["completed_at"] = utc_now_iso()
    manifest["last_error"] = error_message
    manifest["upload"] = upload
    manifest_path = store.save_publish_manifest(
        show_slug=str(job["show_slug"]),
        job_id=str(job["job_id"]),
        payload=manifest,
        bundle_id=bundle_id,
    )
    updated = store.transition_job(
        show_slug=str(job["show_slug"]),
        job_id=str(job["job_id"]),
        state=failure_state,
        actor=actor,
        note="R2 upload failed." if failure_state == STATE_FAILED_RETRYABLE else "R2 upload blocked by config.",
        error=error_message,
        details={"bundle_id": bundle_id, "manifest_path": manifest_path},
    )
    _persist_publish_artifacts(
        store=store,
        job=updated,
        manifest_path=manifest_path,
        bundle=manifest.get("bundle") if isinstance(manifest.get("bundle"), dict) else None,
        bundle_id=bundle_id,
    )
    return {
        "bundle_id": bundle_id,
        "job_id": str(updated["job_id"]),
        "show_slug": str(updated["show_slug"]),
        "final_state": str(updated.get("state") or ""),
        "manifest_path": manifest_path,
        "error": error_message,
    }


def _find_week_dirs(root: Path, lecture_key: str) -> list[Path]:
    if not root.exists():
        return []
    normalized = lecture_key.strip().upper()
    matches: list[Path] = []
    for entry in sorted(root.iterdir(), key=lambda path: path.name):
        if not entry.is_dir():
            continue
        if entry.name.strip().upper() == normalized:
            matches.append(entry)
            continue
        if _normalize_week_dir_key(entry.name) == normalized:
            matches.append(entry)
    return matches


def _normalize_week_dir_key(value: str) -> str:
    text = value.strip().upper()
    if not text.startswith("W") or "L" not in text:
        return text
    week_part, lecture_part = text[1:].split("L", 1)
    try:
        return f"W{int(week_part)}L{int(lecture_part)}"
    except ValueError:
        return text


def _classify_artifact(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix in AUDIO_SUFFIXES:
        return "audio"
    if suffix in INFOGRAPHIC_SUFFIXES:
        return "infographic"
    if suffix == ".json" and _is_publishable_quiz(path):
        return "quiz"
    return None


def _is_publishable_quiz(path: Path) -> bool:
    name = path.name.lower()
    if ".request" in name:
        return False
    if name == "quiz_json_manifest.json":
        return False
    if name.endswith("-manifest.json") or name.endswith("_manifest.json"):
        return False
    return True


def _build_artifact_entry(*, repo_root: Path, week_dir: Path, path: Path, artifact_type: str) -> dict[str, Any]:
    if path.stat().st_size <= 0:
        raise PublishValidationError(f"Artifact has zero size: {path.relative_to(repo_root)}")
    if artifact_type == "quiz":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise PublishValidationError(f"Quiz JSON is invalid for {path.relative_to(repo_root)}: {exc}") from exc
        if not isinstance(payload, (dict, list)):
            raise PublishValidationError(f"Quiz JSON must be an object or list: {path.relative_to(repo_root)}")
    relative_path = path.relative_to(repo_root)
    return {
        "artifact_type": artifact_type,
        "relative_path": str(relative_path),
        "week_relative_path": str(path.relative_to(week_dir)),
        "name": path.name,
        "size": path.stat().st_size,
        "mime_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        "sha256": _sha256_file(path),
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_storage_provider(config: dict[str, object]) -> str:
    storage = config.get("storage")
    if isinstance(storage, dict):
        provider = str(storage.get("provider") or "").strip().lower()
        if provider:
            return provider
    return "drive"
