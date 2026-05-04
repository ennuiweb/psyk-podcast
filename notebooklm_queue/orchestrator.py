"""Service-oriented orchestration for draining one show queue through all ready stages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import time
from typing import Any, Callable

from .constants import BLOCKED_STATES, STATE_FAILED_RETRYABLE, STATE_RETRY_SCHEDULED, TERMINAL_STATES
from .discovery import enqueue_discovered_jobs
from .downstream import DownstreamOptions, sync_downstream_publication
from .execution import ExecutionOptions, execute_job
from .metadata import MetadataOptions, rebuild_repo_metadata
from .publish import PublishOptions, UploadOptions, prepare_publish_bundle, upload_publish_bundle
from .repo_publish import RepoPublishOptions, publish_repo_artifacts
from .show_config import serialize_show_config_path
from .store import QueueStore


@dataclass(frozen=True, slots=True)
class DrainShowOptions:
    repo_root: Path
    actor: str = "system"
    show_config_path: Path | None = None
    content_types: tuple[str, ...] | None = None
    discovery_priority: int = 100
    max_stage_runs: int = 50
    downstream_timeout_seconds: int = 900
    downstream_poll_interval_seconds: int = 10
    remote: str = "origin"
    branch: str = "main"


@dataclass(frozen=True, slots=True)
class ServeShowOptions:
    drain: DrainShowOptions


StageCallable = Callable[[], dict[str, Any]]


def drain_show_queue(
    *,
    store: QueueStore,
    show_slug: str,
    options: DrainShowOptions,
) -> dict[str, Any]:
    repo_root = options.repo_root.resolve()
    show_config_path = options.show_config_path.resolve() if options.show_config_path else None

    retry_ready = store.retry_ready_jobs(show_slug=show_slug)
    discovery = enqueue_discovered_jobs(
        repo_root=repo_root,
        store=store,
        show_slug=show_slug,
        content_types=options.content_types,
        show_config_path=show_config_path,
        priority=int(options.discovery_priority),
    )

    stages: tuple[tuple[str, StageCallable], ...] = (
        (
            "sync_downstream",
            lambda: sync_downstream_publication(
                store=store,
                show_slug=show_slug,
                options=DownstreamOptions(
                    repo_root=repo_root,
                    actor=options.actor,
                    timeout_seconds=int(options.downstream_timeout_seconds),
                    poll_interval_seconds=int(options.downstream_poll_interval_seconds),
                ),
            ),
        ),
        (
            "push_repo",
            lambda: publish_repo_artifacts(
                store=store,
                show_slug=show_slug,
                options=RepoPublishOptions(
                    repo_root=repo_root,
                    actor=options.actor,
                    remote=options.remote,
                    branch=options.branch,
                    show_config_path=show_config_path,
                ),
            ),
        ),
        (
            "rebuild_metadata",
            lambda: rebuild_repo_metadata(
                store=store,
                show_slug=show_slug,
                options=MetadataOptions(
                    repo_root=repo_root,
                    actor=options.actor,
                    show_config_path=show_config_path,
                ),
            ),
        ),
        (
            "upload_r2",
            lambda: upload_publish_bundle(
                store=store,
                show_slug=show_slug,
                options=UploadOptions(
                    repo_root=repo_root,
                    actor=options.actor,
                    show_config_path=show_config_path,
                ),
            ),
        ),
        (
            "prepare_publish",
            lambda: prepare_publish_bundle(
                store=store,
                show_slug=show_slug,
                options=PublishOptions(
                    repo_root=repo_root,
                    actor=options.actor,
                    show_config_path=show_config_path,
                ),
            ),
        ),
        (
            "run_once",
            lambda: execute_job(
                store=store,
                show_slug=show_slug,
                options=ExecutionOptions(
                    repo_root=repo_root,
                    actor=options.actor,
                ),
            ),
        ),
    )

    stage_results: list[dict[str, Any]] = []
    iterations = 0
    max_stage_runs = max(int(options.max_stage_runs), 1)

    while iterations < max_stage_runs:
        progressed = False
        for stage_name, stage_fn in stages:
            try:
                result = stage_fn()
            except FileNotFoundError:
                continue
            progressed = True
            iterations += 1
            stage_results.append(
                {
                    "stage": stage_name,
                    "result": result,
                }
            )
        if not progressed:
            break

    stopped_due_to_cap = iterations >= max_stage_runs
    return {
        "show_slug": show_slug,
        "show_config_path": (
            serialize_show_config_path(repo_root=repo_root, path=show_config_path) if show_config_path else None
        ),
        "retry_ready_count": len(retry_ready),
        "discovery": {
            "discovered_count": len(discovery.get("discovered") or []),
            "enqueued_count": len(discovery.get("enqueued") or []),
        },
        "stage_run_count": iterations,
        "stopped_due_to_max_stage_runs": stopped_due_to_cap,
        "stage_results": stage_results,
        "queue_summary": store.summarize_jobs(show_slug=show_slug),
    }


def serve_show_queue(
    *,
    store: QueueStore,
    show_slug: str,
    options: ServeShowOptions,
) -> dict[str, Any]:
    cycle_results: list[dict[str, Any]] = []
    total_sleep_seconds = 0

    while True:
        cycle = drain_show_queue(store=store, show_slug=show_slug, options=options.drain)
        cycle_results.append(cycle)
        if cycle.get("stopped_due_to_max_stage_runs"):
            continue

        wait_plan = _plan_next_action(store=store, show_slug=show_slug)
        action = str(wait_plan.get("action") or "")
        if action != "wait_for_retry":
            return {
                "show_slug": show_slug,
                "cycle_count": len(cycle_results),
                "total_sleep_seconds": total_sleep_seconds,
                "stop_reason": action,
                "wait_plan": wait_plan,
                "last_cycle": cycle_results[-1],
                "cycle_results": cycle_results,
                "queue_summary": store.summarize_jobs(show_slug=show_slug),
            }

        sleep_seconds = max(int(wait_plan.get("sleep_seconds") or 0), 1)
        time.sleep(sleep_seconds)
        total_sleep_seconds += sleep_seconds


def _plan_next_action(*, store: QueueStore, show_slug: str) -> dict[str, Any]:
    jobs = store.list_jobs(show_slug=show_slug)
    retry_jobs: list[dict[str, Any]] = []
    blocking_jobs: list[dict[str, Any]] = []
    other_active_jobs: list[dict[str, Any]] = []

    for job in jobs:
        state = str(job.get("state") or "").strip()
        if state in TERMINAL_STATES:
            continue
        if state == STATE_RETRY_SCHEDULED:
            retry_jobs.append(job)
            continue
        if state in BLOCKED_STATES or state == STATE_FAILED_RETRYABLE:
            blocking_jobs.append(job)
            continue
        other_active_jobs.append(job)

    if retry_jobs:
        earliest_retry = _earliest_retry_at(retry_jobs)
        if earliest_retry is None:
            return {
                "action": "wait_for_retry",
                "sleep_seconds": 1,
                "retry_job_count": len(retry_jobs),
            }
        now = _utc_now()
        sleep_seconds = max(int((earliest_retry - now).total_seconds()), 1)
        return {
            "action": "wait_for_retry",
            "sleep_seconds": sleep_seconds,
            "retry_job_count": len(retry_jobs),
            "next_retry_at": earliest_retry.replace(microsecond=0).isoformat(),
        }

    if other_active_jobs:
        return {
            "action": "active_backlog_without_progress",
            "state_counts": _state_counts(other_active_jobs),
        }

    if blocking_jobs:
        return {
            "action": "manual_intervention_required",
            "state_counts": _state_counts(blocking_jobs),
        }

    return {"action": "idle"}


def _earliest_retry_at(jobs: list[dict[str, Any]]) -> datetime | None:
    earliest: datetime | None = None
    for job in jobs:
        retry_at = _parse_iso_datetime(str(job.get("next_retry_at") or "").strip())
        if retry_at is None:
            continue
        if earliest is None or retry_at < earliest:
            earliest = retry_at
    return earliest


def _parse_iso_datetime(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _state_counts(jobs: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for job in jobs:
        state = str(job.get("state") or "").strip() or "unknown"
        counts[state] = counts.get(state, 0) + 1
    return dict(sorted(counts.items()))


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)
