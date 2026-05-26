"""Validated answer-enrichment overlays for personlighedspsykologi cards."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Callable

from notebooklm_queue.personlighedspsykologi_matrix_flashcards import (
    LEARNER_TEXT_FORBIDDEN_PATTERNS,
    SUBJECT_SLUG,
)

ANSWER_ENRICHMENT_ARTIFACT_TYPE = "personlighedspsykologi_flashcard_answer_enrichment_overrides"
ANSWER_ENRICHMENT_VERSION = 1
ANSWER_ENRICHMENT_TAG = "answer-enriched"
DEFAULT_ANSWER_ENRICHMENT_JSON = Path(
    "shows/personlighedspsykologi-en/flashcards/answer_enrichment_overrides.json"
)
DEFAULT_ANSWER_ENRICHMENT_MD = Path(
    "shows/personlighedspsykologi-en/flashcards/answer_enrichment_overrides.md"
)
MAX_ENRICHED_ANSWER_WORDS = 80
MIN_ENRICHED_ANSWER_WORDS = 8


class AnswerEnrichmentError(ValueError):
    """Raised when answer-enrichment overlays cannot be applied safely."""


def _text(value: object) -> str:
    return str(value or "").strip()


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_str_list(value: object) -> list[str]:
    return [str(item).strip() for item in _as_list(value) if str(item).strip()]


def _word_count(value: str) -> int:
    return len(re.findall(r"\w+", value, flags=re.UNICODE))


def _assert_safe_text(*, item_id: str, text: str) -> None:
    for pattern in LEARNER_TEXT_FORBIDDEN_PATTERNS:
        if pattern.search(text):
            raise AnswerEnrichmentError(f"Unsafe learner-facing enrichment text in {item_id}")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AnswerEnrichmentError(f"Unable to load answer-enrichment JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise AnswerEnrichmentError(f"Answer-enrichment JSON root must be an object: {path}")
    return payload


def validate_answer_enrichment_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("version") != ANSWER_ENRICHMENT_VERSION:
        raise AnswerEnrichmentError("Answer-enrichment artifact version mismatch")
    if payload.get("artifact_type") != ANSWER_ENRICHMENT_ARTIFACT_TYPE:
        raise AnswerEnrichmentError("Answer-enrichment artifact_type mismatch")
    if payload.get("subject_slug") != SUBJECT_SLUG:
        raise AnswerEnrichmentError(f"Answer-enrichment subject_slug must be {SUBJECT_SLUG}")
    overrides = payload.get("overrides")
    if not isinstance(overrides, list) or not overrides:
        raise AnswerEnrichmentError("Answer-enrichment overrides must be a non-empty list")
    seen: set[str] = set()
    for override in overrides:
        if not isinstance(override, dict):
            raise AnswerEnrichmentError("Answer-enrichment override entries must be objects")
        card_id = _text(override.get("card_id"))
        if not re.fullmatch(r"[A-Za-z0-9_-]{3,120}", card_id):
            raise AnswerEnrichmentError(f"Invalid answer-enrichment card_id: {card_id}")
        if card_id in seen:
            raise AnswerEnrichmentError(f"Duplicate answer-enrichment card_id: {card_id}")
        seen.add(card_id)
        old_back = _text(override.get("old_back_text"))
        new_back = _text(override.get("new_back_text"))
        if not old_back or not new_back:
            raise AnswerEnrichmentError(f"Answer-enrichment override missing text: {card_id}")
        if old_back == new_back:
            raise AnswerEnrichmentError(f"Answer-enrichment override does not change answer: {card_id}")
        word_count = _word_count(new_back)
        if word_count < MIN_ENRICHED_ANSWER_WORDS:
            raise AnswerEnrichmentError(f"Enriched answer is too short for {card_id}: {word_count} words")
        if word_count > MAX_ENRICHED_ANSWER_WORDS:
            raise AnswerEnrichmentError(f"Enriched answer is too long for {card_id}: {word_count} words")
        if not _text(override.get("rationale")):
            raise AnswerEnrichmentError(f"Answer-enrichment override missing rationale: {card_id}")
        if not _as_str_list(override.get("source_matrix_fields")):
            raise AnswerEnrichmentError(f"Answer-enrichment override missing source_matrix_fields: {card_id}")
        _assert_safe_text(item_id=card_id, text=new_back)
    stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
    if int(stats.get("override_count") or 0) != len(overrides):
        raise AnswerEnrichmentError("Answer-enrichment override_count is stale")
    return payload


def load_answer_enrichment_payload(path: Path) -> dict[str, Any]:
    return validate_answer_enrichment_payload(_load_json(path))


def apply_answer_enrichment_overlays(
    deck: dict[str, Any],
    enrichment_payloads: list[dict[str, Any]],
    *,
    html_answer: Callable[[str], str],
    content_hash: Callable[[str, str, str, str], str],
) -> dict[str, Any]:
    if not enrichment_payloads:
        return deck

    cards = deck.get("cards")
    if not isinstance(cards, list):
        raise AnswerEnrichmentError("Deck cards must be a list before answer enrichment")
    cards_by_id = {
        _text(card.get("card_id")): card
        for card in cards
        if isinstance(card, dict) and _text(card.get("card_id"))
    }
    applied_card_ids: list[str] = []
    for payload in enrichment_payloads:
        validate_answer_enrichment_payload(payload)
        for override in payload["overrides"]:
            card_id = _text(override.get("card_id"))
            card = cards_by_id.get(card_id)
            if card is None:
                raise AnswerEnrichmentError(f"Answer-enrichment card not found in deck: {card_id}")
            old_back = _text(override.get("old_back_text"))
            if _text(card.get("back_text")) != old_back:
                raise AnswerEnrichmentError(f"Answer-enrichment old_back_text is stale for {card_id}")
            new_back = _text(override.get("new_back_text"))
            card["back_text"] = new_back
            card["back_html_sanitized"] = html_answer(new_back)
            front = _text(card.get("front_text"))
            category_slug = _text(card.get("category_slug"))
            card["content_sha256"] = content_hash(front, new_back, category_slug, card_id)
            tags = sorted({*_as_str_list(card.get("tags")), ANSWER_ENRICHMENT_TAG})
            card["tags"] = tags
            applied_card_ids.append(card_id)

    deck["answer_enrichment"] = {
        "artifact_type": ANSWER_ENRICHMENT_ARTIFACT_TYPE,
        "applied_count": len(applied_card_ids),
        "card_ids": sorted(applied_card_ids),
    }
    return deck


def render_answer_enrichment_markdown(payload: dict[str, Any]) -> str:
    validate_answer_enrichment_payload(payload)
    lines = [
        "# Flashcard Answer Enrichment Overrides",
        "",
        f"Generated: `{payload.get('generated_at')}`",
        "",
        f"- Override count: {(payload.get('stats') or {}).get('override_count')}",
        f"- Scope: {_text(payload.get('scope'))}",
        "",
    ]
    for override in _as_list(payload.get("overrides")):
        if not isinstance(override, dict):
            continue
        lines.extend(
            [
                f"## {override.get('card_id')}",
                "",
                f"Rationale: {html.escape(_text(override.get('rationale')))}",
                "",
                f"Old: {html.escape(_text(override.get('old_back_text')))}",
                "",
                f"New: {html.escape(_text(override.get('new_back_text')))}",
                "",
            ]
        )
    return "\n".join(lines)
