#!/usr/bin/env python3
"""Compare personlighedspsykologi flashcard pools for independent quality with one Gemini call."""

from __future__ import annotations

import argparse
import json
import signal
import sys
from collections import Counter, defaultdict
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
    GEMINI_QUALITY_COMPARISON_ARTIFACT_TYPE,
    GEMINI_QUALITY_COMPARISON_PROMPT_VERSION,
    REVIEW_VERSION,
    build_gemini_quality_comparison_bundle,
    gemini_quality_comparison_response_schema,
    gemini_quality_comparison_system_instruction,
    gemini_quality_comparison_user_prompt,
    gemini_quality_observation_response_schema,
    gemini_quality_observation_system_instruction,
    gemini_quality_observation_user_prompt,
    validate_gemini_quality_comparison,
    validate_gemini_quality_observations,
    write_gemini_quality_comparison_markdown,
)
from notebooklm_queue.personlighedspsykologi_notebooklm_flashcard_lab import (
    DEFAULT_GEMINI_FLASHCARD_REVIEW_MODEL,
)


class GeminiQualityComparisonTimeout(TimeoutError):
    """Raised when the live Gemini quality comparison exceeds the wall-clock budget."""


@contextmanager
def _wall_clock_timeout(seconds: int):
    if seconds <= 0:
        yield
        return

    def _handler(signum: int, frame: FrameType | None) -> None:
        raise GeminiQualityComparisonTimeout(f"Gemini quality comparison exceeded {seconds}s timeout")

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
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument(
        "--batch-size",
        type=int,
        default=0,
        help="Review sampled cards in batches and aggregate observations. 0 means one call.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Build/write the comparison bundle without calling Gemini.")
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
    review_root = report_root / "quality_comparison"
    return (
        report_root / "flashcard-pool-comparison.json",
        review_root / "flashcard-quality-comparison.gemini-review.json",
        review_root / "flashcard-quality-comparison.gemini-review.md",
        review_root / "flashcard-quality-comparison.gemini-review-bundle.json",
    )


def _chunks(items: list[object], size: int) -> list[list[object]]:
    return [items[index : index + size] for index in range(0, len(items), size)]


def _average_scores(assessments: list[dict[str, object]]) -> dict[str, int]:
    score_values: dict[str, list[int]] = defaultdict(list)
    for assessment in assessments:
        scores = assessment.get("scores") if isinstance(assessment.get("scores"), dict) else {}
        for key, value in scores.items():
            try:
                score_values[str(key)].append(int(value))
            except (TypeError, ValueError):
                continue
    return {key: round(sum(values) / len(values)) for key, values in sorted(score_values.items()) if values}


def _merge_text_lists(assessments: list[dict[str, object]], field: str, *, limit: int = 10) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for assessment in assessments:
        values = assessment.get(field) if isinstance(assessment.get(field), list) else []
        for value in values:
            text = str(value or "").strip()
            if text and text not in seen:
                merged.append(text)
                seen.add(text)
            if len(merged) >= limit:
                return merged
    return merged


