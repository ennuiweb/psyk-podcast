import json
import re
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from notebooklm_queue import personlighedspsykologi_printouts as printout_engine


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
            "teaser_paragraphs": [
                "Der er ikke enighed om, hvad personligheden er, og teksten åbner derfor ikke med en rolig definition, men med en konflikt om selve feltets genstand.",
                "Når bevidsthed, oplevelse og livsverden får så stor vægt, er det fordi teksten vil flytte dig væk fra forestillingen om en lukket indre beholder og ind i et mere åbent problemfelt.",
                "I stedet for at lukke spændingen hurtigt ned, lader teksten den brede sig: hvis bevidsthed altid er rettet mod noget, hvad betyder det så for, hvordan personlighed overhovedet kan beskrives?",
                "Hvis oplevelse ikke kan skilles fra livsverden, hvor meget af personligheden ligger så i personen, og hvor meget ligger allerede i den verden, personen lever i?",
            ],
            "opening_passages": [
                {
                    "number": "1",
                    "source_location": "Indledningen",
                    "excerpt": "Der er ikke enighed om, hvad personligheden er, og tekstens første bevægelse er derfor at åbne et problem snarere end at give dig en enkel definition.",
                    "open_question": "Hvis der ikke er enighed om, hvad personligheden er, hvad er det så præcis teorierne kæmper om?",
                },
                {
                    "number": "2",
                    "source_location": "Midterdelen",
                    "excerpt": "Bevidsthed beskrives som rettet mod noget frem for som en lukket indre beholder, og det skubber hele teorien væk fra en simpel indre-kerne-model.",
                    "open_question": "Hvad ændrer sig i teorien, hvis bevidsthed forstås som en rettet relation i stedet for en ting inde i personen?",
                },
            ],
            "main_problem": "Hvordan forklarer teksten bevidsthed som rettethed uden at gøre den til en lukket indre beholder?",
            "subproblems": [
                {
                    "number": str(index),
                    "question": question,
                    "why_it_matters": why,
                    "answer_form": answer_form,
                }
                for index, question, why, answer_form in [
                    ("1", "Hvad er det afgørende ved intentionalitet?", "Det er tekstens første nøglesvar.", "et centralt begreb"),
                    ("2", "Hvilken misforståelse afviser teksten?", "Det afklarer hvad teorien ikke siger.", "1-2 ord"),
                    ("3", "Hvordan binder teksten oplevelse til livsverden?", "Det samler metodens konsekvens.", "3-4 sætninger"),
                ]
            ],
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
                    "solves_subproblem": f"Delproblem {index}",
                    "local_problem": (
                        "Hvad er det afgørende ved intentionalitet?"
                        if index == 1
                        else "Hvilken misforståelse afviser teksten?"
                        if index == 2
                        else "Hvordan binder teksten oplevelse til livsverden?"
                    ),
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
                    "source_passages": (
                        [
                            {
                                "source_location": f"Afsnit {index}",
                                "passage": "Bevidsthed er altid rettet mod noget, og den kan ikke forstås som en lukket beholder.",
                                "why_it_matters": "Her skal den studerende møde den præcise formulering, fordi resten af afsnittet bygger på den.",
                            }
                        ]
                        if index == 1
                        else []
                    ),
                    "no_quote_anchor_needed": "",
                }
                for index in range(1, 4)
            ],
        },
        "active_reading": {
            "title": "Aktiv læsning",
            "instructions": "Hold abridged reader åben. Løs delproblemerne et trin ad gangen, og skriv kun det der kræves for at få svaret på plads.",
            "solve_steps": [
                {
                    "number": "1",
                    "subproblem_ref": "Delproblem 1",
                    "prompt": "Find det centrale begreb som gør bevidsthed rettet mod noget.",
                    "task_type": "term",
                    "abridged_reader_location": "Abridged reader sektion 1",
                    "answer_shape": "et begreb",
                    "blank_lines": 1,
                    "done_signal": "Stop når du har skrevet begrebet.",
                }
            ]
            + [
                {
                    "number": "2",
                    "subproblem_ref": "Delproblem 2",
                    "prompt": "Afgør om teksten gør bevidsthed til en indre beholder eller en rettet relation.",
                    "task_type": "decision",
                    "abridged_reader_location": "Abridged reader sektion 2",
                    "answer_shape": "1-2 ord",
                    "blank_lines": 1,
                    "done_signal": "Stop når du har valgt side.",
                },
                {
                    "number": "3",
                    "subproblem_ref": "Delproblem 3",
                    "prompt": "Skriv hvordan teksten forbinder oplevelse med livsverden.",
                    "task_type": "short_paragraph",
                    "abridged_reader_location": "Abridged reader sektion 3",
                    "answer_shape": "3-4 sætninger",
                    "blank_lines": 4,
                    "done_signal": "Stop når du har skrevet et kort afsnit.",
                },
            ]
            + [
                {
                    "number": str(index),
                    "subproblem_ref": f"Delproblem {((index - 1) % 3) + 1}",
                    "prompt": f"Find det næste nødvendige svartrin i delproblem {((index - 1) % 3) + 1}.",
                    "task_type": "term" if index % 2 else "decision",
                    "abridged_reader_location": f"Abridged reader sektion {((index - 1) % 3) + 1}",
                    "answer_shape": "1-3 ord",
                    "blank_lines": 1,
                    "done_signal": "Stop når du har skrevet et kort svar.",
                }
                for index in range(4, 7)
            ],
        },
        "consolidation_sheet": {
            "title": "Konsolidering",
            "instructions": "Lav arket uden at kigge. Brug først abridged reader bagefter til at tjekke eller reparere dine svar.",
            "overview": [
                "Teksten handler om oplevelse.",
                "Den forklarer metode.",
                "Den viser centrale begreber.",
            ],
            "fill_in_sentences": [
                {
                    "number": str(index),
                    "sentence": f"Begreb {index} hedder __________.",
                    "where_to_look": f"Abridged reader sektion {index}.",
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


def test_output_dir_for_source_uses_flat_root():
    output_root = Path("/tmp/review-root")
    source = {"source_id": "source-1", "lecture_key": "W01L1"}

    assert (
        printout_engine.output_dir_for_source(
            output_root,
            source,
            output_layout=printout_engine.OUTPUT_LAYOUT_REVIEW,
        )
        == output_root
    )


def test_output_dir_for_source_uses_canonical_main_tree_by_default():
    output_root = Path("/tmp/output-root")
    source = {"source_id": "source-1", "lecture_key": "W01L1"}

    assert printout_engine.output_dir_for_source(output_root, source) == output_root


def test_canonical_output_layout_writes_stable_main_files(tmp_path, monkeypatch):
    repo_root, subject_root, output_root, source_card_dir, source = _source_fixture(tmp_path)

    def fake_markdown_to_pdf(markdown_path: Path, pdf_path: Path):
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"%PDF-1.4 main")

    monkeypatch.setattr(printout_engine, "markdown_to_pdf", fake_markdown_to_pdf)

    result = printout_engine.build_printout_for_source(
        repo_root=repo_root,
        subject_root=subject_root,
        source=source,
        source_card_dir=source_card_dir,
        revised_lecture_substrate_dir=repo_root / "source_intelligence" / "revised_lecture_substrates",
        course_synthesis_path=repo_root / "source_intelligence" / "course_synthesis.json",
        output_root=output_root,
        json_generator=lambda **kwargs: _valid_scaffold_response(),
        render_pdf=True,
        variant_metadata={
            "mode": "canonical_main",
            "variant_key": "problem_driven_v1",
            "render_completion_markers": False,
            "render_exam_bridge": False,
        },
    )

    output_dir = Path(result["output_dir"])
    assert output_dir == output_root
    assert Path(result["json_path"]) == output_root / "printout-json" / "source-1" / "reading-printouts.json"
    assert sorted(path.name for path in output_dir.glob("*.pdf")) == [
        "W01L1--source-1--00-cover.pdf",
        "W01L1--source-1--01-reading-guide.pdf",
        "W01L1--source-1--02-active-reading.pdf",
        "W01L1--source-1--03-abridged-version.pdf",
        "W01L1--source-1--04-consolidation-sheet.pdf",
    ]
    assert all("--source-1--" in path.name for path in output_dir.glob("*.pdf"))


def test_canonical_output_ignores_legacy_schema_and_generates_v3(tmp_path, monkeypatch):
    repo_root, subject_root, output_root, source_card_dir, source = _source_fixture(tmp_path)
    legacy_dir = output_root / "W01L1" / "scaffolding" / "source-1"
    _write_json(
        legacy_dir / printout_engine.LEGACY_PRINTOUT_JSON_NAME,
        {
            "schema_version": printout_engine.LEGACY_SCHEMA_VERSION,
            "source": {"source_id": "source-1", "title": "Phenomenology source", "lecture_key": "W01L1"},
            "scaffolds": {
                "abridged_guide": {
                    "title": "Forberedende oversigt",
                    "overview": ["a", "b", "c"],
                    "structure_and_main_arguments": ["a", "b", "c"],
                    "key_quote_targets": [{"target": "x", "why": "y"}],
                },
                "unit_test_suite": {
                    "title": "Unit Test Suite",
                    "instructions": "Find svarene.",
                    "questions": [{"number": index, "question": f"Spørgsmål {index}?"} for index in range(1, 16)],
                },
                "cloze_scaffold": {
                    "title": "Printout-opgaver",
                    "overview": ["a", "b", "c"],
                    "fill_in_sentences": [{"number": index, "sentence": f"Begreb {index} er __________."} for index in range(1, 6)],
                    "diagram_tasks": [{"number": 1, "task": "Tegn modellen.", "blank_space_hint": "Tre noder."}],
                },
            },
        },
    )
    legacy_dir.mkdir(parents=True, exist_ok=True)
    for stem in printout_engine.V2_RENDER_STEMS:
        (legacy_dir / f"{stem}.pdf").write_bytes(b"%PDF-1.4 legacy")

    generated = []

    def fake_json_generator(**kwargs):
        generated.append(kwargs)
        return _valid_scaffold_response()

    def fake_markdown_to_pdf(markdown_path: Path, pdf_path: Path):
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"%PDF-1.4 v3")

    monkeypatch.setattr(printout_engine, "markdown_to_pdf", fake_markdown_to_pdf)

    result = printout_engine.build_printout_for_source(
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

    output_dir = Path(result["output_dir"])
    assert result["status"] == "written"
    assert generated
    assert Path(result["json_path"]) == output_root / "printout-json" / "source-1" / "reading-printouts.json"
    assert json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))["schema_version"] == printout_engine.SCHEMA_VERSION
    assert sorted(path.name for path in output_dir.glob("*.pdf")) == [
        "W01L1--source-1--00-cover.pdf",
        "W01L1--source-1--01-reading-guide.pdf",
        "W01L1--source-1--02-active-reading.pdf",
        "W01L1--source-1--03-abridged-version.pdf",
        "W01L1--source-1--04-consolidation-sheet.pdf",
    ]


