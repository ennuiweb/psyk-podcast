from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from spotify_transcripts.discovery import load_show_sources
from spotify_transcripts.exporter import export_show_transcripts
from spotify_transcripts.store import TranscriptStore


class ExporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.repo_root = Path(self.temp_dir.name)
        self.show_root = self.repo_root / "shows" / "demo-show"
        self.show_root.mkdir(parents=True, exist_ok=True)
        (self.show_root / "episode_inventory.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "subject_slug": "demo",
                    "episodes": [
                        {"episode_key": "ep-a", "title": "Episode A"},
                        {"episode_key": "ep-b", "title": "Episode B"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        (self.show_root / "spotify_map.json").write_text(
            json.dumps(
                {
                    "version": 2,
                    "subject_slug": "demo",
                    "by_episode_key": {
                        "ep-a": "https://open.spotify.com/episode/aaaaaaaaaaaaaaaa",
                    },
                }
            ),
            encoding="utf-8",
        )
        self.sources = load_show_sources(repo_root=self.repo_root, show_slug="demo-show")
        self.store = TranscriptStore(self.show_root)
        self.store.write_normalized_payload(
            episode_key="ep-a",
            payload={
                "version": 1,
                "language": "en-us",
                "available_translations": [],
                "segment_count": 2,
                "segments": [
                    {"start_ms": 0, "end_ms": 1000, "text": "Hello"},
                    {"start_ms": 1000, "end_ms": 2000, "text": "World"},
                ],
            },
        )
        self.store.save_manifest(
            show_slug="demo-show",
            subject_slug="demo",
            inventory_path=self.show_root / "episode_inventory.json",
            spotify_map_path=self.show_root / "spotify_map.json",
            entries={
                "ep-a": {
                    "episode_key": "ep-a",
                    "title": "Episode A",
                    "spotify_url": "https://open.spotify.com/episode/aaaaaaaaaaaaaaaa",
                    "spotify_episode_id": "aaaaaaaaaaaaaaaa",
                    "status": "downloaded",
                    "last_attempt_status": "downloaded",
                    "last_attempted_at": "2026-01-01T00:00:00+00:00",
                    "downloaded_at": "2026-01-01T00:00:00+00:00",
                    "last_error": None,
                    "http_status": 200,
                    "raw_path": "spotify_transcripts/raw/ep-a.json",
                    "normalized_path": "spotify_transcripts/normalized/ep-a.json",
                    "vtt_path": "spotify_transcripts/vtt/ep-a.vtt",
                    "sha256": "demo",
                    "segment_count": 2,
                    "language": "en-us",
                    "available_translations": [],
                    "pub_date": None,
                    "episode_kind": None,
                    "podcast_kind": None,
                }
            },
        )

    def test_export_show_transcripts_writes_combined_payload(self) -> None:
        summary = export_show_transcripts(
            sources=self.sources,
            store=self.store,
        )
        self.assertEqual(summary["episode_count_exported"], 1)
        self.assertEqual(summary["omitted_episode_count"], 1)
        export_path = self.show_root / summary["export_path"]
        payload = json.loads(export_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["episode_count_total"], 2)
        self.assertEqual(payload["episode_count_exported"], 1)
        self.assertEqual(payload["omitted_episode_count"], 1)
        self.assertEqual(payload["episodes"][0]["episode_key"], "ep-a")
        self.assertEqual(payload["episodes"][0]["transcript_text"], "Hello\nWorld")
        self.assertEqual(payload["omitted_episodes"][0]["episode_key"], "ep-b")
        self.assertEqual(payload["omitted_episodes"][0]["reason"], "missing_mapping")
