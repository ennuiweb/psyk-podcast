from __future__ import annotations

import json
from pathlib import Path

from notebooklm_queue import personlighedspsykologi_flashcard_review as review
from notebooklm_queue import personlighedspsykologi_matrix_flashcards as flashcards
from notebooklm_queue import personlighedspsykologi_notebooklm_variant_flashcards as variants
from notebooklm_queue import personlighedspsykologi_student_synthesis as synthesis
from notebooklm_queue.json_artifact_utils import render_json


def _orientation_points():
    return {
        "essence_context": {"placement": "mixed", "summary": "Person and context both matter."},
        "determination": {"placement": "moderate", "summary": "The person is shaped but not fixed."},
        "agency": {"placement": "situated", "summary": "Action is possible inside conditions."},
        "historicity": {"placement": "life course", "summary": "History matters for development."},
    }


def _row(theory_id: str, label: str, *, target: str | None = None) -> dict[str, object]:
    return {
        "theory_id": theory_id,
        "label": label,
        "aliases": [label],
        "lecture_keys": ["W01L1"],
        "course_role": f"{label} frames the course.",
        "course_summary": f"{label} explains personality in a specific way.",
        "student_note_labels": ["Theory sheet"],
        "model_of_person": f"{label} has a model of the person.",
        "personality_or_subjectivity_model": f"{label} explains subjectivity.",
        "method_evidence_style": "Uses a recognizable method.",
        "main_thinkers": ["Thinker"],
        "central_concepts": ["agency", "subjectivity", "context", "method"],
        "orientation_points": _orientation_points(),
        "strengths": ["Makes one thing visible."],
        "limitations": ["Hides one thing."],
        "comparison_targets": [
            {"target_theory_id": target, "relation": "contrasts_with", "rationale": "Useful exam contrast."}
        ]
        if target
        else [],
        "likely_misunderstandings": ["Reducing the theory to a slogan."],
        "student_synthesis_notes": "Use as compact exam frame.",
        "source_note_basis": [{"note_id": "note", "basis_status": "primary_student_note", "summary": "Supports row."}],
        "source_grounding": {
            "course_theory_map_ids": [theory_id],
            "concept_node_ids": [f"{theory_id}_concept"],
            "distinction_ids": [],
            "representative_source_ids": ["source"],
            "representative_evidence_origins": ["reading_grounded"],
        },
        "validation_status": "validated",
        "warnings": [],
    }


def _matrix() -> dict[str, object]:
    rows = [
        _row("trait_and_assessment_psychology", "Trækpsykologi", target="critical_psychology"),
        _row("critical_psychology", "Kritisk psykologi", target="trait_and_assessment_psychology"),
        _row("narrative_psychology", "Narrativ psykologi", target="trait_and_assessment_psychology"),
        _row("comparative_theory_analysis", "Sammenlignende analyse", target="trait_and_assessment_psychology"),
    ]
    return {
        "artifact_type": "exam_theory_matrix",
        "schema_version": synthesis.STUDENT_SYNTHESIS_SCHEMA_VERSION,
        "subject_slug": "personlighedspsykologi",
        "generated_at": "2026-05-26T00:00:00Z",
        "authority": "student_exam_synthesis",
        "build": {"builder": "test", "model": "test", "prompt_version": "test"},
        "provenance": {"input_source_ids": ["note"], "source_notes_signature": "abc", "dependency_hashes": {"x": "y"}},
        "orientation_points": [
            {"orientation_point_id": point_id, "label": point_id, "question": "Question?"}
            for point_id in synthesis.ORIENTATION_POINT_IDS
        ],
        "rows": rows,
        "stats": {"row_count": len(rows)},
        "warnings": [],
    }


def _matrix_deck(matrix: dict[str, object]) -> dict[str, object]:
    return flashcards.build_flashcard_deck(
        matrix=matrix,
        source_file="matrix.json",
        source_sha256="abc",
        generated_at="2026-05-26T00:00:00Z",
    )


def _variant_deck(deck_slug: str) -> dict[str, object]:
    decisions = {
        "version": 1,
        "artifact_type": variants.PROMOTION_DECISIONS_ARTIFACT_TYPE,
        "subject_slug": "personlighedspsykologi",
        "deck_slug": deck_slug,
        "generated_at": "2026-05-26T00:00:00Z",
        "source_run": {"run_id": "test", "notebook_slug": "test", "candidate_count": 1},
        "source_fingerprints": {"candidates": "abc", "gemini_review": "def"},
        "stats": {"decision_count": 1, "promoted_count": 1, "rejected_count": 0, "gemini_decision_counts": {"accept": 1}},
        "decisions": [
            {
                "candidate_id": f"{deck_slug}-candidate",
                "promote": True,
                "gemini_decision": "accept",
                "confidence": "high",
                "front_text": "Hvordan sammenlignes trækpsykologi og kritisk psykologi?",
                "back_text": "Trækpsykologi vægter indre dispositioner, mens kritisk psykologi vægter betingelser.",
                "category_slug": "sammenligninger",
                "mapped_theory_ids": ["trait_and_assessment_psychology", "critical_psychology"],
                "notebook_slug": "test",
                "source_index": 1,
                "reason": "Useful comparison.",
                "added_value": "Comparison.",
                "nearest_existing_card_id": "",
                "nearest_existing_card_assessment": "",
                "automatic_review_status": "candidate",
                "local_suggested_decision": "accept",
            }
        ],
    }
    return variants.build_variant_deck(
        promotion_decisions=decisions,
        source_file=f"{deck_slug}.json",
        source_sha256="abc",
        deck_slug=deck_slug,
        title=deck_slug,
        generated_at="2026-05-26T00:00:00Z",
    )


