"""Structured models used by Spotify transcript tooling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EpisodeSource:
    show_slug: str
    subject_slug: str | None
    show_root: Path
    episode_key: str
    title: str
    spotify_url: str | None
    spotify_episode_id: str | None
    inventory_entry: dict[str, Any]


@dataclass(frozen=True)
class ShowSources:
    show_slug: str
    subject_slug: str | None
    show_root: Path
    inventory_path: Path
    spotify_map_path: Path
    episodes: tuple[EpisodeSource, ...]


@dataclass(frozen=True)
class AcquisitionResult:
    status: str
    payload: dict[str, Any] | None
    http_status: int | None = None
    error: str | None = None
    transcript_url: str | None = None


@dataclass(frozen=True)
class SyncSummary:
    show_slug: str
    attempted: int
    downloaded: int
    skipped_downloaded: int
    missing_mapping: int
    failed: int
