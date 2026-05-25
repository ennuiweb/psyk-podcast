"""Build Freudd flashcards from the personlighedspsykologi exam matrix."""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from notebooklm_queue.json_artifact_utils import semantic_file_fingerprint
from notebooklm_queue.personlighedspsykologi_student_synthesis import (
    ORIENTATION_POINT_IDS,
    SUBJECT_SLUG,
    StudentSynthesisValidationError,
    sha256_file,
    validate_exam_theory_matrix,
)

FLASHCARD_DECK_SLUG = "eksamensmatrix-personlighedspsykologi"
FLASHCARD_DECK_TITLE = "Eksamensmatrix: personlighedspsykologi"
FLASHCARD_ARTIFACT_TYPE = "freudd_flashcards"
FLASHCARD_VERSION = 1
FLASHCARD_GENERATOR_VERSION = "personlighedspsykologi-matrix-flashcards-v1"
MIN_CARDS_PER_VALIDATED_ROW = 1
MAX_V1_CARD_COUNT = 160

CATEGORIES: tuple[dict[str, str], ...] = (
    {"slug": "orienteringspunkter", "title": "Orienteringspunkter"},
    {"slug": "personbegreb", "title": "Personbegreb"},
    {"slug": "metode-og-evidens", "title": "Metode og evidens"},
    {"slug": "styrker-og-begraensninger", "title": "Styrker og begrænsninger"},
    {"slug": "sammenligninger", "title": "Sammenligninger"},
    {"slug": "eksamenstraps", "title": "Eksamenstraps"},
)

ORIENTATION_LABELS = {
    "essence_context": "essens vs kontekst",
    "determination": "determination",
    "agency": "agency",
    "historicity": "historicitet",
}

LEARNER_TEXT_FORBIDDEN_PATTERNS = (
    re.compile(r"/Users/oskar/", re.IGNORECASE),
    re.compile(r"onedrive local", re.IGNORECASE),
    re.compile(r"\b(?:ane|karla|jaque)\b", re.IGNORECASE),
    re.compile(r"\b(?:anes_tabel|karla_|jaque_)", re.IGNORECASE),
    re.compile(r"student_synthesis/source", re.IGNORECASE),
)


