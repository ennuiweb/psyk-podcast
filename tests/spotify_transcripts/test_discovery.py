from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from spotify_transcripts.discovery import load_show_sources


class DiscoveryTests(unittest.TestCase):
    def test_load_show_sources_joins_inventory_with_episode_map(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            show_root = repo_root / "shows" / "demo-show"
            show_root.mkdir(parents=True, exist_ok=True)
            (show_root / "episode_inventory.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "subject_slug": "demo",
                        "episodes": [
                            {
                                "episode_key": "ep-a",
                                "title": "Episode A",
                            },
                            {
                                "episode_key": "ep-b",
                                "title": "Episode B",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (show_root / "spotify_map.json").write_text(
                json.dumps(
                    {
                        "version": 2,
                        "subject_slug": "demo",
                        "by_episode_key": {
                            "ep-a": "https://open.spotify.com/episode/1234567890abcdef",
                        },
                    }
                ),
                encoding="utf-8",
            )

            sources = load_show_sources(repo_root=repo_root, show_slug="demo-show")

            self.assertEqual(sources.show_slug, "demo-show")
            self.assertEqual(sources.subject_slug, "demo")
            self.assertEqual(len(sources.episodes), 2)
            self.assertEqual(sources.episodes[0].spotify_episode_id, "1234567890abcdef")
            self.assertIsNone(sources.episodes[1].spotify_url)