def test_canonical_rerender_existing_rejects_legacy_schema_without_generation(tmp_path):
    repo_root, subject_root, output_root, source_card_dir, source = _source_fixture(tmp_path)
    legacy_dir = output_root / "W01L1" / "scaffolding" / "source-1"
    _write_json(
        legacy_dir / printout_engine.LEGACY_PRINTOUT_JSON_NAME,
        {
            "schema_version": printout_engine.LEGACY_SCHEMA_VERSION,
            "source": {"source_id": "source-1", "title": "Phenomenology source", "lecture_key": "W01L1"},
            "scaffolds": {},
        },
    )

    with pytest.raises(printout_engine.PrintoutError, match="legacy schema"):
        printout_engine.build_printout_for_source(
            repo_root=repo_root,
            subject_root=subject_root,
            source=source,
            source_card_dir=source_card_dir,
            revised_lecture_substrate_dir=repo_root / "source_intelligence" / "revised_lecture_substrates",
            course_synthesis_path=repo_root / "source_intelligence" / "course_synthesis.json",
            output_root=output_root,
            json_generator=lambda **kwargs: (_ for _ in ()).throw(AssertionError("generation must not run")),
            render_pdf=False,
            rerender_existing=True,
        )


def test_review_pdf_filename_includes_provider_model_and_source_id():
    artifact = {
        "generator": {"provider": "openai", "model": "gpt-5.5"},
        "source": {"source_id": "source-1"},
    }

    assert (
        printout_engine._review_pdf_filename(artifact, "01-reading-guide")
        == "openai-gpt-5_5--source-1--01-reading-guide.pdf"
    )


def test_renderers_prefer_reading_title_over_citation_label():
    artifact = {
        "source": {
            "source_id": "w01l1-lewis-1999-295c67e3",
            "title": "Lewis (1999)",
            "reading_title": "Issues in the Study of Personality Development",
            "lecture_key": "W01L1",
        },
        "variant": {"mode": "evaluation_sandbox", "render_completion_markers": True, "render_exam_bridge": False},
    }

    cover_markdown = printout_engine.render_compendium_cover_markdown(artifact)
    guide_markdown = printout_engine.render_reading_guide_markdown(
        artifact,
        {"teaser_paragraphs": ["En kort teaser om personlighedsudvikling."]},
    )

    assert "Issues in the Study of Personality Development" in cover_markdown
    assert "Issues in the Study of Personality Development" in guide_markdown
    assert "Lewis (1999)" not in cover_markdown
    assert "**Kilde:** Lewis (1999)" not in guide_markdown
    assert "<!-- printout-source: Issues in the Study of Personality Development -->" in cover_markdown


def test_known_review_source_ids_have_reading_title_overrides():
    assert (
        printout_engine._reading_title_from_source(
            {"source_id": "w09l1-dreier-1999-35da58b5", "title": "Dreier (1999)"}
        )
        == "Personal Trajectories of Participation across Contexts of Social Practice"
    )


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
            variant_metadata={
                "mode": "evaluation_sandbox",
                "variant_key": "problem_driven_v1",
                "render_completion_markers": True,
                "render_exam_bridge": False,
            },
            output_layout=printout_engine.OUTPUT_LAYOUT_REVIEW,
        )

    assert result["status"] == "written"
    assert calls[0]["system_instruction"] == "SYSTEM OVERRIDE"
    assert calls[0]["user_prompt"] == "EXPERIMENT\nsource-1"
    artifact = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
    assert artifact["generator"]["provider"] == "gemini"
    assert artifact["generator"]["prompt_version"] == "problem-driven-v1"
    assert artifact["source"]["reading_title"] == "Phenomenology source"
    assert artifact["variant"]["variant_key"] == "problem_driven_v1"
    assert artifact["variant"]["render_completion_markers"] is True
    assert result["output_dir"].endswith("/output")
    expected_json_path = printout_engine.artifact_json_path_for_source_id(
        output_root,
        source_id="source-1",
        provider="gemini",
        model=printout_engine.DEFAULT_GEMINI_PREPROCESSING_MODEL,
    )
    assert Path(result["json_path"]) == expected_json_path
    assert artifact["printouts"]["reading_guide"]["title"] == "Reading Guide"
    assert artifact["printouts"]["abridged_reader"]["title"] == "Abridged Version"
    assert artifact["printouts"]["active_reading"]["title"] == "Active Reading"
    assert artifact["printouts"]["consolidation_sheet"]["title"] == "Consolidation Sheet"
    assert artifact["printouts"]["exam_bridge"]["title"] == "Exam Bridge"
    assert artifact["variant"]["render_exam_bridge"] is False
    assert len(result["markdown_paths"]) == 5
    assert all("/.scaffolding/artifacts/gemini-" in path for path in result["markdown_paths"])
    assert all("/source-1/rendered_markdown/" in path for path in result["markdown_paths"])
    output_dir = Path(result["output_dir"])
    assert not any(path.suffix == ".md" for path in output_dir.glob("*"))
    cover_markdown = Path(result["markdown_paths"][0]).read_text(encoding="utf-8")
    guide_markdown = Path(result["markdown_paths"][1]).read_text(encoding="utf-8")
    active_markdown = Path(result["markdown_paths"][2]).read_text(encoding="utf-8")
    abridged_markdown = Path(result["markdown_paths"][3]).read_text(encoding="utf-8")
    consolidation_markdown = Path(result["markdown_paths"][4]).read_text(encoding="utf-8")
    assert cover_markdown.startswith("<!-- printout-title: Compendium -->")
    assert "Reading Guide" in cover_markdown
    assert "Active Reading" in cover_markdown
    assert "Abridged Version" in cover_markdown
    assert "Consolidation Sheet" in cover_markdown
    assert r"\fbox" not in cover_markdown
    assert guide_markdown.startswith("# Reading Guide")
    assert abridged_markdown.startswith("# Abridged Version")
    assert active_markdown.startswith("# Active Reading")
    assert consolidation_markdown.startswith("# Consolidation Sheet")
    assert "**Problemet.**" not in guide_markdown
    assert "[ ]" not in guide_markdown
    assert printout_engine._vspace_key("guide_paragraph_gap") in guide_markdown
    assert "## 1. Argumenttrin 1" in abridged_markdown
    assert "`afsnit 1`" in abridged_markdown
    assert "*bevidsthed om noget* | `afsnit 1`" not in abridged_markdown
    assert "**Kort sagt:**" in abridged_markdown
    assert "> *“Bevidsthed er altid rettet mod noget, og den kan ikke forstås som en lukket beholder.”*" in abridged_markdown
    assert "> `afsnit 1`" in abridged_markdown
    assert "**1.** **Skriv** begrebet, som besvarer spørgsmålet:" in active_markdown
    assert "[ ]" not in active_markdown
    assert "[ ]" not in consolidation_markdown
    assert "**Overblik**" in consolidation_markdown
    assert "**Udfyld**" in consolidation_markdown
    assert "**Tegn**" in consolidation_markdown
    assert "**Diagram 1.**" in consolidation_markdown
    assert "______________________________" in consolidation_markdown
    assert "\\vspace*{\\fill}" not in active_markdown
    assert printout_engine._vspace_key("active_step_gap") in active_markdown
    assert "Der er ikke enighed om, hvad personligheden er" in guide_markdown
    assert ">" not in guide_markdown
    assert "---" not in guide_markdown
    assert "## Hovedproblem" not in guide_markdown
    assert "## Sådan bruger du arket" not in guide_markdown
    assert "*Afsnit 1*" not in abridged_markdown
    assert "**Lokalt spørgsmål:**" not in abridged_markdown
    assert "**Nøglepunkter:**" not in abridged_markdown
    assert "Kildeanker:" not in abridged_markdown
    assert "source touchpoints" not in active_markdown.casefold()
    assert "Rolle i arbejdsflowet" not in active_markdown
    assert "Tjek bagefter i:" not in active_markdown
    assert "Stop når:" not in active_markdown
    assert "### Delproblem 3" not in active_markdown
    assert "Abridged reader sektion" not in active_markdown
    assert "\\noindent\\rule{\\linewidth}{0.4pt}" in active_markdown
    assert "Rolle i arbejdsflowet" not in consolidation_markdown
    assert "Tjek bagefter i:" not in consolidation_markdown
    assert "Svarform:" not in consolidation_markdown
    assert "Abridged reader sektion" not in consolidation_markdown
    assert "\\vspace*{" in consolidation_markdown
    assert all("05-exam-bridge" not in path for path in result["markdown_paths"])

    forced = printout_engine.build_printout_for_source(
        repo_root=repo_root,
        subject_root=subject_root,
        source=source,
        source_card_dir=source_card_dir,
        revised_lecture_substrate_dir=repo_root / "source_intelligence" / "revised_lecture_substrates",
        course_synthesis_path=repo_root / "source_intelligence" / "course_synthesis.json",
        output_root=output_root,
        json_generator=fake_json_generator,
        render_pdf=False,
        force=True,
        prompt_version="problem-driven-v1",
        system_instruction="SYSTEM OVERRIDE",
        user_prompt_builder=fake_user_prompt_builder,
        variant_metadata={
            "mode": "evaluation_sandbox",
            "variant_key": "problem_driven_v1",
            "render_completion_markers": True,
            "render_exam_bridge": False,
        },
        output_layout=printout_engine.OUTPUT_LAYOUT_REVIEW,
    )
    assert forced["status"] == "written"
    assert forced["output_dir"].endswith("/output")


