"""Build the learner-facing Freudd deck from the full NotebookLM matrix run."""

from __future__ import annotations

import hashlib
import html
import re
from collections import Counter
from pathlib import Path
from typing import Any

from notebooklm_queue.json_artifact_utils import semantic_fingerprint
from notebooklm_queue.personlighedspsykologi_matrix_flashcards import (
    CATEGORIES,
    FLASHCARD_ARTIFACT_TYPE,
    FLASHCARD_VERSION,
    SUBJECT_SLUG,
)
from notebooklm_queue.personlighedspsykologi_notebooklm_flashcard_lab import (
    FlashcardLabError,
    utc_now_iso,
)
from notebooklm_queue.personlighedspsykologi_notebooklm_variant_flashcards import (
    NotebookLMVariantFlashcardError,
    validate_variant_deck,
)
from notebooklm_queue.personlighedspsykologi_gap_repair_review import (
    gap_repair_decisions_to_candidate_payload,
    load_gap_repair_promotion_decisions,
)
from notebooklm_queue.personlighedspsykologi_coverage_closure_flashcards import (
    coverage_closure_to_candidate_payload,
    load_coverage_closure_artifact,
)
from notebooklm_queue.personlighedspsykologi_answer_enrichment import (
    apply_answer_enrichment_overlays,
    load_answer_enrichment_payload,
)
from notebooklm_queue.personlighedspsykologi_flashcard_backgrounds import (
    apply_flashcard_background_overlays,
    load_flashcard_background_payload,
)

FULL_NOTEBOOKLM_DECK_SLUG = "notebooklm-fuld-matrix-personlighedspsykologi"
FULL_NOTEBOOKLM_DECK_TITLE = "Personlighedspsykologi: eksamenskort"
FULL_NOTEBOOKLM_DECK_DESCRIPTION = (
    "Kort til repetition af teorier, begreber, metoder og sammenligninger i personlighedspsykologi."
)
FULL_NOTEBOOKLM_GENERATOR_VERSION = "personlighedspsykologi-full-notebooklm-flashcards-v1"
INCLUDED_REVIEW_STATUSES = frozenset({"candidate", "needs_review"})
EXCLUDED_REVIEW_STATUSES = frozenset({"auto_rejected"})
ALWAYS_REMOVABLE_FRONT_PREFIXES = frozenset(
    {
        "Agency",
        "Begreb",
        "Begrænsning",
        "Eksamenstrap",
        "Eksamensfælde",
        "Historicitet",
        "Kritik",
        "Metode",
        "Orienteringspunkt",
        "Orienteringspunkter",
        "Personbegreb",
        "Sammenligning",
        "Styrke",
        "Styrker og begrænsninger",
    }
)
CONDITIONAL_REMOVABLE_FRONT_PREFIX_KEYWORDS = {
    "Trækpsykologi": ("træk", "assessment"),
}
LEARNER_FACING_PROVENANCE_PATTERNS = (
    re.compile(r"\bmatrix(?:en|ens)?\b", re.IGNORECASE),
    re.compile(r"\bkildegrundlag(?:et)?\b", re.IGNORECASE),
    re.compile(r"\bkildesubstrat(?:et)?\b", re.IGNORECASE),
    re.compile(r"\bsubstrat(?:et)?\b", re.IGNORECASE),
    re.compile(r"\bsource(?:s)?\b", re.IGNORECASE),
)


class FullNotebookLMFlashcardError(ValueError):
    """Raised when the full NotebookLM Freudd deck cannot be built safely."""


def _text(value: object) -> str:
    return str(value or "").strip()


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_str_list(value: object) -> list[str]:
    return [str(item).strip() for item in _as_list(value) if str(item).strip()]


def _content_hash(front: str, back: str, category_slug: str, candidate_id: str) -> str:
    return hashlib.sha256(f"{candidate_id}\n{category_slug}\n{front}\n{back}".encode("utf-8")).hexdigest()


