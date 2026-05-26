#!/usr/bin/env python3
"""Audit live personlighedspsykologi flashcards against the full matrix."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from notebooklm_queue.json_artifact_utils import write_json_stably
from notebooklm_queue.personlighedspsykologi_flashcard_coverage import (
    DEFAULT_DECK_PATH,
    DEFAULT_MATRIX_PATH,
    DEFAULT_OUTPUT_JSON,
    DEFAULT_OUTPUT_MD,
    DEFAULT_SOURCE_NOTES_INDEX_PATH,
    DEFAULT_SOURCE_NOTES_REGISTRY_PATH,
    FlashcardCoverageError,
    build_coverage_report,
    render_coverage_markdown,
)


def _resolve_repo_path(path: Path, repo_root: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--matrix-path", type=Path, default=DEFAULT_MATRIX_PATH)
    parser.add_argument("--deck-path", type=Path, default=DEFAULT_DECK_PATH)
    parser.add_argument("--source-notes-index-path", type=Path, default=DEFAULT_SOURCE_NOTES_INDEX_PATH)
    parser.add_argument("--source-notes-registry-path", type=Path, default=DEFAULT_SOURCE_NOTES_REGISTRY_PATH)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--dry-run", action="store_true", help="Build and validate without writing files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    try:
        report = build_coverage_report(
            repo_root=repo_root,
            matrix_path=args.matrix_path,
            deck_path=args.deck_path,
            source_notes_index_path=args.source_notes_index_path,
            source_notes_registry_path=args.source_notes_registry_path,
        )
    except FlashcardCoverageError as exc:
        raise SystemExit(f"flashcard coverage audit failed: {exc}") from exc

    output_json = _resolve_repo_path(args.output_json, repo_root)
    output_md = _resolve_repo_path(args.output_md, repo_root)
    if not args.dry_run:
        report, _ = write_json_stably(output_json, report)
        markdown = render_coverage_markdown(report)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(markdown, encoding="utf-8")

    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    print(
        "audited full matrix flashcard coverage "
        f"(rows={summary.get('row_count')}, units={summary.get('unit_count')}, "
        f"high_priority_missing_or_weak={summary.get('high_priority_missing_or_weak_count')})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
