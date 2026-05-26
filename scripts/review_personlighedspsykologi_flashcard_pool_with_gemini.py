#!/usr/bin/env python3
"""Review the personlighedspsykologi flashcard pool shortlist with one Gemini call."""

from __future__ import annotations

import argparse
import json
import signal
import sys
from contextlib import contextmanager
from pathlib import Path
from types import FrameType

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from notebooklm_queue.gemini_preprocessing import (
    GeminiPreprocessingError,
    generate_json,
    has_gemini_api_key,
    make_gemini_backend,
    preflight_gemini_json_generation,
)
from notebooklm_queue.json_artifact_utils import write_json_stably
from notebooklm_queue.personlighedspsykologi_flashcard_review import (
    DEFAULT_REPORTS_ROOT,
    DEFAULT_REVIEW_RUN_ID,
    FlashcardReviewError,
    build_gemini_pool_review_bundle,
    gemini_pool_review_response_schema,
    gemini_pool_review_system_instruction,
    gemini_pool_review_user_prompt,
    validate_gemini_pool_review,
    write_gemini_pool_review_markdown,
)
from notebooklm_queue.personlighedspsykologi_notebooklm_flashcard_lab import (
    DEFAULT_GEMINI_FLASHCARD_REVIEW_MODEL,
)


class GeminiPoolReviewTimeout(TimeoutError):
    """Raised when the live Gemini pool review exceeds the wall-clock budget."""


@contextmanager
def _wall_clock_timeout(seconds: int):
    if seconds <= 0:
        yield
        return

    def _handler(signum: int, frame: FrameType | None) -> None:
        raise GeminiPoolReviewTimeout(f"Gemini pool review exceeded {seconds}s timeout")

    previous = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--review-run-id", default=DEFAULT_REVIEW_RUN_ID)
    parser.add_argument("--comparison-json", type=Path, default=None)
    parser.add_argument("--model", default=DEFAULT_GEMINI_FLASHCARD_REVIEW_MODEL)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--review-md", type=Path, default=None)
    parser.add_argument("--bundle-path", type=Path, default=None)
    parser.add_argument("--max-output-tokens", type=int, default=65536)
    parser.add_argument("--thinking-level", default="low")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--dry-run", action="store_true", help="Build/write the review bundle without calling Gemini.")
    parser.add_argument("--preflight-only", action="store_true", help="Only check Gemini JSON generation for the model.")
    parser.add_argument("--skip-preflight", action="store_true")
    return parser.parse_args()


def _resolve_repo_path(path: Path, repo_root: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _repo_relative(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise FlashcardReviewError(f"JSON root must be an object: {path}")
    return payload


def _default_paths(repo_root: Path, review_run_id: str) -> tuple[Path, Path, Path, Path]:
    report_root = _resolve_repo_path(DEFAULT_REPORTS_ROOT, repo_root) / review_run_id
    review_root = report_root / "gemini_review"
    return (
        report_root / "flashcard-pool-comparison.json",
        review_root / "flashcard-pool.gemini-review.json",
        review_root / "flashcard-pool.gemini-review.md",
        review_root / "flashcard-pool.gemini-review-bundle.json",
    )


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    default_comparison, default_output, default_md, default_bundle = _default_paths(repo_root, str(args.review_run_id))
    comparison_path = _resolve_repo_path(args.comparison_json, repo_root) if args.comparison_json else default_comparison
    output_path = _resolve_repo_path(args.output_path, repo_root) if args.output_path else default_output
    review_md = _resolve_repo_path(args.review_md, repo_root) if args.review_md else default_md
    bundle_path = _resolve_repo_path(args.bundle_path, repo_root) if args.bundle_path else default_bundle

    try:
        comparison = _read_json(comparison_path)
        bundle = build_gemini_pool_review_bundle(
            comparison_report=comparison,
            model=str(args.model),
        )
    except (OSError, json.JSONDecodeError, FlashcardReviewError) as exc:
        raise SystemExit(f"Gemini pool review setup failed: {exc}") from exc

    write_json_stably(bundle_path, bundle)
    if args.dry_run:
        print(f"wrote Gemini pool review bundle: {_repo_relative(bundle_path, repo_root)}")
        print("dry run: skipped Gemini call")
        return 0

    if not has_gemini_api_key():
        raise SystemExit("GEMINI_API_KEY or GOOGLE_API_KEY is not set")
    if args.preflight_only:
        try:
            preflight_gemini_json_generation(model=str(args.model))
        except GeminiPreprocessingError as exc:
            raise SystemExit(str(exc)) from exc
        print(f"Gemini preflight ok for model {args.model}")
        return 0
    if not args.skip_preflight:
        try:
            preflight_gemini_json_generation(model=str(args.model))
        except GeminiPreprocessingError as exc:
            raise SystemExit(str(exc)) from exc

    try:
        backend = make_gemini_backend(model=str(args.model))
        with _wall_clock_timeout(int(args.timeout_seconds)):
            raw_review = generate_json(
                backend=backend,
                system_instruction=gemini_pool_review_system_instruction(),
                user_prompt=gemini_pool_review_user_prompt(bundle),
                max_output_tokens=int(args.max_output_tokens),
                response_json_schema=gemini_pool_review_response_schema(),
                thinking_level=str(args.thinking_level),
                retry_count=1,
            )
        review = validate_gemini_pool_review(raw_review, bundle=bundle, model=str(args.model))
    except (GeminiPreprocessingError, FlashcardReviewError, GeminiPoolReviewTimeout) as exc:
        raise SystemExit(f"Gemini pool review failed: {exc}") from exc

    review, changed = write_json_stably(output_path, review)
    write_gemini_pool_review_markdown(review, review_md)
    stats = review.get("stats", {}) if isinstance(review, dict) else {}
    print(
        f"wrote Gemini pool review for {stats.get('candidate_count', 0)} shortlisted card(s) "
        f"to {_repo_relative(output_path, repo_root)}{' (updated)' if changed else ' (unchanged)'}"
    )
    print(f"review markdown: {_repo_relative(review_md, repo_root)}")
    print(f"bundle: {_repo_relative(bundle_path, repo_root)}")
    print(f"decision counts: {stats.get('decision_counts')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
