"""Execution service for queue-owned NotebookLM generation and download phases."""

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters import get_show_adapter
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
from .store import QueueStore, utc_now_iso


@dataclass(frozen=True, slots=True)
class ExecutionOptions:
    repo_root: Path
    retry_at: str | None = None
    actor: str = "system"
    run_download: bool = True


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

    claimed = store.claim_next_job(show_slug=show_slug, target_state=STATE_GENERATING, actor=actor)
    if claimed is None:
        raise FileNotFoundError(f"No runnable job found for show: {show_slug}")
    return claimed


def _run_phase(*, name: str, command: list[str], repo_root: Path) -> dict[str, Any]:
    started_at = utc_now_iso()
    completed = subprocess.run(
        command,
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )
    completed_at = utc_now_iso()
    return {
        "name": name,
        "command": command,
        "command_shell": shlex.join(command),
        "started_at": started_at,
        "completed_at": completed_at,
        "returncode": int(completed.returncode),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


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
    manifest["status"] = "failed"
    manifest["completed_at"] = utc_now_iso()
    manifest["final_state"] = failed_state
    manifest["last_error"] = failed_phase.get("stderr") or failed_phase.get("stdout") or note
    manifest_path = store.save_run_manifest(
        show_slug=show_slug,
        job_id=str(job["job_id"]),
        payload=manifest,
        run_id=run_id,
    )
    updated = store.transition_job(
        show_slug=show_slug,
        job_id=str(job["job_id"]),
        state=failed_state,
        actor=options.actor,
        note=note,
        error=str(manifest["last_error"]),
        retry_at=options.retry_at,
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
    artifacts["execution"] = execution
    updated["artifacts"] = artifacts
    store.save_job(updated)
    return {
        "run_id": run_id,
        "job_id": str(updated["job_id"]),
        "show_slug": show_slug,
        "final_state": failed_state,
        "manifest_path": manifest_path,
        "phases": manifest["phases"],
        "error": manifest["last_error"],
    }
