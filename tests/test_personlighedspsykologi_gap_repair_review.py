from __future__ import annotations

import pytest

from notebooklm_queue import personlighedspsykologi_gap_repair_review as review


def _candidate(candidate_id: str, *, source_index: int = 1, status: str = "candidate") -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "notebook_slug": "gap-repair-comparisons-traps",
        "source_index": source_index,
        "front": "Hvordan sammenlignes to teorier i matrixen?",
        "back": "Kortet tester en konkret forskel, så den kan bruges i mundtlig eksamen.",
        "category_slug": "sammenligninger",
        "category_title": "Sammenligninger",
        "mapped_theory_ids": ["critical_psychology"],
        "warnings": [],
        "review_status": status,
        "manual_card_review": {
            "suggested_decision": "accept",
            "nearest_existing_card": {"card_id": "existing-card"},
            "duplicate_score": 0.22,
        },
    }


def _candidate_payload() -> dict[str, object]:
    return {
        "artifact_type": "personlighedspsykologi_notebooklm_flashcard_candidates",
        "subject_slug": "personlighedspsykologi",
        "run_id": "gap-repair-test",
        "notebook_slug": "gap-repair-comparisons-traps",
        "candidates": [
            _candidate("candidate-accept", source_index=1),
            _candidate("candidate-edit", source_index=2, status="needs_review"),
            _candidate("candidate-auto", source_index=3, status="auto_rejected"),
        ],
    }


def _matrix() -> dict[str, object]:
    return {
        "subject_slug": "personlighedspsykologi",
        "orientation_points": [],
        "rows": [
            {
                "theory_id": "critical_psychology",
                "label": "Kritisk psykologi",
                "course_role": "Tester praksis og handleevne.",
                "course_summary": "Kritisk psykologi forstår personer i konkrete livsbetingelser.",
                "model_of_person": "Personen er deltager i praksis.",
                "personality_or_subjectivity_model": "Subjektivitet formes i praksis.",
                "method_evidence_style": "Analyse af hverdagsliv og praksis.",
                "central_concepts": ["handleevne"],
                "orientation_points": {},
                "strengths": [],
                "limitations": [],
                "likely_misunderstandings": ["At gøre teorien rent individualistisk"],
                "comparison_targets": [
                    {
                        "target_theory_id": "trait_and_assessment_psychology",
                        "relation": "contrasts_with",
                        "rationale": "Kontrast mellem praksis og måling.",
                    }
                ],
            }
        ],
    }


def _plan() -> dict[str, object]:
    return {
        "run_id": "gap-repair-test",
        "notebooks": [
            {
                "slug": "gap-repair-comparisons-traps",
                "gap_unit_ids": [
                    "critical_psychology:comparison_targets:trait_and_assessment_psychology",
                    "critical_psychology:likely_misunderstandings:1",
                    "critical_psychology:comparison_targets:trait_and_assessment_psychology",
                ],
            }
        ],
    }


def _deck() -> dict[str, object]:
    return {
        "deck_slug": "notebooklm-fuld-matrix-personlighedspsykologi",
        "card_count": 1,
        "cards": [],
    }


def _raw_review() -> dict[str, object]:
    return {
        "review_summary": {
            "overall_assessment": "Useful repair candidates.",
            "candidate_count": 2,
            "accept_count": 1,
            "edit_count": 1,
            "merge_with_existing_count": 0,
            "reject_count": 0,
            "main_risks": [],
        },
        "decisions": [
            {
                "candidate_id": "candidate-accept",
                "decision": "accept",
                "confidence": "high",
                "reason": "Covers the target gap.",
                "added_value": "Adds a clear comparison cue.",
                "target_gap_assessment": "Matches the intended comparison.",
                "nearest_existing_card_assessment": "Overlap is acceptable because it repairs the gap.",
                "edited_front": "",
                "edited_back": "",
                "safety_flags": [],
            },
            {
                "candidate_id": "candidate-edit",
                "decision": "edit",
                "confidence": "medium",
                "reason": "Useful but needs tighter wording.",
                "added_value": "Makes the exam trap more precise.",
                "target_gap_assessment": "Matches the intended trap after edit.",
                "nearest_existing_card_assessment": "Related but not equivalent.",
                "edited_front": "Hvordan undgår man at reducere kritisk psykologi til individualisme?",
                "edited_back": "Man viser, at handleevne altid forstås gennem konkrete livsbetingelser og praksis.",
                "safety_flags": [],
            },
        ],
    }


def test_gap_repair_review_bundle_excludes_auto_rejected_and_attaches_targets() -> None:
    bundle = review.build_gap_repair_review_bundle(
        candidate_payloads=[_candidate_payload()],
        plan=_plan(),
        matrix=_matrix(),
        current_deck=_deck(),
        model="gemini-test",
        generated_at="2026-05-26T00:00:00Z",
    )

    assert len(bundle["candidates"]) == 2
    assert bundle["candidates"][0]["target_gap"]["field"] == "comparison_targets"
    assert bundle["review_contract"]["decision_rules"]


def test_gap_repair_review_decisions_can_become_candidate_payload() -> None:
    bundle = review.build_gap_repair_review_bundle(
        candidate_payloads=[_candidate_payload()],
        plan=_plan(),
        matrix=_matrix(),
        current_deck=_deck(),
        model="gemini-test",
        generated_at="2026-05-26T00:00:00Z",
    )
    reviewed = review.validate_gap_repair_review(
        _raw_review(),
        bundle=bundle,
        model="gemini-test",
        generated_at="2026-05-26T00:00:00Z",
    )
    decisions = review.build_gap_repair_promotion_decisions(
        candidate_payloads=[_candidate_payload()],
        review_payload=reviewed,
        bundle=bundle,
        generated_at="2026-05-26T00:00:00Z",
    )
    candidate_payload = review.gap_repair_decisions_to_candidate_payload(decisions)

    assert decisions["stats"]["promoted_count"] == 2
    assert candidate_payload["stats"]["candidate_count"] == 2
    assert candidate_payload["candidates"][1]["front"].startswith("Hvordan undgår")
    assert "notebooklm-gap-repair" in candidate_payload["candidates"][0]["tags"]


def test_gap_repair_review_rejects_unsafe_edits() -> None:
    bundle = review.build_gap_repair_review_bundle(
        candidate_payloads=[_candidate_payload()],
        plan=_plan(),
        matrix=_matrix(),
        current_deck=_deck(),
        model="gemini-test",
        generated_at="2026-05-26T00:00:00Z",
    )
    raw = _raw_review()
    raw["decisions"][1]["edited_back"] = "Se /Users/oskar/noter."

    with pytest.raises(review.GapRepairReviewError, match="Unsafe learner-facing text"):
        review.validate_gap_repair_review(raw, bundle=bundle, model="gemini-test")
