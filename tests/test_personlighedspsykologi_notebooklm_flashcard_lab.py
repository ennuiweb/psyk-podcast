from __future__ import annotations

import json

from notebooklm_queue import personlighedspsykologi_notebooklm_flashcard_lab as lab
from notebooklm_queue import personlighedspsykologi_matrix_flashcards as flashcards
from notebooklm_queue import personlighedspsykologi_student_synthesis as synthesis


def _orientation_points():
    return {
        "essence_context": {
            "placement": "mixed",
            "summary": "Person and context are mutually relevant.",
        },
        "determination": {
            "placement": "moderate",
            "summary": "The person is shaped without being mechanically fixed.",
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


def _row(theory_id: str, label: str, *, target: str | None = None):
    return {
        "theory_id": theory_id,
        "label": label,
        "aliases": [label],
        "lecture_keys": ["W01L1"],
        "course_role": f"{label} gives the course a theory frame.",
        "course_summary": f"{label} explains personality through a compact frame.",
        "student_note_labels": ["Theory sheet"],
        "model_of_person": f"{label} has a specific model of the person.",
        "personality_or_subjectivity_model": f"{label} has a specific model of subjectivity.",
        "method_evidence_style": "Uses a recognizable method and evidence style.",
        "main_thinkers": ["Thinker"],
        "central_concepts": ["agency", "subjectivity", "context"],
        "orientation_points": _orientation_points(),
        "strengths": ["Makes one thing visible."],
        "limitations": ["Hides one thing."],
        "comparison_targets": [
            {
                "target_theory_id": target,
                "relation": "contrasts_with",
                "rationale": "It makes a useful exam contrast.",
            }
        ]
        if target
        else [],
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
        "warnings": [],
    }


def _matrix():
    rows = [
        _row("critical_personalism", "Critical personalism", target="critical_psychology"),
        _row("critical_psychology", "Kritisk psykologi", target="critical_personalism"),
        _row("sociocultural_poststructural_approaches", "Poststrukturalisme"),
        _row("narrative_psychology", "Narrativ psykologi"),
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


def _deck(matrix):
    return flashcards.build_flashcard_deck(
        matrix=matrix,
        source_file="matrix.json",
        source_sha256="abc",
        generated_at="2026-05-25T00:00:00Z",
    )


def test_export_notebook_packs_writes_pilot_sources_and_manifest(tmp_path):
    matrix = _matrix()
    deck = _deck(matrix)

    manifest = lab.export_notebook_packs(
        matrix=matrix,
        deck=deck,
        run_id="test-run",
        lab_root=tmp_path / "lab",
        repo_root=tmp_path,
        notebook_slugs={lab.PILOT_NOTEBOOK_SLUG},
        generated_at="2026-05-25T00:00:00Z",
    )

    notebook = manifest["notebooks"][0]
    pack_dir = tmp_path / notebook["pack_dir"]
    assert manifest["run_id"] == "test-run"
    assert notebook["slug"] == lab.PILOT_NOTEBOOK_SLUG
    assert notebook["source_count"] == 6
    assert (pack_dir / "00-card-authoring-brief.md").exists()
    assert (pack_dir / "02-matrix-slice.md").read_text(encoding="utf-8").count("## ") == 4
    assert all(source["sha256"] and source["bytes"] > 0 for source in notebook["sources"])


def test_export_lab_run_loads_files_and_writes_readme(tmp_path):
    matrix_path = tmp_path / "matrix.json"
    deck_path = tmp_path / "deck.json"
    matrix_path.write_text(json.dumps(_matrix()), encoding="utf-8")
    deck_path.write_text(json.dumps(_deck(_matrix())), encoding="utf-8")

    manifest = lab.export_lab_run(
        run_id="test-run",
        lab_root=tmp_path / "lab",
        matrix_path=matrix_path,
        deck_path=deck_path,
        repo_root=tmp_path,
        notebook_slugs={lab.PILOT_NOTEBOOK_SLUG},
        generated_at="2026-05-25T00:00:00Z",
    )

    run_root = tmp_path / "lab" / "runs" / "test-run"
    assert (run_root / "manifest.json").exists()
    assert (run_root / "README.md").exists()
    assert "Do not import NotebookLM cards directly" in (run_root / "README.md").read_text(encoding="utf-8")
    assert lab.manifest_digest(manifest)


def test_normalize_notebooklm_cards_labels_candidate_risks(tmp_path):
    matrix = _matrix()
    deck = _deck(matrix)
    existing = deck["cards"][0]
    payload = {
        "title": "Pilot cards",
        "cards": [
            {
                "front": "Hvordan placerer kritisk psykologi agency i eksamenssvar?",
                "back": "Kritisk psykologi betoner handleevne som situeret i konkrete livsbetingelser.",
            },
            {
                "front": existing["front_text"],
                "back": existing["back_text"],
            },
            {
                "front": "Hvad skrev Ane om kritisk psykologi?",
                "back": "Ane beskrev en lokal kilde i /Users/oskar/notes.",
            },
            {
                "front": "Hvad er begrebet?",
                "back": "Det er vigtigt.",
            },
        ],
    }

    candidates = lab.normalize_notebooklm_cards(
        notebooklm_payload=payload,
        matrix=matrix,
        current_deck=deck,
        run_id="test-run",
        notebook_slug=lab.PILOT_NOTEBOOK_SLUG,
        source_path="downloads/cards.json",
        generated_at="2026-05-25T00:00:00Z",
    )

    statuses = [candidate["review_status"] for candidate in candidates["candidates"]]
    assert statuses == ["candidate", "auto_rejected", "auto_rejected", "auto_rejected"]
    assert candidates["stats"]["status_counts"] == {"auto_rejected": 3, "candidate": 1}
    assert candidates["candidates"][0]["category_slug"] == "orienteringspunkter"
    assert candidates["candidates"][0]["manual_card_review"]["nearest_existing_card"]["card_id"]
    assert candidates["candidates"][0]["manual_card_review"]["suggested_decision"] in {"accept", "edit"}
    assert candidates["candidates"][1]["duplicate"]["score"] >= lab.DUPLICATE_REJECT_THRESHOLD
    assert candidates["candidates"][1]["manual_card_review"]["suggested_decision"] == "merge_with_existing"
    assert "unsafe_provenance_or_path" in candidates["candidates"][2]["warnings"]
    assert not candidates["candidates"][3]["mapped_theory_ids"]


def test_load_notebooklm_flashcard_payload_accepts_flashcards_key(tmp_path):
    path = tmp_path / "cards.json"
    path.write_text(json.dumps({"flashcards": [{"f": "Q?", "b": "A"}]}), encoding="utf-8")

    payload = lab.load_notebooklm_flashcard_payload(path)

    assert payload["cards"] == [{"f": "Q?", "b": "A"}]


def test_infer_theory_ids_handles_danish_inflected_theory_terms():
    matrix = _matrix()

    assert lab.infer_theory_ids(
        "Hvordan skabes subjektivitet ifølge sociokulturelle og poststrukturalistiske tilgange?",
        "Gennem diskurs, magt og subjektpositioner.",
        matrix,
    ) == ["sociocultural_poststructural_approaches"]
    assert lab.infer_theory_ids(
        "Hvordan forstår narrativ psykologi livshistorie?",
        "Som fortællinger, der organiserer identitet over tid.",
        matrix,
    ) == ["narrative_psychology"]


def test_build_gemini_flashcard_review_bundle_and_validate_response():
    matrix = _matrix()
    deck = _deck(matrix)
    candidates = lab.normalize_notebooklm_cards(
        notebooklm_payload={
            "cards": [
                {
                    "front": "Hvordan placerer kritisk psykologi agency i eksamenssvar?",
                    "back": "Kritisk psykologi betoner handleevne som situeret i konkrete livsbetingelser.",
                }
            ]
        },
        matrix=matrix,
        current_deck=deck,
        run_id="test-run",
        notebook_slug=lab.PILOT_NOTEBOOK_SLUG,
        source_path="downloads/cards.json",
        generated_at="2026-05-25T00:00:00Z",
    )

    bundle = lab.build_gemini_flashcard_review_bundle(
        candidates_payload=candidates,
        matrix=matrix,
        current_deck=deck,
        model="gemini-test",
        generated_at="2026-05-25T00:00:00Z",
    )
    candidate_id = bundle["candidates"][0]["candidate_id"]
    review = lab.validate_gemini_flashcard_review(
        {
            "review_summary": {
                "overall_assessment": "Useful but should stay review-only.",
                "candidate_count": 1,
                "accept_count": 1,
                "edit_count": 0,
                "merge_with_existing_count": 0,
                "reject_count": 0,
                "main_risks": ["Potential overlap."],
            },
            "decisions": [
                {
                    "candidate_id": candidate_id,
                    "decision": "accept",
                    "confidence": "medium",
                    "reason": "Adds an oral-exam cue about agency.",
                    "added_value": "Sharper than the nearest existing card.",
                    "nearest_existing_card_assessment": "Related but not equivalent.",
                    "edited_front": "",
                    "edited_back": "",
                    "safety_flags": [],
                }
            ],
        },
        bundle=bundle,
        model="gemini-test",
        generated_at="2026-05-25T00:00:00Z",
    )

    assert bundle["prompt_version"] == lab.GEMINI_FLASHCARD_REVIEW_PROMPT_VERSION
    assert bundle["matrix_rows"]
    assert lab.gemini_flashcard_review_response_schema()["required"] == ["review_summary", "decisions"]
    assert review["stats"]["decision_counts"] == {"accept": 1}
    assert review["decisions"][0]["candidate_id"] == candidate_id


def test_validate_gemini_flashcard_review_rejects_missing_or_unsafe_edits():
    matrix = _matrix()
    deck = _deck(matrix)
    candidates = lab.normalize_notebooklm_cards(
        notebooklm_payload={
            "cards": [
                {
                    "front": "Hvordan placerer kritisk psykologi agency i eksamenssvar?",
                    "back": "Kritisk psykologi betoner handleevne som situeret i konkrete livsbetingelser.",
                }
            ]
        },
        matrix=matrix,
        current_deck=deck,
        run_id="test-run",
        notebook_slug=lab.PILOT_NOTEBOOK_SLUG,
        source_path="downloads/cards.json",
        generated_at="2026-05-25T00:00:00Z",
    )
    bundle = lab.build_gemini_flashcard_review_bundle(
        candidates_payload=candidates,
        matrix=matrix,
        current_deck=deck,
        model="gemini-test",
        generated_at="2026-05-25T00:00:00Z",
    )
    candidate_id = bundle["candidates"][0]["candidate_id"]

    try:
        lab.validate_gemini_flashcard_review(
            {
                "review_summary": {"overall_assessment": "", "main_risks": []},
                "decisions": [
                    {
                        "candidate_id": candidate_id,
                        "decision": "edit",
                        "confidence": "high",
                        "reason": "Needs edit.",
                        "added_value": "Better focus.",
                        "nearest_existing_card_assessment": "Not duplicate.",
                        "edited_front": "Hvad skrev Ane?",
                        "edited_back": "Se /Users/oskar/noter.",
                        "safety_flags": [],
                    }
                ],
            },
            bundle=bundle,
            model="gemini-test",
        )
    except lab.FlashcardLabError as exc:
        assert "forbidden" in str(exc)
    else:
        raise AssertionError("unsafe Gemini edit should fail validation")
