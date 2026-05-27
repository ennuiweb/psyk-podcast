#!/usr/bin/env python3
"""Review personality flashcard backgrounds with one Gemini rubric call."""

from __future__ import annotations

import argparse
import html
import json
import signal
import sys
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from types import FrameType
from typing import Any

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
from notebooklm_queue.personlighedspsykologi_flashcard_backgrounds import (
    DEFAULT_FLASHCARD_BACKGROUNDS_JSON,
)
from notebooklm_queue.personlighedspsykologi_notebooklm_flashcard_lab import (
    DEFAULT_GEMINI_FLASHCARD_REVIEW_MODEL,
    utc_now_iso,
)

DEFAULT_DECK_PATH = Path("shows/personlighedspsykologi-en/flashcards/notebooklm-fuld-matrix-personlighedspsykologi.json")
DEFAULT_SUBSTRATES_PATH = Path("shows/personlighedspsykologi-en/flashcards/card_background_substrates.json")
DEFAULT_OUTPUT_JSON = Path("shows/personlighedspsykologi-en/flashcards/card_background_gemini_review.json")
DEFAULT_OUTPUT_MD = Path("shows/personlighedspsykologi-en/flashcards/card_background_gemini_review.md")
DEFAULT_BUNDLE_JSON = Path("shows/personlighedspsykologi-en/flashcards/card_background_gemini_review_bundle.json")
DECISIONS = {"accept", "revise", "omit"}


class BackgroundGeminiReviewError(ValueError):
    """Raised when Gemini background review cannot be prepared or validated."""


class BackgroundGeminiReviewTimeout(TimeoutError):
    """Raised when Gemini background review exceeds its wall-clock budget."""


@contextmanager
def _wall_clock_timeout(seconds: int):
    if seconds <= 0:
        yield
        return

    def _handler(signum: int, frame: FrameType | None) -> None:
        raise BackgroundGeminiReviewTimeout(f"Gemini background review exceeded {seconds}s timeout")

    previous = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _resolve(path: Path, repo_root: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _repo_relative(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackgroundGeminiReviewError(f"Unable to load JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise BackgroundGeminiReviewError(f"JSON root must be an object: {path}")
    return payload


def _text(value: object) -> str:
    return str(value or "").strip()


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_str_list(value: object) -> list[str]:
    return [str(item).strip() for item in _as_list(value) if str(item).strip()]


def build_review_bundle(
    *,
    deck: dict[str, Any],
    backgrounds: dict[str, Any],
    substrates: dict[str, Any],
    model: str,
    max_cards: int | None,
) -> dict[str, Any]:
    cards_by_id = {
        _text(card.get("card_id")): card
        for card in _as_list(deck.get("cards"))
        if isinstance(card, dict) and _text(card.get("card_id"))
    }
    substrates_by_id = {
        _text(substrate.get("card_id")): substrate
        for substrate in _as_list(substrates.get("substrates"))
        if isinstance(substrate, dict) and _text(substrate.get("card_id"))
    }
    review_items: list[dict[str, Any]] = []
    for background in _as_list(backgrounds.get("backgrounds")):
        if not isinstance(background, dict):
            continue
        card_id = _text(background.get("card_id"))
        card = cards_by_id.get(card_id, {})
        substrate = substrates_by_id.get(card_id, {})
        review_items.append(
            {
                "card_id": card_id,
                "category_slug": _text(card.get("category_slug")),
                "question": _text(card.get("front_text")),
                "answer": _text(card.get("back_text")),
                "background": _text(background.get("background_text")),
                "theory_names": _as_str_list(background.get("theory_names")),
                "concept_terms": _as_str_list(background.get("concept_terms")),
                "field_support": substrate.get("field_support", []),
                "concept_distinctions": substrate.get("concept_distinctions", []),
            }
        )
        if max_cards is not None and len(review_items) >= max_cards:
            break
    if not review_items:
        raise BackgroundGeminiReviewError("No background review items found")
    return {
        "version": 1,
        "artifact_type": "personlighedspsykologi_flashcard_background_gemini_review_bundle",
        "subject_slug": "personlighedspsykologi",
        "generated_at": utc_now_iso(),
        "model": model,
        "rubric": {
            "decision_values": sorted(DECISIONS),
            "accept": "Accurate, answer-specific, concrete, and useful as learner-facing background.",
            "revise": "Useful direction but inaccurate, vague, awkward, too generic, or missing a key contrast.",
            "omit": "Adds little value, is misleading, mostly repeats the answer, or reads like card/exam meta-talk.",
            "criteria": [
                "Explains the conceptual reason behind the answer, not the purpose of the card.",
                "Uses concrete psychology concepts from the substrate.",
                "For comparisons, names both theories and gives the contrast/common axis.",
                "Does not expose internal provenance, source-note IDs, local files, or pipeline names.",
                "Danish wording is clear and not half-translated from English.",
            ],
        },
        "stats": {"review_item_count": len(review_items)},
        "items": review_items,
    }


def response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["artifact_type", "subject_slug", "summary", "decisions"],
        "properties": {
            "artifact_type": {"type": "string"},
            "subject_slug": {"type": "string"},
            "summary": {
                "type": "object",
                "additionalProperties": False,
                "required": ["overall_assessment", "main_risks"],
                "properties": {
                    "overall_assessment": {"type": "string"},
                    "main_risks": {"type": "array", "items": {"type": "string"}},
                },
            },
            "decisions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "card_id",
                        "decision",
                        "accuracy_score",
                        "specificity_score",
                        "usefulness_score",
                        "wording_score",
                        "reason",
                        "suggested_background",
                    ],
                    "properties": {
                        "card_id": {"type": "string"},
                        "decision": {"type": "string", "enum": sorted(DECISIONS)},
                        "accuracy_score": {"type": "integer"},
                        "specificity_score": {"type": "integer"},
                        "usefulness_score": {"type": "integer"},
                        "wording_score": {"type": "integer"},
                        "reason": {"type": "string"},
                        "suggested_background": {"type": "string"},
                    },
                },
            },
        },
    }