def _html_answer(value: str) -> str:
    escaped = html.escape(value).replace("\n", "<br>")
    return f"<div>{escaped}</div>"


def _category_title(category_slug: str) -> str:
    for category in CATEGORIES:
        if category["slug"] == category_slug:
            return category["title"]
    raise FullNotebookLMFlashcardError(f"Unknown category_slug in NotebookLM candidate: {category_slug}")


def _repo_relative(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def _load_candidate_payload(path: Path) -> dict[str, Any]:
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise FullNotebookLMFlashcardError(f"Unable to read NotebookLM candidates: {path}") from exc
    if not isinstance(payload, dict):
        raise FullNotebookLMFlashcardError(f"NotebookLM candidates root must be an object: {path}")
    if payload.get("artifact_type") != "personlighedspsykologi_notebooklm_flashcard_candidates":
        raise FullNotebookLMFlashcardError(f"Unexpected NotebookLM candidate artifact_type: {path}")
    if payload.get("subject_slug") != SUBJECT_SLUG:
        raise FullNotebookLMFlashcardError(f"Unexpected NotebookLM candidate subject_slug: {path}")
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise FullNotebookLMFlashcardError(f"NotebookLM candidates list missing or invalid: {path}")
    return payload


def load_candidate_payloads(candidate_paths: list[Path]) -> list[dict[str, Any]]:
    if not candidate_paths:
        raise FullNotebookLMFlashcardError("At least one NotebookLM candidate file is required")
    return [_load_candidate_payload(path) for path in candidate_paths]


def source_fingerprint(
    candidate_payloads: list[dict[str, Any]],
    answer_enrichment_payloads: list[dict[str, Any]] | None = None,
    background_payloads: list[dict[str, Any]] | None = None,
) -> str:
    return semantic_fingerprint(
        {
            "candidate_payloads": [
                {
                    "run_id": _text(payload.get("run_id")),
                    "notebook_slug": _text(payload.get("notebook_slug")),
                    "source_path": _text(payload.get("source_path")),
                    "stats": payload.get("stats"),
                    "candidates": payload.get("candidates"),
                }
                for payload in candidate_payloads
            ],
            "answer_enrichment_payloads": [
                {
                    "artifact_type": _text(payload.get("artifact_type")),
                    "stats": payload.get("stats"),
                    "overrides": payload.get("overrides"),
                }
                for payload in (answer_enrichment_payloads or [])
            ],
            "background_payloads": [
                {
                    "artifact_type": _text(payload.get("artifact_type")),
                    "stats": payload.get("stats"),
                    "backgrounds": payload.get("backgrounds"),
                }
                for payload in (background_payloads or [])
            ],
        }
    )


def strip_safe_front_prefix(front: str) -> str:
    match = re.match(r"^([^:]{1,55}):\s+(.+)$", front)
    if not match:
        return front
    prefix, body = match.groups()
    if prefix in ALWAYS_REMOVABLE_FRONT_PREFIXES:
        return body
    keywords = CONDITIONAL_REMOVABLE_FRONT_PREFIX_KEYWORDS.get(prefix)
    if keywords and any(keyword in body.casefold() for keyword in keywords):
        return body
    return front


def clean_learner_facing_provenance(text: str) -> str:
    replacements = [
        (r"\s+ifølge matrixen\b", ""),
        (r"\s+i matrixen\b", ""),
        (r"\bmatrixens\b", "teoriens"),
        (r"\bmatrixen\b", "teorien"),
        (r"\bkildegrundlag(?:et)?\b", "centrale begreber"),
        (r"\bkildesubstrat(?:et)?\b", "faglige begreber"),
        (r"\bsubstrat(?:et)?\b", "faglige grundlag"),
        (r"\bsource(?:s)?\b", "fagligt materiale"),
    ]
    cleaned = text
    for pattern, replacement in replacements:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+([?.!,;:])", r"\1", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def assert_no_learner_facing_provenance(*, card_id: str, fields: dict[str, str]) -> None:
    for field, text in fields.items():
        for pattern in LEARNER_FACING_PROVENANCE_PATTERNS:
            if pattern.search(text):
                raise FullNotebookLMFlashcardError(
                    f"Learner-facing provenance leaked in {card_id}.{field}: {pattern.pattern}"
                )


def _card_from_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    candidate_id = _text(candidate.get("candidate_id"))
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,96}", candidate_id):
        raise FullNotebookLMFlashcardError(f"Invalid NotebookLM candidate_id: {candidate_id}")
    front = clean_learner_facing_provenance(strip_safe_front_prefix(_text(candidate.get("front"))))
    back = _text(candidate.get("back"))
    if not front or not back:
        raise FullNotebookLMFlashcardError(f"NotebookLM candidate missing learner text: {candidate_id}")
    category_slug = _text(candidate.get("category_slug"))
    category_title = _category_title(category_slug)
    status = _text(candidate.get("review_status"))
    notebook_slug = _text(candidate.get("notebook_slug"))
    tags = {
        "notebooklm-full-matrix",
        f"notebook:{notebook_slug}",
        f"review:{status}",
        category_slug,
        *_as_str_list(candidate.get("mapped_theory_ids")),
        *_as_str_list(candidate.get("tags")),
    }
    return {
        "card_id": candidate_id,
        "front_text": front,
        "back_html_sanitized": _html_answer(back),
        "back_text": back,
        "tags": sorted(tag for tag in tags if tag),
        "category_slug": category_slug,
        "category_title": category_title,
        "content_sha256": _content_hash(front, back, category_slug, candidate_id),
    }


