import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MODULE_PATH = (
    REPO_ROOT
    / "notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/scripts/printout_engine.py"
)
SPEC = importlib.util.spec_from_file_location("printout_review_printout_engine", MODULE_PATH)
assert SPEC and SPEC.loader
printout_engine = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(printout_engine)


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _valid_scaffold_response():
    return {
        "metadata": {
            "language": "da",
            "source_id": "source-1",
            "lecture_key": "W01L1",
            "source_title": "Phenomenology source",
        },
        "reading_guide": {
            "title": "Læseguide",
            "how_to_use": "Læs guiden først, og brug stop-signalerne.",
            "why_this_text_matters": "Teksten fungerer som metodisk anker for forelæsningen.",
            "overview": [
                "Teksten introducerer fænomenologi som metode.",
                "Den forklarer bevidsthed som rettethed.",
                "Den viser hvorfor livsverden er central.",
            ],
            "reading_route": [
                {
                    "number": str(index),
                    "source_location": f"Afsnit {index}",
                    "task": f"Find hovedpointen i afsnit {index}.",
                    "why_it_matters": "Det styrer resten af læsningen.",
                    "stop_signal": "Stop når du har skrevet én kort note.",
                }
                for index in range(1, 4)
            ],
            "key_quote_targets": [
                {"target": "det der viser sig", "why": "Definerer fænomenet.", "where_to_look": "Indledningen."},
                {"target": "bevidsthed om noget", "why": "Markerer intentionalitet.", "where_to_look": "Midterdelen."},
                {"target": "livsverden", "why": "Forankrer metoden.", "where_to_look": "Afslutningen."},
            ],
            "do_not_get_stuck_on": [
                "Alle historiske detaljer.",
                "Små terminologiske variationer.",
            ],
        },
        "abridged_reader": {
            "title": "Abridged reader",
            "how_to_use": "Læs denne version som minimumsvej gennem teksten.",
            "coverage_note": "Denne version bevarer argumentets bevægelse, men erstatter ikke alle detaljer.",
            "sections": [
                {
                    "number": str(index),
                    "source_location": f"Afsnit {index}",
                    "heading": f"Argumenttrin {index}",
                    "explanation_paragraphs": [
                        "Teksten gør først pointen enklere ved at placere begrebet i kontekst.",
                        "Derefter viser den, hvorfor begrebet betyder noget for personlighedspsykologi.",
                    ],
                    "key_points": ["Et centralt begreb.", "En vigtig relation."],
                    "quote_anchors": [
                        {
                            "phrase": "bevidsthed om noget",
                            "why_it_matters": "Det er tekstens korte nøgleformulering.",
                            "source_location": f"Afsnit {index}",
                        }
                    ],
                    "no_quote_anchor_needed": "",
                    "source_touchpoint_source_location": f"Afsnit {index}",
                    "source_touchpoint_task": "Find nøgleformuleringen og understreg den.",
                    "source_touchpoint_answer_or_marking_format": "en understregning",
                    "source_touchpoint_stop_signal": "Stop når én sætning er markeret.",
                    "mini_check_question": f"Hvad er hovedpointen i afsnit {index}?",
                    "mini_check_answer_shape": "en kort sætning",
                    "mini_check_done_signal": "Stop når du har skrevet én sætning.",
                }
                for index in range(1, 4)
            ],
        },
        "active_reading": {
            "title": "Aktiv læsning",
            "instructions": "Start med abridged checks, og lav kun source touchpoints hvis du kan.",
            "abridged_checks": [
                {
                    "number": str(index),
                    "question": f"Hvad skal du forstå i del {index}?",
                    "abridged_reader_location": f"Abridged reader del {index}",
                    "answer_shape": "1-3 ord",
                    "done_signal": "Stop når du har skrevet et kort svar.",
                }
                for index in range(1, 9)
            ],
            "source_touchpoints": [
                {
                    "number": str(index),
                    "source_location": f"Afsnit {index}",
                    "task": "Find én nøgleformulering og understreg den.",
                    "answer_or_marking_format": "en understregning",
                    "stop_signal": "Stop når én formulering er markeret.",
                    "why_this_touchpoint": "Det bevarer kontakt med originalens ordlyd.",
                }
                for index in range(1, 6)
            ],
        },
        "consolidation_sheet": {
            "title": "Konsolidering",
            "overview": [
                "Teksten handler om oplevelse.",
                "Den forklarer metode.",
                "Den viser centrale begreber.",
            ],
            "fill_in_sentences": [
                {
                    "number": str(index),
                    "sentence": f"Begreb {index} hedder __________.",
                    "where_to_look": f"Abridged reader del {index}.",
                    "answer_shape": "et begreb",
                }
                for index in range(1, 6)
            ],
            "diagram_tasks": [
                {
                    "number": "1",
                    "task": "Tegn forholdet mellem intentionalitet, fænomen og livsverden.",
                    "required_elements": ["intentionalitet", "fænomen", "livsverden"],
                    "blank_space_hint": "Lav tre noder og pile mellem dem.",
                }
            ],
        },
        "exam_bridge": {
            "title": "Eksamensbro",
            "instructions": "Brug arket til at flytte teksten ind i eksamenssvar.",
            "use_this_text_for": [
                "spørgsmål om metode",
                "spørgsmål om oplevelse",
                "spørgsmål om personlighedens kontekst",
            ],
            "course_connections": [
                {"course_theme": "subjektivitet", "connection": "Teksten viser hvordan oplevelse bliver analyseobjekt."},
                {"course_theme": "metode", "connection": "Teksten viser hvordan beskrivelser bruges systematisk."},
            ],
            "comparison_targets": [
                {"compare_with": "trækpsykologi", "how_to_compare": "Sammenlign måling med beskrivelse."},
                {"compare_with": "psykoanalyse", "how_to_compare": "Sammenlign oplevelse med fortolkning."},
            ],
            "exam_moves": [
                {"prompt_type": "definer", "use_in_answer": "Brug teksten til at definere metoden.", "caution": "Gør det ikke for bredt."},
                {"prompt_type": "sammenlign", "use_in_answer": "Brug den som kontrast til træk.", "caution": "Undgå karikatur."},
                {"prompt_type": "diskuter", "use_in_answer": "Brug den til metodiske konsekvenser.", "caution": "Hold forbindelsen til kurset."},
            ],
            "misunderstanding_traps": [
                {"trap": "At gøre metoden til introspektion.", "better_reading": "Den er systematisk beskrivelse."},
                {"trap": "At ignorere kontekst.", "better_reading": "Oplevelse er altid rettet mod noget."},
            ],
            "mini_exam_prompt_question": "Hvordan kan teksten bruges til at forstå personlighed?",
            "mini_exam_answer_plan_slots": ["definer tekstens metode", "forklar et begreb", "sammenlign med en anden teori"],
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
    return repo_root, subject_root, output_root, source_card_dir, source


def test_printout_engine_accepts_prompt_overrides(tmp_path):
    repo_root, subject_root, output_root, source_card_dir, source = _source_fixture(tmp_path)
    calls = []

    def fake_json_generator(**kwargs):
        calls.append(kwargs)
        return _valid_scaffold_response()

    def fake_user_prompt_builder(**kwargs):
        return f"EXPERIMENT\n{kwargs['source']['source_id']}"

    result = printout_engine.build_printout_for_source(
        repo_root=repo_root,
        subject_root=subject_root,
        source=source,
        source_card_dir=source_card_dir,
        revised_lecture_substrate_dir=repo_root / "source_intelligence" / "revised_lecture_substrates",
        course_synthesis_path=repo_root / "source_intelligence" / "course_synthesis.json",
        output_root=output_root,
        json_generator=fake_json_generator,
        render_pdf=False,
        prompt_version="problem-driven-v1",
        system_instruction="SYSTEM OVERRIDE",
        user_prompt_builder=fake_user_prompt_builder,
        variant_metadata={"variant_key": "problem_driven_v1"},
    )

    assert result["status"] == "written"
    assert calls[0]["system_instruction"] == "SYSTEM OVERRIDE"
    assert calls[0]["user_prompt"] == "EXPERIMENT\nsource-1"
    artifact = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
    assert artifact["generator"]["prompt_version"] == "problem-driven-v1"
    assert artifact["variant"]["variant_key"] == "problem_driven_v1"
    assert len(result["markdown_paths"]) == 5
