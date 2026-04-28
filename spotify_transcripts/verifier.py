"""Integrity verification for downloaded Spotify transcript artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import STATUS_DOWNLOADED
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


def _collect_files(root: Path, suffix: str) -> set[str]:
    if not root.exists():
        return set()
    return {
        str(path.relative_to(root.parent.parent))
        for path in root.rglob(f"*{suffix}")
        if path.is_file()
    }


def verify_show_transcripts(*, sources: ShowSources, store: TranscriptStore) -> dict[str, Any]:
    manifest = store.load_manifest()
    entries = manifest.get("episodes") if isinstance(manifest.get("episodes"), list) else []
    entries_by_key = store.load_entries_by_episode_key()
    issues: list[dict[str, Any]] = []
    downloaded_count = 0

    referenced_raw: set[str] = set()
    referenced_normalized: set[str] = set()
    referenced_vtt: set[str] = set()

    for source in sources.episodes:
        entry = entries_by_key.get(source.episode_key)
        if entry is None:
            if source.spotify_url and source.spotify_episode_id:
                issues.append(
                    {
                        "episode_key": source.episode_key,
                        "title": source.title,
                        "severity": "error",
                        "reason": "missing_manifest_entry",
                    }
                )
            continue

        status = str(entry.get("status") or "").strip()
        if status != STATUS_DOWNLOADED:
            continue
        downloaded_count += 1

        for field_name, bucket in (
            ("raw_path", referenced_raw),
            ("normalized_path", referenced_normalized),
            ("vtt_path", referenced_vtt),
        ):
            rel = str(entry.get(field_name) or "").strip()
            if not rel:
                issues.append(
                    {
                        "episode_key": source.episode_key,
                        "title": source.title,
                        "severity": "error",
                        "reason": f"missing_{field_name}",
                    }
                )
                continue
            bucket.add(rel)
            path = source.show_root / rel
            if not path.exists():
                issues.append(
                    {
                        "episode_key": source.episode_key,
                        "title": source.title,
                        "severity": "error",
                        "reason": f"missing_file_{field_name}",
                        "path": rel,
                    }
                )
                continue
            if path.stat().st_size <= 0:
                issues.append(
                    {
                        "episode_key": source.episode_key,
                        "title": source.title,
                        "severity": "error",
                        "reason": f"empty_file_{field_name}",
                        "path": rel,
                    }
                )

        normalized_rel = str(entry.get("normalized_path") or "").strip()
        if normalized_rel:
            normalized_path = source.show_root / normalized_rel
            if normalized_path.exists() and normalized_path.stat().st_size > 0:
                payload = _load_json(normalized_path, f"normalized transcript for {source.episode_key}")
                segments = payload.get("segments")
                if not isinstance(segments, list) or not segments:
                    issues.append(
                        {
                            "episode_key": source.episode_key,
                            "title": source.title,
                            "severity": "error",
                            "reason": "missing_segments",
                        }
                    )
                else:
                    if int(payload.get("segment_count") or 0) != len(segments):
                        issues.append(
                            {
                                "episode_key": source.episode_key,
                                "title": source.title,
                                "severity": "error",
                                "reason": "segment_count_mismatch",
                                "segment_count": payload.get("segment_count"),
                                "actual_segment_count": len(segments),
                            }
                        )
                    first_segment = segments[0] if isinstance(segments[0], dict) else None
                    if not first_segment or "text" not in first_segment or "start_ms" not in first_segment:
                        issues.append(
                            {
                                "episode_key": source.episode_key,
                                "title": source.title,
                                "severity": "error",
                                "reason": "bad_first_segment",
                            }
                        )

        vtt_rel = str(entry.get("vtt_path") or "").strip()
        if vtt_rel:
            vtt_path = source.show_root / vtt_rel
            if vtt_path.exists() and vtt_path.stat().st_size > 0:
                text = vtt_path.read_text(encoding="utf-8")
                if not text.startswith("WEBVTT"):
                    issues.append(
                        {
                            "episode_key": source.episode_key,
                            "title": source.title,
                            "severity": "error",
                            "reason": "bad_vtt_header",
                        }
                    )

    orphaned_raw = sorted(_collect_files(store.raw_dir, ".json") - referenced_raw)
    orphaned_normalized = sorted(_collect_files(store.normalized_dir, ".json") - referenced_normalized)
    orphaned_vtt = sorted(_collect_files(store.vtt_dir, ".vtt") - referenced_vtt)

    for rel in orphaned_raw:
        issues.append({"severity": "warning", "reason": "orphaned_raw_file", "path": rel})
    for rel in orphaned_normalized:
        issues.append({"severity": "warning", "reason": "orphaned_normalized_file", "path": rel})
    for rel in orphaned_vtt:
        issues.append({"severity": "warning", "reason": "orphaned_vtt_file", "path": rel})

    return {
        "version": 1,
        "show_slug": sources.show_slug,
        "subject_slug": sources.subject_slug,
        "checked_at": utc_now_iso(),
        "inventory_episode_count": len(sources.episodes),
        "manifest_episode_count": len([entry for entry in entries if isinstance(entry, dict)]),
        "downloaded_episode_count": downloaded_count,
        "issue_count": len(issues),
        "issues": issues,
    }