def _candidate_payload(slug: str, candidates: list[dict[str, object]] | None = None) -> dict[str, object]:
    candidates = candidates or []
    return {
        "version": 1,
        "artifact_type": "personlighedspsykologi_notebooklm_flashcard_candidates",
        "subject_slug": "personlighedspsykologi",
        "run_id": "full-run",
        "notebook_slug": slug,
        "generated_at": "2026-05-26T00:00:00Z",
        "source_path": "download.json",
        "raw_title": "Cards",
        "stats": {"raw_card_count": len(candidates), "candidate_count": len(candidates), "status_counts": {"candidate": len(candidates)}},
        "candidates": candidates,
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_json(payload), encoding="utf-8")


def test_classify_family_uses_category_and_keywords() -> None:
    assert review.classify_family(
        front="Hvor placerer narrativ psykologi agency?",
        back="Agency placeres i fortolkning.",
        category_slug="orienteringspunkter",
        tags=[],
    )["review_family"] == "orienteringspunkt"
    assert review.classify_family(
        front="Hvordan adskiller trækpsykologi og kritisk psykologi sig på essens/kontekst?",
        back="De placerer personligheden forskelligt.",
        category_slug="sammenligninger",
        tags=[],
    )["review_family"] == "akse-sammenligning"
    assert review.classify_family(
        front="Hvad er hovedpointen i trækpsykologi?",
        back="Den beskriver stabile forskelle.",
        category_slug="personbegreb",
        tags=[],
    )["review_family"] == "hovedpointe"


def test_build_comparison_report_normalizes_all_pools(tmp_path: Path) -> None:
    repo_root = tmp_path
    matrix = _matrix()
    matrix_path = repo_root / "matrix.json"
    matrix_deck_path = repo_root / "matrix_deck.json"
    variant_path = repo_root / "variant.json"
    independent_path = repo_root / "independent.json"
    lab_root = repo_root / "lab"
    reports_root = lab_root / "reports"

    _write_json(matrix_path, matrix)
    _write_json(matrix_deck_path, _matrix_deck(matrix))
    _write_json(variant_path, _variant_deck("notebooklm-varianter-personlighedspsykologi"))
    _write_json(independent_path, _variant_deck("notebooklm-uafhaengige-varianter-personlighedspsykologi"))
    for slug in review.EXPECTED_NOTEBOOK_SLUGS:
        candidates = []
        if slug == "global-calibration-synthesis":
            candidates.append(
                {
                    "candidate_id": "candidate-1",
                    "notebook_slug": slug,
                    "source_path": "download.json",
                    "source_index": 1,
                    "front": "Hvad er hovedpointen i trækpsykologi?",
                    "back": "Trækpsykologi beskriver stabile personlighedsforskelle.",
                    "category_slug": "personbegreb",
                    "category_title": "Personbegreb",
                    "mapped_theory_ids": ["trait_and_assessment_psychology"],
                    "duplicate": {"score": 0.1, "nearest_card_id": ""},
                    "manual_card_review": {},
                    "warnings": [],
                    "review_status": "candidate",
                }
            )
        _write_json(
            lab_root / "runs" / "full-run" / "candidates" / f"{slug}.candidates.json",
            _candidate_payload(slug, candidates),
        )

    report = review.build_comparison_report(
        repo_root=repo_root,
        review_run_id="test-review",
        matrix_path=matrix_path,
        matrix_deck_path=matrix_deck_path,
        variant_deck_path=variant_path,
        independent_deck_path=independent_path,
        lab_root=lab_root,
        full_run_id="full-run",
        reports_root=reports_root,
        allow_count_drift=True,
        allow_unignored_report_output=True,
        generated_at="2026-05-26T00:00:00Z",
    )

    assert report["stats"]["source_counts"]["canonical_matrix_deck"] == 36
    assert report["stats"]["source_counts"]["full_notebooklm_candidate"] == 1
    assert report["stats"]["candidate_count"] == 1
    assert report["coverage"]["grid"]["traekpsykologi"]["hovedpointe"]["candidates"] == 1
    assert report["manifest"]["inputs"]
    assert "shortlist" in report


