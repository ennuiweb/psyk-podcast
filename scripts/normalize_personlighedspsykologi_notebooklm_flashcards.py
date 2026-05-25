#!/usr/bin/env python3
"""Normalize downloaded NotebookLM flashcards into review-only candidates."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from notebooklm_queue.json_artifact_utils import write_json_stably
from notebooklm_queue.personlighedspsykologi_notebooklm_flashcard_lab import (
    DEFAULT_DECK_PATH,
    DEFAULT_LAB_ROOT,
    DEFAULT_MATRIX_PATH,
    FlashcardLabError,
    load_current_deck,
    load_matrix,
    load_notebooklm_flashcard_payload,
    normalize_notebooklm_cards,
    write_candidate_review_markdown,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--notebook-slug", required=True)
    parser.add_argument("--input-json", type=Path, required=True)
    parser.add_argument("--lab-root", type=Path, default=DEFAULT_LAB_ROOT)
    parser.add_argument("--matrix-path", type=Path, default=DEFAULT_MATRIX_PATH)
    parser.add_argument("--deck-path", type=Path, default=DEFAULT_DECK_PATH)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--review-md", type=Path, default=None)
    return parser.parse_args()


def _resolve_repo_path(path: Path, repo_root: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _default_output_path(lab_root: Path, run_id: str, notebook_slug: str) -> Path:
    return lab_root / "runs" / run_id / "candidates" / f"{notebook_slug}.candidates.json"


def _default_review_path(output_path: Path) -> Path:
    if output_path.name.endswith(".candidates.json"):
        return output_path.with_name(output_path.name.replace(".candidates.json", ".review.md"))
    return output_path.with_suffix(".review.md")


def _repo_relative(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    lab_root = _resolve_repo_path(args.lab_root, repo_root)
    input_json = _resolve_repo_path(args.input_json, repo_root)
    output_path = _resolve_repo_path(args.output_path, repo_root) if args.output_path else _default_output_path(
        lab_root, args.run_id, args.notebook_slug
    )
    review_path = _resolve_repo_path(args.review_md, repo_root) if args.review_md else _default_review_path(output_path)
    try:
        matrix = load_matrix(_resolve_repo_path(args.matrix_path, repo_root))
        deck = load_current_deck(_resolve_repo_path(args.deck_path, repo_root), matrix)
        raw_payload = load_notebooklm_flashcard_payload(input_json)
        candidates = normalize_notebooklm_cards(
            notebooklm_payload=raw_payload,
            matrix=matrix,
            current_deck=deck,
            run_id=args.run_id,
            notebook_slug=args.notebook_slug,
            source_path=_repo_relative(input_json, repo_root),
        )
    except FlashcardLabError as exc:
        raise SystemExit(f"NotebookLM flashcard normalization failed: {exc}") from exc

    candidates, changed = write_json_stably(output_path, candidates)
    write_candidate_review_markdown(candidates, review_path)
    stats = candidates.get("stats", {}) if isinstance(candidates, dict) else {}
    print(
        f"normalized {stats.get('candidate_count', 0)} candidate(s) "
        f"from {stats.get('raw_card_count', 0)} raw card(s) to {output_path}"
        f"{' (updated)' if changed else ' (unchanged)'}"
    )
    print(f"review markdown: {review_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
