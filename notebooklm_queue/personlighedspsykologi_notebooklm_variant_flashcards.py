"""Build Freudd variant flashcards from reviewed NotebookLM candidates."""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from notebooklm_queue.json_artifact_utils import semantic_fingerprint
from notebooklm_queue.personlighedspsykologi_matrix_flashcards import (
    CATEGORIES,
    FLASHCARD_ARTIFACT_TYPE,
    FLASHCARD_VERSION,
    LEARNER_TEXT_FORBIDDEN_PATTERNS,
    SUBJECT_SLUG,
)

VARIANT_DECK_SLUG = "notebooklm-varianter-personlighedspsykologi"
VARIANT_DECK_TITLE = "NotebookLM-varianter: personlighedspsykologi"
VARIANT_DECK_DESCRIPTION = "Gemini-reviewede NotebookLM-varianter til mundtlig eksamen."
VARIANT_GENERATOR_VERSION = "personlighedspsykologi-notebooklm-variants-v1"
PROMOTION_DECISIONS_ARTIFACT_TYPE = "personlighedspsykologi_notebooklm_variant_promotion_decisions"
PROMOTABLE_DECISIONS = {"accept", "edit"}


class NotebookLMVariantFlashcardError(ValueError):
    """Raised when NotebookLM variant flashcards cannot be built safely."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_str_list(value: object) -> list[str]:
    return [str(item).strip() for item in _as_list(value) if str(item).strip()]


def _text(value: object) -> str:
    return str(value or "").strip()


def _slug_token(value: object) -> str:
    token = re.sub(r"[^a-z0-9]+", "-", _text(value).casefold()).strip("-")
    return token or "x"


def _content_hash(*parts: object) -> str:
    rendered = "\n".join(str(part or "") for part in parts)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def source_fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _category_title(category_slug: str) -> str:
    return next((item["title"] for item in CATEGORIES if item["slug"] == category_slug), category_slug)


def _safe_card_id(candidate_id: str) -> str:
    readable = _slug_token(candidate_id)
    card_id = f"nlmv-{readable}"
    if len(card_id) <= 96:
        return card_id
    digest = hashlib.sha256(candidate_id.encode("utf-8")).hexdigest()[:16]
    return f"nlmv-{readable[:74].rstrip('-')}-{digest}"


def _html_answer(back_text: str) -> str:
    return f"<div>{html.escape(back_text)}</div>"


def _assert_text_is_safe(*, item_id: str, fields: dict[str, str]) -> None:
    for field, text in fields.items():
        for pattern in LEARNER_TEXT_FORBIDDEN_PATTERNS:
            if pattern.search(text):
                raise NotebookLMVariantFlashcardError(f"Unsafe learner-facing text in {item_id}.{field}")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NotebookLMVariantFlashcardError(f"Unable to load JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise NotebookLMVariantFlashcardError(f"JSON root must be an object: {path}")
    return payload


def load_promotion_decisions(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    validate_promotion_decisions(payload)
    return payload


def build_promotion_decisions(
    *,
    candidates_payload: dict[str, Any],
    gemini_review_payload: dict[str, Any],
    deck_slug: str = VARIANT_DECK_SLUG,
    generated_at: str | None = None,
) -> dict[str, Any]:
    candidates = {
        _text(candidate.get("candidate_id")): candidate
        for candidate in _as_list(candidates_payload.get("candidates"))
        if isinstance(candidate, dict) and _text(candidate.get("candidate_id"))
    }
    if not candidates:
        raise NotebookLMVariantFlashcardError("No candidates available for promotion decisions")
    decisions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_decision in _as_list(gemini_review_payload.get("decisions")):
        if not isinstance(raw_decision, dict):
            continue
        candidate_id = _text(raw_decision.get("candidate_id"))
        candidate = candidates.get(candidate_id)
        if candidate is None:
            raise NotebookLMVariantFlashcardError(f"Gemini review references unknown candidate: {candidate_id}")
        if candidate_id in seen:
            raise NotebookLMVariantFlashcardError(f"Duplicate Gemini decision for candidate: {candidate_id}")
        seen.add(candidate_id)
        decision = _text(raw_decision.get("decision"))
        if decision not in {"accept", "edit", "merge_with_existing", "reject"}:
            raise NotebookLMVariantFlashcardError(f"Invalid Gemini decision for {candidate_id}: {decision}")
        front = _text(raw_decision.get("edited_front")) if decision == "edit" else _text(candidate.get("front"))
        back = _text(raw_decision.get("edited_back")) if decision == "edit" else _text(candidate.get("back"))
        promote = decision in PROMOTABLE_DECISIONS
        if promote and (not front or not back):
            raise NotebookLMVariantFlashcardError(f"Promoted candidate is missing front/back: {candidate_id}")
        if promote:
            _assert_text_is_safe(item_id=candidate_id, fields={"front": front, "back": back})
        manual_review = candidate.get("manual_card_review") if isinstance(candidate.get("manual_card_review"), dict) else {}
        nearest = manual_review.get("nearest_existing_card") if isinstance(manual_review.get("nearest_existing_card"), dict) else {}
        decisions.append(
            {
                "candidate_id": candidate_id,
                "promote": promote,
                "gemini_decision": decision,
                "confidence": _text(raw_decision.get("confidence")),
                "front_text": front if promote else "",
                "back_text": back if promote else "",
                "category_slug": _text(candidate.get("category_slug")),
                "mapped_theory_ids": _as_str_list(candidate.get("mapped_theory_ids")),
                "notebook_slug": _text(candidate.get("notebook_slug")),
                "source_index": int(candidate.get("source_index") or 0),
                "reason": _text(raw_decision.get("reason")),
                "added_value": _text(raw_decision.get("added_value")),
                "nearest_existing_card_id": _text(nearest.get("card_id")),
                "nearest_existing_card_assessment": _text(raw_decision.get("nearest_existing_card_assessment")),
                "automatic_review_status": _text(candidate.get("review_status")),
                "local_suggested_decision": _text(manual_review.get("suggested_decision")),
            }
        )
    missing = set(candidates) - seen
    if missing:
        raise NotebookLMVariantFlashcardError(
            "Gemini review is missing candidate decisions: " + ", ".join(sorted(missing)[:10])
        )
    promoted_count = sum(1 for decision in decisions if decision["promote"])
    payload = {
        "version": 1,
        "artifact_type": PROMOTION_DECISIONS_ARTIFACT_TYPE,
        "subject_slug": SUBJECT_SLUG,
        "deck_slug": deck_slug,
        "generated_at": generated_at or utc_now_iso(),
        "source_run": {
            "run_id": _text(candidates_payload.get("run_id")),
            "notebook_slug": _text(candidates_payload.get("notebook_slug")),
            "candidate_count": len(candidates),
        },
        "source_fingerprints": {
            "candidates": semantic_fingerprint(candidates_payload),
            "gemini_review": semantic_fingerprint(gemini_review_payload),
        },
        "stats": {
            "decision_count": len(decisions),
            "promoted_count": promoted_count,
            "rejected_count": len(decisions) - promoted_count,
            "gemini_decision_counts": dict(
                sorted(Counter(_text(decision.get("gemini_decision")) for decision in decisions).items())
            ),
        },
        "decisions": decisions,
    }
    validate_promotion_decisions(payload, expected_deck_slug=deck_slug)
    return payload


def validate_promotion_decisions(
    payload: dict[str, Any],
    *,
    expected_deck_slug: str | None = VARIANT_DECK_SLUG,
) -> dict[str, Any]:
    if payload.get("version") != 1:
        raise NotebookLMVariantFlashcardError("Promotion decisions version must be 1")
    if payload.get("artifact_type") != PROMOTION_DECISIONS_ARTIFACT_TYPE:
        raise NotebookLMVariantFlashcardError("Invalid promotion decisions artifact_type")
    if payload.get("subject_slug") != SUBJECT_SLUG:
        raise NotebookLMVariantFlashcardError(f"Promotion decisions subject_slug must be {SUBJECT_SLUG}")
    if expected_deck_slug is not None and payload.get("deck_slug") != expected_deck_slug:
        raise NotebookLMVariantFlashcardError(f"Promotion decisions deck_slug must be {expected_deck_slug}")
    if not _text(payload.get("deck_slug")):
        raise NotebookLMVariantFlashcardError("Promotion decisions deck_slug is required")
    decisions = payload.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        raise NotebookLMVariantFlashcardError("Promotion decisions must contain a non-empty decisions list")
    seen: set[str] = set()
    promoted_count = 0
    for item in decisions:
        if not isinstance(item, dict):
            raise NotebookLMVariantFlashcardError("Promotion decision entries must be objects")
        candidate_id = _text(item.get("candidate_id"))
        if not candidate_id or candidate_id in seen:
            raise NotebookLMVariantFlashcardError(f"Invalid or duplicate candidate_id: {candidate_id}")
        seen.add(candidate_id)
        decision = _text(item.get("gemini_decision"))
        promote = bool(item.get("promote"))
        if promote:
            promoted_count += 1
            if decision not in PROMOTABLE_DECISIONS:
                raise NotebookLMVariantFlashcardError(f"Unpromotable decision marked promote: {candidate_id}")
            front = _text(item.get("front_text"))
            back = _text(item.get("back_text"))
            if not front or not back:
                raise NotebookLMVariantFlashcardError(f"Promoted decision missing front/back: {candidate_id}")
            if _text(item.get("category_slug")) not in {category["slug"] for category in CATEGORIES}:
                raise NotebookLMVariantFlashcardError(f"Unknown category for promoted decision: {candidate_id}")
            _assert_text_is_safe(item_id=candidate_id, fields={"front": front, "back": back})
    if int((payload.get("stats") or {}).get("promoted_count") or 0) != promoted_count:
        raise NotebookLMVariantFlashcardError("Promotion decisions promoted_count is stale")
    return payload


def _card_from_decision(decision: dict[str, Any]) -> dict[str, Any]:
    candidate_id = _text(decision.get("candidate_id"))
    category_slug = _text(decision.get("category_slug"))
    front = _text(decision.get("front_text"))
    back = _text(decision.get("back_text"))
    tags = [
        "notebooklm-variant",
        _text(decision.get("gemini_decision")),
        _text(decision.get("notebook_slug")),
        *_as_str_list(decision.get("mapped_theory_ids")),
    ]
    nearest = _text(decision.get("nearest_existing_card_id"))
    if nearest:
        tags.append(f"nearest:{nearest}")
    return {
        "card_id": _safe_card_id(candidate_id),
        "front_text": front,
        "back_html_sanitized": _html_answer(back),
        "back_text": back,
        "tags": sorted({tag for tag in tags if tag}),
        "category_slug": category_slug,
        "category_title": _category_title(category_slug),
        "content_sha256": _content_hash(front, back, category_slug, candidate_id),
    }


def build_variant_deck(
    *,
    promotion_decisions: dict[str, Any],
    source_file: str,
    source_sha256: str,
    deck_slug: str | None = None,
    title: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    deck_slug = deck_slug or _text(promotion_decisions.get("deck_slug")) or VARIANT_DECK_SLUG
    title = title or VARIANT_DECK_TITLE
    validate_promotion_decisions(promotion_decisions, expected_deck_slug=deck_slug)
    cards = [_card_from_decision(decision) for decision in promotion_decisions["decisions"] if decision.get("promote")]
    if not cards:
        raise NotebookLMVariantFlashcardError("No promoted NotebookLM variant cards")
    category_counts = Counter(_text(card.get("category_slug")) for card in cards)
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
        "deck_slug": deck_slug,
        "title": title,
        "source_file": source_file,
        "source_sha256": source_sha256,
        "generated_at": generated_at or utc_now_iso(),
        "generator": {
            "name": "scripts/build_personlighedspsykologi_notebooklm_variant_flashcards.py",
            "version": VARIANT_GENERATOR_VERSION,
            "source_authority": "gemini_reviewed_notebooklm_candidates",
            "canonical_writer": "deterministic_variant_promotion_generator",
        },
        "card_count": len(cards),
        "categories": categories,
        "cards": cards,
    }
    validate_variant_deck(artifact, expected_deck_slug=deck_slug)
    return artifact


def validate_variant_deck(
    payload: dict[str, Any],
    *,
    expected_deck_slug: str | None = VARIANT_DECK_SLUG,
) -> dict[str, Any]:
    if payload.get("version") != FLASHCARD_VERSION:
        raise NotebookLMVariantFlashcardError("Variant deck version must be 1")
    if payload.get("artifact_type") != FLASHCARD_ARTIFACT_TYPE:
        raise NotebookLMVariantFlashcardError("Variant deck artifact_type must be freudd_flashcards")
    if payload.get("subject_slug") != SUBJECT_SLUG:
        raise NotebookLMVariantFlashcardError(f"Variant deck subject_slug must be {SUBJECT_SLUG}")
    if expected_deck_slug is not None and payload.get("deck_slug") != expected_deck_slug:
        raise NotebookLMVariantFlashcardError(f"Variant deck deck_slug must be {expected_deck_slug}")
    if not _text(payload.get("deck_slug")):
        raise NotebookLMVariantFlashcardError("Variant deck deck_slug is required")
    cards = payload.get("cards")
    if not isinstance(cards, list) or not cards:
        raise NotebookLMVariantFlashcardError("Variant deck cards must be a non-empty list")
    if int(payload.get("card_count") or 0) != len(cards):
        raise NotebookLMVariantFlashcardError("Variant deck card_count mismatch")
    seen: set[str] = set()
    category_counts: Counter[str] = Counter()
    category_titles = {category["slug"]: category["title"] for category in CATEGORIES}
    for card in cards:
        if not isinstance(card, dict):
            raise NotebookLMVariantFlashcardError("Variant deck card entries must be objects")
        card_id = _text(card.get("card_id"))
        if not re.fullmatch(r"[A-Za-z0-9_-]{3,96}", card_id):
            raise NotebookLMVariantFlashcardError(f"Invalid variant card_id: {card_id}")
        if card_id in seen:
            raise NotebookLMVariantFlashcardError(f"Duplicate variant card_id: {card_id}")
        seen.add(card_id)
        front = _text(card.get("front_text"))
        back_html = _text(card.get("back_html_sanitized"))
        back = _text(card.get("back_text"))
        if not front or not back_html or not back:
            raise NotebookLMVariantFlashcardError(f"Variant card missing text: {card_id}")
        category_slug = _text(card.get("category_slug"))
        if category_slug not in category_titles:
            raise NotebookLMVariantFlashcardError(f"Unknown category_slug in variant card: {card_id}")
        if _text(card.get("category_title")) != category_titles[category_slug]:
            raise NotebookLMVariantFlashcardError(f"Category title mismatch in variant card: {card_id}")
        category_counts[category_slug] += 1
        _assert_text_is_safe(item_id=card_id, fields={"front": front, "back_html": back_html, "back": back})
    categories = payload.get("categories")
    if not isinstance(categories, list) or not categories:
        raise NotebookLMVariantFlashcardError("Variant deck categories must be non-empty")
    for category in categories:
        if not isinstance(category, dict):
            raise NotebookLMVariantFlashcardError("Variant deck category entries must be objects")
        slug = _text(category.get("slug"))
        if int(category.get("card_count") or 0) != category_counts[slug]:
            raise NotebookLMVariantFlashcardError(f"Variant deck category count mismatch: {slug}")
    return payload


def load_candidates_and_review(candidates_path: Path, gemini_review_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    return _load_json(candidates_path), _load_json(gemini_review_path)
