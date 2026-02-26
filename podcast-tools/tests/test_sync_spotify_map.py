import importlib.util
import tempfile
import unittest
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[2]
    module_path = repo_root / "scripts" / "sync_spotify_map.py"
    spec = importlib.util.spec_from_file_location("sync_spotify_map", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SyncSpotifyMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module()

    def test_build_spotify_map_adds_search_for_missing_titles(self):
        by_title, stats = self.mod.build_spotify_map(
            rss_titles=[
                "Uge 1, Forelæsning 1 · Podcast · Alle kilder",
                "Uge 1, Forelæsning 1 · Podcast · Lewis (1999)",
            ],
            existing_payload={},
            spotify_episode_by_title={},
            prune_stale=False,
        )
        self.assertEqual(len(by_title), 2)
        self.assertTrue(all(url.startswith("https://open.spotify.com/search/") for url in by_title.values()))
        self.assertEqual(stats["added_search"], 2)
        self.assertEqual(stats["preserved_existing"], 0)
        self.assertEqual(stats["upgraded_search_to_episode"], 0)
        self.assertEqual(stats["repaired_invalid"], 0)

    def test_build_spotify_map_preserves_valid_urls_and_repairs_invalid(self):
        by_title, stats = self.mod.build_spotify_map(
            rss_titles=[
                "Uge 1, Forelæsning 1 · Podcast · Alle kilder",
                "Uge 1, Forelæsning 1 · Podcast · Lewis (1999)",
            ],
            existing_payload={
                "by_rss_title": {
                    "Uge 1, Forelæsning 1 · Podcast · Alle kilder": (
                        "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8"
                    ),
                    "Uge 1, Forelæsning 1 · Podcast · Lewis (1999)": "https://example.test/not-spotify",
                    "Uge 2, Forelæsning 1 · Podcast · Stale": (
                        "https://open.spotify.com/search/Uge%202%2C%20Forel%C3%A6sning%201%20%C2%B7%20Podcast%20%C2%B7%20Stale/episodes"
                    ),
                }
            },
            spotify_episode_by_title={},
            prune_stale=False,
        )
        self.assertEqual(
            by_title["Uge 1, Forelæsning 1 · Podcast · Alle kilder"],
            "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8",
        )
        self.assertTrue(
            by_title["Uge 1, Forelæsning 1 · Podcast · Lewis (1999)"].startswith(
                "https://open.spotify.com/search/"
            )
        )
        self.assertIn("Uge 2, Forelæsning 1 · Podcast · Stale", by_title)
        self.assertEqual(stats["preserved_existing"], 1)
        self.assertEqual(stats["upgraded_search_to_episode"], 0)
        self.assertEqual(stats["repaired_invalid"], 1)
        self.assertEqual(stats["carried_stale"], 1)

    def test_build_spotify_map_matches_direct_episode_urls_from_show_index(self):
        by_title, stats = self.mod.build_spotify_map(
            rss_titles=["Uge 1, Forelæsning 1 · Podcast · Alle kilder"],
            existing_payload={},
            spotify_episode_by_title={
                "uge 1, forelæsning 1 · podcast · alle kilder": (
                    "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8"
                )
            },
            prune_stale=False,
        )
        self.assertEqual(
            by_title["Uge 1, Forelæsning 1 · Podcast · Alle kilder"],
            "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8",
        )
        self.assertEqual(stats["matched_show_episode"], 1)
        self.assertEqual(stats["upgraded_search_to_episode"], 0)
        self.assertEqual(stats["added_search"], 0)

    def test_build_spotify_map_upgrades_existing_search_to_episode_when_show_match_exists(self):
        by_title, stats = self.mod.build_spotify_map(
            rss_titles=["Uge 1, Forelæsning 1 · Podcast · Alle kilder"],
            existing_payload={
                "by_rss_title": {
                    "Uge 1, Forelæsning 1 · Podcast · Alle kilder": (
                        "https://open.spotify.com/search/Uge%201%2C%20Forel%C3%A6sning%201%20%C2%B7%20Podcast%20%C2%B7%20Alle%20kilder/episodes"
                    )
                }
            },
            spotify_episode_by_title={
                "uge 1, forelæsning 1 · podcast · alle kilder": (
                    "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8"
                )
            },
            prune_stale=False,
        )
        self.assertEqual(
            by_title["Uge 1, Forelæsning 1 · Podcast · Alle kilder"],
            "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8",
        )
        self.assertEqual(stats["matched_show_episode"], 1)
        self.assertEqual(stats["upgraded_search_to_episode"], 1)
        self.assertEqual(stats["preserved_existing"], 0)

    def test_parse_show_id_from_url(self):
        self.assertEqual(
            self.mod.parse_show_id_from_url("https://open.spotify.com/show/0jAvkPCcZ1x98lIMno1oqv"),
            "0jAvkPCcZ1x98lIMno1oqv",
        )
        self.assertEqual(
            self.mod.parse_show_id_from_url(
                "https://open.spotify.com/show/0jAvkPCcZ1x98lIMno1oqv?si=abc123"
            ),
            "0jAvkPCcZ1x98lIMno1oqv",
        )
        self.assertIsNone(self.mod.parse_show_id_from_url("https://open.spotify.com/episode/abc123"))
        self.assertIsNone(self.mod.parse_show_id_from_url("not-a-spotify-url"))

    def test_load_rss_titles_dedupes_normalized_titles(self):
        rss_payload = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item><title>Uge 1, Forelæsning 1 · Podcast · Alle kilder</title></item>
    <item><title> Uge 1, Forelæsning 1 · Podcast · Alle   kilder </title></item>
    <item><title>Uge 1, Forelæsning 1 · Podcast · Lewis (1999)</title></item>
  </channel>
</rss>
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            rss_path = Path(temp_dir) / "rss.xml"
            rss_path.write_text(rss_payload, encoding="utf-8")
            titles = self.mod.load_rss_titles(rss_path)
        self.assertEqual(
            titles,
            [
                "Uge 1, Forelæsning 1 · Podcast · Alle kilder",
                "Uge 1, Forelæsning 1 · Podcast · Lewis (1999)",
            ],
        )


if __name__ == "__main__":
    unittest.main()
