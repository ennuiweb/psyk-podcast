"""Audit live personlighedspsykologi flashcards against the matrix/source basis."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from notebooklm_queue.json_artifact_utils import semantic_file_fingerprint
from notebooklm_queue.personlighedspsykologi_matrix_flashcards import (
    CATEGORIES,
    FLASHCARD_ARTIFACT_TYPE,
    SUBJECT_SLUG,
)
from notebooklm_queue.personlighedspsykologi_notebooklm_flashcard_lab import utc_now_iso

COVERAGE_VERSION = 1
COVERAGE_ARTIFACT_TYPE = "personlighedspsykologi_flashcard_matrix_coverage"
DEFAULT_MATRIX_PATH = Path("shows/personlighedspsykologi-en/student_synthesis/exam_theory_matrix.json")
DEFAULT_DECK_PATH = Path("shows/personlighedspsykologi-en/flashcards/notebooklm-fuld-matrix-personlighedspsykologi.json")
DEFAULT_SOURCE_NOTES_INDEX_PATH = Path("shows/personlighedspsykologi-en/student_synthesis/source_notes_index.json")
DEFAULT_SOURCE_NOTES_REGISTRY_PATH = Path("shows/personlighedspsykologi-en/student_synthesis/source_notes.registry.json")
DEFAULT_OUTPUT_JSON = Path("shows/personlighedspsykologi-en/flashcards/coverage/full_matrix_coverage_report.json")
DEFAULT_OUTPUT_MD = Path("shows/personlighedspsykologi-en/flashcards/coverage/full_matrix_coverage_report.md")
CATEGORIES_BY_SLUG = [category["slug"] for category in CATEGORIES]

FIELD_TARGETS: dict[str, dict[str, Any]] = {
    "course_summary": {"category_slugs": set(CATEGORIES_BY_SLUG), "minimum": 1},
    "model_of_person": {"category_slugs": {"personbegreb"}, "minimum": 1},
    "personality_or_subjectivity_model": {"category_slugs": {"personbegreb"}, "minimum": 1},
    "method_evidence_style": {"category_slugs": {"metode-og-evidens"}, "minimum": 1},
    "strengths": {"category_slugs": {"styrker-og-begraensninger"}, "minimum": 1},
    "limitations": {"category_slugs": {"styrker-og-begraensninger"}, "minimum": 1},
    "likely_misunderstandings": {"category_slugs": {"eksamenstraps"}, "minimum": 1},
    "comparison_targets": {"category_slugs": {"sammenligninger"}, "minimum": 1},
    "orientation_points": {"category_slugs": {"orienteringspunkter"}, "minimum": 1},
    "central_concepts": {"category_slugs": set(CATEGORIES_BY_SLUG), "minimum": 1},
    "source_note_basis": {"category_slugs": set(CATEGORIES_BY_SLUG), "minimum": 1},
}
ORIENTATION_POINT_LABELS = {
    "essence_context": "essens kontekst essence context",
    "determination": "determination determinisme bestemt",
    "agency": "agency agens handleevne valg mulighed",
    "historicity": "historicitet historisk udvikling tid",
}
STOPWORDS = {
    "and",
    "eller",
    "the",
    "that",
    "with",
    "for",
    "den",
    "det",
    "der",
    "som",
    "til",
    "fra",
    "kan",
    "hvor",
    "hvordan",
    "hvilken",
    "hvilket",
    "personlighed",
    "personlighedspsykologi",
}
CENTRAL_CONCEPT_TOKEN_ALIASES = {
    "action possibilities": "handlemuligheder handlepotentiale action possibilities",
    "conditions": "betingelser livsbetingelser conditions",
    "everyday life": "hverdagsliv hverdagslivet dagligliv everyday life",
    "expansive agency": "ekspansivt handlepotentiale expansive agency",
    "participation": "deltagelse deltager participation",
    "social practice": "social praksis praksisser social practice",
    "subjectivity": "subjektivitet subjektivitetens subjectivity",
}


class FlashcardCoverageError(ValueError):
    """Raised when coverage cannot be audited safely."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FlashcardCoverageError(f"Unable to load JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise FlashcardCoverageError(f"JSON root must be an object: {path}")
    return payload


def _text(value: object) -> str:
    return str(value or "").strip()


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_str_list(value: object) -> list[str]:
    return [str(item).strip() for item in _as_list(value) if str(item).strip()]


def _tokens(value: object) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-ZæøåÆØÅ0-9]+", _text(value).casefold())
        if len(token) >= 3 and token not in STOPWORDS
    }


