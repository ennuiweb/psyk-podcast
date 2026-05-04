"""Execution service for queue-owned NotebookLM generation and download phases."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters import get_show_adapter
from .alerts import emit_failure_alert
from .constants import (
    STATE_AWAITING_PUBLISH,
    STATE_DOWNLOADED,
    STATE_DOWNLOADING,
    STATE_FAILED_RETRYABLE,
    STATE_GENERATED,
    STATE_GENERATING,
    STATE_QUEUED,
    STATE_RETRY_SCHEDULED,
)
from .processes import run_phase_command
from .store import QueueStore, utc_now_iso

RATE_LIMIT_ERROR_TOKENS = (
    "rate limit",
    "quota exceeded",
    "resource_exhausted",
    "429",
    "too many requests",
)
DEFAULT_RATE_LIMIT_RETRY_SECONDS = int(
    os.environ.get("NOTEBOOKLM_QUEUE_RATE_LIMIT_RETRY_SECONDS") or "900"
)
DEFAULT_EXECUTION_PHASE_TIMEOUT_SECONDS = int(
    os.environ.get("NOTEBOOKLM_QUEUE_EXECUTION_PHASE_TIMEOUT_SECONDS") or "7200"
)


@dataclass(frozen=True, slots=True)
class ExecutionOptions:
    repo_root: Path
    retry_at: str | None = None
    actor: str = "system"
    run_download: bool = True
    phase_timeout_seconds: int = DEFAULT_EXECUTION_PHASE_TIMEOUT_SECONDS


def _looks_like_rate_limit(message: str | None) -> bool:
    text = str(message or "").lower()
    return any(token in text for token in RATE_LIMIT_ERROR_TOKENS)


def _derived_retry_at(*, explicit_retry_at: str | None, error_text: str | None) -> str | None:
    if explicit_retry_at:
        return explicit_retry_at
    if not _looks_like_rate_limit(error_text):
        return None
    retry_at = datetime.now(tz=UTC) + timedelta(seconds=max(DEFAULT_RATE_LIMIT_RETRY_SECONDS, 1))
    return retry_at.replace(microsecond=0).isoformat()


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
        if current_state in {STATE_QUEUED, STATE_RETRY_SCHEDULED, STATE_GENERATING}:
            generate_command = adapter.build_generate_command(
                options.repo_root,
                lecture_key=lecture_key,
                content_types=content_types,
                dry_run=False,
                wait=True,
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
            job = store.transition_job(
                show_slug=show_slug,
                job_id=str(job["job_id"]),
                state=STATE_GENERATED,
                actor=options.actor,
                note="Generate command completed successfully.",
                details={"run_id": run_id},
            )

        if options.run_download and str(job.get("state") or "") in {STATE_GENERATED, STATE_DOWNLOADING}:
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
            final_state = STATE_DOWNLOADED
            if options.run_download:
                final_state = STATE_AWAITING_PUBLISH
            job = store.transition_job(
                show_slug=show_slug,
                job_id=str(job["job_id"]),
                state=final_state,
                actor=options.actor,
                note="Download command completed successfully.",
                details={"run_id": run_id},
            )

        manifest["status"] = "completed"
        manifest["completed_at"] = utc_now_iso()
        manifest["final_state"] = str(job.get("state") or "")
        manifest_path = store.save_run_manifest(
            show_slug=show_slug,
            job_id=str(job["job_id"]),
            payload=manifest,
            run_id=run_id,
        )
        job = store.load_job(show_slug=show_slug, job_id=str(job["job_id"]))
        artifacts = dict(job.get("artifacts") or {})
        execution = dict(artifacts.get("execution") or {})
        execution.update(
            {
                "latest_run_manifest": manifest_path,
                "latest_run_id": run_id,
                "last_success_at": manifest["completed_at"],
                "last_generate_command": manifest["phases"][0]["command"] if manifest["phases"] else None,
                "last_download_command": manifest["phases"][1]["command"]
                if len(manifest["phases"]) > 1
                else None,
            }
        )
        artifacts["execution"] = execution
        job["artifacts"] = artifacts
        store.save_job(job)
        return {
            "run_id": run_id,
            "job_id": str(job["job_id"]),
            "show_slug": show_slug,
            "final_state": str(job.get("state") or ""),
            "manifest_path": manifest_path,
            "phases": manifest["phases"],
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

    resumable_states = {STATE_DOWNLOADING, STATE_GENERATED, STATE_GENERATING}
    resumable = [entry for entry in store.list_jobs(show_slug=show_slug) if str(entry.get("state") or "") in resumable_states]
    if resumable:
        state_rank = {
            STATE_DOWNLOADING: 0,
            STATE_GENERATED: 1,
            STATE_GENERATING: 2,
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
    error_text = failed_phase.get("stderr") or failed_phase.get("stdout") or note
    retry_at = _derived_retry_at(
        explicit_retry_at=options.retry_at,
        error_text=error_text,
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
