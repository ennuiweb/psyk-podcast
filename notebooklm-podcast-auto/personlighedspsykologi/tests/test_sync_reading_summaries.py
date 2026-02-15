import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


def _load_module():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = (
        repo_root
        / "notebooklm-podcast-auto"
        / "personlighedspsykologi"
        / "scripts"
        / "sync_reading_summaries.py"
    )
    spec = importlib.util.spec_from_file_location("sync_reading_summaries", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"audio")


class SyncReadingSummariesTests(unittest.TestCase):
    def test_discover_episode_keys_includes_reading_brief_tts_and_excludes_weekly(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir) / "output"
            week_dir = output_root / "W01L1"
            _touch(week_dir / "W01L1 - Core Reading [EN] {type=audio hash=1234}.mp3")
            _touch(week_dir / "[Brief] W01L1 - Core Reading [EN].mp3")
            _touch(week_dir / "W01L1 - Oplæst Core Reading [EN].mp3")
            _touch(week_dir / "W01L1 - All sources [EN].mp3")
            _touch(week_dir / "W01L1 - Alle kilder [EN].wav")
            _touch(week_dir / "ignore.txt")

            keys, duplicates = mod.discover_episode_keys(output_root, ["W1"])
            self.assertEqual(duplicates, [])
            self.assertEqual(
                set(keys),
                {
                    "W01L1 - Core Reading [EN].mp3",
                    "[Brief] W01L1 - Core Reading [EN].mp3",
                    "W01L1 - Oplæst Core Reading [EN].mp3",
                },
            )

    def test_main_adds_missing_placeholders_without_overwriting_existing(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_root = root / "output"
            week_dir = output_root / "W02L1"
            _touch(week_dir / "W02L1 - Existing [EN].mp3")
            _touch(week_dir / "W02L1 - Missing [EN].mp3")

            summaries_file = root / "reading_summaries.json"
            summaries_file.write_text(
                json.dumps(
                    {
                        "by_name": {
                            "W02L1 - Existing [EN].mp3": {
                                "summary_lines": ["Keep me 1", "Keep me 2"],
                                "key_points": ["Keep 1", "Keep 2", "Keep 3"],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            with mock.patch.object(
                sys,
                "argv",
                [
                    "sync_reading_summaries.py",
                    "--week",
                    "W02",
                    "--output-root",
                    str(output_root),
                    "--summaries-file",
                    str(summaries_file),
                ],
            ):
                rc = mod.main()

            self.assertEqual(rc, 0)
            updated = json.loads(summaries_file.read_text(encoding="utf-8"))
            self.assertEqual(
                updated["by_name"]["W02L1 - Existing [EN].mp3"]["summary_lines"],
                ["Keep me 1", "Keep me 2"],
            )
            self.assertEqual(
                updated["by_name"]["W02L1 - Missing [EN].mp3"],
                {"summary_lines": [], "key_points": []},
            )

    def test_dry_run_does_not_write_summaries_file(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_root = root / "output"
            week_dir = output_root / "W03L1"
            _touch(week_dir / "W03L1 - Foo [EN].mp3")
            summaries_file = root / "reading_summaries.json"

            with mock.patch.object(
                sys,
                "argv",
                [
                    "sync_reading_summaries.py",
                    "--week",
                    "W03",
                    "--output-root",
                    str(output_root),
                    "--summaries-file",
                    str(summaries_file),
                    "--dry-run",
                ],
            ):
                rc = mod.main()

            self.assertEqual(rc, 0)
            self.assertFalse(summaries_file.exists())

    def test_validate_only_reports_missing_and_incomplete_entries(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_root = root / "output"
            week_dir = output_root / "W04L1"
            _touch(week_dir / "W04L1 - Missing [EN].mp3")
            _touch(week_dir / "W04L1 - Incomplete Summary [EN].mp3")
            _touch(week_dir / "W04L1 - Incomplete Points [EN].mp3")
            _touch(week_dir / "W04L1 - Complete [EN].mp3")

            summaries_file = root / "reading_summaries.json"
            summaries_file.write_text(
                json.dumps(
                    {
                        "by_name": {
                            "W04L1 - Incomplete Summary [EN].mp3": {
                                "summary_lines": ["Only one"],
                                "key_points": ["A", "B", "C"],
                            },
                            "W04L1 - Incomplete Points [EN].mp3": {
                                "summary_lines": ["L1", "L2"],
                                "key_points": ["A", "B"],
                            },
                            "W04L1 - Complete [EN].mp3": {
                                "summary_lines": ["L1", "L2"],
                                "key_points": ["A", "B", "C"],
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                with mock.patch.object(
                    sys,
                    "argv",
                    [
                        "sync_reading_summaries.py",
                        "--week",
                        "W04",
                        "--output-root",
                        str(output_root),
                        "--summaries-file",
                        str(summaries_file),
                        "--validate-only",
                    ],
                ):
                    rc = mod.main()

            self.assertEqual(rc, 0)
            output = buffer.getvalue()
            self.assertIn("missing_entry: 1", output)
            self.assertIn("incomplete_summary: 1", output)
            self.assertIn("incomplete_key_points: 1", output)
            self.assertIn("W04L1 - Missing [EN].mp3", output)

    def test_validate_only_uses_custom_min_thresholds(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_root = root / "output"
            week_dir = output_root / "W05L1"
            _touch(week_dir / "W05L1 - Threshold Test [EN].mp3")

            summaries_file = root / "reading_summaries.json"
            summaries_file.write_text(
                json.dumps(
                    {
                        "by_name": {
                            "W05L1 - Threshold Test [EN].mp3": {
                                "summary_lines": ["L1", "L2"],
                                "key_points": ["A", "B", "C"],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                with mock.patch.object(
                    sys,
                    "argv",
                    [
                        "sync_reading_summaries.py",
                        "--week",
                        "W05",
                        "--output-root",
                        str(output_root),
                        "--summaries-file",
                        str(summaries_file),
                        "--validate-only",
                        "--summary-lines-min",
                        "3",
                        "--key-points-min",
                        "4",
                    ],
                ):
                    rc = mod.main()

            self.assertEqual(rc, 0)
            output = buffer.getvalue()
            self.assertIn("incomplete_summary: 1", output)
            self.assertIn("incomplete_key_points: 1", output)

    def test_no_request_log_dependency_when_only_request_files_exist(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_root = root / "output"
            week_dir = output_root / "W06L1"
            week_dir.mkdir(parents=True)
            (week_dir / "foo.request.json").write_text("{}", encoding="utf-8")

            summaries_file = root / "reading_summaries.json"
            summaries_file.write_text('{"by_name": {}}', encoding="utf-8")

            buffer = io.StringIO()
            with redirect_stdout(buffer):
                with mock.patch.object(
                    sys,
                    "argv",
                    [
                        "sync_reading_summaries.py",
                        "--week",
                        "W06",
                        "--output-root",
                        str(output_root),
                        "--summaries-file",
                        str(summaries_file),
                    ],
                ):
                    rc = mod.main()

            self.assertEqual(rc, 0)
            self.assertIn("No local reading/brief/tts episode files found", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
