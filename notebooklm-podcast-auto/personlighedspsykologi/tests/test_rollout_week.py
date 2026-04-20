import importlib.util
import unittest
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = (
        repo_root
        / "notebooklm-podcast-auto"
        / "personlighedspsykologi"
        / "scripts"
        / "rollout_week.py"
    )
    spec = importlib.util.spec_from_file_location("rollout_week", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RolloutWeekTests(unittest.TestCase):
    def test_build_exclude_regex_for_short_uses_title_fragment(self):
        mod = _load_module()

        pattern = mod.build_exclude_regex(
            "[Short] W11L1 - Gergen (1999) [EN] {type=audio lang=en format=deep-dive length=short hash=c3f67e82}.mp3"
        )

        self.assertIsNotNone(pattern)
        self.assertIn("Gergen", pattern)
        self.assertIn("c3f67e82", pattern)

    def test_merge_b_variant_preserves_review_fields(self):
        mod = _load_module()
        existing = {
            "episode_key": "old-id",
            "review_outcome": "accepted",
            "judged_at": "2026-04-18T10:00:00Z",
            "transcribed_at": "2026-04-18T09:00:00Z",
        }
        updates = {
            "episode_key": "new-id",
            "review_outcome": None,
            "judged_at": None,
            "transcribed_at": None,
        }

        merged = mod.merge_b_variant(existing, updates)

        self.assertEqual(merged["episode_key"], "new-id")
        self.assertEqual(merged["review_outcome"], "accepted")
        self.assertEqual(merged["judged_at"], "2026-04-18T10:00:00Z")
        self.assertEqual(merged["transcribed_at"], "2026-04-18T09:00:00Z")
        self.assertEqual(len(merged["history"]), 1)
        self.assertEqual(merged["history"][0]["episode_key"], "old-id")


if __name__ == "__main__":
    unittest.main()
