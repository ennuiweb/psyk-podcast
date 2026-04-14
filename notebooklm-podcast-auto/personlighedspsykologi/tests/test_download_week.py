import importlib.util
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
    def test_disallowed_brief_quiz_request_log_is_skipped(self):
        mod = _load_module()

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


if __name__ == "__main__":
    unittest.main()
