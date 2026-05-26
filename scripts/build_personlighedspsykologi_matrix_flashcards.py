#!/usr/bin/env python3
"""Build Freudd flashcards from the personlighedspsykologi exam matrix."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from notebooklm_queue.json_artifact_utils import write_json_stably
from notebooklm_queue.personlighedspsykologi_matrix_flashcards import (
    FLASHCARD_DECK_SLUG,
    MatrixFlashcardBuildError,
    build_flashcard_deck,
    build_flashcard_registry,
    load_matrix,
    source_fingerprint,
    validate_flashcard_artifact,
)

DEFAULT_MATRIX_PATH = Path("shows/personlighedspsykologi-en/student_synthesis/exam_theory_matrix.json")
DEFAULT_FLASHCARD_DIR = Path("shows/personlighedspsykologi-en/flashcards")
DEFAULT_DECK_PATH = DEFAULT_FLASHCARD_DIR / f"{FLASHCARD_DECK_SLUG}.json"
DEFAULT_REGISTRY_PATH = DEFAULT_FLASHCARD_DIR / "decks.json"


def _repo_relative(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def _preserved_registry_decks(registry_path: Path) -> list[dict[str, object]]:
    if not registry_path.exists():
        return []
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MatrixFlashcardBuildError(f"Unable to load existing flashcard registry: {registry_path}") from exc
    decks = payload.get("decks") if isinstance(payload, dict) else None
    if not isinstance(decks, list):
        raise MatrixFlashcardBuildError(f"Existing flashcard registry has invalid decks list: {registry_path}")
    preserved: list[dict[str, object]] = []
    for deck in decks:
        if not isinstance(deck, dict):
            raise MatrixFlashcardBuildError(f"Existing flashcard registry contains invalid deck entry: {registry_path}")
        if str(deck.get("deck_slug") or "").strip() != FLASHCARD_DECK_SLUG:
            preserved.append(dict(deck))
    return preserved


def build(args: argparse.Namespace) -> dict[str, object]:
    repo_root = args.repo_root.resolve()
    matrix = load_matrix(args.matrix_path)
    source_file = _repo_relative(args.matrix_path, repo_root)
    deck_artifact_path = _repo_relative(args.deck_path, repo_root)
    deck = build_flashcard_deck(
        matrix=matrix,
        source_file=source_file,
        source_sha256=source_fingerprint(args.matrix_path),
    )
    registry = build_flashcard_registry(
        artifact_path=deck_artifact_path,
        card_count=int(deck["card_count"]),
        extra_decks=_preserved_registry_decks(args.registry_path),
    )
    validate_flashcard_artifact(deck, matrix=matrix)

    if not args.validate_only and not args.dry_run:
        deck, _ = write_json_stably(args.deck_path, deck)
        registry, _ = write_json_stably(args.registry_path, registry)

    return {
        "deck": deck,
        "registry": registry,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--matrix-path", type=Path, default=DEFAULT_MATRIX_PATH)
    parser.add_argument("--deck-path", type=Path, default=DEFAULT_DECK_PATH)
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--dry-run", action="store_true", help="Build and validate without writing files.")
    parser.add_argument("--validate-only", action="store_true", help="Validate generation without writing files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = build(args)
    except MatrixFlashcardBuildError as exc:
        raise SystemExit(f"matrix flashcard build failed: {exc}") from exc
    deck = payload["deck"]
    if not isinstance(deck, dict):
        raise SystemExit("matrix flashcard build failed: deck payload is invalid")
    action = "validated" if args.validate_only else "built"
    print(
        f"{action} {deck.get('deck_slug')} "
        f"(cards={deck.get('card_count')}, categories={len(deck.get('categories', []))})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
