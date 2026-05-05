"""Validation helpers for recursive Source Intelligence artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

RECURSIVE_SOURCE_INTELLIGENCE_SCHEMA_VERSION = 1


class SourceIntelligenceValidationError(ValueError):
    """Raised when an LLM-derived source-intelligence artifact is malformed."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _type_name(value: object) -> str:
    return type(value).__name__


def _require_dict(payload: object, path: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SourceIntelligenceValidationError(f"{path} must be an object, got {_type_name(payload)}")
    return payload


def _require_list(payload: object, path: str) -> list[Any]:
    if not isinstance(payload, list):
        raise SourceIntelligenceValidationError(f"{path} must be a list, got {_type_name(payload)}")
    return payload


def _require_nonempty_string(payload: object, path: str) -> str:
    if not isinstance(payload, str) or not payload.strip():
        raise SourceIntelligenceValidationError(f"{path} must be a non-empty string")
    return payload.strip()


def _require_optional_string(payload: object, path: str) -> str:
    if payload is None:
        return ""
    if not isinstance(payload, str):
        raise SourceIntelligenceValidationError(f"{path} must be a string")
    return payload.strip()


def _require_common(payload: object, artifact_type: str) -> dict[str, Any]:
    artifact = _require_dict(payload, "$")
    actual_type = _require_nonempty_string(artifact.get("artifact_type"), "$.artifact_type")
    if actual_type != artifact_type:
        raise SourceIntelligenceValidationError(
            f"$.artifact_type must be {artifact_type!r}, got {actual_type!r}"
        )
    version = artifact.get("schema_version")
    if version != RECURSIVE_SOURCE_INTELLIGENCE_SCHEMA_VERSION:
        raise SourceIntelligenceValidationError(
            "$.schema_version must be "
            f"{RECURSIVE_SOURCE_INTELLIGENCE_SCHEMA_VERSION}, got {version!r}"
        )
    _require_nonempty_string(artifact.get("subject_slug"), "$.subject_slug")
    _require_nonempty_string(artifact.get("generated_at"), "$.generated_at")
    build = _require_dict(artifact.get("build"), "$.build")
    _require_nonempty_string(build.get("model"), "$.build.model")
    _require_nonempty_string(build.get("prompt_version"), "$.build.prompt_version")
    provenance = _require_dict(artifact.get("provenance"), "$.provenance")
    _require_list(provenance.get("input_source_ids"), "$.provenance.input_source_ids")
    _require_dict(provenance.get("dependency_hashes"), "$.provenance.dependency_hashes")
    return artifact


def validate_source_card(payload: object) -> dict[str, Any]:
    artifact = _require_common(payload, "source_card")
    source = _require_dict(artifact.get("source"), "$.source")
    _require_nonempty_string(source.get("source_id"), "$.source.source_id")
    _require_nonempty_string(source.get("lecture_key"), "$.source.lecture_key")
    _require_nonempty_string(source.get("title"), "$.source.title")
    _require_nonempty_string(source.get("source_family"), "$.source.source_family")
    _require_nonempty_string(source.get("evidence_origin"), "$.source.evidence_origin")
    _require_optional_string(source.get("source_sha256"), "$.source.source_sha256")
    analysis = _require_dict(artifact.get("analysis"), "$.analysis")
    _require_list(analysis.get("central_claims"), "$.analysis.central_claims")
    _require_list(analysis.get("key_concepts"), "$.analysis.key_concepts")
    _require_list(analysis.get("distinctions"), "$.analysis.distinctions")
    _require_optional_string(analysis.get("theory_role"), "$.analysis.theory_role")
    _require_optional_string(analysis.get("source_role"), "$.analysis.source_role")
    _require_optional_string(analysis.get("relation_to_lecture"), "$.analysis.relation_to_lecture")
    _require_list(analysis.get("likely_misunderstandings"), "$.analysis.likely_misunderstandings")
    _require_list(analysis.get("quote_targets"), "$.analysis.quote_targets")
    _require_list(analysis.get("grounding_notes"), "$.analysis.grounding_notes")
    _require_list(analysis.get("warnings"), "$.analysis.warnings")
    return artifact


def validate_lecture_substrate(payload: object) -> dict[str, Any]:
    artifact = _require_common(payload, "lecture_substrate")
    lecture = _require_dict(artifact.get("lecture"), "$.lecture")
    _require_nonempty_string(lecture.get("lecture_key"), "$.lecture.lecture_key")
    _require_nonempty_string(lecture.get("lecture_title"), "$.lecture.lecture_title")
    analysis = _require_dict(artifact.get("analysis"), "$.analysis")
    _require_nonempty_string(analysis.get("lecture_question"), "$.analysis.lecture_question")
    _require_nonempty_string(analysis.get("central_learning_problem"), "$.analysis.central_learning_problem")
    _require_list(analysis.get("source_roles"), "$.analysis.source_roles")
    _require_list(analysis.get("source_relations"), "$.analysis.source_relations")
    _require_list(analysis.get("core_concepts"), "$.analysis.core_concepts")
    _require_list(analysis.get("core_tensions"), "$.analysis.core_tensions")
    _require_list(analysis.get("likely_misunderstandings"), "$.analysis.likely_misunderstandings")
    _require_list(analysis.get("must_carry_ideas"), "$.analysis.must_carry_ideas")
    _require_list(analysis.get("missing_sources"), "$.analysis.missing_sources")
    _require_list(analysis.get("warnings"), "$.analysis.warnings")
    return artifact


def validate_course_synthesis(payload: object) -> dict[str, Any]:
    artifact = _require_common(payload, "course_synthesis")
    course = _require_dict(artifact.get("course"), "$.course")
    _require_nonempty_string(course.get("course_title"), "$.course.course_title")
    analysis = _require_dict(artifact.get("analysis"), "$.analysis")
    _require_nonempty_string(analysis.get("course_arc"), "$.analysis.course_arc")
    _require_list(analysis.get("theory_tradition_map"), "$.analysis.theory_tradition_map")
    _require_list(analysis.get("concept_map"), "$.analysis.concept_map")
    _require_list(analysis.get("distinction_map"), "$.analysis.distinction_map")
    _require_list(analysis.get("sideways_relations"), "$.analysis.sideways_relations")
    _require_list(analysis.get("lecture_clusters"), "$.analysis.lecture_clusters")
    _require_list(analysis.get("top_down_priorities"), "$.analysis.top_down_priorities")
    _require_list(analysis.get("weak_spots"), "$.analysis.weak_spots")
    _require_list(analysis.get("podcast_generation_guidance"), "$.analysis.podcast_generation_guidance")
    return artifact


def validate_revised_lecture_substrate(payload: object) -> dict[str, Any]:
    artifact = _require_common(payload, "revised_lecture_substrate")
    lecture = _require_dict(artifact.get("lecture"), "$.lecture")
    _require_nonempty_string(lecture.get("lecture_key"), "$.lecture.lecture_key")
    _require_nonempty_string(lecture.get("lecture_title"), "$.lecture.lecture_title")
    analysis = _require_dict(artifact.get("analysis"), "$.analysis")
    _require_list(analysis.get("what_matters_more"), "$.analysis.what_matters_more")
    _require_list(analysis.get("de_emphasize"), "$.analysis.de_emphasize")
    _require_list(analysis.get("strongest_sideways_connections"), "$.analysis.strongest_sideways_connections")
    _require_nonempty_string(analysis.get("top_down_course_relevance"), "$.analysis.top_down_course_relevance")
    _require_list(analysis.get("revised_podcast_priorities"), "$.analysis.revised_podcast_priorities")
    _require_list(analysis.get("carry_forward"), "$.analysis.carry_forward")
    _require_list(analysis.get("warnings"), "$.analysis.warnings")
    return artifact


def validate_podcast_substrate(payload: object) -> dict[str, Any]:
    artifact = _require_common(payload, "podcast_substrate")
    lecture = _require_dict(artifact.get("lecture"), "$.lecture")
    _require_nonempty_string(lecture.get("lecture_key"), "$.lecture.lecture_key")
    _require_nonempty_string(lecture.get("lecture_title"), "$.lecture.lecture_title")
    podcast = _require_dict(artifact.get("podcast"), "$.podcast")
    _require_dict(podcast.get("weekly"), "$.podcast.weekly")
    _require_list(podcast.get("per_reading"), "$.podcast.per_reading")
    _require_list(podcast.get("per_slide"), "$.podcast.per_slide")
    _require_dict(podcast.get("short"), "$.podcast.short")
    _require_list(podcast.get("selected_concepts"), "$.podcast.selected_concepts")
    _require_list(podcast.get("selected_tensions"), "$.podcast.selected_tensions")
    _require_list(podcast.get("grounding_notes"), "$.podcast.grounding_notes")
    _require_list(podcast.get("source_selection"), "$.podcast.source_selection")
    return artifact

