#!/usr/bin/env python3
"""Compare personlighedspsykologi flashcard pools for review."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from notebooklm_queue.personlighedspsykologi_flashcard_review import (
    DEFAULT_INDEPENDENT_DECK_PATH,
    DEFAULT_REVIEW_RUN_ID,
    DEFAULT_REPORTS_ROOT,
    DEFAULT_VARIANT_DECK_PATH,
    FULL_NOTEBOOKLM_RUN_ID,
    FlashcardReviewError,
    build_comparison_report,
    write_comparison_report,
)
from notebooklm_queue.personlighedspsykologi_notebooklm_flashcard_lab import (
    DEFAULT_DECK_PATH,
    DEFAULT_LAB_ROOT,
    DEFAULT_MATRIX_PATH,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--review-run-id", default=DEFAULT_REVIEW_RUN_ID)
    parser.add_argument("--full-run-id", default=FULL_NOTEBOOKLM_RUN_ID)
    parser.add_argument("--matrix-path", type=Path, default=DEFAULT_MATRIX_PATH)
    parser.add_argument("--matrix-deck-path", type=Path, default=DEFAULT_DECK_PATH)
    parser.add_argument("--variant-deck-path", type=Path, default=DEFAULT_VARIANT_DECK_PATH)
    parser.add_argument("--independent-deck-path", type=Path, default=DEFAULT_INDEPENDENT_DECK_PATH)
    parser.add_argument("--lab-root", type=Path, default=DEFAULT_LAB_ROOT)
    parser.add_argument("--reports-root", type=Path, default=DEFAULT_REPORTS_ROOT)
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--output-md", type=Path, default=None)
    parser.add_argument("--allow-count-drift", action="store_true")
    parser.add_argument("--allow-unignored-report-output", action="store_true")
    return parser.parse_args()


def _resolve_repo_path(path: Path, repo_root: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _repo_relative(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    reports_root = _resolve_repo_path(args.reports_root, repo_root)
    output_json = (
        _resolve_repo_path(args.output_json, repo_root)
        if args.output_json
        else reports_root / args.review_run_id / "flashcard-pool-comparison.json"
    )
    output_md = (
        _resolve_repo_path(args.output_md, repo_root)
        if args.output_md
        else reports_root / args.review_run_id / "flashcard-pool-comparison.md"
    )

    try:
        report = build_comparison_report(
            repo_root=repo_root,
            review_run_id=args.review_run_id,
            matrix_path=_resolve_repo_path(args.matrix_path, repo_root),
            matrix_deck_path=_resolve_repo_path(args.matrix_deck_path, repo_root),
            variant_deck_path=_resolve_repo_path(args.variant_deck_path, repo_root),
            independent_deck_path=_resolve_repo_path(args.independent_deck_path, repo_root),
            lab_root=_resolve_repo_path(args.lab_root, repo_root),
            full_run_id=args.full_run_id,
            reports_root=reports_root,
            allow_count_drift=args.allow_count_drift,
            allow_unignored_report_output=args.allow_unignored_report_output,
        )
        write_comparison_report(report, output_json=output_json, output_markdown=output_md)
    except FlashcardReviewError as exc:
        raise SystemExit(f"flashcard pool comparison failed: {exc}") from exc

    stats = report.get("stats", {}) if isinstance(report, dict) else {}
    stop_gates = report.get("stop_gates", {}) if isinstance(report, dict) else {}
    print(f"wrote flashcard pool comparison JSON: {_repo_relative(output_json, repo_root)}")
    print(f"wrote flashcard pool comparison Markdown: {_repo_relative(output_md, repo_root)}")
    print(f"cards: {stats.get('card_count', 0)}")
    print(f"shortlist: {len(report.get('shortlist', [])) if isinstance(report, dict) else 0}")
    print(f"unknown_rate: {stop_gates.get('unknown_rate')}")
    print(f"gemini_blocked: {stop_gates.get('unknown_rate_blocks_gemini')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
