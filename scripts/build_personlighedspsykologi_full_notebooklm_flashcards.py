#!/usr/bin/env python3
"""Build the live Freudd deck from the newest full NotebookLM matrix run."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from notebooklm_queue.json_artifact_utils import write_json_stably
from notebooklm_queue.personlighedspsykologi_full_notebooklm_flashcards import (
    FULL_NOTEBOOKLM_DECK_SLUG,
    FullNotebookLMFlashcardError,
    build_full_notebooklm_deck,
    build_single_deck_registry,
    load_candidate_payloads,
    source_fingerprint,
)

DEFAULT_RUN_DIR = (
    Path("notebooklm-podcast-auto/personlighedspsykologi/flashcard_lab/runs")
    / "full-matrix-20260526-notebooklm-independent"
)
DEFAULT_CANDIDATES_DIR = DEFAULT_RUN_DIR / "candidates"
DEFAULT_FLASHCARD_DIR = Path("shows/personlighedspsykologi-en/flashcards")
DEFAULT_DECK_PATH = DEFAULT_FLASHCARD_DIR / f"{FULL_NOTEBOOKLM_DECK_SLUG}.json"
DEFAULT_REGISTRY_PATH = DEFAULT_FLASHCARD_DIR / "decks.json"


def _resolve_repo_path(path: Path, repo_root: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _repo_relative(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def _candidate_paths(candidates_dir: Path) -> list[Path]:
    paths = sorted(candidates_dir.glob("*.candidates.json"))
    if not paths:
        raise FullNotebookLMFlashcardError(f"No NotebookLM candidate files found in {candidates_dir}")
    return paths


def build(args: argparse.Namespace) -> dict[str, Any]:
    repo_root = args.repo_root.resolve()
    args.candidates_dir = _resolve_repo_path(args.candidates_dir, repo_root)
    args.deck_path = _resolve_repo_path(args.deck_path, repo_root)
    args.registry_path = _resolve_repo_path(args.registry_path, repo_root)

    candidate_paths = _candidate_paths(args.candidates_dir)
    if args.expected_notebook_count is not None and len(candidate_paths) != args.expected_notebook_count:
        raise FullNotebookLMFlashcardError(
            f"Expected {args.expected_notebook_count} NotebookLM candidate files, found {len(candidate_paths)}"
        )

    candidate_payloads = load_candidate_payloads(candidate_paths)
    source_file = _repo_relative(args.candidates_dir, repo_root)
    deck_artifact_path = _repo_relative(args.deck_path, repo_root)
    deck = build_full_notebooklm_deck(
        candidate_payloads=candidate_payloads,
        source_file=source_file,
        source_sha256=source_fingerprint(candidate_payloads),
    )
    registry = build_single_deck_registry(
        artifact_path=deck_artifact_path,
        card_count=int(deck["card_count"]),
    )

    if not args.validate_only and not args.dry_run:
        deck, _ = write_json_stably(args.deck_path, deck)
        registry, _ = write_json_stably(args.registry_path, registry)

    return {"deck": deck, "registry": registry, "candidate_paths": candidate_paths}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--candidates-dir", type=Path, default=DEFAULT_CANDIDATES_DIR)
    parser.add_argument("--deck-path", type=Path, default=DEFAULT_DECK_PATH)
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--expected-notebook-count", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true", help="Build and validate without writing files.")
    parser.add_argument("--validate-only", action="store_true", help="Validate generation without writing files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = build(args)
    except FullNotebookLMFlashcardError as exc:
        raise SystemExit(f"full NotebookLM flashcard build failed: {exc}") from exc
    deck = payload["deck"]
    action = "validated" if args.validate_only else "built"
    print(
        f"{action} {deck.get('deck_slug')} "
        f"(cards={deck.get('card_count')}, categories={len(deck.get('categories', []))}, "
        f"sources={len(payload.get('candidate_paths', []))})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
