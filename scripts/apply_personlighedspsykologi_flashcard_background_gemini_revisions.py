#!/usr/bin/env python3
"""Apply accepted Gemini revisions to the personality flashcard background overlay."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from notebooklm_queue.json_artifact_utils import write_json_stably
from notebooklm_queue.personlighedspsykologi_flashcard_backgrounds import (
    DEFAULT_FLASHCARD_BACKGROUNDS_JSON,
    DEFAULT_FLASHCARD_BACKGROUNDS_MD,
    FlashcardBackgroundError,
    _contains_term,
    _is_comparison_prompt,
    _mentioned_theory_group_count,
    render_flashcard_background_markdown,
    validate_flashcard_background_payload,
)
from notebooklm_queue.personlighedspsykologi_notebooklm_flashcard_lab import utc_now_iso

DEFAULT_REVIEW_JSON = Path("shows/personlighedspsykologi-en/flashcards/card_background_gemini_review.json")
DEFAULT_OUTPUT_JSON = DEFAULT_FLASHCARD_BACKGROUNDS_JSON
DEFAULT_OUTPUT_MD = DEFAULT_FLASHCARD_BACKGROUNDS_MD
STOPWORDS = {
    "eller",
    "fordi",
    "gennem",
    "hvor",
    "ikke",
    "med",
    "mod",
    "når",
    "og",
    "om",
    "over",
    "som",
    "til",
    "ved",
    "viser",
}


def _resolve(path: Path, repo_root: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FlashcardBackgroundError(f"Unable to load JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise FlashcardBackgroundError(f"JSON root must be an object: {path}")
    return payload


def _text(value: object) -> str:
    return str(value or "").strip()


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_str_list(value: object) -> list[str]:
    return [str(item).strip() for item in _as_list(value) if str(item).strip()]


def _terms_for_text(text: str, existing_terms: list[str], theory_names: list[str]) -> list[str]:
    terms: list[str] = []
    text_cf = text.casefold()
    for term in [*existing_terms, *theory_names]:
        clean = _text(term)
        if clean and clean.casefold() in text_cf:
            terms.append(clean)
    for word in re.findall(r"[A-Za-zÆØÅæøåéÉ-]{5,}", text):
        clean = word.strip("-")
        key = clean.casefold()
        if key in STOPWORDS:
            continue
        terms.append(clean)
        if len(terms) >= 8:
            break
    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        key = term.casefold()
        if key in seen:
            continue
        deduped.append(term)
        seen.add(key)
    return deduped[:8]


def _comparison_text_is_explicit(background: dict[str, Any], text: str) -> bool:
    theory_names = _as_str_list(background.get("theory_names"))
    if len(theory_names) < 2 or not _is_comparison_prompt(background):
        return True
    mentioned_theories = [name for name in theory_names if _contains_term(text, name)]
    return len(mentioned_theories) >= 2 or _mentioned_theory_group_count(text) >= 2


def _trim_sentence(value: str) -> str:
    return _text(value).rstrip(".;: ")


def _repair_comparison_background(background: dict[str, Any]) -> str:
    current_text = _text(background.get("background_text"))
    match = re.match(
        r"^(?P<first>.+?) forklarer personlighed gennem (?P<first_focus>.+?)\. "
        r"(?P<second>.+?) flytter tyngden til (?P<second_focus>.+?)\.",
        current_text,
    )
    if match:
        first = _trim_sentence(match.group("first"))
        first_focus = _trim_sentence(match.group("first_focus"))
        second = _trim_sentence(match.group("second"))
        second_focus = _trim_sentence(match.group("second_focus"))
        return (
            f"{first} lægger vægt på {first_focus}, mens {second} lægger vægt på {second_focus}. "
            f"{_trim_sentence(background.get('old_back_text'))}."
        )
    theory_names = _as_str_list(background.get("theory_names"))
    if len(theory_names) >= 2:
        return (
            f"{theory_names[0]} og {theory_names[1]} adskilles især ved forklaringsniveauet. "
            f"{_trim_sentence(background.get('old_back_text'))}."
        )
    raise FlashcardBackgroundError(f"Unable to repair comparison background: {_text(background.get('card_id'))}")


def apply_revisions(*, backgrounds: dict[str, Any], review: dict[str, Any], generated_at: str) -> dict[str, Any]:
    decisions_by_id = {
        _text(decision.get("card_id")): decision
        for decision in _as_list(review.get("decisions"))
        if isinstance(decision, dict) and _text(decision.get("card_id"))
    }
    revised_backgrounds: list[dict[str, Any]] = []
    decision_counts: Counter[str] = Counter()
    for background in _as_list(backgrounds.get("backgrounds")):
        if not isinstance(background, dict):
            continue
        card_id = _text(background.get("card_id"))
        decision = decisions_by_id.get(card_id)
        if not decision:
            revised_backgrounds.append(background)
            continue
        decision_value = _text(decision.get("decision"))
        decision_counts[decision_value] += 1
        if decision_value == "omit":
            continue
        updated = dict(background)
        if decision_value == "revise":
            suggested = _text(decision.get("suggested_background"))
            if not suggested:
                raise FlashcardBackgroundError(f"Missing suggested background for revised card: {card_id}")
            applied_source = "gemini_suggested_background"
            if not _comparison_text_is_explicit(background, suggested):
                suggested = _repair_comparison_background(background)
                applied_source = "deterministic_comparison_repair"
            updated["background_text"] = suggested
            updated["concept_terms"] = _terms_for_text(
                suggested,
                _as_str_list(background.get("concept_terms")),
                _as_str_list(background.get("theory_names")),
            )
            updated["gemini_revision"] = {
                "decision": decision_value,
                "reason": _text(decision.get("reason")),
                "scores": {
                    "accuracy": int(decision.get("accuracy_score") or 0),
                    "specificity": int(decision.get("specificity_score") or 0),
                    "usefulness": int(decision.get("usefulness_score") or 0),
                    "wording": int(decision.get("wording_score") or 0),
                },
                "applied_background_source": applied_source,
            }
        revised_backgrounds.append(updated)
    confidence_counts = Counter(_text(background.get("confidence")) for background in revised_backgrounds)
    payload = dict(backgrounds)
    payload["generated_at"] = generated_at
    payload["backgrounds"] = revised_backgrounds
    payload["stats"] = {
        **(payload.get("stats") if isinstance(payload.get("stats"), dict) else {}),
        "background_count": len(revised_backgrounds),
        "gemini_revision_decision_counts": dict(sorted(decision_counts.items())),
        "confidence_counts": dict(sorted(confidence_counts.items())),
    }
    payload["quality_policy"] = {
        **(payload.get("quality_policy") if isinstance(payload.get("quality_policy"), dict) else {}),
        "gemini_review_applied": True,
    }
    payload["gemini_review"] = {
        "artifact_type": review.get("artifact_type"),
        "generated_at": review.get("generated_at"),
        "model": review.get("model"),
        "decision_counts": (review.get("stats") or {}).get("decision_counts")
        if isinstance(review.get("stats"), dict)
        else None,
    }
    validate_flashcard_background_payload(payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--backgrounds-json", type=Path, default=DEFAULT_FLASHCARD_BACKGROUNDS_JSON)
    parser.add_argument("--review-json", type=Path, default=DEFAULT_REVIEW_JSON)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    backgrounds = _load_json(_resolve(args.backgrounds_json, repo_root))
    review = _load_json(_resolve(args.review_json, repo_root))
    revised = apply_revisions(backgrounds=backgrounds, review=review, generated_at=utc_now_iso())
    markdown = render_flashcard_background_markdown(revised)
    if not args.dry_run:
        write_json_stably(_resolve(args.output_json, repo_root), revised)
        _resolve(args.output_md, repo_root).write_text(markdown + "\n", encoding="utf-8")
    stats = revised.get("stats") if isinstance(revised.get("stats"), dict) else {}
    print(
        "applied Gemini background revisions "
        f"(backgrounds={stats.get('background_count')}, decisions={stats.get('gemini_revision_decision_counts')})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
