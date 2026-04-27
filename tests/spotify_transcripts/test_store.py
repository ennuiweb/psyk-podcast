from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from spotify_transcripts.models import EpisodeSource
from spotify_transcripts.store import TranscriptStore


class StoreTests(unittest.TestCase):
    def test_manifest_roundtrip_and_base_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            show_root = Path(temp_dir)
            store = TranscriptStore(show_root)
            source = EpisodeSource(
                show_slug="demo-show",
                subject_slug="demo",
                show_root=show_root,
                episode_key="ep-a",
                title="Episode A",
                spotify_url="https://open.spotify.com/episode/abc123",
                spotify_episode_id="abc123",
                inventory_entry={"pub_date": "Mon, 01 Jan 2026 00:00:00 +0000"},
            )
            entry = store.build_base_entry(source)
            entry["status"] = "downloaded"
            entry["last_attempt_status"] = "downloaded"
            entry["downloaded_at"] = "2026-01-01T00:00:00+00:00"

            store.save_manifest(
                show_slug="demo-show",
                subject_slug="demo",
                inventory_path=show_root / "episode_inventory.json",
                spotify_map_path=show_root / "spotify_map.json",
                entries={"ep-a": entry},
            )

            manifest = store.load_manifest()
            self.assertEqual(manifest["show_slug"], "demo-show")
            self.assertEqual(manifest["episodes"][0]["episode_key"], "ep-a")

    def test_writes_raw_normalized_and_vtt_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = TranscriptStore(Path(temp_dir))
            raw_path, digest = store.write_raw_payload(episode_key="ep-a", payload={"ok": True})
            normalized_path = store.write_normalized_payload(
                episode_key="ep-a",
                payload={"segments": []},
            )
            vtt_path = store.write_vtt(episode_key="ep-a", content="WEBVTT\n")
            export_path = store.write_export_payload(
                file_name="demo-show.combined.json",
                payload={"episodes": []},
            )

            self.assertEqual(raw_path, "spotify_transcripts/raw/ep-a.json")
            self.assertTrue(digest)
            self.assertEqual(normalized_path, "spotify_transcripts/normalized/ep-a.json")
            self.assertEqual(vtt_path, "spotify_transcripts/vtt/ep-a.vtt")
            self.assertEqual(export_path, "spotify_transcripts/exports/demo-show.combined.json")
