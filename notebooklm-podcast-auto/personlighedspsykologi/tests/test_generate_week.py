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
        / "generate_week.py"
    )
    spec = importlib.util.spec_from_file_location("generate_week", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _touch(path: Path, payload: bytes = b"data") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


class GenerateWeekTests(unittest.TestCase):
    def test_should_skip_generation_accepts_legacy_weekly_overview_output(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            week_dir = Path(tmpdir) / "W1L1"
            legacy_output = (
                week_dir
                / "W1L1 - Alle kilder [EN] {type=quiz lang=en quantity=standard difficulty=easy download=json hash=0aa8e6f0}.json"
            )
            _touch(legacy_output, b"{}")

            canonical_output = (
                week_dir
                / "W1L1 - Alle kilder (undtagen slides) [EN] {type=quiz lang=en quantity=standard difficulty=easy download=json hash=0aa8e6f0}.json"
            )
            should_skip, reason = mod.should_skip_generation(canonical_output, True)

            self.assertTrue(should_skip)
            self.assertEqual(reason, "output exists")

    def test_should_skip_generation_accepts_legacy_weekly_overview_request_log(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            week_dir = Path(tmpdir) / "W1L1"
            legacy_output = (
                week_dir
                / "W1L1 - Alle kilder [EN] {type=quiz lang=en quantity=standard difficulty=medium download=json hash=05f7d73e}.json"
            )
            legacy_output.parent.mkdir(parents=True, exist_ok=True)
            legacy_log = legacy_output.with_suffix(".json.request.json")
            legacy_log.write_text(json.dumps({"artifact_id": "artifact-123"}), encoding="utf-8")

            canonical_output = (
                week_dir
                / "W1L1 - Alle kilder (undtagen slides) [EN] {type=quiz lang=en quantity=standard difficulty=medium download=json hash=05f7d73e}.json"
            )
            should_skip, reason = mod.should_skip_generation(canonical_output, True)

            self.assertTrue(should_skip)
            self.assertEqual(reason, "request log exists")

    def test_migrate_legacy_weekly_overview_outputs_renames_files(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            week_dir = Path(tmpdir) / "W1L1"
            legacy_audio = (
                week_dir
                / "W1L1 - Alle kilder [EN] {type=audio lang=en format=deep-dive length=long sources=2 hash=f104a13e}.mp3"
            )
            legacy_quiz = (
                week_dir
                / "W1L1 - Alle kilder [EN] {type=quiz lang=en quantity=standard difficulty=hard download=json hash=f06c6752}.json"
            )
            _touch(legacy_audio)
            _touch(legacy_quiz, b"{}")

            migrated = mod.migrate_legacy_weekly_overview_outputs(week_dir)

            self.assertEqual(len(migrated), 2)
            self.assertFalse(legacy_audio.exists())
            self.assertFalse(legacy_quiz.exists())
            self.assertTrue(
                (
                    week_dir
                    / "W1L1 - Alle kilder (undtagen slides) [EN] {type=audio lang=en format=deep-dive length=long sources=2 hash=f104a13e}.mp3"
                ).exists()
            )
            self.assertTrue(
                (
                    week_dir
                    / "W1L1 - Alle kilder (undtagen slides) [EN] {type=quiz lang=en quantity=standard difficulty=hard download=json hash=f06c6752}.json"
                ).exists()
            )

    def test_should_skip_generation_accepts_legacy_prefixed_reading_output(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            week_dir = Path(tmpdir) / "W2L1"
            legacy_output = (
                week_dir
                / "W2L1 - X Zettler et al. (2020) [EN] {type=quiz lang=en quantity=standard difficulty=easy download=json hash=0aa8e6f0}.json"
            )
            _touch(legacy_output, b"{}")

            canonical_output = (
                week_dir
                / "W2L1 - Zettler et al. (2020) [EN] {type=quiz lang=en quantity=standard difficulty=easy download=json hash=0aa8e6f0}.json"
            )
            should_skip, reason = mod.should_skip_generation(canonical_output, True)

            self.assertTrue(should_skip)
            self.assertEqual(reason, "output exists")

    def test_migrate_legacy_prefixed_reading_outputs_renames_files(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            week_dir = Path(tmpdir) / "W2L1"
            legacy_audio = (
                week_dir
                / "W2L1 - X Zettler et al. (2020) [EN] {type=audio lang=en format=deep-dive length=long hash=fa9adbcf}.mp3"
            )
            legacy_quiz = (
                week_dir
                / "W2L1 - X Zettler et al. (2020) [EN] {type=quiz lang=en quantity=standard difficulty=medium download=json hash=05f7d73e}.json"
            )
            _touch(legacy_audio)
            _touch(legacy_quiz, b"{}")

            migrated = mod.migrate_legacy_prefixed_reading_outputs(week_dir)

            self.assertEqual(len(migrated), 2)
            self.assertFalse(legacy_audio.exists())
            self.assertFalse(legacy_quiz.exists())
            self.assertTrue(
                (
                    week_dir
                    / "W2L1 - Zettler et al. (2020) [EN] {type=audio lang=en format=deep-dive length=long hash=fa9adbcf}.mp3"
                ).exists()
            )
            self.assertTrue(
                (
                    week_dir
                    / "W2L1 - Zettler et al. (2020) [EN] {type=quiz lang=en quantity=standard difficulty=medium download=json hash=05f7d73e}.json"
                ).exists()
            )


if __name__ == "__main__":
    unittest.main()
