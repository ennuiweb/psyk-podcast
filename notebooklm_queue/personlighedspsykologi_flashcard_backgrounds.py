"""Validated background overlays for personlighedspsykologi flashcards."""

from __future__ import annotations

import html
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from notebooklm_queue.personlighedspsykologi_matrix_flashcards import (
    LEARNER_TEXT_FORBIDDEN_PATTERNS,
    SUBJECT_SLUG,
)

FLASHCARD_BACKGROUNDS_ARTIFACT_TYPE = "personlighedspsykologi_flashcard_background_overlays"
FLASHCARD_BACKGROUNDS_VERSION = 1
FLASHCARD_BACKGROUND_TAG = "background"
DEFAULT_FLASHCARD_BACKGROUNDS_JSON = Path(
    "shows/personlighedspsykologi-en/flashcards/card_background_overlays.json"
)
DEFAULT_FLASHCARD_BACKGROUNDS_MD = Path(
    "shows/personlighedspsykologi-en/flashcards/card_background_overlays.md"
)
MIN_BACKGROUND_WORDS = 24
MAX_BACKGROUND_WORDS = 110


class FlashcardBackgroundError(ValueError):
    """Raised when flashcard background overlays cannot be used safely."""


def _text(value: object) -> str:
    return str(value or "").strip()


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_str_list(value: object) -> list[str]:
    return [str(item).strip() for item in _as_list(value) if str(item).strip()]


