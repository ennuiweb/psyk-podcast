import importlib.util
import json
import sys
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
        / "sync_reading_summaries.py"
    )
    spec = importlib.util.spec_from_file_location("sync_reading_summaries", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SyncReadingSummariesTests(unittest.TestCase):
    def test_collect_reading_requests_includes_reading_and_brief_excludes_weekly(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            week_dir = Path(tmpdir) / "W01L1"
            week_dir.mkdir(parents=True)
            payloads = {
                "reading.request.json": {
                    "artifact_type": "audio",
                    "output_path": str(week_dir / "W01L1 - Foo [EN].mp3"),
                },
                "brief.request.json": {
                    "artifact_type": "audio",
                    "output_path": str(week_dir / "[Brief] W01L1 - Foo [EN].mp3"),
                },
                "weekly.request.json": {
                    "artifact_type": "audio",
                    "output_path": str(week_dir / "W01L1 - Alle kilder [EN].mp3"),
                },
                "infographic.request.json": {
                    "artifact_type": "infographic",
                    "output_path": str(week_dir / "W01L1 - Foo [EN].png"),
                },
            }
            for name, payload in payloads.items():
                (week_dir / name).write_text(json.dumps(payload), encoding="utf-8")

            candidates = mod.collect_reading_requests(week_dir)
            names = {Path(item[1]["output_path"]).name for item in candidates}
            self.assertEqual(
                names,
                {"W01L1 - Foo [EN].mp3", "[Brief] W01L1 - Foo [EN].mp3"},
            )

    def test_parse_ask_summary_payload_success(self):
        mod = _load_module()
        payload = {
            "answer": json.dumps(
                {
                    "summary_lines": ["Line 1", "Line 2", "Line 3"],
                    "key_points": ["Point 1", "Point 2", "Point 3"],
                }
            )
        }
        parsed = mod.parse_ask_summary_payload(payload)
        self.assertIsNotNone(parsed)
        summary_lines, key_points = parsed
        self.assertEqual(summary_lines[0], "Line 1")
        self.assertEqual(key_points[0], "Point 1")

    def test_build_summary_entry_falls_back_to_source_guide_when_ask_not_json(self):
        mod = _load_module()
        payload = {
            "artifact_type": "audio",
            "output_path": "/tmp/W01L1 - Foo [EN].mp3",
            "notebook_id": "nb_123",
            "sources": [{"kind": "file", "value": "/tmp/Foo.pdf"}],
        }
        responses = [
            {
                "notebook_id": "nb_123",
                "sources": [
                    {
                        "id": "src_123",
                        "title": "Foo.pdf",
                        "url": None,
                    }
                ],
            },
            {"answer": "This is not JSON"},
            {
                "summary": "Guide summary one. Guide summary two. Guide summary three.",
                "keywords": ["Alpha", "Beta", "Gamma", "Delta"],
            },
        ]
        with mock.patch.object(mod, "_run_notebooklm_json", side_effect=responses):
            key, entry = mod._build_summary_entry(
                notebooklm_cli=Path("/bin/echo"),
                storage_path=None,
                payload=payload,
                min_summary=2,
                max_summary=4,
                min_points=3,
                max_points=5,
            )
        self.assertEqual(key, "W01L1 - Foo [EN].mp3")
        self.assertEqual(entry["meta"]["method"], "source_guide_fallback_v1")
        self.assertGreaterEqual(len(entry["summary_lines"]), 2)
        self.assertGreaterEqual(len(entry["key_points"]), 3)

    def test_normalization_enforces_limits(self):
        mod = _load_module()
        summary_lines = mod.normalize_summary_lines(
            ["A. B. C. D. E."],
            min_count=2,
            max_count=4,
            source_title="Foo.pdf",
        )
        self.assertLessEqual(len(summary_lines), 4)
        self.assertGreaterEqual(len(summary_lines), 2)

        key_points = mod.normalize_key_points(
            ["One", "Two", "Three", "Four", "Five", "Six"],
            min_count=3,
            max_count=5,
            source_title="Foo.pdf",
            summary_lines=summary_lines,
        )
        self.assertLessEqual(len(key_points), 5)
        self.assertGreaterEqual(len(key_points), 3)

    def test_refresh_overwrites_existing_entry(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_root = root / "output"
            week_dir = output_root / "W01L1"
            week_dir.mkdir(parents=True)
            request_payload = {
                "artifact_type": "audio",
                "output_path": str(week_dir / "W01L1 - Foo [EN].mp3"),
                "notebook_id": "nb_123",
                "sources": [{"kind": "file", "value": "/tmp/Foo.pdf"}],
            }
            (week_dir / "foo.request.json").write_text(
                json.dumps(request_payload),
                encoding="utf-8",
            )
            summaries_file = root / "reading_summaries.json"
            summaries_file.write_text(
                json.dumps(
                    {
                        "by_name": {
                            "W01L1 - Foo [EN].mp3": {
                                "summary_lines": ["Old line 1", "Old line 2"],
                                "key_points": ["Old point 1", "Old point 2", "Old point 3"],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            new_entry = {
                "summary_lines": ["New line 1", "New line 2"],
                "key_points": ["New point 1", "New point 2", "New point 3"],
                "meta": {"method": "ask_json_with_guide_fallback_v1"},
            }

            with mock.patch.object(mod, "_build_summary_entry", return_value=("W01L1 - Foo [EN].mp3", new_entry)) as builder:
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
                        "--notebooklm-cli",
                        sys.executable,
                    ],
                ):
                    rc = mod.main()
            self.assertEqual(rc, 0)
            builder.assert_not_called()

            with mock.patch.object(mod, "_build_summary_entry", return_value=("W01L1 - Foo [EN].mp3", new_entry)) as builder:
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
                        "--notebooklm-cli",
                        sys.executable,
                        "--refresh",
                    ],
                ):
                    rc = mod.main()
            self.assertEqual(rc, 0)
            builder.assert_called_once()
            updated = json.loads(summaries_file.read_text(encoding="utf-8"))
            self.assertEqual(
                updated["by_name"]["W01L1 - Foo [EN].mp3"]["summary_lines"],
                ["New line 1", "New line 2"],
            )

    def test_dry_run_does_not_write_summaries_file(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_root = root / "output"
            week_dir = output_root / "W01L1"
            week_dir.mkdir(parents=True)
            request_payload = {
                "artifact_type": "audio",
                "output_path": str(week_dir / "W01L1 - Foo [EN].mp3"),
                "notebook_id": "nb_123",
                "sources": [{"kind": "file", "value": "/tmp/Foo.pdf"}],
            }
            (week_dir / "foo.request.json").write_text(
                json.dumps(request_payload),
                encoding="utf-8",
            )
            summaries_file = root / "reading_summaries.json"
            new_entry = {
                "summary_lines": ["New line 1", "New line 2"],
                "key_points": ["New point 1", "New point 2", "New point 3"],
                "meta": {"method": "ask_json_with_guide_fallback_v1"},
            }

            with mock.patch.object(mod, "_build_summary_entry", return_value=("W01L1 - Foo [EN].mp3", new_entry)):
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
                        "--notebooklm-cli",
                        sys.executable,
                        "--dry-run",
                    ],
                ):
                    rc = mod.main()
            self.assertEqual(rc, 0)
            self.assertFalse(summaries_file.exists())


if __name__ == "__main__":
    unittest.main()
