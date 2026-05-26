from notebooklm_queue import personlighedspsykologi_coverage_closure_flashcards as closure


def _matrix() -> dict[str, object]:
    return {
        "subject_slug": "personlighedspsykologi",
        "rows": [
            {
                "theory_id": "test_theory",
                "label": "Testteori",
                "course_summary": "A compact test row.",
                "model_of_person": "Person as test subject.",
                "personality_or_subjectivity_model": "Subjectivity through testing.",
                "method_evidence_style": "Interpretive comparison and source triangulation.",
                "central_concepts": ["agency"],
                "strengths": ["Shows why deterministic closure matters."],
                "limitations": ["Can become too mechanical if detached from review."],
                "source_note_basis": [
                    {"note_id": "student_note", "summary": "Adds an exam nuance about source basis."}
                ],
            }
        ],
    }


def _coverage_report() -> dict[str, object]:
    return {
        "rows": [
            {
                "theory_id": "test_theory",
                "units": [
                    {
                        "unit_id": "test_theory:method_evidence_style",
                        "status": "missing",
                        "confidence": "high",
                        "best_overlap": 0,
                        "card_ids": [],
                    },
                    {
                        "unit_id": "test_theory:strengths:1",
                        "status": "missing",
                        "confidence": "high",
                        "best_overlap": 0,
                        "card_ids": [],
                    },
                    {
                        "unit_id": "test_theory:source_note_basis:student_note",
                        "status": "weak",
                        "confidence": "medium",
                        "best_overlap": 0.01,
                        "card_ids": ["existing-card"],
                    },
                ],
            }
        ],
    }


def test_build_coverage_closure_artifact_targets_missing_and_weak_units():
    artifact = closure.build_coverage_closure_artifact(
        matrix=_matrix(),
        coverage_report=_coverage_report(),
        generated_at="2026-05-26T00:00:00Z",
    )

    assert artifact["artifact_type"] == closure.COVERAGE_CLOSURE_ARTIFACT_TYPE
    assert artifact["stats"]["card_count"] == 3
    assert artifact["stats"]["field_counts"] == {
        "method_evidence_style": 1,
        "source_note_basis": 1,
        "strengths": 1,
    }
    cards = {card["target_coverage_unit"]["unit_id"]: card for card in artifact["cards"]}
    assert cards["test_theory:method_evidence_style"]["category_slug"] == "metode-og-evidens"
    assert cards["test_theory:strengths:1"]["category_slug"] == "styrker-og-begraensninger"
    assert cards["test_theory:source_note_basis:student_note"]["category_slug"] == "personbegreb"
    assert "coverage-status:weak" in cards["test_theory:source_note_basis:student_note"]["tags"]


def test_coverage_closure_artifact_can_be_folded_into_candidate_payload():
    artifact = closure.build_coverage_closure_artifact(
        matrix=_matrix(),
        coverage_report=_coverage_report(),
        generated_at="2026-05-26T00:00:00Z",
    )
    payload = closure.coverage_closure_to_candidate_payload(artifact)

    assert payload["artifact_type"] == "personlighedspsykologi_notebooklm_flashcard_candidates"
    assert payload["notebook_slug"] == "coverage-closure"
    assert payload["stats"]["candidate_count"] == 3
    assert all(candidate["review_status"] == "candidate" for candidate in payload["candidates"])


def test_coverage_closure_markdown_renders_reviewable_targets():
    artifact = closure.build_coverage_closure_artifact(
        matrix=_matrix(),
        coverage_report=_coverage_report(),
        generated_at="2026-05-26T00:00:00Z",
    )
    markdown = closure.render_coverage_closure_markdown(artifact)

    assert "# Coverage Closure Flashcards" in markdown
    assert "test_theory:method_evidence_style" in markdown
