#!/usr/bin/env python3
"""Build Freudd variant flashcards from Gemini-reviewed NotebookLM candidates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from notebooklm_queue.json_artifact_utils import write_json_stably
from notebooklm_queue.personlighedspsykologi_matrix_flashcards import SUBJECT_SLUG
from notebooklm_queue.personlighedspsykologi_notebooklm_variant_flashcards import (
    VARIANT_DECK_DESCRIPTION,
    VARIANT_DECK_SLUG,
    VARIANT_DECK_TITLE,
    NotebookLMVariantFlashcardError,
    build_promotion_decisions,
    build_variant_deck,
    load_candidates_and_review,
    load_promotion_decisions,
    source_fingerprint,
    validate_variant_deck,
)

DEFAULT_FLASHCARD_DIR = Path("shows/personlighedspsykologi-en/flashcards")
DEFAULT_ARCHIVE_DIR = DEFAULT_FLASHCARD_DIR / "archive" / "retired-live-decks-2026-05-26"
DEFAULT_PROMOTION_DECISIONS_PATH = DEFAULT_ARCHIVE_DIR / "notebooklm_variant_promotion_decisions.json"
DEFAULT_DECK_PATH = DEFAULT_ARCHIVE_DIR / f"{VARIANT_DECK_SLUG}.json"
DEFAULT_REGISTRY_PATH = DEFAULT_FLASHCARD_DIR / "decks.json"
DEFAULT_RUN_DIR = (
    Path("notebooklm-podcast-auto/personlighedspsykologi/flashcard_lab/runs")
    / "pilot-20260525-critical-sociocultural-narrative"
)
DEFAULT_CANDIDATES_PATH = DEFAULT_RUN_DIR / "candidates" / "critical-sociocultural-narrative.candidates.json"
DEFAULT_GEMINI_REVIEW_PATH = DEFAULT_RUN_DIR / "gemini_review" / "critical-sociocultural-narrative.gemini-review.json"


def _resolve_repo_path(path: Path, repo_root: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _repo_relative(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def _load_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "subject_slug": SUBJECT_SLUG, "decks": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NotebookLMVariantFlashcardError(f"Unable to load existing flashcard registry: {path}") from exc
    if not isinstance(payload, dict):
        raise NotebookLMVariantFlashcardError(f"Flashcard registry must be an object: {path}")
    if payload.get("version") != 1 or payload.get("subject_slug") != SUBJECT_SLUG:
        raise NotebookLMVariantFlashcardError(f"Flashcard registry has invalid version or subject_slug: {path}")
    decks = payload.get("decks")
    if not isinstance(decks, list):
        raise NotebookLMVariantFlashcardError(f"Flashcard registry has invalid decks list: {path}")
    for deck in decks:
        if not isinstance(deck, dict) or not str(deck.get("deck_slug") or "").strip():
            raise NotebookLMVariantFlashcardError(f"Flashcard registry contains invalid deck entry: {path}")
    return payload


def _variant_registry_entry(
    *,
    deck_slug: str,
    title: str,
    description: str,
    artifact_path: str,
    card_count: int,
) -> dict[str, Any]:
    return {
        "deck_slug": deck_slug,
        "title": title,
        "description": description,
        "artifact_path": artifact_path,
        "card_count": int(card_count),
        "enabled": True,
    }


def _build_registry(
    *,
    registry_path: Path,
    deck_slug: str,
    title: str,
    description: str,
    artifact_path: str,
    card_count: int,
) -> dict[str, Any]:
    current = _load_registry(registry_path)
    decks = [
        dict(deck)
        for deck in current.get("decks", [])
        if isinstance(deck, dict) and str(deck.get("deck_slug") or "").strip() != deck_slug
    ]
    decks.append(
        _variant_registry_entry(
            deck_slug=deck_slug,
            title=title,
            description=description,
            artifact_path=artifact_path,
            card_count=card_count,
        )
    )
    return {"version": 1, "subject_slug": SUBJECT_SLUG, "decks": decks}


def _build_promotion_payload(args: argparse.Namespace) -> dict[str, Any]:
    candidates_path = args.candidates_json
    gemini_review_path = args.gemini_review_json
    if candidates_path.exists() and gemini_review_path.exists() and not args.from_existing_decisions:
        candidates, review = load_candidates_and_review(candidates_path, gemini_review_path)
        return build_promotion_decisions(
            candidates_payload=candidates,
            gemini_review_payload=review,
            deck_slug=args.deck_slug,
        )
    return load_promotion_decisions(args.promotion_decisions_path)


def build(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = args.repo_root.resolve()
    args.candidates_json = _resolve_repo_path(args.candidates_json, repo_root)
    args.gemini_review_json = _resolve_repo_path(args.gemini_review_json, repo_root)
    args.promotion_decisions_path = _resolve_repo_path(args.promotion_decisions_path, repo_root)
    args.deck_path = _resolve_repo_path(args.deck_path, repo_root)
    args.registry_path = _resolve_repo_path(args.registry_path, repo_root)

    promotion_decisions = _build_promotion_payload(args)
    source_file = _repo_relative(args.promotion_decisions_path, repo_root)
    deck_artifact_path = _repo_relative(args.deck_path, repo_root)
    deck = build_variant_deck(
        promotion_decisions=promotion_decisions,
        source_file=source_file,
        source_sha256=source_fingerprint(args.promotion_decisions_path)
        if args.promotion_decisions_path.exists()
        else "",
        deck_slug=args.deck_slug,
        title=args.title,
    )
    registry = None
    if args.update_registry:
        registry = _build_registry(
            registry_path=args.registry_path,
            deck_slug=args.deck_slug,
            title=args.title,
            description=args.description,
            artifact_path=deck_artifact_path,
            card_count=int(deck["card_count"]),
        )
    validate_variant_deck(deck, expected_deck_slug=args.deck_slug)

    if not args.validate_only and not args.dry_run:
        promotion_decisions, _ = write_json_stably(args.promotion_decisions_path, promotion_decisions)
        deck = build_variant_deck(
            promotion_decisions=promotion_decisions,
            source_file=source_file,
            source_sha256=source_fingerprint(args.promotion_decisions_path),
            deck_slug=args.deck_slug,
            title=args.title,
        )
        deck, _ = write_json_stably(args.deck_path, deck)
        if args.update_registry:
            registry = _build_registry(
                registry_path=args.registry_path,
                deck_slug=args.deck_slug,
                title=args.title,
                description=args.description,
                artifact_path=deck_artifact_path,
                card_count=int(deck["card_count"]),
            )
            registry, _ = write_json_stably(args.registry_path, registry)

    return {"promotion_decisions": promotion_decisions, "deck": deck, "registry": registry}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--candidates-json", type=Path, default=DEFAULT_CANDIDATES_PATH)
    parser.add_argument("--gemini-review-json", type=Path, default=DEFAULT_GEMINI_REVIEW_PATH)
    parser.add_argument("--promotion-decisions-path", type=Path, default=DEFAULT_PROMOTION_DECISIONS_PATH)
    parser.add_argument("--deck-path", type=Path, default=DEFAULT_DECK_PATH)
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--deck-slug", default=VARIANT_DECK_SLUG)
    parser.add_argument("--title", default=VARIANT_DECK_TITLE)
    parser.add_argument("--description", default=VARIANT_DECK_DESCRIPTION)
    parser.add_argument(
        "--update-registry",
        action="store_true",
        help="Also write this archived variant deck into decks.json. This should normally stay off.",
    )
    parser.add_argument(
        "--from-existing-decisions",
        action="store_true",
        help="Ignore local NotebookLM/Gemini run files and rebuild only from the committed decisions artifact.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Build and validate without writing files.")
    parser.add_argument("--validate-only", action="store_true", help="Validate generation without writing files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = build(args)
    except NotebookLMVariantFlashcardError as exc:
        raise SystemExit(f"NotebookLM variant flashcard build failed: {exc}") from exc
    deck = payload["deck"]
    action = "validated" if args.validate_only else "built"
    print(
        f"{action} {deck.get('deck_slug')} "
        f"(cards={deck.get('card_count')}, categories={len(deck.get('categories', []))})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