def system_instruction() -> str:
    return (
        "You are a senior Danish psychology teaching-material reviewer. "
        "Evaluate flashcard background texts for a personality psychology course. "
        "Be strict: generic exam coaching, card-meta language, vague restatement, "
        "half-translated English, or hidden provenance should be marked revise or omit. "
        "Do not reject merely because a background overlaps with another card."
    )


def user_prompt(bundle: dict[str, Any]) -> str:
    return (
        "Review every background item using the rubric. Return JSON matching the schema. "
        "Scores are 1-5 where 5 is excellent. Use `suggested_background` only for revise; "
        "otherwise return an empty string. Keep reasons concise.\n\n"
        + json.dumps(bundle, ensure_ascii=False)
    )


def validate_review(raw: object, *, bundle: dict[str, Any], model: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise BackgroundGeminiReviewError("Gemini review root must be an object")
    decisions = raw.get("decisions")
    if not isinstance(decisions, list):
        raise BackgroundGeminiReviewError("Gemini review decisions must be a list")
    expected_ids = {item["card_id"] for item in _as_list(bundle.get("items")) if isinstance(item, dict)}
    seen: set[str] = set()
    decision_counts: Counter[str] = Counter()
    for decision in decisions:
        if not isinstance(decision, dict):
            raise BackgroundGeminiReviewError("Gemini decision entries must be objects")
        card_id = _text(decision.get("card_id"))
        if card_id not in expected_ids:
            raise BackgroundGeminiReviewError(f"Unexpected Gemini review card_id: {card_id}")
        if card_id in seen:
            raise BackgroundGeminiReviewError(f"Duplicate Gemini review card_id: {card_id}")
        seen.add(card_id)
        value = _text(decision.get("decision"))
        if value not in DECISIONS:
            raise BackgroundGeminiReviewError(f"Invalid Gemini background decision for {card_id}: {value}")
        decision_counts[value] += 1
        for key in ("accuracy_score", "specificity_score", "usefulness_score", "wording_score"):
            score = int(decision.get(key) or 0)
            if score < 1 or score > 5:
                raise BackgroundGeminiReviewError(f"Invalid {key} for {card_id}: {score}")
            decision[key] = score
    missing = expected_ids - seen
    if missing:
        raise BackgroundGeminiReviewError(f"Gemini review missing {len(missing)} card(s)")
    review = {
        "version": 1,
        "artifact_type": "personlighedspsykologi_flashcard_background_gemini_review",
        "subject_slug": "personlighedspsykologi",
        "generated_at": utc_now_iso(),
        "model": model,
        "bundle_generated_at": bundle.get("generated_at"),
        "summary": raw.get("summary") if isinstance(raw.get("summary"), dict) else {},
        "stats": {
            "reviewed_count": len(decisions),
            "decision_counts": dict(sorted(decision_counts.items())),
        },
        "decisions": decisions,
    }
    return review


def render_markdown(review: dict[str, Any]) -> str:
    stats = review.get("stats") if isinstance(review.get("stats"), dict) else {}
    summary = review.get("summary") if isinstance(review.get("summary"), dict) else {}
    lines = [
        "# Flashcard Background Gemini Review",
        "",
        f"Generated: `{review.get('generated_at')}`",
        f"Model: `{review.get('model')}`",
        "",
        f"- Reviewed: {stats.get('reviewed_count')}",
        f"- Decisions: `{stats.get('decision_counts')}`",
        "",
        "## Summary",
        "",
        _text(summary.get("overall_assessment")),
        "",
    ]
    risks = _as_str_list(summary.get("main_risks"))
    if risks:
        lines.extend(["## Main Risks", ""])
        lines.extend(f"- {html.escape(risk)}" for risk in risks)
        lines.append("")
    lines.extend(["## Non-Accept Decisions", ""])
    for decision in _as_list(review.get("decisions")):
        if not isinstance(decision, dict) or decision.get("decision") == "accept":
            continue
        lines.extend(
            [
                f"### {html.escape(_text(decision.get('card_id')))}",
                "",
                f"Decision: `{html.escape(_text(decision.get('decision')))}`",
                "",
                f"Scores: accuracy={decision.get('accuracy_score')}, specificity={decision.get('specificity_score')}, usefulness={decision.get('usefulness_score')}, wording={decision.get('wording_score')}",
                "",
                f"Reason: {html.escape(_text(decision.get('reason')))}",
                "",
            ]
        )
        suggested = _text(decision.get("suggested_background"))
        if suggested:
            lines.extend([f"Suggested: {html.escape(suggested)}", ""])
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--deck-path", type=Path, default=DEFAULT_DECK_PATH)
    parser.add_argument("--backgrounds-json", type=Path, default=DEFAULT_FLASHCARD_BACKGROUNDS_JSON)
    parser.add_argument("--substrates-json", type=Path, default=DEFAULT_SUBSTRATES_PATH)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--bundle-json", type=Path, default=DEFAULT_BUNDLE_JSON)
    parser.add_argument("--model", default=DEFAULT_GEMINI_FLASHCARD_REVIEW_MODEL)
    parser.add_argument("--max-cards", type=int, default=None)
    parser.add_argument("--max-output-tokens", type=int, default=65536)
    parser.add_argument("--thinking-level", default="low")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--skip-preflight", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    deck = _load_json(_resolve(args.deck_path, repo_root))
    backgrounds = _load_json(_resolve(args.backgrounds_json, repo_root))
    substrates = _load_json(_resolve(args.substrates_json, repo_root))
    bundle = build_review_bundle(
        deck=deck,
        backgrounds=backgrounds,
        substrates=substrates,
        model=str(args.model),
        max_cards=args.max_cards,
    )
    bundle_path = _resolve(args.bundle_json, repo_root)
    write_json_stably(bundle_path, bundle)
    if args.dry_run:
        print(f"wrote Gemini background review bundle: {_repo_relative(bundle_path, repo_root)}")
        print("dry run: skipped Gemini call")
        return 0
    if not has_gemini_api_key():
        raise SystemExit("GEMINI_API_KEY or GOOGLE_API_KEY is not set")
    if args.preflight_only:
        preflight_gemini_json_generation(model=str(args.model))
        print(f"Gemini preflight ok for model {args.model}")
        return 0
    if not args.skip_preflight:
        preflight_gemini_json_generation(model=str(args.model))
    try:
        backend = make_gemini_backend(model=str(args.model))
        with _wall_clock_timeout(int(args.timeout_seconds)):
            raw_review = generate_json(
                backend=backend,
                system_instruction=system_instruction(),
                user_prompt=user_prompt(bundle),
                max_output_tokens=int(args.max_output_tokens),
                response_json_schema=response_schema(),
                thinking_level=str(args.thinking_level),
                retry_count=1,
            )
        review = validate_review(raw_review, bundle=bundle, model=str(args.model))
    except (GeminiPreprocessingError, BackgroundGeminiReviewError, BackgroundGeminiReviewTimeout) as exc:
        raise SystemExit(f"Gemini background review failed: {exc}") from exc
    review, changed = write_json_stably(_resolve(args.output_json, repo_root), review)
    _resolve(args.output_md, repo_root).write_text(render_markdown(review) + "\n", encoding="utf-8")
    print(
        f"wrote Gemini background review for {review['stats']['reviewed_count']} card(s) "
        f"to {_repo_relative(_resolve(args.output_json, repo_root), repo_root)}"
        f"{' (updated)' if changed else ' (unchanged)'}"
    )
    print(f"decision counts: {review['stats']['decision_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
