import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def _load_module():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = (
        repo_root
        / "notebooklm-podcast-auto"
        / "personlighedspsykologi"
        / "scripts"
        / "transcribe_episode_ab_review.py"
    )
    spec = importlib.util.spec_from_file_location("transcribe_episode_ab_review", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TranscribeEpisodeABReviewTests(unittest.TestCase):
    def test_build_stt_prompt_includes_source_labels_and_key_points(self):
        mod = _load_module()

        prompt = mod.build_stt_prompt(
            {
                "prompt_type": "single_reading",
                "lecture_key": "W10L2",
                "source_context": {
                    "source_files": [
                        "/tmp/W10L2 Davies (1990).pdf",
                        "/tmp/W10L2 Foucault (1997).pdf",
                    ],
                    "key_points": [
                        "power relations are not identical to domination",
                        "freedom practices differ from liberation",
                    ],
                },
            }
        )

        self.assertIn("Episode type: single_reading.", prompt)
        self.assertIn("Lecture key: W10L2.", prompt)
        self.assertIn("W10L2 Davies (1990)", prompt)
        self.assertIn("freedom practices differ from liberation", prompt)

    def test_segment_time_for_size_returns_zero_below_limit(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "audio.mp3"
            path.write_bytes(b"x" * 1024)

            result = mod.segment_time_for_size(path, max_upload_bytes=2048)

        self.assertEqual(result, 0)

    def test_segment_time_for_size_scales_from_duration(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "audio.mp3"
            path.write_bytes(b"x" * 10_000)

            with mock.patch.object(mod, "ffprobe_duration_seconds", return_value=1000.0):
                result = mod.segment_time_for_size(path, max_upload_bytes=1_000)

        self.assertGreaterEqual(result, 300)

    def test_resolve_paths_uses_run_relative_layout(self):
        mod = _load_module()
        manifest_path = Path("/tmp/run/manifest.json")
        entry = {
            "sample_id": "single_reading__w11l1__hacking_2007",
            "baseline": {
                "transcript_path": "transcripts/before/single_reading__w11l1__hacking_2007.txt",
            },
        }

        resolved = mod.resolve_paths(manifest_path, entry, "baseline")

        self.assertEqual(
            resolved["transcript_txt"],
            Path("/tmp/run/transcripts/before/single_reading__w11l1__hacking_2007.txt"),
        )
        self.assertEqual(
            resolved["stt_prompt"],
            Path("/tmp/run/stt_prompts/before/single_reading__w11l1__hacking_2007.txt"),
        )


if __name__ == "__main__":
    unittest.main()
