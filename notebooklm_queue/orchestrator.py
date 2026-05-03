"""Service-oriented orchestration for draining one show queue through all ready stages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

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