def test_printout_engine_records_non_gemini_generation_provider(tmp_path):
    repo_root, subject_root, output_root, source_card_dir, source = _source_fixture(tmp_path)

    result = printout_engine.build_printout_for_source(
        repo_root=repo_root,
        subject_root=subject_root,
        source=source,
        source_card_dir=source_card_dir,
        revised_lecture_substrate_dir=repo_root / "source_intelligence" / "revised_lecture_substrates",
        course_synthesis_path=repo_root / "source_intelligence" / "course_synthesis.json",
        output_root=output_root,
        json_generator=lambda **kwargs: _valid_scaffold_response(),
        render_pdf=False,
        generation_provider="openai",
        generation_config_metadata_override={"version": "openai-test-config"},
        model="gpt-5.5",
        variant_metadata={
            "variant_key": "problem_driven_v1",
            "render_completion_markers": True,
            "render_exam_bridge": False,
        },
    )

    artifact = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
    assert artifact["generator"]["provider"] == "openai"
    assert artifact["generator"]["model"] == "gpt-5.5"
    assert artifact["generator"]["generation_config"] == {"version": "openai-test-config"}


def test_build_printout_skips_exam_bridge_validation_when_render_disabled(tmp_path):
    repo_root, subject_root, output_root, source_card_dir, source = _source_fixture(tmp_path)
    payload = _valid_scaffold_response()
    payload["exam_bridge"]["exam_moves"] = []

    result = printout_engine.build_printout_for_source(
        repo_root=repo_root,
        subject_root=subject_root,
        source=source,
        source_card_dir=source_card_dir,
        revised_lecture_substrate_dir=repo_root / "source_intelligence" / "revised_lecture_substrates",
        course_synthesis_path=repo_root / "source_intelligence" / "course_synthesis.json",
        output_root=output_root,
        json_generator=lambda **kwargs: payload,
        render_pdf=False,
        variant_metadata={
            "variant_key": "problem_driven_v1",
            "render_completion_markers": True,
            "render_exam_bridge": False,
        },
    )

    assert result["status"] == "written"


def test_completion_markers_can_be_disabled(tmp_path):
    repo_root, subject_root, output_root, source_card_dir, source = _source_fixture(tmp_path)

    result = printout_engine.build_printout_for_source(
        repo_root=repo_root,
        subject_root=subject_root,
        source=source,
        source_card_dir=source_card_dir,
        revised_lecture_substrate_dir=repo_root / "source_intelligence" / "revised_lecture_substrates",
        course_synthesis_path=repo_root / "source_intelligence" / "course_synthesis.json",
        output_root=output_root,
        json_generator=lambda **kwargs: _valid_scaffold_response(),
        render_pdf=False,
        prompt_version="problem-driven-v1",
        variant_metadata={
            "variant_key": "problem_driven_v1",
            "render_completion_markers": False,
            "render_exam_bridge": False,
        },
    )

    cover_markdown = Path(result["markdown_paths"][0]).read_text(encoding="utf-8")
    guide_markdown = Path(result["markdown_paths"][1]).read_text(encoding="utf-8")
    active_markdown = Path(result["markdown_paths"][2]).read_text(encoding="utf-8")
    abridged_markdown = Path(result["markdown_paths"][3]).read_text(encoding="utf-8")
    consolidation_markdown = Path(result["markdown_paths"][4]).read_text(encoding="utf-8")

    assert "[ ]" not in cover_markdown
    assert r"\fbox" not in cover_markdown
    assert "[ ]" not in guide_markdown
    assert "## [ ]" not in abridged_markdown
    assert "[ ] **1.**" not in active_markdown
    assert "[ ] blanks udfyldt" not in consolidation_markdown
    assert len(result["markdown_paths"]) == 5


def test_source_passage_renderer_marks_fragments_without_context():
    block = printout_engine._render_source_passage_block("inherently valuable unity", "Side 6")

    assert block == "> *“(...) inherently valuable unity (...)”*\n>\n> `s. 6`"


def test_exam_bridge_is_optional_at_render_time_and_removed_when_disabled(tmp_path):
    artifact = {
        "schema_version": printout_engine.SCHEMA_VERSION,
        "source": {"source_id": "source-1", "title": "Phenomenology source", "lecture_key": "W01L1"},
        "variant": {"mode": "evaluation_sandbox", "render_completion_markers": True, "render_exam_bridge": False},
        "printouts": _valid_scaffold_response(),
    }
    output_dir = tmp_path / "printouts"
    output_dir.mkdir()
    stale_exam = output_dir / ".scaffolding" / "source-1" / "rendered_markdown" / "05-exam-bridge.md"
    stale_exam.parent.mkdir(parents=True, exist_ok=True)
    stale_exam.write_text("stale", encoding="utf-8")

    result = printout_engine.render_v3_printout_files(
        artifact=artifact,
        output_dir=output_dir,
        render_pdf=False,
    )

    assert len(result["markdown_paths"]) == 5
    assert not stale_exam.exists()
    assert all("05-exam-bridge" not in path for path in result["markdown_paths"])

    artifact["variant"]["render_exam_bridge"] = True
    result_with_exam = printout_engine.render_v3_printout_files(
        artifact=artifact,
        output_dir=output_dir,
        render_pdf=False,
    )
    assert len(result_with_exam["markdown_paths"]) == 6
    exam_markdown = Path(result_with_exam["markdown_paths"][5]).read_text(encoding="utf-8")
    assert exam_markdown.startswith("# Exam Bridge")
    assert "## Sig Højt" in exam_markdown
    assert "**Undgå:**" in exam_markdown


def test_no_pdf_render_keeps_output_dir_free_of_markdown_and_json(tmp_path):
    artifact = {
        "schema_version": printout_engine.SCHEMA_VERSION,
        "source": {"source_id": "source-1", "title": "Phenomenology source", "lecture_key": "W01L1"},
        "variant": {"mode": "evaluation_sandbox", "render_completion_markers": True, "render_exam_bridge": False},
        "printouts": _valid_scaffold_response(),
    }
    output_dir = tmp_path / "review"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "00-cover.md").write_text("stale", encoding="utf-8")
    (output_dir / "reading-scaffolds.json").write_text("stale", encoding="utf-8")

    result = printout_engine.render_v3_printout_files(
        artifact=artifact,
        output_dir=output_dir,
        render_pdf=False,
    )

    assert len(result["markdown_paths"]) == 5
    assert all("/.scaffolding/source-1/rendered_markdown/" in path for path in result["markdown_paths"])
    files = sorted(path.name for path in output_dir.iterdir() if path.is_file())
    assert files == []


