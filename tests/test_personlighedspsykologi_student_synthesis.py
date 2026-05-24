import pytest

from notebooklm_queue import personlighedspsykologi_student_synthesis as synthesis


def _orientation_points():
    return {
        "essence_context": {
            "placement": "mixed",
            "summary": "The theory places the person between inner pattern and context.",
        },
        "determination": {
            "placement": "moderate",
            "summary": "The person is shaped without being fully determined.",
        },
        "agency": {
            "placement": "situated",
            "summary": "Agency is possible inside concrete conditions.",
        },
        "historicity": {
            "placement": "ontogenetic",
            "summary": "The life course matters for the account.",
        },
    }


def _basis():
    return [
        {
            "note_id": "note-1",
            "basis_status": "primary_student_note",
            "summary": "The student note gives the row's comparison frame.",
        }
    ]


def _matrix_row(**overrides):
    row = {
        "theory_id": "theory_a",
        "label": "Theory A",
        "aliases": ["A"],
        "lecture_keys": ["W01L1"],
        "course_role": "Introduces the test theory.",
        "course_summary": "A compact course summary.",
        "student_note_labels": ["Student label"],
        "model_of_person": "The person is understood through a compact model.",
        "personality_or_subjectivity_model": "Personality is modeled in a compact way.",
        "method_evidence_style": "Uses a clear method.",
        "main_thinkers": ["Thinker"],
        "central_concepts": ["concept"],
        "orientation_points": _orientation_points(),
        "strengths": ["A strength."],
        "limitations": ["A limitation."],
        "comparison_targets": [],
        "likely_misunderstandings": ["A misunderstanding."],
        "student_synthesis_notes": "Compact exam synthesis.",
        "source_note_basis": _basis(),
        "source_grounding": {
            "course_theory_map_ids": ["theory_a"],
            "concept_node_ids": ["concept_a"],
            "distinction_ids": [],
            "representative_source_ids": ["source-1"],
            "representative_evidence_origins": ["reading_grounded"],
        },
        "validation_status": "validated",
        "warnings": [],
    }
    row.update(overrides)
    return row


def _matrix(rows=None):
    return {
        "artifact_type": "exam_theory_matrix",
        "schema_version": synthesis.STUDENT_SYNTHESIS_SCHEMA_VERSION,
        "subject_slug": "personlighedspsykologi",
        "generated_at": "2026-05-24T00:00:00Z",
        "authority": "student_exam_synthesis",
        "build": {
            "builder": "scripts/build_personlighedspsykologi_exam_theory_matrix.py",
            "model": "deterministic-curated-student-synthesis",
            "prompt_version": "test",
        },
        "provenance": {
            "input_source_ids": ["note-1"],
            "source_notes_signature": "abc",
            "dependency_hashes": {"seed": "123"},
        },
        "orientation_points": [
            {"orientation_point_id": point_id, "label": point_id, "question": "Question?"}
            for point_id in synthesis.ORIENTATION_POINT_IDS
        ],
        "rows": rows or [_matrix_row()],
        "stats": {"row_count": 1},
        "warnings": [],
    }


def test_build_source_notes_index_extracts_plain_text(tmp_path):
    note_path = tmp_path / "note.txt"
    note_path.write_text(
        "Essens og kontekst. Agency, determination og historicitet. Narrativ teori.",
        encoding="utf-8",
    )

    payload = synthesis.build_source_notes_index(
        [{"note_id": "note-1", "label": "Note", "path": str(note_path)}],
        repo_root=tmp_path,
        generated_at="2026-05-24T00:00:00Z",
    )

    assert payload["stats"]["note_count"] == 1
    note = payload["notes"][0]
    assert note["sha256"]
    assert note["extraction_method"] == "plain-text"
    assert note["keyword_hits"]["essence_context"] == 2
    assert note["keyword_hits"]["agency"] == 1
    assert note["keyword_hits"]["narrative"] == 1
    assert synthesis.validate_source_notes_index(payload) is payload


