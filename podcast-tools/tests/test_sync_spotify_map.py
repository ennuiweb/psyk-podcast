import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock


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

    def test_build_spotify_map_reports_unresolved_titles_when_missing(self):
        by_title, unresolved, stats = self.mod.build_spotify_map(
            rss_titles=[
                "Uge 1, Forelæsning 1 · Podcast · Alle kilder",
                "Uge 1, Forelæsning 1 · Podcast · Lewis (1999)",
            ],
            existing_payload={},
            spotify_episode_by_title={},
            prune_stale=False,
        )
        self.assertEqual(by_title, {})
        self.assertEqual(
            unresolved,
            [
                "Uge 1, Forelæsning 1 · Podcast · Alle kilder",
                "Uge 1, Forelæsning 1 · Podcast · Lewis (1999)",
            ],
        )
        self.assertEqual(stats["unresolved"], 2)
        self.assertEqual(stats["preserved_existing"], 0)
        self.assertEqual(stats["matched_show_episode"], 0)

    def test_build_spotify_map_preserves_episode_urls_only_and_ignores_non_episode(self):
        by_title, unresolved, stats = self.mod.build_spotify_map(
            rss_titles=[
                "Uge 1, Forelæsning 1 · Podcast · Alle kilder",
                "Uge 1, Forelæsning 1 · Podcast · Lewis (1999)",
            ],
            existing_payload={
                "by_rss_title": {
                    "Uge 1, Forelæsning 1 · Podcast · Alle kilder": (
                        "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8"
                    ),
                    "Uge 1, Forelæsning 1 · Podcast · Lewis (1999)": (
                        "https://open.spotify.com/search/Uge%201%2C%20Forel%C3%A6sning%201%20%C2%B7%20Podcast%20%C2%B7%20Lewis%20%281999%29/episodes"
                    ),
                    "Uge 2, Forelæsning 1 · Podcast · Stale episode": (
                        "https://open.spotify.com/episode/0Yqa6gY5GJfNfQfY7wsY5Y"
                    ),
                    "Uge 2, Forelæsning 1 · Podcast · Stale search": (
                        "https://open.spotify.com/search/Uge%202%2C%20Forel%C3%A6sning%201%20%C2%B7%20Podcast/episodes"
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
        self.assertNotIn("Uge 1, Forelæsning 1 · Podcast · Lewis (1999)", by_title)
        self.assertIn("Uge 2, Forelæsning 1 · Podcast · Stale episode", by_title)
        self.assertNotIn("Uge 2, Forelæsning 1 · Podcast · Stale search", by_title)
        self.assertEqual(unresolved, ["Uge 1, Forelæsning 1 · Podcast · Lewis (1999)"])
        self.assertEqual(stats["preserved_existing"], 1)
        self.assertEqual(stats["carried_stale"], 1)
        self.assertEqual(stats["discarded_non_episode"], 1)
        self.assertEqual(stats["unresolved"], 1)

    def test_build_spotify_map_matches_direct_episode_urls_from_show_index(self):
        by_title, unresolved, stats = self.mod.build_spotify_map(
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
        self.assertEqual(unresolved, [])
        self.assertEqual(stats["matched_show_episode"], 1)
        self.assertEqual(stats["unresolved"], 0)

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

    def test_main_returns_non_zero_when_unresolved_without_allow_unresolved(self):
        rss_payload = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><item><title>Uge 1, Forelæsning 1 · Podcast · Alle kilder</title></item></channel></rss>
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            rss_path = Path(temp_dir) / "rss.xml"
            map_path = Path(temp_dir) / "spotify_map.json"
            rss_path.write_text(rss_payload, encoding="utf-8")

            argv = [
                "sync_spotify_map.py",
                "--rss",
                str(rss_path),
                "--spotify-map",
                str(map_path),
                "--subject-slug",
                "personlighedspsykologi",
            ]
            with mock.patch("sys.argv", argv), mock.patch("sys.stderr", new=io.StringIO()):
                code = self.mod.main()

            self.assertEqual(code, 2)
            self.assertFalse(map_path.exists())

    def test_main_writes_map_when_allow_unresolved_is_set(self):
        rss_payload = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><item><title>Uge 1, Forelæsning 1 · Podcast · Alle kilder</title></item></channel></rss>
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            rss_path = Path(temp_dir) / "rss.xml"
            map_path = Path(temp_dir) / "spotify_map.json"
            rss_path.write_text(rss_payload, encoding="utf-8")

            argv = [
                "sync_spotify_map.py",
                "--rss",
                str(rss_path),
                "--spotify-map",
                str(map_path),
                "--subject-slug",
                "personlighedspsykologi",
                "--allow-unresolved",
            ]
            with mock.patch("sys.argv", argv), mock.patch("sys.stderr", new=io.StringIO()):
                code = self.mod.main()

            self.assertEqual(code, 0)
            payload = self.mod.json.loads(map_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["version"], 1)
            self.assertEqual(payload["subject_slug"], "personlighedspsykologi")
            self.assertEqual(payload["by_rss_title"], {})
            self.assertEqual(
                payload["unresolved_rss_titles"],
                ["Uge 1, Forelæsning 1 · Podcast · Alle kilder"],
            )


if __name__ == "__main__":
    unittest.main()
