"""Dry-run execution planning for queued NotebookLM jobs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .adapters import get_show_adapter
from .constants import STATE_QUEUED, STATE_RETRY_SCHEDULED
from .store import QueueStore


def build_dry_run_plan(
    *,
    repo_root: Path,
    store: QueueStore,
    show_slug: str,
    job_id: str | None = None,
) -> dict[str, Any]:
    adapter = get_show_adapter(show_slug)
    if job_id:
        job = store.load_job(show_slug=show_slug, job_id=job_id)
    else:
        jobs = store.list_jobs(show_slug=show_slug)
        queued = [entry for entry in jobs if str(entry.get("state") or "") in {STATE_QUEUED, STATE_RETRY_SCHEDULED}]
        queued.sort(
            key=lambda entry: (
                int(entry.get("priority") or 100),
                str(entry.get("created_at") or ""),
                str(entry.get("job_id") or ""),
            )
        )
        job = store.load_job(show_slug=show_slug, job_id=str(queued[0]["job_id"])) if queued else {}
    if not job:
        raise FileNotFoundError(f"No runnable job found for show: {show_slug}")

    lecture_key = str(job.get("lecture_key") or "")
    content_types = tuple(str(item) for item in (job.get("content_types") or []) if str(item).strip())
    if not content_types:
        content_types = tuple(adapter.default_content_types)
    return {
        "show_slug": show_slug,
        "subject_slug": adapter.subject_slug,
        "job_id": str(job.get("job_id") or ""),
        "state": str(job.get("state") or ""),
        "lecture_key": lecture_key,
        "content_types": list(content_types),
        "generate_command": adapter.build_generate_command(
            repo_root,
            lecture_key=lecture_key,
            content_types=content_types,
            dry_run=True,
            wait=False,
        ),
        "download_command": adapter.build_download_command(
            repo_root,
            lecture_key=lecture_key,
            content_types=content_types,
            dry_run=True,
        ),
        "metadata": dict(job.get("metadata") or {}),
    }
