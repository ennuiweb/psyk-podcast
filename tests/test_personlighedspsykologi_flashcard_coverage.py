import json

import pytest

from notebooklm_queue import personlighedspsykologi_flashcard_coverage as coverage


def _write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _matrix():
    return {
        "subject_slug": "personlighedspsykologi",
        "rows": [
            {
                "theory_id": "test_theory",
                "label": "Testteori",
                "course_summary": "Testteorien forklarer personen som situeret aktør.",
                "model_of_person": "Personen forstås som situeret aktør.",
                "personality_or_subjectivity_model": "Subjektivitet formes i praksis.",
                "method_evidence_style": "Kvalitative analyser af praksis.",
                "central_concepts": ["situering", "praksis"],
                "orientation_points": {
                    "agency": {"placement": "aktiv agency", "summary": "Aktøren handler med muligheder."}
                },
                "strengths": ["Synliggør praksis"],
                "limitations": ["Kan undervurdere biologi"],
                "likely_misunderstandings": ["At gøre teorien rent individualistisk"],
                "comparison_targets": [
                    {
                        "target_theory_id": "other_theory",
                        "relation": "contrast",
                        "rationale": "Kontrast til en mere biologisk forklaring.",
                    }
                ],
                "source_note_basis": [
                    {
                        "note_id": "source_a",
                        "basis_status": "primary_student_note",
                        "summary": "Source A fremhæver situeret agency og praksis.",
                    }
                ],
            }
        ],
    }


def _notes():
    return {
        "subject_slug": "personlighedspsykologi",
        "notes": [
            {
                "note_id": "source_a",
                "label": "Source A",
                "matrix_policy": "primary_basis",
            }
        ],
    }


def _deck(cards):
    return {
        "version": 1,
        "artifact_type": "freudd_flashcards",
        "subject_slug": "personlighedspsykologi",
        "deck_slug": "notebooklm-fuld-matrix-personlighedspsykologi",
        "title": "Deck",
        "card_count": len(cards),
        "categories": [],
        "cards": cards,
    }


def _card(card_id, category_slug, front, back, tags=None):
    return {
        "card_id": card_id,
        "front_text": front,
        "back_text": back,
        "back_html_sanitized": f"<div>{back}</div>",
        "category_slug": category_slug,
        "category_title": category_slug,
        "tags": tags or ["test_theory"],
        "content_sha256": card_id,
    }


def test_build_coverage_report_marks_covered_and_missing_units(tmp_path):
    matrix_path = tmp_path / "matrix.json"
    deck_path = tmp_path / "deck.json"
    notes_index_path = tmp_path / "notes-index.json"
    notes_registry_path = tmp_path / "notes-registry.json"
    _write_json(matrix_path, _matrix())
    _write_json(notes_index_path, _notes())
    _write_json(notes_registry_path, _notes())
    _write_json(
        deck_path,
        _deck(
            [
                _card(
                    "card-model",
                    "personbegreb",
                    "Hvordan forstår testteorien personen?",
                    "Personen er en situeret aktør, og subjektivitet formes i praksis.",
                ),
                _card(
                    "card-method",
                    "metode-og-evidens",
                    "Hvilken metode bruger testteorien?",
                    "Den bruger kvalitative analyser af praksis.",
                ),
                _card(
                    "card-source",
                    "orienteringspunkter",
                    "Hvordan viser testteorien agency?",
                    "Source A peger på situeret agency og praksis som handlemulighed.",
                ),
            ]
        ),
    )

    report = coverage.build_coverage_report(
        repo_root=tmp_path,
        matrix_path=matrix_path,
        deck_path=deck_path,
        source_notes_index_path=notes_index_path,
        source_notes_registry_path=notes_registry_path,
        generated_at="2026-05-26T00:00:00Z",
    )

    row = report["rows"][0]
    units = {unit["unit_id"]: unit for unit in row["units"]}
    assert report["summary"]["row_count"] == 1
    assert units["test_theory:method_evidence_style"]["status"] in {"strong", "partial"}
    assert units["test_theory:comparison_targets:other_theory"]["status"] == "missing"
    assert report["source_notes"][0]["note_id"] == "source_a"
    assert report["source_notes"][0]["status"] in {"strong", "partial"}


def test_build_coverage_report_rejects_cards_without_theory_tags(tmp_path):
    matrix_path = tmp_path / "matrix.json"
    deck_path = tmp_path / "deck.json"
    notes_index_path = tmp_path / "notes-index.json"
    notes_registry_path = tmp_path / "notes-registry.json"
    _write_json(matrix_path, _matrix())
    _write_json(notes_index_path, _notes())
    _write_json(notes_registry_path, _notes())
    _write_json(
        deck_path,
        _deck([_card("card-no-theory", "personbegreb", "Q?", "A", tags=["not-a-theory"])]),
    )

    with pytest.raises(coverage.FlashcardCoverageError, match="without matrix theory tags"):
        coverage.build_coverage_report(
            repo_root=tmp_path,
            matrix_path=matrix_path,
            deck_path=deck_path,
            source_notes_index_path=notes_index_path,
            source_notes_registry_path=notes_registry_path,
        )
