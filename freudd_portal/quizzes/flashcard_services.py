"""File-backed flashcard deck loading and review helpers."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone

from .models import FlashcardReview
from .subject_services import resolve_subject_paths

logger = logging.getLogger(__name__)

SUBJECT_SLUG_RE = re.compile(r"^[a-z0-9-]+$")
DECK_SLUG_RE = re.compile(r"^[a-z0-9-]+$")
CARD_ID_RE = re.compile(r"^[A-Za-z0-9_-]{3,96}$")
FLASHCARD_RATINGS = {
    FlashcardReview.Rating.AGAIN,
    FlashcardReview.Rating.HARD,
    FlashcardReview.Rating.GOOD,
    FlashcardReview.Rating.EASY,
}
RATING_DUE_OFFSETS = {
    FlashcardReview.Rating.AGAIN: timedelta(minutes=10),
    FlashcardReview.Rating.HARD: timedelta(days=1),
    FlashcardReview.Rating.GOOD: timedelta(days=3),
    FlashcardReview.Rating.EASY: timedelta(days=7),
}
RATING_SORT_ORDER = {
    FlashcardReview.Rating.AGAIN: 0,
    FlashcardReview.Rating.HARD: 1,
    FlashcardReview.Rating.GOOD: 2,
    FlashcardReview.Rating.EASY: 3,
}


class FlashcardServiceError(RuntimeError):
    """Base error for flashcard loading failures."""


class FlashcardDeckNotFound(FlashcardServiceError):
    """Raised when a requested flashcard deck is not registered or enabled."""


class FlashcardValidationError(FlashcardServiceError):
    """Raised when a flashcard registry or deck artifact is malformed."""


@dataclass(frozen=True)
class FlashcardDeckEntry:
    subject_slug: str
    deck_slug: str
    title: str
    description: str
    artifact_path: Path
    artifact_path_display: str
    card_count: int
    enabled: bool


@dataclass(frozen=True)
class FlashcardDeck:
    subject_slug: str
    deck_slug: str
    title: str
    description: str
    source_file: str
    source_sha256: str
    generated_at: str
    card_count: int
    cards: tuple[dict[str, object], ...]


_REGISTRY_CACHE: dict[str, Any] = {"path": None, "mtime": None, "subject_slug": None, "entries": None}
_DECK_CACHE: dict[tuple[str, str, str, int], FlashcardDeck] = {}


def clear_flashcard_service_caches() -> None:
    _REGISTRY_CACHE["path"] = None
    _REGISTRY_CACHE["mtime"] = None
    _REGISTRY_CACHE["subject_slug"] = None
    _REGISTRY_CACHE["entries"] = None
    _DECK_CACHE.clear()


def _repo_root() -> Path:
    return Path(settings.BASE_DIR).resolve().parent


def _normalize_slug(value: object, *, pattern: re.Pattern[str], label: str) -> str:
    slug = str(value or "").strip().lower()
    if not pattern.fullmatch(slug):
        raise FlashcardValidationError(f"Invalid {label}: {value!r}")
    return slug


def _subject_flashcard_registry_path(subject_slug: str) -> Path:
    subject_paths = resolve_subject_paths(subject_slug)
    return subject_paths.content_manifest_path.parent / "flashcards" / "decks.json"


def _resolve_artifact_path(raw_value: object) -> tuple[Path, str]:
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise FlashcardValidationError("Flashcard deck is missing artifact_path.")
    display = raw_value.strip().replace("\\", "/")
    candidate = Path(display)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise FlashcardValidationError("Flashcard artifact_path must be repo-relative.")
    resolved = (_repo_root() / candidate).resolve()
    try:
        resolved.relative_to(_repo_root())
    except ValueError as exc:
        raise FlashcardValidationError("Flashcard artifact_path escapes repo root.") from exc
    return resolved, display


def _load_registry_entries(subject_slug: str) -> tuple[FlashcardDeckEntry, ...]:
    normalized_subject = _normalize_slug(subject_slug, pattern=SUBJECT_SLUG_RE, label="subject slug")
    path = _subject_flashcard_registry_path(normalized_subject)
    if not path.is_file():
        return tuple()

    try:
        mtime = path.stat().st_mtime_ns
    except OSError as exc:
        raise FlashcardValidationError(f"Unable to stat flashcard registry: {path}") from exc

    cache_hit = (
        _REGISTRY_CACHE.get("path") == str(path)
        and _REGISTRY_CACHE.get("mtime") == mtime
        and _REGISTRY_CACHE.get("subject_slug") == normalized_subject
        and isinstance(_REGISTRY_CACHE.get("entries"), tuple)
    )
    if cache_hit:
        return _REGISTRY_CACHE["entries"]

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FlashcardValidationError(f"Unable to parse flashcard registry: {path}") from exc

    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise FlashcardValidationError("Flashcard registry must be a version 1 object.")
    registry_subject = _normalize_slug(payload.get("subject_slug"), pattern=SUBJECT_SLUG_RE, label="subject slug")
    if registry_subject != normalized_subject:
        raise FlashcardValidationError("Flashcard registry subject_slug does not match requested subject.")

    raw_decks = payload.get("decks")
    if not isinstance(raw_decks, list):
        raise FlashcardValidationError("Flashcard registry decks must be a list.")

    entries: list[FlashcardDeckEntry] = []
    seen: set[str] = set()
    for raw_deck in raw_decks:
        if not isinstance(raw_deck, dict):
            continue
        deck_slug = _normalize_slug(raw_deck.get("deck_slug"), pattern=DECK_SLUG_RE, label="deck slug")
        if deck_slug in seen:
            raise FlashcardValidationError(f"Duplicate flashcard deck_slug: {deck_slug}")
        artifact_path, artifact_display = _resolve_artifact_path(raw_deck.get("artifact_path"))
        entries.append(
            FlashcardDeckEntry(
                subject_slug=normalized_subject,
                deck_slug=deck_slug,
                title=str(raw_deck.get("title") or deck_slug).strip() or deck_slug,
                description=str(raw_deck.get("description") or "").strip(),
                artifact_path=artifact_path,
                artifact_path_display=artifact_display,
                card_count=max(0, int(raw_deck.get("card_count") or 0)),
                enabled=bool(raw_deck.get("enabled", True)),
            )
        )
        seen.add(deck_slug)

    result = tuple(entries)
    _REGISTRY_CACHE["path"] = str(path)
    _REGISTRY_CACHE["mtime"] = mtime
    _REGISTRY_CACHE["subject_slug"] = normalized_subject
    _REGISTRY_CACHE["entries"] = result
    return result


def list_flashcard_deck_entries(subject_slug: str) -> tuple[FlashcardDeckEntry, ...]:
    return tuple(entry for entry in _load_registry_entries(subject_slug) if entry.enabled)


def get_flashcard_deck_entry(subject_slug: str, deck_slug: str) -> FlashcardDeckEntry:
    normalized_deck = _normalize_slug(deck_slug, pattern=DECK_SLUG_RE, label="deck slug")
    for entry in list_flashcard_deck_entries(subject_slug):
        if entry.deck_slug == normalized_deck:
            return entry
    raise FlashcardDeckNotFound(f"Flashcard deck not found: {subject_slug}/{deck_slug}")


def _normalize_card(raw_card: Any) -> dict[str, object] | None:
    if not isinstance(raw_card, dict):
        return None
    card_id = str(raw_card.get("card_id") or "").strip()
    if not CARD_ID_RE.fullmatch(card_id):
        return None
    front_text = str(raw_card.get("front_text") or "").strip()
    back_html = str(raw_card.get("back_html_sanitized") or "").strip()
    back_text = str(raw_card.get("back_text") or "").strip()
    if not front_text or not back_html or not back_text:
        return None
    tags = raw_card.get("tags")
    tag_values = [str(tag).strip() for tag in tags if str(tag).strip()] if isinstance(tags, list) else []
    return {
        "card_id": card_id,
        "front_text": front_text,
        "back_html": back_html,
        "back_text": back_text,
        "tags": tag_values,
        "content_sha256": str(raw_card.get("content_sha256") or "").strip(),
    }


def load_flashcard_deck(subject_slug: str, deck_slug: str) -> FlashcardDeck:
    entry = get_flashcard_deck_entry(subject_slug, deck_slug)
    try:
        mtime = entry.artifact_path.stat().st_mtime_ns
    except OSError as exc:
        raise FlashcardValidationError(f"Unable to stat flashcard artifact: {entry.artifact_path}") from exc

    cache_key = (entry.subject_slug, entry.deck_slug, str(entry.artifact_path), mtime)
    cached = _DECK_CACHE.get(cache_key)
    if cached is not None:
        return cached

    try:
        payload = json.loads(entry.artifact_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FlashcardValidationError(f"Unable to parse flashcard artifact: {entry.artifact_path}") from exc

    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise FlashcardValidationError("Flashcard artifact must be a version 1 object.")
    if payload.get("artifact_type") != "freudd_flashcards":
        raise FlashcardValidationError("Flashcard artifact has an unsupported artifact_type.")
    if str(payload.get("subject_slug") or "").strip().lower() != entry.subject_slug:
        raise FlashcardValidationError("Flashcard artifact subject_slug does not match registry.")
    if str(payload.get("deck_slug") or "").strip().lower() != entry.deck_slug:
        raise FlashcardValidationError("Flashcard artifact deck_slug does not match registry.")

    raw_cards = payload.get("cards")
    if not isinstance(raw_cards, list):
        raise FlashcardValidationError("Flashcard artifact cards must be a list.")
    cards = tuple(card for raw_card in raw_cards if (card := _normalize_card(raw_card)) is not None)
    declared_count = int(payload.get("card_count") or 0)
    if declared_count != len(cards):
        raise FlashcardValidationError("Flashcard artifact card_count does not match usable cards.")

    deck = FlashcardDeck(
        subject_slug=entry.subject_slug,
        deck_slug=entry.deck_slug,
        title=str(payload.get("title") or entry.title).strip() or entry.title,
        description=entry.description,
        source_file=str(payload.get("source_file") or "").strip(),
        source_sha256=str(payload.get("source_sha256") or "").strip(),
        generated_at=str(payload.get("generated_at") or "").strip(),
        card_count=len(cards),
        cards=cards,
    )
    _DECK_CACHE[cache_key] = deck
    return deck


def _reviews_for_deck(*, user, subject_slug: str, deck_slug: str) -> dict[str, FlashcardReview]:
    if user is None or not getattr(user, "is_authenticated", False):
        return {}
    rows = FlashcardReview.objects.filter(
        user=user,
        subject_slug=subject_slug,
        deck_slug=deck_slug,
    )
    return {row.card_id: row for row in rows}


def review_summary_for_deck(*, user, subject_slug: str, deck_slug: str, card_count: int) -> dict[str, object]:
    reviews = _reviews_for_deck(user=user, subject_slug=subject_slug, deck_slug=deck_slug)
    ratings = {rating: 0 for rating in FLASHCARD_RATINGS}
    due_count = 0
    now = timezone.now()
    for review in reviews.values():
        if review.rating in ratings:
            ratings[review.rating] += 1
        if review.next_review_at is not None and review.next_review_at <= now:
            due_count += 1
    reviewed_count = len(reviews)
    total = max(0, int(card_count))
    return {
        "reviewed_count": reviewed_count,
        "remaining_count": max(0, total - reviewed_count),
        "card_count": total,
        "due_count": due_count,
        "ratings": ratings,
    }


def deck_summary_payload(*, entry: FlashcardDeckEntry, user=None) -> dict[str, object]:
    payload: dict[str, object] = {
        "subject_slug": entry.subject_slug,
        "deck_slug": entry.deck_slug,
        "title": entry.title,
        "description": entry.description,
        "card_count": entry.card_count,
    }
    if user is not None and getattr(user, "is_authenticated", False):
        payload["review_summary"] = review_summary_for_deck(
            user=user,
            subject_slug=entry.subject_slug,
            deck_slug=entry.deck_slug,
            card_count=entry.card_count,
        )
    return payload


def list_flashcard_deck_summaries(subject_slug: str, *, user=None) -> list[dict[str, object]]:
    return [
        deck_summary_payload(entry=entry, user=user)
        for entry in list_flashcard_deck_entries(subject_slug)
    ]


def _card_review_payload(review: FlashcardReview | None) -> dict[str, object] | None:
    if review is None:
        return None
    return {
        "rating": review.rating,
        "review_count": int(review.review_count or 0),
        "last_reviewed_at": review.last_reviewed_at.isoformat() if review.last_reviewed_at else None,
        "next_review_at": review.next_review_at.isoformat() if review.next_review_at else None,
    }


def deck_cards_payload(*, deck: FlashcardDeck, user=None) -> list[dict[str, object]]:
    reviews = _reviews_for_deck(user=user, subject_slug=deck.subject_slug, deck_slug=deck.deck_slug)

    def sort_key(card: dict[str, object]) -> tuple[int, int, str, str]:
        card_id = str(card.get("card_id") or "")
        review = reviews.get(card_id)
        if review is None:
            return (0, 0, "", card_id)
        reviewed_at = review.last_reviewed_at.isoformat() if review.last_reviewed_at else ""
        return (1, RATING_SORT_ORDER.get(review.rating, 9), reviewed_at, card_id)

    cards = sorted(deck.cards, key=sort_key) if reviews else list(deck.cards)
    payload: list[dict[str, object]] = []
    for card in cards:
        card_id = str(card.get("card_id") or "")
        payload.append(
            {
                "card_id": card_id,
                "front_text": str(card.get("front_text") or ""),
                "back_html": str(card.get("back_html") or ""),
                "tags": card.get("tags") if isinstance(card.get("tags"), list) else [],
                "review": _card_review_payload(reviews.get(card_id)),
            }
        )
    return payload


def flashcard_deck_api_payload(*, deck: FlashcardDeck, user=None) -> dict[str, object]:
    return {
        "subject_slug": deck.subject_slug,
        "deck_slug": deck.deck_slug,
        "title": deck.title,
        "description": deck.description,
        "source_file": deck.source_file,
        "generated_at": deck.generated_at,
        "card_count": deck.card_count,
        "review_summary": review_summary_for_deck(
            user=user,
            subject_slug=deck.subject_slug,
            deck_slug=deck.deck_slug,
            card_count=deck.card_count,
        )
        if user is not None and getattr(user, "is_authenticated", False)
        else None,
        "cards": deck_cards_payload(deck=deck, user=user),
    }


def next_review_at_for_rating(rating: str):
    offset = RATING_DUE_OFFSETS.get(rating)
    if offset is None:
        return None
    return timezone.now() + offset


def upsert_flashcard_review(*, user, subject_slug: str, deck_slug: str, card_id: str, rating: str) -> FlashcardReview:
    if rating not in FLASHCARD_RATINGS:
        raise FlashcardValidationError("Invalid flashcard rating.")
    deck = load_flashcard_deck(subject_slug, deck_slug)
    known_card_ids = {str(card.get("card_id") or "") for card in deck.cards}
    if card_id not in known_card_ids:
        raise FlashcardValidationError("Unknown flashcard card_id.")

    now = timezone.now()
    review, created = FlashcardReview.objects.get_or_create(
        user=user,
        subject_slug=deck.subject_slug,
        deck_slug=deck.deck_slug,
        card_id=card_id,
        defaults={
            "rating": rating,
            "review_count": 0,
        },
    )
    review.rating = rating
    review.review_count = int(review.review_count or 0) + 1
    review.last_reviewed_at = now
    review.next_review_at = next_review_at_for_rating(rating)
    review.save(
        update_fields=[
            "rating",
            "review_count",
            "last_reviewed_at",
            "next_review_at",
            "updated_at",
        ]
        if not created
        else None
    )
    return review
