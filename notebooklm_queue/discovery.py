"""Discovery helpers for NotebookLM queue jobs."""

from __future__ import annotations

from pathlib import Path

from .adapters import get_show_adapter
from .models import JobIdentity
from .show_config import resolve_show_config_path, serialize_show_config_path
from .store import QueueStore


def discover_show_jobs(
    *,
    repo_root: Path,
    show_slug: str,
    content_types: tuple[str, ...] | None = None,
    show_config_path: str | Path | None = None,
) -> list[dict[str, object]]:
    adapter = get_show_adapter(show_slug)
    effective_content_types = content_types or adapter.default_content_types
    config_hash = adapter.config_hash(repo_root, show_config_path=show_config_path)
    serialized_show_config_path = None
    if show_config_path is not None:
        serialized_show_config_path = serialize_show_config_path(
            repo_root=repo_root,
            path=resolve_show_config_path(
                repo_root=repo_root,
                default_path=adapter.show_config_path,
                override_path=show_config_path,
            ),
        )
    jobs: list[dict[str, object]] = []
    for lecture in adapter.discover_lectures(repo_root):
        metadata = dict(lecture.metadata)
        if serialized_show_config_path is not None:
            metadata["show_config_path"] = serialized_show_config_path
        identity = JobIdentity(
            show_slug=adapter.show_slug,
            subject_slug=adapter.subject_slug,
            lecture_key=lecture.lecture_key,
            content_types=effective_content_types,
            config_hash=config_hash,
        )
        jobs.append(
            {
                "job_id": identity.stable_key(),
                "identity": identity,
                "metadata": metadata,
            }
        )
    return jobs


def enqueue_discovered_jobs(
    *,
    repo_root: Path,
    store: QueueStore,
    show_slug: str,
    content_types: tuple[str, ...] | None = None,
    show_config_path: str | Path | None = None,
    priority: int = 100,
) -> list[dict[str, object]]:
    discovered = discover_show_jobs(
        repo_root=repo_root,
        show_slug=show_slug,
        content_types=content_types,
        show_config_path=show_config_path,
    )
    created: list[dict[str, object]] = []
    for item in discovered:
        payload = store.upsert_job(
            item["identity"],
            metadata=item["metadata"],
            priority=priority,
        )
        created.append(payload)
    return created
