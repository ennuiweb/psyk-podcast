import importlib.util
import json
import os
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
    def _default_prompt_context(self, mod):
        return {
            "prompt_strategy": mod.normalize_audio_prompt_strategy({}),
            "exam_focus": mod.normalize_exam_focus({}),
            "meta_prompting": mod.normalize_meta_prompting({}),
        }

    def test_default_output_root_prefers_environment_override(self):
        mod = _load_module()
        with mock.patch.dict(
            os.environ,
            {mod.OUTPUT_ROOT_ENV_VAR: "/tmp/personlighedspsykologi-output"},
            clear=False,
        ):
            self.assertEqual(mod.default_output_root(), "/tmp/personlighedspsykologi-output")

    def test_resolve_output_root_uses_existing_directory(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_root = Path(tmpdir)
            self.assertEqual(mod.resolve_output_root(output_root), output_root.resolve())

    def test_resolve_output_root_resolves_macos_alias_files(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            alias_file = Path(tmpdir) / "output"
            alias_file.write_text("alias placeholder", encoding="utf-8")
            resolved_dir = Path(tmpdir) / "resolved-output"
            resolved_dir.mkdir()
            with mock.patch.object(mod.sys, "platform", "darwin"):
                with mock.patch.object(mod, "resolve_macos_alias", return_value=resolved_dir):
                    self.assertEqual(mod.resolve_output_root(alias_file), resolved_dir.resolve())

    def test_should_generate_brief_for_source_respects_apply_to_modes(self):
        mod = _load_module()
        lecture_slide_item = mod.SourceItem(
            path=Path("/tmp/lecture.pdf"),
            base_name="Slide lecture: Example",
            source_type="slide",
            slide_subcategory="lecture",
        )
        exercise_slide_item = mod.SourceItem(
            path=Path("/tmp/exercise.pdf"),
            base_name="Slide exercise: Example",
            source_type="slide",
            slide_subcategory="exercise",
        )
        grundbog_item = mod.SourceItem(
            path=Path("/tmp/Grundbog kapitel 1.pdf"),
            base_name="Grundbog kapitel 1",
            source_type="reading",
        )
        article_item = mod.SourceItem(
            path=Path("/tmp/Lewis (1999).pdf"),
            base_name="Lewis (1999)",
            source_type="reading",
        )

        self.assertTrue(
            mod.should_generate_brief_for_source(
                lecture_slide_item,
                brief_cfg={"apply_to": "all"},
            )
        )
        self.assertTrue(
            mod.should_generate_brief_for_source(
                exercise_slide_item,
                brief_cfg={"apply_to": "all"},
            )
        )
        self.assertTrue(
            mod.should_generate_brief_for_source(grundbog_item, brief_cfg={"apply_to": "all"})
        )
        self.assertFalse(
            mod.should_generate_brief_for_source(
                lecture_slide_item,
                brief_cfg={"apply_to": "none"},
            )
        )
        self.assertTrue(
            mod.should_generate_brief_for_source(
                grundbog_item,
                brief_cfg={"apply_to": "grundbog_only"},
            )
        )
        self.assertFalse(
            mod.should_generate_brief_for_source(
                article_item,
                brief_cfg={"apply_to": "grundbog_only"},
            )
        )
        self.assertFalse(
            mod.should_generate_brief_for_source(
                lecture_slide_item,
                brief_cfg={"apply_to": "grundbog_only"},
            )
        )
        self.assertTrue(
            mod.should_generate_brief_for_source(
                article_item,
                brief_cfg={"apply_to": "reading_only"},
            )
        )
        self.assertFalse(
            mod.should_generate_brief_for_source(
                lecture_slide_item,
                brief_cfg={"apply_to": "reading_only"},
            )
        )
        self.assertTrue(
            mod.should_generate_brief_for_source(
                lecture_slide_item,
                brief_cfg={"apply_to": "slides_only"},
            )
        )
        self.assertTrue(
            mod.should_generate_brief_for_source(
                exercise_slide_item,
                brief_cfg={"apply_to": "slides_only"},
            )
        )
        self.assertFalse(
            mod.should_generate_brief_for_source(
                article_item,
                brief_cfg={"apply_to": "slides_only"},
            )
        )
        self.assertTrue(
            mod.should_generate_brief_for_source(
                lecture_slide_item,
                brief_cfg={"apply_to": "lecture_slides_only"},
            )
        )
        self.assertFalse(
            mod.should_generate_brief_for_source(
                exercise_slide_item,
                brief_cfg={"apply_to": "lecture_slides_only"},
            )
        )
        self.assertTrue(
            mod.should_generate_brief_for_source(
                lecture_slide_item,
                brief_cfg={"apply_to": "readings_and_lecture_slides"},
            )
        )
        self.assertFalse(
            mod.should_generate_brief_for_source(
                exercise_slide_item,
                brief_cfg={"apply_to": "readings_and_lecture_slides"},
            )
        )
        self.assertTrue(
            mod.should_generate_brief_for_source(
                article_item,
                brief_cfg={"apply_to": "readings_and_lecture_slides"},
            )
        )

    def test_resolve_brief_apply_to_rejects_unknown_values(self):
        mod = _load_module()

        with self.assertRaises(SystemExit):
            mod.resolve_brief_apply_to({"apply_to": "lectureish"})

    def test_per_source_audio_settings_use_per_slide_defaults_for_slides(self):
        mod = _load_module()
        slide_item = mod.SourceItem(
            path=Path("/tmp/lecture.pdf"),
            base_name="Slide lecture: Example",
            source_type="slide",
            slide_subcategory="lecture",
        )
        reading_item = mod.SourceItem(
            path=Path("/tmp/reading.pdf"),
            base_name="Grundbog kapitel 1",
            source_type="reading",
        )

        slide_settings = mod.per_source_audio_settings(
            slide_item,
            per_reading_cfg={"format": "deep-dive", "length": "long", "prompt": ""},
            per_slide_cfg={"format": "deep-dive", "length": "default", "prompt": ""},
            **self._default_prompt_context(mod),
        )
        self.assertEqual(slide_settings[0], "per_slide")
        self.assertIn("The source is a slide deck.", slide_settings[1])
        self.assertEqual(slide_settings[2:], ("deep-dive", "default"))

        reading_settings = mod.per_source_audio_settings(
            reading_item,
            per_reading_cfg={"format": "deep-dive", "length": "long", "prompt": ""},
            per_slide_cfg={"format": "deep-dive", "length": "default", "prompt": ""},
            **self._default_prompt_context(mod),
        )
        self.assertEqual(reading_settings[0], "per_reading")
        self.assertIn("central claims and argument structure", reading_settings[1])
        self.assertEqual(reading_settings[2:], ("deep-dive", "long"))

    def test_build_audio_prompt_for_reading_uses_distinction_focused_defaults(self):
        mod = _load_module()
        reading_item = mod.SourceItem(
            path=Path("/tmp/Foucault.pdf"),
            base_name="Foucault",
            source_type="reading",
        )

        prompt = mod.build_audio_prompt(
            prompt_type="single_reading",
            custom_prompt="",
            source_item=reading_item,
            **self._default_prompt_context(mod),
        )

        self.assertIn("central claims and argument structure", prompt)
        self.assertIn("conceptual distinctions and delimitations", prompt)
        self.assertIn("Exam lens:", prompt)
        self.assertIn("historical tradition and core assumptions", prompt)
        self.assertIn("Tone: calm, precise, teaching-oriented.", prompt)

    def test_build_audio_prompt_for_mixed_sources_assigns_source_roles(self):
        mod = _load_module()
        reading_item = mod.SourceItem(
            path=Path("/tmp/text.pdf"),
            base_name="Text",
            source_type="reading",
        )
        slide_item = mod.SourceItem(
            path=Path("/tmp/slides.pdf"),
            base_name="Slide lecture: Intro",
            source_type="slide",
            slide_subcategory="lecture",
        )

        prompt = mod.build_audio_prompt(
            prompt_type="mixed_sources",
            custom_prompt="",
            source_items=[reading_item, slide_item],
            week_dir=Path("/tmp/W01L1"),
            week_label="W01L1",
            **self._default_prompt_context(mod),
        )

        self.assertIn("You are working with both slides and readings.", prompt)
        self.assertIn("Source roles:", prompt)
        self.assertIn("Use the slides as the structural map", prompt)
        self.assertIn("Use the readings for conceptual distinctions", prompt)

    def test_build_audio_prompt_includes_source_sidecar_notes(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            source_path = tmp_path / "Foucault.pdf"
            source_path.write_bytes(b"data")
            (tmp_path / "Foucault.prompt.md").write_text(
                "Focus on liberation versus practices of freedom.",
                encoding="utf-8",
            )
            reading_item = mod.SourceItem(
                path=source_path,
                base_name="Foucault",
                source_type="reading",
            )

            prompt = mod.build_audio_prompt(
                prompt_type="single_reading",
                custom_prompt="",
                source_item=reading_item,
                **self._default_prompt_context(mod),
            )

            self.assertIn("External pre-analysis to integrate if useful:", prompt)
            self.assertIn("liberation versus practices of freedom", prompt)

    def test_build_audio_prompt_uses_in_memory_meta_note_overrides(self):
        mod = _load_module()
        reading_item = mod.SourceItem(
            path=Path("/tmp/Foucault.pdf"),
            base_name="Foucault",
            source_type="reading",
        )

        prompt = mod.build_audio_prompt(
            prompt_type="single_reading",
            custom_prompt="",
            source_item=reading_item,
            meta_note_overrides={Path("/tmp/Foucault.analysis.md"): "Focus on power relations vs domination."},
            **self._default_prompt_context(mod),
        )

        self.assertIn("External pre-analysis to integrate if useful:", prompt)
        self.assertIn("power relations vs domination", prompt)

    def test_build_audio_prompt_for_short_uses_short_prompt_type(self):
        mod = _load_module()
        reading_item = mod.SourceItem(
            path=Path("/tmp/short.pdf"),
            base_name="Short text",
            source_type="reading",
        )

        prompt = mod.build_audio_prompt(
            prompt_type="short",
            custom_prompt="",
            source_item=reading_item,
            **self._default_prompt_context(mod),
        )

        self.assertIn("Keep the explanation compact, memorable, and exam-oriented", prompt)
        self.assertIn("what matters most for exam preparation", prompt)

    def test_build_audio_prompt_includes_weekly_sidecar_notes(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            week_dir = Path(tmpdir) / "W01L1"
            week_dir.mkdir(parents=True, exist_ok=True)
            (week_dir / "week.analysis.md").write_text(
                "Prioritize distinctions between normalization and subject formation.",
                encoding="utf-8",
            )

            reading_item = mod.SourceItem(
                path=week_dir / "text.pdf",
                base_name="Text",
                source_type="reading",
            )

            prompt = mod.build_audio_prompt(
                prompt_type="weekly_readings_only",
                custom_prompt="",
                source_items=[reading_item],
                week_dir=week_dir,
                week_label="W01L1",
                **self._default_prompt_context(mod),
            )

            self.assertIn("weekly_readings_only", mod.normalize_exam_focus({})["prompt_types"])
            self.assertIn("normalization and subject formation", prompt)

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

    def test_build_source_items_excludes_meta_prompt_sidecars(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            week_dir = root / "W1L1"
            week_dir.mkdir(parents=True, exist_ok=True)
            _touch(week_dir / "Foucault.pdf")
            (week_dir / "week.analysis.md").write_text("meta", encoding="utf-8")

            reading_sources, generation_sources = mod.build_source_items(
                week_dir=week_dir,
                week_label="W01L1",
                slides_catalog_path=None,
                slides_source_root=None,
                meta_prompting=mod.normalize_meta_prompting({}),
            )

            self.assertEqual([item.base_name for item in reading_sources], ["Foucault"])
            self.assertEqual([item.base_name for item in generation_sources], ["Foucault"])

    def test_review_manifest_filter_selects_only_sample_outputs(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            reading_path = tmp_path / "W11L1 Hacking.pdf"
            _touch(reading_path)
            manifest_path = tmp_path / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "entries": [
                            {
                                "prompt_type": "weekly_readings_only",
                                "lecture_key": "W11L1",
                                "baseline": {
                                    "source_name": (
                                        "W11L1 - Alle kilder (undtagen slides) [EN] "
                                        "{type=audio hash=aaaa}.mp3"
                                    )
                                },
                                "source_context": {"source_files": [str(reading_path)]},
                            },
                            {
                                "prompt_type": "single_reading",
                                "lecture_key": "W11L1",
                                "baseline": {
                                    "source_name": "W11L1 - Hacking [EN] {type=audio hash=bbbb}.mp3"
                                },
                                "source_context": {"source_files": [str(reading_path)]},
                            },
                            {
                                "prompt_type": "short",
                                "lecture_key": "W11L1",
                                "baseline": {
                                    "source_name": "[Short] W11L1 - Hacking [EN] {type=audio hash=cccc}.mp3"
                                },
                                "source_context": {"source_files": [str(reading_path)]},
                            },
                            {
                                "prompt_type": "single_slide",
                                "lecture_key": "W09L1",
                                "baseline": {
                                    "source_name": (
                                        "W09L1 - Slide lecture: 17. Kritisk psykologi [EN] "
                                        "{type=audio hash=dddd}.mp3"
                                    )
                                },
                                "source_context": {
                                    "catalog_match": {
                                        "slide_key": "w09l1-lecture-17-kritisk-psykologi-30798115"
                                    }
                                },
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            review_filter = mod.load_review_manifest_filter(manifest_path)
            reading_item = mod.SourceItem(
                path=reading_path,
                base_name="Hacking",
                source_type="reading",
            )
            other_item = mod.SourceItem(
                path=tmp_path / "Other.pdf",
                base_name="Other",
                source_type="reading",
            )
            slide_item = mod.SourceItem(
                path=tmp_path / "slide.pdf",
                base_name="Slide lecture: 17. Kritisk psykologi",
                source_type="slide",
                slide_key="w09l1-lecture-17-kritisk-psykologi-30798115",
            )

            self.assertTrue(mod.review_filter_includes_weekly(review_filter, "W11L1"))
            self.assertFalse(mod.review_filter_includes_weekly(review_filter, "W10L2"))
            self.assertTrue(mod.review_filter_includes_source(review_filter, reading_item))
            self.assertFalse(mod.review_filter_includes_source(review_filter, other_item))
            self.assertTrue(mod.review_filter_includes_source(review_filter, slide_item))
            self.assertTrue(mod.review_filter_includes_short_source(review_filter, reading_item))
            self.assertTrue(
                mod.review_filter_includes_output(
                    review_filter,
                    "single_reading",
                    Path("W11L1 - Hacking [EN] {type=audio hash=newhash}.mp3"),
                )
            )
            self.assertFalse(
                mod.review_filter_includes_output(
                    review_filter,
                    "single_reading",
                    Path("W11L1 - Other [EN] {type=audio hash=newhash}.mp3"),
                )
            )

    def test_normalize_meta_prompting_keeps_automatic_output_names_addressable(self):
        mod = _load_module()

        normalized = mod.normalize_meta_prompting(
            {
                "per_source_suffixes": [".prompt.md"],
                "weekly_sidecars": ["week.prompt.md"],
                "automatic": {
                    "default_per_source_output_suffix": ".analysis.md",
                    "default_weekly_output_name": "week.analysis.md",
                },
            }
        )

        self.assertIn(".analysis.md", normalized["per_source_suffixes"])
        self.assertIn("week.analysis.md", normalized["weekly_sidecars"])

    def test_extract_pdf_text_for_meta_prompt_fails_when_pdf_has_no_text(self):
        mod = _load_module()
        fake_reader = mock.Mock()
        fake_reader.pages = [mock.Mock(extract_text=mock.Mock(return_value=""))]

        with mock.patch.dict("sys.modules", {"pypdf": mock.Mock(PdfReader=mock.Mock(return_value=fake_reader))}):
            with self.assertRaises(mod.MetaPromptInputError):
                mod._extract_pdf_text_for_meta_prompt(Path("/tmp/scan.pdf"), 1000)

    def test_normalize_meta_prompting_rejects_unknown_provider(self):
        mod = _load_module()

        with self.assertRaises(SystemExit):
            mod.normalize_meta_prompting({"automatic": {"provider": "openrouter"}})

    def test_build_auto_meta_prompt_jobs_skips_existing_sidecars(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            week_dir = Path(tmpdir) / "W01L1"
            week_dir.mkdir(parents=True, exist_ok=True)
            reading_path = week_dir / "Foucault.pdf"
            slide_path = week_dir / "slides.pdf"
            _touch(reading_path)
            _touch(slide_path)
            (week_dir / "Foucault.analysis.md").write_text("manual note", encoding="utf-8")

            reading_item = mod.SourceItem(
                path=reading_path,
                base_name="Foucault",
                source_type="reading",
            )
            slide_item = mod.SourceItem(
                path=slide_path,
                base_name="Slide lecture: Intro",
                source_type="slide",
                slide_subcategory="lecture",
            )

            jobs = mod.build_auto_meta_prompt_jobs(
                week_dir=week_dir,
                week_label="W01L1",
                reading_sources=[reading_item],
                generation_sources=[reading_item, slide_item],
                generate_weekly_overview=True,
                meta_prompting=mod.normalize_meta_prompting(
                    {"automatic": {"enabled": True, "default_per_source_output_suffix": ".analysis.md"}}
                ),
            )

            self.assertEqual([job.prompt_type for job in jobs], ["weekly_readings_only", "single_slide"])
            self.assertEqual(jobs[0].output_path, week_dir / "week.analysis.md")
            self.assertEqual(jobs[1].output_path, week_dir / "slides.analysis.md")

    def test_prepare_auto_meta_prompt_overrides_dry_run_keeps_notes_in_memory(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            week_dir = Path(tmpdir) / "W01L1"
            week_dir.mkdir(parents=True, exist_ok=True)
            reading_path = week_dir / "Foucault.pdf"
            _touch(reading_path)
            reading_item = mod.SourceItem(
                path=reading_path,
                base_name="Foucault",
                source_type="reading",
            )

            with mock.patch.object(
                mod,
                "_meta_prompt_backend_for_automatic",
                return_value=mod.MetaPromptBackend(provider="gemini", client=object(), support=object()),
            ), mock.patch.object(
                mod,
                "generate_meta_prompt_markdown",
                return_value="## Core distinctions\n- Focus on subject formation.",
            ):
                overrides, lines = mod.prepare_auto_meta_prompt_overrides(
                    course_title="Personlighedspsykologi",
                    week_dir=week_dir,
                    week_label="W01L1",
                    reading_sources=[reading_item],
                    generation_sources=[reading_item],
                    generate_weekly_overview=True,
                    meta_prompting=mod.normalize_meta_prompting({"automatic": {"enabled": True}}),
                    dry_run=True,
                )

            self.assertIn(week_dir / "Foucault.analysis.md", overrides)
            self.assertIn(week_dir / "week.analysis.md", overrides)
            self.assertFalse((week_dir / "Foucault.analysis.md").exists())
            self.assertTrue(any(line.startswith("META WOULD GENERATE:") for line in lines))

    def test_prepare_auto_meta_prompt_overrides_fails_hard_on_unreadable_pdf(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            week_dir = Path(tmpdir) / "W01L1"
            week_dir.mkdir(parents=True, exist_ok=True)
            reading_path = week_dir / "Foucault.pdf"
            _touch(reading_path)
            reading_item = mod.SourceItem(
                path=reading_path,
                base_name="Foucault",
                source_type="reading",
            )

            with mock.patch.object(
                mod,
                "_meta_prompt_backend_for_automatic",
                return_value=mod.MetaPromptBackend(provider="gemini", client=object(), support=object()),
            ), mock.patch.object(
                mod,
                "generate_meta_prompt_markdown",
                side_effect=mod.MetaPromptInputError("no extractable text found in PDF Foucault.pdf"),
            ):
                with self.assertRaises(SystemExit):
                    mod.prepare_auto_meta_prompt_overrides(
                        course_title="Personlighedspsykologi",
                        week_dir=week_dir,
                        week_label="W01L1",
                        reading_sources=[reading_item],
                        generation_sources=[reading_item],
                        generate_weekly_overview=False,
                        meta_prompting=mod.normalize_meta_prompting(
                            {"automatic": {"enabled": True, "fail_open": True}}
                        ),
                        dry_run=False,
                    )

    def test_generate_meta_prompt_markdown_wraps_non_rate_limit_errors(self):
        mod = _load_module()
        job = mod.MetaPromptJob(
            prompt_type="single_reading",
            output_path=Path("/tmp/Foucault.analysis.md"),
            label="Foucault",
            source_items=(
                mod.SourceItem(
                    path=Path("/tmp/Foucault.pdf"),
                    base_name="Foucault",
                    source_type="reading",
                ),
            ),
        )

        fake_client = mock.Mock()
        fake_backend = mod.MetaPromptBackend(provider="anthropic", client=fake_client, support=object())
        fake_client.messages.create.side_effect = ValueError("boom")
        with mock.patch.object(
            mod,
            "_build_meta_prompt_request",
            return_value=("system", "user"),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                mod.generate_meta_prompt_markdown(
                    job=job,
                    course_title="Personlighedspsykologi",
                    meta_prompting=mod.normalize_meta_prompting({"automatic": {"enabled": True}}),
                    backend=fake_backend,
                )

        self.assertIn("meta prompt generation failed for Foucault", str(ctx.exception))

    def test_generate_meta_prompt_markdown_supports_gemini_backend(self):
        mod = _load_module()
        job = mod.MetaPromptJob(
            prompt_type="single_reading",
            output_path=Path("/tmp/Foucault.analysis.md"),
            label="Foucault",
            source_items=(
                mod.SourceItem(
                    path=Path("/tmp/Foucault.pdf"),
                    base_name="Foucault",
                    source_type="reading",
                ),
            ),
        )

        fake_response = mock.Mock(text="## Core distinctions\n- Focus on power relations.")
        fake_client = mock.Mock()
        fake_client.models.generate_content.return_value = fake_response
        fake_support = mock.Mock()
        fake_support.GenerateContentConfig.return_value = {"system_instruction": "system"}

        with mock.patch.object(
            mod,
            "_build_meta_prompt_request",
            return_value=("system", "user"),
        ):
            content = mod.generate_meta_prompt_markdown(
                job=job,
                course_title="Personlighedspsykologi",
                meta_prompting=mod.normalize_meta_prompting({"automatic": {"enabled": True}}),
                backend=mod.MetaPromptBackend(
                    provider="gemini",
                    client=fake_client,
                    support=fake_support,
                ),
            )

        self.assertIn("power relations", content)
        fake_client.models.generate_content.assert_called_once()

    def test_prepare_auto_meta_prompt_overrides_fail_open_on_generic_generation_error(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            week_dir = Path(tmpdir) / "W01L1"
            week_dir.mkdir(parents=True, exist_ok=True)
            reading_path = week_dir / "Foucault.pdf"
            _touch(reading_path)
            reading_item = mod.SourceItem(
                path=reading_path,
                base_name="Foucault",
                source_type="reading",
            )

            with mock.patch.object(
                mod,
                "_meta_prompt_backend_for_automatic",
                return_value=mod.MetaPromptBackend(provider="gemini", client=object(), support=object()),
            ), mock.patch.object(
                mod,
                "generate_meta_prompt_markdown",
                side_effect=RuntimeError("network exploded"),
            ):
                overrides, lines = mod.prepare_auto_meta_prompt_overrides(
                    course_title="Personlighedspsykologi",
                    week_dir=week_dir,
                    week_label="W01L1",
                    reading_sources=[reading_item],
                    generation_sources=[reading_item],
                    generate_weekly_overview=False,
                    meta_prompting=mod.normalize_meta_prompting({"automatic": {"enabled": True, "fail_open": True}}),
                    dry_run=False,
                )

            self.assertEqual(overrides, {})
            self.assertEqual(lines, [])

    def test_prepare_auto_meta_prompt_overrides_drops_override_when_write_fails(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            week_dir = Path(tmpdir) / "W01L1"
            week_dir.mkdir(parents=True, exist_ok=True)
            reading_path = week_dir / "Foucault.pdf"
            _touch(reading_path)
            reading_item = mod.SourceItem(
                path=reading_path,
                base_name="Foucault",
                source_type="reading",
            )

            with mock.patch.object(
                mod,
                "_meta_prompt_backend_for_automatic",
                return_value=mod.MetaPromptBackend(provider="gemini", client=object(), support=object()),
            ), mock.patch.object(
                mod,
                "generate_meta_prompt_markdown",
                return_value="## Core distinctions\n- Focus on subject formation.",
            ), mock.patch.object(
                Path,
                "write_text",
                side_effect=OSError("disk full"),
            ):
                overrides, lines = mod.prepare_auto_meta_prompt_overrides(
                    course_title="Personlighedspsykologi",
                    week_dir=week_dir,
                    week_label="W01L1",
                    reading_sources=[reading_item],
                    generation_sources=[reading_item],
                    generate_weekly_overview=False,
                    meta_prompting=mod.normalize_meta_prompting({"automatic": {"enabled": True, "fail_open": True}}),
                    dry_run=False,
                )

            self.assertEqual(overrides, {})
            self.assertEqual(lines, [])
            self.assertFalse((week_dir / "Foucault.analysis.md").exists())

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

    def test_cleanup_disallowed_slide_brief_outputs_respects_short_scope(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            week_dir = Path(tmpdir) / "W1L1"
            lecture_brief = (
                week_dir
                / "[Short] W1L1 - Slide lecture: 1. gang [EN] {type=audio lang=en format=deep-dive length=long hash=fa9adbcf}.mp3"
            )
            exercise_brief = (
                week_dir
                / "[Short] W1L1 - Slide exercise: 1. Intro [EN] {type=audio lang=en format=deep-dive length=long hash=fa9adbcf}.mp3"
            )
            seminar_brief = (
                week_dir
                / "[Brief] W1L1 - Slide seminar: 1. Seminar [EN] {type=audio lang=en format=deep-dive length=long hash=fa9adbcf}.mp3"
            )
            exercise_request = exercise_brief.with_suffix(".mp3.request.json")
            _touch(lecture_brief)
            _touch(exercise_brief)
            _touch(seminar_brief)
            _touch(exercise_request, b"{}")

            removed = mod.cleanup_disallowed_slide_brief_outputs(
                week_dir,
                brief_cfg={"apply_to": "readings_and_lecture_slides"},
            )

            self.assertEqual(
                {path.name for path in removed},
                {exercise_brief.name, seminar_brief.name, exercise_request.name},
            )
            self.assertTrue(lecture_brief.exists())
            self.assertFalse(exercise_brief.exists())
            self.assertFalse(seminar_brief.exists())
            self.assertFalse(exercise_request.exists())

    def test_brief_content_types_excludes_quiz_and_preserves_supported_order(self):
        mod = _load_module()

        self.assertEqual(
            mod.brief_content_types(["quiz", "audio", "infographic"]),
            ["audio", "infographic"],
        )

    def test_cleanup_disallowed_brief_quiz_outputs_removes_short_quiz_artifacts(self):
        mod = _load_module()
        with tempfile.TemporaryDirectory() as tmpdir:
            week_dir = Path(tmpdir) / "W1L1"
            brief_quiz = (
                week_dir
                / "[Short] W1L1 - Foo [EN] {type=quiz lang=en quantity=standard difficulty=easy hash=beef1234}.json"
            )
            brief_request = brief_quiz.with_suffix(".json.request.json")
            brief_audio = (
                week_dir
                / "[Short] W1L1 - Foo [EN] {type=audio lang=en format=deep-dive length=long hash=fa9adbcf}.mp3"
            )
            _touch(brief_quiz, b"{}")
            _touch(brief_request, b"{}")
            _touch(brief_audio)

            removed = mod.cleanup_disallowed_brief_quiz_outputs(week_dir)

            self.assertEqual({path.name for path in removed}, {brief_quiz.name, brief_request.name})
            self.assertFalse(brief_quiz.exists())
            self.assertFalse(brief_request.exists())
            self.assertTrue(brief_audio.exists())

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
