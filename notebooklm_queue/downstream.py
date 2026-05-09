"""Observe post-push downstream actions and complete queue-owned publication."""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime, timedelta
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters import get_show_adapter
from .constants import (
    STATE_COMPLETED,
    STATE_FAILED_RETRYABLE,
    STATE_REPO_PUSHED,
    STATE_SYNCING_DOWNSTREAM,
    STATE_WAITING_FOR_ARTIFACT,
)
from .processes import run_process
from .show_config import ShowConfigSelectionError, load_show_config, resolve_manifest_bound_show_config_path
from .show_runtime import QueueShowPolicies, resolve_queue_show_policies
from .store import QueueStore, parse_utcish_iso, utc_now_iso
DEFAULT_ARTIFACT_POLL_INTERVAL_SECONDS = int(os.environ.get("NOTEBOOKLM_QUEUE_ARTIFACT_POLL_INTERVAL_SECONDS") or "60")


@dataclass(frozen=True, slots=True)
class DownstreamOptions:
    repo_root: Path
    actor: str = "system"
    gh_bin: str = os.environ.get("NOTEBOOKLM_QUEUE_GH_BIN") or "gh"
    timeout_seconds: int = int(os.environ.get("NOTEBOOKLM_QUEUE_DOWNSTREAM_TIMEOUT_SECONDS") or "900")
    poll_interval_seconds: int = int(os.environ.get("NOTEBOOKLM_QUEUE_DOWNSTREAM_POLL_SECONDS") or "10")
    gh_timeout_seconds: int = int(os.environ.get("NOTEBOOKLM_QUEUE_GH_TIMEOUT_SECONDS") or "60")
    freudd_workflow_file: str = (
        os.environ.get("NOTEBOOKLM_QUEUE_FREUDD_DEPLOY_WORKFLOW_FILE") or "deploy-freudd-portal.yml"
    )


@dataclass(frozen=True, slots=True)
class DownstreamTarget:
    name: str
    workflow_file: str
    changed_paths: tuple[str, ...]


class DownstreamSyncError(RuntimeError):
    """Raised when a downstream synchronization step fails or cannot be verified."""


def sync_downstream_publication(
    *,
    store: QueueStore,
    show_slug: str,
    options: DownstreamOptions,
    job_id: str | None = None,
) -> dict[str, Any]:
    with store.acquire_show_lock(show_slug):
        job = _claim_or_resume_job(store=store, show_slug=show_slug, job_id=job_id, actor=options.actor)
        manifest_path = _latest_publish_manifest_path(store=store, job=job)
        manifest = _load_publish_manifest(manifest_path)
        bundle_id = str(manifest.get("bundle_id") or job.get("artifacts", {}).get("publish", {}).get("latest_bundle_id") or "")
        if not bundle_id:
            raise RuntimeError(f"Missing bundle_id for downstream sync job {job['job_id']}")
        adapter = get_show_adapter(show_slug)
        try:
            resolved_show_config_path = resolve_manifest_bound_show_config_path(
                repo_root=options.repo_root,
                default_path=adapter.show_config_path,
                manifest=manifest,
                override_path=None,
            )
            config = load_show_config(
                repo_root=options.repo_root,
                default_path=adapter.show_config_path,
                override_path=resolved_show_config_path,
            )
            queue_policies = resolve_queue_show_policies(show_slug=show_slug, config=config)
        except (ShowConfigSelectionError, ValueError) as exc:
            return _finalize_failure(
                store=store,
                job=job,
                manifest=manifest,
                bundle_id=bundle_id,
                actor=options.actor,
                error_message=str(exc),
            )
        commit_sha = _resolve_commit_sha(job=job, manifest=manifest)
        targets = _build_targets(
            show_slug=show_slug,
            manifest=manifest,
            queue_policies=queue_policies,
            options=options,
        )

        downstream_payload: dict[str, Any] = {
            "status": "running",
            "started_at": utc_now_iso(),
            "commit_sha": commit_sha,
            "targets": [],
        }
        manifest["downstream"] = downstream_payload

        try:
            for target in targets:
                result = _wait_for_workflow_target(repo_root=options.repo_root, commit_sha=commit_sha, target=target, options=options)
                downstream_payload["targets"].append(result)
        except DownstreamSyncError as exc:
            return _finalize_failure(
                store=store,
                job=job,
                manifest=manifest,
                bundle_id=bundle_id,
                actor=options.actor,
                error_message=str(exc),
            )

        downstream_payload["status"] = "completed"
        downstream_payload["completed_at"] = utc_now_iso()
        pending_request_count = _bundle_pending_request_count(manifest)
        final_state = STATE_COMPLETED
        note = "Downstream publication validated successfully."
        retry_at: str | None = None
        manifest["status"] = "completed"
        if pending_request_count > 0:
            final_state = STATE_WAITING_FOR_ARTIFACT
            note = "Partial publish completed; waiting for remaining NotebookLM artifacts."
            retry_at = _resume_retry_at(job)
            manifest["status"] = "waiting_for_artifact"
        manifest["completed_at"] = utc_now_iso()
        manifest_path_rel = store.save_publish_manifest(
            show_slug=show_slug,
            job_id=str(job["job_id"]),
            payload=manifest,
            bundle_id=bundle_id,
        )
        updated = store.transition_job(
            show_slug=show_slug,
            job_id=str(job["job_id"]),
            state=final_state,
            actor=options.actor,
            note=note,
            details={
                "bundle_id": bundle_id,
                "manifest_path": manifest_path_rel,
                "commit_sha": commit_sha,
                "target_count": len(targets),
            },
            retry_at=retry_at,
            expected_states={STATE_SYNCING_DOWNSTREAM},
        )
        updated = _persist_downstream_artifacts(
            store=store,
            job=updated,
            manifest_path=manifest_path_rel,
            commit_sha=commit_sha,
            targets=downstream_payload["targets"],
            bundle_hash=_bundle_hash(manifest),
        )
        return {
            "job_id": str(updated["job_id"]),
            "show_slug": show_slug,
            "bundle_id": bundle_id,
            "commit_sha": commit_sha,
            "final_state": str(updated.get("state") or ""),
            "manifest_path": manifest_path_rel,
            "targets": downstream_payload["targets"],
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
        if state == STATE_REPO_PUSHED:
            return store.transition_job(
                show_slug=show_slug,
                job_id=job_id,
                state=STATE_SYNCING_DOWNSTREAM,
                actor=actor,
                note="Synchronizing downstream publication for explicitly selected job.",
                expected_states={STATE_REPO_PUSHED},
            )
        if state != STATE_SYNCING_DOWNSTREAM:
            raise ValueError(
                f"Job {job_id} is in state {state}, expected {STATE_REPO_PUSHED} or {STATE_SYNCING_DOWNSTREAM}."
            )
        return job

    resumable = [
        entry
        for entry in store.list_jobs(show_slug=show_slug)
        if str(entry.get("state") or "") == STATE_SYNCING_DOWNSTREAM
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
        if str(entry.get("state") or "") == STATE_REPO_PUSHED
    ]
    if not candidates:
        raise FileNotFoundError(f"No repo_pushed job found for show: {show_slug}")
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
        state=STATE_SYNCING_DOWNSTREAM,
        actor=actor,
        note="Claimed next repo_pushed job for downstream sync.",
        expected_states={STATE_REPO_PUSHED},
    )


