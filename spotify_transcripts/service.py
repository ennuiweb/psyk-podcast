"""Show-level sync orchestration for Spotify transcripts."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Callable

from .constants import (
    DEFAULT_TIMEOUT_MS,
    STATUS_DOWNLOADED,
    STATUS_MISSING_MAPPING,
    STATUS_SCHEMA_CHANGED,
)
from .models import AcquisitionResult, EpisodeSource, ShowSources, SyncSummary
from .normalizer import TranscriptSchemaError, normalize_transcript_payload
from .store import TranscriptStore, utc_now_iso

Downloader = Callable[..., AcquisitionResult]


def process_episode_source(
    *,
    source: EpisodeSource,
    existing_entry: dict[str, object] | None,
    store: TranscriptStore,
    downloader: Downloader,
    force: bool = False,
    headless: bool = False,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> tuple[dict[str, object], str]:
    entry = store.build_base_entry(source, existing_entry)
    now = utc_now_iso()

    if not source.spotify_url or not source.spotify_episode_id:
        if entry.get("status") != STATUS_DOWNLOADED:
            entry["status"] = STATUS_MISSING_MAPPING
        entry["last_attempt_status"] = STATUS_MISSING_MAPPING
        entry["last_attempted_at"] = now
        entry["last_error"] = "Episode has no direct Spotify episode mapping in spotify_map.json."
        return entry, "missing_mapping"

    if entry.get("status") == STATUS_DOWNLOADED and not force:
        return entry, "skipped_downloaded"

    result = downloader(
        episode_url=source.spotify_url,
        episode_id=source.spotify_episode_id,
        headless=headless,
        timeout_ms=timeout_ms,
    )
    entry["last_attempt_status"] = result.status
    entry["last_attempted_at"] = now
    entry["http_status"] = result.http_status

    if result.status == STATUS_DOWNLOADED and result.payload is not None:
        raw_path, digest = store.write_raw_payload(episode_key=source.episode_key, payload=result.payload)
        entry["raw_path"] = raw_path
        entry["sha256"] = digest
        try:
            normalized = normalize_transcript_payload(
                episode_key=source.episode_key,
                title=source.title,
                spotify_url=source.spotify_url,
                raw_payload=result.payload,
            )
        except TranscriptSchemaError as exc:
            if entry.get("status") != STATUS_DOWNLOADED:
                entry["status"] = STATUS_SCHEMA_CHANGED
            entry["last_attempt_status"] = STATUS_SCHEMA_CHANGED
            entry["last_error"] = str(exc)
            return entry, "failed"

        entry["normalized_path"] = store.write_normalized_payload(
            episode_key=source.episode_key,
            payload=normalized.payload,
        )
        entry["vtt_path"] = store.write_vtt(
            episode_key=source.episode_key,
            content=normalized.vtt,
        )
        entry["status"] = STATUS_DOWNLOADED
        entry["downloaded_at"] = now
        entry["last_error"] = None
        entry["segment_count"] = normalized.payload.get("segment_count")
        entry["language"] = normalized.payload.get("language")
        entry["available_translations"] = normalized.payload.get("available_translations") or []
        return entry, "downloaded"

    if entry.get("status") != STATUS_DOWNLOADED:
        entry["status"] = result.status
    entry["last_error"] = result.error
    return entry, "failed"


def sync_show_transcripts(
    *,
    sources: ShowSources,
    store: TranscriptStore,
    downloader: Downloader,
    episode_keys: Iterable[str] | None = None,
    limit: int | None = None,
    force: bool = False,
    headless: bool = False,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> SyncSummary:
    requested_keys = {str(key).strip() for key in (episode_keys or []) if str(key).strip()}
    existing_entries = store.load_entries_by_episode_key()

    attempted = 0
    downloaded = 0
    skipped_downloaded = 0
    missing_mapping = 0
    failed = 0
    processed = 0

    for source in sources.episodes:
        if requested_keys and source.episode_key not in requested_keys:
            continue
        if limit is not None and processed >= limit:
            break
        processed += 1

        action_attempted = bool(source.spotify_url and source.spotify_episode_id and not (
            existing_entries.get(source.episode_key, {}).get("status") == STATUS_DOWNLOADED and not force
        ))
        entry, outcome = process_episode_source(
            source=source,
            existing_entry=existing_entries.get(source.episode_key),
            store=store,
            downloader=downloader,
            force=force,
            headless=headless,
            timeout_ms=timeout_ms,
        )
        if action_attempted:
            attempted += 1
        if outcome == "missing_mapping":
            missing_mapping += 1
        elif outcome == "skipped_downloaded":
            skipped_downloaded += 1
        elif outcome == "downloaded":
            downloaded += 1
        elif outcome == "failed":
            failed += 1
        existing_entries[source.episode_key] = entry

    store.save_manifest(
        show_slug=sources.show_slug,
        subject_slug=sources.subject_slug,
        inventory_path=sources.inventory_path,
        spotify_map_path=sources.spotify_map_path,
        entries=existing_entries,
    )

    return SyncSummary(
        show_slug=sources.show_slug,
        attempted=attempted,
        downloaded=downloaded,
        skipped_downloaded=skipped_downloaded,
        missing_mapping=missing_mapping,
        failed=failed,
    )


def build_show_queue(*, sources: ShowSources, store: TranscriptStore) -> dict[str, object]:
    manifest_entries = store.load_entries_by_episode_key()
    previous_queue = store.load_queue()
    previous_entries_by_key: dict[str, dict[str, object]] = {}
    raw_previous_entries = previous_queue.get("entries")
    if isinstance(raw_previous_entries, list):
        for entry in raw_previous_entries:
            if not isinstance(entry, dict):
                continue
            episode_key = str(entry.get("episode_key") or "").strip()
            if episode_key:
                previous_entries_by_key[episode_key] = dict(entry)
    entries: list[dict[str, object]] = []
    summary = {
        "total": 0,
        "pending": 0,
        "done_downloaded": 0,
        "blocked_missing_mapping": 0,
        "failed": 0,
    }

    for index, source in enumerate(sources.episodes, start=1):
        manifest_entry = manifest_entries.get(source.episode_key, {})
        previous_queue_entry = previous_entries_by_key.get(source.episode_key, {})
        transcript_status = str(manifest_entry.get("status") or "").strip() or None
        if not source.spotify_url or not source.spotify_episode_id:
            queue_status = "blocked_missing_mapping"
        elif transcript_status == STATUS_DOWNLOADED:
            queue_status = "done_downloaded"
        elif str(previous_queue_entry.get("queue_status") or "") == "failed":
            queue_status = "failed"
        else:
            queue_status = "pending"
        summary["total"] += 1
        summary[queue_status] = int(summary.get(queue_status, 0)) + 1
        entries.append(
            {
                "queue_position": index,
                "episode_key": source.episode_key,
                "title": source.title,
                "spotify_url": source.spotify_url,
                "spotify_episode_id": source.spotify_episode_id,
                "queue_status": queue_status,
                "transcript_status": transcript_status,
                "last_attempt_status": manifest_entry.get("last_attempt_status"),
                "last_attempted_at": manifest_entry.get("last_attempted_at"),
                "last_error": manifest_entry.get("last_error"),
            }
        )

    payload = {
        "version": 1,
        "show_slug": sources.show_slug,
        "subject_slug": sources.subject_slug,
        "generated_at": utc_now_iso(),
        "inventory_path": store._relpath(sources.inventory_path),
        "spotify_map_path": store._relpath(sources.spotify_map_path),
        "manifest_path": store._relpath(store.manifest_path),
        "worker_strategy": {
            "default_workers": 1,
            "max_recommended_workers": 1,
            "note": "Queue runner is intentionally single-worker by default because Spotify Web auth and transcript loading are session-sensitive.",
        },
        "summary": summary,
        "entries": entries,
    }
    store.save_queue(payload)
    return payload


def run_show_queue(
    *,
    sources: ShowSources,
    store: TranscriptStore,
    downloader: Downloader,
    limit: int | None = None,
    force: bool = False,
    headless: bool = False,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> dict[str, object]:
    queue_payload = build_show_queue(sources=sources, store=store)
    queue_entries = queue_payload.get("entries")
    if not isinstance(queue_entries, list):
        raise SystemExit("Queue payload is invalid; expected entries list.")

    source_by_key = {source.episode_key: source for source in sources.episodes}
    manifest_entries = store.load_entries_by_episode_key()
    attempted = 0
    downloaded = 0
    failed = 0
    processed = 0

    for queue_entry in queue_entries:
        if not isinstance(queue_entry, dict):
            continue
        if str(queue_entry.get("queue_status") or "") not in {"pending", "failed"}:
            continue
        if limit is not None and processed >= limit:
            break
        processed += 1
        episode_key = str(queue_entry.get("episode_key") or "").strip()
        if not episode_key:
            continue
        source = source_by_key.get(episode_key)
        if source is None:
            queue_entry["queue_status"] = "failed"
            queue_entry["last_error"] = "Episode key was not found in the current episode inventory."
            failed += 1
            continue

        attempted += 1
        entry, outcome = process_episode_source(
            source=source,
            existing_entry=manifest_entries.get(episode_key),
            store=store,
            downloader=downloader,
            force=force,
            headless=headless,
            timeout_ms=timeout_ms,
        )
        manifest_entries[episode_key] = entry
        queue_entry["transcript_status"] = entry.get("status")
        queue_entry["last_attempt_status"] = entry.get("last_attempt_status")
        queue_entry["last_attempted_at"] = entry.get("last_attempted_at")
        queue_entry["last_error"] = entry.get("last_error")
        if outcome == "downloaded":
            queue_entry["queue_status"] = "done_downloaded"
            downloaded += 1
        elif outcome == "missing_mapping":
            queue_entry["queue_status"] = "blocked_missing_mapping"
        elif outcome == "skipped_downloaded":
            queue_entry["queue_status"] = "done_downloaded"
        else:
            queue_entry["queue_status"] = "failed"
            failed += 1

    store.save_manifest(
        show_slug=sources.show_slug,
        subject_slug=sources.subject_slug,
        inventory_path=sources.inventory_path,
        spotify_map_path=sources.spotify_map_path,
        entries=manifest_entries,
    )
    queue_payload["entries"] = queue_entries
    store.save_queue(queue_payload)
    return build_show_queue(sources=sources, store=store) | {
        "attempted": attempted,
        "downloaded": downloaded,
        "failed": failed,
    }
