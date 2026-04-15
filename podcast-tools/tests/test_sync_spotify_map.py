import importlib.util
import io
import json
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


def _write_inventory(path: Path, episodes: list[dict[str, str]]) -> None:
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "subject_slug": "personlighedspsykologi",
                "episodes": episodes,
            }
        ),
        encoding="utf-8",
    )


class SyncSpotifyMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module()

    def test_build_spotify_map_reports_unresolved_titles_when_missing(self):
        by_episode_key, by_rss_title, unresolved, stats = self.mod.build_spotify_map(
            inventory_episodes=[
                {"episode_key": "ep-1", "title": "Uge 1, Forelæsning 1 · Podcast · Alle kilder"},
                {"episode_key": "ep-2", "title": "Uge 1, Forelæsning 1 · Podcast · Lewis (1999)"},
            ],
            existing_payload={},
            spotify_episode_by_title={},
            prune_stale=False,
        )
        self.assertEqual(by_episode_key, {})
        self.assertEqual(by_rss_title, {})
        self.assertEqual(
            unresolved,
            [
                {"episode_key": "ep-1", "title": "Uge 1, Forelæsning 1 · Podcast · Alle kilder"},
                {"episode_key": "ep-2", "title": "Uge 1, Forelæsning 1 · Podcast · Lewis (1999)"},
            ],
        )
        self.assertEqual(stats["unresolved"], 2)

    def test_build_spotify_map_preserves_episode_urls_only_and_ignores_non_episode(self):
        by_episode_key, by_rss_title, unresolved, stats = self.mod.build_spotify_map(
            inventory_episodes=[
                {"episode_key": "ep-1", "title": "Uge 1, Forelæsning 1 · Podcast · Alle kilder"},
                {"episode_key": "ep-2", "title": "Uge 1, Forelæsning 1 · Podcast · Lewis (1999)"},
            ],
            existing_payload={
                "by_episode_key": {
                    "ep-1": "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8",
                    "ep-2": "https://open.spotify.com/search/Uge%201%2C%20Forel%C3%A6sning%201%20%C2%B7%20Podcast%20%C2%B7%20Lewis%20%281999%29/episodes",
                    "stale-1": "https://open.spotify.com/episode/0Yqa6gY5GJfNfQfY7wsY5Y",
                }
            },
            spotify_episode_by_title={},
            prune_stale=False,
        )
        self.assertEqual(
            by_episode_key["ep-1"],
            "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8",
        )
        self.assertEqual(
            by_rss_title["Uge 1, Forelæsning 1 · Podcast · Alle kilder"],
            "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8",
        )
        self.assertNotIn("ep-2", by_episode_key)
        self.assertIn("stale-1", by_episode_key)
        self.assertEqual(
            unresolved,
            [{"episode_key": "ep-2", "title": "Uge 1, Forelæsning 1 · Podcast · Lewis (1999)"}],
        )
        self.assertEqual(stats["preserved_existing"], 1)
        self.assertEqual(stats["carried_stale"], 1)
        self.assertEqual(stats["discarded_non_episode"], 1)

    def test_build_spotify_map_matches_direct_episode_urls_from_show_index(self):
        by_episode_key, by_rss_title, unresolved, stats = self.mod.build_spotify_map(
            inventory_episodes=[{"episode_key": "ep-1", "title": "Uge 1, Forelæsning 1 · Podcast · Alle kilder"}],
            existing_payload={},
            spotify_episode_by_title={
                "uge 1, forelæsning 1 · podcast · alle kilder": (
                    "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8"
                )
            },
            prune_stale=False,
        )
        self.assertEqual(
            by_episode_key["ep-1"],
            "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8",
        )
        self.assertEqual(
            by_rss_title["Uge 1, Forelæsning 1 · Podcast · Alle kilder"],
            "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8",
        )
        self.assertEqual(unresolved, [])
        self.assertEqual(stats["matched_show_episode"], 1)

    def test_build_spotify_map_matches_normalized_show_titles(self):
        by_episode_key, by_rss_title, unresolved, stats = self.mod.build_spotify_map(
            inventory_episodes=[{"episode_key": "ep-1", "title": "U1F1 · [Podcast] · Alle kilder"}],
            existing_payload={},
            spotify_episode_by_title={
                "[Podcast] · Alle kilder": "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8"
            },
            prune_stale=False,
        )
        self.assertEqual(
            by_episode_key["ep-1"],
            "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8",
        )
        self.assertEqual(unresolved, [])
        self.assertEqual(stats["matched_show_episode"], 1)
        self.assertIn("U1F1 · [Podcast] · Alle kilder", by_rss_title)

    def test_build_spotify_map_refreshes_existing_episode_with_show_match(self):
        by_episode_key, _, unresolved, stats = self.mod.build_spotify_map(
            inventory_episodes=[{"episode_key": "ep-1", "title": "Uge 1, Forelæsning 1 · Podcast · Alle kilder"}],
            existing_payload={
                "by_episode_key": {
                    "ep-1": "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8"
                }
            },
            spotify_episode_by_title={
                "uge 1, forelæsning 1 · podcast · alle kilder": (
                    "https://open.spotify.com/episode/0Yqa6gY5GJfNfQfY7wsY5Y"
                )
            },
            prune_stale=False,
        )
        self.assertEqual(
            by_episode_key["ep-1"],
            "https://open.spotify.com/episode/0Yqa6gY5GJfNfQfY7wsY5Y",
        )
        self.assertEqual(unresolved, [])
        self.assertEqual(stats["refreshed_from_show_episode"], 1)

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

    def test_load_inventory_episodes_dedupes_episode_keys(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            inventory_path = Path(temp_dir) / "episode_inventory.json"
            _write_inventory(
                inventory_path,
                [
                    {"episode_key": "ep-1", "title": "Uge 1, Forelæsning 1 · Podcast · Alle kilder"},
                    {"episode_key": "ep-1", "title": "Duplicate should be ignored"},
                    {"episode_key": "ep-2", "title": "Uge 1, Forelæsning 1 · Podcast · Lewis (1999)"},
                ],
            )
            episodes = self.mod.load_inventory_episodes(inventory_path)
        self.assertEqual(
            episodes,
            [
                {"episode_key": "ep-1", "title": "Uge 1, Forelæsning 1 · Podcast · Alle kilder"},
                {"episode_key": "ep-2", "title": "Uge 1, Forelæsning 1 · Podcast · Lewis (1999)"},
            ],
        )

    def test_main_returns_non_zero_when_unresolved_without_allow_unresolved(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            inventory_path = Path(temp_dir) / "episode_inventory.json"
            map_path = Path(temp_dir) / "spotify_map.json"
            _write_inventory(
                inventory_path,
                [{"episode_key": "ep-1", "title": "Uge 1, Forelæsning 1 · Podcast · Alle kilder"}],
            )

            argv = [
                "sync_spotify_map.py",
                "--inventory",
                str(inventory_path),
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
        with tempfile.TemporaryDirectory() as temp_dir:
            inventory_path = Path(temp_dir) / "episode_inventory.json"
            map_path = Path(temp_dir) / "spotify_map.json"
            _write_inventory(
                inventory_path,
                [{"episode_key": "ep-1", "title": "Uge 1, Forelæsning 1 · Podcast · Alle kilder"}],
            )

            argv = [
                "sync_spotify_map.py",
                "--inventory",
                str(inventory_path),
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
            self.assertEqual(payload["version"], 2)
            self.assertEqual(payload["subject_slug"], "personlighedspsykologi")
            self.assertEqual(payload["by_episode_key"], {})
            self.assertEqual(payload["by_rss_title"], {})
            self.assertEqual(payload["unresolved_episode_keys"], ["ep-1"])
            self.assertEqual(
                payload["unresolved_rss_titles"],
                ["Uge 1, Forelæsning 1 · Podcast · Alle kilder"],
            )

    def test_main_can_derive_inventory_path_from_rss(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            show_root = Path(temp_dir) / "shows" / "personlighedspsykologi-en"
            feeds_dir = show_root / "feeds"
            feeds_dir.mkdir(parents=True, exist_ok=True)
            rss_path = feeds_dir / "rss.xml"
            inventory_path = show_root / "episode_inventory.json"
            map_path = show_root / "spotify_map.json"
            rss_path.write_text("<rss version='2.0'><channel /></rss>", encoding="utf-8")
            _write_inventory(
                inventory_path,
                [{"episode_key": "ep-1", "title": "Uge 1, Forelæsning 1 · Podcast · Alle kilder"}],
            )

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
            self.assertEqual(payload["unresolved_episode_keys"], ["ep-1"])

    def test_build_spotify_map_prunes_stale_entries_when_requested(self):
        by_episode_key, _, unresolved, stats = self.mod.build_spotify_map(
            inventory_episodes=[{"episode_key": "ep-1", "title": "Uge 1, Forelæsning 1 · Podcast · Lewis (1999)"}],
            existing_payload={
                "by_episode_key": {
                    "ep-1": "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8",
                    "ep-2": "https://open.spotify.com/episode/0Yqa6gY5GJfNfQfY7wsY5Y",
                }
            },
            spotify_episode_by_title={},
            prune_stale=True,
        )
        self.assertEqual(
            by_episode_key,
            {
                "ep-1": "https://open.spotify.com/episode/5m0hYfDU9ThM5qR2xMugr8",
            },
        )
        self.assertEqual(unresolved, [])
        self.assertEqual(stats["carried_stale"], 0)


if __name__ == "__main__":
    unittest.main()
