"""Prepare and validate publish bundles for queue-owned NotebookLM jobs."""

from __future__ import annotations

import hashlib
import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters import get_show_adapter
from .constants import (
    STATE_APPROVED_FOR_PUBLISH,
    STATE_AWAITING_PUBLISH,
    STATE_FAILED_RETRYABLE,
    STATE_VALIDATING_GENERATED_ARTIFACTS,
)
from .store import QueueStore, utc_now_iso

AUDIO_SUFFIXES = {".mp3", ".m4a", ".wav"}
INFOGRAPHIC_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


@dataclass(frozen=True, slots=True)
class PublishOptions:
    repo_root: Path
    actor: str = "system"


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
            bundle = _build_publish_bundle(
                repo_root=options.repo_root,
                show_slug=show_slug,
                lecture_key=str(job.get("lecture_key") or ""),
                requested_types=tuple(str(item) for item in (job.get("content_types") or []) if str(item).strip()),
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


def _build_publish_bundle(
    *,
    repo_root: Path,
    show_slug: str,
    lecture_key: str,
    requested_types: tuple[str, ...],
) -> dict[str, Any]:
    adapter = get_show_adapter(show_slug)
    config = adapter.load_show_config(repo_root)
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