def test_validate_exam_theory_matrix_accepts_valid_payload():
    payload = _matrix()

    assert (
        synthesis.validate_exam_theory_matrix(
            payload,
            known_theory_ids={"theory_a"},
            known_lecture_keys={"W01L1"},
        )
        is payload
    )


def test_validate_exam_theory_matrix_rejects_duplicate_theory_id():
    payload = _matrix(rows=[_matrix_row(), _matrix_row(label="Theory A duplicate")])

    with pytest.raises(synthesis.StudentSynthesisValidationError, match="Duplicate theory_id"):
        synthesis.validate_exam_theory_matrix(payload)


def test_validate_exam_theory_matrix_rejects_missing_orientation_point():
    orientation = _orientation_points()
    orientation.pop("agency")
    payload = _matrix(rows=[_matrix_row(orientation_points=orientation)])

    with pytest.raises(synthesis.StudentSynthesisValidationError, match="orientation_points missing"):
        synthesis.validate_exam_theory_matrix(payload)


def test_validate_exam_theory_matrix_rejects_validated_without_sources():
    payload = _matrix(
        rows=[
            _matrix_row(
                source_grounding={
                    "course_theory_map_ids": ["theory_a"],
                    "concept_node_ids": ["concept_a"],
                    "distinction_ids": [],
                    "representative_source_ids": [],
                    "representative_evidence_origins": [],
                }
            )
        ]
    )

    with pytest.raises(synthesis.StudentSynthesisValidationError, match="representative_source_ids"):
        synthesis.validate_exam_theory_matrix(payload)


def test_build_exam_theory_matrix_enriches_seed_with_course_grounding():
    seed = {
        "version": synthesis.STUDENT_SYNTHESIS_SCHEMA_VERSION,
        "subject_slug": "personlighedspsykologi",
        "source_note_ids": ["note-1"],
        "rows": [
            {
                "theory_id": "theory_a",
                "lecture_keys": ["W01L1"],
                "student_note_labels": ["Student label"],
                "model_of_person": "The person is compactly modeled.",
                "personality_or_subjectivity_model": "Personality has a compact model.",
                "method_evidence_style": "A compact method.",
                "main_thinkers": ["Thinker"],
                "central_concepts": ["concept"],
                "orientation_points": _orientation_points(),
                "strengths": ["A strength."],
                "limitations": ["A limitation."],
                "comparison_targets": [],
                "likely_misunderstandings": ["A misunderstanding."],
                "student_synthesis_notes": "A compact note.",
                "source_note_basis": _basis(),
            }
        ],
    }
    source_notes_index = {
        "notes": [
            {
                "note_id": "note-1",
                "sha256": "abc",
                "extraction_method": "plain-text",
                "embedded_media_count": 0,
            }
        ]
    }
    theory_map = {
        "theories": [
            {
                "theory_id": "theory_a",
                "label": "Theory A",
                "aliases": ["A"],
                "lecture_keys": ["W01L1"],
                "course_role": "Introduces the test theory.",
                "summary": "A compact course summary.",
                "representative_source_ids": ["source-1"],
                "representative_evidence_origins": ["reading_grounded"],
            }
        ]
    }
    concept_graph = {
        "nodes": [
            {
                "node_id": "concept_a",
                "node_type": "term",
                "label": "Concept A",
                "theory_ids": ["theory_a"],
            }
        ],
        "distinctions": [
            {
                "distinction_id": "distinction_a",
                "term_ids": ["concept_a"],
            }
        ],
    }

    payload = synthesis.build_exam_theory_matrix(
        seed=seed,
        source_notes_index=source_notes_index,
        theory_map=theory_map,
        concept_graph=concept_graph,
        dependency_hashes_payload={"seed": "123"},
        generated_at="2026-05-24T00:00:00Z",
    )

    row = payload["rows"][0]
    assert row["validation_status"] == "validated"
    assert row["source_grounding"]["representative_source_ids"] == ["source-1"]
    assert row["source_grounding"]["concept_node_ids"] == ["concept_a"]
    assert row["source_grounding"]["distinction_ids"] == ["distinction_a"]