class MatrixFlashcardBuildError(ValueError):
    """Raised when matrix-derived flashcards cannot be generated safely."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_str_list(value: object) -> list[str]:
    return [str(item).strip() for item in _as_list(value) if str(item).strip()]


def _nonempty(value: object) -> str:
    return str(value or "").strip()


def _slug_token(value: object) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().casefold()).strip("-")
    return token or "x"


def _identity_card_id(*parts: object) -> str:
    readable_parts = [_slug_token(part) for part in parts if str(part or "").strip()]
    identity = "|".join(readable_parts)
    readable = "-".join(readable_parts)
    if len(readable) <= 93:
        return f"mx-{readable}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    prefix = "-".join(readable_parts[:2])[:70].rstrip("-")
    return f"mx-{prefix}-{digest}"


def _content_hash(*parts: object) -> str:
    rendered = "\n".join(str(part or "") for part in parts)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _html_div(text: object) -> str:
    return f"<div>{html.escape(str(text or '').strip())}</div>"


def _html_section(label: str, value: object) -> str:
    return f"<div><strong>{html.escape(label)}:</strong> {html.escape(str(value or '').strip())}</div>"


def _html_list(label: str, values: Iterable[object]) -> str:
    items = [str(value or "").strip() for value in values if str(value or "").strip()]
    if not items:
        return ""
    rendered_items = "".join(f"<li>{html.escape(item)}</li>" for item in items)
    return f"<div><strong>{html.escape(label)}:</strong><ul>{rendered_items}</ul></div>"


def _plain_section(label: str, value: object) -> str:
    return f"{label}: {str(value or '').strip()}"


def _plain_list(label: str, values: Iterable[object]) -> str:
    items = [str(value or "").strip() for value in values if str(value or "").strip()]
    if not items:
        return ""
    return f"{label}: " + "; ".join(items)


def _row_label(row: Mapping[str, Any]) -> str:
    return _nonempty(row.get("label")) or _nonempty(row.get("theory_id"))


def _target_label(theory_id: str, rows_by_id: Mapping[str, Mapping[str, Any]]) -> str:
    target = rows_by_id.get(theory_id)
    return _row_label(target) if target else theory_id.replace("_", " ")


def _make_card(
    *,
    card_id: str,
    front_text: str,
    back_html: str,
    back_text: str,
    category_slug: str,
    category_title: str,
    tags: Iterable[str],
) -> dict[str, Any]:
    if not front_text.strip() or not back_html.strip() or not back_text.strip():
        raise MatrixFlashcardBuildError(f"Empty flashcard field for {card_id}")
    return {
        "card_id": card_id,
        "front_text": front_text.strip(),
        "back_html_sanitized": back_html.strip(),
        "back_text": back_text.strip(),
        "tags": sorted({str(tag).strip() for tag in tags if str(tag).strip()}),
        "category_slug": category_slug,
        "category_title": category_title,
        "content_sha256": _content_hash(front_text, back_text, category_slug),
    }


def _orientation_cards(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    label = _row_label(row)
    theory_id = _nonempty(row.get("theory_id"))
    cards: list[dict[str, Any]] = []
    orientation = row.get("orientation_points") if isinstance(row.get("orientation_points"), dict) else {}
    for point_id in ORIENTATION_POINT_IDS:
        point = orientation.get(point_id) if isinstance(orientation, dict) else None
        if not isinstance(point, dict):
            continue
        point_label = ORIENTATION_LABELS.get(point_id, point_id)
        placement = _nonempty(point.get("placement"))
        summary = _nonempty(point.get("summary"))
        front = f"Hvor placerer {label} {point_label}?"
        back_html = "".join(
            [
                _html_section("Placering", placement),
                _html_section("Forklaring", summary),
            ]
        )
        back_text = "\n".join(
            [
                _plain_section("Placering", placement),
                _plain_section("Forklaring", summary),
            ]
        )
        cards.append(
            _make_card(
                card_id=_identity_card_id(theory_id, "orientation", point_id),
                front_text=front,
                back_html=back_html,
                back_text=back_text,
                category_slug="orienteringspunkter",
                category_title="Orienteringspunkter",
                tags=[theory_id, "orientation", point_id, *_as_str_list(row.get("lecture_keys"))],
            )
        )
    return cards


def _model_card(row: Mapping[str, Any]) -> dict[str, Any]:
    label = _row_label(row)
    theory_id = _nonempty(row.get("theory_id"))
    person = _nonempty(row.get("model_of_person"))
    personality = _nonempty(row.get("personality_or_subjectivity_model"))
    front = f"Hvilket personbegreb ligger i {label}?"
    back_html = "".join(
        [
            _html_section("Person", person),
            _html_section("Personlighed/subjektivitet", personality),
        ]
    )
    back_text = "\n".join(
        [
            _plain_section("Person", person),
            _plain_section("Personlighed/subjektivitet", personality),
        ]
    )
    return _make_card(
        card_id=_identity_card_id(theory_id, "model"),
        front_text=front,
        back_html=back_html,
        back_text=back_text,
        category_slug="personbegreb",
        category_title="Personbegreb",
        tags=[theory_id, "model", *_as_str_list(row.get("lecture_keys"))],
    )


def _method_card(row: Mapping[str, Any]) -> dict[str, Any]:
    label = _row_label(row)
    theory_id = _nonempty(row.get("theory_id"))
    front = f"Hvilken metode eller evidensform stoler {label} især på?"
    method = _nonempty(row.get("method_evidence_style"))
    back_html = _html_div(method)
    return _make_card(
        card_id=_identity_card_id(theory_id, "method"),
        front_text=front,
        back_html=back_html,
        back_text=method,
        category_slug="metode-og-evidens",
        category_title="Metode og evidens",
        tags=[theory_id, "method", *_as_str_list(row.get("lecture_keys"))],
    )


def _affordance_card(row: Mapping[str, Any]) -> dict[str, Any]:
    label = _row_label(row)
    theory_id = _nonempty(row.get("theory_id"))
    strengths = _as_str_list(row.get("strengths"))
    limitations = _as_str_list(row.get("limitations"))
    front = f"Hvad gør {label} synligt, og hvad risikerer teorien at skjule?"
    back_html = "".join(
        [
            _html_list("Gør synligt", strengths),
            _html_list("Risikerer at skjule", limitations),
        ]
    )
    back_text = "\n".join(
        [
            _plain_list("Gør synligt", strengths),
            _plain_list("Risikerer at skjule", limitations),
        ]
    )
    return _make_card(
        card_id=_identity_card_id(theory_id, "affordance-limit"),
        front_text=front,
        back_html=back_html,
        back_text=back_text,
        category_slug="styrker-og-begraensninger",
        category_title="Styrker og begrænsninger",
        tags=[theory_id, "affordance-limit", *_as_str_list(row.get("lecture_keys"))],
    )


def _comparison_cards(row: Mapping[str, Any], rows_by_id: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    label = _row_label(row)
    theory_id = _nonempty(row.get("theory_id"))
    cards: list[dict[str, Any]] = []
    for index, target in enumerate(_as_list(row.get("comparison_targets")), start=1):
        if not isinstance(target, dict):
            continue
        target_id = _nonempty(target.get("target_theory_id"))
        if not target_id:
            continue
        target_label = _target_label(target_id, rows_by_id)
        relation = _nonempty(target.get("relation"))
        rationale = _nonempty(target.get("rationale"))
        front = f"Hvordan kan {label} sammenlignes med {target_label}?"
        back_html = "".join(
            [
                _html_section("Relation", relation.replace("_", " ")),
                _html_section("Eksamenstræk", rationale),
            ]
        )
        back_text = "\n".join(
            [
                _plain_section("Relation", relation.replace("_", " ")),
                _plain_section("Eksamenstræk", rationale),
            ]
        )
        cards.append(
            _make_card(
                card_id=_identity_card_id(theory_id, "comparison", target_id, index),
                front_text=front,
                back_html=back_html,
                back_text=back_text,
                category_slug="sammenligninger",
                category_title="Sammenligninger",
                tags=[theory_id, target_id, "comparison", *_as_str_list(row.get("lecture_keys"))],
            )
        )
    return cards


def _misunderstanding_cards(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    label = _row_label(row)
    theory_id = _nonempty(row.get("theory_id"))
    course_summary = _nonempty(row.get("course_summary"))
    synthesis_note = _nonempty(row.get("student_synthesis_notes"))
    concepts = _as_str_list(row.get("central_concepts"))[:5]
    cards: list[dict[str, Any]] = []
    for index, misunderstanding in enumerate(_as_str_list(row.get("likely_misunderstandings")), start=1):
        front = f"Eksamenstrap i {label}: hvorfor er dette for simpelt? {misunderstanding}"
        back_html = "".join(
            [
                _html_section("Korrigering", f"Undgå at gøre {label} så flad."),
                _html_section("Hold fast i", course_summary),
                _html_section("Eksamensvinkel", synthesis_note),
                _html_list("Begreber der kan nuancere svaret", concepts),
            ]
        )
        back_text = "\n".join(
            item
            for item in [
                _plain_section("Korrigering", f"Undgå at gøre {label} så flad."),
                _plain_section("Hold fast i", course_summary),
                _plain_section("Eksamensvinkel", synthesis_note),
                _plain_list("Begreber der kan nuancere svaret", concepts),
            ]
            if item
        )
        cards.append(
            _make_card(
                card_id=_identity_card_id(theory_id, "trap", index),
                front_text=front,
                back_html=back_html,
                back_text=back_text,
                category_slug="eksamenstraps",
                category_title="Eksamenstraps",
                tags=[theory_id, "trap", *_as_str_list(row.get("lecture_keys"))],
            )
        )
    return cards


def matrix_rows_for_flashcards(matrix: Mapping[str, Any]) -> list[dict[str, Any]]:
    validate_exam_theory_matrix(matrix, known_theory_ids=None, known_lecture_keys=None)
    rows = []
    for index, row in enumerate(_as_list(matrix.get("rows"))):
        if not isinstance(row, dict):
            raise MatrixFlashcardBuildError(f"Matrix row {index} is not an object")
        theory_id = _nonempty(row.get("theory_id"))
        if row.get("validation_status") != "validated":
            raise MatrixFlashcardBuildError(f"Matrix row is not validated: {theory_id}")
        if _as_str_list(row.get("warnings")):
            raise MatrixFlashcardBuildError(f"Matrix row has warnings: {theory_id}")
        rows.append(row)
    if not rows:
        raise MatrixFlashcardBuildError("Matrix has no validated rows for flashcards")
    return rows


def _assert_learner_text_is_safe(cards: Iterable[Mapping[str, Any]]) -> None:
    for card in cards:
        card_id = _nonempty(card.get("card_id"))
        for field in ("front_text", "back_html_sanitized", "back_text"):
            text = _nonempty(card.get(field))
            for pattern in LEARNER_TEXT_FORBIDDEN_PATTERNS:
                if pattern.search(text):
                    raise MatrixFlashcardBuildError(f"Unsafe learner-facing text in {card_id}.{field}")


def validate_flashcard_artifact(artifact: Mapping[str, Any], *, matrix: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
    if artifact.get("version") != FLASHCARD_VERSION:
        raise MatrixFlashcardBuildError("Flashcard artifact version must be 1")
    if artifact.get("artifact_type") != FLASHCARD_ARTIFACT_TYPE:
        raise MatrixFlashcardBuildError("Flashcard artifact_type must be freudd_flashcards")
    if artifact.get("subject_slug") != SUBJECT_SLUG:
        raise MatrixFlashcardBuildError(f"Flashcard subject_slug must be {SUBJECT_SLUG}")
    if artifact.get("deck_slug") != FLASHCARD_DECK_SLUG:
        raise MatrixFlashcardBuildError(f"Flashcard deck_slug must be {FLASHCARD_DECK_SLUG}")
    cards = artifact.get("cards")
    if not isinstance(cards, list) or not cards:
        raise MatrixFlashcardBuildError("Flashcard artifact cards must be a non-empty list")
    if int(artifact.get("card_count") or 0) != len(cards):
        raise MatrixFlashcardBuildError("Flashcard card_count does not match cards")
    if len(cards) > MAX_V1_CARD_COUNT:
        raise MatrixFlashcardBuildError(f"Flashcard deck exceeds v1 card cap: {len(cards)}")
    seen_card_ids: set[str] = set()
    category_counts: Counter[str] = Counter()
    category_titles = {category["slug"]: category["title"] for category in CATEGORIES}
    covered_theory_ids: set[str] = set()
    for index, card in enumerate(cards):
        if not isinstance(card, dict):
            raise MatrixFlashcardBuildError(f"Flashcard {index} is not an object")
        card_id = _nonempty(card.get("card_id"))
        if not re.fullmatch(r"[A-Za-z0-9_-]{3,96}", card_id):
            raise MatrixFlashcardBuildError(f"Invalid card_id: {card_id}")
        if card_id in seen_card_ids:
            raise MatrixFlashcardBuildError(f"Duplicate card_id: {card_id}")
        seen_card_ids.add(card_id)
        for field in ("front_text", "back_html_sanitized", "back_text", "content_sha256"):
            if not _nonempty(card.get(field)):
                raise MatrixFlashcardBuildError(f"Flashcard {card_id} missing {field}")
        category_slug = _nonempty(card.get("category_slug"))
        category_title = _nonempty(card.get("category_title"))
        if category_slug not in category_titles:
            raise MatrixFlashcardBuildError(f"Unknown category_slug in {card_id}: {category_slug}")
        if category_titles[category_slug] != category_title:
            raise MatrixFlashcardBuildError(f"Category title mismatch in {card_id}: {category_title}")
        category_counts[category_slug] += 1
        for tag in _as_str_list(card.get("tags")):
            if tag in {str(row.get("theory_id")) for row in _as_list((matrix or {}).get("rows")) if isinstance(row, dict)}:
                covered_theory_ids.add(tag)
    categories = artifact.get("categories")
    if not isinstance(categories, list) or not categories:
        raise MatrixFlashcardBuildError("Flashcard categories must be a non-empty list")
    for category in categories:
        if not isinstance(category, dict):
            raise MatrixFlashcardBuildError("Flashcard category entries must be objects")
        slug = _nonempty(category.get("slug"))
        if int(category.get("card_count") or 0) != category_counts[slug]:
            raise MatrixFlashcardBuildError(f"Category count mismatch for {slug}")
    if matrix is not None:
        rows = matrix_rows_for_flashcards(matrix)
        expected_theory_ids = {_nonempty(row.get("theory_id")) for row in rows}
        if not expected_theory_ids <= covered_theory_ids:
            missing = ", ".join(sorted(expected_theory_ids - covered_theory_ids))
            raise MatrixFlashcardBuildError(f"Flashcard deck missing row coverage: {missing}")
        for theory_id in expected_theory_ids:
            count = sum(1 for card in cards if theory_id in _as_str_list(card.get("tags")))
            if count < MIN_CARDS_PER_VALIDATED_ROW:
                raise MatrixFlashcardBuildError(f"Flashcard coverage too low for {theory_id}")
    _assert_learner_text_is_safe(cards)
    return artifact


def build_flashcard_deck(
    *,
    matrix: Mapping[str, Any],
    source_file: str,
    source_sha256: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    rows = matrix_rows_for_flashcards(matrix)
    rows_by_id = {_nonempty(row.get("theory_id")): row for row in rows}
    cards: list[dict[str, Any]] = []
    for row in rows:
        cards.extend(_orientation_cards(row))
        cards.append(_model_card(row))
        cards.append(_method_card(row))
        cards.append(_affordance_card(row))
        cards.extend(_comparison_cards(row, rows_by_id))
        cards.extend(_misunderstanding_cards(row))
    category_counts = Counter(_nonempty(card.get("category_slug")) for card in cards)
    categories = [
        {
            "slug": category["slug"],
            "title": category["title"],
            "card_count": category_counts[category["slug"]],
        }
        for category in CATEGORIES
        if category_counts[category["slug"]]
    ]
    artifact = {
        "version": FLASHCARD_VERSION,
        "artifact_type": FLASHCARD_ARTIFACT_TYPE,
        "subject_slug": SUBJECT_SLUG,
        "deck_slug": FLASHCARD_DECK_SLUG,
        "title": FLASHCARD_DECK_TITLE,
        "source_file": source_file,
        "source_sha256": source_sha256,
        "generated_at": generated_at or utc_now_iso(),
        "generator": {
            "name": "scripts/build_personlighedspsykologi_matrix_flashcards.py",
            "version": FLASHCARD_GENERATOR_VERSION,
            "source_authority": "student_exam_synthesis",
            "canonical_writer": "deterministic_matrix_generator",
        },
        "card_count": len(cards),
        "categories": categories,
        "cards": cards,
    }
    validate_flashcard_artifact(artifact, matrix=matrix)
    return artifact


def build_flashcard_registry(*, artifact_path: str, card_count: int) -> dict[str, Any]:
    return {
        "version": 1,
        "subject_slug": SUBJECT_SLUG,
        "decks": [
            {
                "deck_slug": FLASHCARD_DECK_SLUG,
                "title": FLASHCARD_DECK_TITLE,
                "description": "Matrixbaserede eksamenskort til teori, orienteringspunkter og sammenligninger.",
                "artifact_path": artifact_path,
                "card_count": int(card_count),
                "enabled": True,
            }
        ],
    }


def source_fingerprint(path: Path) -> str:
    if path.suffix.lower() == ".json":
        return semantic_file_fingerprint(path)
    return sha256_file(path)


def load_matrix(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MatrixFlashcardBuildError(f"Unable to load matrix: {path}") from exc
    try:
        validate_exam_theory_matrix(payload, known_theory_ids=None, known_lecture_keys=None)
    except StudentSynthesisValidationError as exc:
        raise MatrixFlashcardBuildError(f"Matrix is invalid for flashcard generation: {exc}") from exc
    return payload
