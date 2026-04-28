"""Persistent artifact storage for Spotify transcripts."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .constants import MANIFEST_VERSION
from .models import EpisodeSource


def utc_now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    _write_text_atomic(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


class TranscriptStore:
    """Manage transcript artifacts for one show."""

    def __init__(self, show_root: Path):
        self.show_root = show_root.resolve()
        self.base_dir = self.show_root / "spotify_transcripts"
        self.raw_dir = self.base_dir / "raw"
        self.normalized_dir = self.base_dir / "normalized"
        self.vtt_dir = self.base_dir / "vtt"
        self.export_dir = self.base_dir / "exports"
        self.manifest_path = self.base_dir / "manifest.json"
        self.queue_path = self.base_dir / "queue.json"

    def load_manifest(self) -> dict[str, Any]:
        return _load_manifest(self.manifest_path)

    def load_queue(self) -> dict[str, Any]:
        return _load_manifest(self.queue_path)

    def load_entries_by_episode_key(self) -> dict[str, dict[str, Any]]:
        manifest = self.load_manifest()
        raw_entries = manifest.get("episodes")
        entries_by_key: dict[str, dict[str, Any]] = {}
        if not isinstance(raw_entries, list):
            return entries_by_key
        for entry in raw_entries:
            if not isinstance(entry, dict):
                continue
            episode_key = str(entry.get("episode_key") or "").strip()
            if episode_key:
                entries_by_key[episode_key] = dict(entry)
        return entries_by_key

    def write_raw_payload(self, *, episode_key: str, payload: dict[str, Any]) -> tuple[str, str]:
        path = self.raw_dir / f"{episode_key}.json"
        rendered = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
        digest = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
        _write_text_atomic(path, rendered)
        return self._relpath(path), digest

    def write_normalized_payload(self, *, episode_key: str, payload: dict[str, Any]) -> str:
        path = self.normalized_dir / f"{episode_key}.json"
        _write_json_atomic(path, payload)
        return self._relpath(path)

    def write_vtt(self, *, episode_key: str, content: str) -> str:
        path = self.vtt_dir / f"{episode_key}.vtt"
        _write_text_atomic(path, content)
        return self._relpath(path)

    def write_export_payload(self, *, file_name: str, payload: dict[str, Any]) -> str:
        path = self.export_dir / file_name
        _write_json_atomic(path, payload)
        return self._relpath(path)

    def save_manifest(
        self,
        *,
        show_slug: str,
        subject_slug: str | None,
        inventory_path: Path,
        spotify_map_path: Path,
        entries: dict[str, dict[str, Any]],
    ) -> None:
        ordered_entries = [entries[key] for key in sorted(entries.keys())]
        payload = {
            "version": MANIFEST_VERSION,
            "show_slug": show_slug,
            "subject_slug": subject_slug,
            "generated_at": utc_now_iso(),
            "inventory_path": self._relpath(inventory_path),
            "spotify_map_path": self._relpath(spotify_map_path),
            "episodes": ordered_entries,
        }
        _write_json_atomic(self.manifest_path, payload)

    def save_queue(self, payload: dict[str, Any]) -> None:
        _write_json_atomic(self.queue_path, payload)

    def build_base_entry(self, source: EpisodeSource, existing: dict[str, Any] | None = None) -> dict[str, Any]:
        previous = dict(existing or {})
        return {
            "episode_key": source.episode_key,
            "title": source.title,
            "spotify_url": source.spotify_url,
            "spotify_episode_id": source.spotify_episode_id,
            "status": previous.get("status"),
            "attempt_count": previous.get("attempt_count") or 0,
            "consecutive_failure_count": previous.get("consecutive_failure_count") or 0,
            "last_attempt_status": previous.get("last_attempt_status"),
            "last_attempted_at": previous.get("last_attempted_at"),
            "downloaded_at": previous.get("downloaded_at"),
            "last_error": previous.get("last_error"),
            "http_status": previous.get("http_status"),
            "transcript_url": previous.get("transcript_url"),
            "raw_path": previous.get("raw_path"),
            "normalized_path": previous.get("normalized_path"),
            "vtt_path": previous.get("vtt_path"),
            "sha256": previous.get("sha256"),
            "segment_count": previous.get("segment_count"),
            "language": previous.get("language"),
            "available_translations": previous.get("available_translations") or [],
            "pub_date": str(source.inventory_entry.get("pub_date") or "").strip() or None,
            "episode_kind": str(source.inventory_entry.get("episode_kind") or "").strip() or None,
            "podcast_kind": str(source.inventory_entry.get("podcast_kind") or "").strip() or None,
        }

    def _relpath(self, path: Path) -> str:
        return str(path.resolve().relative_to(self.show_root))