def _build_targets(
    *,
    show_slug: str,
    manifest: dict[str, Any],
    queue_policies: QueueShowPolicies,
    options: DownstreamOptions,
) -> list[DownstreamTarget]:
    changed_paths = tuple(
        str(path)
        for path in (manifest.get("repo_publish") or {}).get("changed_allowlist_paths") or []
        if isinstance(path, str) and path.strip()
    )
    if not queue_policies.downstream_freudd_deploy:
        return []
    freudd_paths = {
        f"shows/{show_slug}/content_manifest.json",
        f"shows/{show_slug}/quiz_links.json",
        f"shows/{show_slug}/spotify_map.json",
    }
    matched = tuple(path for path in changed_paths if path in freudd_paths)
    if not matched:
        return []
    return [
        DownstreamTarget(
            name="freudd_deploy",
            workflow_file=options.freudd_workflow_file,
            changed_paths=matched,
        )
    ]


def _wait_for_workflow_target(
    *,
    repo_root: Path,
    commit_sha: str,
    target: DownstreamTarget,
    options: DownstreamOptions,
) -> dict[str, Any]:
    deadline = time.monotonic() + max(int(options.timeout_seconds), 1)
    last_status = "not_found"
    while time.monotonic() <= deadline:
        run = _find_workflow_run(
            repo_root=repo_root,
            commit_sha=commit_sha,
            workflow_file=target.workflow_file,
            gh_bin=options.gh_bin,
            timeout_seconds=options.gh_timeout_seconds,
        )
        if run is None:
            last_status = "not_found"
            time.sleep(max(int(options.poll_interval_seconds), 1))
            continue
        status = str(run.get("status") or "")
        conclusion = str(run.get("conclusion") or "")
        if status == "completed":
            if conclusion == "success":
                return {
                    "name": target.name,
                    "workflow_file": target.workflow_file,
                    "status": status,
                    "conclusion": conclusion,
                    "run_id": run.get("databaseId"),
                    "url": run.get("url"),
                    "changed_paths": list(target.changed_paths),
                }
            raise DownstreamSyncError(
                f"Downstream workflow failed for {target.name}: "
                f"status={status} conclusion={conclusion} url={run.get('url') or ''}".strip()
            )
        last_status = status or "in_progress"
        time.sleep(max(int(options.poll_interval_seconds), 1))
    raise DownstreamSyncError(
        f"Timed out waiting for downstream workflow {target.workflow_file} for commit {commit_sha} "
        f"(last_status={last_status})."
    )


