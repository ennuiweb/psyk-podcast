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
        / "sync_episode_ab_review_candidates.py"
    )
    spec = importlib.util.spec_from_file_location("sync_episode_ab_review_candidates", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SyncEpisodeABReviewCandidatesTests(unittest.TestCase):
    def test_sync_manifest_matches_candidate_audio_by_title_without_hash(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_dir = root / "run"
            output_root = root / "candidate_output"
            audio_path = (
                output_root
                / "W11L1"
                / "W11L1 - Hacking [EN] {type=audio lang=en hash=newhash}.mp3"
            )
            audio_path.parent.mkdir(parents=True, exist_ok=True)
            audio_path.write_bytes(b"mp3")
            manifest_path = run_dir / "manifest.json"
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(
                json.dumps(
                    {
                        "status": "before_only",
                        "entries": [
                            {
                                "sample_id": "single_reading__w11l1__hacking",
                                "lecture_key": "W11L1",
                                "baseline": {
                                    "title": "Hacking",
                                    "source_name": (
                                        "W11L1 - Hacking [EN] "
                                        "{type=audio lang=en hash=oldhash}.mp3"
                                    ),
                                },
                                "candidate": {},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            manifest, lines = mod.sync_manifest(manifest_path, output_root)

        candidate = manifest["entries"][0]["candidate"]
        self.assertEqual(candidate["source_name"], audio_path.name)
        self.assertEqual(candidate["local_audio_path"], str(audio_path.resolve()))
        self.assertEqual(candidate["transcription_status"], "pending")
        self.assertEqual(manifest["status"], "candidate_audio_ready")
        self.assertIn("summary: matched 1, missing 0", lines)


if __name__ == "__main__":
    unittest.main()
