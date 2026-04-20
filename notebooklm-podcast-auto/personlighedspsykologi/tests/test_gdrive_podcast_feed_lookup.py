import importlib.util
import unittest
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "podcast-tools" / "gdrive_podcast_feed.py"
    spec = importlib.util.spec_from_file_location("gdrive_podcast_feed", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GDrivePodcastFeedLookupTests(unittest.TestCase):
    def test_lookup_matches_legacy_weekly_overview_name(self):
        mod = _load_module()
        mapping = {
            "W05L1 - Alle kilder [EN].mp3": {
                "summary_lines": ["L1", "L2"],
                "key_points": ["A", "B", "C"],
            }
        }

        match = mod._lookup_by_name_with_cfg_fallback(
            mapping,
            "W05L1 - Alle kilder (undtagen slides) [EN].mp3",
        )

        self.assertIs(match, mapping["W05L1 - Alle kilder [EN].mp3"])

    def test_lookup_matches_long_and_short_foucault_titles(self):
        mod = _load_module()
        mapping = {
            "W10L2 - Foucault, M. (1997). The Ethics of the Concern of the Self as a Practice of Freedom - Essential Works 1954-1984, Penguin Books. Vol. 1, s. 281-301 [EN].mp3": {
                "summary_lines": ["L1", "L2"],
                "key_points": ["A", "B", "C"],
            }
        }

        match = mod._lookup_by_name_with_cfg_fallback(
            mapping,
            "W10L2 - Foucault, M. (1997). s. 281-301 [EN] {type=audio lang=en format=deep-dive length=long hash=fa9adbcf}.mp3",
        )

        self.assertIsNotNone(match)
        self.assertEqual(match["summary_lines"], ["L1", "L2"])

    def test_registry_selection_prefers_active_b_variant(self):
        mod = _load_module()
        entry = {
            "logical_episode_id": "short__w11l1__gergen_1999_en",
            "active_variant": "B",
            "variants": {
                "A": {
                    "episode_key": "old-short-id",
                    "source_name": "[Short] W11L1 - Gergen (1999) [EN] {type=audio hash=old}.mp3",
                },
                "B": {
                    "episode_key": "new-short-id",
                    "source_name": "[Short] W11L1 - Gergen (1999) [EN] {type=audio hash=new}.mp3",
                },
            },
        }
        registry = {entry["logical_episode_id"]: entry}

        include, logical_id, matched_slot = mod._registry_selection_for_file(
            {
                "id": "new-short-id",
                "name": "[Short] W11L1 - Gergen (1999) [EN] {type=audio hash=new}.mp3",
            },
            registry,
        )

        self.assertTrue(include)
        self.assertEqual(logical_id, entry["logical_episode_id"])
        self.assertEqual(matched_slot, "B")

    def test_registry_selection_skips_old_a_when_b_is_active(self):
        mod = _load_module()
        entry = {
            "logical_episode_id": "short__w11l1__gergen_1999_en",
            "active_variant": "B",
            "variants": {
                "A": {
                    "episode_key": "old-short-id",
                    "source_name": "[Short] W11L1 - Gergen (1999) [EN] {type=audio hash=old}.mp3",
                },
                "B": {
                    "episode_key": "new-short-id",
                    "source_name": "[Short] W11L1 - Gergen (1999) [EN] {type=audio hash=new}.mp3",
                },
            },
        }
        registry = {entry["logical_episode_id"]: entry}

        include, logical_id, matched_slot = mod._registry_selection_for_file(
            {
                "id": "old-short-id",
                "name": "[Short] W11L1 - Gergen (1999) [EN] {type=audio hash=old}.mp3",
            },
            registry,
        )

        self.assertFalse(include)
        self.assertEqual(logical_id, entry["logical_episode_id"])
        self.assertEqual(matched_slot, "A")


if __name__ == "__main__":
    unittest.main()
