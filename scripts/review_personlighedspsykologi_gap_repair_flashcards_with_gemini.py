#!/usr/bin/env python3
"""Review targeted gap-repair NotebookLM flashcards with one Gemini JSON call."""

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
from notebooklm_queue.personlighedspsykologi_gap_repair_review import (
    DEFAULT_GAP_REPAIR_CANDIDATES_DIR,
    DEFAULT_GAP_REPAIR_REVIEW_JSON,
    DEFAULT_GAP_REPAIR_REVIEW_MD,
    DEFAULT_PLAN_JSON,
    GapRepairReviewError,
    build_gap_repair_promotion_decisions,
    build_gap_repair_review_bundle,
    gap_repair_review_response_schema,
    gap_repair_review_system_instruction,
    gap_repair_review_user_prompt,
    load_gap_repair_candidate_payloads,
    validate_gap_repair_review,
    write_gap_repair_review_markdown,
)
from notebooklm_queue.personlighedspsykologi_notebooklm_flashcard_lab import (
    DEFAULT_DECK_PATH,
    DEFAULT_GEMINI_FLASHCARD_REVIEW_MODEL,
    DEFAULT_MATRIX_PATH,
    FlashcardLabError,
    load_current_deck,
    load_matrix,
)


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
        raise GapRepairReviewError(f"JSON root must be an object: {path}")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--candidates-dir", type=Path, default=DEFAULT_GAP_REPAIR_CANDIDATES_DIR)
    parser.add_argument("--plan-json", type=Path, default=DEFAULT_PLAN_JSON)
    parser.add_argument("--matrix-path", type=Path, default=DEFAULT_MATRIX_PATH)
    parser.add_argument("--deck-path", type=Path, default=DEFAULT_DECK_PATH)
    parser.add_argument("--model", default=DEFAULT_GEMINI_FLASHCARD_REVIEW_MODEL)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_GAP_REPAIR_REVIEW_JSON)
    parser.add_argument("--review-md", type=Path, default=DEFAULT_GAP_REPAIR_REVIEW_MD)
    parser.add_argument(
        "--bundle-path",
        type=Path,
        default=DEFAULT_GAP_REPAIR_CANDIDATES_DIR.parent / "gemini_review" / "gap-repair-review-bundle.json",
    )
    parser.add_argument(
        "--raw-review-path",
        type=Path,
        default=DEFAULT_GAP_REPAIR_CANDIDATES_DIR.parent / "gemini_review" / "gap-repair-raw-review.json",
    )
    parser.add_argument("--max-output-tokens", type=int, default=32768)
    parser.add_argument("--thinking-level", default="low")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--dry-run", action="store_true", help="Build/write the review bundle without calling Gemini.")
    parser.add_argument("--preflight-only", action="store_true", help="Only check Gemini JSON generation for the model.")
    parser.add_argument("--skip-preflight", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    candidates_dir = _resolve_repo_path(args.candidates_dir, repo_root)
    plan_json = _resolve_repo_path(args.plan_json, repo_root)
    output_path = _resolve_repo_path(args.output_path, repo_root)
    review_md = _resolve_repo_path(args.review_md, repo_root)
    bundle_path = _resolve_repo_path(args.bundle_path, repo_root)
    raw_review_path = _resolve_repo_path(args.raw_review_path, repo_root)
    try:
        candidate_payloads = load_gap_repair_candidate_payloads(candidates_dir)
        plan = _read_json(plan_json)
        matrix = load_matrix(_resolve_repo_path(args.matrix_path, repo_root))
        current_deck = load_current_deck(_resolve_repo_path(args.deck_path, repo_root), matrix)
        bundle = build_gap_repair_review_bundle(
            candidate_payloads=candidate_payloads,
            plan=plan,
            matrix=matrix,
            current_deck=current_deck,
            model=str(args.model),
        )
    except (GapRepairReviewError, FlashcardLabError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Gap-repair review setup failed: {exc}") from exc

    write_json_stably(bundle_path, bundle)
    if args.dry_run:
        print(f"wrote gap-repair review bundle: {bundle_path}")
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
                system_instruction=gap_repair_review_system_instruction(),
                user_prompt=gap_repair_review_user_prompt(bundle),
                max_output_tokens=int(args.max_output_tokens),
                response_json_schema=gap_repair_review_response_schema(),
                thinking_level=str(args.thinking_level),
                retry_count=1,
            )
        raw_review_path.parent.mkdir(parents=True, exist_ok=True)
        write_json_stably(raw_review_path, raw_review)
        review = validate_gap_repair_review(raw_review, bundle=bundle, model=str(args.model))
        decisions = build_gap_repair_promotion_decisions(
            candidate_payloads=candidate_payloads,
            review_payload=review,
            bundle=bundle,
        )
    except (GeminiPreprocessingError, GapRepairReviewError, GeminiReviewTimeout) as exc:
        raise SystemExit(f"Gemini gap-repair review failed: {exc}") from exc

    decisions, changed = write_json_stably(output_path, decisions)
    write_gap_repair_review_markdown(decisions, review_md)
    stats = decisions.get("stats", {}) if isinstance(decisions, dict) else {}
    print(
        f"wrote gap-repair review decisions for {stats.get('decision_count', 0)} candidate(s) "
        f"to {output_path}{' (updated)' if changed else ' (unchanged)'}"
    )
    print(f"review markdown: {review_md}")
    print(f"bundle: {bundle_path}")
    print(f"raw review: {raw_review_path}")
    print(f"decision counts: {stats.get('gemini_decision_counts')}")
    print(f"promoted: {stats.get('promoted_count')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
