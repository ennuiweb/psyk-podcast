import json
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
RECURSIVE_PATH = REPO_ROOT / "notebooklm_queue" / "personlighedspsykologi_recursive.py"
MODULE_PATH = Path(__file__).resolve().parents[1] / "notebooklm_queue" / "personlighedspsykologi_printouts.py"
SPEC = importlib.util.spec_from_file_location("personlighedspsykologi_printouts", MODULE_PATH)
assert SPEC and SPEC.loader
printouts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(printouts)
RECURSIVE_SPEC = importlib.util.spec_from_file_location("personlighedspsykologi_recursive", RECURSIVE_PATH)
assert RECURSIVE_SPEC and RECURSIVE_SPEC.loader
recursive = importlib.util.module_from_spec(RECURSIVE_SPEC)
RECURSIVE_SPEC.loader.exec_module(recursive)


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _valid_printout_response():
    return {
        "metadata": {
            "language": "da",
            "source_id": "source-1",
            "lecture_key": "W01L1",
            "source_title": "Phenomenology source",
        },
        "abridged_guide": {
            "title": "Forberedende oversigt",
            "overview": [
                "Teksten introducerer faenomenologi som metode.",
                "Den forklarer bevidsthed som rettethed.",
                "Den viser hvorfor livsverden er central.",
            ],
            "structure_and_main_arguments": [
                "Foerst defineres faenomenet.",
                "Dernast forklares intentionalitet.",
                "Til sidst kobles metoden til personlighed.",
            ],
            "key_quote_targets": [
                {"target": "det der viser sig", "why": "Definerer faenomenet."},
                {"target": "bevidsthed om noget", "why": "Markerer intentionalitet."},
                {"target": "livsverden", "why": "Forankrer metoden."},
            ],
        },
        "unit_test_suite": {
            "title": "Unit Test Suite",
            "instructions": "Find svarene i raekkefoelge og stop efter hvert svar.",
            "questions": [
                {"number": index, "question": f"Hvad skal du finde i afsnit {index}?"}
                for index in range(1, 16)
            ],
        },
        "cloze_scaffold": {
            "title": "Printout-opgaver",
            "overview": [
                "Teksten handler om oplevelse.",
                "Den forklarer metode.",
                "Den viser centrale begreber.",
            ],
            "fill_in_sentences": [
                {"number": index, "sentence": f"Begreb {index} hedder __________."}
                for index in range(1, 6)
            ],
            "diagram_tasks": [
                {
                    "number": 1,
                    "task": "Tegn forholdet mellem intentionalitet, faenomen og livsverden.",
                    "blank_space_hint": "Lav tre noder og pile mellem dem.",
                }
            ],
        },
    }


def _source_fixture(tmp_path: Path):
    repo_root = tmp_path / "repo"
    subject_root = tmp_path / "subject"
    output_root = tmp_path / "output"
    source_path = subject_root / "Readings" / "source.pdf"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"%PDF-1.4 source")
    source = {
        "source_id": "source-1",
        "lecture_key": "W01L1",
        "lecture_keys": ["W01L1"],
        "sequence_index": 1,
        "title": "Phenomenology source",
        "source_family": "reading",
        "evidence_origin": "reading_grounded",
        "source_exists": True,
        "subject_relative_path": "Readings/source.pdf",
    }
    source_card_dir = repo_root / "source_intelligence" / "source_cards"
    _write_json(
        source_card_dir / "source-1.json",
        {
            "source": {
                "source_id": "source-1",
                "lecture_key": "W01L1",
                "title": "Phenomenology source",
            },
            "analysis": {
                "theory_role": "Anchor theory role.",
                "source_role": "Anchor source.",
                "relation_to_lecture": "Frames the lecture.",
                "central_claims": [{"claim": "Consciousness is intentional."}],
                "key_concepts": [{"term": "intentionalitet"}],
                "distinctions": [{"label": "pre-reflective vs reflective"}],
                "likely_misunderstandings": ["Treating it as vague introspection."],
                "quote_targets": [{"target": "bevidsthed om noget", "why": "Core phrase."}],
                "grounding_notes": [],
            },
        },
    )
    return repo_root, subject_root, output_root, source_card_dir, source_path, source


def test_build_printout_attaches_source_pdf_to_gemini_and_renders_files(tmp_path, monkeypatch):
    repo_root, subject_root, output_root, source_card_dir, source_path, source = _source_fixture(tmp_path)
    calls = []

    def fake_json_generator(**kwargs):
        calls.append(kwargs)
        return _valid_printout_response()

    def fake_markdown_to_pdf(markdown_path, pdf_path):
        pdf_path.write_bytes(b"%PDF printout")

    monkeypatch.setattr(printouts, "markdown_to_pdf", fake_markdown_to_pdf)

    result = printouts.build_printout_for_source(
        repo_root=repo_root,
        subject_root=subject_root,
        source=source,
        source_card_dir=source_card_dir,
        revised_lecture_substrate_dir=repo_root / "source_intelligence" / "revised_lecture_substrates",
        course_synthesis_path=repo_root / "source_intelligence" / "course_synthesis.json",
        output_root=output_root,
        json_generator=fake_json_generator,
        render_pdf=True,
    )

    assert result["status"] == "written"
    assert calls[0]["source_paths"] == [source_path]
    assert "response_json_schema" in calls[0]
    assert Path(result["json_path"]).exists()
    assert len(result["markdown_paths"]) == 3
    assert len(result["pdf_paths"]) == 3
    assert all(Path(path).exists() for path in result["markdown_paths"])
    assert all(Path(path).exists() for path in result["pdf_paths"])
    cloze_text = Path(result["markdown_paths"][2]).read_text(encoding="utf-8")
    assert "Udfyldningssætninger" in cloze_text
    assert "__________" in cloze_text


def test_build_printouts_default_family_filter_is_reading_only(tmp_path):
    catalog_path = tmp_path / "source_catalog.json"
    _write_json(
        catalog_path,
        {
            "sources": [
                {
                    "source_id": "reading-1",
                    "lecture_key": "W01L1",
                    "lecture_keys": ["W01L1"],
                    "sequence_index": 1,
                    "source_family": "reading",
                    "source_exists": True,
                },
                {
                    "source_id": "slide-1",
                    "lecture_key": "W01L1",
                    "lecture_keys": ["W01L1"],
                    "sequence_index": 2,
                    "source_family": "lecture_slide",
                    "source_exists": True,
                },
            ]
        },
    )

    selected = printouts.select_sources(
        source_catalog_path=catalog_path,
        lecture_keys=recursive.normalize_lecture_keys("W01L1"),
        source_families=printouts.parse_source_families([]),
    )

    assert [item["source_id"] for item in selected] == ["reading-1"]


def test_validate_printout_requires_blank_markers():
    payload = _valid_printout_response()
    payload["cloze_scaffold"]["fill_in_sentences"][0]["sentence"] = "Ingen blank her."

    try:
        printouts.validate_printout_payload(payload)
    except printouts.PrintoutError as exc:
        assert "blank marker" in str(exc)
    else:
        raise AssertionError("expected PrintoutError")