def _repo_relative(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def _known_theory_ids(matrix: dict[str, Any]) -> set[str]:
    return {
        _text(row.get("theory_id"))
        for row in _as_list(matrix.get("rows"))
        if isinstance(row, dict) and _text(row.get("theory_id"))
    }


def _validate_inputs(matrix: dict[str, Any], deck: dict[str, Any]) -> None:
    if matrix.get("subject_slug") != SUBJECT_SLUG:
        raise FlashcardCoverageError(f"Matrix subject_slug must be {SUBJECT_SLUG}")
    if deck.get("subject_slug") != SUBJECT_SLUG:
        raise FlashcardCoverageError(f"Deck subject_slug must be {SUBJECT_SLUG}")
    if deck.get("artifact_type") != FLASHCARD_ARTIFACT_TYPE:
        raise FlashcardCoverageError("Deck artifact_type must be freudd_flashcards")
    cards = deck.get("cards")
    if not isinstance(cards, list) or not cards:
        raise FlashcardCoverageError("Deck cards must be a non-empty list")
    if int(deck.get("card_count") or 0) != len(cards):
        raise FlashcardCoverageError("Deck card_count mismatch")


def _normalize_cards(deck: dict[str, Any], matrix: dict[str, Any]) -> list[dict[str, Any]]:
    known_theory_ids = _known_theory_ids(matrix)
    cards = []
    for card in _as_list(deck.get("cards")):
        if not isinstance(card, dict):
            continue
        tags = _as_str_list(card.get("tags"))
        theory_ids = sorted(tag for tag in tags if tag in known_theory_ids)
        cards.append(
            {
                "card_id": _text(card.get("card_id")),
                "front": _text(card.get("front_text")),
                "back": _text(card.get("back_text")),
                "category_slug": _text(card.get("category_slug")),
                "tags": tags,
                "theory_ids": theory_ids,
                "tokens": _tokens(_text(card.get("front_text")) + " " + _text(card.get("back_text"))),
            }
        )
    missing_theory = [card["card_id"] for card in cards if not card["theory_ids"]]
    if missing_theory:
        raise FlashcardCoverageError(
            "Cards without matrix theory tags: " + ", ".join(missing_theory[:10])
        )
    return cards


def _coverage_aliases(field: str, expected_text: str) -> str:
    if field != "central_concepts":
        return ""
    return CENTRAL_CONCEPT_TOKEN_ALIASES.get(_text(expected_text).casefold(), "")


def _unit(unit_id: str, field: str, label: str, expected_text: str, priority: str = "normal", target_id: str = "") -> dict[str, Any]:
    return {
        "unit_id": unit_id,
        "field": field,
        "label": label,
        "expected_text": expected_text,
        "priority": priority,
        "target_theory_id": target_id,
        "expected_tokens": sorted(_tokens(label + " " + expected_text + " " + _coverage_aliases(field, expected_text))),
    }


def matrix_coverage_units(row: dict[str, Any]) -> list[dict[str, Any]]:
    theory_id = _text(row.get("theory_id"))
    label = _text(row.get("label")) or theory_id
    units = [
        _unit(f"{theory_id}:course_summary", "course_summary", f"{label}: hovedpointe", _text(row.get("course_summary")), "high"),
        _unit(f"{theory_id}:model_of_person", "model_of_person", f"{label}: personbegreb", _text(row.get("model_of_person")), "high"),
        _unit(
            f"{theory_id}:personality_or_subjectivity_model",
            "personality_or_subjectivity_model",
            f"{label}: personlighed/subjektivitet",
            _text(row.get("personality_or_subjectivity_model")),
            "high",
        ),
        _unit(
            f"{theory_id}:method_evidence_style",
            "method_evidence_style",
            f"{label}: metode/evidens",
            _text(row.get("method_evidence_style")),
            "high",
        ),
    ]
    orientation = row.get("orientation_points") if isinstance(row.get("orientation_points"), dict) else {}
    for point_id, point in orientation.items():
        if not isinstance(point, dict):
            continue
        expected = " ".join(
            item
            for item in [
                ORIENTATION_POINT_LABELS.get(_text(point_id), _text(point_id)),
                _text(point.get("placement")),
                _text(point.get("summary")),
            ]
            if item
        )
        units.append(
            _unit(
                f"{theory_id}:orientation_points:{point_id}",
                "orientation_points",
                f"{label}: {point_id}",
                expected,
                "high",
            )
        )
    for index, concept in enumerate(_as_str_list(row.get("central_concepts")), start=1):
        units.append(
            _unit(f"{theory_id}:central_concepts:{index}", "central_concepts", f"{label}: begreb", concept, "normal")
        )
    for field, title, priority in (
        ("strengths", "styrke", "normal"),
        ("limitations", "begrænsning", "normal"),
        ("likely_misunderstandings", "eksamenstrap", "high"),
    ):
        for index, item in enumerate(_as_str_list(row.get(field)), start=1):
            units.append(_unit(f"{theory_id}:{field}:{index}", field, f"{label}: {title}", item, priority))
    for index, target in enumerate(_as_list(row.get("comparison_targets")), start=1):
        if not isinstance(target, dict):
            continue
        target_id = _text(target.get("target_theory_id"))
        expected = " ".join(
            item
            for item in [
                target_id.replace("_", " "),
                _text(target.get("relation")).replace("_", " "),
                _text(target.get("rationale")),
            ]
            if item
        )
        units.append(
            _unit(
                f"{theory_id}:comparison_targets:{target_id or index}",
                "comparison_targets",
                f"{label}: sammenligning",
                expected,
                "high",
                target_id,
            )
        )
    for basis in _as_list(row.get("source_note_basis")):
        if not isinstance(basis, dict):
            continue
        note_id = _text(basis.get("note_id"))
        summary = _text(basis.get("summary"))
        if not note_id or not summary:
            continue
        units.append(
            _unit(
                f"{theory_id}:source_note_basis:{note_id}",
                "source_note_basis",
                f"{label}: source basis {note_id}",
                summary,
                "high",
            )
        )
    return units


def _candidate_cards_for_unit(unit: dict[str, Any], theory_id: str, cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    field = _text(unit.get("field"))
    category_slugs = FIELD_TARGETS.get(field, {}).get("category_slugs", set(CATEGORIES_BY_SLUG))
    row_cards = [card for card in cards if theory_id in card["theory_ids"]]
    if field == "comparison_targets":
        target_id = _text(unit.get("target_theory_id"))
        return [
            card
            for card in row_cards
            if card["category_slug"] in category_slugs
            and (not target_id or target_id in card["theory_ids"] or target_id.replace("_", " ") in (card["front"] + " " + card["back"]).casefold())
        ]
    if field == "central_concepts":
        unit_tokens = set(unit.get("expected_tokens") or [])
        return [card for card in row_cards if unit_tokens & card["tokens"]]
    if field == "source_note_basis":
        return row_cards
    return [card for card in row_cards if card["category_slug"] in category_slugs]


def _coverage_status(unit: dict[str, Any], cards: list[dict[str, Any]]) -> dict[str, Any]:
    if not cards:
        return {"status": "missing", "confidence": "high", "best_overlap": 0.0, "card_ids": []}
    unit_tokens = set(unit.get("expected_tokens") or [])
    best_overlap = 0.0
    scored_cards = []
    for card in cards:
        overlap = len(unit_tokens & card["tokens"]) / max(1, len(unit_tokens))
        if overlap > best_overlap:
            best_overlap = overlap
        scored_cards.append((overlap, card["card_id"]))
    scored_cards.sort(key=lambda item: (-item[0], item[1]))
    field = _text(unit.get("field"))
    if field in {"model_of_person", "personality_or_subjectivity_model", "method_evidence_style", "strengths", "limitations", "likely_misunderstandings", "comparison_targets"}:
        status = "strong" if best_overlap >= 0.12 else "partial"
    elif field == "orientation_points":
        status = "strong" if best_overlap >= 0.10 else "partial"
    elif field == "central_concepts":
        status = "strong" if best_overlap >= 0.40 else "partial"
    elif field == "source_note_basis":
        status = "strong" if best_overlap >= 0.18 else "partial" if best_overlap >= 0.06 else "weak"
    else:
        status = "strong" if best_overlap >= 0.10 else "partial"
    confidence = "medium" if status in {"partial", "weak"} else "high"
    return {
        "status": status,
        "confidence": confidence,
        "best_overlap": round(best_overlap, 4),
        "card_ids": [card_id for _, card_id in scored_cards[:5]],
    }


def _summarize_statuses(items: list[dict[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(_text(item.get("status")) for item in items).items()))


def _row_status(unit_reports: list[dict[str, Any]]) -> str:
    high_priority = [unit for unit in unit_reports if unit.get("priority") == "high"]
    missing_high = sum(1 for unit in high_priority if unit.get("status") == "missing")
    weak_high = sum(1 for unit in high_priority if unit.get("status") == "weak")
    strong_or_partial = sum(1 for unit in unit_reports if unit.get("status") in {"strong", "partial"})
    ratio = strong_or_partial / max(1, len(unit_reports))
    if missing_high == 0 and weak_high == 0 and ratio >= 0.72:
        return "strong"
    if missing_high <= 2 and ratio >= 0.55:
        return "partial"
    if strong_or_partial:
        return "weak"
    return "missing"


def _note_lookup(*payloads: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        for note in _as_list(payload.get("notes")):
            if isinstance(note, dict) and _text(note.get("note_id")):
                lookup.setdefault(_text(note.get("note_id")), note)
    return lookup


def _source_note_coverage(rows: list[dict[str, Any]], row_reports: list[dict[str, Any]], notes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows_by_id = {_text(row.get("theory_id")): row for row in rows}
    reports_by_row = {_text(row.get("theory_id")): row for row in row_reports}
    note_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        theory_id = _text(row.get("theory_id"))
        for basis in _as_list(row.get("source_note_basis")):
            if isinstance(basis, dict) and _text(basis.get("note_id")):
                note_rows[_text(basis.get("note_id"))].append({"theory_id": theory_id, "summary": _text(basis.get("summary"))})
    output = []
    for note_id in sorted(set(notes) | set(note_rows)):
        linked = note_rows.get(note_id, [])
        unit_statuses = []
        for link in linked:
            report = reports_by_row.get(_text(link.get("theory_id")), {})
            source_units = [
                unit
                for unit in _as_list(report.get("units"))
                if unit.get("field") == "source_note_basis" and unit.get("unit_id", "").endswith(f":{note_id}")
            ]
            unit_statuses.extend(source_units)
        status_counts = _summarize_statuses(unit_statuses)
        covered = status_counts.get("strong", 0) + status_counts.get("partial", 0)
        total = len(unit_statuses)
        if total == 0:
            status = "missing"
        elif status_counts.get("strong", 0) == total:
            status = "strong"
        elif covered:
            status = "partial"
        else:
            status = "weak"
        output.append(
            {
                "note_id": note_id,
                "label": _text((notes.get(note_id) or {}).get("label")) or note_id,
                "matrix_policy": _text((notes.get(note_id) or {}).get("matrix_policy")),
                "linked_row_count": len({_text(item.get("theory_id")) for item in linked}),
                "linked_theory_ids": sorted({_text(item.get("theory_id")) for item in linked if _text(item.get("theory_id")) in rows_by_id}),
                "basis_unit_count": total,
                "status": status,
                "status_counts": status_counts,
            }
        )
    return output


def build_coverage_report(
    *,
    repo_root: Path,
    matrix_path: Path = DEFAULT_MATRIX_PATH,
    deck_path: Path = DEFAULT_DECK_PATH,
    source_notes_index_path: Path = DEFAULT_SOURCE_NOTES_INDEX_PATH,
    source_notes_registry_path: Path = DEFAULT_SOURCE_NOTES_REGISTRY_PATH,
    generated_at: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    matrix_path = matrix_path if matrix_path.is_absolute() else repo_root / matrix_path
    deck_path = deck_path if deck_path.is_absolute() else repo_root / deck_path
    source_notes_index_path = source_notes_index_path if source_notes_index_path.is_absolute() else repo_root / source_notes_index_path
    source_notes_registry_path = (
        source_notes_registry_path if source_notes_registry_path.is_absolute() else repo_root / source_notes_registry_path
    )
    matrix = _load_json(matrix_path)
    deck = _load_json(deck_path)
    notes_index = _load_json(source_notes_index_path)
    notes_registry = _load_json(source_notes_registry_path)
    _validate_inputs(matrix, deck)
    cards = _normalize_cards(deck, matrix)
    rows = [row for row in _as_list(matrix.get("rows")) if isinstance(row, dict)]
    row_reports = []
    all_units = []
    for row in rows:
        theory_id = _text(row.get("theory_id"))
        row_cards = [card for card in cards if theory_id in card["theory_ids"]]
        unit_reports = []
        for unit in matrix_coverage_units(row):
            candidates = _candidate_cards_for_unit(unit, theory_id, cards)
            result = _coverage_status(unit, candidates)
            unit_report = {
                "unit_id": unit["unit_id"],
                "field": unit["field"],
                "label": unit["label"],
                "priority": unit["priority"],
                "status": result["status"],
                "confidence": result["confidence"],
                "best_overlap": result["best_overlap"],
                "card_ids": result["card_ids"],
            }
            unit_reports.append(unit_report)
            all_units.append(unit_report)
        category_counts = Counter(card["category_slug"] for card in row_cards)
        row_reports.append(
            {
                "theory_id": theory_id,
                "label": _text(row.get("label")) or theory_id,
                "card_count": len(row_cards),
                "category_counts": dict(sorted(category_counts.items())),
                "status": _row_status(unit_reports),
                "unit_status_counts": _summarize_statuses(unit_reports),
                "units": unit_reports,
            }
        )
    notes = _note_lookup(notes_registry, notes_index)
    source_notes = _source_note_coverage(rows, row_reports, notes)
    field_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for unit in all_units:
        field_counts[_text(unit.get("field"))][_text(unit.get("status"))] += 1
    missing_or_weak = [
        unit
        for unit in all_units
        if unit.get("status") in {"missing", "weak"} and unit.get("priority") == "high"
    ]
    by_status = _summarize_statuses(all_units)
    report = {
        "version": COVERAGE_VERSION,
        "artifact_type": COVERAGE_ARTIFACT_TYPE,
        "subject_slug": SUBJECT_SLUG,
        "generated_at": generated_at or utc_now_iso(),
        "inputs": {
            "matrix": {"path": _repo_relative(matrix_path, repo_root), "fingerprint": semantic_file_fingerprint(matrix_path)},
            "deck": {"path": _repo_relative(deck_path, repo_root), "fingerprint": semantic_file_fingerprint(deck_path)},
            "source_notes_index": {
                "path": _repo_relative(source_notes_index_path, repo_root),
                "fingerprint": semantic_file_fingerprint(source_notes_index_path),
            },
            "source_notes_registry": {
                "path": _repo_relative(source_notes_registry_path, repo_root),
                "fingerprint": semantic_file_fingerprint(source_notes_registry_path),
            },
        },
        "deck": {
            "deck_slug": _text(deck.get("deck_slug")),
            "card_count": len(cards),
            "category_counts": dict(sorted(Counter(card["category_slug"] for card in cards).items())),
        },
        "summary": {
            "row_count": len(row_reports),
            "unit_count": len(all_units),
            "unit_status_counts": by_status,
            "field_status_counts": {field: dict(sorted(counts.items())) for field, counts in sorted(field_counts.items())},
            "source_note_status_counts": _summarize_statuses(source_notes),
            "high_priority_missing_or_weak_count": len(missing_or_weak),
        },
        "rows": row_reports,
        "source_notes": source_notes,
        "recommendations": _recommendations(row_reports, source_notes, missing_or_weak),
    }
    validate_coverage_report(report)
    return report


def validate_coverage_report(report: dict[str, Any]) -> dict[str, Any]:
    if report.get("version") != COVERAGE_VERSION:
        raise FlashcardCoverageError("Coverage report version mismatch")
    if report.get("artifact_type") != COVERAGE_ARTIFACT_TYPE:
        raise FlashcardCoverageError("Coverage report artifact_type mismatch")
    if report.get("subject_slug") != SUBJECT_SLUG:
        raise FlashcardCoverageError("Coverage report subject_slug mismatch")
    rows = report.get("rows")
    if not isinstance(rows, list) or not rows:
        raise FlashcardCoverageError("Coverage report rows must be non-empty")
    for row in rows:
        if not isinstance(row, dict) or not _text(row.get("theory_id")):
            raise FlashcardCoverageError("Coverage row missing theory_id")
        if row.get("status") not in {"strong", "partial", "weak", "missing"}:
            raise FlashcardCoverageError(f"Invalid row coverage status: {row.get('status')}")
        units = row.get("units")
        if not isinstance(units, list) or not units:
            raise FlashcardCoverageError(f"Coverage row has no units: {row.get('theory_id')}")
    return report


def _recommendations(
    row_reports: list[dict[str, Any]],
    source_notes: list[dict[str, Any]],
    missing_or_weak: list[dict[str, Any]],
) -> list[str]:
    recommendations = []
    weak_rows = [row for row in row_reports if row.get("status") in {"weak", "missing"}]
    if weak_rows:
        recommendations.append(
            "Prioritize new or edited cards for weak theory rows: "
            + ", ".join(_text(row.get("theory_id")) for row in weak_rows[:8])
        )
    if missing_or_weak:
        by_field = Counter(_text(unit.get("field")) for unit in missing_or_weak)
        recommendations.append(
            "High-priority missing/weak fields: "
            + ", ".join(f"{field}={count}" for field, count in by_field.most_common())
        )
    weak_notes = [note for note in source_notes if note.get("status") in {"weak", "missing"} and note.get("basis_unit_count")]
    if weak_notes:
        recommendations.append(
            "Review source-note basis coverage for: "
            + ", ".join(_text(note.get("note_id")) for note in weak_notes[:8])
        )
    if not recommendations:
        recommendations.append("No high-priority deterministic coverage gaps detected; use LLM review only for qualitative fidelity.")
    recommendations.append("Use this report as a coverage audit, not as proof of conceptual correctness for every card.")
    return recommendations


def render_coverage_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    deck = report.get("deck") if isinstance(report.get("deck"), dict) else {}
    lines = [
        "# Full Matrix Flashcard Coverage Report",
        "",
        f"Generated: `{report.get('generated_at')}`",
        f"Deck: `{deck.get('deck_slug')}` ({deck.get('card_count')} cards)",
        "",
        "## Summary",
        "",
        f"- Matrix rows: {summary.get('row_count')}",
        f"- Coverage units: {summary.get('unit_count')}",
        f"- Unit status counts: `{summary.get('unit_status_counts')}`",
        f"- High-priority missing/weak units: {summary.get('high_priority_missing_or_weak_count')}",
        f"- Source-note status counts: `{summary.get('source_note_status_counts')}`",
        "",
        "## Recommendations",
        "",
    ]
    lines.extend(f"- {item}" for item in _as_str_list(report.get("recommendations")))
    lines.extend(["", "## Field Coverage", ""])
    field_counts = summary.get("field_status_counts") if isinstance(summary.get("field_status_counts"), dict) else {}
    lines.extend(["| Field | Strong | Partial | Weak | Missing |", "|---|---:|---:|---:|---:|"])
    for field, counts in sorted(field_counts.items()):
        if not isinstance(counts, dict):
            continue
        lines.append(
            f"| `{field}` | {counts.get('strong', 0)} | {counts.get('partial', 0)} | "
            f"{counts.get('weak', 0)} | {counts.get('missing', 0)} |"
        )
    lines.extend(["", "## Theory Rows", ""])
    lines.extend(["| Theory | Status | Cards | Unit Status Counts |", "|---|---|---:|---|"])
    for row in _as_list(report.get("rows")):
        if not isinstance(row, dict):
            continue
        lines.append(
            f"| `{row.get('theory_id')}` | `{row.get('status')}` | {row.get('card_count')} | "
            f"`{row.get('unit_status_counts')}` |"
        )
    lines.extend(["", "## High-Priority Missing Or Weak Units", ""])
    weak_units = []
    for row in _as_list(report.get("rows")):
        if not isinstance(row, dict):
            continue
        for unit in _as_list(row.get("units")):
            if isinstance(unit, dict) and unit.get("priority") == "high" and unit.get("status") in {"missing", "weak"}:
                weak_units.append(unit)
    if not weak_units:
        lines.append("No high-priority missing or weak units were detected deterministically.")
    else:
        lines.extend(["| Unit | Field | Status | Best Cards |", "|---|---|---|---|"])
        for unit in weak_units[:120]:
            lines.append(
                f"| `{unit.get('unit_id')}` | `{unit.get('field')}` | `{unit.get('status')}` | "
                f"{', '.join(_as_str_list(unit.get('card_ids'))) or '-'} |"
            )
    lines.extend(["", "## Source Notes", ""])
    lines.extend(["| Source Note | Status | Linked Rows | Basis Units | Status Counts |", "|---|---|---:|---:|---|"])
    for note in _as_list(report.get("source_notes")):
        if not isinstance(note, dict):
            continue
        lines.append(
            f"| `{note.get('note_id')}` | `{note.get('status')}` | {note.get('linked_row_count')} | "
            f"{note.get('basis_unit_count')} | `{note.get('status_counts')}` |"
        )
    lines.extend(
        [
            "",
            "## Interpretation Notes",
            "",
            "- `strong` and `partial` are deterministic coverage labels, not a final content-quality verdict.",
            "- Source-note coverage is assessed through the matrix row/source-basis summaries, not by exposing raw source notes in learner cards.",
            "- Ambiguous `partial`, `weak`, and `missing` high-priority units are the best candidates for a later targeted LLM review.",
            "",
        ]
    )
    return "\n".join(lines)