def _find_workflow_run(
    *,
    repo_root: Path,
    commit_sha: str,
    workflow_file: str,
    gh_bin: str,
    timeout_seconds: int,
) -> dict[str, Any] | None:
    completed = run_process(
        [
            gh_bin,
            "run",
            "list",
            "--workflow",
            workflow_file,
            "--limit",
            "20",
            "--json",
            "databaseId,headSha,status,conclusion,url,workflowName,createdAt",
        ],
        cwd=repo_root,
        timeout_seconds=timeout_seconds,
    )
    if completed.returncode != 0:
        raise DownstreamSyncError(
            f"Failed to query downstream workflow runs with {gh_bin}: "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )
    try:
        payload = json.loads(completed.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise DownstreamSyncError(f"Invalid JSON from {gh_bin} run list: {exc}") from exc
    if not isinstance(payload, list):
        raise DownstreamSyncError(f"Unexpected payload from {gh_bin} run list for {workflow_file}")
    matches = [
        item
        for item in payload
        if isinstance(item, dict) and str(item.get("headSha") or "").strip() == commit_sha
    ]
    if not matches:
        return None
    matches.sort(key=lambda item: int(item.get("databaseId") or 0), reverse=True)
    return matches[0]


def _resolve_commit_sha(*, job: dict[str, Any], manifest: dict[str, Any]) -> str:
    commit_sha = str((manifest.get("repo_publish") or {}).get("head_sha") or "").strip()
    if commit_sha:
        return commit_sha
    commit_sha = str(((job.get("artifacts") or {}).get("publish") or {}).get("last_repo_commit_sha") or "").strip()
    if commit_sha:
        return commit_sha
    raise RuntimeError(f"Missing repo commit SHA for downstream sync job {job['job_id']}")


def _latest_publish_manifest_path(*, store: QueueStore, job: dict[str, Any]) -> Path:
    publish = dict((job.get("artifacts") or {}).get("publish") or {})
    relative = str(publish.get("latest_bundle_manifest") or "").strip()
    if not relative:
        raise RuntimeError(f"No publish manifest recorded for job {job['job_id']}")
    path = store.root / relative
    if not path.exists():
        raise RuntimeError(f"Publish manifest missing for job {job['job_id']}: {path}")
    return path


def _load_publish_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to load publish manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Publish manifest must be a JSON object: {path}")
    return payload


def _persist_downstream_artifacts(
    *,
    store: QueueStore,
    job: dict[str, Any],
    manifest_path: str,
    commit_sha: str,
    targets: list[dict[str, Any]],
    bundle_hash: str | None,
) -> dict[str, Any]:
    artifacts = dict(job.get("artifacts") or {})
    publish = dict(artifacts.get("publish") or {})
    publish.update(
        {
            "latest_bundle_manifest": manifest_path,
            "last_downstream_sync_at": utc_now_iso(),
            "last_downstream_commit_sha": commit_sha,
            "last_downstream_targets": targets,
        }
    )
    if bundle_hash:
        publish["last_completed_bundle_hash"] = bundle_hash
        publish["last_completed_publish_at"] = utc_now_iso()
    artifacts["publish"] = publish
    job["artifacts"] = artifacts
    store.save_job(job)
    return job


def _finalize_failure(
    *,
    store: QueueStore,
    job: dict[str, Any],
    manifest: dict[str, Any],
    bundle_id: str,
    actor: str,
    error_message: str,
) -> dict[str, Any]:
    downstream = dict(manifest.get("downstream") or {})
    downstream["status"] = "failed"
    downstream["completed_at"] = utc_now_iso()
    downstream["last_error"] = error_message
    manifest["downstream"] = downstream
    manifest["status"] = "downstream_failed"
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
        note="Downstream sync failed.",
        error=error_message,
        details={"bundle_id": bundle_id, "manifest_path": manifest_path},
        expected_states={STATE_SYNCING_DOWNSTREAM},
    )
    _persist_downstream_artifacts(
        store=store,
        job=updated,
        manifest_path=manifest_path,
        commit_sha=str(((job.get("artifacts") or {}).get("publish") or {}).get("last_repo_commit_sha") or ""),
        targets=[],
        bundle_hash=None,
    )
    return {
        "bundle_id": bundle_id,
        "job_id": str(updated["job_id"]),
        "show_slug": str(updated["show_slug"]),
        "final_state": str(updated.get("state") or ""),
        "manifest_path": manifest_path,
        "error": error_message,
    }


def _bundle_pending_request_count(manifest: dict[str, Any]) -> int:
    bundle = manifest.get("bundle")
    if not isinstance(bundle, dict):
        return 0
    return max(int(bundle.get("pending_request_count") or 0), 0)


def _bundle_hash(manifest: dict[str, Any]) -> str | None:
    bundle = manifest.get("bundle")
    if not isinstance(bundle, dict):
        return None
    value = str(bundle.get("bundle_hash") or "").strip()
    return value or None


def _resume_retry_at(job: dict[str, Any]) -> str:
    existing = parse_utcish_iso(str(job.get("next_retry_at") or "").strip())
    if existing is not None:
        return existing.replace(microsecond=0).isoformat()
    retry_at = datetime.now(tz=UTC) + timedelta(seconds=max(DEFAULT_ARTIFACT_POLL_INTERVAL_SECONDS, 1))
    return retry_at.replace(microsecond=0).isoformat()
