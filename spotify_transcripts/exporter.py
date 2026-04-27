"""Export normalized Spotify transcripts into combined show-level deliverables."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import ShowSources
from .store import TranscriptStore, utc_now_iso


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit(f"Unable to read {label}: {path} ({exc})") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Unable to parse {label}: {path} ({exc})") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"{label} must be a JSON object: {path}")
    return payload


def _combined_transcript_text(segments: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for segment in segments:
        text = str(segment.get("text") or "").strip()
        if text:
            parts.append(text)
    return "\n".join(parts)


def export_show_transcripts(
    *,
    sources: ShowSources,
    store: TranscriptStore,
    output_name: str | None = None,
) -> dict[str, Any]:
    manifest = store.load_manifest()
    manifest_entries = store.load_entries_by_episode_key()
    exported_episodes: list[dict[str, Any]] = []
    omitted_episodes: list[dict[str, str]] = []

    for source in sources.episodes:
        entry = manifest_entries.get(source.episode_key)
        if not entry:
            omitted_episodes.append(
                {
                    "episode_key": source.episode_key,
                    "title": source.title,
                    "reason": "missing_mapping" if not source.spotify_url else "missing_manifest_entry",
                }
            )
            continue
        normalized_rel = str(entry.get("normalized_path") or "").strip()
        if not normalized_rel:
            omitted_episodes.append(
                {
                    "episode_key": source.episode_key,
                    "title": source.title,
                    "reason": str(entry.get("status") or "missing_normalized_path"),
                }
            )
            continue

        normalized_path = source.show_root / normalized_rel
        normalized_payload = _load_json(normalized_path, f"normalized transcript for {source.episode_key}")
        raw_segments = normalized_payload.get("segments")
        segments = raw_segments if isinstance(raw_segments, list) else []
        exported_episodes.append(
            {
                "episode_key": source.episode_key,
                "title": source.title,
                "pub_date": entry.get("pub_date"),
                "spotify_url": source.spotify_url,
                "spotify_episode_id": source.spotify_episode_id,
                "status": entry.get("status"),
                "downloaded_at": entry.get("downloaded_at"),
                "language": normalized_payload.get("language"),
                "available_translations": normalized_payload.get("available_translations") or [],
                "segment_count": normalized_payload.get("segment_count"),
                "transcript_text": _combined_transcript_text(segments),
                "segments": segments,
            }
        )

    export_payload = {
        "version": 1,
        "show_slug": sources.show_slug,
        "subject_slug": sources.subject_slug,
        "generated_at": utc_now_iso(),
        "inventory_path": store._relpath(sources.inventory_path),
        "spotify_map_path": store._relpath(sources.spotify_map_path),
        "manifest_path": store._relpath(store.manifest_path),
        "episode_count_total": len(sources.episodes),
        "episode_count_exported": len(exported_episodes),
        "omitted_episode_count": len(omitted_episodes),
        "omitted_episodes": omitted_episodes,
        "episodes": exported_episodes,
    }
    file_name = output_name or f"{sources.show_slug}.combined.json"
    export_path = store.write_export_payload(file_name=file_name, payload=export_payload)
    return {
        "show_slug": sources.show_slug,
        "export_path": export_path,
        "episode_count_exported": len(exported_episodes),
        "omitted_episode_count": len(omitted_episodes),
    }
