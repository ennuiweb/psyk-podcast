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


def test_safe_front_prefixes_are_removed_from_live_deck_cards():
    payloads = [
        _payload(
            notebook_slug="global-calibration-synthesis",
            candidates=[
                {
                    **_candidate("nlm-test-concept", "candidate"),
                    "front": "Begreb: Hvad er 'whole trait theory'?",
                },
                {
                    **_candidate("nlm-test-comparison", "candidate"),
                    "front": "Sammenligning: Hvordan adskiller narrativ psykologi sig fra trækpsykologi?",
                },
                {
                    **_candidate("nlm-test-trait-context", "candidate"),
                    "front": "Trækpsykologi: Hvilken status har 'agency' i statiske trækmodeller?",
                },
            ],
        )
    ]

    deck = full_cards.build_full_notebooklm_deck(
        candidate_payloads=payloads,
        source_file="runs/test/candidates",
        source_sha256=full_cards.source_fingerprint(payloads),
        generated_at="2026-05-26T00:00:00Z",
    )

    fronts = {card["card_id"]: card["front_text"] for card in deck["cards"]}
    assert fronts["nlm-test-concept"] == "Hvad er 'whole trait theory'?"
    assert fronts["nlm-test-comparison"] == "Hvordan adskiller narrativ psykologi sig fra trækpsykologi?"
    assert fronts["nlm-test-trait-context"] == "Hvilken status har 'agency' i statiske trækmodeller?"


def test_context_prefixes_are_kept_when_removal_would_make_question_ambiguous():
    payloads = [
        _payload(
            notebook_slug="measurement-development-pathology",
            candidates=[
                {
                    **_candidate("nlm-test-biosocial", "candidate"),
                    "front": "Biosociale perspektiver: Nævn en teoretisk begrænsning ved denne tradition.",
                },
                {
                    **_candidate("nlm-test-functioning", "candidate"),
                    "front": "Personlighedsfunktion: Hvordan adskiller denne tilgang sig fra den klassiske trækpsykologi?",
                },
                {
                    **_candidate("nlm-test-trait-deictic", "candidate"),
                    "front": "Trækpsykologi: Hvordan forstås 'determination' i denne tradition?",
                },
            ],
        )
    ]

    deck = full_cards.build_full_notebooklm_deck(
        candidate_payloads=payloads,
        source_file="runs/test/candidates",
        source_sha256=full_cards.source_fingerprint(payloads),
        generated_at="2026-05-26T00:00:00Z",
    )

    fronts = {card["card_id"]: card["front_text"] for card in deck["cards"]}
    assert fronts["nlm-test-biosocial"].startswith("Biosociale perspektiver:")
    assert fronts["nlm-test-functioning"].startswith("Personlighedsfunktion:")
    assert fronts["nlm-test-trait-deictic"].startswith("Trækpsykologi:")


def test_full_deck_applies_validated_answer_enrichment_overlay():
    payloads = [
        _payload(
            notebook_slug="coverage-closure",
            candidates=[
                {
                    **_candidate("nlm-test-enriched", "candidate"),
                    "front": "Hvilket centralbegreb skal du kende?",
                    "back": "Centralbegreb: needs",
                }
            ],
        )
    ]
    enrichment = {
        "version": 1,
        "artifact_type": "personlighedspsykologi_flashcard_answer_enrichment_overrides",
        "subject_slug": "personlighedspsykologi",
        "generated_at": "2026-05-26T00:00:00Z",
        "scope": "test",
        "stats": {"override_count": 1},
        "overrides": [
            {
                "card_id": "nlm-test-enriched",
                "old_back_text": "Centralbegreb: needs",
                "new_back_text": (
                    "Needs: I humanistisk psykologi er behov udviklingsbetingelser "
                    "for vækst, relation og selvrealisering."
                ),
                "rationale": "Expand a label-only answer.",
                "source_matrix_fields": ["test.central_concepts"],
            }
        ],
    }

    deck = full_cards.build_full_notebooklm_deck(
        candidate_payloads=payloads,
        source_file="runs/test/candidates + enrichment.json",
        source_sha256=full_cards.source_fingerprint(payloads, [enrichment]),
        answer_enrichment_payloads=[enrichment],
        generated_at="2026-05-26T00:00:00Z",
    )

    card = deck["cards"][0]
    assert card["back_text"].startswith("Needs: I humanistisk psykologi")
    assert "answer-enriched" in card["tags"]
    assert deck["answer_enrichment"]["applied_count"] == 1