def _aggregate_batch_reviews(
    *,
    full_bundle: dict[str, object],
    batch_reviews: list[dict[str, object]],
    model: str,
) -> dict[str, object]:
    expected_keys = {
        str(card.get("card_key") or "").strip()
        for card in full_bundle.get("sample_cards", [])
        if isinstance(card, dict) and str(card.get("card_key") or "").strip()
    }
    observations = [
        observation
        for review in batch_reviews
        for observation in review.get("card_observations", [])
        if isinstance(observation, dict)
    ]
    observed_keys = {str(item.get("card_key") or "").strip() for item in observations if str(item.get("card_key") or "").strip()}
    verdict_counts = Counter(str(item.get("quality_verdict") or "").strip() for item in observations)
    verdict_counts.pop("", None)
    cards_by_key = {
        str(card.get("card_key") or "").strip(): card
        for card in full_bundle.get("sample_cards", [])
        if isinstance(card, dict) and str(card.get("card_key") or "").strip()
    }
    pool_names = sorted({str(card.get("source_pool") or "").strip() for card in cards_by_key.values()})
    pool_assessments: list[dict[str, object]] = []
    for pool in pool_names:
        pool_observations = [
            observation
            for observation in observations
            if cards_by_key.get(str(observation.get("card_key") or "").strip(), {}).get("source_pool") == pool
        ]
        score_values: dict[str, list[int]] = defaultdict(list)
        for observation in pool_observations:
            scores = observation.get("scores") if isinstance(observation.get("scores"), dict) else {}
            for key, value in scores.items():
                try:
                    score_values[str(key)].append(int(value))
                except (TypeError, ValueError):
                    continue
        scores = {key: round(sum(values) / len(values), 2) for key, values in sorted(score_values.items()) if values}
        learning_value = float(scores.get("learning_value") or 0)
        exam_value = float(scores.get("exam_usefulness") or 0)
        visibility = "main_deck" if pool == "canonical_matrix_deck" and learning_value >= 4 else "supplement"
        if pool == "full_notebooklm_candidate" and learning_value < 3.5:
            visibility = "raw_material"
        pool_assessments.append(
            {
                "source_pool": pool,
                "scores": scores,
                "recommended_visibility": visibility,
                "strengths": [
                    f"Observed {len(pool_observations)} cards.",
                    f"Average learning value {learning_value:.2f}.",
                ],
                "weaknesses": [
                    f"Average exam usefulness {exam_value:.2f}.",
                ],
                "best_use_case": (
                    "Primary structured exam rehearsal."
                    if pool == "canonical_matrix_deck"
                    else "Supplementary matrix rehearsal and wording variation."
                ),
            }
        )
    missing = sorted(expected_keys - observed_keys)
    by_pool = {assessment["source_pool"]: assessment for assessment in pool_assessments}
    best_overall = max(pool_assessments, key=lambda item: float(item.get("scores", {}).get("learning_value") or 0), default={})
    best_exam = max(pool_assessments, key=lambda item: float(item.get("scores", {}).get("exam_usefulness") or 0), default={})
    canonical = by_pool.get("canonical_matrix_deck", {})
    full = by_pool.get("full_notebooklm_candidate", {})
    return {
        "version": REVIEW_VERSION,
        "artifact_type": GEMINI_QUALITY_COMPARISON_ARTIFACT_TYPE,
        "subject_slug": full_bundle.get("subject_slug"),
        "review_run_id": full_bundle.get("review_run_id"),
        "generated_at": batch_reviews[-1].get("generated_at") if batch_reviews else None,
        "model": model,
        "prompt_version": GEMINI_QUALITY_COMPARISON_PROMPT_VERSION,
        "input_fingerprints": full_bundle.get("input_fingerprints"),
        "batching": {
            "batch_count": len(batch_reviews),
            "batch_source": "quality_comparison_batches",
        },
        "stats": {
            "sample_card_count": len(expected_keys),
            "observed_sample_card_count": len(observed_keys),
            "missing_sample_card_count": len(missing),
            "pool_count": len(pool_assessments),
            "quality_verdict_counts": dict(sorted(verdict_counts.items())),
        },
        "validation_warnings": (
            ["partial_card_observations_due_to_model_output_limit"] if missing else []
        ),
        "missing_card_keys": missing,
        "review_summary": {
            "overall_assessment": (
                "Batch aggregate over original matrix cards and newest NotebookLM candidates. "
                "Scores are averaged from per-card observations."
            ),
            "best_overall_pool": best_overall.get("source_pool", ""),
            "best_for_matrix_rehearsal": best_overall.get("source_pool", ""),
            "best_for_exam_preparation": best_exam.get("source_pool", ""),
            "main_risks": [
                "Batch aggregation is score-based and less rhetorically nuanced than one long narrative review.",
            ],
            "recommended_next_action": "Use the averaged pool scores and per-card observations for the deck decision.",
        },
        "pool_assessments": pool_assessments,
        "card_observations": observations,
        "comparison_conclusion": {
            "original_cards_assessment": f"Average scores: {canonical.get('scores', {})}",
            "newest_notebooklm_assessment": f"Average scores: {full.get('scores', {})}",
            "variant_decks_assessment": "Not in scope for this comparison.",
            "freudd_visibility_recommendation": (
                "Keep the original matrix deck as main deck; use newest NotebookLM candidates only if their averaged scores justify a supplement."
            ),
        },
    }


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
        bundle = build_gemini_quality_comparison_bundle(
            comparison_report=comparison,
            model=str(args.model),
        )
    except (OSError, json.JSONDecodeError, FlashcardReviewError) as exc:
        raise SystemExit(f"Gemini quality comparison setup failed: {exc}") from exc

    write_json_stably(bundle_path, bundle)
    if args.dry_run:
        print(f"wrote Gemini quality comparison bundle: {_repo_relative(bundle_path, repo_root)}")
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
        if int(args.batch_size) > 0:
            sample_cards = [item for item in bundle.get("sample_cards", []) if isinstance(item, dict)]
            batch_reviews: list[dict[str, object]] = []
            batch_root = output_path.parent / "batches"
            for batch_index, chunk in enumerate(_chunks(sample_cards, int(args.batch_size)), start=1):
                batch_bundle = dict(bundle)
                batch_bundle["sample_cards"] = chunk
                batch_bundle["batch"] = {
                    "batch_index": batch_index,
                    "batch_count": (len(sample_cards) + int(args.batch_size) - 1) // int(args.batch_size),
                    "sample_card_count": len(chunk),
                }
                batch_bundle_path = batch_root / f"batch-{batch_index:03d}.bundle.json"
                batch_output_path = batch_root / f"batch-{batch_index:03d}.review.json"
                batch_md_path = batch_root / f"batch-{batch_index:03d}.review.md"
                write_json_stably(batch_bundle_path, batch_bundle)
                with _wall_clock_timeout(int(args.timeout_seconds)):
                    raw_review = generate_json(
                        backend=backend,
                        system_instruction=gemini_quality_observation_system_instruction(),
                        user_prompt=gemini_quality_observation_user_prompt(batch_bundle),
                        max_output_tokens=int(args.max_output_tokens),
                        response_json_schema=gemini_quality_observation_response_schema(),
                        thinking_level=str(args.thinking_level),
                        retry_count=1,
                    )
                batch_review = validate_gemini_quality_observations(raw_review, bundle=batch_bundle)
                batch_review.update(
                    {
                        "version": REVIEW_VERSION,
                        "artifact_type": "personlighedspsykologi_gemini_flashcard_quality_observation_batch",
                        "subject_slug": bundle.get("subject_slug"),
                        "review_run_id": bundle.get("review_run_id"),
                        "generated_at": None,
                        "model": str(args.model),
                        "prompt_version": "personlighedspsykologi-gemini-flashcard-quality-observation-v1",
                    }
                )
                write_json_stably(batch_output_path, batch_review)
                write_gemini_quality_comparison_markdown(batch_review, batch_md_path)
                print(
                    f"batch {batch_index}: observed "
                    f"{batch_review.get('stats', {}).get('observed_sample_card_count')} / "
                    f"{batch_review.get('stats', {}).get('sample_card_count')}"
                )
                batch_reviews.append(batch_review)
            review = _aggregate_batch_reviews(full_bundle=bundle, batch_reviews=batch_reviews, model=str(args.model))
        else:
            with _wall_clock_timeout(int(args.timeout_seconds)):
                raw_review = generate_json(
                    backend=backend,
                    system_instruction=gemini_quality_comparison_system_instruction(),
                    user_prompt=gemini_quality_comparison_user_prompt(bundle),
                    max_output_tokens=int(args.max_output_tokens),
                    response_json_schema=gemini_quality_comparison_response_schema(),
                    thinking_level=str(args.thinking_level),
                    retry_count=1,
                )
            review = validate_gemini_quality_comparison(raw_review, bundle=bundle, model=str(args.model))
    except (GeminiPreprocessingError, FlashcardReviewError, GeminiQualityComparisonTimeout) as exc:
        raise SystemExit(f"Gemini quality comparison failed: {exc}") from exc

    review, changed = write_json_stably(output_path, review)
    write_gemini_quality_comparison_markdown(review, review_md)
    stats = review.get("stats", {}) if isinstance(review, dict) else {}
    print(
        f"wrote Gemini quality comparison for {stats.get('sample_card_count', 0)} sampled card(s) "
        f"to {_repo_relative(output_path, repo_root)}{' (updated)' if changed else ' (unchanged)'}"
    )
    print(f"review markdown: {_repo_relative(review_md, repo_root)}")
    print(f"bundle: {_repo_relative(bundle_path, repo_root)}")
    print(f"quality verdict counts: {stats.get('quality_verdict_counts')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