def test_no_pdf_render_removes_stale_user_facing_pdfs(tmp_path):
    artifact = {
        "schema_version": printout_engine.SCHEMA_VERSION,
        "source": {"source_id": "source-1", "title": "Phenomenology source", "lecture_key": "W01L1"},
        "variant": {"mode": "evaluation_sandbox", "render_completion_markers": True, "render_exam_bridge": False},
        "printouts": _valid_scaffold_response(),
    }
    output_dir = tmp_path / "review"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / printout_engine._review_pdf_filename(artifact, "00-cover")).write_bytes(b"%PDF-1.4 stale")
    (output_dir / printout_engine._review_pdf_filename(artifact, "05-exam-bridge")).write_bytes(b"%PDF-1.4 stale")

    result = printout_engine.render_v3_printout_files(
        artifact=artifact,
        output_dir=output_dir,
        render_pdf=False,
    )

    assert len(result["markdown_paths"]) == 5
    assert sorted(path.name for path in output_dir.iterdir() if path.is_file()) == []


def test_pdf_render_keeps_printout_output_pdf_only_and_moves_json_internal(tmp_path, monkeypatch):
    repo_root, subject_root, output_root, source_card_dir, source = _source_fixture(tmp_path)

    def fake_markdown_to_pdf(markdown_path: Path, pdf_path: Path):
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"%PDF-1.4 fake")

    monkeypatch.setattr(printout_engine, "markdown_to_pdf", fake_markdown_to_pdf)

    result = printout_engine.build_printout_for_source(
        repo_root=repo_root,
        subject_root=subject_root,
        source=source,
        source_card_dir=source_card_dir,
        revised_lecture_substrate_dir=repo_root / "source_intelligence" / "revised_lecture_substrates",
        course_synthesis_path=repo_root / "source_intelligence" / "course_synthesis.json",
        output_root=output_root,
        json_generator=lambda **kwargs: _valid_scaffold_response(),
        render_pdf=True,
        prompt_version="problem-driven-v1",
            variant_metadata={
                "mode": "evaluation_sandbox",
                "variant_key": "problem_driven_v1",
                "render_completion_markers": True,
                "render_exam_bridge": False,
            },
            output_layout=printout_engine.OUTPUT_LAYOUT_REVIEW,
        )

    output_dir = Path(result["output_dir"])
    files = sorted(path.name for path in output_dir.iterdir() if path.is_file())
    expected_files = [
        printout_engine._review_pdf_filename(json.loads(Path(result["json_path"]).read_text(encoding="utf-8")), stem)
        for stem in (
            "00-cover",
            "01-reading-guide",
            "02-active-reading",
            "03-abridged-version",
            "04-consolidation-sheet",
        )
    ]
    assert files == expected_files
    assert Path(result["json_path"]).name == printout_engine.LEGACY_PRINTOUT_JSON_NAME
    assert Path(result["json_path"]).exists()


def test_pdf_render_failure_keeps_existing_public_bundle_untouched(tmp_path, monkeypatch):
    artifact = {
        "schema_version": printout_engine.SCHEMA_VERSION,
        "source": {"source_id": "source-1", "title": "Phenomenology source", "lecture_key": "W01L1"},
        "generator": {"provider": "gemini", "model": "gemini-3.1-pro-preview"},
        "variant": {"render_completion_markers": True, "render_exam_bridge": False},
        "printouts": _valid_scaffold_response(),
    }
    output_dir = tmp_path / "review"
    output_dir.mkdir(parents=True, exist_ok=True)
    expected_stems = (
        "00-cover",
        "01-reading-guide",
        "02-active-reading",
        "03-abridged-version",
        "04-consolidation-sheet",
    )
    for stem in expected_stems:
        (output_dir / printout_engine._review_pdf_filename(artifact, stem)).write_bytes(f"old {stem}".encode())

    monkeypatch.setattr(printout_engine, "preflight_render_toolchain", lambda: {})

    def fake_markdown_to_pdf(markdown_path: Path, pdf_path: Path):
        pdf_path.write_bytes(f"new {markdown_path.stem}".encode())
        if markdown_path.stem == "03-abridged-version":
            raise printout_engine.PrintoutError("render exploded")

    monkeypatch.setattr(printout_engine, "markdown_to_pdf", fake_markdown_to_pdf)

    with pytest.raises(printout_engine.PrintoutError, match="render exploded"):
        printout_engine.render_v3_printout_files(
            artifact=artifact,
            output_dir=output_dir,
            render_pdf=True,
        )

    for stem in expected_stems:
        path = output_dir / printout_engine._review_pdf_filename(artifact, stem)
        assert path.read_bytes() == f"old {stem}".encode()
    assert not (output_dir / printout_engine.INTERNAL_REVIEW_ARTIFACT_DIRNAME / "source-1" / printout_engine.PDF_STAGING_DIRNAME).exists()


def test_preflight_render_toolchain_requires_known_binaries(monkeypatch):
    binary_map = {
        "pandoc": "/usr/local/bin/pandoc",
        "lualatex": "/usr/local/bin/lualatex",
        "pdfinfo": "/usr/local/bin/pdfinfo",
    }
    monkeypatch.setattr(printout_engine.shutil, "which", lambda name: binary_map.get(name))

    toolchain = printout_engine.preflight_render_toolchain()

    assert toolchain == {
        "pandoc": "/usr/local/bin/pandoc",
        "pdf_engine": "lualatex",
        "pdfinfo": "/usr/local/bin/pdfinfo",
    }


def test_preflight_render_toolchain_fails_without_pdfinfo(monkeypatch):
    binary_map = {
        "pandoc": "/usr/local/bin/pandoc",
        "xelatex": "/usr/local/bin/xelatex",
    }
    monkeypatch.setattr(printout_engine.shutil, "which", lambda name: binary_map.get(name))

    with pytest.raises(printout_engine.PrintoutError, match="pdfinfo"):
        printout_engine.preflight_render_toolchain()


def test_rerender_existing_migrates_from_numbered_test_dir_to_flat_output(tmp_path, monkeypatch):
    repo_root, subject_root, output_root, source_card_dir, source = _source_fixture(tmp_path)
    numbered_output_dir = output_root / "W01L1" / "printouts" / "source-1" / "001"
    numbered_output_dir.mkdir(parents=True, exist_ok=True)
    (numbered_output_dir / "00-reading-guide.pdf").write_bytes(b"%PDF-1.4 old")

    legacy_numbered_dir = output_root / "W01L1" / "scaffolding" / "source-1" / "001"
    legacy_numbered_dir.mkdir(parents=True, exist_ok=True)
    _write_json(legacy_numbered_dir / printout_engine.LEGACY_PRINTOUT_JSON_NAME, {
        "schema_version": printout_engine.SCHEMA_VERSION,
        "source": {"title": "Phenomenology source", "lecture_key": "W01L1"},
        "variant": {"render_completion_markers": True, "render_exam_bridge": False},
        "printouts": _valid_scaffold_response(),
    })

    def fake_markdown_to_pdf(markdown_path: Path, pdf_path: Path):
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"%PDF-1.4 rerendered")

    monkeypatch.setattr(printout_engine, "markdown_to_pdf", fake_markdown_to_pdf)

    result = printout_engine.build_printout_for_source(
        repo_root=repo_root,
        subject_root=subject_root,
        source=source,
        source_card_dir=source_card_dir,
        revised_lecture_substrate_dir=repo_root / "source_intelligence" / "revised_lecture_substrates",
        course_synthesis_path=repo_root / "source_intelligence" / "course_synthesis.json",
        output_root=output_root,
        render_pdf=True,
        rerender_existing=True,
            variant_metadata={
                "mode": "evaluation_sandbox",
                "variant_key": "problem_driven_v1",
                "render_completion_markers": True,
                "render_exam_bridge": False,
            },
            output_layout=printout_engine.OUTPUT_LAYOUT_REVIEW,
        )

    assert result["status"] == "rerendered_existing"
    assert result["output_dir"].endswith("/output")
    assert Path(result["json_path"]).exists()
    files = sorted(path.name for path in Path(result["output_dir"]).iterdir() if path.is_file())
    rerendered_artifact = json.loads(Path(result["json_path"]).read_text(encoding="utf-8"))
    assert files == [
        printout_engine._review_pdf_filename(rerendered_artifact, stem)
        for stem in (
            "00-cover",
            "01-reading-guide",
            "02-active-reading",
            "03-abridged-version",
            "04-consolidation-sheet",
        )
    ]
    assert not (output_root / "W01L1").exists()


def test_find_existing_artifact_json_checks_legacy_run_candidate_output_when_using_review_root(tmp_path):
    review_root = tmp_path / "printout_review" / "review"
    legacy_json_path = (
        tmp_path
        / "printout_review"
        / "runs"
        / "legacy-run"
        / "candidate_output"
        / ".scaffolding"
        / "source-1"
        / printout_engine.LEGACY_PRINTOUT_JSON_NAME
    )
    _write_json(
        legacy_json_path,
        {
            "schema_version": printout_engine.SCHEMA_VERSION,
            "source": {"source_id": "source-1", "lecture_key": "W01L1"},
            "generator": {"provider": "openai", "model": "gpt-5.5"},
            "variant": {"render_completion_markers": True},
            "printouts": _valid_scaffold_response(),
        },
    )

    source = {"source_id": "source-1", "lecture_key": "W01L1"}
    found = printout_engine._find_existing_artifact_json(review_root, source, review_root)

    assert found == legacy_json_path


