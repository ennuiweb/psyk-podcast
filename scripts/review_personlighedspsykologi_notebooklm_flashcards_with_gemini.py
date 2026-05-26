#!/usr/bin/env python3
"""Review NotebookLM flashcard candidates with one Gemini JSON call."""

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
from notebooklm_queue.personlighedspsykologi_notebooklm_flashcard_lab import (
    DEFAULT_DECK_PATH,
    DEFAULT_GEMINI_FLASHCARD_REVIEW_MODEL,
    DEFAULT_MATRIX_PATH,
    FlashcardLabError,
    build_gemini_flashcard_review_bundle,
    gemini_flashcard_review_response_schema,
    gemini_flashcard_review_system_instruction,
    gemini_flashcard_review_user_prompt,
    load_current_deck,
    load_matrix,
    validate_gemini_flashcard_review,
    write_gemini_flashcard_review_markdown,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--candidates-json", type=Path, required=True)
    parser.add_argument("--matrix-path", type=Path, default=DEFAULT_MATRIX_PATH)
    parser.add_argument("--deck-path", type=Path, default=DEFAULT_DECK_PATH)
    parser.add_argument("--model", default=DEFAULT_GEMINI_FLASHCARD_REVIEW_MODEL)
    parser.add_argument("--output-path", type=Path, default=None)
    parser.add_argument("--review-md", type=Path, default=None)
    parser.add_argument("--bundle-path", type=Path, default=None)
    parser.add_argument("--max-output-tokens", type=int, default=32768)
    parser.add_argument(
        "--thinking-level",
        default="low",
        help="Gemini thinking level for review generation. Existing preprocessing pipelines still default to high.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=600,
        help="Wall-clock timeout for the live Gemini review call.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Build/write the review bundle without calling Gemini.")
    parser.add_argument("--preflight-only", action="store_true", help="Only check Gemini JSON generation for the model.")
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip the small Gemini JSON preflight before the live review call.",
    )
    return parser.parse_args()


class GeminiReviewTimeout(TimeoutError):
    """Raised when the Gemini review call exceeds the local wall-clock budget."""


@contextmanager
def _wall_clock_timeout(seconds: int):
    if seconds <= 0:
        yield
        return

    def _handler(signum: int, frame: FrameType | None) -> None:
        raise GeminiReviewTimeout(f"Gemini review exceeded {seconds}s timeout")

    previous = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _resolve_repo_path(path: Path, repo_root: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise FlashcardLabError(f"JSON root must be an object: {path}")
    return payload


def _default_output_paths(candidates_path: Path) -> tuple[Path, Path, Path]:
    run_root = candidates_path.parent.parent if candidates_path.parent.name == "candidates" else candidates_path.parent
    review_root = run_root / "gemini_review"
    stem = candidates_path.name.replace(".candidates.json", "")
    return (
        review_root / f"{stem}.gemini-review.json",
        review_root / f"{stem}.gemini-review.md",
        review_root / f"{stem}.gemini-review-bundle.json",
    )


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    candidates_path = _resolve_repo_path(args.candidates_json, repo_root)
    default_output_path, default_review_md, default_bundle_path = _default_output_paths(candidates_path)
    output_path = _resolve_repo_path(args.output_path, repo_root) if args.output_path else default_output_path
    review_md = _resolve_repo_path(args.review_md, repo_root) if args.review_md else default_review_md
    bundle_path = _resolve_repo_path(args.bundle_path, repo_root) if args.bundle_path else default_bundle_path

    try:
        candidates = _read_json(candidates_path)
        matrix = load_matrix(_resolve_repo_path(args.matrix_path, repo_root))
        deck = load_current_deck(_resolve_repo_path(args.deck_path, repo_root), matrix)
        bundle = build_gemini_flashcard_review_bundle(
            candidates_payload=candidates,
            matrix=matrix,
            current_deck=deck,
            model=str(args.model),
        )
    except (FlashcardLabError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Gemini flashcard review setup failed: {exc}") from exc

    write_json_stably(bundle_path, bundle)
    if args.dry_run:
        print(f"wrote Gemini review bundle: {bundle_path}")
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
                system_instruction=gemini_flashcard_review_system_instruction(),
                user_prompt=gemini_flashcard_review_user_prompt(bundle),
                max_output_tokens=int(args.max_output_tokens),
                response_json_schema=gemini_flashcard_review_response_schema(),
                thinking_level=str(args.thinking_level),
                retry_count=1,
            )
        review = validate_gemini_flashcard_review(raw_review, bundle=bundle, model=str(args.model))
    except (GeminiPreprocessingError, FlashcardLabError, GeminiReviewTimeout) as exc:
        raise SystemExit(f"Gemini flashcard review failed: {exc}") from exc

    review, changed = write_json_stably(output_path, review)
    write_gemini_flashcard_review_markdown(review, review_md)
    stats = review.get("stats", {}) if isinstance(review, dict) else {}
    print(
        f"wrote Gemini review for {stats.get('candidate_count', 0)} candidate(s) "
        f"to {output_path}{' (updated)' if changed else ' (unchanged)'}"
    )
    print(f"review markdown: {review_md}")
    print(f"bundle: {bundle_path}")
    print(f"decision counts: {stats.get('decision_counts')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
