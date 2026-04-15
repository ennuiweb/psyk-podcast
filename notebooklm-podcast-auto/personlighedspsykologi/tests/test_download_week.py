import importlib.util
import os
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
        / "download_week.py"
    )
    spec = importlib.util.spec_from_file_location("download_week", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DownloadWeekTests(unittest.TestCase):
    def test_default_output_root_prefers_environment_override(self):
        mod = _load_module()
        with unittest.mock.patch.dict(
            os.environ,
            {mod.OUTPUT_ROOT_ENV_VAR: "/tmp/personlighedspsykologi-output"},
            clear=False,
        ):
            self.assertEqual(mod.default_output_root(), "/tmp/personlighedspsykologi-output")

    def test_disallowed_short_quiz_request_log_is_skipped(self):
        mod = _load_module()

        self.assertTrue(
            mod.is_disallowed_brief_quiz_request_log(
                "/tmp/[Short] W01L1 - Foo [EN] {type=quiz lang=en quantity=standard difficulty=easy hash=beef1234}.json",
                "quiz",
            )
        )
        self.assertTrue(
            mod.is_disallowed_brief_quiz_request_log(
                "/tmp/[Brief] W01L1 - Foo [EN] {type=quiz lang=en quantity=standard difficulty=easy hash=beef1234}.json",
                "quiz",
            )
        )
        self.assertFalse(
            mod.is_disallowed_brief_quiz_request_log(
                "/tmp/[Brief] W01L1 - Foo [EN] {type=audio lang=en format=brief hash=beef1234}.mp3",
                "audio",
            )
        )

    def test_cleanup_request_logs_removes_request_and_error_only(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir) / "artifact.json"
            request_log = base.with_suffix(".json.request.json")
            error_log = base.with_suffix(".json.request.error.json")
            done_log = base.with_suffix(".json.request.done.json")
            request_log.write_text("{}", encoding="utf-8")
            error_log.write_text("{}", encoding="utf-8")
            done_log.write_text("{}", encoding="utf-8")

            mod.cleanup_request_logs(request_log)

            self.assertFalse(request_log.exists())
            self.assertFalse(error_log.exists())
            self.assertTrue(done_log.exists())

    def test_detect_existing_artifact_type_ignores_request_logs(self):
        mod = _load_module()

        self.assertEqual(mod.detect_existing_artifact_type(Path("foo.mp3")), "audio")
        self.assertEqual(mod.detect_existing_artifact_type(Path("foo.png")), "infographic")
        self.assertEqual(mod.detect_existing_artifact_type(Path("foo.json")), "quiz")
        self.assertIsNone(mod.detect_existing_artifact_type(Path("foo.mp3.request.json")))
        self.assertIsNone(mod.detect_existing_artifact_type(Path("foo.json.request.error.json")))

    def test_count_existing_outputs_filters_requested_content_types(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            week_dir = Path(tmpdir) / "W01L1"
            week_dir.mkdir()
            (week_dir / "episode.mp3").write_text("", encoding="utf-8")
            (week_dir / "cover.png").write_text("", encoding="utf-8")
            (week_dir / "quiz.json").write_text("{}", encoding="utf-8")
            (week_dir / "episode.mp3.request.json").write_text("{}", encoding="utf-8")

            counts = mod.count_existing_outputs([week_dir], ["audio", "quiz"])

            self.assertEqual(counts, {"audio": 1, "quiz": 1})

    def test_format_existing_output_counts_omits_zero_values(self):
        mod = _load_module()

        self.assertEqual(
            mod.format_existing_output_counts({"audio": 7, "quiz": 0, "infographic": 2}),
            "audio=7, infographic=2",
        )


if __name__ == "__main__":
    unittest.main()
