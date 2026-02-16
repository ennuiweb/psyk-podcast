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

    def test_discover_weekly_overview_keys_includes_only_alle_kilder_audio(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir) / "output"
            week_dir = output_root / "W01L1"
            _touch(week_dir / "W01L1 - Foo [EN].mp3")
            _touch(week_dir / "W01L1 - Alle kilder [EN] {type=audio hash=1234}.mp3")
            _touch(week_dir / "W01L1 - All sources [EN].wav")

            keys, duplicates = mod.discover_weekly_overview_keys(output_root, ["W1"])
            self.assertEqual(duplicates, [])
            self.assertEqual(
                set(keys),
                {
                    "W01L1 - Alle kilder [EN].mp3",
                    "W01L1 - All sources [EN].wav",
                },
            )

    def test_sync_weekly_overview_cache_preserves_manual_text_and_refreshes_meta(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sources_root = root / "sources"
            source_dir = sources_root / "W01L1 Topic"
            source_dir.mkdir(parents=True)
            (source_dir / "A.pdf").write_text("a", encoding="utf-8")
            (source_dir / "B.pdf").write_text("b", encoding="utf-8")

            reading_by_name = {
                "W01L1 - Reading A [EN].mp3": {
                    "summary_lines": ["Reading summary A"],
                    "key_points": ["Reading point A"],
                    "meta": {"source_file": str(source_dir / "A.pdf")},
                },
                "[Brief] W01L1 - Reading A [EN].mp3": {
                    "summary_lines": ["Brief summary A should lose"],
                    "key_points": ["Brief point A should lose"],
                    "meta": {"source_file": str(source_dir / "A.pdf")},
                },
                "[TTS] W01L1 - Reading B.wav": {
                    "summary_lines": ["Reading summary B"],
                    "key_points": ["Reading point B"],
                    "meta": {"source_file": str(source_dir / "B.pdf")},
                },
            }
            weekly_by_name = {
                "W01L1 - Alle kilder [EN].mp3": {
                    "summary_lines": ["Manuel dansk linje"],
                    "key_points": ["Manuelt punkt"],
                    "meta": {"status": "manual_da"},
                }
            }

            added, updated, missing = mod.sync_weekly_overview_cache(
                weekly_by_name,
                ["W01L1 - Alle kilder [EN].mp3"],
                reading_by_name,
                sources_root=sources_root,
                summary_lines_max=4,
                key_points_max=5,
                repo_root=root,
            )
            self.assertEqual(added, [])
            self.assertEqual(updated, ["W01L1 - Alle kilder [EN].mp3"])
            self.assertEqual(missing, [])
            entry = weekly_by_name["W01L1 - Alle kilder [EN].mp3"]
            self.assertEqual(entry["summary_lines"], ["Manuel dansk linje"])
            self.assertEqual(entry["key_points"], ["Manuelt punkt"])
            self.assertEqual(entry["meta"]["source_count_expected"], 2)
            self.assertEqual(entry["meta"]["source_count_covered"], 2)
            self.assertEqual(
                entry["meta"]["draft_from_reading_summaries"]["summary_lines"],
                ["Reading summary A", "Reading summary B"],
            )
            self.assertEqual(
                entry["meta"]["draft_from_reading_summaries"]["key_points"],
                ["Reading point A", "Reading point B"],
            )

    def test_weekly_validation_report_includes_expected_warning_categories(self):
        mod = _load_module()
        weekly_keys = [
            "W01L1 - Alle kilder [EN].mp3",
            "W01L2 - Alle kilder [EN].mp3",
            "W01L3 - Alle kilder [EN].mp3",
        ]
        weekly_by_name = {
            "W01L2 - Alle kilder [EN].mp3": {
                "summary_lines": ["Only one line"],
                "key_points": ["A", "B", "C"],
                "meta": {"source_count_expected": 4, "source_count_covered": 2},
            },
            "W01L3 - Alle kilder [EN].mp3": {
                "summary_lines": ["This weekly summary is still in English."],
                "key_points": ["This point is English", "Another English point", "Third English point"],
                "meta": {"source_count_expected": 2, "source_count_covered": 2},
            },
        }
        report = mod._build_weekly_validation_report(
            weekly_by_name,
            weekly_keys,
            summary_lines_min=2,
            key_points_min=3,
        )
        self.assertEqual(report["weekly_missing_entry"], ["W01L1 - Alle kilder [EN].mp3"])
        self.assertIn("W01L2 - Alle kilder [EN].mp3", report["weekly_incomplete_summary"])
        self.assertIn("W01L2 - Alle kilder [EN].mp3 (2/4)", report["weekly_source_coverage_gap"])
        self.assertIn("W01L3 - Alle kilder [EN].mp3", report["weekly_non_danish"])

    def test_sync_weekly_overview_dry_run_does_not_write_weekly_cache(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_root = root / "output"
            week_dir = output_root / "W01L1"
            _touch(week_dir / "W01L1 - Alle kilder [EN].mp3")

            summaries_file = root / "reading_summaries.json"
            summaries_file.write_text(
                json.dumps({"by_name": {}}),
                encoding="utf-8",
            )
            weekly_summaries_file = root / "weekly_overview_summaries.json"
            sources_root = root / "sources"
            (sources_root / "W01L1 Topic").mkdir(parents=True)

            with mock.patch.object(
                sys,
                "argv",
                [
                    "sync_reading_summaries.py",
                    "--week",
                    "W01L1",
                    "--output-root",
                    str(output_root),
                    "--summaries-file",
                    str(summaries_file),
                    "--weekly-summaries-file",
                    str(weekly_summaries_file),
                    "--sources-root",
                    str(sources_root),
                    "--sync-weekly-overview",
                    "--dry-run",
                ],
            ):
                rc = mod.main()

            self.assertEqual(rc, 0)
            self.assertFalse(weekly_summaries_file.exists())


if __name__ == "__main__":
    unittest.main()
