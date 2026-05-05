import pytest

from notebooklm_queue import source_intelligence_schemas as schemas


def _base_artifact(artifact_type):
    return {
        "artifact_type": artifact_type,
        "schema_version": schemas.RECURSIVE_SOURCE_INTELLIGENCE_SCHEMA_VERSION,
        "subject_slug": "personlighedspsykologi",
        "generated_at": "2026-05-05T00:00:00Z",
        "build": {
            "model": "gemini-3.1-pro-preview",
            "prompt_version": "test",
        },
        "provenance": {
            "input_source_ids": ["source-1"],
            "dependency_hashes": {"source": "abc"},
        },
    }


def test_validate_source_card_accepts_minimal_valid_payload():
    payload = {
        **_base_artifact("source_card"),
        "source": {
            "source_id": "source-1",
            "lecture_key": "W01L1",
            "title": "Source",
            "source_family": "reading",
            "evidence_origin": "reading_grounded",
            "source_sha256": "abc",
        },
        "analysis": {
            "central_claims": [{"claim": "A grounded claim."}],
            "key_concepts": [{"term": "lived experience"}],
            "distinctions": [],
            "theory_role": "",
            "source_role": "Anchor source.",
            "relation_to_lecture": "Supports the lecture.",
            "likely_misunderstandings": [],
            "quote_targets": [],
            "grounding_notes": [],
            "warnings": [],
        },
    }

    assert schemas.validate_source_card(payload) is payload


def test_validate_source_card_rejects_wrong_artifact_type():
    payload = _base_artifact("lecture_substrate")

    with pytest.raises(schemas.SourceIntelligenceValidationError):
        schemas.validate_source_card(payload)


def test_validate_source_card_rejects_empty_semantic_payload():
    payload = {
        **_base_artifact("source_card"),
        "source": {
            "source_id": "source-1",
            "lecture_key": "W01L1",
            "title": "Source",
            "source_family": "reading",
            "evidence_origin": "reading_grounded",
            "source_sha256": "abc",
        },
        "analysis": {
            "central_claims": [],
            "key_concepts": [],
            "distinctions": [],
            "theory_role": "",
            "source_role": "",
            "relation_to_lecture": "",
            "likely_misunderstandings": [],
            "quote_targets": [],
            "grounding_notes": [],
            "warnings": [],
        },
    }

    with pytest.raises(schemas.SourceIntelligenceValidationError, match="central_claims"):
        schemas.validate_source_card(payload)


def test_validate_source_card_rejects_template_placeholder_payload():
    payload = {
        **_base_artifact("source_card"),
        "source": {
            "source_id": "source-1",
            "lecture_key": "W01L1",
            "title": "Source",
            "source_family": "reading",
            "evidence_origin": "reading_grounded",
            "source_sha256": "abc",
        },
        "analysis": {
            "central_claims": [{}],
            "key_concepts": [{}],
            "distinctions": [{}],
            "theory_role": "the source's role in a theory/tradition map",
            "source_role": "how this source should be used in the lecture",
            "relation_to_lecture": "how it serves the lecture problem",
            "likely_misunderstandings": ["student misunderstanding to avoid"],
            "quote_targets": [{}],
            "grounding_notes": ["source-grounding or evidence-origin caveat"],
            "warnings": ["quality caveats, OCR caveats, or empty list"],
        },
    }

    with pytest.raises(schemas.SourceIntelligenceValidationError, match="placeholder|meaningful"):
        schemas.validate_source_card(payload)
