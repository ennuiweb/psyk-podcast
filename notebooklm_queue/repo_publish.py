"""Commit and push queue-owned generated repo artifacts."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters import get_show_adapter
from .constants import STATE_COMMITTING_REPO_ARTIFACTS, STATE_FAILED_RETRYABLE, STATE_REPO_PUSHED
from .processes import ProcessResult, run_process
from .show_artifacts import resolve_show_artifact_paths
from .show_config import ShowConfigSelectionError, load_show_config, resolve_manifest_bound_show_config_path
from .store import QueueStore, utc_now_iso


@dataclass(frozen=True, slots=True)
class RepoPublishOptions:
    repo_root: Path
    actor: str = "system"
    remote: str = "origin"
    branch: str = "main"
    git_user_name: str = "NotebookLM Queue"
    git_user_email: str = "queue@localhost"
    max_push_attempts: int = 3
    show_config_path: Path | None = None
    git_timeout_seconds: int = int(os.environ.get("NOTEBOOKLM_QUEUE_GIT_TIMEOUT_SECONDS") or "300")


def publish_repo_artifacts(
    *,
    store: QueueStore,
    show_slug: str,
    options: RepoPublishOptions,
    job_id: str | None = None,
) -> dict[str, Any]:
    adapter = get_show_adapter(show_slug)
    with store.acquire_show_lock(show_slug):
        job = _claim_or_resume_job(store=store, show_slug=show_slug, job_id=job_id, actor=options.actor)
        manifest_path = _latest_publish_manifest_path(store=store, job=job)
        manifest = _load_publish_manifest(manifest_path)
        bundle_id = str(manifest.get("bundle_id") or job.get("artifacts", {}).get("publish", {}).get("latest_bundle_id") or "")
        if not bundle_id:
            raise RuntimeError(f"Missing bundle_id for repo publish job {job['job_id']}")

        try:
            publish_result = _commit_and_push_show_artifacts(
                repo_root=options.repo_root,
                show_slug=show_slug,
                options=options,
                adapter=adapter,
                job=job,
                manifest=manifest,
            )
        except ShowConfigSelectionError as exc:
            return _finalize_failure(
                store=store,
                job=job,
                manifest=manifest,
                bundle_id=bundle_id,
                actor=options.actor,
                error_message=str(exc),
            )
        except RepoPublishError as exc:
            return _finalize_failure(
                store=store,
                job=job,
                manifest=manifest,
                bundle_id=bundle_id,
                actor=options.actor,
                error_message=str(exc),
            )

        publish_payload = dict(manifest.get("repo_publish") or {})
        publish_payload.update(publish_result)
        publish_payload["status"] = "completed"
        publish_payload["completed_at"] = utc_now_iso()
        manifest["repo_publish"] = publish_payload
        manifest["status"] = "repo_pushed"
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
            state=STATE_REPO_PUSHED,
            actor=options.actor,
            note="Committed and pushed queue-owned repo artifacts.",
            details={
                "bundle_id": bundle_id,
                "manifest_path": manifest_path_rel,
                "commit_sha": publish_result["head_sha"],
                "pushed": publish_result["pushed"],
            },
        )
        updated = _persist_repo_publish_artifacts(
            store=store,
            job=updated,
            manifest_path=manifest_path_rel,
            commit_sha=str(publish_result["head_sha"]),
            pushed=bool(publish_result["pushed"]),
        )
        return {
            "job_id": str(updated["job_id"]),
            "show_slug": show_slug,
            "bundle_id": bundle_id,
            "final_state": str(updated.get("state") or ""),
            "manifest_path": manifest_path_rel,
            "commit_sha": publish_result["head_sha"],
            "pushed": publish_result["pushed"],
            "push_attempts": publish_result["push_attempts"],
            "resolved_rebase_conflicts": publish_result["resolved_rebase_conflicts"],
        }


class RepoPublishError(RuntimeError):
    """Raised when queue-owned repo publication cannot proceed safely."""


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
        if state != STATE_COMMITTING_REPO_ARTIFACTS:
            raise ValueError(
                f"Job {job_id} is in state {state}, expected {STATE_COMMITTING_REPO_ARTIFACTS}."
            )
        return job

    candidates = [
        entry
        for entry in store.list_jobs(show_slug=show_slug)
        if str(entry.get("state") or "") == STATE_COMMITTING_REPO_ARTIFACTS
    ]
    if not candidates:
        raise FileNotFoundError(f"No committing_repo_artifacts job found for show: {show_slug}")
    candidates.sort(
        key=lambda item: (
            int(item.get("priority") or 100),
            str(item.get("created_at") or ""),
            str(item.get("job_id") or ""),
        )
    )
    return store.load_job(show_slug=show_slug, job_id=str(candidates[0]["job_id"]))


def _commit_and_push_show_artifacts(
    *,
    repo_root: Path,
    show_slug: str,
    options: RepoPublishOptions,
    adapter,
    job: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    allowlist = _allowed_paths(
        repo_root=repo_root,
        show_slug=show_slug,
        adapter=adapter,
        manifest=manifest,
        requested_show_config_path=options.show_config_path,
    )
    status_entries = _git_status(repo_root, timeout_seconds=options.git_timeout_seconds)
    unexpected_tracked = [
        entry["path"]
        for entry in status_entries
        if entry["tracked"] and entry["path"] not in allowlist
    ]
    if unexpected_tracked:
        raise RepoPublishError(
            f"Unexpected tracked repo changes outside the queue allowlist: {', '.join(sorted(unexpected_tracked))}"
        )

    changed_allowed = [entry["path"] for entry in status_entries if entry["path"] in allowlist]
    if changed_allowed:
        _run_git(
            repo_root,
            ["git", "add", "--", *sorted(changed_allowed)],
            timeout_seconds=options.git_timeout_seconds,
        )
        _run_git(
            repo_root,
            [
                "git",
                "-c",
                f"user.name={options.git_user_name}",
                "-c",
                f"user.email={options.git_user_email}",
                "commit",
                "-m",
                f"queue: publish {show_slug} {job['lecture_key']}",
            ],
            timeout_seconds=options.git_timeout_seconds,
        )

    branch = options.branch
    max_attempts = max(int(options.max_push_attempts), 1)
    pushed = False
    resolved_conflicts: list[str] = []
    local_head = _run_git(repo_root, ["git", "rev-parse", "HEAD"], timeout_seconds=options.git_timeout_seconds).stdout.strip()
    attempts_used = 0
    for attempt in range(1, max_attempts + 1):
        attempts_used = attempt
        _run_git(repo_root, ["git", "fetch", options.remote, branch], timeout_seconds=options.git_timeout_seconds)
        resolved_conflicts.extend(
            _pull_rebase_with_conflict_resolution(
                repo_root=repo_root,
                remote=options.remote,
                branch=branch,
                allowlist=allowlist,
                timeout_seconds=options.git_timeout_seconds,
            )
        )
        local_head = _run_git(repo_root, ["git", "rev-parse", "HEAD"], timeout_seconds=options.git_timeout_seconds).stdout.strip()
        remote_head = _run_git(
            repo_root,
            ["git", "rev-parse", f"{options.remote}/{branch}"],
            timeout_seconds=options.git_timeout_seconds,
        ).stdout.strip()
        if local_head == remote_head:
            break
        push_completed = _run_git_raw(
            repo_root,
            ["git", "push", options.remote, f"HEAD:{branch}"],
            timeout_seconds=options.git_timeout_seconds,
        )
        if push_completed.returncode == 0:
            pushed = True
            local_head = _run_git(repo_root, ["git", "rev-parse", "HEAD"], timeout_seconds=options.git_timeout_seconds).stdout.strip()
            break
        if attempt >= max_attempts:
            raise RepoPublishError(
                f"Failed to push allowlisted repo artifacts after {max_attempts} attempts: "
                f"{push_completed.stderr.strip() or push_completed.stdout.strip()}"
            )

    return {
        "status": "completed",
        "head_sha": local_head,
        "branch": branch,
        "remote": options.remote,
        "pushed": pushed,
        "push_attempts": attempts_used,
        "allowlist_paths": sorted(allowlist),
        "changed_allowlist_paths": sorted(changed_allowed),
        "resolved_rebase_conflicts": sorted(set(resolved_conflicts)),
    }


def _allowed_paths(
    *,
    repo_root: Path,
    show_slug: str,
    adapter,
    manifest: dict[str, Any],
    requested_show_config_path: Path | None,
) -> set[str]:
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
    artifact_paths = resolve_show_artifact_paths(
        repo_root=repo_root,
        show_slug=show_slug,
        config=config,
    )
    allowlist = {
        str(artifact_paths.feed_path.relative_to(repo_root)),
        str(artifact_paths.inventory_path.relative_to(repo_root)),
        str(artifact_paths.quiz_links_path.relative_to(repo_root)),
        str(artifact_paths.spotify_map_path.relative_to(repo_root)),
        str(artifact_paths.content_manifest_path.relative_to(repo_root)),
    }
    if artifact_paths.media_manifest_path is not None:
        allowlist.add(str(artifact_paths.media_manifest_path.relative_to(repo_root)))
    return allowlist


def _git_status(repo_root: Path, *, timeout_seconds: int) -> list[dict[str, Any]]:
    result = _run_git(
        repo_root,
        ["git", "status", "--porcelain", "--untracked-files=all"],
        timeout_seconds=timeout_seconds,
    )
    entries: list[dict[str, Any]] = []
    for raw_line in result.stdout.splitlines():
        if not raw_line:
            continue
        status = raw_line[:2]
        path = raw_line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        tracked = status != "??"
        entries.append({"status": status, "path": path, "tracked": tracked})
    return entries


def _run_git(repo_root: Path, command: list[str], *, timeout_seconds: int) -> ProcessResult:
    completed = _run_git_raw(repo_root, command, timeout_seconds=timeout_seconds)
    if completed.returncode != 0:
        raise RepoPublishError(
            f"Git command failed ({' '.join(command)}): {completed.stderr.strip() or completed.stdout.strip()}"
        )
    return completed


def _run_git_raw(
    repo_root: Path,
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout_seconds: int,
) -> ProcessResult:
    git_env = dict(os.environ)
    if env:
        git_env.update(env)
    return run_process(
        command,
        cwd=repo_root,
        env=git_env,
        timeout_seconds=timeout_seconds,
    )


def _pull_rebase_with_conflict_resolution(
    *,
    repo_root: Path,
    remote: str,
    branch: str,
    allowlist: set[str],
    timeout_seconds: int,
) -> list[str]:
    completed = _run_git_raw(repo_root, ["git", "pull", "--rebase", remote, branch], timeout_seconds=timeout_seconds)
    if completed.returncode == 0:
        return []
    return _resolve_rebase_conflicts(repo_root=repo_root, allowlist=allowlist, timeout_seconds=timeout_seconds)


def _resolve_rebase_conflicts(*, repo_root: Path, allowlist: set[str], timeout_seconds: int) -> list[str]:
    completed = _run_git_raw(repo_root, ["git", "diff", "--name-only", "--diff-filter=U"], timeout_seconds=timeout_seconds)
    conflicted_files = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if not conflicted_files:
        _run_git_raw(repo_root, ["git", "rebase", "--abort"], timeout_seconds=timeout_seconds)
        raise RepoPublishError("Rebase failed without conflicted files.")

    resolved: list[str] = []
    for conflicted in conflicted_files:
        if conflicted not in allowlist:
            _run_git_raw(repo_root, ["git", "rebase", "--abort"], timeout_seconds=timeout_seconds)
            raise RepoPublishError(f"Unexpected rebase conflict outside the queue allowlist: {conflicted}")
        # During rebase, "theirs" is the queue-generated commit being replayed.
        _run_git(repo_root, ["git", "checkout", "--theirs", "--", conflicted], timeout_seconds=timeout_seconds)
        _run_git(repo_root, ["git", "add", "--", conflicted], timeout_seconds=timeout_seconds)
        resolved.append(conflicted)

    continued = _run_git_raw(
        repo_root,
        ["git", "rebase", "--continue"],
        env={"GIT_EDITOR": "true"},
        timeout_seconds=timeout_seconds,
    )
    if continued.returncode != 0:
        _run_git_raw(repo_root, ["git", "rebase", "--abort"], timeout_seconds=timeout_seconds)
        raise RepoPublishError(
            f"Failed to continue rebase after resolving generated-file conflicts: "
            f"{continued.stderr.strip() or continued.stdout.strip()}"
        )
    return resolved


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


def _persist_repo_publish_artifacts(
    *,
    store: QueueStore,
    job: dict[str, Any],
    manifest_path: str,
    commit_sha: str,
    pushed: bool,
) -> dict[str, Any]:
    artifacts = dict(job.get("artifacts") or {})
    publish = dict(artifacts.get("publish") or {})
    publish.update(
        {
            "latest_bundle_manifest": manifest_path,
            "last_repo_publish_at": utc_now_iso(),
            "last_repo_commit_sha": commit_sha,
            "last_repo_push_performed": bool(pushed),
        }
    )
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
    payload = dict(manifest.get("repo_publish") or {})
    payload["status"] = "failed"
    payload["completed_at"] = utc_now_iso()
    payload["last_error"] = error_message
    manifest["repo_publish"] = payload
    manifest["status"] = "repo_publish_failed"
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
        note="Repo publish failed.",
        error=error_message,
        details={"bundle_id": bundle_id, "manifest_path": manifest_path},
    )
    _persist_repo_publish_artifacts(
        store=store,
        job=updated,
        manifest_path=manifest_path,
        commit_sha="",
        pushed=False,
    )
    return {
        "bundle_id": bundle_id,
        "job_id": str(updated["job_id"]),
        "show_slug": str(updated["show_slug"]),
        "final_state": str(updated.get("state") or ""),
        "manifest_path": manifest_path,
        "error": error_message,
    }