def test_build_printout_auto_rerenders_legacy_run_artifact_into_shared_review_root(tmp_path, monkeypatch):
    repo_root, subject_root, _, source_card_dir, source = _source_fixture(tmp_path)
    review_root = tmp_path / "printout_review" / "review"
    legacy_json_path = (
        tmp_path
        / "printout_review"
        / "runs"
        / "legacy-run"
        / "candidate_output"
        / ".scaffolding"
        / "source-1"
        / printout_engine.LEGACY_PRINTOUT_JSON_NAME
    )
    _write_json(
        legacy_json_path,
        {
            "schema_version": printout_engine.SCHEMA_VERSION,
            "source": {"source_id": "source-1", "title": "Phenomenology source", "lecture_key": "W01L1"},
            "generator": {"provider": "openai", "model": "gpt-5.5"},
            "variant": {"render_completion_markers": True, "render_exam_bridge": False},
            "printouts": _valid_scaffold_response(),
        },
    )

    def fake_markdown_to_pdf(markdown_path: Path, pdf_path: Path):
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"%PDF-1.4 migrated")

    monkeypatch.setattr(printout_engine, "markdown_to_pdf", fake_markdown_to_pdf)

    result = printout_engine.build_printout_for_source(
        repo_root=repo_root,
        subject_root=subject_root,
        source=source,
        source_card_dir=source_card_dir,
        revised_lecture_substrate_dir=repo_root / "source_intelligence" / "revised_lecture_substrates",
        course_synthesis_path=repo_root / "source_intelligence" / "course_synthesis.json",
            output_root=review_root,
            generation_provider="openai",
            model="gpt-5.5",
            render_pdf=True,
            output_layout=printout_engine.OUTPUT_LAYOUT_REVIEW,
        )

    assert result["status"] == "rerendered_existing"
    assert result["output_dir"].endswith("/review")
    assert Path(result["json_path"]).exists()
    assert Path(result["json_path"]).parent == review_root / ".scaffolding" / "artifacts" / "openai-gpt-5_5" / "source-1"
    assert sorted(path.name for path in review_root.glob("*.pdf")) == [
        "openai-gpt-5_5--source-1--00-cover.pdf",
        "openai-gpt-5_5--source-1--01-reading-guide.pdf",
        "openai-gpt-5_5--source-1--02-active-reading.pdf",
        "openai-gpt-5_5--source-1--03-abridged-version.pdf",
        "openai-gpt-5_5--source-1--04-consolidation-sheet.pdf",
    ]


def test_seeded_variant_metadata_is_rejected(tmp_path):
    repo_root, subject_root, output_root, source_card_dir, source = _source_fixture(tmp_path)

    with pytest.raises(printout_engine.PrintoutError, match="seeded_from_baseline is forbidden"):
        printout_engine.build_printout_for_source(
            repo_root=repo_root,
            subject_root=subject_root,
            source=source,
            source_card_dir=source_card_dir,
            revised_lecture_substrate_dir=repo_root / "source_intelligence" / "revised_lecture_substrates",
            course_synthesis_path=repo_root / "source_intelligence" / "course_synthesis.json",
            output_root=output_root,
            json_generator=lambda **kwargs: _valid_scaffold_response(),
            render_pdf=False,
            variant_metadata={"seeded_from_baseline": True},
        )


def test_seeded_existing_candidate_is_rejected_on_skip(tmp_path):
    repo_root, subject_root, output_root, source_card_dir, source = _source_fixture(tmp_path)
    seeded_json_path = output_root / "W01L1" / "scaffolding" / "source-1" / printout_engine.LEGACY_PRINTOUT_JSON_NAME
    _write_json(
        seeded_json_path,
        {
            "schema_version": printout_engine.SCHEMA_VERSION,
            "generator": {"provider": "seeded-from-baseline"},
            "variant": {"seeded_from_baseline": True, "render_exam_bridge": False},
            "source": {"title": "Phenomenology source", "lecture_key": "W01L1"},
            "printouts": _valid_scaffold_response(),
        },
    )

    with pytest.raises(printout_engine.PrintoutError, match="seeded and invalid for reuse"):
        printout_engine.build_printout_for_source(
            repo_root=repo_root,
            subject_root=subject_root,
            source=source,
            source_card_dir=source_card_dir,
            revised_lecture_substrate_dir=repo_root / "source_intelligence" / "revised_lecture_substrates",
            course_synthesis_path=repo_root / "source_intelligence" / "course_synthesis.json",
            output_root=output_root,
            render_pdf=False,
        )


def test_seeded_existing_candidate_is_rejected_on_rerender(tmp_path):
    repo_root, subject_root, output_root, source_card_dir, source = _source_fixture(tmp_path)
    seeded_json_path = output_root / "W01L1" / "scaffolding" / "source-1" / printout_engine.LEGACY_PRINTOUT_JSON_NAME
    _write_json(
        seeded_json_path,
        {
            "schema_version": printout_engine.SCHEMA_VERSION,
            "generator": {"provider": "seeded-from-baseline"},
            "variant": {"seeded_from_baseline": True, "render_exam_bridge": False},
            "source": {"title": "Phenomenology source", "lecture_key": "W01L1"},
            "printouts": _valid_scaffold_response(),
        },
    )

    with pytest.raises(printout_engine.PrintoutError, match="seeded and invalid for reuse"):
        printout_engine.build_printout_for_source(
            repo_root=repo_root,
            subject_root=subject_root,
            source=source,
            source_card_dir=source_card_dir,
            revised_lecture_substrate_dir=repo_root / "source_intelligence" / "revised_lecture_substrates",
            course_synthesis_path=repo_root / "source_intelligence" / "course_synthesis.json",
            output_root=output_root,
            render_pdf=False,
            rerender_existing=True,
        )


def test_pdf_wrapper_adds_margin_metadata():
    markdown = (
        "# Reading Guide\n\n"
        "**Kilde:** Grundbog kapitel 01 - Introduktion til personlighedspsykologi\n\n"
        "**Forelæsning:** W01L1\n\n"
        "Kort tekst."
    )

    metadata = printout_engine._pdf_margin_metadata(markdown)
    assert metadata["title"] == "Reading Guide"
    assert metadata["lecture_key"] == "W01L1"
    assert (
        metadata["meta_text"]
        == "forelæsning 1, uge 1 | grundbog kapitel 01 - introduktion til personlighedspsykologi | reading guide"
    )

    wrapped = printout_engine._pdf_wrapped_markdown(markdown, total_pages=7)
    assert wrapped.startswith("---\nheader-includes:")
    assert r"\usepackage{fancyhdr}" in wrapped
    assert rf"\AtBeginDocument{{\linespread{{{printout_engine.PDF_BODY_LINE_SPREAD}}}\selectfont}}" in wrapped
    assert r"\newcommand{\printoutneedspace}[1]{%" in wrapped
    assert r"\renewcommand{\section}{\printoutneedspace{6\baselineskip}\@ifstar{\printoutoldsection*}{\printoutoldsection}}" in wrapped
    assert r"\fancyhead[L]{\printoutmarginpage}" in wrapped
    assert r"\fancyfoot[R]{\printoutmarginpage}" in wrapped
    assert r"\newcommand{\printoutmarginpage}{\printoutmarginfont side \thepage/7}" in wrapped
    assert (
        "forelæsning 1, uge 1 | grundbog kapitel 01 - introduktion til personlighedspsykologi | reading guide"
        in wrapped
    )


def test_pdf_wrapper_uses_standard_line_spread_for_consolidation_sheet():
    markdown = (
        "# Consolidation Sheet\n\n"
        "**Kilde:** Grundbog kapitel 01 - Introduktion til personlighedspsykologi\n\n"
        "**Forelæsning:** W01L1\n\n"
        "Kort tekst."
    )

    wrapped = printout_engine._pdf_wrapped_markdown(markdown, total_pages=2)

    assert rf"\AtBeginDocument{{\linespread{{{printout_engine.PDF_BODY_LINE_SPREAD}}}\selectfont}}" in wrapped
    assert printout_engine.PDF_CONSOLIDATION_FILL_BODY_LINE_SPREAD not in wrapped


def test_consolidation_applies_double_line_spread_only_to_fill_section():
    artifact = {
        "source": {"title": "Phenomenology source", "lecture_key": "W01L1"},
        "variant": {"render_completion_markers": True},
    }
    payload = _valid_scaffold_response()

    markdown = printout_engine.render_consolidation_markdown(
        artifact,
        payload["consolidation_sheet"],
    )

    fill_spread = rf"\begingroup\linespread{{{printout_engine.PDF_CONSOLIDATION_FILL_BODY_LINE_SPREAD}}}\selectfont"
    assert fill_spread in markdown
    assert r"\endgroup" in markdown
    assert markdown.index(fill_spread) < markdown.index(r"\endgroup") < markdown.index("**Tegn**")
    assert printout_engine.PDF_CONSOLIDATION_FILL_BODY_LINE_SPREAD not in markdown.split("**Tegn**", 1)[1]