def _word_count(value: str) -> int:
    return len(re.findall(r"\w+", value, flags=re.UNICODE))


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FlashcardBackgroundError(f"Unable to load flashcard backgrounds JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise FlashcardBackgroundError(f"Flashcard backgrounds JSON root must be an object: {path}")
    return payload


def _assert_safe_text(*, item_id: str, text: str) -> None:
    for pattern in LEARNER_TEXT_FORBIDDEN_PATTERNS:
        if pattern.search(text):
            raise FlashcardBackgroundError(f"Unsafe learner-facing background text in {item_id}")
    if re.search(
        r"\b(?:source_id|note_id|artifact|matrix|matrixen|matrixens|kildegrundlag|kildesubstrat|substrat|JSON|overlay|source)\b",
        text,
        flags=re.IGNORECASE,
    ):
        raise FlashcardBackgroundError(f"Hidden provenance leaked into background text for {item_id}")


def _validate_support_entry(entry: object, *, card_id: str) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise FlashcardBackgroundError(f"Background support entries must be objects: {card_id}")
    support_type = _text(entry.get("type"))
    if support_type not in {"matrix_field", "source_card", "course_synthesis", "lecture_substrate"}:
        raise FlashcardBackgroundError(f"Invalid background support type for {card_id}: {support_type}")
    if support_type == "matrix_field":
        if not _text(entry.get("theory_id")) or not _text(entry.get("field")):
            raise FlashcardBackgroundError(f"Matrix support missing theory_id/field for {card_id}")
    if support_type == "source_card":
        if not _text(entry.get("source_id")) or not _as_str_list(entry.get("fields")):
            raise FlashcardBackgroundError(f"Source-card support missing source_id/fields for {card_id}")
    if support_type == "lecture_substrate":
        if not _text(entry.get("lecture_key")) or not _as_str_list(entry.get("fields")):
            raise FlashcardBackgroundError(f"Lecture support missing lecture_key/fields for {card_id}")
    if support_type == "course_synthesis" and not _as_str_list(entry.get("fields")):
        raise FlashcardBackgroundError(f"Course-synthesis support missing fields for {card_id}")
    return entry


def validate_flashcard_background_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("version") != FLASHCARD_BACKGROUNDS_VERSION:
        raise FlashcardBackgroundError("Flashcard backgrounds artifact version mismatch")
    if payload.get("artifact_type") != FLASHCARD_BACKGROUNDS_ARTIFACT_TYPE:
        raise FlashcardBackgroundError("Flashcard backgrounds artifact_type mismatch")
    if payload.get("subject_slug") != SUBJECT_SLUG:
        raise FlashcardBackgroundError(f"Flashcard backgrounds subject_slug must be {SUBJECT_SLUG}")
    backgrounds = payload.get("backgrounds")
    if not isinstance(backgrounds, list) or not backgrounds:
        raise FlashcardBackgroundError("Flashcard backgrounds must be a non-empty list")

    seen: set[str] = set()
    confidence_counts: Counter[str] = Counter()
    for background in backgrounds:
        if not isinstance(background, dict):
            raise FlashcardBackgroundError("Flashcard background entries must be objects")
        card_id = _text(background.get("card_id"))
        if not re.fullmatch(r"[A-Za-z0-9_-]{3,120}", card_id):
            raise FlashcardBackgroundError(f"Invalid flashcard background card_id: {card_id}")
        if card_id in seen:
            raise FlashcardBackgroundError(f"Duplicate flashcard background card_id: {card_id}")
        seen.add(card_id)
        if not _text(background.get("old_front_text")) or not _text(background.get("old_back_text")):
            raise FlashcardBackgroundError(f"Background missing stale-check text: {card_id}")
        background_text = _text(background.get("background_text"))
        if not background_text:
            raise FlashcardBackgroundError(f"Background text missing: {card_id}")
        word_count = _word_count(background_text)
        if word_count < MIN_BACKGROUND_WORDS:
            raise FlashcardBackgroundError(f"Background text is too short for {card_id}: {word_count} words")
        if word_count > MAX_BACKGROUND_WORDS:
            raise FlashcardBackgroundError(f"Background text is too long for {card_id}: {word_count} words")
        _assert_safe_text(item_id=card_id, text=background_text)
        support = [_validate_support_entry(entry, card_id=card_id) for entry in _as_list(background.get("support"))]
        if not support:
            raise FlashcardBackgroundError(f"Background support missing: {card_id}")
        if not any(entry.get("type") == "matrix_field" for entry in support):
            raise FlashcardBackgroundError(f"Background must include matrix support: {card_id}")
        confidence = _text(background.get("confidence"))
        if confidence not in {"high", "medium", "low"}:
            raise FlashcardBackgroundError(f"Invalid background confidence for {card_id}: {confidence}")
        confidence_counts[confidence] += 1

    stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
    if int(stats.get("background_count") or 0) != len(backgrounds):
        raise FlashcardBackgroundError("Flashcard background_count is stale")
    recorded_confidence_counts = {
        str(key): int(value)
        for key, value in (stats.get("confidence_counts") or {}).items()
        if str(key).strip()
    }
    if recorded_confidence_counts and recorded_confidence_counts != dict(sorted(confidence_counts.items())):
        raise FlashcardBackgroundError("Flashcard background confidence_counts are stale")
    return payload


def load_flashcard_background_payload(path: Path) -> dict[str, Any]:
    return validate_flashcard_background_payload(_load_json(path))


def apply_flashcard_background_overlays(
    deck: dict[str, Any],
    background_payloads: list[dict[str, Any]],
    *,
    html_background: Callable[[str], str],
) -> dict[str, Any]:
    if not background_payloads:
        return deck
    cards = deck.get("cards")
    if not isinstance(cards, list):
        raise FlashcardBackgroundError("Deck cards must be a list before background overlays")
    cards_by_id = {
        _text(card.get("card_id")): card
        for card in cards
        if isinstance(card, dict) and _text(card.get("card_id"))
    }
    applied_card_ids: list[str] = []
    for payload in background_payloads:
        validate_flashcard_background_payload(payload)
        for background in payload["backgrounds"]:
            card_id = _text(background.get("card_id"))
            card = cards_by_id.get(card_id)
            if card is None:
                raise FlashcardBackgroundError(f"Background card not found in deck: {card_id}")
            if _text(card.get("front_text")) != _text(background.get("old_front_text")):
                raise FlashcardBackgroundError(f"Background old_front_text is stale for {card_id}")
            if _text(card.get("back_text")) != _text(background.get("old_back_text")):
                raise FlashcardBackgroundError(f"Background old_back_text is stale for {card_id}")
            background_text = _text(background.get("background_text"))
            card["background_text"] = background_text
            card["background_html_sanitized"] = html_background(background_text)
            tags = sorted({*_as_str_list(card.get("tags")), FLASHCARD_BACKGROUND_TAG})
            card["tags"] = tags
            applied_card_ids.append(card_id)

    deck["card_backgrounds"] = {
        "artifact_type": FLASHCARD_BACKGROUNDS_ARTIFACT_TYPE,
        "applied_count": len(applied_card_ids),
        "card_ids": sorted(applied_card_ids),
    }
    return deck


def render_flashcard_background_markdown(payload: dict[str, Any]) -> str:
    validate_flashcard_background_payload(payload)
    stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
    lines = [
        "# Flashcard Background Overlays",
        "",
        f"Generated: `{payload.get('generated_at')}`",
        "",
        f"- Background count: {stats.get('background_count')}",
        f"- Scope: {_text(payload.get('scope'))}",
        f"- Confidence counts: {stats.get('confidence_counts')}",
        "",
    ]
    for background in _as_list(payload.get("backgrounds")):
        if not isinstance(background, dict):
            continue
        lines.extend(
            [
                f"## {background.get('card_id')}",
                "",
                f"Confidence: `{html.escape(_text(background.get('confidence')))}`",
                "",
                f"Question: {html.escape(_text(background.get('old_front_text')))}",
                "",
                f"Answer: {html.escape(_text(background.get('old_back_text')))}",
                "",
                f"Background: {html.escape(_text(background.get('background_text')))}",
                "",
            ]
        )
    return "\n".join(lines)
