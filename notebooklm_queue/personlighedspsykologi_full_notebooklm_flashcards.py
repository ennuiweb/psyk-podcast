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

FULL_NOTEBOOKLM_DECK_SLUG = "notebooklm-fuld-matrix-personlighedspsykologi"
FULL_NOTEBOOKLM_DECK_TITLE = "NotebookLM fuld matrix: personlighedspsykologi"
FULL_NOTEBOOKLM_DECK_DESCRIPTION = (
    "Nyeste NotebookLM-kort fra alle matrixklynger, genereret uden de tidligere Freudd-kort som NotebookLM-kilde."
)
FULL_NOTEBOOKLM_GENERATOR_VERSION = "personlighedspsykologi-full-notebooklm-flashcards-v1"
INCLUDED_REVIEW_STATUSES = frozenset({"candidate", "needs_review"})
EXCLUDED_REVIEW_STATUSES = frozenset({"auto_rejected"})


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


def source_fingerprint(candidate_payloads: list[dict[str, Any]]) -> str:
    return semantic_fingerprint(
        [
            {
                "run_id": _text(payload.get("run_id")),
                "notebook_slug": _text(payload.get("notebook_slug")),
                "source_path": _text(payload.get("source_path")),
                "stats": payload.get("stats"),
                "candidates": payload.get("candidates"),
            }
            for payload in candidate_payloads
        ]
    )


def _card_from_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    candidate_id = _text(candidate.get("candidate_id"))
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,96}", candidate_id):
        raise FullNotebookLMFlashcardError(f"Invalid NotebookLM candidate_id: {candidate_id}")
    front = _text(candidate.get("front"))
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


def build_full_notebooklm_deck(
    *,
    candidate_payloads: list[dict[str, Any]],
    source_file: str,
    source_sha256: str,
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
        validate_variant_deck(artifact, expected_deck_slug=FULL_NOTEBOOKLM_DECK_SLUG)
    except NotebookLMVariantFlashcardError as exc:
        raise FullNotebookLMFlashcardError(str(exc)) from exc
    return artifact


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