def test_consolidation_uses_fill_for_last_diagram_page():
    artifact = {
        "source": {"title": "Phenomenology source", "lecture_key": "W01L1"},
        "variant": {"render_completion_markers": True},
    }
    payload = _valid_scaffold_response()

    single_diagram_markdown = printout_engine.render_consolidation_markdown(
        artifact,
        payload["consolidation_sheet"],
    )
    assert "\\vspace*{\\fill}" in single_diagram_markdown
    assert "\\hrule" not in single_diagram_markdown
    assert "---" not in single_diagram_markdown
    assert "**Tegn**" in single_diagram_markdown
    assert "**Diagram 1.**" in single_diagram_markdown

    payload["consolidation_sheet"]["diagram_tasks"] = [
        {
            "number": "1",
            "task": "Tegn første model.",
            "required_elements": ["a", "b"],
            "blank_space_hint": "Lav fire felter.",
        },
        {
            "number": "2",
            "task": "Tegn anden model.",
            "required_elements": ["c", "d"],
            "blank_space_hint": "Lav et gitter.",
        },
    ]
    two_diagram_markdown = printout_engine.render_consolidation_markdown(
        artifact,
        payload["consolidation_sheet"],
    )
    assert "\\newpage" in two_diagram_markdown
    assert "\\vspace*{\\fill}" in two_diagram_markdown
    assert "\\hrule" not in two_diagram_markdown
    assert "---" not in two_diagram_markdown
    assert two_diagram_markdown.count("**Tegn**") == 2
    assert two_diagram_markdown.count("\\newpage") == 2
    assert two_diagram_markdown.count("\\vspace*{\\fill}") == 2
    assert two_diagram_markdown.index(r"\endgroup") < two_diagram_markdown.index(r"\newpage") < two_diagram_markdown.index("**Tegn**")
    assert "**Diagram 2.** Tegn anden model." in two_diagram_markdown
    assert "\n- a" in two_diagram_markdown
    assert (
        printout_engine._vspace_cm(printout_engine._spacing_cm("diagram_dedicated_page_floor"))
        in two_diagram_markdown
    )


def test_printout_length_budget_varies_with_source_length_and_complexity():
    short_budget = printout_engine.build_printout_length_budget(
        source={"length_band": "short", "page_count": 5},
        source_card={"analysis": {"key_concepts": ["a"], "central_claims": ["b"]}},
    )
    long_budget = printout_engine.build_printout_length_budget(
        source={"length_band": "long", "page_count": 34},
        source_card={
            "analysis": {
                "key_concepts": list("abcdefgh"),
                "central_claims": ["c1", "c2", "c3", "c4", "c5", "c6"],
                "distinctions": ["d1", "d2", "d3", "d4", "d5", "d6"],
                "likely_misunderstandings": ["m1", "m2", "m3", "m4", "m5"],
                "grounding_notes": ["g1", "g2", "g3", "g4"],
            }
        },
    )

    assert short_budget["profile"] == "short"
    assert long_budget["profile"] == "long"
    assert (
        short_budget["active_reading"]["solve_steps"]["max"]
        < long_budget["active_reading"]["solve_steps"]["max"]
    )
    assert (
        short_budget["consolidation_sheet"]["fill_in_sentences"]["max"]
        < long_budget["consolidation_sheet"]["fill_in_sentences"]["max"]
    )
    assert (
        short_budget["abridged_reader"]["sections"]["max"]
        < long_budget["abridged_reader"]["sections"]["max"]
    )


def test_active_reading_moves_large_final_synthesis_to_new_page():
    artifact = {
        "source": {"title": "Phenomenology source", "lecture_key": "W01L1"},
        "variant": {"render_completion_markers": True},
    }
    payload = _valid_scaffold_response()
    payload["active_reading"]["solve_steps"] = [
        {
            "number": "1",
            "subproblem_ref": "Delproblem 1",
            "prompt": "Find det centrale begreb som gør bevidsthed rettet mod noget.",
            "task_type": "term",
            "abridged_reader_location": "Abridged reader sektion 1",
            "answer_shape": "1-2 ord",
            "blank_lines": 1,
            "done_signal": "Stop når begrebet står på arket.",
        },
        {
            "number": "2",
            "subproblem_ref": "Delproblem 2",
            "prompt": "Forklar kort, hvilken misforståelse teksten afviser.",
            "task_type": "short_paragraph",
            "abridged_reader_location": "Abridged reader sektion 2",
            "answer_shape": "2-3 sætninger",
            "blank_lines": 2,
            "done_signal": "Stop når du har afgrænset misforståelsen.",
        },
        {
            "number": "3",
            "subproblem_ref": "Delproblem 3",
            "prompt": "Vælg side i spændingen og begrund kort.",
            "task_type": "decision",
            "abridged_reader_location": "Abridged reader sektion 3",
            "answer_shape": "1-2 sætninger",
            "blank_lines": 2,
            "done_signal": "Stop når du har valgt side og begrundet kort.",
        },
        {
            "number": "4",
            "subproblem_ref": "Delproblem 4",
            "prompt": "Skriv nøgleordet for metodevalget.",
            "task_type": "term",
            "abridged_reader_location": "Abridged reader sektion 4",
            "answer_shape": "1-2 ord",
            "blank_lines": 1,
            "done_signal": "Stop når nøgleordet står på arket.",
        },
        {
            "number": "5",
            "subproblem_ref": "Hovedproblem",
            "prompt": "Brug dine delsvar til at besvare hovedproblemet kort.",
            "task_type": "short_paragraph",
            "abridged_reader_location": "Abridged reader sektion 1-4",
            "answer_shape": "5-7 linjer",
            "blank_lines": 5,
            "done_signal": "Stop når du har et samlet svar.",
        },
    ]
    markdown = printout_engine.render_active_reading_markdown(artifact, payload["active_reading"])
    assert "\\newpage" not in markdown
    assert "\\vspace*{\\fill}" not in markdown
    assert r"\printoutneedspace{13\baselineskip}" in markdown
    assert markdown.count("\\noindent\\rule{\\linewidth}{0.4pt}") >= 12


def test_normalize_scaffold_payload_repairs_source_reference_in_active_reading():
    payload = _valid_scaffold_response()
    payload["active_reading"]["solve_steps"][0]["abridged_reader_location"] = "S. 67 i originalteksten"

    normalized = printout_engine.normalize_scaffold_payload(payload)

    assert normalized["active_reading"]["solve_steps"][0]["abridged_reader_location"].startswith("Abridged reader sektion")
    printout_engine.validate_printout_payload(normalized)


def test_normalize_scaffold_payload_repairs_source_reference_in_consolidation():
    payload = _valid_scaffold_response()
    payload["consolidation_sheet"]["fill_in_sentences"][0]["where_to_look"] = "S. 70 i originalen"

    normalized = printout_engine.normalize_scaffold_payload(payload)

    assert normalized["consolidation_sheet"]["fill_in_sentences"][0]["where_to_look"].startswith(
        "Abridged reader sektion"
    )
    printout_engine.validate_printout_payload(normalized)


def test_normalize_scaffold_payload_repairs_too_short_opening_passages():
    payload = _valid_scaffold_response()
    payload["reading_guide"]["opening_passages"] = payload["reading_guide"]["opening_passages"][:1]

    normalized = printout_engine.normalize_scaffold_payload(payload)

    assert len(normalized["reading_guide"]["opening_passages"]) >= 2
    printout_engine.validate_printout_payload(normalized)


def test_call_json_generator_retries_transient_generation_error(monkeypatch):
    attempts = {"count": 0}
    sleeps: list[int] = []

    def fake_generate_json(**kwargs):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise printout_engine.GeminiPreprocessingGenerationError(
                "Gemini preprocessing failed: [Errno 54] Connection reset by peer"
            )
        return {"ok": True}

    monkeypatch.setattr(printout_engine, "generate_json", fake_generate_json)
    monkeypatch.setattr(printout_engine.time, "sleep", lambda seconds: sleeps.append(seconds))

    result = printout_engine.call_json_generator(
        backend=object(),  # unused by fake_generate_json
        json_generator=None,
        model="gemini-test",
        system_instruction="SYSTEM",
        user_prompt="PROMPT",
        source_paths=[],
        max_output_tokens=512,
        response_json_schema=None,
    )

    assert result == {"ok": True}
    assert attempts["count"] == 3
    assert sleeps == [5, 15]


def test_call_json_generator_does_not_retry_non_transient_generation_error(monkeypatch):
    attempts = {"count": 0}
    sleeps: list[int] = []

    def fake_generate_json(**kwargs):
        attempts["count"] += 1
        raise printout_engine.GeminiPreprocessingGenerationError(
            "Gemini response was not valid JSON: unexpected character"
        )

    monkeypatch.setattr(printout_engine, "generate_json", fake_generate_json)
    monkeypatch.setattr(printout_engine.time, "sleep", lambda seconds: sleeps.append(seconds))

    with pytest.raises(printout_engine.GeminiPreprocessingGenerationError, match="not valid JSON"):
        printout_engine.call_json_generator(
            backend=object(),
            json_generator=None,
            model="gemini-test",
            system_instruction="SYSTEM",
            user_prompt="PROMPT",
            source_paths=[],
            max_output_tokens=512,
            response_json_schema=None,
        )

    assert attempts["count"] == 1
    assert sleeps == []


