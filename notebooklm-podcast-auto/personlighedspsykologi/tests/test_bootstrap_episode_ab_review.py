import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


def _load_module():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = (
        repo_root
        / "notebooklm-podcast-auto"
        / "personlighedspsykologi"
        / "scripts"
        / "bootstrap_episode_ab_review.py"
    )
    spec = importlib.util.spec_from_file_location("bootstrap_episode_ab_review", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BootstrapEpisodeABReviewTests(unittest.TestCase):
    def test_normalize_episode_lookup_name_strips_prefix_and_config_tag(self):
        mod = _load_module()

        result = mod.normalize_episode_lookup_name(
            "[Short] W11L1 - Hacking (2007) [EN] {type=audio lang=en format=deep-dive}.mp3"
        )

        self.assertEqual(result, "w11l1 - hacking (2007) [en].mp3")

    def test_classify_episode_distinguishes_prompt_types(self):
        mod = _load_module()

        self.assertEqual(
            mod.classify_episode("W11L1 - Alle kilder (undtagen slides) [EN] {type=audio}.mp3"),
            "weekly_readings_only",
        )
        self.assertEqual(
            mod.classify_episode("W11L1 - Slide lecture: Intro [EN] {type=audio}.mp3"),
            "single_slide",
        )
        self.assertEqual(
            mod.classify_episode("[Short] W11L1 - Hacking (2007) [EN] {type=audio}.mp3"),
            "short",
        )
        self.assertEqual(
            mod.classify_episode("W11L1 - Hacking (2007) [EN] {type=audio}.mp3"),
            "single_reading",
        )
        self.assertIsNone(mod.classify_episode("[TTS] W11L1 - Hacking (2007).mp3"))

    def test_choose_samples_picks_latest_per_prompt_type(self):
        mod = _load_module()
        episodes = [
            {"source_name": "W01L1 - Hacking (2007) [EN] {type=audio}.mp3", "published_at": "2026-04-19T10:00:00+02:00"},
            {"source_name": "W02L1 - Hacking (2007) [EN] {type=audio}.mp3", "published_at": "2026-04-20T10:00:00+02:00"},
            {"source_name": "W01L1 - Slide lecture: Intro [EN] {type=audio}.mp3", "published_at": "2026-04-19T08:00:00+02:00"},
            {"source_name": "W02L1 - Slide lecture: Intro [EN] {type=audio}.mp3", "published_at": "2026-04-20T08:00:00+02:00"},
            {"source_name": "W01L1 - Alle kilder (undtagen slides) [EN] {type=audio}.mp3", "published_at": "2026-04-19T06:00:00+02:00"},
            {"source_name": "W02L1 - Alle kilder (undtagen slides) [EN] {type=audio}.mp3", "published_at": "2026-04-20T06:00:00+02:00"},
            {"source_name": "[Short] W01L1 - Hacking (2007) [EN] {type=audio}.mp3", "published_at": "2026-04-19T04:00:00+02:00"},
            {"source_name": "[Short] W02L1 - Hacking (2007) [EN] {type=audio}.mp3", "published_at": "2026-04-20T04:00:00+02:00"},
        ]

        chosen = mod.choose_samples(
            episodes,
            counts={
                "weekly_readings_only": 1,
                "single_reading": 1,
                "single_slide": 1,
                "short": 1,
            },
        )

        self.assertEqual(
            [item["source_name"] for item in chosen],
            [
                "W02L1 - Alle kilder (undtagen slides) [EN] {type=audio}.mp3",
                "W02L1 - Hacking (2007) [EN] {type=audio}.mp3",
                "W02L1 - Slide lecture: Intro [EN] {type=audio}.mp3",
                "[Short] W02L1 - Hacking (2007) [EN] {type=audio}.mp3",
            ],
        )

    def test_build_entry_uses_reading_summary_source_file(self):
        mod = _load_module()
        episode = {
            "episode_key": "abc",
            "title": "U11F1 · Hacking (2007)",
            "source_name": "W11L1 - Hacking (2007) [EN] {type=audio}.mp3",
            "published_at": "2026-04-20T16:00:00+02:00",
            "audio_url": "https://example.com/audio.mp3",
        }
        reading_index = {
            "w11l1 - hacking (2007) [en].mp3": {
                "summary_lines": ["line"],
                "key_points": ["point"],
                "meta": {"source_file": "/tmp/Hacking.pdf"},
            }
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            entry = mod.build_entry(
                episode,
                run_dir=Path(tmpdir),
                episode_output_root=None,
                reading_index=reading_index,
                weekly_index={},
                slide_index={},
            )

        self.assertEqual(entry["prompt_type"], "single_reading")
        self.assertEqual(entry["source_context"]["source_files"], ["/tmp/Hacking.pdf"])
        self.assertEqual(entry["review"]["status"], "pending")

    def test_resolve_local_audio_path_uses_episode_output_root(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            audio_path = root / "output" / "W11L1" / "W11L1 - Hacking (2007) [EN] {type=audio}.mp3"
            audio_path.parent.mkdir(parents=True, exist_ok=True)
            audio_path.write_bytes(b"mp3")

            result = mod.resolve_local_audio_path(
                {"source_name": "W11L1 - Hacking (2007) [EN] {type=audio}.mp3"},
                root,
            )

        self.assertEqual(result, str(audio_path))


if __name__ == "__main__":
    unittest.main()
