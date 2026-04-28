from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from spotify_transcripts.discovery import load_show_sources
from spotify_transcripts.store import TranscriptStore
from spotify_transcripts.verifier import verify_show_transcripts


class VerifierTests(unittest.TestCase):
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
                        "ep-b": "https://open.spotify.com/episode/bbbbbbbbbbbbbbbb",
                    },
                }
            ),
            encoding="utf-8",
        )
        self.sources = load_show_sources(repo_root=self.repo_root, show_slug="demo-show")
        self.store = TranscriptStore(self.show_root)

    def test_verify_show_transcripts_reports_clean_download(self) -> None:
        self.store.write_raw_payload(episode_key="ep-a", payload={"ok": True})
        self.store.write_normalized_payload(
            episode_key="ep-a",
            payload={
                "segment_count": 1,
                "segments": [
                    {"start_ms": 0, "end_ms": 1000, "text": "Hello"},
                ],
            },
        )
        self.store.write_vtt(episode_key="ep-a", content="WEBVTT\n\n1\n00:00:00.000 --> 00:00:01.000\nHello\n")
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
                    "transcript_url": "https://example.test/transcript",
                    "raw_path": "spotify_transcripts/raw/ep-a.json",
                    "normalized_path": "spotify_transcripts/normalized/ep-a.json",
                    "vtt_path": "spotify_transcripts/vtt/ep-a.vtt",
                    "sha256": "demo",
                    "attempt_count": 1,
                    "consecutive_failure_count": 0,
                    "segment_count": 1,
                    "language": "en-us",
                    "available_translations": [],
                    "pub_date": None,
                    "episode_kind": None,
                    "podcast_kind": None,
                }
            },
        )
        payload = verify_show_transcripts(sources=self.sources, store=self.store)
        self.assertEqual(payload["downloaded_episode_count"], 1)
        self.assertEqual(payload["issue_count"], 1)
        self.assertEqual(payload["issues"][0]["reason"], "missing_manifest_entry")

    def test_verify_show_transcripts_reports_orphaned_and_bad_files(self) -> None:
        (self.show_root / "spotify_transcripts" / "raw").mkdir(parents=True, exist_ok=True)
        (self.show_root / "spotify_transcripts" / "raw" / "orphan.json").write_text("{}", encoding="utf-8")
        payload = verify_show_transcripts(sources=self.sources, store=self.store)
        reasons = {issue["reason"] for issue in payload["issues"]}
        self.assertIn("missing_manifest_entry", reasons)
        self.assertIn("orphaned_raw_file", reasons)
