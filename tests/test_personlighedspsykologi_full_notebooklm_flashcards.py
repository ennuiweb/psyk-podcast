from notebooklm_queue import personlighedspsykologi_full_notebooklm_flashcards as full_cards


def _payload(*, notebook_slug: str, candidates: list[dict[str, object]]) -> dict[str, object]:
    return {
        "version": 1,
        "artifact_type": "personlighedspsykologi_notebooklm_flashcard_candidates",
        "subject_slug": "personlighedspsykologi",
        "run_id": "full-matrix-test",
        "notebook_slug": notebook_slug,
        "source_path": f"downloads/{notebook_slug}.json",
        "stats": {"candidate_count": len(candidates)},
        "candidates": candidates,
    }


def _candidate(candidate_id: str, status: str) -> dict[str, object]:
    return {
        "candidate_id": candidate_id,
        "notebook_slug": "global-calibration-synthesis",
        "front": f"Hvad tester kortet {candidate_id}?",
        "back": "Det tester, at full NotebookLM-kort kan gøres til Freudd-kort.",
        "category_slug": "personbegreb",
        "mapped_theory_ids": ["trait_and_assessment_psychology"],
        "review_status": status,
    }


def test_build_full_notebooklm_deck_filters_auto_rejected_candidates():
    payloads = [
        _payload(
            notebook_slug="global-calibration-synthesis",
            candidates=[
                _candidate("nlm-test-accepted", "candidate"),
                _candidate("nlm-test-review", "needs_review"),
                _candidate("nlm-test-rejected", "auto_rejected"),
            ],
        )
    ]

    deck = full_cards.build_full_notebooklm_deck(
        candidate_payloads=payloads,
        source_file="runs/test/candidates",
        source_sha256=full_cards.source_fingerprint(payloads),
        generated_at="2026-05-26T00:00:00Z",
    )

    assert deck["deck_slug"] == full_cards.FULL_NOTEBOOKLM_DECK_SLUG
    assert deck["card_count"] == 2
    assert deck["candidate_status_counts"] == {"auto_rejected": 1, "candidate": 1, "needs_review": 1}
    assert deck["included_status_counts"] == {"candidate": 1, "needs_review": 1}
    assert [card["card_id"] for card in deck["cards"]] == ["nlm-test-accepted", "nlm-test-review"]


def test_build_single_deck_registry_exposes_only_full_notebooklm_deck():
    registry = full_cards.build_single_deck_registry(
        artifact_path="shows/personlighedspsykologi-en/flashcards/notebooklm-fuld-matrix-personlighedspsykologi.json",
        card_count=234,
    )

    assert registry["subject_slug"] == "personlighedspsykologi"
    assert len(registry["decks"]) == 1
    assert registry["decks"][0]["deck_slug"] == full_cards.FULL_NOTEBOOKLM_DECK_SLUG
    assert registry["decks"][0]["enabled"] is True
