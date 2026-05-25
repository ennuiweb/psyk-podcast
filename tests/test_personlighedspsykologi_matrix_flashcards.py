from __future__ import annotations

import copy

import pytest

from notebooklm_queue import personlighedspsykologi_matrix_flashcards as flashcards
from notebooklm_queue import personlighedspsykologi_student_synthesis as synthesis


def _orientation_points():
    return {
        "essence_context": {
            "placement": "mixed",
            "summary": "The theory treats person and context as mutually relevant.",
        },
        "determination": {
            "placement": "moderate",
            "summary": "The person is shaped, but not mechanically fixed.",
        },
        "agency": {
            "placement": "situated agency",
            "summary": "Action is possible inside concrete conditions.",
        },
        "historicity": {
            "placement": "ontogenetic and sociogenetic",
            "summary": "Life course and social history matter.",
        },
    }


def _row(theory_id: str, label: str, *, target: str | None = None, warning: str | None = None):
    comparisons = (
        [
            {
                "target_theory_id": target,
                "relation": "contrasts_with",
                "rationale": "It makes a useful exam contrast.",
            }
        ]
        if target
        else []
    )
    return {
        "theory_id": theory_id,
        "label": label,
        "aliases": [label],
        "lecture_keys": ["W01L1"],
        "course_role": "Gives the course a testable theory frame.",
        "course_summary": f"{label} explains personality through a compact course frame.",
        "student_note_labels": ["Theory sheet"],
        "model_of_person": f"{label} has a specific model of the person.",
        "personality_or_subjectivity_model": f"{label} has a specific model of subjectivity.",
        "method_evidence_style": "Uses a recognizable method and evidence style.",
        "main_thinkers": ["Thinker"],
        "central_concepts": ["concept one", "concept two"],
        "orientation_points": _orientation_points(),
        "strengths": ["Makes one thing visible."],
        "limitations": ["Hides one thing."],
        "comparison_targets": comparisons,
        "likely_misunderstandings": ["Reducing the theory to a slogan."],
        "student_synthesis_notes": "Use this row as a compact exam comparison frame.",
        "source_note_basis": [
            {
                "note_id": "note_1",
                "basis_status": "primary_student_note",
                "summary": "The source note supports the row's comparison frame.",
            }
        ],
        "source_grounding": {
            "course_theory_map_ids": [theory_id],
            "concept_node_ids": [f"{theory_id}_concept"],
            "distinction_ids": [],
            "representative_source_ids": ["source-1"],
            "representative_evidence_origins": ["reading_grounded"],
        },
        "validation_status": "validated",
        "warnings": [warning] if warning else [],
    }


def _matrix():
    rows = [
        _row("theory_a", "Theory A", target="theory_b"),
        _row("theory_b", "Theory B", target="theory_a"),
    ]
    return {
        "artifact_type": "exam_theory_matrix",
        "schema_version": synthesis.STUDENT_SYNTHESIS_SCHEMA_VERSION,
        "subject_slug": "personlighedspsykologi",
        "generated_at": "2026-05-25T00:00:00Z",
        "authority": "student_exam_synthesis",
        "build": {
            "builder": "scripts/build_personlighedspsykologi_exam_theory_matrix.py",
            "model": "deterministic-curated-student-synthesis",
            "prompt_version": "test",
        },
        "provenance": {
            "input_source_ids": ["note_1"],
            "source_notes_signature": "abc",
            "dependency_hashes": {"seed": "123"},
        },
        "orientation_points": [
            {"orientation_point_id": point_id, "label": point_id, "question": "Question?"}
            for point_id in synthesis.ORIENTATION_POINT_IDS
        ],
        "rows": rows,
        "stats": {"row_count": len(rows)},
        "warnings": [],
    }


def test_build_flashcard_deck_creates_deterministic_freudd_artifact():
    matrix = _matrix()

    first = flashcards.build_flashcard_deck(
        matrix=matrix,
        source_file="matrix.json",
        source_sha256="abc",
        generated_at="2026-05-25T00:00:00Z",
    )
    second = flashcards.build_flashcard_deck(
        matrix=matrix,
        source_file="matrix.json",
        source_sha256="abc",
        generated_at="2026-05-25T00:00:00Z",
    )

    assert first == second
    assert first["artifact_type"] == "freudd_flashcards"
    assert first["subject_slug"] == "personlighedspsykologi"
    assert first["deck_slug"] == flashcards.FLASHCARD_DECK_SLUG
    assert first["card_count"] == 18
    assert len({card["card_id"] for card in first["cards"]}) == first["card_count"]
    assert sum(category["card_count"] for category in first["categories"]) == first["card_count"]
    assert all(card["front_text"] and card["back_html_sanitized"] and card["back_text"] for card in first["cards"])
    assert flashcards.validate_flashcard_artifact(first, matrix=matrix) is first


def test_build_flashcard_deck_keeps_ids_stable_when_wording_changes():
    matrix = _matrix()
    changed = copy.deepcopy(matrix)
    changed["rows"][0]["course_summary"] = "Theory A has updated explanatory wording."

    original = flashcards.build_flashcard_deck(
        matrix=matrix,
        source_file="matrix.json",
        source_sha256="abc",
        generated_at="2026-05-25T00:00:00Z",
    )
    updated = flashcards.build_flashcard_deck(
        matrix=changed,
        source_file="matrix.json",
        source_sha256="def",
        generated_at="2026-05-25T00:00:00Z",
    )

    assert [card["card_id"] for card in original["cards"]] == [card["card_id"] for card in updated["cards"]]
    assert original["cards"] != updated["cards"]


def test_build_flashcard_deck_rejects_unresolved_matrix_warning():
    matrix = _matrix()
    matrix["rows"][0]["warnings"] = ["needs review"]

    with pytest.raises(flashcards.MatrixFlashcardBuildError, match="warnings"):
        flashcards.build_flashcard_deck(
            matrix=matrix,
            source_file="matrix.json",
            source_sha256="abc",
            generated_at="2026-05-25T00:00:00Z",
        )


def test_validate_flashcard_artifact_rejects_leaked_student_provenance():
    matrix = _matrix()
    artifact = flashcards.build_flashcard_deck(
        matrix=matrix,
        source_file="matrix.json",
        source_sha256="abc",
        generated_at="2026-05-25T00:00:00Z",
    )
    artifact["cards"][0]["front_text"] = "Ane said this in a local note"

    with pytest.raises(flashcards.MatrixFlashcardBuildError, match="Unsafe learner-facing text"):
        flashcards.validate_flashcard_artifact(artifact, matrix=matrix)


def test_build_flashcard_registry_points_to_generated_deck():
    registry = flashcards.build_flashcard_registry(
        artifact_path="shows/personlighedspsykologi-en/flashcards/eksamensmatrix-personlighedspsykologi.json",
        card_count=152,
    )

    assert registry == {
        "version": 1,
        "subject_slug": "personlighedspsykologi",
        "decks": [
            {
                "deck_slug": "eksamensmatrix-personlighedspsykologi",
                "title": "Eksamensmatrix: personlighedspsykologi",
                "description": "Matrixbaserede eksamenskort til teori, orienteringspunkter og sammenligninger.",
                "artifact_path": "shows/personlighedspsykologi-en/flashcards/eksamensmatrix-personlighedspsykologi.json",
                "card_count": 152,
                "enabled": True,
            }
        ],
    }
