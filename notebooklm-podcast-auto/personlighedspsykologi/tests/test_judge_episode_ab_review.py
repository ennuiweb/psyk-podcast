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
        / "judge_episode_ab_review.py"
    )
    spec = importlib.util.spec_from_file_location("judge_episode_ab_review", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class JudgeEpisodeABReviewTests(unittest.TestCase):
    def test_build_judge_prompt_includes_rubric_context_and_transcripts(self):
        mod = _load_module()
        prompt = mod.build_judge_prompt(
            judge_prompt_template="# Judge Prompt\n\nUse the rubric.",
            entry={
                "sample_id": "single_reading__w11l2__narrative",
                "prompt_type": "single_reading",
                "lecture_key": "W11L2",
                "baseline": {"source_name": "before.mp3"},
                "candidate": {"source_name": "after.mp3"},
                "source_context": {
                    "summary_lines": ["Narrative identity is constructed over time."],
                    "key_points": ["distinguish life story from trait list"],
                },
            },
            source_paths=[Path("/tmp/W11L2 Grundbog kapitel 9.pdf")],
            transcript_a="A transcript",
            transcript_b="B transcript",
        )

        self.assertIn("Episode type: single_reading", prompt)
        self.assertIn("Narrative identity is constructed over time.", prompt)
        self.assertIn("distinguish life story from trait list", prompt)
        self.assertIn("## Transcript A - Baseline\nA transcript", prompt)
        self.assertIn("## Transcript B - Candidate\nB transcript", prompt)

    def test_parse_verdict_extracts_winner_and_confidence(self):
        mod = _load_module()

        parsed = mod.parse_verdict(
            "# sample\n\n## Verdict\n- Overall winner: B\n- Confidence: high\n"
        )

        self.assertEqual(parsed["overall_winner"], "B")
        self.assertEqual(parsed["confidence"], "high")

    def test_source_files_resolve_slide_local_relative_path(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            slide = root / "Forelaesning" / "lecture.pdf"
            slide.parent.mkdir(parents=True)
            slide.write_bytes(b"pdf")

            entry = {
                "sample_id": "single_slide__w01l1__lecture",
                "source_context": {
                    "source_files": ["W01L1/lecture/lecture.pdf"],
                    "catalog_match": {
                        "local_relative_path": "Forelaesning/lecture.pdf",
                    },
                },
            }

            resolved = mod.source_files_for_entry(entry, {"slides_source_root": str(root)})

        self.assertEqual(resolved, [slide.resolve()])

    def test_judge_entry_dry_run_writes_prompt_report_and_manifest_review(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            source = run_dir / "source.pdf"
            source.write_bytes(b"pdf")
            before = run_dir / "transcripts" / "before" / "sample.txt"
            after = run_dir / "transcripts" / "after" / "sample.txt"
            before.parent.mkdir(parents=True)
            after.parent.mkdir(parents=True)
            before.write_text("Before transcript", encoding="utf-8")
            after.write_text("After transcript", encoding="utf-8")
            manifest_path = run_dir / "manifest.json"
            manifest_path.write_text("{}", encoding="utf-8")
            entry = {
                "sample_id": "sample",
                "prompt_type": "short",
                "lecture_key": "W01L1",
                "baseline": {"speaker_transcript_path": "transcripts/before/sample.txt"},
                "candidate": {"speaker_transcript_path": "transcripts/after/sample.txt"},
                "source_context": {"source_files": [str(source)]},
                "review": {"judge_report_path": "judgments/sample.md"},
            }

            report_rel, parsed = mod.judge_entry(
                client=None,
                genai_types=None,
                model="gemini-test",
                manifest_path=manifest_path,
                judge_prompt_template="# Judge Prompt",
                entry=entry,
                config={},
                max_transcript_chars=None,
                max_output_tokens=100,
                request_retries=0,
                request_backoff_seconds=0.1,
                dry_run=True,
            )

            self.assertEqual(report_rel, "judgments/sample.md")
            self.assertEqual(parsed, {"overall_winner": None, "confidence": None})
            self.assertTrue((run_dir / "judge_prompts" / "sample.txt").exists())
            self.assertTrue((run_dir / "judgments" / "sample.md").exists())
            self.assertEqual(entry["review"]["status"], "judged_dry_run")


if __name__ == "__main__":
    unittest.main()
