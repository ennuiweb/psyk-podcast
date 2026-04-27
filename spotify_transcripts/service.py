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

        entry = store.build_base_entry(source, existing_entries.get(source.episode_key))
        now = utc_now_iso()

        if not source.spotify_url or not source.spotify_episode_id:
            if entry.get("status") != STATUS_DOWNLOADED:
                entry["status"] = STATUS_MISSING_MAPPING
            entry["last_attempt_status"] = STATUS_MISSING_MAPPING
            entry["last_attempted_at"] = now
            entry["last_error"] = "Episode has no direct Spotify episode mapping in spotify_map.json."
            existing_entries[source.episode_key] = entry
            missing_mapping += 1
            continue

        if entry.get("status") == STATUS_DOWNLOADED and not force:
            skipped_downloaded += 1
            existing_entries[source.episode_key] = entry
            continue

        attempted += 1
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
                failed += 1
            else:
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
                downloaded += 1
        else:
            if entry.get("status") != STATUS_DOWNLOADED:
                entry["status"] = result.status
            entry["last_error"] = result.error
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
