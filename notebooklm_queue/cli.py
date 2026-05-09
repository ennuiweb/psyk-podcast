"""CLI entrypoint for NotebookLM queue management."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .constants import DEFAULT_STORAGE_ROOT, STATE_GENERATING, STATE_QUEUED
from .downstream import DownstreamOptions, sync_downstream_publication
from .discovery import discover_show_jobs, enqueue_discovered_jobs
from .execution import ExecutionOptions, execute_job
from .metadata import MetadataOptions, rebuild_repo_metadata
from .models import JobIdentity
from .orchestrator import DrainShowOptions, ServeShowOptions, drain_show_queue, serve_show_queue
from .publish import PublishOptions, UploadOptions, prepare_publish_bundle, upload_publish_bundle
from .repo_publish import RepoPublishOptions, publish_repo_artifacts
from .runner import build_dry_run_plan
from .store import QueueLockError, QueueStore


def _print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=_json_default))


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    to_payload = getattr(value, "to_payload", None)
    if callable(to_payload):
        return to_payload()
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def _load_json_arg(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    payload = json.loads(raw)
    return payload if isinstance(payload, dict) else {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-root", type=Path, default=DEFAULT_STORAGE_ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    enqueue = subparsers.add_parser("enqueue", help="Create or refresh one queue job.")
    enqueue.add_argument("--show-slug", required=True)
    enqueue.add_argument("--subject-slug", required=True)
    enqueue.add_argument("--lecture-key", required=True)
    enqueue.add_argument("--content-type", action="append", dest="content_types", required=True)
    enqueue.add_argument("--config-hash", required=True)
    enqueue.add_argument("--campaign")
    enqueue.add_argument("--initial-state", default=STATE_QUEUED)
    enqueue.add_argument("--priority", type=int, default=100)
    enqueue.add_argument("--blocked-reason")
    enqueue.add_argument("--note")
    enqueue.add_argument("--metadata-json")

    list_parser = subparsers.add_parser("list", help="List queue jobs.")
    list_parser.add_argument("--show-slug")
    list_parser.add_argument("--state")

    inspect_parser = subparsers.add_parser("inspect", help="Show one queue job.")
    inspect_parser.add_argument("--job-id", required=True)
    inspect_parser.add_argument("--show-slug")

    report = subparsers.add_parser("report", help="Summarize queue state.")
    report.add_argument("--show-slug")

    transition = subparsers.add_parser("transition", help="Transition one queue job to a new state.")
    transition.add_argument("--job-id", required=True)
    transition.add_argument("--show-slug", required=True)
    transition.add_argument("--state", required=True)
    transition.add_argument("--note")
    transition.add_argument("--error")
    transition.add_argument("--retry-at")
    transition.add_argument("--details-json")
    transition.add_argument("--expected-state", action="append", dest="expected_states", default=[])
    transition.add_argument("--increment-attempt", action="store_true")

    claim = subparsers.add_parser("claim-next", help="Claim the next ready job for one show.")
    claim.add_argument("--show-slug", required=True)
    claim.add_argument("--ready-state", action="append", dest="ready_states", default=[])
    claim.add_argument("--target-state", default=STATE_GENERATING)

    retry = subparsers.add_parser("retry-ready", help="Re-queue retry-scheduled jobs whose retry window has arrived.")
    retry.add_argument("--show-slug")
    retry.add_argument("--limit", type=int)

    reconcile = subparsers.add_parser("reconcile", help="Rebuild queue indexes from job files.")
    reconcile.add_argument("--show-slug")

    lock = subparsers.add_parser("lock-check", help="Acquire and release a show lock.")
    lock.add_argument("--show-slug", required=True)

    discover = subparsers.add_parser("discover", help="Discover lecture-scoped jobs for one supported show.")
    discover.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    discover.add_argument("--show-slug", required=True)
    discover.add_argument("--show-config", type=Path)
    discover.add_argument("--content-type", action="append", dest="content_types", default=[])
    discover.add_argument("--include-published", action="store_true")
    discover.add_argument("--enqueue", action="store_true")
    discover.add_argument("--priority", type=int, default=100)

    dry_run = subparsers.add_parser("run-dry", help="Resolve the exact dry-run generate/download plan for a queued job.")
    dry_run.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    dry_run.add_argument("--show-slug", required=True)
    dry_run.add_argument("--job-id")

    run_once = subparsers.add_parser(
        "run-once",
        help="Execute generate/download for one queued or explicit job and persist a run manifest.",
    )
    run_once.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    run_once.add_argument("--show-slug", required=True)
    run_once.add_argument("--job-id")
    run_once.add_argument("--retry-at")
    run_once.add_argument("--skip-download", action="store_true")

    prepare_publish = subparsers.add_parser(
        "prepare-publish",
        help="Validate local generated artifacts and persist a publish bundle manifest.",
    )
    prepare_publish.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    prepare_publish.add_argument("--show-slug", required=True)
    prepare_publish.add_argument("--job-id")
    prepare_publish.add_argument("--show-config", type=Path)

    upload_r2 = subparsers.add_parser(
        "upload-r2",
        help="Upload approved media artifacts to R2 and update the repo-side media manifest.",
    )
    upload_r2.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    upload_r2.add_argument("--show-slug", required=True)
    upload_r2.add_argument("--job-id")
    upload_r2.add_argument("--show-config", type=Path)

    rebuild_metadata = subparsers.add_parser(
        "rebuild-metadata",
        help="Rebuild repo-side RSS/inventory sidecars from uploaded objects.",
    )
    rebuild_metadata.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    rebuild_metadata.add_argument("--show-slug", required=True)
    rebuild_metadata.add_argument("--job-id")
    rebuild_metadata.add_argument("--show-config", type=Path)

    push_repo = subparsers.add_parser(
        "push-repo",
        help="Commit and push allowlisted queue-owned generated repo artifacts.",
    )
    push_repo.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    push_repo.add_argument("--show-slug", required=True)
    push_repo.add_argument("--job-id")
    push_repo.add_argument("--show-config", type=Path)
    push_repo.add_argument("--remote", default="origin")
    push_repo.add_argument("--branch", default="main")

    sync_downstream = subparsers.add_parser(
        "sync-downstream",
        help="Wait for expected post-push downstream workflows and mark publication complete.",
    )
    sync_downstream.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    sync_downstream.add_argument("--show-slug", required=True)
    sync_downstream.add_argument("--job-id")
    sync_downstream.add_argument("--timeout-seconds", type=int, default=900)
    sync_downstream.add_argument("--poll-interval-seconds", type=int, default=10)

    drain_show = subparsers.add_parser(
        "drain-show",
        help="Discover, resume, and advance one show through all ready queue stages.",
    )
    drain_show.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    drain_show.add_argument("--show-slug", required=True)
    drain_show.add_argument("--show-config", type=Path)
    drain_show.add_argument("--content-type", action="append", dest="content_types", default=[])
    drain_show.add_argument("--priority", type=int, default=100)
    drain_show.add_argument("--max-stage-runs", type=int, default=50)
    drain_show.add_argument("--timeout-seconds", type=int, default=900)
    drain_show.add_argument("--poll-interval-seconds", type=int, default=10)
    drain_show.add_argument("--remote", default="origin")
    drain_show.add_argument("--branch", default="main")

    serve_show = subparsers.add_parser(
        "serve-show",
        help="Keep draining one show, waiting through retry windows until the backlog is idle or needs intervention.",
    )
    serve_show.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    serve_show.add_argument("--show-slug", required=True)
    serve_show.add_argument("--show-config", type=Path)
    serve_show.add_argument("--content-type", action="append", dest="content_types", default=[])
    serve_show.add_argument("--priority", type=int, default=100)
    serve_show.add_argument("--max-stage-runs", type=int, default=50)
    serve_show.add_argument("--timeout-seconds", type=int, default=900)
    serve_show.add_argument("--poll-interval-seconds", type=int, default=10)
    serve_show.add_argument("--remote", default="origin")
    serve_show.add_argument("--branch", default="main")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    store = QueueStore(Path(args.storage_root).resolve())

    if args.command == "enqueue":
        identity = JobIdentity(
            show_slug=args.show_slug,
            subject_slug=args.subject_slug,
            lecture_key=args.lecture_key,
            content_types=tuple(args.content_types),
            config_hash=args.config_hash,
            campaign=args.campaign,
        )
        payload = store.upsert_job(
            identity,
            initial_state=args.initial_state,
            priority=int(args.priority),
            blocked_reason=args.blocked_reason,
            note=args.note,
            metadata=_load_json_arg(args.metadata_json),
        )
        _print_json(payload)
        return 0

    if args.command == "list":
        _print_json(store.list_jobs(show_slug=args.show_slug, state=args.state))
        return 0

    if args.command == "inspect":
        if args.show_slug:
            payload = store.load_job(show_slug=args.show_slug, job_id=args.job_id)
        else:
            payload = store.load_job_by_id(args.job_id)
        _print_json(payload)
        return 0 if payload else 1

    if args.command == "report":
        _print_json(store.summarize_jobs(show_slug=args.show_slug))
        return 0

    if args.command == "transition":
        payload = store.transition_job(
            show_slug=args.show_slug,
            job_id=args.job_id,
            state=args.state,
            note=args.note,
            error=args.error,
            retry_at=args.retry_at,
            details=_load_json_arg(args.details_json),
            expected_states=set(args.expected_states),
            increment_attempt=bool(args.increment_attempt),
        )
        _print_json(payload)
        return 0

    if args.command == "claim-next":
        payload = store.claim_next_job(
            show_slug=args.show_slug,
            ready_states=set(args.ready_states),
            target_state=args.target_state,
        )
        _print_json(payload or {})
        return 0 if payload else 1

    if args.command == "retry-ready":
        _print_json(store.retry_ready_jobs(show_slug=args.show_slug, limit=args.limit))
        return 0

    if args.command == "reconcile":
        _print_json(store.reconcile_indexes(show_slug=args.show_slug))
        return 0

    if args.command == "lock-check":
        try:
            with store.acquire_show_lock(args.show_slug):
                payload = {"show_slug": args.show_slug, "lock_acquired": True}
        except QueueLockError as exc:
            payload = {"show_slug": args.show_slug, "lock_acquired": False, "error": str(exc)}
            _print_json(payload)
            return 1
        _print_json(payload)
        return 0

    if args.command == "discover":
        repo_root = Path(args.repo_root).resolve()
        content_types = tuple(args.content_types) if args.content_types else None
        if args.enqueue:
            payload = enqueue_discovered_jobs(
                repo_root=repo_root,
                store=store,
                show_slug=args.show_slug,
                content_types=content_types,
                show_config_path=Path(args.show_config).resolve() if args.show_config else None,
                include_published=bool(args.include_published),
                priority=int(args.priority),
            )
        else:
            payload = [
                {
                    **{key: value for key, value in item.items() if key != "identity"},
                    "identity": item["identity"].to_payload(),
                }
                for item in discover_show_jobs(
                    repo_root=repo_root,
                    show_slug=args.show_slug,
                    content_types=content_types,
                    show_config_path=Path(args.show_config).resolve() if args.show_config else None,
                    include_published=bool(args.include_published),
                )
            ]
        _print_json(payload)
        return 0

    if args.command == "run-dry":
        payload = build_dry_run_plan(
            repo_root=Path(args.repo_root).resolve(),
            store=store,
            show_slug=args.show_slug,
            job_id=args.job_id,
        )
        _print_json(payload)
        return 0

    if args.command == "run-once":
        payload = execute_job(
            store=store,
            show_slug=args.show_slug,
            job_id=args.job_id,
            options=ExecutionOptions(
                repo_root=Path(args.repo_root).resolve(),
                retry_at=args.retry_at,
                run_download=not bool(args.skip_download),
            ),
        )
        _print_json(payload)
        return 0

    if args.command == "prepare-publish":
        payload = prepare_publish_bundle(
            store=store,
            show_slug=args.show_slug,
            job_id=args.job_id,
            options=PublishOptions(
                repo_root=Path(args.repo_root).resolve(),
                show_config_path=Path(args.show_config).resolve() if args.show_config else None,
            ),
        )
        _print_json(payload)
        return 0

    if args.command == "upload-r2":
        payload = upload_publish_bundle(
            store=store,
            show_slug=args.show_slug,
            job_id=args.job_id,
            options=UploadOptions(
                repo_root=Path(args.repo_root).resolve(),
                show_config_path=Path(args.show_config).resolve() if args.show_config else None,
            ),
        )
        _print_json(payload)
        return 0

    if args.command == "rebuild-metadata":
        payload = rebuild_repo_metadata(
            store=store,
            show_slug=args.show_slug,
            job_id=args.job_id,
            options=MetadataOptions(
                repo_root=Path(args.repo_root).resolve(),
                show_config_path=Path(args.show_config).resolve() if args.show_config else None,
            ),
        )
        _print_json(payload)
        return 0

    if args.command == "push-repo":
        payload = publish_repo_artifacts(
            store=store,
            show_slug=args.show_slug,
            job_id=args.job_id,
            options=RepoPublishOptions(
                repo_root=Path(args.repo_root).resolve(),
                show_config_path=Path(args.show_config).resolve() if args.show_config else None,
                remote=args.remote,
                branch=args.branch,
            ),
        )
        _print_json(payload)
        return 0

    if args.command == "sync-downstream":
        payload = sync_downstream_publication(
            store=store,
            show_slug=args.show_slug,
            job_id=args.job_id,
            options=DownstreamOptions(
                repo_root=Path(args.repo_root).resolve(),
                timeout_seconds=int(args.timeout_seconds),
                poll_interval_seconds=int(args.poll_interval_seconds),
            ),
        )
        _print_json(payload)
        return 0

    if args.command == "drain-show":
        payload = drain_show_queue(
            store=store,
            show_slug=args.show_slug,
            options=DrainShowOptions(
                repo_root=Path(args.repo_root).resolve(),
                show_config_path=Path(args.show_config).resolve() if args.show_config else None,
                content_types=tuple(args.content_types) if args.content_types else None,
                discovery_priority=int(args.priority),
                max_stage_runs=int(args.max_stage_runs),
                downstream_timeout_seconds=int(args.timeout_seconds),
                downstream_poll_interval_seconds=int(args.poll_interval_seconds),
                remote=args.remote,
                branch=args.branch,
            ),
        )
        _print_json(payload)
        return 0

    if args.command == "serve-show":
        payload = serve_show_queue(
            store=store,
            show_slug=args.show_slug,
            options=ServeShowOptions(
                drain=DrainShowOptions(
                    repo_root=Path(args.repo_root).resolve(),
                    show_config_path=Path(args.show_config).resolve() if args.show_config else None,
                    content_types=tuple(args.content_types) if args.content_types else None,
                    discovery_priority=int(args.priority),
                    max_stage_runs=int(args.max_stage_runs),
                    downstream_timeout_seconds=int(args.timeout_seconds),
                    downstream_poll_interval_seconds=int(args.poll_interval_seconds),
                    remote=args.remote,
                    branch=args.branch,
                )
            ),
        )
        _print_json(payload)
        return 0 if payload.get("stop_reason") == "idle" else 1

    parser.error(f"Unhandled command: {args.command}")
    return 2
