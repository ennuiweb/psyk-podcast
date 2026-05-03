import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from notebooklm_queue import course_context


class CourseContextTests(unittest.TestCase):
    def test_load_bundle_resolves_show_paths_from_slides_catalog(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            show_dir = repo_root / "shows" / "demo-show"
            docs_dir = show_dir / "docs"
            docs_dir.mkdir(parents=True, exist_ok=True)

            (show_dir / "slides_catalog.json").write_text(json.dumps({"slides": []}), encoding="utf-8")
            (show_dir / "content_manifest.json").write_text(
                json.dumps(
                    {
                        "lectures": [
                            {
                                "lecture_key": "W1L1",
                                "lecture_title": "Intro",
                                "sequence_index": 1,
                                "readings": [],
                                "slides": [],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (docs_dir / "overblik.md").write_text("- W1L1 Intro\n- W1L2 Next", encoding="utf-8")

            config = course_context.normalize_course_context({})
            bundle = course_context.load_course_prompt_context_bundle(
                repo_root=repo_root,
                config=config,
                slides_catalog_path=show_dir / "slides_catalog.json",
            )

            assert bundle is not None
            self.assertEqual(bundle.content_manifest_path, (show_dir / "content_manifest.json").resolve())
            self.assertEqual(bundle.course_overview_path, (docs_dir / "overblik.md").resolve())
            self.assertEqual(bundle.lecture_index["W01L1"], 0)

    def test_build_course_prompt_context_note_includes_course_slide_and_source_fit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            show_dir = repo_root / "shows" / "demo-show"
            docs_dir = show_dir / "docs"
            docs_dir.mkdir(parents=True, exist_ok=True)

            (show_dir / "slides_catalog.json").write_text(json.dumps({"slides": []}), encoding="utf-8")
            (show_dir / "content_manifest.json").write_text(
                json.dumps(
                    {
                        "lectures": [
                            {
                                "lecture_key": "W1L1",
                                "lecture_title": "Introduktion",
                                "sequence_index": 1,
                                "summary": {
                                    "summary_lines": [
                                        "Lecturen introduces the course's core disputes."
                                    ],
                                    "key_points": [
                                        "Definitions of personality shape method choices."
                                    ],
                                },
                                "readings": [
                                    {
                                        "reading_title": "Grundbog kapitel 1",
                                        "source_filename": "W1L1 Grundbog kapitel 1.pdf",
                                        "summary": {
                                            "summary_lines": [
                                                "The chapter maps the field's main conceptual tensions."
                                            ],
                                            "key_points": [
                                                "Competing definitions imply different evidence standards."
                                            ],
                                        },
                                    }
                                ],
                                "slides": [
                                    {
                                        "slide_key": "lecture-1",
                                        "subcategory": "lecture",
                                        "title": "Hvad er personlighed?",
                                        "source_filename": "lecture.pdf",
                                    },
                                    {
                                        "slide_key": "seminar-1",
                                        "subcategory": "seminar",
                                        "title": "Diskussionsspoergsmaal",
                                        "source_filename": "seminar.pdf",
                                    },
                                ],
                            },
                            {
                                "lecture_key": "W1L2",
                                "lecture_title": "Fortsat",
                                "sequence_index": 2,
                                "readings": [],
                                "slides": [],
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (docs_dir / "overblik.md").write_text(
                "- W1L1 Introduktion\n- W1L2 Fortsat",
                encoding="utf-8",
            )

            config = course_context.normalize_course_context({})
            bundle = course_context.load_course_prompt_context_bundle(
                repo_root=repo_root,
                config=config,
                slides_catalog_path=show_dir / "slides_catalog.json",
            )
            assert bundle is not None

            reading_note = course_context.build_course_prompt_context_note(
                bundle=bundle,
                config=config,
                lecture_key="W1L1",
                prompt_type="single_reading",
                source_item=SimpleNamespace(
                    source_type="reading",
                    base_name="Grundbog kapitel 1",
                    path=Path("/tmp/W1L1 Grundbog kapitel 1.pdf"),
                ),
            )

            self.assertIn("Course position: lecture 1 of 2", reading_note)
            self.assertIn("Current lecture theme: Introduktion.", reading_note)
            self.assertIn("Broader course themes in play across the semester: Introduktion; Fortsat.", reading_note)
            self.assertIn("Course overview excerpt:", reading_note)
            self.assertIn("## Source character", reading_note)
            self.assertIn("This is a textbook chapter", reading_note)
            self.assertIn("Forelaesning slides frame the lecture through: Hvad er personlighed?", reading_note)
            self.assertIn("Seminar slides operationalize or test the material through: Diskussionsspoergsmaal.", reading_note)
            self.assertIn("Grundbog kapitel 1", reading_note)
            self.assertIn("Target source: Grundbog kapitel 1.", reading_note)
            self.assertIn("Grounding rules", reading_note)

            slide_note = course_context.build_course_prompt_context_note(
                bundle=bundle,
                config=config,
                lecture_key="W1L1",
                prompt_type="single_slide",
                source_item=SimpleNamespace(
                    source_type="slide",
                    slide_key="seminar-1",
                    base_name="Slide seminar: Diskussionsspoergsmaal",
                    path=Path("/tmp/seminar.pdf"),
                ),
            )

            self.assertIn("seminar slide deck 'Diskussionsspoergsmaal'", slide_note)
            self.assertIn("This is a seminar slide deck", slide_note)


if __name__ == "__main__":
    unittest.main()
