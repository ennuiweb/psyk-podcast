import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MODULE_PATH = (
    REPO_ROOT
    / "notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/scripts/generate_candidates.py"
)
SPEC = importlib.util.spec_from_file_location("printout_review_generate_candidates", MODULE_PATH)
assert SPEC and SPEC.loader
generate_candidates = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generate_candidates)


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _manifest_fixture(tmp_path: Path) -> tuple[Path, Path]:
    run_dir = tmp_path / "run"
    prompt_path = run_dir / "variant.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text("variant prompt", encoding="utf-8")
    manifest_path = run_dir / "manifest.json"
    _write_json(
        manifest_path,
        {
            "variant_prompt_path": str(prompt_path),
            "candidate_output_root": str(run_dir / "candidate_output"),
            "entries": [
                {"source_id": "source-a"},
                {"source_id": "source-b"},
            ],
        },
    )
    return run_dir, manifest_path


def test_generate_candidates_continues_batch_and_updates_manifest_progress(tmp_path, monkeypatch):
    _, manifest_path = _manifest_fixture(tmp_path)

    monkeypatch.setattr(generate_candidates, "has_gemini_api_key", lambda: True)
    monkeypatch.setattr(generate_candidates, "preflight_gemini_json_generation", lambda **kwargs: None)
    monkeypatch.setattr(
        generate_candidates.printout_engine,
        "select_sources",
        lambda **kwargs: [
            {"source_id": "source-a", "lecture_key": "W01L1"},
            {"source_id": "source-b", "lecture_key": "W01L1"},
        ],
    )

    def fake_build_printout_for_source(**kwargs):
        source_id = kwargs["source"]["source_id"]
        if source_id == "source-a":
            raise generate_candidates.printout_engine.PrintoutError("boom")
        out_dir = Path(kwargs["output_root"]) / source_id
        out_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = out_dir / "00-reading-guide.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake")
        json_path = Path(kwargs["output_root"]) / ".scaffolding" / source_id / "reading-scaffolds.json"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text("{}", encoding="utf-8")
        return {
            "status": "written",
            "output_dir": str(out_dir),
            "json_path": str(json_path),
            "markdown_paths": [],
            "pdf_paths": [str(pdf_path)],
        }

    monkeypatch.setattr(
        generate_candidates.printout_engine,
        "build_printout_for_source",
        fake_build_printout_for_source,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_candidates.py",
            "--manifest",
            str(manifest_path),
        ],
    )

    exit_code = generate_candidates.main()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert exit_code == 1
    assert manifest["status"] == "generate_partial"
    assert manifest["summary"]["error_count"] == 1
    assert manifest["summary"]["written_count"] == 1
    assert manifest["summary"]["pending_count"] == 0
    assert manifest["entries"][0]["candidate"]["status"] == "error"
    assert manifest["entries"][1]["candidate"]["status"] == "written"
    assert manifest["entries"][0]["candidate"]["duration_seconds"] is not None
    assert manifest["entries"][1]["candidate"]["duration_seconds"] is not None


def test_generate_candidates_fail_fast_leaves_remaining_entries_pending(tmp_path, monkeypatch):
    _, manifest_path = _manifest_fixture(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["entries"][1]["candidate"] = {"status": "written", "error": ""}
    _write_json(manifest_path, manifest)

    monkeypatch.setattr(generate_candidates, "has_gemini_api_key", lambda: True)
    monkeypatch.setattr(generate_candidates, "preflight_gemini_json_generation", lambda **kwargs: None)
    monkeypatch.setattr(
        generate_candidates.printout_engine,
        "select_sources",
        lambda **kwargs: [
            {"source_id": "source-a", "lecture_key": "W01L1"},
            {"source_id": "source-b", "lecture_key": "W01L1"},
        ],
    )
    monkeypatch.setattr(
        generate_candidates.printout_engine,
        "build_printout_for_source",
        lambda **kwargs: (_ for _ in ()).throw(generate_candidates.printout_engine.PrintoutError("boom")),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_candidates.py",
            "--manifest",
            str(manifest_path),
            "--fail-fast",
        ],
    )

    exit_code = generate_candidates.main()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert exit_code == 1
    assert manifest["entries"][0]["candidate"]["status"] == "error"
    assert manifest["entries"][1]["candidate"]["status"] == "pending"
    assert manifest["summary"]["pending_count"] == 1


