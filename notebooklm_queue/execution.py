"""Execution service for queue-owned NotebookLM generation and download phases."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from typing import Any

from .adapters import get_show_adapter
from .alerts import emit_failure_alert
from .constants import (
    STATE_AWAITING_PUBLISH,
    STATE_DOWNLOADING,
    STATE_FAILED_RETRYABLE,
    STATE_GENERATED,
    STATE_GENERATING,
    STATE_QUEUED,
    STATE_RETRY_SCHEDULED,
    STATE_WAITING_FOR_ARTIFACT,
)
from .processes import run_phase_command
from .store import QueueStore, parse_utcish_iso, utc_now_iso

RATE_LIMIT_ERROR_TOKENS = (
    "rate limit",
    "quota exceeded",
    "resource_exhausted",
    "too many requests",
)
PROFILE_COOLDOWN_ERROR_TOKENS = (
    "no usable profiles found after filtering missing/cooldown entries",
    "is on cooldown",
)
TRANSIENT_NOTEBOOKLM_ERROR_TOKENS = (
    "generator timed out before writing a usable request log",
    "rpc create_artifact failed",
    "rpc create_notebook failed",
    "null result data (possible server error",
)
DEFAULT_RATE_LIMIT_RETRY_SECONDS = 900
DEFAULT_RETRY_BACKOFF_MULTIPLIER = 1.5
DEFAULT_RETRY_BACKOFF_MAX_SECONDS = 3600
DEFAULT_EXECUTION_PHASE_TIMEOUT_SECONDS = int(
    os.environ.get("NOTEBOOKLM_QUEUE_EXECUTION_PHASE_TIMEOUT_SECONDS") or "7200"
)
DEFAULT_ARTIFACT_WAIT_TIMEOUT_SECONDS = int(
    os.environ.get("NOTEBOOKLM_QUEUE_ARTIFACT_WAIT_TIMEOUT_SECONDS") or "60"
)
DEFAULT_ARTIFACT_POLL_INTERVAL_SECONDS = int(
    os.environ.get("NOTEBOOKLM_QUEUE_ARTIFACT_POLL_INTERVAL_SECONDS") or "60"
)


@dataclass(frozen=True, slots=True)
class ExecutionOptions:
    repo_root: Path
    retry_at: str | None = None
    actor: str = "system"
    run_download: bool = True
    phase_timeout_seconds: int = DEFAULT_EXECUTION_PHASE_TIMEOUT_SECONDS
    artifact_wait_timeout_seconds: int = DEFAULT_ARTIFACT_WAIT_TIMEOUT_SECONDS
    artifact_poll_interval_seconds: int = DEFAULT_ARTIFACT_POLL_INTERVAL_SECONDS


def _looks_like_rate_limit(message: str | None) -> bool:
    text = str(message or "").lower()
    return any(token in text for token in RATE_LIMIT_ERROR_TOKENS) or any(
        token in text
        for token in (
            "http 429",
            "status 429",
            "code 429",
            "rpc_code=429",
            "429 too many requests",
        )
    )


def _looks_like_profile_cooldown_exhaustion(message: str | None) -> bool:
    text = str(message or "").lower()
    return any(token in text for token in PROFILE_COOLDOWN_ERROR_TOKENS)


def _looks_like_transient_notebooklm_failure(message: str | None) -> bool:
    text = str(message or "").lower()
    return any(token in text for token in TRANSIENT_NOTEBOOKLM_ERROR_TOKENS)


def _int_env(name: str, default: int) -> int:
    raw = str(os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = str(os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _classify_retryable_failure(message: str | None) -> str | None:
    if _looks_like_rate_limit(message):
        return "rate_limit"
    if _looks_like_profile_cooldown_exhaustion(message):
        return "profile_cooldown"
    if _looks_like_transient_notebooklm_failure(message):
        return "transient_notebooklm"
    return None


def _retry_delay_seconds(*, attempt_count: int, error_text: str | None) -> int | None:
    if _classify_retryable_failure(error_text) is None:
        return None

    base_seconds = max(_int_env("NOTEBOOKLM_QUEUE_RATE_LIMIT_RETRY_SECONDS", DEFAULT_RATE_LIMIT_RETRY_SECONDS), 1)
    multiplier = max(
        _float_env("NOTEBOOKLM_QUEUE_RETRY_BACKOFF_MULTIPLIER", DEFAULT_RETRY_BACKOFF_MULTIPLIER),
        1.0,
    )
    max_seconds = max(
        _int_env("NOTEBOOKLM_QUEUE_RETRY_BACKOFF_MAX_SECONDS", DEFAULT_RETRY_BACKOFF_MAX_SECONDS),
        base_seconds,
    )
    exponent = max(int(attempt_count) - 1, 0)
    delay_seconds = ceil(base_seconds * (multiplier**exponent))
    return min(max(delay_seconds, base_seconds), max_seconds)


def _derived_retry_at(
    *,
    explicit_retry_at: str | None,
    error_text: str | None,
    attempt_count: int,
) -> str | None:
    if explicit_retry_at:
        return explicit_retry_at
    delay_seconds = _retry_delay_seconds(
        attempt_count=attempt_count,
        error_text=error_text,
    )
    if delay_seconds is None:
        return None
    retry_at = datetime.now(tz=UTC) + timedelta(seconds=max(delay_seconds, 1))
    return retry_at.replace(microsecond=0).isoformat()


def _phase_primary_error_text(phase: dict[str, Any], fallback: str) -> str:
    for key in ("stderr", "stdout"):
        text = str(phase.get(key) or "").strip()
        if text:
            return text
    return fallback


def _phase_retry_detection_text(phase: dict[str, Any], fallback: str) -> str:
    parts = []
    for key in ("stderr", "stdout"):
        text = str(phase.get(key) or "").strip()
        if text:
            parts.append(text)
    if fallback:
        parts.append(fallback)
    return "\n".join(parts)


def _find_lecture_dirs(*, output_root: Path, lecture_key: str) -> list[Path]:
    if not output_root.exists():
        return []
    matches: list[Path] = []
    exact = output_root / lecture_key
    if exact.exists() and exact.is_dir():
        matches.append(exact)
    for candidate in sorted(output_root.glob(f"{lecture_key}*"), key=lambda path: path.name):
        if candidate.is_dir() and candidate not in matches:
            matches.append(candidate)
    return matches


def _artifact_type_for_output(path: Path) -> str | None:
    name = path.name
    if name.endswith(".request.json") or name.endswith(".request.error.json"):
        return None
    if path.suffix == ".mp3":
        return "audio"
    if path.suffix == ".png":
        return "infographic"
    if path.suffix == ".json":
        return "quiz"
    return None


def _relative_to_repo(repo_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def _collect_output_progress(
    *,
    adapter: Any,
    repo_root: Path,
    lecture_key: str,
    content_types: tuple[str, ...],
) -> dict[str, Any]:
    counts = {artifact_type: 0 for artifact_type in content_types}
    pending_request_logs: list[str] = []
    error_request_logs: list[str] = []
    publishable_artifacts: list[dict[str, Any]] = []
    lecture_dirs = _find_lecture_dirs(output_root=adapter.output_root_path(repo_root), lecture_key=lecture_key)

    for lecture_dir in lecture_dirs:
        for request_log in sorted(lecture_dir.glob("*.request.json"), key=lambda path: path.name):
            pending_request_logs.append(_relative_to_repo(repo_root, request_log))
        for error_log in sorted(lecture_dir.glob("*.request.error.json"), key=lambda path: path.name):
            error_request_logs.append(_relative_to_repo(repo_root, error_log))
        for artifact_path in lecture_dir.iterdir():
            if not artifact_path.is_file():
                continue
            artifact_type = _artifact_type_for_output(artifact_path)
            if artifact_type not in counts:
                continue
            counts[artifact_type] += 1
            publishable_artifacts.append(
                {
                    "relative_path": _relative_to_repo(repo_root, artifact_path),
                    "artifact_type": artifact_type,
                    "size": artifact_path.stat().st_size,
                    "sha256": _sha256_file(artifact_path),
                }
            )

    publishable_artifacts.sort(
        key=lambda item: (
            str(item["relative_path"]),
            str(item["artifact_type"]),
        )
    )
    publishable_bundle_hash = _publishable_bundle_hash(publishable_artifacts)

    return {
        "lecture_key": lecture_key,
        "lecture_dirs": [_relative_to_repo(repo_root, path) for path in lecture_dirs],
        "pending_request_count": len(pending_request_logs),
        "pending_request_logs": pending_request_logs,
        "error_request_count": len(error_request_logs),
        "error_request_logs": error_request_logs,
        "existing_outputs": counts,
        "existing_output_count": sum(counts.values()),
        "publishable_bundle_hash": publishable_bundle_hash,
        "publishable_artifacts": publishable_artifacts,
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


def _publishable_bundle_hash(artifacts: list[dict[str, Any]]) -> str | None:
    if not artifacts:
        return None
    payload = [
        {
            "relative_path": str(item["relative_path"]),
            "artifact_type": str(item["artifact_type"]),
            "size": int(item["size"]),
            "sha256": str(item["sha256"]),
        }
        for item in artifacts
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _last_completed_bundle_hash(job: dict[str, Any]) -> str | None:
    publish = dict((job.get("artifacts") or {}).get("publish") or {})
    value = str(publish.get("last_completed_bundle_hash") or "").strip()
    return value or None


def _has_unpublished_outputs(*, job: dict[str, Any], progress: dict[str, Any] | None) -> bool:
    if not progress or int(progress.get("existing_output_count") or 0) <= 0:
        return False
    current_hash = str(progress.get("publishable_bundle_hash") or "").strip()
    if not current_hash:
        return False
    return current_hash != _last_completed_bundle_hash(job)


def _next_poll_at(*, poll_interval_seconds: int) -> str:
    retry_at = datetime.now(tz=UTC) + timedelta(seconds=max(int(poll_interval_seconds), 1))
    return retry_at.replace(microsecond=0).isoformat()


def _persist_execution_artifacts(
    *,
    store: QueueStore,
    job: dict[str, Any],
    run_id: str,
    manifest_path: str,
    manifest: dict[str, Any],
    progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    refreshed = store.load_job(show_slug=str(job["show_slug"]), job_id=str(job["job_id"]))
    artifacts = dict(refreshed.get("artifacts") or {})
    execution = dict(artifacts.get("execution") or {})
    execution.update(
        {
            "latest_run_manifest": manifest_path,
            "latest_run_id": run_id,
            "last_generate_command": manifest["phases"][0]["command"] if manifest["phases"] else None,
            "last_download_command": manifest["phases"][1]["command"] if len(manifest["phases"]) > 1 else None,
            "last_progress_at": utc_now_iso(),
        }
    )
    if progress is not None:
        execution["last_progress"] = progress
    if manifest.get("status") == "completed":
        execution["last_success_at"] = str(manifest.get("completed_at") or utc_now_iso())
    if manifest.get("status") == "waiting":
        execution["last_waiting_at"] = str(manifest.get("completed_at") or utc_now_iso())
    artifacts["execution"] = execution
    refreshed["artifacts"] = artifacts
    store.save_job(refreshed)
    return refreshed


def _finalize_execution_manifest(
    *,
    store: QueueStore,
    job: dict[str, Any],
    show_slug: str,
    manifest: dict[str, Any],
    run_id: str,
    progress: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest_path = store.save_run_manifest(
        show_slug=show_slug,
        job_id=str(job["job_id"]),
        payload=manifest,
        run_id=run_id,
    )
    refreshed = _persist_execution_artifacts(
        store=store,
        job=job,
        run_id=run_id,
        manifest_path=manifest_path,
        manifest=manifest,
        progress=progress,
    )
    return {
        "run_id": run_id,
        "job_id": str(refreshed["job_id"]),
        "show_slug": show_slug,
        "final_state": str(refreshed.get("state") or ""),
        "manifest_path": manifest_path,
        "phases": manifest["phases"],
    }


def execute_job(
    *,
    store: QueueStore,
    show_slug: str,
    options: ExecutionOptions,
    job_id: str | None = None,
) -> dict[str, Any]:
    adapter = get_show_adapter(show_slug)
    with store.acquire_show_lock(show_slug):
        job = _claim_or_resume_job(store=store, show_slug=show_slug, job_id=job_id, actor=options.actor)
        current_state = str(job.get("state") or "")
        run_id = utc_now_iso().replace(":", "").replace("-", "")
        manifest: dict[str, Any] = {
            "version": 1,
            "run_id": run_id,
            "show_slug": show_slug,
            "subject_slug": adapter.subject_slug,
            "job_id": str(job.get("job_id") or ""),
            "lecture_key": str(job.get("lecture_key") or ""),
            "content_types": list(job.get("content_types") or []),
            "started_at": utc_now_iso(),
            "initial_state": current_state,
            "status": "running",
            "phases": [],
        }

        lecture_key = str(job.get("lecture_key") or "")
        content_types = tuple(str(item) for item in (job.get("content_types") or []) if str(item).strip())
        if not content_types:
            content_types = tuple(adapter.default_content_types)
        latest_progress: dict[str, Any] | None = None
        if current_state in {STATE_QUEUED, STATE_RETRY_SCHEDULED, STATE_GENERATING}:
            generate_command = adapter.build_generate_command(
                options.repo_root,
                lecture_key=lecture_key,
                content_types=content_types,
                dry_run=False,
                wait=False,
            )
            phase = _run_phase(
                name="generate",
                command=generate_command,
                repo_root=options.repo_root,
                timeout_seconds=options.phase_timeout_seconds,
            )
            manifest["phases"].append(phase)
            if phase["returncode"] != 0:
                return _finalize_failure(
                    store=store,
                    job=job,
                    show_slug=show_slug,
                    manifest=manifest,
                    run_id=run_id,
                    options=options,
                    failed_state=STATE_FAILED_RETRYABLE,
                    note="Generate command failed.",
                )
            latest_progress = _collect_output_progress(
                adapter=adapter,
                repo_root=options.repo_root,
                lecture_key=lecture_key,
                content_types=content_types,
            )
            phase["progress"] = latest_progress
            if latest_progress["pending_request_count"] > 0:
                next_retry_at = _next_poll_at(poll_interval_seconds=options.artifact_poll_interval_seconds)
                if _has_unpublished_outputs(job=job, progress=latest_progress):
                    job = store.transition_job(
                        show_slug=show_slug,
                        job_id=str(job["job_id"]),
                        state=STATE_AWAITING_PUBLISH,
                        actor=options.actor,
                        note="Generate command produced unpublished outputs while other artifacts remain pending.",
                        retry_at=next_retry_at,
                        details={"run_id": run_id, "progress": latest_progress},
                    )
                else:
                    job = store.transition_job(
                        show_slug=show_slug,
                        job_id=str(job["job_id"]),
                        state=STATE_WAITING_FOR_ARTIFACT,
                        actor=options.actor,
                        note="Generate command created NotebookLM artifact requests; waiting for upstream completion.",
                        retry_at=next_retry_at,
                        details={"run_id": run_id, "progress": latest_progress},
                    )
                if not options.run_download:
                    manifest["status"] = "completed" if str(job.get("state") or "") == STATE_AWAITING_PUBLISH else "waiting"
                    manifest["completed_at"] = utc_now_iso()
                    manifest["final_state"] = str(job.get("state") or "")
                    return _finalize_execution_manifest(
                        store=store,
                        job=job,
                        show_slug=show_slug,
                        manifest=manifest,
                        run_id=run_id,
                        progress=latest_progress,
                    )
            elif latest_progress["existing_output_count"] > 0:
                job = store.transition_job(
                    show_slug=show_slug,
                    job_id=str(job["job_id"]),
                    state=STATE_GENERATED,
                    actor=options.actor,
                    note="Generate command completed with local outputs and no pending request logs.",
                    details={"run_id": run_id, "progress": latest_progress},
                )
            else:
                return _finalize_failure(
                    store=store,
                    job=job,
                    show_slug=show_slug,
                    manifest=manifest,
                    run_id=run_id,
                    options=options,
                    failed_state=STATE_FAILED_RETRYABLE,
                    note="Generate command completed without creating request logs or outputs.",
                )

        if options.run_download and str(job.get("state") or "") in {
            STATE_WAITING_FOR_ARTIFACT,
            STATE_GENERATED,
            STATE_DOWNLOADING,
        }:
            if str(job.get("state") or "") != STATE_DOWNLOADING:
                job = store.transition_job(
                    show_slug=show_slug,
                    job_id=str(job["job_id"]),
                    state=STATE_DOWNLOADING,
                    actor=options.actor,
                    note="Starting download command.",
                    details={"run_id": run_id},
                )
            download_command = adapter.build_download_command(
                options.repo_root,
                lecture_key=lecture_key,
                dry_run=False,
                timeout_seconds=options.artifact_wait_timeout_seconds,
                interval_seconds=options.artifact_poll_interval_seconds,
            )
            phase = _run_phase(
                name="download",
                command=download_command,
                repo_root=options.repo_root,
                timeout_seconds=options.phase_timeout_seconds,
            )
            manifest["phases"].append(phase)
            if phase["returncode"] != 0:
                return _finalize_failure(
                    store=store,
                    job=job,
                    show_slug=show_slug,
                    manifest=manifest,
                    run_id=run_id,
                    options=options,
                    failed_state=STATE_FAILED_RETRYABLE,
                    note="Download command failed.",
                )
            latest_progress = _collect_output_progress(
                adapter=adapter,
                repo_root=options.repo_root,
                lecture_key=lecture_key,
                content_types=content_types,
            )
            phase["progress"] = latest_progress
            if latest_progress["pending_request_count"] > 0:
                next_retry_at = _next_poll_at(poll_interval_seconds=options.artifact_poll_interval_seconds)
                if _has_unpublished_outputs(job=job, progress=latest_progress):
                    job = store.transition_job(
                        show_slug=show_slug,
                        job_id=str(job["job_id"]),
                        state=STATE_AWAITING_PUBLISH,
                        actor=options.actor,
                        note="Download phase produced unpublished outputs while other artifacts remain pending.",
                        retry_at=next_retry_at,
                        details={"run_id": run_id, "progress": latest_progress},
                    )
                    manifest["status"] = "completed"
                else:
                    job = store.transition_job(
                        show_slug=show_slug,
                        job_id=str(job["job_id"]),
                        state=STATE_WAITING_FOR_ARTIFACT,
                        actor=options.actor,
                        note="Download window ended with pending NotebookLM artifacts; scheduling another poll.",
                        retry_at=next_retry_at,
                        details={"run_id": run_id, "progress": latest_progress},
                    )
                    manifest["status"] = "waiting"
                manifest["completed_at"] = utc_now_iso()
                manifest["final_state"] = str(job.get("state") or "")
                return _finalize_execution_manifest(
                    store=store,
                    job=job,
                    show_slug=show_slug,
                    manifest=manifest,
                    run_id=run_id,
                    progress=latest_progress,
                )
            if latest_progress["existing_output_count"] <= 0:
                return _finalize_failure(
                    store=store,
                    job=job,
                    show_slug=show_slug,
                    manifest=manifest,
                    run_id=run_id,
                    options=options,
                    failed_state=STATE_FAILED_RETRYABLE,
                    note="Download command completed without resolving request logs or producing outputs.",
                )
            job = store.transition_job(
                show_slug=show_slug,
                job_id=str(job["job_id"]),
                state=STATE_AWAITING_PUBLISH,
                actor=options.actor,
                note="Download command completed successfully.",
                details={"run_id": run_id, "progress": latest_progress},
            )

        manifest["status"] = "completed"
        manifest["completed_at"] = utc_now_iso()
        manifest["final_state"] = str(job.get("state") or "")
        return _finalize_execution_manifest(
            store=store,
            job=job,
            show_slug=show_slug,
            manifest=manifest,
            run_id=run_id,
            progress=latest_progress,
        )


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
        if state in {STATE_QUEUED, STATE_RETRY_SCHEDULED}:
            return store.transition_job(
                show_slug=show_slug,
                job_id=job_id,
                state=STATE_GENERATING,
                actor=actor,
                note="Starting execution for explicitly selected job.",
                expected_states={STATE_QUEUED, STATE_RETRY_SCHEDULED},
                increment_attempt=True,
            )
        return job

    now = datetime.now(tz=UTC)
    resumable_states = {
        STATE_DOWNLOADING,
        STATE_WAITING_FOR_ARTIFACT,
        STATE_GENERATED,
        STATE_GENERATING,
    }
    resumable: list[dict[str, Any]] = []
    for entry in store.list_jobs(show_slug=show_slug):
        state = str(entry.get("state") or "")
        if state not in resumable_states:
            continue
        if state == STATE_WAITING_FOR_ARTIFACT:
            retry_at = parse_utcish_iso(str(entry.get("next_retry_at") or "").strip())
            if retry_at is not None and retry_at > now:
                continue
        resumable.append(entry)
    if resumable:
        state_rank = {
            STATE_DOWNLOADING: 0,
            STATE_WAITING_FOR_ARTIFACT: 1,
            STATE_GENERATED: 2,
            STATE_GENERATING: 3,
        }
        resumable.sort(
            key=lambda entry: (
                int(state_rank.get(str(entry.get("state") or ""), 99)),
                int(entry.get("priority") or 100),
                str(entry.get("created_at") or ""),
                str(entry.get("job_id") or ""),
            )
        )
        return store.load_job(show_slug=show_slug, job_id=str(resumable[0]["job_id"]))

    claimed = store.claim_next_job(
        show_slug=show_slug,
        ready_states={STATE_QUEUED, STATE_RETRY_SCHEDULED},
        target_state=STATE_GENERATING,
        actor=actor,
    )
    if claimed is None:
        raise FileNotFoundError(f"No runnable job found for show: {show_slug}")
    return claimed


def _run_phase(*, name: str, command: list[str], repo_root: Path, timeout_seconds: int) -> dict[str, Any]:
    return run_phase_command(
        name=name,
        command=command,
        cwd=repo_root,
        timeout_seconds=timeout_seconds,
    )


def _finalize_failure(
    *,
    store: QueueStore,
    job: dict[str, Any],
    show_slug: str,
    manifest: dict[str, Any],
    run_id: str,
    options: ExecutionOptions,
    failed_state: str,
    note: str,
) -> dict[str, Any]:
    failed_phase = manifest["phases"][-1]
    error_text = _phase_primary_error_text(failed_phase, note)
    retry_at = _derived_retry_at(
        explicit_retry_at=options.retry_at,
        error_text=_phase_retry_detection_text(failed_phase, note),
        attempt_count=max(int(job.get("attempt_count") or 0), 1),
    )
    effective_failed_state = failed_state
    if retry_at and failed_state == STATE_FAILED_RETRYABLE:
        effective_failed_state = STATE_RETRY_SCHEDULED
    manifest["status"] = "failed"
    manifest["completed_at"] = utc_now_iso()
    manifest["final_state"] = effective_failed_state
    manifest["last_error"] = error_text
    manifest_path = store.save_run_manifest(
        show_slug=show_slug,
        job_id=str(job["job_id"]),
        payload=manifest,
        run_id=run_id,
    )
    updated = store.transition_job(
        show_slug=show_slug,
        job_id=str(job["job_id"]),
        state=effective_failed_state,
        actor=options.actor,
        note=note,
        error=str(manifest["last_error"]),
        retry_at=retry_at,
        details={"run_id": run_id, "manifest_path": manifest_path},
    )
    artifacts = dict(updated.get("artifacts") or {})
    execution = dict(artifacts.get("execution") or {})
    execution.update(
        {
            "latest_run_manifest": manifest_path,
            "latest_run_id": run_id,
            "last_failure_at": manifest["completed_at"],
        }
    )
    alert_payload = emit_failure_alert(
        store=store,
        show_slug=show_slug,
        job=updated,
        manifest=manifest,
        failed_state=effective_failed_state,
        error_text=manifest["last_error"],
        note=note,
    )
    if alert_payload:
        execution["latest_alert_path"] = str(alert_payload.get("alert_path") or "")
        execution["latest_alert_kind"] = str(alert_payload.get("kind") or "")
        execution["latest_alert_at"] = str(alert_payload.get("occurred_at") or "")
    artifacts["execution"] = execution
    updated["artifacts"] = artifacts
    store.save_job(updated)
    return {
        "run_id": run_id,
        "job_id": str(updated["job_id"]),
        "show_slug": show_slug,
        "final_state": effective_failed_state,
        "manifest_path": manifest_path,
        "phases": manifest["phases"],
        "error": manifest["last_error"],
    }
