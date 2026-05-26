"""Deterministic flashcards that close remaining matrix coverage gaps."""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from notebooklm_queue.json_artifact_utils import semantic_fingerprint
from notebooklm_queue.personlighedspsykologi_flashcard_coverage import matrix_coverage_units
from notebooklm_queue.personlighedspsykologi_matrix_flashcards import (
    CATEGORIES,
    LEARNER_TEXT_FORBIDDEN_PATTERNS,
    SUBJECT_SLUG,
)
from notebooklm_queue.personlighedspsykologi_notebooklm_flashcard_lab import (
    _as_list,
    _as_str_list,
    _text,
    utc_now_iso,
)

COVERAGE_CLOSURE_ARTIFACT_TYPE = "personlighedspsykologi_coverage_closure_flashcards"
COVERAGE_CLOSURE_GENERATOR_VERSION = "personlighedspsykologi-coverage-closure-v1"
DEFAULT_COVERAGE_CLOSURE_JSON = Path(
    "shows/personlighedspsykologi-en/flashcards/coverage/coverage_closure_flashcards.json"
)
DEFAULT_COVERAGE_CLOSURE_MD = Path(
    "shows/personlighedspsykologi-en/flashcards/coverage/coverage_closure_flashcards.md"
)


class CoverageClosureError(ValueError):
    """Raised when deterministic coverage-closure cards cannot be built safely."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CoverageClosureError(f"Unable to load JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise CoverageClosureError(f"JSON root must be an object: {path}")
    return payload


def _category_title(category_slug: str) -> str:
    for category in CATEGORIES:
        if category["slug"] == category_slug:
            return category["title"]
    raise CoverageClosureError(f"Unknown category_slug: {category_slug}")


def _assert_safe_text(*, item_id: str, fields: dict[str, str]) -> None:
    for field, text in fields.items():
        for pattern in LEARNER_TEXT_FORBIDDEN_PATTERNS:
            if pattern.search(text):
                raise CoverageClosureError(f"Unsafe learner-facing text in {item_id}.{field}")


def _rows_by_id(matrix: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        _text(row.get("theory_id")): row
        for row in _as_list(matrix.get("rows"))
        if isinstance(row, dict) and _text(row.get("theory_id"))
    }


def _coverage_units_by_id(matrix: dict[str, Any]) -> dict[str, dict[str, Any]]:
    units: dict[str, dict[str, Any]] = {}
    for row in _as_list(matrix.get("rows")):
        if not isinstance(row, dict):
            continue
        theory_id = _text(row.get("theory_id"))
        for unit in matrix_coverage_units(row):
            unit = dict(unit)
            unit["theory_id"] = theory_id
            units[_text(unit.get("unit_id"))] = unit
    return units


def _closure_targets(coverage_report: dict[str, Any], matrix: dict[str, Any]) -> list[dict[str, Any]]:
    units_by_id = _coverage_units_by_id(matrix)
    targets: list[dict[str, Any]] = []
    for row_report in _as_list(coverage_report.get("rows")):
        if not isinstance(row_report, dict):
            continue
        for unit_report in _as_list(row_report.get("units")):
            if not isinstance(unit_report, dict):
                continue
            if unit_report.get("status") not in {"missing", "weak"}:
                continue
            unit_id = _text(unit_report.get("unit_id"))
            unit = dict(units_by_id.get(unit_id) or {})
            if not unit:
                raise CoverageClosureError(f"Coverage report references unknown matrix coverage unit: {unit_id}")
            unit.update(
                {
                    "status": _text(unit_report.get("status")),
                    "confidence": _text(unit_report.get("confidence")),
                    "best_overlap": unit_report.get("best_overlap"),
                    "card_ids": _as_str_list(unit_report.get("card_ids")),
                    "priority": _text(unit.get("priority")) or _text(unit_report.get("priority")),
                }
            )
            targets.append(unit)
    targets.sort(key=lambda item: (_text(item.get("theory_id")), _text(item.get("field")), _text(item.get("unit_id"))))
    return targets


def _slug_token(value: object) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", _text(value).casefold()).strip("-")
    return token or "x"


def _card_id(unit_id: str) -> str:
    readable = _slug_token(unit_id)
    prefix = "nlm-coverage-closure-"
    if len(prefix + readable) <= 96:
        return prefix + readable
    digest = hashlib.sha256(unit_id.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}{readable[:56].rstrip('-')}-{digest}"


def _category_for_field(field: str) -> str:
    return {
        "method_evidence_style": "metode-og-evidens",
        "strengths": "styrker-og-begraensninger",
        "limitations": "styrker-og-begraensninger",
        "central_concepts": "personbegreb",
        "source_note_basis": "personbegreb",
    }.get(field, "personbegreb")


def _front_for_target(row_label: str, target: dict[str, Any]) -> str:
    field = _text(target.get("field"))
    if field == "method_evidence_style":
        return f"Hvilken metode- og evidensstil kendetegner {row_label}?"
    if field == "strengths":
        return f"Hvilken styrke ved {row_label} er vigtig at kunne nævne?"
    if field == "limitations":
        return f"Hvilken begrænsning ved {row_label} er vigtig at kunne nævne?"
    if field == "central_concepts":
        return f"Hvilket centralbegreb i {row_label} skal du kunne genkende?"
    if field == "source_note_basis":
        return f"Hvilken eksamensnuance skal du huske om {row_label}?"
    return f"Hvad skal du kunne huske om {row_label}?"


def _back_for_target(target: dict[str, Any]) -> str:
    field = _text(target.get("field"))
    expected = _text(target.get("expected_text"))
    if not expected:
        raise CoverageClosureError(f"Coverage closure target has no expected text: {_text(target.get('unit_id'))}")
    if field == "method_evidence_style":
        return f"Metode/evidens: {expected}"
    if field == "strengths":
        return f"Styrke: {expected}"
    if field == "limitations":
        return f"Begrænsning: {expected}"
    if field == "central_concepts":
        return f"Centralbegreb: {expected}"
    if field == "source_note_basis":
        return f"Nuance: {expected}"
    return expected


def _card_for_target(target: dict[str, Any], rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    theory_id = _text(target.get("theory_id"))
    row = rows.get(theory_id) or {}
    row_label = _text(row.get("label")) or theory_id.replace("_", " ")
    category_slug = _category_for_field(_text(target.get("field")))
    front = _front_for_target(row_label, target)
    back = _back_for_target(target)
    card_id = _card_id(_text(target.get("unit_id")))
    _assert_safe_text(item_id=card_id, fields={"front": front, "back": back})
    mapped_theory_ids = {theory_id}
    target_theory_id = _text(target.get("target_theory_id"))
    if target_theory_id:
        mapped_theory_ids.add(target_theory_id)
    return {
        "candidate_id": card_id,
        "notebook_slug": "coverage-closure",
        "source_path": "coverage_closure_flashcards",
        "source_index": 0,
        "front": front,
        "back": back,
        "category_slug": category_slug,
        "category_title": _category_title(category_slug),
        "mapped_theory_ids": sorted(mapped_theory_ids),
        "warnings": [],
        "review_status": "candidate",
        "tags": [
            "deterministic-coverage-closure",
            f"coverage:{_text(target.get('field'))}",
            f"coverage-status:{_text(target.get('status'))}",
        ],
        "target_coverage_unit": {
            "unit_id": _text(target.get("unit_id")),
            "field": _text(target.get("field")),
            "priority": _text(target.get("priority")),
            "previous_status": _text(target.get("status")),
            "expected_text": _text(target.get("expected_text")),
        },
    }


def build_coverage_closure_artifact(
    *,
    matrix: dict[str, Any],
    coverage_report: dict[str, Any],
    generated_at: str | None = None,
) -> dict[str, Any]:
    targets = _closure_targets(coverage_report, matrix)
    if not targets:
        raise CoverageClosureError("No missing or weak coverage units found")
    rows = _rows_by_id(matrix)
    cards = [_card_for_target(target, rows) for target in targets]
    field_counts = Counter(_text(target.get("field")) for target in targets)
    priority_counts = Counter(_text(target.get("priority")) for target in targets)
    status_counts = Counter(_text(target.get("status")) for target in targets)
    artifact = {
        "version": 1,
        "artifact_type": COVERAGE_CLOSURE_ARTIFACT_TYPE,
        "subject_slug": SUBJECT_SLUG,
        "run_id": "coverage-closure-current",
        "generated_at": generated_at or utc_now_iso(),
        "generator": {
            "name": "scripts/build_personlighedspsykologi_coverage_closure_flashcards.py",
            "version": COVERAGE_CLOSURE_GENERATOR_VERSION,
            "source_authority": "validated_exam_matrix_and_coverage_audit",
        },
        "input_fingerprints": {
            "matrix": semantic_fingerprint(matrix),
            "coverage_report": semantic_fingerprint(coverage_report),
        },
        "stats": {
            "card_count": len(cards),
            "field_counts": dict(sorted(field_counts.items())),
            "priority_counts": dict(sorted(priority_counts.items())),
            "previous_status_counts": dict(sorted(status_counts.items())),
        },
        "cards": cards,
    }
    validate_coverage_closure_artifact(artifact)
    return artifact


def validate_coverage_closure_artifact(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("version") != 1:
        raise CoverageClosureError("Coverage closure artifact version must be 1")
    if payload.get("artifact_type") != COVERAGE_CLOSURE_ARTIFACT_TYPE:
        raise CoverageClosureError("Invalid coverage closure artifact_type")
    if payload.get("subject_slug") != SUBJECT_SLUG:
        raise CoverageClosureError(f"Coverage closure subject_slug must be {SUBJECT_SLUG}")
    cards = payload.get("cards")
    if not isinstance(cards, list) or not cards:
        raise CoverageClosureError("Coverage closure cards must be a non-empty list")
    seen: set[str] = set()
    for card in cards:
        if not isinstance(card, dict):
            raise CoverageClosureError("Coverage closure card entries must be objects")
        card_id = _text(card.get("candidate_id"))
        if not re.fullmatch(r"[A-Za-z0-9_-]{3,96}", card_id) or card_id in seen:
            raise CoverageClosureError(f"Invalid or duplicate coverage closure card id: {card_id}")
        seen.add(card_id)
        front = _text(card.get("front"))
        back = _text(card.get("back"))
        if not front or not back:
            raise CoverageClosureError(f"Coverage closure card missing text: {card_id}")
        _category_title(_text(card.get("category_slug")))
        if not _as_str_list(card.get("mapped_theory_ids")):
            raise CoverageClosureError(f"Coverage closure card missing theory tags: {card_id}")
        target = card.get("target_coverage_unit")
        if not isinstance(target, dict) or not _text(target.get("unit_id")):
            raise CoverageClosureError(f"Coverage closure card missing target unit: {card_id}")
        _assert_safe_text(item_id=card_id, fields={"front": front, "back": back})
    if int((payload.get("stats") or {}).get("card_count") or 0) != len(cards):
        raise CoverageClosureError("Coverage closure card_count is stale")
    return payload


def load_coverage_closure_artifact(path: Path) -> dict[str, Any]:
    return validate_coverage_closure_artifact(_load_json(path))


def coverage_closure_to_candidate_payload(payload: dict[str, Any]) -> dict[str, Any]:
    validate_coverage_closure_artifact(payload)
    cards = []
    for card in _as_list(payload.get("cards")):
        if not isinstance(card, dict):
            continue
        cards.append(
            {
                "candidate_id": _text(card.get("candidate_id")),
                "notebook_slug": "coverage-closure",
                "source_path": "shows/personlighedspsykologi-en/flashcards/coverage/coverage_closure_flashcards.json",
                "source_index": int(card.get("source_index") or 0),
                "front": _text(card.get("front")),
                "back": _text(card.get("back")),
                "category_slug": _text(card.get("category_slug")),
                "category_title": _text(card.get("category_title")),
                "mapped_theory_ids": _as_str_list(card.get("mapped_theory_ids")),
                "warnings": [],
                "review_status": "candidate",
                "tags": _as_str_list(card.get("tags")),
            }
        )
    return {
        "version": 1,
        "artifact_type": "personlighedspsykologi_notebooklm_flashcard_candidates",
        "subject_slug": SUBJECT_SLUG,
        "run_id": _text(payload.get("run_id")) or "coverage-closure-current",
        "notebook_slug": "coverage-closure",
        "source_path": "shows/personlighedspsykologi-en/flashcards/coverage/coverage_closure_flashcards.json",
        "stats": {
            "raw_card_count": len(cards),
            "candidate_count": len(cards),
            "status_counts": {"candidate": len(cards)},
        },
        "candidates": cards,
    }


def render_coverage_closure_markdown(payload: dict[str, Any]) -> str:
    validate_coverage_closure_artifact(payload)
    stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
    lines = [
        "# Coverage Closure Flashcards",
        "",
        f"Generated: `{payload.get('generated_at')}`",
        "",
        f"- Card count: {stats.get('card_count')}",
        f"- Field counts: `{stats.get('field_counts')}`",
        f"- Priority counts: `{stats.get('priority_counts')}`",
        f"- Previous status counts: `{stats.get('previous_status_counts')}`",
        "",
    ]
    for card in _as_list(payload.get("cards")):
        if not isinstance(card, dict):
            continue
        target = card.get("target_coverage_unit") if isinstance(card.get("target_coverage_unit"), dict) else {}
        lines.extend(
            [
                f"## {card.get('candidate_id')}",
                "",
                f"Target: `{target.get('unit_id')}`",
                f"Field: `{target.get('field')}`",
                f"Previous status: `{target.get('previous_status')}`",
                f"Category: `{card.get('category_slug')}`",
                "",
                f"Front: {html.escape(_text(card.get('front')))}",
                "",
                f"Back: {html.escape(_text(card.get('back')))}",
                "",
            ]
        )
    return "\n".join(lines)