def test_answer_enrichment_fails_closed_when_old_answer_is_stale():
    payloads = [
        _payload(
            notebook_slug="coverage-closure",
            candidates=[
                {
                    **_candidate("nlm-test-stale", "candidate"),
                    "front": "Hvilket centralbegreb skal du kende?",
                    "back": "Centralbegreb: needs",
                }
            ],
        )
    ]
    enrichment = {
        "version": 1,
        "artifact_type": "personlighedspsykologi_flashcard_answer_enrichment_overrides",
        "subject_slug": "personlighedspsykologi",
        "generated_at": "2026-05-26T00:00:00Z",
        "scope": "test",
        "stats": {"override_count": 1},
        "overrides": [
            {
                "card_id": "nlm-test-stale",
                "old_back_text": "Centralbegreb: growth",
                "new_back_text": "Growth: Humanistisk psykologi forstår vækst som relationel udvikling.",
                "rationale": "This should fail because the old answer is stale.",
                "source_matrix_fields": ["test.central_concepts"],
            }
        ],
    }

    try:
        full_cards.build_full_notebooklm_deck(
            candidate_payloads=payloads,
            source_file="runs/test/candidates + enrichment.json",
            source_sha256=full_cards.source_fingerprint(payloads, [enrichment]),
            answer_enrichment_payloads=[enrichment],
            generated_at="2026-05-26T00:00:00Z",
        )
    except full_cards.FullNotebookLMFlashcardError as exc:
        assert "old_back_text is stale" in str(exc)
    else:
        raise AssertionError("Expected stale answer enrichment to fail")


def test_full_deck_applies_validated_background_overlay():
    payloads = [
        _payload(
            notebook_slug="global-calibration-synthesis",
            candidates=[_candidate("nlm-test-background", "candidate")],
        )
    ]
    backgrounds = {
        "version": 1,
        "artifact_type": "personlighedspsykologi_flashcard_background_overlays",
        "subject_slug": "personlighedspsykologi",
        "generated_at": "2026-05-26T00:00:00Z",
        "scope": "test",
        "stats": {"background_count": 1, "confidence_counts": {"high": 1}},
        "backgrounds": [
            {
                "card_id": "nlm-test-background",
                "old_front_text": "Hvad tester kortet nlm-test-background?",
                "old_back_text": "Det tester, at full NotebookLM-kort kan gøres til Freudd-kort.",
                "background_text": (
                    "Trækpsykologi forstår personlighed gennem stabile træk og måling på tværs af personer. "
                    "Derfor er træk og måling centrale begreber, når svaret kobles til teoriens personbegreb."
                ),
                "theory_names": ["Trækpsykologi"],
                "concept_terms": ["træk", "måling"],
                "support": [
                    {
                        "type": "matrix_field",
                        "theory_id": "trait_and_assessment_psychology",
                        "field": "model_of_person",
                    }
                ],
                "confidence": "high",
            }
        ],
    }

    deck = full_cards.build_full_notebooklm_deck(
        candidate_payloads=payloads,
        source_file="runs/test/candidates + backgrounds.json",
        source_sha256=full_cards.source_fingerprint(payloads, background_payloads=[backgrounds]),
        background_payloads=[backgrounds],
        generated_at="2026-05-26T00:00:00Z",
    )

    card = deck["cards"][0]
    assert card["background_text"].startswith("Trækpsykologi forstår")
    assert "background" in card["tags"]
    assert deck["card_backgrounds"]["applied_count"] == 1


def test_background_overlay_fails_closed_when_front_is_stale():
    payloads = [
        _payload(
            notebook_slug="global-calibration-synthesis",
            candidates=[_candidate("nlm-test-background-stale", "candidate")],
        )
    ]
    backgrounds = {
        "version": 1,
        "artifact_type": "personlighedspsykologi_flashcard_background_overlays",
        "subject_slug": "personlighedspsykologi",
        "generated_at": "2026-05-26T00:00:00Z",
        "scope": "test",
        "stats": {"background_count": 1, "confidence_counts": {"high": 1}},
        "backgrounds": [
            {
                "card_id": "nlm-test-background-stale",
                "old_front_text": "Et gammelt spørgsmål?",
                "old_back_text": "Det tester, at full NotebookLM-kort kan gøres til Freudd-kort.",
                "background_text": (
                    "Trækpsykologi forstår personlighed gennem stabile træk og måling på tværs af personer. "
                    "Derfor er træk og måling centrale begreber, når svaret kobles til teoriens personbegreb."
                ),
                "theory_names": ["Trækpsykologi"],
                "concept_terms": ["træk", "måling"],
                "support": [
                    {
                        "type": "matrix_field",
                        "theory_id": "trait_and_assessment_psychology",
                        "field": "model_of_person",
                    }
                ],
                "confidence": "high",
            }
        ],
    }

    try:
        full_cards.build_full_notebooklm_deck(
            candidate_payloads=payloads,
            source_file="runs/test/candidates + backgrounds.json",
            source_sha256=full_cards.source_fingerprint(payloads, background_payloads=[backgrounds]),
            background_payloads=[backgrounds],
            generated_at="2026-05-26T00:00:00Z",
        )
    except full_cards.FullNotebookLMFlashcardError as exc:
        assert "old_front_text is stale" in str(exc)
    else:
        raise AssertionError("Expected stale background overlay to fail")


