"""Discovery helpers for NotebookLM queue jobs."""

from __future__ import annotations

import json
from pathlib import Path
import re

from .adapters import get_show_adapter
from .models import JobIdentity
from .show_config import load_show_config, resolve_show_config_path, serialize_show_config_path
from .store import QueueStore

LECTURE_KEY_PATTERN = re.compile(r"^W(\d+)L(\d+)$", re.IGNORECASE)


def discover_show_jobs(
    *,
    repo_root: Path,
    show_slug: str,
    content_types: tuple[str, ...] | None = None,
    show_config_path: str | Path | None = None,
    include_published: bool = False,
) -> list[dict[str, object]]:
    adapter = get_show_adapter(show_slug)
    effective_content_types = content_types or adapter.default_content_types
    config_hash = adapter.config_hash(repo_root, show_config_path=show_config_path)
    serialized_show_config_path = None
    resolved_show_config_path = None
    if show_config_path is not None:
        resolved_show_config_path = resolve_show_config_path(
            repo_root=repo_root,
            default_path=adapter.show_config_path,
            override_path=show_config_path,
        )
        serialized_show_config_path = serialize_show_config_path(
            repo_root=repo_root,
            path=resolved_show_config_path,
        )
    published_lecture_keys = set()
    if not include_published:
        config = load_show_config(
            repo_root=repo_root,
            default_path=adapter.show_config_path,
            override_path=resolved_show_config_path,
        )
        published_lecture_keys = _published_lecture_keys(repo_root=repo_root, config=config)
    jobs: list[dict[str, object]] = []
    for lecture in adapter.discover_lectures(repo_root):
        if _normalized_lecture_key(lecture.lecture_key) in published_lecture_keys:
            continue
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
    include_published: bool = False,
    priority: int = 100,
) -> dict[str, list[dict[str, object]]]:
    discovered = discover_show_jobs(
        repo_root=repo_root,
        show_slug=show_slug,
        content_types=content_types,
        show_config_path=show_config_path,
        include_published=include_published,
    )
    created: list[dict[str, object]] = []
    for item in discovered:
        payload = store.upsert_job(
            item["identity"],
            metadata=item["metadata"],
            priority=priority,
        )
        created.append(payload)
    return {
        "discovered": discovered,
        "enqueued": created,
    }


def _published_lecture_keys(*, repo_root: Path, config: dict[str, object]) -> set[str]:
    inventory_rel = str(config.get("output_inventory") or "").strip()
    if not inventory_rel:
        return set()
    path = repo_root / inventory_rel
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    episodes = payload.get("episodes") if isinstance(payload, dict) else None
    if not isinstance(episodes, list):
        return set()
    lecture_keys: set[str] = set()
    for episode in episodes:
        if not isinstance(episode, dict):
            continue
        lecture_key = str(episode.get("lecture_key") or "").strip()
        if lecture_key:
            lecture_keys.add(_normalized_lecture_key(lecture_key))
    return lecture_keys


def _normalized_lecture_key(value: str) -> str:
    raw = str(value or "").strip().upper()
    match = LECTURE_KEY_PATTERN.match(raw)
    if not match:
        return raw
    return f"W{int(match.group(1))}L{int(match.group(2))}"