def test_generate_candidates_openai_provider_uses_openai_preflight_and_metadata(tmp_path, monkeypatch):
    _, manifest_path = _manifest_fixture(tmp_path)
    preflight_calls = []

    monkeypatch.setattr(generate_candidates, "has_gemini_api_key", lambda: False)
    monkeypatch.setattr(generate_candidates.openai_preprocessing, "has_openai_api_key", lambda: True)
    monkeypatch.setattr(
        generate_candidates.openai_preprocessing,
        "preflight_openai_json_generation",
        lambda **kwargs: preflight_calls.append(kwargs),
    )
    monkeypatch.setattr(
        generate_candidates.openai_preprocessing,
        "make_openai_backend",
        lambda **kwargs: object(),
    )
    monkeypatch.setattr(
        generate_candidates.openai_preprocessing,
        "generation_config_metadata",
        lambda: {"version": "openai-config"},
    )
    monkeypatch.setattr(
        generate_candidates.openai_preprocessing,
        "generate_json",
        lambda **kwargs: {
            "metadata": {
                "language": "da",
                "source_id": "source-a",
                "lecture_key": "W01L1",
                "source_title": "Phenomenology source",
            },
            "reading_guide": {
                "title": "Læseguide",
                "teaser_paragraphs": ["Kort teaser 1.", "Kort teaser 2."],
                "opening_passages": [
                    {
                        "number": "1",
                        "source_location": "s. 1",
                        "excerpt": "Et kort uddrag der åbner problemet på en læsbar måde.",
                        "open_question": "Hvad er problemet?",
                    }
                ],
                "main_problem": "Hovedproblem",
                "subproblems": [
                    {
                        "number": "1",
                        "question": "Delspørgsmål?",
                        "why_it_matters": "Det styrer resten.",
                        "answer_form": "et begreb",
                    }
                ],
            },
            "abridged_reader": {
                "title": "Abridged reader",
                "sections": [
                    {
                        "number": "1",
                        "source_location": "s. 1-2",
                        "heading": "Første sektion",
                        "solves_subproblem": "Delproblem 1",
                        "local_problem": "Delspørgsmål?",
                        "explanation_paragraphs": ["Forklaring."],
                        "key_points": ["Punkt."],
                        "quote_anchors": [],
                        "source_passages": [],
                    }
                ],
            },
            "active_reading": {"title": "Aktiv læsning", "solve_steps": []},
            "consolidation_sheet": {
                "title": "Konsolidering",
                "overview": ["Overblik."],
                "fill_in_sentences": [
                    {
                        "number": "1",
                        "sentence": "Begrebet hedder _____.",
                        "answer_shape": "et begreb",
                    }
                ],
                "diagram_tasks": [
                    {
                        "number": "1",
                        "task": "Tegn modellen.",
                        "required_elements": ["a"],
                        "blank_space_hint": "Lav en model.",
                    }
                ],
            },
            "exam_bridge": {
                "title": "Exam bridge",
                "use_this_text_for": [],
                "course_connections": [],
                "comparison_targets": [],
                "exam_moves": [
                    {"prompt_type": "definer", "use_in_answer": "Brug teksten.", "caution": "Undgå overdrivelse."}
                ],
                "misunderstanding_traps": [],
                "mini_exam_prompt_question": "Spørgsmål?",
                "mini_exam_answer_plan_slots": ["Definér"],
            },
        },
    )
    monkeypatch.setattr(
        generate_candidates.printout_engine,
        "select_sources",
        lambda **kwargs: [
            {"source_id": "source-a", "lecture_key": "W01L1", "title": "Source A", "subject_relative_path": "Readings/source-a.pdf"},
            {"source_id": "source-b", "lecture_key": "W01L1", "title": "Source B", "subject_relative_path": "Readings/source-b.pdf"},
        ],
    )

    captured = {}

    def fake_build_printout_for_source(**kwargs):
        captured["provider"] = kwargs["generation_provider"]
        captured["model"] = kwargs["model"]
        captured["generation_config"] = kwargs["generation_config_metadata_override"]
        captured["json_generator"] = kwargs["json_generator"]
        out_dir = Path(kwargs["output_root"]) / kwargs["source"]["source_id"]
        out_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = out_dir / "00-reading-guide.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake")
        json_path = Path(kwargs["output_root"]) / ".scaffolding" / kwargs["source"]["source_id"] / "reading-scaffolds.json"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text("{}", encoding="utf-8")
        return {
            "status": "written",
            "output_dir": str(out_dir),
            "json_path": str(json_path),
            "markdown_paths": [],
            "pdf_paths": [str(pdf_path)],
        }

    monkeypatch.setattr(
        generate_candidates.printout_engine,
        "build_printout_for_source",
        fake_build_printout_for_source,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_candidates.py",
            "--manifest",
            str(manifest_path),
            "--source-id",
            "source-a",
            "--provider",
            "openai",
            "--model",
            "gpt-5.5",
        ],
    )

    exit_code = generate_candidates.main()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert preflight_calls == [{"model": "gpt-5.5"}]
    assert captured["provider"] == "openai"
    assert captured["model"] == "gpt-5.5"
    assert captured["generation_config"] == {"version": "openai-config"}
    assert callable(captured["json_generator"])
    assert manifest["status"] == "generated"
    assert manifest["entries"][0]["candidate"]["status"] == "written"