def test_normalize_scaffold_payload_migrates_legacy_abridged_checks():
    payload = _valid_scaffold_response()
    payload["reading_guide"].pop("main_problem", None)
    payload["reading_guide"].pop("subproblems", None)
    payload["reading_guide"].pop("teaser_paragraphs", None)
    payload["active_reading"]["abridged_checks"] = [
        {
            "number": "1",
            "question": "Hvad hedder nøglebegrebet",
            "abridged_reader_location": "Abridged reader sektion 1",
            "answer_shape": "et begreb",
            "done_signal": "Stop når du har skrevet begrebet.",
        }
    ]
    payload["active_reading"].pop("solve_steps", None)

    normalized = printout_engine.normalize_scaffold_payload(payload, legacy_compat=True)

    assert normalized["reading_guide"]["main_problem"]
    assert normalized["reading_guide"]["subproblems"]
    assert normalized["reading_guide"]["teaser_paragraphs"]
    assert len(normalized["active_reading"]["solve_steps"]) >= 4
    assert normalized["active_reading"]["solve_steps"][-1]["subproblem_ref"] == "Hovedproblem"
    assert any(item["task_type"] == "short_paragraph" for item in normalized["active_reading"]["solve_steps"])
    assert not any(
        "Find det centrale svar på dette spørgsmål" in item["prompt"]
        for item in normalized["active_reading"]["solve_steps"]
    )
    assert normalized["active_reading"]["solve_steps"][-1]["prompt"].startswith(
        "Brug dine delsvar til at samle tekstens hovedbevægelse kort"
    )


def test_normalize_scaffold_payload_repairs_empty_no_quote_anchor_needed():
    payload = _valid_scaffold_response()
    payload["abridged_reader"]["sections"][1]["quote_anchors"] = []
    payload["abridged_reader"]["sections"][1]["no_quote_anchor_needed"] = ""

    normalized = printout_engine.normalize_scaffold_payload(payload)

    assert (
        normalized["abridged_reader"]["sections"][1]["no_quote_anchor_needed"]
        == "Sektionen bæres af forklaringen frem for en kort citerbar formulering."
    )
    printout_engine.validate_printout_payload(normalized)


def test_normalize_scaffold_payload_recovers_unknown_task_type_alias():
    payload = _valid_scaffold_response()
    payload["active_reading"]["solve_steps"][0]["task_type"] = "short_answer"
    payload["active_reading"]["solve_steps"][0]["prompt"] = "Hvilket begreb er tekstens nøgleord?"
    payload["active_reading"]["solve_steps"][0]["answer_shape"] = "1-2 ord"

    normalized = printout_engine.normalize_scaffold_payload(payload)

    assert normalized["active_reading"]["solve_steps"][0]["task_type"] == "term"
    printout_engine.validate_printout_payload(normalized)


def test_normalize_scaffold_payload_rebalances_broad_active_steps():
    payload = _valid_scaffold_response()
    payload["active_reading"]["solve_steps"][0]["prompt"] = "Diskuter hvordan teksten forstår intentionalitet."
    payload["active_reading"]["solve_steps"][0]["task_type"] = "short_paragraph"
    payload["active_reading"]["solve_steps"][0]["answer_shape"] = "3-4 sætninger"
    payload["active_reading"]["solve_steps"][0]["blank_lines"] = 4

    normalized = printout_engine.normalize_scaffold_payload(payload)

    assert normalized["active_reading"]["solve_steps"][0]["prompt"].startswith(("Skriv", "Vælg", "Forklar", "Afgør"))
    assert "Diskuter" not in normalized["active_reading"]["solve_steps"][0]["prompt"]
    printout_engine.validate_printout_payload(normalized)


def test_normalize_scaffold_payload_derives_active_reading_from_guide_and_reader():
    payload = _valid_scaffold_response()
    payload["active_reading"] = {"title": "Ligegyldigt", "instructions": "Ligegyldigt", "solve_steps": []}

    normalized = printout_engine.normalize_scaffold_payload(payload)

    assert normalized["active_reading"]["title"] == "Active Reading"
    assert len(normalized["active_reading"]["solve_steps"]) >= 4
    assert normalized["active_reading"]["solve_steps"][-1]["subproblem_ref"] == "Hovedproblem"
    printout_engine.validate_printout_payload(normalized)


def test_normalize_scaffold_payload_uses_subproblem_questions_when_local_problem_is_goal_phrase():
    payload = _valid_scaffold_response()
    payload["reading_guide"]["subproblems"][0]["question"] = "Hvad er det grundlæggende problem med intentionalitet?"
    payload["reading_guide"]["subproblems"][0]["answer_form"] = "1-2 sætninger"
    payload["abridged_reader"]["sections"][0]["local_problem"] = "At forstå intentionalitetens grundproblem?"
    payload["active_reading"] = {"title": "Ligegyldigt", "instructions": "Ligegyldigt", "solve_steps": []}

    normalized = printout_engine.normalize_scaffold_payload(payload)

    assert normalized["active_reading"]["solve_steps"][0]["prompt"].endswith(
        "Hvad er det grundlæggende problem med intentionalitet?"
    )
    assert normalized["active_reading"]["solve_steps"][0]["subproblem_ref"] == "Delproblem 1"
    assert normalized["active_reading"]["solve_steps"][0]["task_type"] == "short_paragraph"
    assert normalized["active_reading"]["solve_steps"][0]["blank_lines"] == 2


def test_normalize_scaffold_payload_treats_brief_explanations_as_compact_paragraphs():
    payload = _valid_scaffold_response()
    payload["reading_guide"]["subproblems"][2]["answer_form"] = "En kort begrebsforklaring"
    payload["abridged_reader"]["sections"][2]["local_problem"] = "Hvad er intentionalitet?"
    payload["active_reading"] = {"title": "Ligegyldigt", "instructions": "Ligegyldigt", "solve_steps": []}

    normalized = printout_engine.normalize_scaffold_payload(payload)

    step = normalized["active_reading"]["solve_steps"][2]
    assert step["task_type"] == "short_paragraph"
    assert step["blank_lines"] == 2


def test_normalize_scaffold_payload_keeps_plural_mechanism_questions_as_paragraph_work():
    payload = _valid_scaffold_response()
    payload["reading_guide"]["subproblems"][1]["question"] = "Hvilke antagelser gør teorien om udvikling?"
    payload["reading_guide"]["subproblems"][1]["answer_form"] = "1-2 mekanismer"
    payload["abridged_reader"]["sections"][1]["local_problem"] = "Hvilke antagelser gør teorien om udvikling?"
    payload["active_reading"] = {"title": "Ligegyldigt", "instructions": "Ligegyldigt", "solve_steps": []}

    normalized = printout_engine.normalize_scaffold_payload(payload)

    step = normalized["active_reading"]["solve_steps"][1]
    assert step["task_type"] == "short_paragraph"
    assert step["blank_lines"] == 3
    assert step["prompt"].startswith("Skriv et kort, sammenhængende svar på dette:")


def test_normalize_scaffold_payload_rephrases_infinitive_main_problem_for_synthesis():
    payload = _valid_scaffold_response()
    payload["reading_guide"]["main_problem"] = "At etablere en fast komparativ ramme for at forstå feltets uenigheder"
    payload["active_reading"] = {"title": "Ligegyldigt", "instructions": "Ligegyldigt", "solve_steps": []}

    normalized = printout_engine.normalize_scaffold_payload(payload)

    final_step = normalized["active_reading"]["solve_steps"][-1]
    assert final_step["subproblem_ref"] == "Hovedproblem"
    assert "Hvordan hjælper teksten med at etablere en fast komparativ ramme" in final_step["prompt"]
    assert final_step["prompt"].endswith("?")


def test_normalize_scaffold_payload_repairs_sparse_diagram_required_elements():
    payload = _valid_scaffold_response()
    payload["consolidation_sheet"]["diagram_tasks"][0]["task"] = "Tegn en 2x3 matrix over forskningstilgange."
    payload["consolidation_sheet"]["diagram_tasks"][0]["required_elements"] = ["2 rækker"]

    normalized = printout_engine.normalize_scaffold_payload(payload)

    assert len(normalized["consolidation_sheet"]["diagram_tasks"][0]["required_elements"]) >= 2
    printout_engine.validate_printout_payload(normalized)


