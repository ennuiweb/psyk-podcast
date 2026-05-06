"""Experimental schema-v3 scaffold generation for printout review runs."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import importlib.util
from copy import deepcopy
from collections.abc import Callable
from pathlib import Path
from typing import Any

from notebooklm_queue.gemini_preprocessing import (
    DEFAULT_GEMINI_PREPROCESSING_MODEL,
    GeminiPreprocessingBackend,
    generate_json,
    generation_config_metadata,
    make_gemini_backend,
)
from notebooklm_queue.source_intelligence_schemas import utc_now_iso

try:
    from notebooklm_queue import personlighedspsykologi_recursive as recursive
except ImportError:
    _RECURSIVE_PATH = Path(__file__).resolve().parents[5] / "notebooklm_queue" / "personlighedspsykologi_recursive.py"
    _RECURSIVE_SPEC = importlib.util.spec_from_file_location("personlighedspsykologi_recursive", _RECURSIVE_PATH)
    assert _RECURSIVE_SPEC and _RECURSIVE_SPEC.loader
    recursive = importlib.util.module_from_spec(_RECURSIVE_SPEC)
    _RECURSIVE_SPEC.loader.exec_module(recursive)

SUBJECT_SLUG = recursive.SUBJECT_SLUG
DEFAULT_SOURCE_CATALOG = recursive.DEFAULT_SOURCE_CATALOG
DEFAULT_SOURCE_CARD_DIR = recursive.DEFAULT_SOURCE_CARD_DIR
DEFAULT_REVISED_LECTURE_SUBSTRATE_DIR = recursive.DEFAULT_REVISED_LECTURE_SUBSTRATE_DIR
DEFAULT_COURSE_SYNTHESIS_PATH = recursive.DEFAULT_COURSE_SYNTHESIS_PATH
DEFAULT_SUBJECT_ROOT = recursive.DEFAULT_SUBJECT_ROOT
DEFAULT_OUTPUT_ROOT = Path("notebooklm-podcast-auto/personlighedspsykologi/output")
PROMPT_VERSION = "personlighedspsykologi-reading-printouts-v3"
SCHEMA_VERSION = 3
LEGACY_SCHEMA_VERSION = 2
CANONICAL_PRINTOUT_DIRNAME = "printouts"
LEGACY_PRINTOUT_DIRNAME = "scaffolding"
CANONICAL_PRINTOUT_JSON_NAME = "reading-printouts.json"
LEGACY_PRINTOUT_JSON_NAME = "reading-scaffolds.json"

JsonGenerator = Callable[..., dict[str, Any]]
UserPromptBuilder = Callable[..., str]


class PrintoutError(RuntimeError):
    """Raised when a printable printout cannot be generated or rendered."""


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def source_card_path(source_card_dir: Path, source_id: str) -> Path:
    return source_card_dir / f"{source_id}.json"


def output_dir_for_source(output_root: Path, source: dict[str, Any]) -> Path:
    lecture_key = str(source.get("lecture_key") or "UNKNOWN").strip().upper() or "UNKNOWN"
    source_id = str(source.get("source_id") or "source").strip()
    return output_root / lecture_key / CANONICAL_PRINTOUT_DIRNAME / source_id


def legacy_output_dir_for_source(output_root: Path, source: dict[str, Any]) -> Path:
    lecture_key = str(source.get("lecture_key") or "UNKNOWN").strip().upper() or "UNKNOWN"
    source_id = str(source.get("source_id") or "source").strip()
    return output_root / lecture_key / LEGACY_PRINTOUT_DIRNAME / source_id


def _copy_printout_tree(*, source_dir: Path, target_dir: Path, legacy_json_name: bool = False) -> None:
    if not source_dir.exists():
        return
    target_dir.mkdir(parents=True, exist_ok=True)
    for child in source_dir.iterdir():
        if not child.is_file():
            continue
        target_name = child.name
        if legacy_json_name and child.name == CANONICAL_PRINTOUT_JSON_NAME:
            target_name = LEGACY_PRINTOUT_JSON_NAME
        elif not legacy_json_name and child.name == LEGACY_PRINTOUT_JSON_NAME:
            target_name = CANONICAL_PRINTOUT_JSON_NAME
        target_path = target_dir / target_name
        if child.suffix.lower() in {".json", ".md"}:
            target_path.write_text(child.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            target_path.write_bytes(child.read_bytes())


def _promote_legacy_printouts_if_present(*, canonical_out_dir: Path, legacy_out_dir: Path) -> None:
    legacy_json_path = legacy_out_dir / LEGACY_PRINTOUT_JSON_NAME
    canonical_json_path = canonical_out_dir / CANONICAL_PRINTOUT_JSON_NAME
    if canonical_json_path.exists() or not legacy_json_path.exists():
        return
    _copy_printout_tree(source_dir=legacy_out_dir, target_dir=canonical_out_dir, legacy_json_name=False)


def _sync_legacy_printout_aliases(*, canonical_out_dir: Path, legacy_out_dir: Path) -> None:
    _copy_printout_tree(source_dir=canonical_out_dir, target_dir=legacy_out_dir, legacy_json_name=True)


def select_sources(
    *,
    source_catalog_path: Path,
    lecture_keys: list[str] | None = None,
    source_ids: list[str] | None = None,
    source_families: set[str] | None = None,
) -> list[dict[str, Any]]:
    catalog = read_json(source_catalog_path)
    if not isinstance(catalog, dict):
        raise PrintoutError(f"invalid source catalog: {source_catalog_path}")
    normalized_lectures = set(recursive.normalize_lecture_keys(",".join(lecture_keys or [])))
    normalized_source_ids = {item.strip() for item in source_ids or [] if item.strip()}
    selected: list[dict[str, Any]] = []
    for source in catalog.get("sources", []):
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("source_id") or "").strip()
        source_family = str(source.get("source_family") or "").strip()
        lecture_values = set(recursive.normalize_lecture_keys(str(source.get("lecture_key") or "")))
        for value in source.get("lecture_keys", []) or []:
            lecture_values.update(recursive.normalize_lecture_keys(str(value or "")))
        if normalized_source_ids and source_id not in normalized_source_ids:
            continue
        if normalized_lectures and not lecture_values.intersection(normalized_lectures):
            continue
        if source_families is not None and source_family not in source_families:
            continue
        if not source.get("source_exists", False):
            continue
        selected.append(source)
    return sorted(
        selected,
        key=lambda item: (
            str(item.get("lecture_key") or ""),
            int(item.get("sequence_index") or 0),
            str(item.get("source_id") or ""),
        ),
    )


def _compact_source_card(source_card: dict[str, Any]) -> dict[str, Any]:
    analysis = source_card.get("analysis") if isinstance(source_card.get("analysis"), dict) else {}
    return {
        "source": source_card.get("source", {}),
        "analysis": {
            "theory_role": analysis.get("theory_role", ""),
            "source_role": analysis.get("source_role", ""),
            "relation_to_lecture": analysis.get("relation_to_lecture", ""),
            "central_claims": analysis.get("central_claims", [])[:6],
            "key_concepts": analysis.get("key_concepts", [])[:8],
            "distinctions": analysis.get("distinctions", [])[:6],
            "likely_misunderstandings": analysis.get("likely_misunderstandings", [])[:5],
            "quote_targets": analysis.get("quote_targets", [])[:4],
            "grounding_notes": analysis.get("grounding_notes", [])[:4],
        },
    }


def _load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    payload = read_json(path)
    return payload if isinstance(payload, dict) else None


def _compact_lecture_context(revised_substrate_dir: Path, lecture_key: str) -> dict[str, Any] | None:
    payload = _load_optional_json(revised_substrate_dir / f"{lecture_key}.json")
    if payload is None:
        return None
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    return {
        "lecture_key": lecture_key,
        "what_matters_more": analysis.get("what_matters_more", [])[:5],
        "de_emphasize": analysis.get("de_emphasize", [])[:4],
        "strongest_sideways_connections": analysis.get("strongest_sideways_connections", [])[:5],
        "top_down_course_relevance": analysis.get("top_down_course_relevance", ""),
        "carry_forward": analysis.get("carry_forward", [])[:5],
    }


def _compact_course_context(course_synthesis_path: Path) -> dict[str, Any] | None:
    payload = _load_optional_json(course_synthesis_path)
    if payload is None:
        return None
    analysis = payload.get("analysis") if isinstance(payload.get("analysis"), dict) else {}
    return {
        "scope": payload.get("scope", {}),
        "course_arc": analysis.get("course_arc", ""),
        "top_down_priorities": analysis.get("top_down_priorities", [])[:8],
        "sideways_relations": analysis.get("sideways_relations", [])[:8],
        "weak_spots": analysis.get("weak_spots", [])[:5],
    }


def _string_schema() -> dict[str, str]:
    return {"type": "string"}


def _string_list_schema(*, min_items: int = 0, max_items: int | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "array", "items": _string_schema()}
    if min_items:
        schema["minItems"] = min_items
    # Gemini rejects maxItems in response schemas; upper bounds are enforced locally.
    return schema


def _object_list_schema(
    *,
    properties: dict[str, Any],
    required: list[str],
    min_items: int = 0,
    max_items: int | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "array",
        "items": {"type": "object", "properties": properties, "required": required},
    }
    if min_items:
        schema["minItems"] = min_items
    # Gemini rejects maxItems in response schemas; upper bounds are enforced locally.
    return schema


def scaffold_response_schema() -> dict[str, Any]:
    quote_anchor = {
        "phrase": _string_schema(),
        "why_it_matters": _string_schema(),
        "source_location": _string_schema(),
    }
    quote_target = {
        "target": _string_schema(),
        "why": _string_schema(),
        "where_to_look": _string_schema(),
    }
    route_item = {
        "number": _string_schema(),
        "source_location": _string_schema(),
        "task": _string_schema(),
        "why_it_matters": _string_schema(),
        "stop_signal": _string_schema(),
    }
    abridged_section = {
        "number": _string_schema(),
        "source_location": _string_schema(),
        "heading": _string_schema(),
        "explanation_paragraphs": _string_list_schema(min_items=2, max_items=5),
        "key_points": _string_list_schema(min_items=1, max_items=5),
        "quote_anchors": _object_list_schema(
            properties=quote_anchor,
            required=["phrase", "why_it_matters", "source_location"],
            min_items=0,
            max_items=3,
        ),
        "no_quote_anchor_needed": _string_schema(),
        "source_touchpoint_source_location": _string_schema(),
        "source_touchpoint_task": _string_schema(),
        "source_touchpoint_answer_or_marking_format": _string_schema(),
        "source_touchpoint_stop_signal": _string_schema(),
        "mini_check_question": _string_schema(),
        "mini_check_answer_shape": _string_schema(),
        "mini_check_done_signal": _string_schema(),
    }
    abridged_check = {
        "number": _string_schema(),
        "question": _string_schema(),
        "abridged_reader_location": _string_schema(),
        "answer_shape": _string_schema(),
        "done_signal": _string_schema(),
    }
    source_touchpoint = {
        "number": _string_schema(),
        "source_location": _string_schema(),
        "task": _string_schema(),
        "answer_or_marking_format": _string_schema(),
        "stop_signal": _string_schema(),
        "why_this_touchpoint": _string_schema(),
    }
    cloze_sentence = {
        "number": _string_schema(),
        "sentence": _string_schema(),
        "where_to_look": _string_schema(),
        "answer_shape": _string_schema(),
    }
    diagram_task = {
        "number": _string_schema(),
        "task": _string_schema(),
        "required_elements": _string_list_schema(min_items=2, max_items=6),
        "blank_space_hint": _string_schema(),
    }
    course_connection = {
        "course_theme": _string_schema(),
        "connection": _string_schema(),
    }
    comparison_target = {
        "compare_with": _string_schema(),
        "how_to_compare": _string_schema(),
    }
    exam_move = {
        "prompt_type": _string_schema(),
        "use_in_answer": _string_schema(),
        "caution": _string_schema(),
    }
    misunderstanding_trap = {
        "trap": _string_schema(),
        "better_reading": _string_schema(),
    }
    return {
        "type": "object",
        "properties": {
            "metadata": {
                "type": "object",
                "properties": {
                    "language": _string_schema(),
                    "source_id": _string_schema(),
                    "lecture_key": _string_schema(),
                    "source_title": _string_schema(),
                },
                "required": ["language", "source_id", "lecture_key", "source_title"],
            },
            "reading_guide": {
                "type": "object",
                "properties": {
                    "title": _string_schema(),
                    "how_to_use": _string_schema(),
                    "why_this_text_matters": _string_schema(),
                    "overview": _string_list_schema(min_items=3, max_items=3),
                    "reading_route": _object_list_schema(
                        properties=route_item,
                        required=["number", "source_location", "task", "why_it_matters", "stop_signal"],
                        min_items=3,
                        max_items=7,
                    ),
                    "key_quote_targets": _object_list_schema(
                        properties=quote_target,
                        required=["target", "why", "where_to_look"],
                        min_items=3,
                        max_items=4,
                    ),
                    "do_not_get_stuck_on": _string_list_schema(min_items=2, max_items=5),
                },
                "required": [
                    "title",
                    "how_to_use",
                    "why_this_text_matters",
                    "overview",
                    "reading_route",
                    "key_quote_targets",
                    "do_not_get_stuck_on",
                ],
            },
            "abridged_reader": {
                "type": "object",
                "properties": {
                    "title": _string_schema(),
                    "how_to_use": _string_schema(),
                    "coverage_note": _string_schema(),
                    "sections": _object_list_schema(
                        properties=abridged_section,
                        required=[
                            "number",
                            "source_location",
                            "heading",
                            "explanation_paragraphs",
                            "key_points",
                            "quote_anchors",
                            "no_quote_anchor_needed",
                            "source_touchpoint_source_location",
                            "source_touchpoint_task",
                            "source_touchpoint_answer_or_marking_format",
                            "source_touchpoint_stop_signal",
                            "mini_check_question",
                            "mini_check_answer_shape",
                            "mini_check_done_signal",
                        ],
                        min_items=3,
                        max_items=9,
                    ),
                },
                "required": ["title", "how_to_use", "coverage_note", "sections"],
            },
            "active_reading": {
                "type": "object",
                "properties": {
                    "title": _string_schema(),
                    "instructions": _string_schema(),
                    "abridged_checks": _object_list_schema(
                        properties=abridged_check,
                        required=["number", "question", "abridged_reader_location", "answer_shape", "done_signal"],
                        min_items=8,
                        max_items=12,
                    ),
                    "source_touchpoints": _object_list_schema(
                        properties=source_touchpoint,
                        required=[
                            "number",
                            "source_location",
                            "task",
                            "answer_or_marking_format",
                            "stop_signal",
                            "why_this_touchpoint",
                        ],
                        min_items=5,
                        max_items=8,
                    ),
                },
                "required": ["title", "instructions", "abridged_checks", "source_touchpoints"],
            },
            "consolidation_sheet": {
                "type": "object",
                "properties": {
                    "title": _string_schema(),
                    "overview": _string_list_schema(min_items=3, max_items=3),
                    "fill_in_sentences": _object_list_schema(
                        properties=cloze_sentence,
                        required=["number", "sentence", "where_to_look", "answer_shape"],
                        min_items=5,
                        max_items=8,
                    ),
                    "diagram_tasks": _object_list_schema(
                        properties=diagram_task,
                        required=["number", "task", "required_elements", "blank_space_hint"],
                        min_items=1,
                        max_items=3,
                    ),
                },
                "required": ["title", "overview", "fill_in_sentences", "diagram_tasks"],
            },
            "exam_bridge": {
                "type": "object",
                "properties": {
                    "title": _string_schema(),
                    "instructions": _string_schema(),
                    "use_this_text_for": _string_list_schema(min_items=3, max_items=6),
                    "course_connections": _object_list_schema(
                        properties=course_connection,
                        required=["course_theme", "connection"],
                        min_items=2,
                        max_items=5,
                    ),
                    "comparison_targets": _object_list_schema(
                        properties=comparison_target,
                        required=["compare_with", "how_to_compare"],
                        min_items=2,
                        max_items=5,
                    ),
                    "exam_moves": _object_list_schema(
                        properties=exam_move,
                        required=["prompt_type", "use_in_answer", "caution"],
                        min_items=3,
                        max_items=6,
                    ),
                    "misunderstanding_traps": _object_list_schema(
                        properties=misunderstanding_trap,
                        required=["trap", "better_reading"],
                        min_items=2,
                        max_items=5,
                    ),
                    "mini_exam_prompt_question": _string_schema(),
                    "mini_exam_answer_plan_slots": _string_list_schema(min_items=3, max_items=5),
                },
                "required": [
                    "title",
                    "instructions",
                    "use_this_text_for",
                    "course_connections",
                    "comparison_targets",
                    "exam_moves",
                    "misunderstanding_traps",
                    "mini_exam_prompt_question",
                    "mini_exam_answer_plan_slots",
                ],
            },
        },
        "required": [
            "metadata",
            "reading_guide",
            "abridged_reader",
            "active_reading",
            "consolidation_sheet",
            "exam_bridge",
        ],
    }


def scaffold_prompt_contract() -> dict[str, Any]:
    """Human-readable JSON contract used when Gemini schema mode is too restrictive."""
    return {
        "top_level_required_keys": [
            "metadata",
            "reading_guide",
            "abridged_reader",
            "active_reading",
            "consolidation_sheet",
            "exam_bridge",
        ],
        "metadata": {
            "required_keys": ["language", "source_id", "lecture_key", "source_title"],
            "language": "da",
        },
        "reading_guide": {
            "required_keys": [
                "title",
                "how_to_use",
                "why_this_text_matters",
                "overview",
                "reading_route",
                "key_quote_targets",
                "do_not_get_stuck_on",
            ],
            "cardinality": {
                "overview": "exactly 3 strings",
                "reading_route": "3-7 objects in source order",
                "key_quote_targets": "3-4 objects",
                "do_not_get_stuck_on": "2-5 strings",
            },
            "reading_route_item_keys": ["number", "source_location", "task", "why_it_matters", "stop_signal"],
            "key_quote_target_keys": ["target", "why", "where_to_look"],
            "quote_target_limit": "target must be max 12 words and max 140 characters",
        },
        "abridged_reader": {
            "required_keys": ["title", "how_to_use", "coverage_note", "sections"],
            "cardinality": {"sections": "3-9 objects in source order"},
            "section_required_keys": [
                "number",
                "source_location",
                "heading",
                "explanation_paragraphs",
                "key_points",
                "quote_anchors",
                "no_quote_anchor_needed",
                "source_touchpoint_source_location",
                "source_touchpoint_task",
                "source_touchpoint_answer_or_marking_format",
                "source_touchpoint_stop_signal",
                "mini_check_question",
                "mini_check_answer_shape",
                "mini_check_done_signal",
            ],
            "section_cardinality": {
                "explanation_paragraphs": "2-5 strings; each paragraph max 95 words",
                "key_points": "1-5 strings",
                "quote_anchors": "0-3 objects; each phrase must be max 12 words and max 140 characters",
            },
            "quote_anchor_keys": ["phrase", "why_it_matters", "source_location"],
        },
        "active_reading": {
            "required_keys": ["title", "instructions", "abridged_checks", "source_touchpoints"],
            "cardinality": {
                "abridged_checks": "8-12 objects answerable from abridged_reader",
                "source_touchpoints": "5-8 objects requiring tiny original-source contact",
            },
            "abridged_check_keys": [
                "number",
                "question",
                "abridged_reader_location",
                "answer_shape",
                "done_signal",
            ],
            "source_touchpoint_keys": [
                "number",
                "source_location",
                "task",
                "answer_or_marking_format",
                "stop_signal",
                "why_this_touchpoint",
            ],
        },
        "consolidation_sheet": {
            "required_keys": ["title", "overview", "fill_in_sentences", "diagram_tasks"],
            "cardinality": {
                "overview": "exactly 3 strings, no blanks",
                "fill_in_sentences": "5-8 objects, each sentence has exactly one __________ blank",
                "diagram_tasks": "1-3 objects",
            },
            "fill_in_sentence_keys": ["number", "sentence", "where_to_look", "answer_shape"],
            "diagram_task_keys": ["number", "task", "required_elements", "blank_space_hint"],
        },
        "exam_bridge": {
            "required_keys": [
                "title",
                "instructions",
                "use_this_text_for",
                "course_connections",
                "comparison_targets",
                "exam_moves",
                "misunderstanding_traps",
                "mini_exam_prompt_question",
                "mini_exam_answer_plan_slots",
            ],
            "cardinality": {
                "use_this_text_for": "3-6 strings",
                "course_connections": "2-5 objects with course_theme and connection",
                "comparison_targets": "2-5 objects with compare_with and how_to_compare",
                "exam_moves": "3-6 objects with prompt_type, use_in_answer, and caution",
                "misunderstanding_traps": "2-5 objects with trap and better_reading",
                "mini_exam_answer_plan_slots": "3-5 strings",
            },
        },
        "global_quality_rules": [
            "All required keys must be present even when a list is short.",
            "Use Danish for student-facing text.",
            "Do not reveal answers in active_reading or consolidation_sheet.",
            "answer_shape fields describe answer format only, never semantic hints.",
            "done_signal and stop_signal must not contain parenthetical answer hints.",
            "Use only short quote anchors; do not reproduce long source passages.",
        ],
    }


def printout_generation_config_metadata() -> dict[str, Any]:
    metadata = generation_config_metadata()
    metadata["response_json_schema"] = None
    metadata["json_contract"] = "prompt_contract_v3_with_local_validation"
    return metadata


def printout_system_instruction() -> str:
    return "\n".join(
        [
            "You generate printable Danish reading scaffolds for Personlighedspsykologi.",
            "Return only valid JSON that matches the output_contract exactly.",
            "Use the attached source file as authority. Use supplied source-card and course context only to prioritize what matters.",
            "The student has ADD and needs offline, short, dopamine-friendly tasks while reading.",
            "The abridged reader is a legitimate minimum viable reading path, not a failure mode.",
            "The original source should become targeted source contact through short source touchpoints, not an all-or-nothing wall.",
            "The output must be a coherent printout kit, not one overloaded everything sheet.",
            "Make every task operational: it should tell the student what to do, where to look, and when to stop.",
            "Do not reveal answers in active-reading checks or consolidation tasks.",
            "Never put the answer inside parentheses in answer_shape, locations, done_signal, or stop_signal.",
            "answer_shape must describe only the answer format, e.g. '1 ord', '2 ord', 'et navn', or 'en kort sætning'. Do not add semantic hints.",
            "A done_signal should say when to stop, for example 'når du har skrevet gruppen', not what the group is.",
            "Do not make broad essay prompts, vague blanks, or questions that can be answered without reading the source.",
            "Respect copyright: use only short quote anchors or short phrase targets, never long reproduced passages.",
            "Quote anchors and quote targets must be max 12 words and max 140 characters.",
            "Abridged-reader prose should be 80-90% rewritten explanation and 10-20% short original anchors/page references.",
            "Prefer concrete Danish wording and avoid generic study-skills language.",
            "Use a serious, practical university-student tone. Avoid hype, motivational language, and childish metaphors.",
        ]
    )


def printout_user_prompt(
    *,
    source: dict[str, Any],
    source_card: dict[str, Any],
    lecture_context: dict[str, Any] | None,
    course_context: dict[str, Any] | None,
) -> str:
    payload = {
        "source_metadata": source,
        "source_card": _compact_source_card(source_card),
        "lecture_context": lecture_context,
        "course_context": course_context,
        "output_contract": scaffold_prompt_contract(),
        "required_outputs": {
            "reading_guide": [
                "A one-page advance organizer in Danish.",
                "Explain why this text matters for the lecture/course before detail.",
                "Include a chronological reading route with concrete stop signals.",
                "Include exactly 3-4 short quote targets or short phrases the student should look for.",
                "Include 2-5 things the student should not get stuck on.",
            ],
            "abridged_reader": [
                "An ADHD-friendly shortened reading path, in Danish, that can serve as the student's minimum viable reading.",
                "Preserve the source's argument movement in source order.",
                "Use short paragraphs, section headings, page/source anchors, and bullets where helpful.",
                "Mostly rewrite and explain; include only short quote anchors or quote fragments where exact wording matters.",
                "Every section must include source_location, explanation_paragraphs, key_points, quote_anchors or no_quote_anchor_needed, source_touchpoint_* fields, and mini_check_* fields.",
                "The reader should be strong enough to support consolidation and exam transfer if the student cannot read the full source.",
            ],
            "active_reading": [
                "Split active reading into abridged_checks and source_touchpoints.",
                "abridged_checks: 8-12 checks answerable from the abridged reader.",
                "source_touchpoints: 5-8 tiny original-source hunts for high-value passages, definitions, examples, and quote anchors.",
                "Source touchpoints should not ask the student to read long sections; make them open-source-find-one-thing tasks.",
                "Do not include answers.",
                "answer_shape must describe form only, not meaning. Good: '2 ord'. Bad: '2 ord der beskriver mistillid'.",
                "done_signal and stop_signal must never contain the answer or a parenthetical hint with the answer.",
                "Avoid 'discuss', 'reflect on', broad comparison questions, and questions that require whole-text synthesis.",
            ],
            "consolidation_sheet": [
                "Three-sentence overview of what the text is about; do not put blanks in this overview.",
                "5-8 fill-in-the-blank sentences where one key term, distinction, result, or connection is removed.",
                "Each blank must be narrow enough that the intended answer is findable in the text.",
                "Each fill-in sentence must include where_to_look and a form-only answer_shape, but not the answer.",
                "1-3 blank diagram tasks; describe what to draw but do not draw it.",
                "Each diagram task must list required_elements.",
                "Leave all answer fields blank and do not explain answers.",
            ],
            "exam_bridge": [
                "A transfer worksheet, in Danish, that makes the reading usable for exam answers.",
                "Include where this source is useful, course connections, comparison targets, exam moves, misunderstanding traps, and a mini exam prompt.",
                "Use concrete course language and avoid generic exam-advice filler.",
                "Do not include a full model answer.",
            ],
        },
    }
    return (
        "Generate printable printout outputs for the attached source file.\n"
        "Use Danish for student-facing text.\n"
        "Here is the source/context payload:\n\n"
        f"{json.dumps(payload, indent=2, ensure_ascii=False)}"
    )


def _coerce_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _looks_like_answer_leak(text: str, *, forbid_parentheses: bool = False) -> bool:
    lowered = text.lower()
    if forbid_parentheses and ("(" in text or ")" in text):
        return True
    return (
        "svaret er" in lowered
        or "answer is" in lowered
        or "fx:" in lowered
        or "f.eks.:" in lowered
    )


def _blank_count(text: str) -> int:
    return len(re.findall(r"_{3,}", text))


def _require_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise PrintoutError(f"scaffold field must not be empty: {field_name}")
    return text


def _reject_broad_prompt(text: str, field_name: str) -> None:
    lowered = text.lower()
    broad_patterns = (
        r"^\s*(diskuter|reflekter|perspektiver|vurder|sammenlign)\b",
        r"^\s*analyser\s+hvordan\b",
        r"\bhvad\s+mener\s+du\b",
        r"\btag\s+stilling\b",
        r"\bovervej\b",
    )
    if any(re.search(pattern, lowered) for pattern in broad_patterns):
        raise PrintoutError(f"{field_name} is too broad for a reading micro-task")


def _require_safe_task_hint(value: Any, field_name: str, *, forbid_parentheses: bool = False) -> str:
    text = _require_text(value, field_name)
    if _looks_like_answer_leak(text, forbid_parentheses=forbid_parentheses):
        raise PrintoutError(f"{field_name} must not reveal the answer")
    return text


def _require_answer_shape(value: Any, field_name: str) -> str:
    text = _require_safe_task_hint(value, field_name)
    if len(text) > 80:
        raise PrintoutError(f"{field_name} must describe answer format only")
    lowered = text.lower()
    semantic_hint_patterns = (
        r"\bder\b",
        r"\bsom\b",
        r"\bom\b",
        r"\bbeskriver\b",
        r"\bforklarer\b",
        r"\bhentet\s+fra\b",
        r"\bhandler\s+om\b",
        r"\binden\s+for\b",
    )
    if any(re.search(pattern, lowered) for pattern in semantic_hint_patterns):
        raise PrintoutError(f"{field_name} must describe answer format only")
    if re.search(r"\bfor\b", lowered):
        raise PrintoutError(f"{field_name} must describe answer format only")
    return text


def _normalize_answer_shape(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return text
    text = re.sub(r"\([^)]*\)", "", text).strip()
    text = re.sub(r"\([^)]*$", "", text).strip()
    text = re.sub(r"\s+(der|som|om)\b.*$", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\s+inden\s+for\b.*$", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\s+hentet\s+fra\b.*$", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\s+handler\s+om\b.*$", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"\s+for\b.*$", "", text, flags=re.IGNORECASE).strip()
    text = text.rstrip(" .;:")
    return text if text else str(value or "").strip()


def _normalize_quote_anchor(value: Any, *, max_words: int = 12, max_chars: int = 140) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return text
    words = text.split()
    if len(words) > max_words:
        text = " ".join(words[:max_words])
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0].strip() or text[:max_chars].strip()
    return text.strip(" .,;:")


def _normalize_question_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text or text.endswith("?"):
        return text
    return text.rstrip(" .;:!") + "?"


def _normalize_stop_signal(value: Any, *, fallback: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"\[[^\]]*\]", "", text)
    text = re.sub(r"\s+", " ", text).strip(" .;:")
    return text or fallback


def _split_required_element_text(value: str) -> list[str]:
    text = re.sub(r"\s+", " ", value.strip())
    if not text:
        return []
    text = re.sub(r"^[\s:.-]*(fx|f\.eks\.|elementer|begreber)\s*[:.-]\s*", "", text, flags=re.IGNORECASE)
    parts = re.split(r"\s*(?:,|;|/|→|->|\bog\b|\bsamt\b|\bvs\.?\b|\bversus\b)\s*", text, flags=re.IGNORECASE)
    return [part.strip(" .:;()[]") for part in parts if part.strip(" .:;()[]")]


def _clean_required_element_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if text.count("(") > text.count(")"):
        text = text.replace("(", ": ")
    if text.count(")") > text.count("("):
        text = text.replace(")", "")
    text = text.replace(" :", ":")
    text = re.sub(r":\s*:", ":", text)
    return text.strip(" .:;[]")


def _short_required_element_fragment(text: str) -> bool:
    return 1 <= _word_count(text) <= 3 and len(text) <= 36


def _should_merge_required_element_fragment(previous: str, current: str) -> bool:
    previous_lower = previous.casefold().strip()
    current_lower = current.casefold().strip()
    if previous_lower in {"pile", "pile,", "pile:"} and current_lower.startswith("der "):
        return True
    if current_lower.startswith("pile"):
        return False
    if previous_lower.endswith((" med", " uden", " og", " der viser")):
        return True
    if ":" not in previous or not _short_required_element_fragment(current):
        return False
    merge_prefixes = (
        "2 rækker",
        "3 kolonner",
        "akser",
        "de tre",
        "de fire",
        "deres",
        "det midterste",
        "det nederste",
        "det øverste",
        "en boks",
        "en fordelingskurve",
        "en markering",
        "en x-akse",
        "en y-akse",
        "navnet",
        "række ",
        "to elementer",
        "to kolonner",
    )
    return previous_lower.startswith(merge_prefixes)


def _split_embedded_required_elements(items: list[str]) -> list[str]:
    split_items: list[str] = []
    for item in items:
        match = re.search(r",\s+(Pile(?:\s+der\b.*)?)$", item)
        if match:
            prefix = item[: match.start()].strip(" ,")
            suffix = match.group(1).strip()
            if prefix:
                split_items.append(prefix)
            if suffix:
                split_items.append(suffix)
            continue
        split_items.append(item)
    return split_items


def _repair_required_element_fragments(items: list[str]) -> list[str]:
    repaired: list[str] = []
    for item in items:
        text = _clean_required_element_text(item)
        if not text:
            continue
        if repaired and _should_merge_required_element_fragment(repaired[-1], text):
            separator = " " if repaired[-1].casefold().strip() == "pile" else ", "
            repaired[-1] = f"{repaired[-1]}{separator}{text}".strip()
            continue
        repaired.append(text)
    return _split_embedded_required_elements(repaired)


def _extract_required_elements_from_task(task: Any) -> list[str]:
    text = re.sub(r"\s+", " ", str(task or "").strip())
    if not text:
        return []
    quoted = re.findall(r"['\"“”‘’]([^'\"“”‘’]{2,60})['\"“”‘’]", text)
    elements: list[str] = []
    for item in quoted:
        elements.extend(_split_required_element_text(item))
    if elements:
        return elements
    match = re.search(r"\bmellem\s+(.+?)(?:\.|$)", text, flags=re.IGNORECASE)
    if match:
        elements.extend(_split_required_element_text(match.group(1)))
    match = re.search(r"\b(?:forholdet|relationen)\s+(.+?)(?:\.|$)", text, flags=re.IGNORECASE)
    if match:
        elements.extend(_split_required_element_text(match.group(1)))
    return elements


def _normalize_required_elements(value: Any, *, task: Any) -> list[str]:
    elements: list[str] = []
    if isinstance(value, list):
        raw_items: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = str(item.get("term") or item.get("name") or item.get("label") or "").strip()
            else:
                text = str(item or "").strip()
            if text:
                raw_items.append(text)
        if len(raw_items) == 1:
            elements.extend(_split_required_element_text(raw_items[0]) or [_clean_required_element_text(raw_items[0])])
        else:
            elements.extend(_repair_required_element_fragments(raw_items))
    elif isinstance(value, str):
        elements.extend(_split_required_element_text(value))
    if len(elements) < 2:
        elements.extend(_extract_required_elements_from_task(task))
    unique: list[str] = []
    seen: set[str] = set()
    for element in elements:
        cleaned = re.sub(r"\s+", " ", str(element or "").strip(" .:;()[]"))
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(cleaned)
    return unique[:6]


def _normalize_exam_moves(value: Any) -> list[dict[str, str]]:
    moves = [dict(item) for item in _coerce_list(value) if isinstance(item, dict)]
    defaults = [
        {
            "prompt_type": "definer",
            "use_in_answer": "Brug teksten til at definere dens centrale begreb eller position præcist.",
            "caution": "Hold definitionen knyttet til teksten, ikke til en løs hverdagsforståelse.",
        },
        {
            "prompt_type": "sammenlign",
            "use_in_answer": "Brug teksten som kontrast til en anden tilgang fra kurset.",
            "caution": "Undgå karikatur; sammenlign på antagelser, metode eller menneskesyn.",
        },
        {
            "prompt_type": "diskuter",
            "use_in_answer": "Brug teksten til at nuancere styrker, begrænsninger eller anvendelse.",
            "caution": "Skriv ikke et generelt essay; bind diskussionen til tekstens konkrete pointe.",
        },
    ]
    existing = {str(item.get("prompt_type") or "").strip().casefold() for item in moves}
    for default in defaults:
        if len(moves) >= 3:
            break
        if default["prompt_type"].casefold() not in existing:
            moves.append(default)
            existing.add(default["prompt_type"].casefold())
    return moves[:6]


def normalize_v2_scaffold_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(payload)
    tests = normalized.get("unit_test_suite") if isinstance(normalized.get("unit_test_suite"), dict) else {}
    for item in _coerce_list(tests.get("questions")):
        if isinstance(item, dict) and "answer_shape" in item:
            item["answer_shape"] = _normalize_answer_shape(item.get("answer_shape"))
    cloze = normalized.get("cloze_scaffold") if isinstance(normalized.get("cloze_scaffold"), dict) else {}
    for item in _coerce_list(cloze.get("fill_in_sentences")):
        if isinstance(item, dict) and "answer_shape" in item:
            item["answer_shape"] = _normalize_answer_shape(item.get("answer_shape"))
    return normalized


def normalize_scaffold_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(payload)
    guide = normalized.get("reading_guide") if isinstance(normalized.get("reading_guide"), dict) else {}
    for item in _coerce_list(guide.get("key_quote_targets")):
        if isinstance(item, dict) and "target" in item:
            item["target"] = _normalize_quote_anchor(item.get("target"))
    for item in _coerce_list(guide.get("reading_route")):
        if isinstance(item, dict) and "stop_signal" in item:
            item["stop_signal"] = _normalize_stop_signal(
                item.get("stop_signal"),
                fallback="Stop når du har skrevet en kort note",
            )
    active = normalized.get("active_reading") if isinstance(normalized.get("active_reading"), dict) else {}
    for item in _coerce_list(active.get("abridged_checks")):
        if isinstance(item, dict) and "answer_shape" in item:
            item["answer_shape"] = _normalize_answer_shape(item.get("answer_shape"))
    reader = normalized.get("abridged_reader") if isinstance(normalized.get("abridged_reader"), dict) else {}
    for section in _coerce_list(reader.get("sections")):
        if not isinstance(section, dict):
            continue
        for anchor in _coerce_list(section.get("quote_anchors")):
            if isinstance(anchor, dict) and "phrase" in anchor:
                anchor["phrase"] = _normalize_quote_anchor(anchor.get("phrase"))
        if "mini_check_answer_shape" in section:
            section["mini_check_answer_shape"] = _normalize_answer_shape(section.get("mini_check_answer_shape"))
        if "mini_check_question" in section:
            section["mini_check_question"] = _normalize_question_text(section.get("mini_check_question"))
        if "source_touchpoint_stop_signal" in section:
            section["source_touchpoint_stop_signal"] = _normalize_stop_signal(
                section.get("source_touchpoint_stop_signal"),
                fallback="Stop når du har fundet punktet",
            )
        if "mini_check_done_signal" in section:
            section["mini_check_done_signal"] = _normalize_stop_signal(
                section.get("mini_check_done_signal"),
                fallback="Stop når du har skrevet et kort svar",
            )
    consolidation = (
        normalized.get("consolidation_sheet")
        if isinstance(normalized.get("consolidation_sheet"), dict)
        else {}
    )
    for item in _coerce_list(consolidation.get("fill_in_sentences")):
        if isinstance(item, dict) and "answer_shape" in item:
            item["answer_shape"] = _normalize_answer_shape(item.get("answer_shape"))
    for item in _coerce_list(consolidation.get("diagram_tasks")):
        if isinstance(item, dict):
            item["required_elements"] = _normalize_required_elements(
                item.get("required_elements"),
                task=item.get("task"),
            )
    for item in _coerce_list(active.get("abridged_checks")):
        if not isinstance(item, dict):
            continue
        if "question" in item:
            item["question"] = _normalize_question_text(item.get("question"))
        if "done_signal" in item:
            item["done_signal"] = _normalize_stop_signal(
                item.get("done_signal"),
                fallback="Stop når du har skrevet et kort svar",
            )
    for item in _coerce_list(active.get("source_touchpoints")):
        if isinstance(item, dict) and "stop_signal" in item:
            item["stop_signal"] = _normalize_stop_signal(
                item.get("stop_signal"),
                fallback="Stop når du har fundet punktet",
            )
    exam_bridge = normalized.get("exam_bridge") if isinstance(normalized.get("exam_bridge"), dict) else {}
    if isinstance(exam_bridge, dict):
        exam_bridge["exam_moves"] = _normalize_exam_moves(exam_bridge.get("exam_moves"))
    return normalized


def _number_label(item: dict[str, Any], fallback: int) -> str:
    value = str(item.get("number") or "").strip().rstrip(".")
    return value or str(fallback)


def validate_v2_scaffold_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise PrintoutError("scaffold payload must be a JSON object")
    for key in ("metadata", "abridged_guide", "unit_test_suite", "cloze_scaffold"):
        if not isinstance(payload.get(key), dict):
            raise PrintoutError(f"scaffold payload missing object: {key}")
    guide = payload["abridged_guide"]
    tests = payload["unit_test_suite"]
    cloze = payload["cloze_scaffold"]
    guide_overview = _coerce_list(guide.get("overview"))
    structure_map = _coerce_list(guide.get("structure_map"))
    quote_targets = _coerce_list(guide.get("key_quote_targets"))
    questions = _coerce_list(tests.get("questions"))
    fill_ins = _coerce_list(cloze.get("fill_in_sentences"))
    diagrams = _coerce_list(cloze.get("diagram_tasks"))
    overview = _coerce_list(cloze.get("overview"))
    if len(guide_overview) != 3:
        raise PrintoutError("abridged guide must include a three-sentence overview")
    _require_text(guide.get("title"), "abridged_guide.title")
    _require_text(guide.get("how_to_use"), "abridged_guide.how_to_use")
    _require_text(guide.get("why_this_text_matters"), "abridged_guide.why_this_text_matters")
    _require_text(tests.get("title"), "unit_test_suite.title")
    _require_text(tests.get("instructions"), "unit_test_suite.instructions")
    _require_text(cloze.get("title"), "cloze_scaffold.title")
    if not 3 <= len(structure_map) <= 7:
        raise PrintoutError("abridged guide must include 3-7 structure-map items")
    if not 3 <= len(quote_targets) <= 4:
        raise PrintoutError("abridged guide must include 3-4 quote targets")
    if not 2 <= len(_coerce_list(guide.get("do_not_get_stuck_on"))) <= 5:
        raise PrintoutError("abridged guide must include 2-5 do-not-get-stuck-on items")
    if not 15 <= len(questions) <= 20:
        raise PrintoutError("unit-test suite must include 15-20 questions")
    if len(overview) != 3:
        raise PrintoutError("cloze scaffold must include a three-sentence overview")
    if not 5 <= len(fill_ins) <= 8:
        raise PrintoutError("cloze scaffold must include 5-8 fill-in sentences")
    if not 1 <= len(diagrams) <= 3:
        raise PrintoutError("cloze scaffold must include 1-3 diagram tasks")
    for item in guide_overview + overview:
        if "____" in str(item):
            raise PrintoutError("overview sentences must not contain blanks")
    for index, item in enumerate(structure_map, start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each structure-map item must be an object")
        _require_text(item.get("number"), f"abridged_guide.structure_map[{index}].number")
        _require_text(item.get("section_hint"), f"abridged_guide.structure_map[{index}].section_hint")
        _require_text(item.get("what_to_get"), f"abridged_guide.structure_map[{index}].what_to_get")
        _require_text(item.get("why_it_matters"), f"abridged_guide.structure_map[{index}].why_it_matters")
        _require_safe_task_hint(item.get("stop_after"), f"abridged_guide.structure_map[{index}].stop_after")
    for index, item in enumerate(quote_targets, start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each quote target must be an object")
        target = _require_text(item.get("target"), f"abridged_guide.key_quote_targets[{index}].target")
        if len(target) > 140:
            raise PrintoutError("quote targets must be short search phrases, not reproduced passages")
        _require_text(item.get("why"), f"abridged_guide.key_quote_targets[{index}].why")
        _require_text(item.get("where_to_look"), f"abridged_guide.key_quote_targets[{index}].where_to_look")
    for index, item in enumerate(questions, start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each unit-test question must be an object")
        _require_text(item.get("number"), f"unit_test_suite.questions[{index}].number")
        question = _require_text(item.get("question"), f"unit_test_suite.questions[{index}].question")
        if not question.endswith("?"):
            raise PrintoutError("each unit-test question must be phrased as a question")
        if len(question) > 220:
            raise PrintoutError("unit-test questions must stay short and concrete")
        _reject_broad_prompt(question, "unit-test question")
        _require_safe_task_hint(item.get("where_to_look"), f"unit_test_suite.questions[{index}].where_to_look")
        _require_answer_shape(item.get("answer_shape"), f"unit_test_suite.questions[{index}].answer_shape")
        _require_safe_task_hint(
            item.get("done_signal"),
            f"unit_test_suite.questions[{index}].done_signal",
            forbid_parentheses=True,
        )
    for index, item in enumerate(fill_ins, start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each cloze sentence must be an object")
        _require_text(item.get("number"), f"cloze_scaffold.fill_in_sentences[{index}].number")
        sentence = str(item.get("sentence") if isinstance(item, dict) else item)
        if _blank_count(sentence) != 1:
            raise PrintoutError("each cloze sentence must contain exactly one blank marker")
        if len(sentence) > 220:
            raise PrintoutError("cloze sentences must stay short enough for print use")
        _reject_broad_prompt(sentence, "cloze sentence")
        _require_safe_task_hint(item.get("where_to_look"), f"cloze_scaffold.fill_in_sentences[{index}].where_to_look")
        _require_answer_shape(item.get("answer_shape"), f"cloze_scaffold.fill_in_sentences[{index}].answer_shape")
    for index, item in enumerate(diagrams, start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each diagram task must be an object")
        _require_text(item.get("number"), f"cloze_scaffold.diagram_tasks[{index}].number")
        _reject_broad_prompt(_require_text(item.get("task"), f"cloze_scaffold.diagram_tasks[{index}].task"), "diagram task")
        _require_text(item.get("blank_space_hint"), f"cloze_scaffold.diagram_tasks[{index}].blank_space_hint")
        elements = _coerce_list(item.get("required_elements")) if isinstance(item, dict) else []
        if len(elements) < 2:
            raise PrintoutError("each diagram task must include at least two required elements")
        for element in elements:
            _require_text(element, f"cloze_scaffold.diagram_tasks[{index}].required_elements[]")
    return payload


def _require_object(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PrintoutError(f"scaffold payload missing object: {field_name}")
    return value


def _require_count(items: list[Any], field_name: str, minimum: int, maximum: int) -> None:
    if not minimum <= len(items) <= maximum:
        raise PrintoutError(f"{field_name} must include {minimum}-{maximum} items")


def _word_count(text: str) -> int:
    return len([part for part in re.split(r"\s+", text.strip()) if part])


def _require_short_quote_anchor(value: Any, field_name: str) -> str:
    text = _require_text(value, field_name)
    if len(text) > 180 or _word_count(text) > 18:
        raise PrintoutError(f"{field_name} must be a short quote anchor, not a reproduced passage")
    return text


def _validate_v3_reading_guide(guide: dict[str, Any]) -> None:
    _require_text(guide.get("title"), "reading_guide.title")
    _require_text(guide.get("how_to_use"), "reading_guide.how_to_use")
    _require_text(guide.get("why_this_text_matters"), "reading_guide.why_this_text_matters")
    overview = _coerce_list(guide.get("overview"))
    route = _coerce_list(guide.get("reading_route"))
    quote_targets = _coerce_list(guide.get("key_quote_targets"))
    stuck_items = _coerce_list(guide.get("do_not_get_stuck_on"))
    if len(overview) != 3:
        raise PrintoutError("reading guide must include a three-sentence overview")
    _require_count(route, "reading_guide.reading_route", 3, 7)
    _require_count(quote_targets, "reading_guide.key_quote_targets", 3, 4)
    _require_count(stuck_items, "reading_guide.do_not_get_stuck_on", 2, 5)
    for item in overview:
        if "____" in str(item):
            raise PrintoutError("reading guide overview must not contain blanks")
    for index, item in enumerate(route, start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each reading-route item must be an object")
        _require_text(item.get("number"), f"reading_guide.reading_route[{index}].number")
        _require_text(item.get("source_location"), f"reading_guide.reading_route[{index}].source_location")
        _require_text(item.get("task"), f"reading_guide.reading_route[{index}].task")
        _require_text(item.get("why_it_matters"), f"reading_guide.reading_route[{index}].why_it_matters")
        _require_safe_task_hint(item.get("stop_signal"), f"reading_guide.reading_route[{index}].stop_signal")
    for index, item in enumerate(quote_targets, start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each reading-guide quote target must be an object")
        _require_short_quote_anchor(item.get("target"), f"reading_guide.key_quote_targets[{index}].target")
        _require_text(item.get("why"), f"reading_guide.key_quote_targets[{index}].why")
        _require_text(item.get("where_to_look"), f"reading_guide.key_quote_targets[{index}].where_to_look")


def _validate_v3_abridged_reader(reader: dict[str, Any]) -> None:
    _require_text(reader.get("title"), "abridged_reader.title")
    _require_text(reader.get("how_to_use"), "abridged_reader.how_to_use")
    _require_text(reader.get("coverage_note"), "abridged_reader.coverage_note")
    sections = _coerce_list(reader.get("sections"))
    _require_count(sections, "abridged_reader.sections", 3, 9)
    for index, item in enumerate(sections, start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each abridged-reader section must be an object")
        _require_text(item.get("number"), f"abridged_reader.sections[{index}].number")
        _require_text(item.get("source_location"), f"abridged_reader.sections[{index}].source_location")
        _require_text(item.get("heading"), f"abridged_reader.sections[{index}].heading")
        paragraphs = _coerce_list(item.get("explanation_paragraphs"))
        key_points = _coerce_list(item.get("key_points"))
        quote_anchors = _coerce_list(item.get("quote_anchors"))
        _require_count(paragraphs, f"abridged_reader.sections[{index}].explanation_paragraphs", 2, 5)
        _require_count(key_points, f"abridged_reader.sections[{index}].key_points", 1, 5)
        if len(quote_anchors) > 3:
            raise PrintoutError("each abridged-reader section may include at most 3 quote anchors")
        if not quote_anchors:
            _require_text(
                item.get("no_quote_anchor_needed"),
                f"abridged_reader.sections[{index}].no_quote_anchor_needed",
            )
        for paragraph in paragraphs:
            text = _require_text(paragraph, f"abridged_reader.sections[{index}].explanation_paragraphs[]")
            if _word_count(text) > 95:
                raise PrintoutError("abridged-reader paragraphs must stay short")
        for anchor_index, anchor in enumerate(quote_anchors, start=1):
            if not isinstance(anchor, dict):
                raise PrintoutError("each quote anchor must be an object")
            _require_short_quote_anchor(
                anchor.get("phrase"),
                f"abridged_reader.sections[{index}].quote_anchors[{anchor_index}].phrase",
            )
            _require_text(
                anchor.get("why_it_matters"),
                f"abridged_reader.sections[{index}].quote_anchors[{anchor_index}].why_it_matters",
            )
            _require_text(
                anchor.get("source_location"),
                f"abridged_reader.sections[{index}].quote_anchors[{anchor_index}].source_location",
            )
        _require_text(
            item.get("source_touchpoint_source_location"),
            f"abridged_reader.sections[{index}].source_touchpoint_source_location",
        )
        _require_text(item.get("source_touchpoint_task"), f"abridged_reader.sections[{index}].source_touchpoint_task")
        _require_text(
            item.get("source_touchpoint_answer_or_marking_format"),
            f"abridged_reader.sections[{index}].source_touchpoint_answer_or_marking_format",
        )
        _require_safe_task_hint(
            item.get("source_touchpoint_stop_signal"),
            f"abridged_reader.sections[{index}].source_touchpoint_stop_signal",
            forbid_parentheses=True,
        )
        question = _require_text(item.get("mini_check_question"), f"abridged_reader.sections[{index}].mini_check_question")
        if not question.endswith("?"):
            raise PrintoutError("abridged-reader mini checks must be questions")
        _require_answer_shape(
            item.get("mini_check_answer_shape"),
            f"abridged_reader.sections[{index}].mini_check_answer_shape",
        )
        _require_safe_task_hint(
            item.get("mini_check_done_signal"),
            f"abridged_reader.sections[{index}].mini_check_done_signal",
            forbid_parentheses=True,
        )


def _validate_v3_active_reading(active: dict[str, Any]) -> None:
    _require_text(active.get("title"), "active_reading.title")
    _require_text(active.get("instructions"), "active_reading.instructions")
    abridged_checks = _coerce_list(active.get("abridged_checks"))
    source_touchpoints = _coerce_list(active.get("source_touchpoints"))
    _require_count(abridged_checks, "active_reading.abridged_checks", 8, 12)
    _require_count(source_touchpoints, "active_reading.source_touchpoints", 5, 8)
    for index, item in enumerate(abridged_checks, start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each abridged check must be an object")
        _require_text(item.get("number"), f"active_reading.abridged_checks[{index}].number")
        question = _require_text(item.get("question"), f"active_reading.abridged_checks[{index}].question")
        if not question.endswith("?"):
            raise PrintoutError("abridged checks must be phrased as questions")
        _reject_broad_prompt(question, "abridged check")
        _require_text(
            item.get("abridged_reader_location"),
            f"active_reading.abridged_checks[{index}].abridged_reader_location",
        )
        _require_answer_shape(item.get("answer_shape"), f"active_reading.abridged_checks[{index}].answer_shape")
        _require_safe_task_hint(
            item.get("done_signal"),
            f"active_reading.abridged_checks[{index}].done_signal",
            forbid_parentheses=True,
        )
    for index, item in enumerate(source_touchpoints, start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each source touchpoint must be an object")
        _require_text(item.get("number"), f"active_reading.source_touchpoints[{index}].number")
        _require_text(item.get("source_location"), f"active_reading.source_touchpoints[{index}].source_location")
        task = _require_text(item.get("task"), f"active_reading.source_touchpoints[{index}].task")
        if _word_count(task) > 45:
            raise PrintoutError("source touchpoint tasks must stay tiny")
        _require_text(
            item.get("answer_or_marking_format"),
            f"active_reading.source_touchpoints[{index}].answer_or_marking_format",
        )
        _require_safe_task_hint(
            item.get("stop_signal"),
            f"active_reading.source_touchpoints[{index}].stop_signal",
            forbid_parentheses=True,
        )
        _require_text(
            item.get("why_this_touchpoint"),
            f"active_reading.source_touchpoints[{index}].why_this_touchpoint",
        )


def _validate_v3_consolidation(consolidation: dict[str, Any]) -> None:
    _require_text(consolidation.get("title"), "consolidation_sheet.title")
    overview = _coerce_list(consolidation.get("overview"))
    fill_ins = _coerce_list(consolidation.get("fill_in_sentences"))
    diagrams = _coerce_list(consolidation.get("diagram_tasks"))
    if len(overview) != 3:
        raise PrintoutError("consolidation sheet must include a three-sentence overview")
    _require_count(fill_ins, "consolidation_sheet.fill_in_sentences", 5, 8)
    _require_count(diagrams, "consolidation_sheet.diagram_tasks", 1, 3)
    for item in overview:
        if "____" in str(item):
            raise PrintoutError("consolidation overview must not contain blanks")
    for index, item in enumerate(fill_ins, start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each consolidation fill-in sentence must be an object")
        _require_text(item.get("number"), f"consolidation_sheet.fill_in_sentences[{index}].number")
        sentence = str(item.get("sentence") or "")
        if _blank_count(sentence) != 1:
            raise PrintoutError("each consolidation fill-in sentence must contain exactly one blank marker")
        if len(sentence) > 240:
            raise PrintoutError("consolidation fill-in sentences must stay short enough for print use")
        _reject_broad_prompt(sentence, "consolidation fill-in sentence")
        _require_safe_task_hint(
            item.get("where_to_look"),
            f"consolidation_sheet.fill_in_sentences[{index}].where_to_look",
        )
        _require_answer_shape(item.get("answer_shape"), f"consolidation_sheet.fill_in_sentences[{index}].answer_shape")
    for index, item in enumerate(diagrams, start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each consolidation diagram task must be an object")
        _require_text(item.get("number"), f"consolidation_sheet.diagram_tasks[{index}].number")
        _reject_broad_prompt(
            _require_text(item.get("task"), f"consolidation_sheet.diagram_tasks[{index}].task"),
            "consolidation diagram task",
        )
        _require_text(item.get("blank_space_hint"), f"consolidation_sheet.diagram_tasks[{index}].blank_space_hint")
        elements = _coerce_list(item.get("required_elements"))
        if len(elements) < 2:
            raise PrintoutError("each consolidation diagram task must include at least two required elements")
        for element in elements:
            _require_text(element, f"consolidation_sheet.diagram_tasks[{index}].required_elements[]")


def _validate_v3_exam_bridge(exam_bridge: dict[str, Any]) -> None:
    _require_text(exam_bridge.get("title"), "exam_bridge.title")
    _require_text(exam_bridge.get("instructions"), "exam_bridge.instructions")
    _require_count(_coerce_list(exam_bridge.get("use_this_text_for")), "exam_bridge.use_this_text_for", 3, 6)
    _require_count(_coerce_list(exam_bridge.get("course_connections")), "exam_bridge.course_connections", 2, 5)
    _require_count(_coerce_list(exam_bridge.get("comparison_targets")), "exam_bridge.comparison_targets", 2, 5)
    _require_count(_coerce_list(exam_bridge.get("exam_moves")), "exam_bridge.exam_moves", 3, 6)
    _require_count(_coerce_list(exam_bridge.get("misunderstanding_traps")), "exam_bridge.misunderstanding_traps", 2, 5)
    for index, item in enumerate(_coerce_list(exam_bridge.get("course_connections")), start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each exam bridge course connection must be an object")
        _require_text(item.get("course_theme"), f"exam_bridge.course_connections[{index}].course_theme")
        _require_text(item.get("connection"), f"exam_bridge.course_connections[{index}].connection")
    for index, item in enumerate(_coerce_list(exam_bridge.get("comparison_targets")), start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each exam bridge comparison target must be an object")
        _require_text(item.get("compare_with"), f"exam_bridge.comparison_targets[{index}].compare_with")
        _require_text(item.get("how_to_compare"), f"exam_bridge.comparison_targets[{index}].how_to_compare")
    for index, item in enumerate(_coerce_list(exam_bridge.get("exam_moves")), start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each exam bridge move must be an object")
        _require_text(item.get("prompt_type"), f"exam_bridge.exam_moves[{index}].prompt_type")
        _require_text(item.get("use_in_answer"), f"exam_bridge.exam_moves[{index}].use_in_answer")
        _require_text(item.get("caution"), f"exam_bridge.exam_moves[{index}].caution")
    for index, item in enumerate(_coerce_list(exam_bridge.get("misunderstanding_traps")), start=1):
        if not isinstance(item, dict):
            raise PrintoutError("each exam bridge misunderstanding trap must be an object")
        _require_text(item.get("trap"), f"exam_bridge.misunderstanding_traps[{index}].trap")
        _require_text(item.get("better_reading"), f"exam_bridge.misunderstanding_traps[{index}].better_reading")
    _require_text(exam_bridge.get("mini_exam_prompt_question"), "exam_bridge.mini_exam_prompt_question")
    _require_count(_coerce_list(exam_bridge.get("mini_exam_answer_plan_slots")), "exam_bridge.mini_exam_answer_plan_slots", 3, 5)


def validate_printout_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise PrintoutError("scaffold payload must be a JSON object")
    for key in (
        "metadata",
        "reading_guide",
        "abridged_reader",
        "active_reading",
        "consolidation_sheet",
        "exam_bridge",
    ):
        if not isinstance(payload.get(key), dict):
            raise PrintoutError(f"scaffold payload missing object: {key}")
    _validate_v3_reading_guide(payload["reading_guide"])
    _validate_v3_abridged_reader(payload["abridged_reader"])
    _validate_v3_active_reading(payload["active_reading"])
    _validate_v3_consolidation(payload["consolidation_sheet"])
    _validate_v3_exam_bridge(payload["exam_bridge"])
    return payload


def call_json_generator(
    *,
    backend: GeminiPreprocessingBackend | None,
    json_generator: JsonGenerator | None,
    model: str,
    system_instruction: str,
    user_prompt: str,
    source_paths: list[Path],
    max_output_tokens: int,
    response_json_schema: dict[str, Any] | None,
) -> dict[str, Any]:
    if json_generator is not None:
        return json_generator(
            system_instruction=system_instruction,
            user_prompt=user_prompt,
            source_paths=source_paths,
            max_output_tokens=max_output_tokens,
            response_json_schema=response_json_schema,
        )
    active_backend = backend or make_gemini_backend(model=model)
    return generate_json(
        backend=active_backend,
        system_instruction=system_instruction,
        user_prompt=user_prompt,
        source_paths=source_paths,
        max_output_tokens=max_output_tokens,
        response_json_schema=response_json_schema,
    )


def build_printout_for_source(
    *,
    repo_root: Path,
    subject_root: Path,
    source: dict[str, Any],
    source_card_dir: Path,
    revised_lecture_substrate_dir: Path,
    course_synthesis_path: Path,
    output_root: Path,
    model: str = DEFAULT_GEMINI_PREPROCESSING_MODEL,
    backend: GeminiPreprocessingBackend | None = None,
    json_generator: JsonGenerator | None = None,
    render_pdf: bool = True,
    force: bool = False,
    rerender_existing: bool = False,
    prompt_version: str = PROMPT_VERSION,
    system_instruction: str | None = None,
    user_prompt_builder: UserPromptBuilder | None = None,
    variant_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_id = str(source.get("source_id") or "").strip()
    if not source_id:
        raise PrintoutError("source is missing source_id")
    source_paths = recursive.source_file_paths(subject_root, source)
    if not source_paths:
        raise PrintoutError(f"source has no subject_relative_path: {source_id}")
    missing_paths = [path for path in source_paths if not path.exists() or not path.is_file()]
    if missing_paths:
        raise PrintoutError(f"source file not found: {missing_paths[0]}")
    card_path = source_card_path(source_card_dir, source_id)
    if not card_path.exists():
        raise PrintoutError(f"source card not found: {card_path}")
    out_dir = output_dir_for_source(output_root, source)
    legacy_out_dir = legacy_output_dir_for_source(output_root, source)
    _promote_legacy_printouts_if_present(canonical_out_dir=out_dir, legacy_out_dir=legacy_out_dir)
    json_path = out_dir / CANONICAL_PRINTOUT_JSON_NAME
    if rerender_existing and not force and not json_path.exists():
        raise PrintoutError(f"existing printout JSON not found for rerender: {json_path}")
    if json_path.exists() and not force:
        if rerender_existing:
            artifact = read_json(json_path)
            if _artifact_schema_version(artifact) >= SCHEMA_VERSION:
                artifact["schema_version"] = SCHEMA_VERSION
                normalized = validate_printout_payload(
                    normalize_scaffold_payload(artifact.get("printouts") or artifact.get("scaffolds", {}))
                )
                artifact["printouts"] = normalized
                artifact["scaffolds"] = normalized
            else:
                artifact["schema_version"] = LEGACY_SCHEMA_VERSION
                artifact["scaffolds"] = validate_v2_scaffold_payload(
                    normalize_v2_scaffold_payload(artifact.get("scaffolds", {}))
                )
            write_json(json_path, artifact)
            rendered = render_printout_files(artifact=artifact, output_dir=out_dir, render_pdf=render_pdf)
            _sync_legacy_printout_aliases(canonical_out_dir=out_dir, legacy_out_dir=legacy_out_dir)
            return {
                "source_id": source_id,
                "status": "rerendered_existing",
                "output_dir": str(out_dir),
                "json_path": str(json_path),
                "markdown_paths": rendered["markdown_paths"],
                "pdf_paths": rendered["pdf_paths"],
            }
        return {
            "source_id": source_id,
            "status": "skipped_existing",
            "output_dir": str(out_dir),
            "json_path": str(json_path),
            "pdf_paths": _existing_pdf_paths(out_dir),
        }

    source_card = read_json(card_path)
    lecture_key = str(source.get("lecture_key") or source_card.get("source", {}).get("lecture_key") or "").strip()
    response = call_json_generator(
        backend=backend,
        json_generator=json_generator,
        model=model,
        system_instruction=system_instruction or printout_system_instruction(),
        user_prompt=(user_prompt_builder or printout_user_prompt)(
            source=source,
            source_card=source_card,
            lecture_context=_compact_lecture_context(revised_lecture_substrate_dir, lecture_key),
            course_context=_compact_course_context(course_synthesis_path),
        ),
        source_paths=source_paths,
        max_output_tokens=32768,
        response_json_schema=None,
    )
    printouts = validate_printout_payload(normalize_scaffold_payload(response))
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "reading_printouts",
        "subject_slug": SUBJECT_SLUG,
        "generated_at": utc_now_iso(),
        "generator": {
            "provider": "gemini",
            "model": model,
            "prompt_version": prompt_version,
            "generation_config": printout_generation_config_metadata(),
        },
        "provenance": {
            "source_file": recursive.sha256_file(source_paths[0])
            if len(source_paths) == 1
            else recursive.signature_for_files(source_paths),
            "source_files_signature": recursive.signature_for_files(source_paths),
            "source_card": recursive.sha256_file(card_path),
            "revised_lecture_substrate": _sha256_if_exists(revised_lecture_substrate_dir / f"{lecture_key}.json"),
            "course_synthesis": _sha256_if_exists(course_synthesis_path),
        },
        "source": {
            "source_id": source_id,
            "lecture_key": lecture_key,
            "title": str(source.get("title") or ""),
            "source_family": str(source.get("source_family") or ""),
            "evidence_origin": str(source.get("evidence_origin") or ""),
            "source_path": str(source_paths[0].resolve()),
            "source_paths": [str(path.resolve()) for path in source_paths],
            "repo_display_path": recursive.display_path(source_paths[0], repo_root),
            "repo_display_paths": [recursive.display_path(path, repo_root) for path in source_paths],
        },
        "printouts": printouts,
        "scaffolds": printouts,
    }
    if variant_metadata:
        artifact["variant"] = dict(variant_metadata)
    write_json(json_path, artifact)
    rendered = render_printout_files(artifact=artifact, output_dir=out_dir, render_pdf=render_pdf)
    _sync_legacy_printout_aliases(canonical_out_dir=out_dir, legacy_out_dir=legacy_out_dir)
    return {
        "source_id": source_id,
        "status": "written",
        "output_dir": str(out_dir),
        "json_path": str(json_path),
        "markdown_paths": rendered["markdown_paths"],
        "pdf_paths": rendered["pdf_paths"],
    }


def _sha256_if_exists(path: Path) -> str:
    return recursive.sha256_file(path) if path.exists() and path.is_file() else ""


def _existing_pdf_paths(out_dir: Path) -> list[str]:
    return [str(path) for path in sorted(out_dir.glob("*.pdf"))]


def _artifact_schema_version(artifact: dict[str, Any]) -> int:
    try:
        return int(artifact.get("schema_version") or 0)
    except (TypeError, ValueError):
        return 0


def render_printout_files(*, artifact: dict[str, Any], output_dir: Path, render_pdf: bool = True) -> dict[str, list[str]]:
    if _artifact_schema_version(artifact) < SCHEMA_VERSION:
        return render_v2_printout_files(artifact=artifact, output_dir=output_dir, render_pdf=render_pdf)
    return render_v3_printout_files(artifact=artifact, output_dir=output_dir, render_pdf=render_pdf)


def render_v2_printout_files(*, artifact: dict[str, Any], output_dir: Path, render_pdf: bool = True) -> dict[str, list[str]]:
    scaffolds = artifact.get("scaffolds") if isinstance(artifact.get("scaffolds"), dict) else {}
    markdown_items = [
        ("01-abridged-guide", render_abridged_markdown(artifact, scaffolds.get("abridged_guide", {}))),
        ("02-unit-test-suite", render_unit_test_markdown(artifact, scaffolds.get("unit_test_suite", {}))),
        ("03-cloze-scaffold", render_cloze_markdown(artifact, scaffolds.get("cloze_scaffold", {}))),
    ]
    markdown_paths: list[str] = []
    pdf_paths: list[str] = []
    for stem, markdown in markdown_items:
        markdown_path = output_dir / f"{stem}.md"
        write_text(markdown_path, markdown)
        markdown_paths.append(str(markdown_path))
        if render_pdf:
            pdf_path = output_dir / f"{stem}.pdf"
            markdown_to_pdf(markdown_path, pdf_path)
            pdf_paths.append(str(pdf_path))
    return {"markdown_paths": markdown_paths, "pdf_paths": pdf_paths}


def render_v3_printout_files(*, artifact: dict[str, Any], output_dir: Path, render_pdf: bool = True) -> dict[str, list[str]]:
    scaffolds = artifact.get("printouts") if isinstance(artifact.get("printouts"), dict) else {}
    if not scaffolds:
        scaffolds = artifact.get("scaffolds") if isinstance(artifact.get("scaffolds"), dict) else {}
    markdown_items = [
        ("00-reading-guide", render_reading_guide_markdown(artifact, scaffolds.get("reading_guide", {}))),
        ("01-abridged-reader", render_abridged_reader_markdown(artifact, scaffolds.get("abridged_reader", {}))),
        ("02-active-reading", render_active_reading_markdown(artifact, scaffolds.get("active_reading", {}))),
        ("03-consolidation-sheet", render_consolidation_markdown(artifact, scaffolds.get("consolidation_sheet", {}))),
        ("04-exam-bridge", render_exam_bridge_markdown(artifact, scaffolds.get("exam_bridge", {}))),
    ]
    markdown_paths: list[str] = []
    pdf_paths: list[str] = []
    for stem, markdown in markdown_items:
        markdown_path = output_dir / f"{stem}.md"
        write_text(markdown_path, markdown)
        markdown_paths.append(str(markdown_path))
        if render_pdf:
            pdf_path = output_dir / f"{stem}.pdf"
            markdown_to_pdf(markdown_path, pdf_path)
            pdf_paths.append(str(pdf_path))
    return {"markdown_paths": markdown_paths, "pdf_paths": pdf_paths}


def _source_heading(artifact: dict[str, Any]) -> str:
    source = artifact.get("source") if isinstance(artifact.get("source"), dict) else {}
    title = str(source.get("title") or "Ukendt kilde").strip()
    lecture_key = str(source.get("lecture_key") or "").strip()
    return f"**Kilde:** {title}\n\n**Forelæsning:** {lecture_key}"


def _as_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _as_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def render_reading_guide_markdown(artifact: dict[str, Any], guide: dict[str, Any]) -> str:
    lines = [f"# {guide.get('title') or 'Læseguide'}", "", _source_heading(artifact), ""]
    how_to_use = str(guide.get("how_to_use") or "").strip()
    if how_to_use:
        lines.extend(["## Sådan bruger du arket", "", how_to_use, ""])
    why = str(guide.get("why_this_text_matters") or "").strip()
    if why:
        lines.extend(["## Hvorfor teksten er vigtig", "", why, ""])
    lines.extend(["## Tre-sætningsoversigt", ""])
    for sentence in _as_strings(guide.get("overview")):
        lines.append(f"- {sentence}")
    lines.extend(["", "## Læserute", ""])
    for index, item in enumerate(_as_dicts(guide.get("reading_route")), start=1):
        number = _number_label(item, index)
        source_location = str(item.get("source_location") or "").strip()
        task = str(item.get("task") or "").strip()
        why_it_matters = str(item.get("why_it_matters") or "").strip()
        stop_signal = str(item.get("stop_signal") or "").strip()
        lines.append(f"{number}. **{source_location}**")
        lines.append(f"   - Gør: {task}")
        lines.append(f"   - Hvorfor: {why_it_matters}")
        lines.append(f"   - Stop når: {stop_signal}")
        lines.append("")
    lines.extend(["", "## Korte quote-ankre", ""])
    for item in _as_dicts(guide.get("key_quote_targets")):
        target = str(item.get("target") or "").strip()
        why = str(item.get("why") or "").strip()
        where_to_look = str(item.get("where_to_look") or "").strip()
        lines.append(f"- **{target}**: {why}")
        if where_to_look:
            lines.append(f"  - Findes: {where_to_look}")
    stuck_items = _as_strings(guide.get("do_not_get_stuck_on"))
    if stuck_items:
        lines.extend(["", "## Brug ikke for meget energi på", ""])
        for item in stuck_items:
            lines.append(f"- {item}")
    return "\n".join(lines)


def render_abridged_reader_markdown(artifact: dict[str, Any], reader: dict[str, Any]) -> str:
    lines = [f"# {reader.get('title') or 'Abridged reader'}", "", _source_heading(artifact), ""]
    how_to_use = str(reader.get("how_to_use") or "").strip()
    if how_to_use:
        lines.extend(["## Sådan læser du denne version", "", how_to_use, ""])
    coverage_note = str(reader.get("coverage_note") or "").strip()
    if coverage_note:
        lines.extend(["## Hvad denne version gør", "", coverage_note, ""])
    for index, section in enumerate(_as_dicts(reader.get("sections")), start=1):
        number = _number_label(section, index)
        heading = str(section.get("heading") or "").strip()
        source_location = str(section.get("source_location") or "").strip()
        lines.extend(["", f"## {number}. {heading}", "", f"**Kildeanker:** {source_location}", ""])
        for paragraph in _as_strings(section.get("explanation_paragraphs")):
            lines.extend([paragraph, ""])
        key_points = _as_strings(section.get("key_points"))
        if key_points:
            lines.extend(["**Nøglepunkter:**", ""])
            for item in key_points:
                lines.append(f"- {item}")
            lines.append("")
        quote_anchors = _as_dicts(section.get("quote_anchors"))
        if quote_anchors:
            lines.extend(["**Korte originale ankre:**", ""])
            for anchor in quote_anchors:
                phrase = str(anchor.get("phrase") or "").strip()
                why = str(anchor.get("why_it_matters") or "").strip()
                location = str(anchor.get("source_location") or "").strip()
                lines.append(f"- **{phrase}** ({location}): {why}")
            lines.append("")
        lines.extend(["**Hvis du kan åbne originalen i 2 minutter:**", ""])
        lines.append(f"- Gå til: {str(section.get('source_touchpoint_source_location') or '').strip()}")
        lines.append(f"- Gør: {str(section.get('source_touchpoint_task') or '').strip()}")
        lines.append(
            f"- Svar/markering: {str(section.get('source_touchpoint_answer_or_marking_format') or '').strip()}"
        )
        lines.append(f"- Stop når: {str(section.get('source_touchpoint_stop_signal') or '').strip()}")
        lines.append("")
        question = str(section.get("mini_check_question") or "").strip()
        answer_shape = str(section.get("mini_check_answer_shape") or "kort svar").strip()
        done_signal = str(section.get("mini_check_done_signal") or "").strip()
        lines.extend(["**Mini-tjek:**", ""])
        lines.append(f"- {question}")
        lines.append(f"- Svar ({answer_shape}): ______________________________")
        if done_signal:
            lines.append(f"- Stop når: {done_signal}")
        lines.append("")
    return "\n".join(lines)


def render_active_reading_markdown(artifact: dict[str, Any], active: dict[str, Any]) -> str:
    lines = [f"# {active.get('title') or 'Aktiv læsning'}", "", _source_heading(artifact), ""]
    instructions = str(active.get("instructions") or "").strip()
    if instructions:
        lines.extend([instructions, ""])
    lines.extend(["## A. Tjek efter abridged reader", ""])
    for index, item in enumerate(_as_dicts(active.get("abridged_checks")), start=1):
        number = _number_label(item, index)
        question = str(item.get("question") or "").strip()
        location = str(item.get("abridged_reader_location") or "").strip()
        answer_shape = str(item.get("answer_shape") or "kort svar").strip()
        done_signal = str(item.get("done_signal") or "").strip()
        lines.append(f"{number}. [ ] {question}")
        if location:
            lines.append(f"   - Brug: {location}")
        lines.append(f"   - Svar ({answer_shape}): ______________________________")
        if done_signal:
            lines.append(f"   - Stop når: {done_signal}")
        lines.append("")
    lines.extend(["", "## B. Korte source touchpoints", ""])
    for index, item in enumerate(_as_dicts(active.get("source_touchpoints")), start=1):
        number = _number_label(item, index)
        lines.append(f"{number}. [ ] **{str(item.get('source_location') or '').strip()}**")
        lines.append(f"   - Gør: {str(item.get('task') or '').strip()}")
        lines.append(f"   - Svar/markering: {str(item.get('answer_or_marking_format') or '').strip()}")
        lines.append(f"   - Stop når: {str(item.get('stop_signal') or '').strip()}")
        lines.append(f"   - Hvorfor dette punkt: {str(item.get('why_this_touchpoint') or '').strip()}")
        lines.append("")
    return "\n".join(lines)


def render_consolidation_markdown(artifact: dict[str, Any], consolidation: dict[str, Any]) -> str:
    lines = [f"# {consolidation.get('title') or 'Konsolidering'}", "", _source_heading(artifact), ""]
    lines.extend(["## Tre-sætningsoversigt", ""])
    for sentence in _as_strings(consolidation.get("overview")):
        lines.append(f"- {sentence}")
    lines.extend(["", "## Udfyldningssætninger", ""])
    for index, item in enumerate(_as_dicts(consolidation.get("fill_in_sentences")), start=1):
        number = _number_label(item, index)
        sentence = str(item.get("sentence") or "").strip()
        where_to_look = str(item.get("where_to_look") or "").strip()
        answer_shape = str(item.get("answer_shape") or "").strip()
        lines.append(f"{number}. {sentence}")
        details = " | ".join(
            part
            for part in [
                f"Brug: {where_to_look}" if where_to_look else "",
                f"Svarform: {answer_shape}" if answer_shape else "",
            ]
            if part
        )
        if details:
            lines.append(f"   - {details}")
        lines.append("")
    lines.extend(["", "## Tomme diagramopgaver", ""])
    diagram_items = _as_dicts(consolidation.get("diagram_tasks"))
    space_cm = 2.2 if len(diagram_items) == 1 else 1.5 if len(diagram_items) == 2 else 1.0
    for index, item in enumerate(diagram_items, start=1):
        number = _number_label(item, index)
        lines.append(f"{number}. {str(item.get('task') or '').strip()}")
        elements = _as_strings(item.get("required_elements"))
        if elements:
            lines.extend(["", "Diagrammet skal indeholde:"])
            for element in elements:
                lines.append(f"- {element}")
        hint = str(item.get("blank_space_hint") or "Brug feltet nedenfor.").strip()
        lines.extend(["", f"*{hint}*", "", f"\\vspace{{{space_cm:.1f}cm}}", "", "\\hrule", ""])
    return "\n".join(lines)


def render_exam_bridge_markdown(artifact: dict[str, Any], exam_bridge: dict[str, Any]) -> str:
    lines = [f"# {exam_bridge.get('title') or 'Eksamensbro'}", "", _source_heading(artifact), ""]
    instructions = str(exam_bridge.get("instructions") or "").strip()
    if instructions:
        lines.extend([instructions, ""])
    lines.extend(["## Brug teksten når spørgsmålet handler om", ""])
    for item in _as_strings(exam_bridge.get("use_this_text_for")):
        lines.append(f"- {item}")
    lines.extend(["", "## Kursusforbindelser", ""])
    for item in _as_dicts(exam_bridge.get("course_connections")):
        lines.append(f"- **{str(item.get('course_theme') or '').strip()}**: {str(item.get('connection') or '').strip()}")
    lines.extend(["", "## Sammenlign med", ""])
    for item in _as_dicts(exam_bridge.get("comparison_targets")):
        lines.append(f"- **{str(item.get('compare_with') or '').strip()}**: {str(item.get('how_to_compare') or '').strip()}")
    lines.extend(["", "## Eksamensgreb", ""])
    for item in _as_dicts(exam_bridge.get("exam_moves")):
        lines.append(f"- **{str(item.get('prompt_type') or '').strip()}**")
        lines.append(f"  - Brug sådan: {str(item.get('use_in_answer') or '').strip()}")
        lines.append(f"  - Pas på: {str(item.get('caution') or '').strip()}")
    lines.extend(["", "## Misforståelsesfælder", ""])
    for item in _as_dicts(exam_bridge.get("misunderstanding_traps")):
        lines.append(f"- **Fælde:** {str(item.get('trap') or '').strip()}")
        lines.append(f"  - Bedre læsning: {str(item.get('better_reading') or '').strip()}")
    lines.extend(["", "## Mini-eksamensprompt", "", str(exam_bridge.get("mini_exam_prompt_question") or "").strip(), ""])
    lines.append("Svarplan:")
    for item in _as_strings(exam_bridge.get("mini_exam_answer_plan_slots")):
        lines.append(f"- {item}: ______________________________")
    return "\n".join(lines)


def render_abridged_markdown(artifact: dict[str, Any], guide: dict[str, Any]) -> str:
    lines = [f"# {guide.get('title') or 'Forberedende oversigt'}", "", _source_heading(artifact), ""]
    how_to_use = str(guide.get("how_to_use") or "").strip()
    if how_to_use:
        lines.extend(["## Sådan bruger du arket", "", how_to_use, ""])
    why_this_text_matters = str(guide.get("why_this_text_matters") or "").strip()
    if why_this_text_matters:
        lines.extend(["## Hvorfor teksten er vigtig", "", why_this_text_matters, ""])
    lines.extend(["## Tre-sætningsoversigt", ""])
    for sentence in _as_strings(guide.get("overview")):
        lines.append(f"- {sentence}")
    lines.extend(["", "## Læserute", ""])
    for index, item in enumerate(_as_dicts(guide.get("structure_map")), start=1):
        number = _number_label(item, index)
        section_hint = str(item.get("section_hint") or "").strip()
        what_to_get = str(item.get("what_to_get") or "").strip()
        why_it_matters = str(item.get("why_it_matters") or "").strip()
        stop_after = str(item.get("stop_after") or "").strip()
        lines.append(f"{number}. **{section_hint}**")
        lines.append(f"   - Fang: {what_to_get}")
        lines.append(f"   - Hvorfor: {why_it_matters}")
        lines.append(f"   - Stop når: {stop_after}")
        lines.append("")
    lines.extend(["", "## Nøglecitater at finde", ""])
    for item in _as_dicts(guide.get("key_quote_targets")):
        target = str(item.get("target") or "").strip()
        why = str(item.get("why") or "").strip()
        where_to_look = str(item.get("where_to_look") or "").strip()
        lines.append(f"- **{target}**: {why}")
        if where_to_look:
            lines.append(f"  - Led efter: {where_to_look}")
    stuck_items = _as_strings(guide.get("do_not_get_stuck_on"))
    if stuck_items:
        lines.extend(["", "## Brug ikke for meget energi på", ""])
        for item in stuck_items:
            lines.append(f"- {item}")
    return "\n".join(lines)


def render_unit_test_markdown(artifact: dict[str, Any], suite: dict[str, Any]) -> str:
    lines = [f"# {suite.get('title') or 'Unit Test Suite'}", "", _source_heading(artifact), ""]
    instructions = str(suite.get("instructions") or "").strip()
    if instructions:
        lines.extend([f"*{instructions}*", ""])
    lines.extend(["## Spørgsmål i tekstens rækkefølge", ""])
    for index, item in enumerate(_as_dicts(suite.get("questions")), start=1):
        number = _number_label(item, index)
        question = str(item.get("question") or "").strip()
        where_to_look = str(item.get("where_to_look") or "").strip()
        answer_shape = str(item.get("answer_shape") or "kort svar").strip()
        done_signal = str(item.get("done_signal") or "").strip()
        lines.append(f"{number}. [ ] {question}")
        if where_to_look:
            lines.append(f"   - Led efter: {where_to_look}")
        lines.append(f"   - Svar ({answer_shape}): ______________________________")
        if done_signal:
            lines.append(f"   - Stop når: {done_signal}")
        lines.append("")
    return "\n".join(lines)


def render_cloze_markdown(artifact: dict[str, Any], cloze: dict[str, Any]) -> str:
    lines = [f"# {cloze.get('title') or 'Printout-opgaver'}", "", _source_heading(artifact), ""]
    lines.extend(["## Tre-sætningsoversigt", ""])
    for sentence in _as_strings(cloze.get("overview")):
        lines.append(f"- {sentence}")
    lines.extend(["", "## Udfyldningssætninger", ""])
    for index, item in enumerate(_as_dicts(cloze.get("fill_in_sentences")), start=1):
        number = _number_label(item, index)
        sentence = str(item.get("sentence") or "").strip()
        where_to_look = str(item.get("where_to_look") or "").strip()
        answer_shape = str(item.get("answer_shape") or "").strip()
        lines.append(f"{number}. {sentence}")
        if where_to_look or answer_shape:
            detail = " | ".join(part for part in [f"Led efter: {where_to_look}" if where_to_look else "", f"Svarform: {answer_shape}" if answer_shape else ""] if part)
            lines.append(f"   - {detail}")
        lines.append("")
    lines.extend(["", "## Tomme diagramopgaver", ""])
    diagram_items = _as_dicts(cloze.get("diagram_tasks"))
    space_cm = 2.2 if len(diagram_items) == 1 else 1.5 if len(diagram_items) == 2 else 1.0
    for index, item in enumerate(diagram_items, start=1):
        number = _number_label(item, index)
        task = str(item.get("task") or "").strip()
        hint = str(item.get("blank_space_hint") or "Brug feltet nedenfor.").strip()
        lines.append(f"{number}. {task}")
        elements = _as_strings(item.get("required_elements"))
        if elements:
            lines.append("")
            lines.append("Diagrammet skal indeholde:")
            for element in elements:
                lines.append(f"- {element}")
        lines.append("")
        lines.append(f"*{hint}*")
        lines.append("")
        lines.append(f"\\vspace{{{space_cm:.1f}cm}}")
        lines.append("")
        lines.append("\\hrule")
        lines.append("")
    return "\n".join(lines)


def markdown_to_pdf(markdown_path: Path, pdf_path: Path) -> None:
    if shutil.which("pandoc") is None:
        raise PrintoutError("pandoc is required to render printout PDFs")
    engine = "xelatex" if shutil.which("xelatex") else None
    command = [
        "pandoc",
        str(markdown_path),
        "-o",
        str(pdf_path),
        "-V",
        "papersize=a4",
        "-V",
        "geometry:margin=1.8cm",
        "-V",
        "fontsize=11pt",
    ]
    if engine:
        command.extend(["--pdf-engine", engine])
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise PrintoutError(f"pandoc failed for {markdown_path}: {detail}") from exc


def build_printouts(
    *,
    repo_root: Path,
    subject_root: Path,
    source_catalog_path: Path,
    source_card_dir: Path,
    revised_lecture_substrate_dir: Path,
    course_synthesis_path: Path,
    output_root: Path,
    lecture_keys: list[str] | None = None,
    source_ids: list[str] | None = None,
    source_families: set[str] | None = None,
    model: str = DEFAULT_GEMINI_PREPROCESSING_MODEL,
    backend: GeminiPreprocessingBackend | None = None,
    json_generator: JsonGenerator | None = None,
    render_pdf: bool = True,
    force: bool = False,
    rerender_existing: bool = False,
    dry_run: bool = False,
    continue_on_error: bool = False,
    prompt_version: str = PROMPT_VERSION,
    system_instruction: str | None = None,
    user_prompt_builder: UserPromptBuilder | None = None,
    variant_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sources = select_sources(
        source_catalog_path=source_catalog_path,
        lecture_keys=lecture_keys,
        source_ids=source_ids,
        source_families=source_families,
    )
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    if dry_run:
        return {
            "status": "planned",
            "source_count": len(sources),
            "sources": [
                {
                    "source_id": str(source.get("source_id") or ""),
                    "lecture_key": str(source.get("lecture_key") or ""),
                    "title": str(source.get("title") or ""),
                    "output_dir": str(output_dir_for_source(output_root, source)),
                }
                for source in sources
            ],
        }
    for source in sources:
        source_id = str(source.get("source_id") or "").strip()
        try:
            results.append(
                build_printout_for_source(
                    repo_root=repo_root,
                    subject_root=subject_root,
                    source=source,
                    source_card_dir=source_card_dir,
                    revised_lecture_substrate_dir=revised_lecture_substrate_dir,
                    course_synthesis_path=course_synthesis_path,
                    output_root=output_root,
                    model=model,
                    backend=backend,
                    json_generator=json_generator,
                    render_pdf=render_pdf,
                    force=force,
                    rerender_existing=rerender_existing,
                    prompt_version=prompt_version,
                    system_instruction=system_instruction,
                    user_prompt_builder=user_prompt_builder,
                    variant_metadata=variant_metadata,
                )
            )
        except Exception as exc:
            errors.append({"source_id": source_id, "error": recursive.format_error(exc)})
            if not continue_on_error:
                break
    return {
        "status": "error" if errors else "ok",
        "source_count": len(sources),
        "written_count": sum(1 for item in results if item.get("status") == "written"),
        "rerendered_count": sum(1 for item in results if item.get("status") == "rerendered_existing"),
        "skipped_count": sum(1 for item in results if item.get("status") == "skipped_existing"),
        "error_count": len(errors),
        "results": results,
        "errors": errors,
    }


def parse_source_families(values: list[str], *, all_families: bool = False) -> set[str] | None:
    if all_families:
        return None
    families = {item.strip() for value in values for item in value.split(",") if item.strip()}
    return families or {"reading"}


# Legacy compatibility aliases for the renamed printout engine.
ScaffoldingError = PrintoutError
scaffold_generation_config_metadata = printout_generation_config_metadata
scaffold_system_instruction = printout_system_instruction
scaffold_user_prompt = printout_user_prompt
validate_scaffold_payload = validate_printout_payload
build_scaffold_for_source = build_printout_for_source
render_scaffold_files = render_printout_files
render_v2_scaffold_files = render_v2_printout_files
render_v3_scaffold_files = render_v3_printout_files
build_scaffolds = build_printouts