def test_generate_candidates_preflights_render_toolchain_with_requested_output_mode(tmp_path, monkeypatch):
    _, manifest_path = _manifest_fixture(tmp_path)
    render_preflight_calls = []

    monkeypatch.setattr(generate_candidates, "has_gemini_api_key", lambda: True)
    monkeypatch.setattr(generate_candidates, "preflight_gemini_json_generation", lambda **kwargs: None)
    monkeypatch.setattr(
        generate_candidates.printout_engine,
        "preflight_render_toolchain",
        lambda **kwargs: render_preflight_calls.append(kwargs) or {},
    )
    monkeypatch.setattr(
        generate_candidates.printout_engine,
        "select_sources",
        lambda **kwargs: [
            {
                "source_id": "source-a",
                "lecture_key": "W01L1",
                "title": "Source A",
                "subject_relative_path": "Readings/source-a.pdf",
            }
        ],
    )
    monkeypatch.setattr(
        generate_candidates.printout_engine,
        "build_printout_for_source",
        lambda **kwargs: {
            "status": "written",
            "output_dir": str(Path(kwargs["output_root"]) / "source-a"),
            "json_path": str(Path(kwargs["output_root"]) / ".scaffolding" / "source-a" / "reading-scaffolds.json"),
            "markdown_paths": [],
            "pdf_paths": [],
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_candidates.py",
            "--manifest",
            str(manifest_path),
            "--source-id",
            "source-a",
            "--no-pdf",
        ],
    )

    exit_code = generate_candidates.main()

    assert exit_code == 0
    assert render_preflight_calls == [{"render_pdf": False}]


def test_generate_candidates_records_generation_failure_stats(tmp_path, monkeypatch):
    _, manifest_path = _manifest_fixture(tmp_path)

    monkeypatch.setattr(generate_candidates, "has_gemini_api_key", lambda: True)
    monkeypatch.setattr(generate_candidates, "preflight_gemini_json_generation", lambda **kwargs: None)
    monkeypatch.setattr(
        generate_candidates.printout_engine,
        "select_sources",
        lambda **kwargs: [{"source_id": "source-a", "lecture_key": "W01L1"}],
    )

    def fail_generation(**kwargs):
        raise generate_candidates.printout_engine.GenerationFailure(
            "generation failed after 3 attempt(s): reset",
            generation_stats={
                "attempt_count": 3,
                "transient_error_count": 2,
                "last_transient_error": "connection reset",
                "last_error_kind": "GeminiPreprocessingGenerationError",
                "last_error_summary": "connection reset",
            },
        )

    monkeypatch.setattr(
        generate_candidates.printout_engine,
        "build_printout_for_source",
        fail_generation,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_candidates.py",
            "--manifest",
            str(manifest_path),
            "--source-id",
            "source-a",
        ],
    )

    exit_code = generate_candidates.main()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    candidate = manifest["entries"][0]["candidate"]

    assert exit_code == 1
    assert candidate["status"] == "error"
    assert candidate["attempt_count"] == 3
    assert candidate["transient_error_count"] == 2
    assert candidate["last_error_kind"] == "GeminiPreprocessingGenerationError"
    assert candidate["last_error_summary"] == "connection reset"