def test_background_overlay_rejects_generic_card_meta_language():
    payloads = [
        _payload(
            notebook_slug="global-calibration-synthesis",
            candidates=[_candidate("nlm-test-background-generic", "candidate")],
        )
    ]
    backgrounds = {
        "version": 1,
        "artifact_type": "personlighedspsykologi_flashcard_background_overlays",
        "subject_slug": "personlighedspsykologi",
        "generated_at": "2026-05-26T00:00:00Z",
        "scope": "test",
        "stats": {"background_count": 1, "confidence_counts": {"high": 1}},
        "backgrounds": [
            {
                "card_id": "nlm-test-background-generic",
                "old_front_text": "Hvad tester kortet nlm-test-background-generic?",
                "old_back_text": "Det tester, at full NotebookLM-kort kan gøres til Freudd-kort.",
                "background_text": (
                    "Kortet træner en generel sammenligning, hvor træk og måling nævnes uden at forklare "
                    "den faglige mekanisme bag svaret."
                ),
                "theory_names": ["Trækpsykologi"],
                "concept_terms": ["træk", "måling"],
                "support": [
                    {
                        "type": "matrix_field",
                        "theory_id": "trait_and_assessment_psychology",
                        "field": "model_of_person",
                    }
                ],
                "confidence": "high",
            }
        ],
    }

    try:
        full_cards.build_full_notebooklm_deck(
            candidate_payloads=payloads,
            source_file="runs/test/candidates + backgrounds.json",
            source_sha256=full_cards.source_fingerprint(payloads, background_payloads=[backgrounds]),
            background_payloads=[backgrounds],
            generated_at="2026-05-26T00:00:00Z",
        )
    except full_cards.FullNotebookLMFlashcardError as exc:
        assert "Generic coaching background text" in str(exc)
    else:
        raise AssertionError("Expected generic background wording to fail")


def test_build_single_deck_registry_exposes_only_full_notebooklm_deck():
    registry = full_cards.build_single_deck_registry(
        artifact_path="shows/personlighedspsykologi-en/flashcards/notebooklm-fuld-matrix-personlighedspsykologi.json",
        card_count=234,
    )

    assert registry["subject_slug"] == "personlighedspsykologi"
    assert len(registry["decks"]) == 1
    assert registry["decks"][0]["deck_slug"] == full_cards.FULL_NOTEBOOKLM_DECK_SLUG
    assert registry["decks"][0]["enabled"] is True


def test_full_deck_can_include_reviewed_gap_repair_candidates():
    base_payload = _payload(
        notebook_slug="global-calibration-synthesis",
        candidates=[_candidate("nlm-test-accepted", "candidate")],
    )
    repair_payload = {
        "version": 1,
        "artifact_type": "personlighedspsykologi_notebooklm_flashcard_candidates",
        "subject_slug": "personlighedspsykologi",
        "run_id": "gap-repair-test",
        "notebook_slug": "gap-repair-promoted",
        "source_path": "gap_repair_review_decisions",
        "stats": {"candidate_count": 1},
        "candidates": [
            {
                **_candidate("nlm-gap-repair-accepted", "candidate"),
                "notebook_slug": "gap-repair-comparisons-traps",
                "tags": ["notebooklm-gap-repair"],
            }
        ],
    }

    deck = full_cards.build_full_notebooklm_deck(
        candidate_payloads=[base_payload, repair_payload],
        source_file="runs/test/candidates + gap_repair_review_decisions.json",
        source_sha256=full_cards.source_fingerprint([base_payload, repair_payload]),
        generated_at="2026-05-26T00:00:00Z",
    )

    assert deck["card_count"] == 2
    repair_card = next(card for card in deck["cards"] if card["card_id"] == "nlm-gap-repair-accepted")
    assert "notebooklm-gap-repair" in repair_card["tags"]
    assert deck["run_ids"] == ["full-matrix-test", "gap-repair-test"]


def test_full_deck_can_include_coverage_closure_candidates():
    base_payload = _payload(
        notebook_slug="global-calibration-synthesis",
        candidates=[_candidate("nlm-test-accepted", "candidate")],
    )
    closure_payload = {
        "version": 1,
        "artifact_type": "personlighedspsykologi_notebooklm_flashcard_candidates",
        "subject_slug": "personlighedspsykologi",
        "run_id": "coverage-closure-current",
        "notebook_slug": "coverage-closure",
        "source_path": "coverage_closure_flashcards.json",
        "stats": {"candidate_count": 1},
        "candidates": [
            {
                **_candidate("nlm-coverage-closure-test", "candidate"),
                "notebook_slug": "coverage-closure",
                "tags": ["deterministic-coverage-closure", "coverage:strengths"],
            }
        ],
    }

    deck = full_cards.build_full_notebooklm_deck(
        candidate_payloads=[base_payload, closure_payload],
        source_file="runs/test/candidates + coverage_closure_flashcards.json",
        source_sha256=full_cards.source_fingerprint([base_payload, closure_payload]),
        generated_at="2026-05-26T00:00:00Z",
    )

    assert deck["card_count"] == 2
    closure_card = next(card for card in deck["cards"] if card["card_id"] == "nlm-coverage-closure-test")
    assert "deterministic-coverage-closure" in closure_card["tags"]
    assert deck["run_ids"] == ["coverage-closure-current", "full-matrix-test"]