def clean_deck_learner_facing_provenance(deck: dict[str, Any]) -> dict[str, Any]:
    cards = deck.get("cards")
    if not isinstance(cards, list):
        raise FullNotebookLMFlashcardError("Deck cards must be a list before provenance cleanup")
    for card in cards:
        if not isinstance(card, dict):
            continue
        card_id = _text(card.get("card_id"))
        front = clean_learner_facing_provenance(_text(card.get("front_text")))
        back = clean_learner_facing_provenance(_text(card.get("back_text")))
        background = clean_learner_facing_provenance(_text(card.get("background_text")))
        card["front_text"] = front
        card["back_text"] = back
        card["back_html_sanitized"] = _html_answer(back)
        if background:
            card["background_text"] = background
            card["background_html_sanitized"] = _html_answer(background)
        category_slug = _text(card.get("category_slug"))
        card["content_sha256"] = _content_hash(front, back, category_slug, card_id)
    return deck


def build_full_notebooklm_deck(
    *,
    candidate_payloads: list[dict[str, Any]],
    source_file: str,
    source_sha256: str,
    answer_enrichment_payloads: list[dict[str, Any]] | None = None,
    background_payloads: list[dict[str, Any]] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    cards: list[dict[str, Any]] = []
    raw_status_counts: Counter[str] = Counter()
    included_status_counts: Counter[str] = Counter()
    notebook_counts: Counter[str] = Counter()
    run_ids: set[str] = set()
    notebook_slugs: set[str] = set()
    for payload in candidate_payloads:
        run_id = _text(payload.get("run_id"))
        notebook_slug = _text(payload.get("notebook_slug"))
        if run_id:
            run_ids.add(run_id)
        if notebook_slug:
            notebook_slugs.add(notebook_slug)
        for candidate in payload["candidates"]:
            if not isinstance(candidate, dict):
                raise FullNotebookLMFlashcardError("NotebookLM candidate entries must be objects")
            status = _text(candidate.get("review_status"))
            raw_status_counts[status] += 1
            if status in EXCLUDED_REVIEW_STATUSES:
                continue
            if status not in INCLUDED_REVIEW_STATUSES:
                raise FullNotebookLMFlashcardError(
                    f"Unexpected NotebookLM candidate review_status {status!r} in {_text(candidate.get('candidate_id'))}"
                )
            card = _card_from_candidate(candidate)
            cards.append(card)
            included_status_counts[status] += 1
            notebook_counts[_text(candidate.get("notebook_slug"))] += 1

    if not cards:
        raise FullNotebookLMFlashcardError("No learner-facing NotebookLM cards after filtering")
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
        "deck_slug": FULL_NOTEBOOKLM_DECK_SLUG,
        "title": FULL_NOTEBOOKLM_DECK_TITLE,
        "source_file": source_file,
        "source_sha256": source_sha256,
        "generated_at": generated_at or utc_now_iso(),
        "generator": {
            "name": "scripts/build_personlighedspsykologi_full_notebooklm_flashcards.py",
            "version": FULL_NOTEBOOKLM_GENERATOR_VERSION,
            "source_authority": "full_notebooklm_matrix_candidate_run",
            "inclusion_policy": "include candidate and needs_review; exclude auto_rejected",
        },
        "run_ids": sorted(run_ids),
        "notebook_slugs": sorted(notebook_slugs),
        "candidate_status_counts": dict(sorted(raw_status_counts.items())),
        "included_status_counts": dict(sorted(included_status_counts.items())),
        "included_notebook_counts": dict(sorted(notebook_counts.items())),
        "card_count": len(cards),
        "categories": categories,
        "cards": cards,
    }
    try:
        apply_answer_enrichment_overlays(
            artifact,
            answer_enrichment_payloads or [],
            html_answer=_html_answer,
            content_hash=_content_hash,
        )
        clean_deck_learner_facing_provenance(artifact)
        apply_flashcard_background_overlays(
            artifact,
            background_payloads or [],
            html_background=_html_answer,
        )
        clean_deck_learner_facing_provenance(artifact)
    except ValueError as exc:
        raise FullNotebookLMFlashcardError(str(exc)) from exc
    try:
        validate_variant_deck(artifact, expected_deck_slug=FULL_NOTEBOOKLM_DECK_SLUG)
    except NotebookLMVariantFlashcardError as exc:
        raise FullNotebookLMFlashcardError(str(exc)) from exc
    for card in artifact.get("cards", []):
        if isinstance(card, dict):
            assert_no_learner_facing_provenance(
                card_id=_text(card.get("card_id")),
                fields={
                    "front_text": _text(card.get("front_text")),
                    "back_text": _text(card.get("back_text")),
                    "background_text": _text(card.get("background_text")),
                },
            )
    return artifact