def test_gemini_pool_review_bundle_and_validation(tmp_path: Path) -> None:
    repo_root = tmp_path
    matrix = _matrix()
    matrix_path = repo_root / "matrix.json"
    matrix_deck_path = repo_root / "matrix_deck.json"
    variant_path = repo_root / "variant.json"
    independent_path = repo_root / "independent.json"
    lab_root = repo_root / "lab"

    _write_json(matrix_path, matrix)
    _write_json(matrix_deck_path, _matrix_deck(matrix))
    _write_json(variant_path, _variant_deck("notebooklm-varianter-personlighedspsykologi"))
    _write_json(independent_path, _variant_deck("notebooklm-uafhaengige-varianter-personlighedspsykologi"))
    for slug in review.EXPECTED_NOTEBOOK_SLUGS:
        candidates = []
        if slug == "global-calibration-synthesis":
            candidates.append(
                {
                    "candidate_id": "candidate-1",
                    "notebook_slug": slug,
                    "source_path": "download.json",
                    "source_index": 1,
                    "front": "Hvad er hovedpointen i trækpsykologi?",
                    "back": "Trækpsykologi beskriver stabile personlighedsforskelle.",
                    "category_slug": "personbegreb",
                    "category_title": "Personbegreb",
                    "mapped_theory_ids": ["trait_and_assessment_psychology"],
                    "duplicate": {"score": 0.1, "nearest_card_id": ""},
                    "manual_card_review": {},
                    "warnings": [],
                    "review_status": "candidate",
                }
            )
        _write_json(
            lab_root / "runs" / "full-run" / "candidates" / f"{slug}.candidates.json",
            _candidate_payload(slug, candidates),
        )

    report = review.build_comparison_report(
        repo_root=repo_root,
        review_run_id="test-review",
        matrix_path=matrix_path,
        matrix_deck_path=matrix_deck_path,
        variant_deck_path=variant_path,
        independent_deck_path=independent_path,
        lab_root=lab_root,
        full_run_id="full-run",
        reports_root=lab_root / "reports",
        allow_count_drift=True,
        allow_unignored_report_output=True,
        generated_at="2026-05-26T00:00:00Z",
    )
    bundle = review.build_gemini_pool_review_bundle(
        comparison_report=report,
        model="gemini-test",
        generated_at="2026-05-26T00:00:00Z",
    )

    assert bundle["artifact_type"] == review.GEMINI_POOL_REVIEW_BUNDLE_ARTIFACT_TYPE
    assert len(bundle["shortlist"]) == 1
    card_key = bundle["shortlist"][0]["card_key"]
    validated = review.validate_gemini_pool_review(
        {
            "review_summary": {
                "overall_assessment": "Kortet er brugbart, men overlap skal vurderes.",
                "best_pool": "hybrid",
                "candidate_count": 1,
                "promote_count": 0,
                "promote_after_edit_count": 1,
                "merge_with_existing_count": 0,
                "reject_count": 0,
                "defer_count": 0,
                "main_risks": ["Dubletpres."],
                "implementation_priorities": ["Rediger før promotion."],
            },
            "decisions": [
                {
                    "card_key": card_key,
                    "decision": "promote_after_edit",
                    "winner": "hybrid",
                    "confidence": "medium",
                    "coverage_score": 4,
                    "exam_usefulness_score": 4,
                    "precision_score": 4,
                    "wording_score": 3,
                    "duplicate_risk_score": 2,
                    "reason": "Dækker en central pointe, men formuleringen kan strammes.",
                    "added_value": "Giver en kompakt repetitionscue.",
                    "implementation_note": "Promover kun i redigeret form.",
                    "edited_front": "Hvad er kernepointen i trækpsykologi?",
                    "edited_back": "Trækpsykologi forklarer personlighed via relativt stabile forskelle mellem personer.",
                    "safety_flags": [],
                }
            ],
        },
        bundle=bundle,
        model="gemini-test",
        generated_at="2026-05-26T00:00:00Z",
    )

    assert validated["artifact_type"] == review.GEMINI_POOL_REVIEW_ARTIFACT_TYPE
    assert validated["stats"]["decision_counts"] == {"promote_after_edit": 1}


def test_preflight_rejects_missing_full_run_candidates(tmp_path: Path) -> None:
    matrix = _matrix()
    matrix_path = tmp_path / "matrix.json"
    matrix_deck_path = tmp_path / "matrix_deck.json"
    variant_path = tmp_path / "variant.json"
    independent_path = tmp_path / "independent.json"
    _write_json(matrix_path, matrix)
    _write_json(matrix_deck_path, _matrix_deck(matrix))
    _write_json(variant_path, _variant_deck("notebooklm-varianter-personlighedspsykologi"))
    _write_json(independent_path, _variant_deck("notebooklm-uafhaengige-varianter-personlighedspsykologi"))

    try:
        review.build_comparison_report(
            repo_root=tmp_path,
            matrix_path=matrix_path,
            matrix_deck_path=matrix_deck_path,
            variant_deck_path=variant_path,
            independent_deck_path=independent_path,
            lab_root=tmp_path / "lab",
            reports_root=tmp_path / "lab" / "reports",
            allow_count_drift=True,
            allow_unignored_report_output=True,
        )
    except review.FlashcardReviewError as exc:
        assert "Missing full-run NotebookLM candidate files" in str(exc)
    else:
        raise AssertionError("missing full-run candidates should fail preflight")
