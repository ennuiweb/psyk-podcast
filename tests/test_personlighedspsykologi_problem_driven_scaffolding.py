import json
from pathlib import Path

from notebooklm_queue import personlighedspsykologi_problem_driven_scaffolding as problem_scaffolding


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
            "title": "Mission brief",
            "how_to_use": "Start med missionen og tag ruten ét punkt ad gangen.",
            "why_this_text_matters": "Teksten afgør et centralt metodisk spørgsmål i forelæsningen.",
            "overview": [
                "Teksten gør oplevelse til et systematisk analysepunkt.",
                "Den afviser en løs introspektionsforståelse.",
                "Den forbinder metode med personlighedspsykologi.",
            ],
            "reading_route": [
                {
                    "number": str(index),
                    "source_location": f"Afsnit {index}",
                    "task": f"Find den lokale pointe i afsnit {index}.",
                    "why_it_matters": "Det låser næste trin op.",
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
                "Historiske sidedetaljer.",
                "Små terminologiske variationer.",
            ],
        },
        "abridged_reader": {
            "title": "Guided solve path",
            "how_to_use": "Løs ét delproblem ad gangen.",
            "coverage_note": "Denne version bevarer argumentets bevægelse som minimumsvej.",
            "sections": [
                {
                    "number": str(index),
                    "source_location": f"Afsnit {index}",
                    "heading": f"Delproblem {index}",
                    "explanation_paragraphs": [
                        "Først opstår en lokal spænding i teksten, som gør begrebet nødvendigt.",
                        "Derefter løser teksten spændingen ved at præcisere begrebet og dets funktion.",
                    ],
                    "key_points": ["Et centralt begreb.", "En vigtig relation."],
                    "quote_anchors": [
                        {
                            "phrase": "bevidsthed om noget",
                            "why_it_matters": "Det er tekstens nøgleanker.",
                            "source_location": f"Afsnit {index}",
                        }
                    ],
                    "no_quote_anchor_needed": "",
                    "source_touchpoint_source_location": f"Afsnit {index}",
                    "source_touchpoint_task": "Find nøgleformuleringen og understreg den.",
                    "source_touchpoint_answer_or_marking_format": "en understregning",
                    "source_touchpoint_stop_signal": "Stop når én sætning er markeret.",
                    "mini_check_question": f"Hvad løser afsnit {index}?",
                    "mini_check_answer_shape": "en kort sætning",
                    "mini_check_done_signal": "Stop når du har skrevet én sætning.",
                }
                for index in range(1, 4)
            ],
        },
        "active_reading": {
            "title": "Evidence hunt",
            "instructions": "Start med de hurtige checks og gå derefter til tekstens beviser.",
            "abridged_checks": [
                {
                    "number": str(index),
                    "question": f"Hvilken lokal beslutning træffes i del {index}?",
                    "abridged_reader_location": f"Guided solve path del {index}",
                    "answer_shape": "1-3 ord",
                    "done_signal": "Stop når du har skrevet et kort svar.",
                }
                for index in range(1, 9)
            ],
            "source_touchpoints": [
                {
                    "number": str(index),
                    "source_location": f"Afsnit {index}",
                    "task": "Find den formulering der beviser pointen og marker den.",
                    "answer_or_marking_format": "en understregning",
                    "stop_signal": "Stop når én formulering er markeret.",
                    "why_this_touchpoint": "Det holder kontakt med originalens ordlyd.",
                }
                for index in range(1, 6)
            ],
        },
        "consolidation_sheet": {
            "title": "Model builder",
            "overview": [
                "Teksten bygger et syn på oplevelse.",
                "Den viser hvorfor metode betyder noget.",
                "Den forbinder begreberne i en samlet model.",
            ],
            "fill_in_sentences": [
                {
                    "number": str(index),
                    "sentence": f"Begreb {index} fungerer som __________ i modellen.",
                    "where_to_look": f"Guided solve path del {index}.",
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
            "title": "Boss fight",
            "instructions": "Brug arket til at bevise at du kan bruge modellen.",
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
                {"prompt_type": "definer", "use_in_answer": "Brug teksten til at definere metoden præcist.", "caution": "Gør det ikke for bredt."},
                {"prompt_type": "sammenlign", "use_in_answer": "Brug den som kontrast til træk.", "caution": "Undgå karikatur."},
                {"prompt_type": "diskuter", "use_in_answer": "Brug den til metodiske konsekvenser.", "caution": "Hold forbindelsen til kurset."},
            ],
            "misunderstanding_traps": [
                {"trap": "At gøre metoden til introspektion.", "better_reading": "Den er systematisk beskrivelse."},
                {"trap": "At ignorere kontekst.", "better_reading": "Oplevelse er altid rettet mod noget."},
            ],
            "mini_exam_prompt_question": "Hvordan løser teksten problemet om oplevelse og metode?",
            "mini_exam_answer_plan_slots": ["definer problemet", "vis modelens løsning", "sammenlign med en anden teori"],
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


def test_problem_driven_scaffold_uses_variant_prompt_and_metadata(tmp_path):
    repo_root, subject_root, output_root, source_card_dir, source = _source_fixture(tmp_path)
    calls = []

    def fake_json_generator(**kwargs):
        calls.append(kwargs)
        return _valid_scaffold_response()

    result = problem_scaffolding.build_scaffold_for_source(
        repo_root=repo_root,
        subject_root=subject_root,
        source=source,
        source_card_dir=source_card_dir,
        revised_lecture_substrate_dir=repo_root / "source_intelligence" / "revised_lecture_substrates",
        course_synthesis_path=repo_root / "source_intelligence" / "course_synthesis.json",
        output_root=output_root,
        json_generator=fake_json_generator,
        render_pdf=False,
    )

    assert result["status"] == "written"
    assert calls[0]["response_json_schema"] is None
    assert "mission brief" in calls[0]["system_instruction"].lower()
    assert "problem to solve" in calls[0]["system_instruction"].lower()
    assert '"section_roles"' in calls[0]["user_prompt"]
    assert '"boss_fight"' in calls[0]["user_prompt"]
    artifact = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
    assert artifact["generator"]["prompt_version"] == problem_scaffolding.PROMPT_VERSION
    assert artifact["variant"]["mode"] == "problem_driven"
    assert artifact["variant"]["variant_key"] == problem_scaffolding.VARIANT_KEY
    assert len(result["markdown_paths"]) == 5


def test_problem_driven_build_scaffolds_dry_run_reports_variant(tmp_path):
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
                    "title": "Reading 1",
                    "source_family": "reading",
                    "source_exists": True,
                }
            ]
        },
    )

    result = problem_scaffolding.build_scaffolds(
        repo_root=tmp_path,
        subject_root=tmp_path / "subject",
        source_catalog_path=catalog_path,
        source_card_dir=tmp_path / "cards",
        revised_lecture_substrate_dir=tmp_path / "revised",
        course_synthesis_path=tmp_path / "course.json",
        output_root=tmp_path / "candidate_output",
        lecture_keys=["W01L1"],
        dry_run=True,
    )

    assert result["status"] == "planned"
    assert result["variant"] == problem_scaffolding.VARIANT_KEY
    assert result["source_count"] == 1
    assert result["sources"][0]["output_dir"].endswith("candidate_output/W01L1/scaffolding/reading-1")
