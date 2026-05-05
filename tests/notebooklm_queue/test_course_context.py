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
            (show_dir / "course_glossary.json").write_text(
                json.dumps(
                    {
                        "terms": [
                            {
                                "term_id": "personality",
                                "label": "personality",
                                "category": "construct",
                                "salience_score": 80,
                                "lecture_keys": ["W01L1"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (show_dir / "course_theory_map.json").write_text(
                json.dumps(
                    {
                        "theories": [
                            {
                                "theory_id": "trait_theory",
                                "label": "trait theory",
                                "salience_score": 70,
                                "lecture_keys": ["W01L1"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (show_dir / "source_weighting.json").write_text(
                json.dumps(
                    {
                        "lectures": [
                            {
                                "lecture_key": "W01L1",
                                "ranked_sources": [
                                    {
                                        "title": "Grundbog kapitel 1",
                                        "weight_band": "anchor",
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (show_dir / "course_concept_graph.json").write_text(
                json.dumps(
                    {
                        "distinctions": [
                            {
                                "distinction_id": "trait-vs-state",
                                "label": "trait vs state",
                                "importance": 3,
                                "lecture_keys": ["W01L1"],
                            }
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
            self.assertIn("Broader course arc in play: Introduktion; Fortsat.", reading_note)
            self.assertIn("Course overview excerpt:", reading_note)
            self.assertIn("## Source character", reading_note)
            self.assertIn("This is a textbook chapter", reading_note)
            self.assertIn("Forelaesning slides frame the lecture through: Hvad er personlighed?", reading_note)
            self.assertIn("Seminar slides operationalize or test the material through: Diskussionsspoergsmaal.", reading_note)
            self.assertIn("Grundbog kapitel 1", reading_note)
            self.assertIn("## Semantic guidance", reading_note)
            self.assertIn("Ranked source emphasis: Grundbog kapitel 1 [anchor].", reading_note)
            self.assertIn("Course concepts in play: personality (construct).", reading_note)
            self.assertIn("Theory frame: trait theory.", reading_note)
            self.assertIn("Cross-lecture tensions to keep explicit: trait vs state.", reading_note)
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

    def test_short_prompt_context_trims_semantic_guidance(self):
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
                                    "summary_lines": ["Intro lecture summary."],
                                },
                                "readings": [
                                    {
                                        "reading_title": "Grundbog kapitel 1",
                                        "source_filename": "W1L1 Grundbog kapitel 1.pdf",
                                        "summary": {
                                            "summary_lines": ["Field-framing overview."],
                                        },
                                    },
                                    {
                                        "reading_title": "Other reading",
                                        "source_filename": "W1L1 Other reading.pdf",
                                        "summary": {
                                            "summary_lines": ["Secondary reading summary."],
                                        },
                                    }
                                ],
                                "slides": [],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (show_dir / "course_glossary.json").write_text(
                json.dumps(
                    {
                        "terms": [
                            {
                                "term_id": "personality",
                                "label": "personality",
                                "category": "construct",
                                "salience_score": 80,
                                "lecture_keys": ["W01L1"],
                                "source_ids": ["w01l1-grundbog-kapitel-1"],
                                "source_evidence_origins": ["textbook_framing"],
                            },
                            {
                                "term_id": "assessment",
                                "label": "assessment",
                                "category": "practice",
                                "salience_score": 75,
                                "lecture_keys": ["W01L1"],
                                "source_ids": ["w01l1-other"],
                                "source_evidence_origins": ["reading_grounded"],
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (show_dir / "course_theory_map.json").write_text(
                json.dumps(
                    {
                        "theories": [
                            {
                                "theory_id": "trait_theory",
                                "label": "trait theory",
                                "salience_score": 70,
                                "lecture_keys": ["W01L1"],
                                "representative_source_ids": ["w01l1-grundbog-kapitel-1"],
                                "representative_evidence_origins": ["textbook_framing"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (show_dir / "source_weighting.json").write_text(
                json.dumps(
                    {
                        "lectures": [
                            {
                                "lecture_key": "W01L1",
                                "ranked_sources": [
                                    {
                                        "source_id": "w01l1-grundbog-kapitel-1",
                                        "title": "Grundbog kapitel 1",
                                        "weight_band": "anchor",
                                        "weight_score": 90,
                                        "evidence_origin": "textbook_framing",
                                    },
                                    {
                                        "source_id": "w01l1-other",
                                        "title": "Other reading",
                                        "weight_band": "major",
                                        "weight_score": 89,
                                        "evidence_origin": "reading_grounded",
                                    },
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (show_dir / "course_concept_graph.json").write_text(
                json.dumps(
                    {
                        "distinctions": [
                            {
                                "distinction_id": "trait-vs-state",
                                "label": "trait vs state",
                                "importance": 3,
                                "lecture_keys": ["W01L1"],
                                "supporting_source_ids": ["w01l1-grundbog-kapitel-1"],
                                "supporting_evidence_origins": ["textbook_framing"],
                            },
                            {
                                "distinction_id": "person-vs-variable",
                                "label": "person vs variable profile",
                                "importance": 2,
                                "lecture_keys": ["W01L1"],
                                "supporting_source_ids": ["w01l1-other"],
                                "supporting_evidence_origins": ["reading_grounded"],
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (docs_dir / "overblik.md").write_text("- W1L1 Introduktion", encoding="utf-8")

            config = course_context.normalize_course_context({})
            bundle = course_context.load_course_prompt_context_bundle(
                repo_root=repo_root,
                config=config,
                slides_catalog_path=show_dir / "slides_catalog.json",
            )
            assert bundle is not None

            note = course_context.build_course_prompt_context_note(
                bundle=bundle,
                config=config,
                lecture_key="W1L1",
                prompt_type="short",
                source_item=SimpleNamespace(
                    source_type="reading",
                    base_name="Grundbog kapitel 1",
                    path=Path("/tmp/W1L1 Grundbog kapitel 1.pdf"),
                ),
            )

            self.assertIn("Ranked source emphasis: Grundbog kapitel 1 [anchor].", note)
            self.assertNotIn("Other reading [major]", note)
            self.assertIn("Grundbog kapitel 1: Field-framing overview.", note)
            self.assertNotIn("Other reading: Secondary reading summary.", note)
            self.assertIn("Course concepts in play: personality (construct).", note)
            self.assertNotIn("assessment (practice)", note)
            self.assertNotIn("Theory frame:", note)
            self.assertNotIn("## Grounding rules", note)
            self.assertIn("Cross-lecture tensions to keep explicit: trait vs state.", note)
            self.assertNotIn("person vs variable profile", note)

    def test_reading_prompt_prioritizes_matched_target_source(self):
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
                                "readings": [
                                    {
                                        "reading_title": "Freud, S. (1984/1905). Brudstykke af en hysteri-analyse",
                                        "source_filename": "W1L1 Freud source.pdf",
                                        "summary": {
                                            "summary_lines": ["Target reading summary."],
                                        },
                                    }
                                ],
                                "slides": [],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (show_dir / "source_weighting.json").write_text(
                json.dumps(
                    {
                        "lectures": [
                            {
                                "lecture_key": "W01L1",
                                "ranked_sources": [
                                    {
                                        "source_id": "w01l1-ricoeur",
                                        "title": "Ricoeur (1981)",
                                        "weight_band": "anchor",
                                        "weight_score": 95,
                                        "evidence_origin": "reading_grounded",
                                    },
                                    {
                                        "source_id": "w01l1-freud",
                                        "title": "Freud, S. (1984/1905). Brudstykke af en hysteri-analyse",
                                        "weight_band": "major",
                                        "weight_score": 80,
                                        "evidence_origin": "reading_grounded",
                                    },
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (docs_dir / "overblik.md").write_text("- W1L1 Introduktion", encoding="utf-8")

            config = course_context.normalize_course_context({})
            bundle = course_context.load_course_prompt_context_bundle(
                repo_root=repo_root,
                config=config,
                slides_catalog_path=show_dir / "slides_catalog.json",
            )
            assert bundle is not None

            note = course_context.build_course_prompt_context_note(
                bundle=bundle,
                config=config,
                lecture_key="W1L1",
                prompt_type="single_reading",
                source_item=SimpleNamespace(
                    source_type="reading",
                    base_name="Freud source",
                    path=Path("/tmp/W1L1 Freud source.pdf"),
                ),
            )

            semantic_line = next(
                line for line in note.splitlines() if line.startswith("- Ranked source emphasis:")
            )
            self.assertIn(
                "Freud, S. (1984/1905). Brudstykke af en hysteri-analyse [major]",
                semantic_line,
            )
            self.assertLess(
                semantic_line.index("Freud, S. (1984/1905). Brudstykke af en hysteri-analyse [major]"),
                semantic_line.index("Ricoeur (1981) [anchor]"),
            )

    def test_redundant_theory_frame_is_suppressed(self):
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
                                "readings": [],
                                "slides": [],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (show_dir / "course_glossary.json").write_text(
                json.dumps(
                    {
                        "terms": [
                            {
                                "term_id": "psychoanalysis",
                                "label": "psychoanalysis",
                                "category": "tradition",
                                "salience_score": 90,
                                "lecture_keys": ["W01L1"],
                                "linked_theories": ["psychoanalytic_personality_theory"],
                                "source_evidence_origins": ["reading_grounded"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (show_dir / "course_theory_map.json").write_text(
                json.dumps(
                    {
                        "theories": [
                            {
                                "theory_id": "psychoanalytic_personality_theory",
                                "label": "psychoanalytic personality theory",
                                "salience_score": 80,
                                "lecture_keys": ["W01L1"],
                                "core_term_ids": ["psychoanalysis"],
                                "representative_evidence_origins": ["reading_grounded"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (docs_dir / "overblik.md").write_text("- W1L1 Introduktion", encoding="utf-8")

            config = course_context.normalize_course_context({})
            bundle = course_context.load_course_prompt_context_bundle(
                repo_root=repo_root,
                config=config,
                slides_catalog_path=show_dir / "slides_catalog.json",
            )
            assert bundle is not None

            note = course_context.build_course_prompt_context_note(
                bundle=bundle,
                config=config,
                lecture_key="W1L1",
                prompt_type="weekly_readings_only",
                source_item=None,
            )

            self.assertIn("Course concepts in play: psychoanalysis (tradition).", note)
            self.assertNotIn("Theory frame: psychoanalytic personality theory.", note)

    def test_short_prompt_uses_local_course_arc(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            show_dir = repo_root / "shows" / "demo-show"
            docs_dir = show_dir / "docs"
            docs_dir.mkdir(parents=True, exist_ok=True)

            lectures = []
            for index, title in enumerate(
                [
                    "Intro",
                    "Assessment",
                    "Traits",
                    "Psychoanalysis I",
                    "Psychoanalysis II",
                    "Phenomenology",
                ],
                start=1,
            ):
                lectures.append(
                    {
                        "lecture_key": f"W1L{index}",
                        "lecture_title": title,
                        "sequence_index": index,
                        "readings": [
                            {
                                "reading_title": "Target reading" if index == 4 else f"Reading {index}",
                                "source_filename": "target.pdf" if index == 4 else f"reading-{index}.pdf",
                                "summary": {"summary_lines": [f"Summary {index}."]},
                            }
                        ],
                        "slides": [],
                    }
                )

            (show_dir / "slides_catalog.json").write_text(json.dumps({"slides": []}), encoding="utf-8")
            (show_dir / "content_manifest.json").write_text(
                json.dumps({"lectures": lectures}),
                encoding="utf-8",
            )
            (docs_dir / "overblik.md").write_text(
                "\n".join(
                    [
                        "| W01 | x | Intro |",
                        "| W02 | x | Assessment |",
                        "| W03 | x | Traits |",
                        "| W04 | x | Psychoanalysis I |",
                        "| W05 | x | Psychoanalysis II |",
                        "| W06 | x | Phenomenology |",
                    ]
                ),
                encoding="utf-8",
            )

            config = course_context.normalize_course_context({})
            bundle = course_context.load_course_prompt_context_bundle(
                repo_root=repo_root,
                config=config,
                slides_catalog_path=show_dir / "slides_catalog.json",
            )
            assert bundle is not None

            note = course_context.build_course_prompt_context_note(
                bundle=bundle,
                config=config,
                lecture_key="W1L4",
                prompt_type="short",
                source_item=SimpleNamespace(
                    source_type="reading",
                    base_name="Target reading",
                    path=Path("/tmp/target.pdf"),
                ),
            )

            self.assertIn(
                "Broader course arc in play: Assessment; Traits; Psychoanalysis I; Psychoanalysis II; Phenomenology.",
                note,
            )
            self.assertNotIn("Broader course arc in play: Intro;", note)

    def test_podcast_substrate_is_optional_and_compact_when_enabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            show_dir = repo_root / "shows" / "demo-show"
            docs_dir = show_dir / "docs"
            substrate_dir = show_dir / "source_intelligence" / "podcast_substrates"
            docs_dir.mkdir(parents=True, exist_ok=True)
            substrate_dir.mkdir(parents=True, exist_ok=True)

            (show_dir / "slides_catalog.json").write_text(json.dumps({"slides": []}), encoding="utf-8")
            (show_dir / "content_manifest.json").write_text(
                json.dumps(
                    {
                        "lectures": [
                            {
                                "lecture_key": "W1L1",
                                "lecture_title": "Phenomenology",
                                "sequence_index": 1,
                                "readings": [
                                    {
                                        "reading_title": "Phenomenology source",
                                        "source_filename": "source.pdf",
                                    }
                                ],
                                "slides": [],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            (docs_dir / "overblik.md").write_text("- W1L1 Phenomenology", encoding="utf-8")
            (substrate_dir / "W01L1.json").write_text(
                json.dumps(
                    {
                        "podcast": {
                            "weekly": {
                                "angle": "Explain phenomenology as a disciplined shift in viewpoint.",
                                "must_cover": ["lived experience"],
                                "avoid": ["vague introspection caricature"],
                                "grounding": ["anchor claims in the reading"],
                            },
                            "per_reading": [
                                {
                                    "source_filename": "source.pdf",
                                    "angle": "Use this reading as the anchor.",
                                    "must_cover": ["description vs explanation"],
                                    "avoid": [],
                                }
                            ],
                            "per_slide": [],
                            "short": {"angle": "compact angle", "must_cover": [], "avoid": []},
                            "selected_concepts": [{"concept": "lived experience", "role": "anchor"}],
                            "selected_tensions": [{"tension": "description vs explanation", "stakes": "method"}],
                            "grounding_notes": ["substrate is prioritization only"],
                            "source_selection": [{"source_id": "source-1", "priority": "anchor", "why": "main text"}],
                        }
                    }
                ),
                encoding="utf-8",
            )

            disabled_config = course_context.normalize_course_context({})
            bundle = course_context.load_course_prompt_context_bundle(
                repo_root=repo_root,
                config=disabled_config,
                slides_catalog_path=show_dir / "slides_catalog.json",
            )
            assert bundle is not None
            disabled_note = course_context.build_course_prompt_context_note(
                bundle=bundle,
                config=disabled_config,
                lecture_key="W1L1",
                prompt_type="weekly_readings_only",
            )
            self.assertNotIn("Podcast substrate", disabled_note)

            enabled_config = course_context.normalize_course_context(
                {"podcast_substrate": {"enabled": True, "max_items": 2}}
            )
            reading_note = course_context.build_course_prompt_context_note(
                bundle=bundle,
                config=enabled_config,
                lecture_key="W1L1",
                prompt_type="single_reading",
                source_item=SimpleNamespace(
                    source_type="reading",
                    base_name="Phenomenology source",
                    path=Path("/tmp/source.pdf"),
                ),
            )

            self.assertIn("## Podcast substrate", reading_note)
            self.assertIn("Use this reading as the anchor", reading_note)
            self.assertIn("description vs explanation", reading_note)
            self.assertIn("lived experience", reading_note)


if __name__ == "__main__":
    unittest.main()
