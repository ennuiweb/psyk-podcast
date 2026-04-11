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
    def test_build_source_items_excludes_seminar_slides(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            week_dir = root / "W1L1"
            week_dir.mkdir(parents=True, exist_ok=True)
            _touch(week_dir / "Grundbog kapitel 1.pdf")

            slides_root = root / "slides"
            lecture_slide = slides_root / "lecture.pdf"
            seminar_slide = slides_root / "seminar.pdf"
            exercise_slide = slides_root / "exercise.pdf"
            _touch(lecture_slide)
            _touch(seminar_slide)
            _touch(exercise_slide)

            slides_catalog = root / "slides_catalog.json"
            slides_catalog.write_text(
                json.dumps(
                    {
                        "slides": [
                            {
                                "lecture_key": "W01L1",
                                "subcategory": "lecture",
                                "title": "Lecture title",
                                "local_relative_path": lecture_slide.name,
                            },
                            {
                                "lecture_key": "W01L1",
                                "subcategory": "seminar",
                                "title": "Seminar title",
                                "local_relative_path": seminar_slide.name,
                            },
                            {
                                "lecture_key": "W01L1",
                                "subcategory": "exercise",
                                "title": "Exercise title",
                                "local_relative_path": exercise_slide.name,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            reading_sources, generation_sources = mod.build_source_items(
                week_dir=week_dir,
                week_label="W01L1",
                slides_catalog_path=slides_catalog,
                slides_source_root=slides_root,
            )

            self.assertEqual([item.base_name for item in reading_sources], ["Grundbog kapitel 1"])
            self.assertEqual(
                [item.base_name for item in generation_sources],
                [
                    "Grundbog kapitel 1",
                    "Slide lecture: Lecture title",
                    "Slide exercise: Exercise title",
                ],
            )
            self.assertEqual(
                [item.slide_subcategory for item in generation_sources if item.source_type == "slide"],
                ["lecture", "exercise"],
            )

    def test_cleanup_disallowed_slide_outputs_removes_seminar_artifacts(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            week_dir = Path(tmpdir) / "W1L1"
            seminar_audio = (
                week_dir
                / "W1L1 - Slide seminar: 1. Introduktion [EN] {type=audio lang=en format=deep-dive length=long hash=fa9adbcf}.mp3"
            )
            seminar_request = seminar_audio.with_suffix(".mp3.request.json")
            lecture_audio = (
                week_dir
                / "W1L1 - Slide lecture: 1. gang [EN] {type=audio lang=en format=deep-dive length=long hash=fa9adbcf}.mp3"
            )
            _touch(seminar_audio)
            _touch(seminar_request, b"{}")
            _touch(lecture_audio)

            removed = mod.cleanup_disallowed_slide_outputs(week_dir)

            self.assertEqual(
                {path.name for path in removed},
                {seminar_audio.name, seminar_request.name},
            )
            self.assertFalse(seminar_audio.exists())
            self.assertFalse(seminar_request.exists())
            self.assertTrue(lecture_audio.exists())

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

    def test_update_profile_cooldowns_handles_profile_error_logs(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "W6L1 - Spinelli.mp3"
            error_log = output_path.with_suffix(".mp3.request.error.json")
            error_log.write_text(
                json.dumps(
                    {
                        "auth": {"profile": "default"},
                        "error_type": "profile_error",
                        "error": "No result found for RPC ID: CCqFvf",
                    }
                ),
                encoding="utf-8",
            )

            cooldowns: dict[str, float] = {}
            mod.update_profile_cooldowns(output_path, cooldowns, 300, 3600)

            self.assertIn("default", cooldowns)
            self.assertGreater(cooldowns["default"], 0)


if __name__ == "__main__":
    unittest.main()