def test_render_active_reading_markdown_keeps_steps_together_without_forced_final_page():
    artifact = {
        "source": {"title": "Phenomenology source", "lecture_key": "W01L1"},
        "variant": {"render_completion_markers": True},
    }
    payload = _valid_scaffold_response()
    payload["active_reading"] = {
        "title": "Ligegyldigt",
        "instructions": "Ligegyldigt",
        "solve_steps": [
            {
                "number": "1",
                "subproblem_ref": "Delproblem 1",
                "prompt": "Forklar kort intentionalitetens hovedpointe.",
                "task_type": "short_paragraph",
                "abridged_reader_location": "Abridged reader sektion 1",
                "answer_shape": "1-2 sætninger",
                "blank_lines": 2,
                "done_signal": "Stop når du har skrevet et kort svar.",
            },
            {
                "number": "2",
                "subproblem_ref": "Hovedproblem",
                "prompt": "Brug dine delsvar til at besvare hovedproblemet kort: Hvordan hænger intentionalitet og livsverden sammen.",
                "task_type": "short_paragraph",
                "abridged_reader_location": "Abridged reader sektion 1-3",
                "answer_shape": "4-5 sætninger",
                "blank_lines": 4,
                "done_signal": "Stop når du har skrevet et samlet svar.",
            },
        ],
    }

    markdown = printout_engine.render_active_reading_markdown(artifact, payload["active_reading"])

    assert r"\printoutneedspace{11\baselineskip}" in markdown
    assert r"\newpage" not in markdown
    assert "\\vspace*{\\fill}" not in markdown


def test_render_active_reading_term_step_reserves_space_for_prompt_and_lines():
    artifact = {
        "source": {"title": "Freud source", "lecture_key": "W05L2"},
        "variant": {"render_completion_markers": True},
    }
    payload = {
        "solve_steps": [
            {
                "number": "4",
                "subproblem_ref": "Delproblem 4",
                "prompt": "Skriv det korte svar på spørgsmålet: Hvilken konsekvens fik forførelsesteoriens fald for forståelsen af subjektet?",
                "task_type": "term",
                "abridged_reader_location": "Abridged reader sektion 4",
                "answer_shape": "1-3 ord",
                "blank_lines": 1,
                "done_signal": "Stop når du har skrevet det korte svar.",
            }
        ]
    }

    markdown = printout_engine.render_active_reading_markdown(artifact, payload)

    assert r"\printoutneedspace{6\baselineskip}" in markdown


def test_render_consolidation_markdown_stacks_long_fill_in_blank_away_from_right_margin():
    artifact = {
        "source": {"title": "Freud source", "lecture_key": "W05L2"},
        "variant": {"render_completion_markers": True},
    }
    consolidation = {
        "overview": [],
        "fill_in_sentences": [
            {
                "number": "1",
                "sentence": (
                    "Freuds motivationspsykologi bygger på en __________ synsvinkel, "
                    "hvor indre energikvantiteter udøver et konstant tryk."
                ),
            }
        ],
        "diagram_tasks": [],
    }

    markdown = printout_engine.render_consolidation_markdown(artifact, consolidation)

    assert "**1.** Freuds motivationspsykologi bygger på en" in markdown
    assert re.search(
        r"\n\n\\noindent\\underline\{\\hspace\{0\.\d+\\linewidth\}\}\n\nsynsvinkel, hvor indre energikvantiteter udøver et konstant tryk\.",
        markdown,
    )
    assert "på en ________________________________ synsvinkel" not in markdown


def test_render_consolidation_markdown_keeps_punctuation_attached_to_stacked_blank():
    artifact = {
        "source": {"title": "Mitchell source", "lecture_key": "W10L1"},
        "variant": {"render_completion_markers": True},
    }
    consolidation = {
        "overview": [],
        "fill_in_sentences": [
            {
                "number": "2",
                "sentence": (
                    "Ifølge Mitchell holdes den ubevidste kønsforskel på plads af den universelle "
                    "__________, som udspringer af forbuddet mod incest og drab."
                ),
            }
        ],
        "diagram_tasks": [],
    }

    markdown = printout_engine.render_consolidation_markdown(artifact, consolidation)

    assert re.search(
        r"\\noindent\\underline\{\\hspace\{0\.32\\linewidth\}\}, som udspringer af forbuddet mod incest og drab\.",
        markdown,
    )
    assert "\n\n,\n\n" not in markdown


def test_render_consolidation_markdown_keeps_terminal_punctuation_inline_when_blank_ends_sentence():
    artifact = {
        "source": {"title": "Mitchell source", "lecture_key": "W10L1"},
        "variant": {"render_completion_markers": True},
    }
    consolidation = {
        "overview": [],
        "fill_in_sentences": [
            {
                "number": "1",
                "sentence": (
                    "Mitchell skelner mellem det socialt foranderlige ‘gender’ og den mere ufravigelige, "
                    "strukturelle __________."
                ),
            }
        ],
        "diagram_tasks": [],
    }

    markdown = printout_engine.render_consolidation_markdown(artifact, consolidation)

    assert re.search(r"strukturelle _{30,}\.", markdown)
    assert r"\noindent\underline" not in markdown


def test_build_printout_commits_json_only_after_render_success(tmp_path, monkeypatch):
    repo_root, subject_root, output_root, source_card_dir, source = _source_fixture(tmp_path)

    def fake_json_generator(**kwargs):
        return _valid_scaffold_response()

    def fail_render(**kwargs):
        raise printout_engine.PrintoutError("render failed")

    monkeypatch.setattr(printout_engine, "render_printout_files", fail_render)

    with pytest.raises(printout_engine.PrintoutError, match="render failed"):
        printout_engine.build_printout_for_source(
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

    expected_json_path = printout_engine.artifact_json_path_for_source_id(
        output_root,
        source_id="source-1",
        provider="gemini",
        model=printout_engine.DEFAULT_GEMINI_PREPROCESSING_MODEL,
    )
    assert not expected_json_path.exists()


def test_build_printout_rerenders_existing_json_when_expected_pdfs_are_missing(tmp_path, monkeypatch):
    repo_root, subject_root, output_root, source_card_dir, source = _source_fixture(tmp_path)

    def fake_json_generator(**kwargs):
        return _valid_scaffold_response()

    first = printout_engine.build_printout_for_source(
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
    assert Path(first["json_path"]).exists()

    generation_calls = []
    render_calls = []

    def fail_if_generation_is_called(**kwargs):
        generation_calls.append(kwargs)
        raise AssertionError("generation should not be called for existing JSON rerender")

    def fake_render_printout_files(*, artifact, output_dir, render_pdf=True):
        render_calls.append(render_pdf)
        pdf_paths = []
        for stem in sorted(printout_engine._expected_pdf_stems_for_artifact(artifact)):
            pdf_path = output_dir / printout_engine._review_pdf_filename(artifact, stem)
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            pdf_path.write_bytes(b"%PDF-1.4 fake")
            pdf_paths.append(str(pdf_path))
        return {"markdown_paths": [], "pdf_paths": pdf_paths}

    monkeypatch.setattr(printout_engine, "render_printout_files", fake_render_printout_files)

    second = printout_engine.build_printout_for_source(
        repo_root=repo_root,
        subject_root=subject_root,
        source=source,
        source_card_dir=source_card_dir,
        revised_lecture_substrate_dir=repo_root / "source_intelligence" / "revised_lecture_substrates",
        course_synthesis_path=repo_root / "source_intelligence" / "course_synthesis.json",
        output_root=output_root,
        json_generator=fail_if_generation_is_called,
        render_pdf=True,
    )

    assert second["status"] == "rerendered_existing"
    assert not generation_calls
    assert render_calls == [True]
    assert len(second["pdf_paths"]) == 5


def test_provider_model_scoped_artifacts_can_coexist_for_same_source(tmp_path):
    repo_root, subject_root, output_root, source_card_dir, source = _source_fixture(tmp_path)

    def fake_json_generator(**kwargs):
        return _valid_scaffold_response()

    gemini = printout_engine.build_printout_for_source(
        repo_root=repo_root,
        subject_root=subject_root,
        source=source,
        source_card_dir=source_card_dir,
        revised_lecture_substrate_dir=repo_root / "source_intelligence" / "revised_lecture_substrates",
        course_synthesis_path=repo_root / "source_intelligence" / "course_synthesis.json",
        output_root=output_root,
        json_generator=fake_json_generator,
        render_pdf=False,
        generation_provider="gemini",
        model="gemini-3.1-pro-preview",
        variant_metadata={"mode": "evaluation_sandbox"},
        output_layout=printout_engine.OUTPUT_LAYOUT_REVIEW,
    )
    openai = printout_engine.build_printout_for_source(
        repo_root=repo_root,
        subject_root=subject_root,
        source=source,
        source_card_dir=source_card_dir,
        revised_lecture_substrate_dir=repo_root / "source_intelligence" / "revised_lecture_substrates",
        course_synthesis_path=repo_root / "source_intelligence" / "course_synthesis.json",
        output_root=output_root,
        json_generator=fake_json_generator,
        render_pdf=False,
        generation_provider="openai",
        model="gpt-5.5",
        variant_metadata={"mode": "evaluation_sandbox"},
        output_layout=printout_engine.OUTPUT_LAYOUT_REVIEW,
    )

    assert Path(gemini["json_path"]).exists()
    assert Path(openai["json_path"]).exists()
    assert gemini["json_path"] != openai["json_path"]
    assert ".scaffolding/artifacts/gemini-gemini-3_1-pro-preview/source-1/" in gemini["json_path"]
    assert ".scaffolding/artifacts/openai-gpt-5_5/source-1/" in openai["json_path"]