def load_gap_repair_candidate_payloads(decision_paths: list[Path]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for path in decision_paths:
        decisions = load_gap_repair_promotion_decisions(path)
        payloads.append(gap_repair_decisions_to_candidate_payload(decisions))
    return payloads


def load_coverage_closure_candidate_payloads(artifact_paths: list[Path]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for path in artifact_paths:
        payloads.append(coverage_closure_to_candidate_payload(load_coverage_closure_artifact(path)))
    return payloads


def load_answer_enrichment_payloads(artifact_paths: list[Path]) -> list[dict[str, Any]]:
    return [load_answer_enrichment_payload(path) for path in artifact_paths]


def load_background_payloads(artifact_paths: list[Path]) -> list[dict[str, Any]]:
    return [load_flashcard_background_payload(path) for path in artifact_paths]


def build_single_deck_registry(*, artifact_path: str, card_count: int) -> dict[str, Any]:
    return {
        "version": 1,
        "subject_slug": SUBJECT_SLUG,
        "decks": [
            {
                "deck_slug": FULL_NOTEBOOKLM_DECK_SLUG,
                "title": FULL_NOTEBOOKLM_DECK_TITLE,
                "description": FULL_NOTEBOOKLM_DECK_DESCRIPTION,
                "artifact_path": artifact_path,
                "card_count": int(card_count),
                "enabled": True,
            }
        ],
    }
