from __future__ import annotations

import copy

import pytest

from notebooklm_queue import personlighedspsykologi_notebooklm_variant_flashcards as variants


def _candidate(candidate_id: str, *, source_index: int = 1) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "front": "Hvad tester dette variantkort?",
        "back": "Det tester om NotebookLM-varianter kan promoveres sikkert.",
        "category_slug": "personbegreb",
        "mapped_theory_ids": ["critical_psychology"],
        "notebook_slug": "critical-sociocultural-narrative",
        "source_index": source_index,
        "review_status": "candidate",
        "manual_card_review": {
            "suggested_decision": "accept",
            "nearest_existing_card": {"card_id": "mx-critical-psychology-model"},
        },
    }


def _candidates_payload() -> dict[str, object]:
    return {
        "run_id": "pilot-test",
        "notebook_slug": "critical-sociocultural-narrative",
        "candidates": [
            _candidate("candidate-accept", source_index=1),
            _candidate("candidate-edit", source_index=2),
            _candidate("candidate-reject", source_index=3),
        ],
    }


def _review_payload() -> dict[str, object]:
    return {
        "run_id": "pilot-test",
        "notebook_slug": "critical-sociocultural-narrative",
        "decisions": [
            {
                "candidate_id": "candidate-accept",
                "decision": "accept",
                "confidence": "high",
                "reason": "Distinct enough.",
                "added_value": "Audit-only note.",
            },
            {
                "candidate_id": "candidate-edit",
                "decision": "edit",
                "confidence": "high",
                "edited_front": "Hvad er den redigerede variant?",
                "edited_back": "Den redigerede variant bruger Gemini-reviewet formulering.",
                "reason": "Needs tighter wording.",
                "added_value": "Audit-only note.",
            },
            {
                "candidate_id": "candidate-reject",
                "decision": "reject",
                "confidence": "high",
                "reason": "Too close.",
            },
        ],
    }


def test_build_promotion_decisions_and_variant_deck_are_deterministic() -> None:
    decisions = variants.build_promotion_decisions(
        candidates_payload=_candidates_payload(),
        gemini_review_payload=_review_payload(),
        generated_at="2026-05-26T00:00:00Z",
    )
    deck = variants.build_variant_deck(
        promotion_decisions=decisions,
        source_file="shows/personlighedspsykologi-en/flashcards/notebooklm_variant_promotion_decisions.json",
        source_sha256="abc",
        generated_at="2026-05-26T00:00:00Z",
    )

    assert decisions["stats"]["decision_count"] == 3
    assert decisions["stats"]["promoted_count"] == 2
    assert decisions["stats"]["gemini_decision_counts"] == {"accept": 1, "edit": 1, "reject": 1}
    assert deck["deck_slug"] == variants.VARIANT_DECK_SLUG
    assert deck["card_count"] == 2
    assert all(card["card_id"].startswith("nlmv-") for card in deck["cards"])
    assert all("Audit-only note" not in card["back_text"] for card in deck["cards"])
    assert variants.validate_promotion_decisions(decisions) is decisions
    assert variants.validate_variant_deck(deck) is deck


def test_promotion_decisions_reject_missing_gemini_review() -> None:
    review = copy.deepcopy(_review_payload())
    review["decisions"] = review["decisions"][:-1]

    with pytest.raises(variants.NotebookLMVariantFlashcardError, match="missing candidate decisions"):
        variants.build_promotion_decisions(
            candidates_payload=_candidates_payload(),
            gemini_review_payload=review,
            generated_at="2026-05-26T00:00:00Z",
        )


def test_variant_deck_rejects_learner_facing_source_leaks() -> None:
    candidates = _candidates_payload()
    candidates["candidates"][0]["front"] = "Ane said this in a local note"

    with pytest.raises(variants.NotebookLMVariantFlashcardError, match="Unsafe learner-facing text"):
        variants.build_promotion_decisions(
            candidates_payload=candidates,
            gemini_review_payload=_review_payload(),
            generated_at="2026-05-26T00:00:00Z",
        )
