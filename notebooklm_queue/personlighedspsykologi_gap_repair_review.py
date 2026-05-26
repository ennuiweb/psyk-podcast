"""Review and promote targeted NotebookLM gap-repair flashcards."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from notebooklm_queue.json_artifact_utils import render_json, semantic_fingerprint
from notebooklm_queue.personlighedspsykologi_matrix_flashcards import (
    CATEGORIES,
    LEARNER_TEXT_FORBIDDEN_PATTERNS,
    SUBJECT_SLUG,
)
from notebooklm_queue.personlighedspsykologi_notebooklm_flashcard_lab import (
    CONFIDENCE_VALUES,
    DECISION_VALUES,
    LAB_VERSION,
    MAX_BACK_CHARS,
    MAX_FRONT_CHARS,
    _as_list,
    _as_str_list,
    _normalize_card_text,
    _text,
    matrix_review_rows,
    utc_now_iso,
)
from notebooklm_queue.personlighedspsykologi_notebooklm_gap_repair import (
    DEFAULT_GAP_REPAIR_RUN_ID,
    DEFAULT_PLAN_JSON,
)

GAP_REPAIR_REVIEW_PROMPT_VERSION = "personlighedspsykologi-gap-repair-review-v1"
GAP_REPAIR_REVIEW_BUNDLE_ARTIFACT_TYPE = "personlighedspsykologi_gap_repair_flashcard_review_bundle"
GAP_REPAIR_REVIEW_ARTIFACT_TYPE = "personlighedspsykologi_gap_repair_flashcard_review"
GAP_REPAIR_PROMOTION_DECISIONS_ARTIFACT_TYPE = "personlighedspsykologi_gap_repair_promotion_decisions"
PROMOTABLE_DECISIONS = {"accept", "edit"}
DEFAULT_GAP_REPAIR_RUN_DIR = (
    Path("notebooklm-podcast-auto/personlighedspsykologi/flashcard_lab/runs")
    / DEFAULT_GAP_REPAIR_RUN_ID
)
DEFAULT_GAP_REPAIR_CANDIDATES_DIR = DEFAULT_GAP_REPAIR_RUN_DIR / "candidates"
DEFAULT_GAP_REPAIR_REVIEW_JSON = (
    Path("shows/personlighedspsykologi-en/flashcards/coverage/gap_repair_review_decisions.json")
)
DEFAULT_GAP_REPAIR_REVIEW_MD = (
    Path("shows/personlighedspsykologi-en/flashcards/coverage/gap_repair_review_decisions.md")
)


class GapRepairReviewError(ValueError):
    """Raised when gap-repair review artifacts cannot be built safely."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GapRepairReviewError(f"Unable to load JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise GapRepairReviewError(f"JSON root must be an object: {path}")
    return payload


def _repo_relative(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def _category_title(category_slug: str) -> str:
    for category in CATEGORIES:
        if category["slug"] == category_slug:
            return category["title"]
    raise GapRepairReviewError(f"Unknown category_slug: {category_slug}")


def _promotion_category_slug(candidate: dict[str, Any], target_gap: dict[str, Any] | None) -> str:
    field = _text((target_gap or {}).get("field"))
    field_categories = {
        "comparison_targets": "sammenligninger",
        "likely_misunderstandings": "eksamenstraps",
        "orientation_points": "orienteringspunkter",
        "method_evidence_style": "metode-og-evidens",
    }
    return field_categories.get(field) or _text(candidate.get("category_slug"))


def _assert_safe_text(*, item_id: str, fields: dict[str, str]) -> None:
    for field, text in fields.items():
        for pattern in LEARNER_TEXT_FORBIDDEN_PATTERNS:
            if pattern.search(text):
                raise GapRepairReviewError(f"Unsafe learner-facing text in {item_id}.{field}")


def _candidate_payload_paths(candidates_dir: Path) -> list[Path]:
    paths = sorted(candidates_dir.glob("*.candidates.json"))
    if not paths:
        raise GapRepairReviewError(f"No gap-repair candidate files found in {candidates_dir}")
    return paths


def load_gap_repair_candidate_payloads(candidates_dir: Path = DEFAULT_GAP_REPAIR_CANDIDATES_DIR) -> list[dict[str, Any]]:
    payloads = [_load_json(path) for path in _candidate_payload_paths(candidates_dir)]
    for payload in payloads:
        if payload.get("artifact_type") != "personlighedspsykologi_notebooklm_flashcard_candidates":
            raise GapRepairReviewError("Unexpected candidate artifact_type")
        if payload.get("subject_slug") != SUBJECT_SLUG:
            raise GapRepairReviewError(f"Candidate subject_slug must be {SUBJECT_SLUG}")
    return payloads


def _plan_gap_lookup(plan: dict[str, Any]) -> dict[tuple[str, int], dict[str, Any]]:
    lookup: dict[tuple[str, int], dict[str, Any]] = {}
    for notebook in _as_list(plan.get("notebooks")):
        if not isinstance(notebook, dict):
            continue
        slug = _text(notebook.get("slug"))
        for index, unit_id in enumerate(_as_str_list(notebook.get("gap_unit_ids")), start=1):
            lookup[(slug, index)] = {"unit_id": unit_id}
    return lookup


def _coverage_unit_lookup(matrix: dict[str, Any]) -> dict[str, dict[str, Any]]:
    from notebooklm_queue.personlighedspsykologi_flashcard_coverage import matrix_coverage_units

    lookup: dict[str, dict[str, Any]] = {}
    for row in _as_list(matrix.get("rows")):
        if not isinstance(row, dict):
            continue
        theory_id = _text(row.get("theory_id"))
        for unit in matrix_coverage_units(row):
            unit = dict(unit)
            unit["theory_id"] = theory_id
            lookup[_text(unit.get("unit_id"))] = unit
    return lookup


def _candidate_for_review(candidate: dict[str, Any], target_gap: dict[str, Any] | None) -> dict[str, Any]:
    manual_review = candidate.get("manual_card_review") if isinstance(candidate.get("manual_card_review"), dict) else {}
    nearest = manual_review.get("nearest_existing_card") if isinstance(manual_review.get("nearest_existing_card"), dict) else None
    target = {}
    if target_gap:
        target = {
            "unit_id": _text(target_gap.get("unit_id")),
            "field": _text(target_gap.get("field")),
            "label": _text(target_gap.get("label")),
            "expected_text": _text(target_gap.get("expected_text")),
            "priority": _text(target_gap.get("priority")),
            "target_theory_id": _text(target_gap.get("target_theory_id")),
            "theory_id": _text(target_gap.get("theory_id")),
        }
    return {
        "candidate_id": _text(candidate.get("candidate_id")),
        "notebook_slug": _text(candidate.get("notebook_slug")),
        "source_index": int(candidate.get("source_index") or 0),
        "front": _text(candidate.get("front")),
        "back": _text(candidate.get("back")),
        "category_slug": _text(candidate.get("category_slug")),
        "mapped_theory_ids": _as_str_list(candidate.get("mapped_theory_ids")),
        "warnings": _as_str_list(candidate.get("warnings")),
        "automatic_review_status": _text(candidate.get("review_status")),
        "local_suggested_decision": _text(manual_review.get("suggested_decision")),
        "local_review_rationale": _text(manual_review.get("rationale")),
        "duplicate_score": float(manual_review.get("duplicate_score") or 0.0),
        "nearest_existing_card": nearest,
        "shared_terms": _as_str_list(manual_review.get("shared_terms")),
        "target_gap": target,
    }


def build_gap_repair_review_bundle(
    *,
    candidate_payloads: list[dict[str, Any]],
    plan: dict[str, Any],
    matrix: dict[str, Any],
    current_deck: dict[str, Any],
    model: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    plan_lookup = _plan_gap_lookup(plan)
    units_by_id = _coverage_unit_lookup(matrix)
    review_candidates: list[dict[str, Any]] = []
    for payload in candidate_payloads:
        notebook_slug = _text(payload.get("notebook_slug"))
        for candidate in _as_list(payload.get("candidates")):
            if not isinstance(candidate, dict):
                continue
            if _text(candidate.get("review_status")) == "auto_rejected":
                continue
            source_index = int(candidate.get("source_index") or 0)
            plan_gap = plan_lookup.get((notebook_slug, source_index))
            target_gap = units_by_id.get(_text((plan_gap or {}).get("unit_id"))) if plan_gap else None
            review_candidates.append(_candidate_for_review(candidate, target_gap))
    if not review_candidates:
        raise GapRepairReviewError("No reviewable gap-repair candidates found")
    candidate_ids = [_text(candidate.get("candidate_id")) for candidate in review_candidates]
    if any(not candidate_id for candidate_id in candidate_ids) or len(set(candidate_ids)) != len(candidate_ids):
        raise GapRepairReviewError("Gap-repair candidate IDs must be non-empty and unique")
    theory_ids = {
        theory_id
        for candidate in review_candidates
        for theory_id in _as_str_list(candidate.get("mapped_theory_ids"))
        if theory_id != "comparative_theory_analysis"
    }
    return {
        "version": LAB_VERSION,
        "artifact_type": GAP_REPAIR_REVIEW_BUNDLE_ARTIFACT_TYPE,
        "subject_slug": SUBJECT_SLUG,
        "run_id": _text(plan.get("run_id")) or DEFAULT_GAP_REPAIR_RUN_ID,
        "generated_at": generated_at or utc_now_iso(),
        "model": model,
        "prompt_version": GAP_REPAIR_REVIEW_PROMPT_VERSION,
        "input_fingerprints": {
            "candidate_payloads": semantic_fingerprint(candidate_payloads),
            "gap_repair_plan": semantic_fingerprint(plan),
            "matrix": semantic_fingerprint(matrix),
            "current_deck": semantic_fingerprint(current_deck),
        },
        "review_contract": {
            "task": "Review targeted NotebookLM gap-repair flashcards for promotion into the live Freudd deck.",
            "decisions": sorted(DECISION_VALUES),
            "decision_rules": [
                "accept when the card safely covers the target_gap and is usable as an oral-exam flashcard",
                "edit when the card covers the target_gap but needs tighter wording, precision, or category cleanup",
                "merge_with_existing only when the candidate is best handled by changing an existing card instead of adding a new one",
                "reject when the card is unsafe, misleading, too vague, not grounded in the target_gap, or not useful for recall",
                "do not reject only because it overlaps the existing live deck; judge whether it repairs the intended coverage gap",
                "broad matrix restatements are allowed when the target_gap itself is broad",
                "never approve cards that mention student note owners, local paths, source-note IDs, coverage IDs, or internal provenance",
            ],
            "promotion_boundary": "This review is advisory until the deterministic promotion script rebuilds the Freudd deck.",
        },
        "current_deck": {
            "deck_slug": _text(current_deck.get("deck_slug")),
            "card_count": int(current_deck.get("card_count") or 0),
        },
        "matrix_rows": matrix_review_rows(matrix, theory_ids),
        "candidates": review_candidates,
    }


def gap_repair_review_system_instruction() -> str:
    return "\n".join(
        [
            "You are a strict Danish university psychology flashcard reviewer.",
            "Return only valid JSON matching the requested schema.",
            "Review targeted NotebookLM gap-repair cards against their supplied target_gap.",
            "The goal is coverage repair for Freudd, not novelty for its own sake.",
            "Do not reject merely because a card overlaps the existing deck; decide whether it repairs the intended matrix/source gap.",
            "Do not invent course claims beyond the supplied matrix rows, target gaps, and candidate text.",
            "Do not approve learner-facing text that leaks student note owners, local paths, source-note IDs, coverage IDs, or hidden provenance.",
        ]
    )


def gap_repair_review_user_prompt(bundle: dict[str, Any]) -> str:
    return "\n".join(
        [
            "Review every candidate in this JSON bundle.",
            "",
            "Return one decision per candidate_id.",
            "Use Danish for edited_front and edited_back.",
            "Keep edited_front and edited_back empty unless decision is edit.",
            "Reasons should be concise but should say whether the card repairs its target_gap.",
            "",
            "Important rubric correction: duplication/redundancy with the live deck is not by itself a rejection criterion.",
            "A card may be broad if the target_gap is broad. Reject only if it is unsafe, wrong, vague, unhelpful, or fails the target_gap.",
            "",
            "Input bundle:",
            "",
            render_json(bundle),
        ]
    )


def gap_repair_review_response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "review_summary": {
                "type": "object",
                "properties": {
                    "overall_assessment": {"type": "string"},
                    "candidate_count": {"type": "integer"},
                    "accept_count": {"type": "integer"},
                    "edit_count": {"type": "integer"},
                    "merge_with_existing_count": {"type": "integer"},
                    "reject_count": {"type": "integer"},
                    "main_risks": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "overall_assessment",
                    "candidate_count",
                    "accept_count",
                    "edit_count",
                    "merge_with_existing_count",
                    "reject_count",
                    "main_risks",
                ],
            },
            "decisions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "candidate_id": {"type": "string"},
                        "decision": {"type": "string", "enum": sorted(DECISION_VALUES)},
                        "confidence": {"type": "string", "enum": sorted(CONFIDENCE_VALUES)},
                        "reason": {"type": "string"},
                        "added_value": {"type": "string"},
                        "target_gap_assessment": {"type": "string"},
                        "nearest_existing_card_assessment": {"type": "string"},
                        "edited_front": {"type": "string"},
                        "edited_back": {"type": "string"},
                        "safety_flags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "candidate_id",
                        "decision",
                        "confidence",
                        "reason",
                        "added_value",
                        "target_gap_assessment",
                        "nearest_existing_card_assessment",
                        "edited_front",
                        "edited_back",
                        "safety_flags",
                    ],
                },
            },
        },
        "required": ["review_summary", "decisions"],
    }


def validate_gap_repair_review(
    review_payload: dict[str, Any],
    *,
    bundle: dict[str, Any],
    model: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    raw_decisions = review_payload.get("decisions")
    if not isinstance(raw_decisions, list):
        raise GapRepairReviewError("Gemini gap-repair review payload must contain decisions list")
    candidates_by_id = {
        _text(candidate.get("candidate_id")): candidate
        for candidate in _as_list(bundle.get("candidates"))
        if isinstance(candidate, dict)
    }
    if not candidates_by_id:
        raise GapRepairReviewError("Gap-repair review bundle has no candidates")
    decisions: list[dict[str, Any]] = []
    seen: set[str] = set()
    decision_counts: Counter[str] = Counter()
    for raw in raw_decisions:
        if not isinstance(raw, dict):
            raise GapRepairReviewError("Gap-repair review decisions must be objects")
        candidate_id = _text(raw.get("candidate_id"))
        candidate = candidates_by_id.get(candidate_id)
        if candidate is None:
            raise GapRepairReviewError(f"Gap-repair review returned unknown candidate_id: {candidate_id}")
        if candidate_id in seen:
            raise GapRepairReviewError(f"Gap-repair review returned duplicate candidate_id: {candidate_id}")
        seen.add(candidate_id)
        decision = _text(raw.get("decision"))
        confidence = _text(raw.get("confidence"))
        if decision not in DECISION_VALUES:
            raise GapRepairReviewError(f"Invalid gap-repair decision for {candidate_id}: {decision}")
        if confidence not in CONFIDENCE_VALUES:
            raise GapRepairReviewError(f"Invalid gap-repair confidence for {candidate_id}: {confidence}")
        edited_front = _normalize_card_text(raw.get("edited_front"))
        edited_back = _normalize_card_text(raw.get("edited_back"))
        if decision == "edit" and (not edited_front or not edited_back):
            raise GapRepairReviewError(f"Gap-repair edit decision must include edited text: {candidate_id}")
        if decision != "edit" and (edited_front or edited_back):
            raise GapRepairReviewError(f"Only edit decisions may include edited text: {candidate_id}")
        if len(edited_front) > MAX_FRONT_CHARS:
            raise GapRepairReviewError(f"Gap-repair edited front too long: {candidate_id}")
        if len(edited_back) > MAX_BACK_CHARS:
            raise GapRepairReviewError(f"Gap-repair edited back too long: {candidate_id}")
        safety_text = "\n".join([edited_front, edited_back, _text(raw.get("reason")), _text(raw.get("added_value"))])
        _assert_safe_text(item_id=candidate_id, fields={"review": safety_text})
        if decision == "accept" and _text(candidate.get("automatic_review_status")) == "auto_rejected":
            raise GapRepairReviewError(f"Cannot accept auto-rejected candidate: {candidate_id}")
        decision_counts[decision] += 1
        decisions.append(
            {
                "candidate_id": candidate_id,
                "decision": decision,
                "confidence": confidence,
                "reason": _text(raw.get("reason")),
                "added_value": _text(raw.get("added_value")),
                "target_gap_assessment": _text(raw.get("target_gap_assessment")),
                "nearest_existing_card_assessment": _text(raw.get("nearest_existing_card_assessment")),
                "edited_front": edited_front,
                "edited_back": edited_back,
                "safety_flags": _as_str_list(raw.get("safety_flags")),
                "local_suggested_decision": _text(candidate.get("local_suggested_decision")),
                "automatic_review_status": _text(candidate.get("automatic_review_status")),
                "notebook_slug": _text(candidate.get("notebook_slug")),
            }
        )
    missing = set(candidates_by_id) - seen
    if missing:
        raise GapRepairReviewError("Gap-repair review missing decisions: " + ", ".join(sorted(missing)[:10]))
    summary = review_payload.get("review_summary") if isinstance(review_payload.get("review_summary"), dict) else {}
    return {
        "version": LAB_VERSION,
        "artifact_type": GAP_REPAIR_REVIEW_ARTIFACT_TYPE,
        "subject_slug": SUBJECT_SLUG,
        "run_id": _text(bundle.get("run_id")),
        "generated_at": generated_at or utc_now_iso(),
        "model": model,
        "prompt_version": GAP_REPAIR_REVIEW_PROMPT_VERSION,
        "input_fingerprints": bundle.get("input_fingerprints"),
        "stats": {
            "candidate_count": len(candidates_by_id),
            "decision_counts": dict(sorted(decision_counts.items())),
        },
        "review_summary": {
            "overall_assessment": _text(summary.get("overall_assessment")),
            "main_risks": _as_str_list(summary.get("main_risks")),
        },
        "decisions": decisions,
    }


def build_gap_repair_promotion_decisions(
    *,
    candidate_payloads: list[dict[str, Any]],
    review_payload: dict[str, Any],
    bundle: dict[str, Any],
    generated_at: str | None = None,
) -> dict[str, Any]:
    candidates_by_id = {
        _text(candidate.get("candidate_id")): candidate
        for payload in candidate_payloads
        for candidate in _as_list(payload.get("candidates"))
        if isinstance(candidate, dict) and _text(candidate.get("candidate_id"))
    }
    target_by_id = {
        _text(candidate.get("candidate_id")): candidate.get("target_gap")
        for candidate in _as_list(bundle.get("candidates"))
        if isinstance(candidate, dict)
    }
    decisions: list[dict[str, Any]] = []
    for review_decision in _as_list(review_payload.get("decisions")):
        if not isinstance(review_decision, dict):
            continue
        candidate_id = _text(review_decision.get("candidate_id"))
        candidate = candidates_by_id.get(candidate_id)
        if candidate is None:
            raise GapRepairReviewError(f"Review references unknown candidate: {candidate_id}")
        decision = _text(review_decision.get("decision"))
        promote = decision in PROMOTABLE_DECISIONS
        target_gap = target_by_id.get(candidate_id) if isinstance(target_by_id.get(candidate_id), dict) else {}
        category_slug = _promotion_category_slug(candidate, target_gap)
        front = _text(review_decision.get("edited_front")) if decision == "edit" else _text(candidate.get("front"))
        back = _text(review_decision.get("edited_back")) if decision == "edit" else _text(candidate.get("back"))
        if promote:
            if not front or not back:
                raise GapRepairReviewError(f"Promoted gap-repair card missing text: {candidate_id}")
            _assert_safe_text(item_id=candidate_id, fields={"front": front, "back": back})
            _category_title(category_slug)
        mapped_theory_ids = set(_as_str_list(candidate.get("mapped_theory_ids")))
        for theory_id in (_text(target_gap.get("theory_id")), _text(target_gap.get("target_theory_id"))):
            if theory_id:
                mapped_theory_ids.add(theory_id)
        manual_review = candidate.get("manual_card_review") if isinstance(candidate.get("manual_card_review"), dict) else {}
        nearest = manual_review.get("nearest_existing_card") if isinstance(manual_review.get("nearest_existing_card"), dict) else {}
        decisions.append(
            {
                "candidate_id": candidate_id,
                "promote": promote,
                "gemini_decision": decision,
                "confidence": _text(review_decision.get("confidence")),
                "front_text": front if promote else "",
                "back_text": back if promote else "",
                "category_slug": category_slug,
                "mapped_theory_ids": sorted(mapped_theory_ids),
                "notebook_slug": _text(candidate.get("notebook_slug")),
                "source_index": int(candidate.get("source_index") or 0),
                "target_gap": target_gap,
                "reason": _text(review_decision.get("reason")),
                "added_value": _text(review_decision.get("added_value")),
                "target_gap_assessment": _text(review_decision.get("target_gap_assessment")),
                "nearest_existing_card_id": _text(nearest.get("card_id")),
                "nearest_existing_card_assessment": _text(review_decision.get("nearest_existing_card_assessment")),
                "automatic_review_status": _text(candidate.get("review_status")),
                "local_suggested_decision": _text(manual_review.get("suggested_decision")),
            }
        )
    payload = {
        "version": 1,
        "artifact_type": GAP_REPAIR_PROMOTION_DECISIONS_ARTIFACT_TYPE,
        "subject_slug": SUBJECT_SLUG,
        "run_id": _text(review_payload.get("run_id")) or DEFAULT_GAP_REPAIR_RUN_ID,
        "generated_at": generated_at or utc_now_iso(),
        "source_fingerprints": {
            "candidate_payloads": semantic_fingerprint(candidate_payloads),
            "review": semantic_fingerprint(review_payload),
            "bundle": semantic_fingerprint(bundle),
        },
        "stats": {
            "decision_count": len(decisions),
            "promoted_count": sum(1 for decision in decisions if decision["promote"]),
            "rejected_count": sum(1 for decision in decisions if not decision["promote"]),
            "gemini_decision_counts": dict(
                sorted(Counter(_text(decision.get("gemini_decision")) for decision in decisions).items())
            ),
        },
        "decisions": decisions,
    }
    validate_gap_repair_promotion_decisions(payload)
    return payload


def validate_gap_repair_promotion_decisions(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("version") != 1:
        raise GapRepairReviewError("Gap-repair promotion decisions version must be 1")
    if payload.get("artifact_type") != GAP_REPAIR_PROMOTION_DECISIONS_ARTIFACT_TYPE:
        raise GapRepairReviewError("Invalid gap-repair promotion decisions artifact_type")
    if payload.get("subject_slug") != SUBJECT_SLUG:
        raise GapRepairReviewError(f"Gap-repair promotion subject_slug must be {SUBJECT_SLUG}")
    decisions = payload.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        raise GapRepairReviewError("Gap-repair promotion decisions must be a non-empty list")
    seen: set[str] = set()
    promoted_count = 0
    for decision in decisions:
        if not isinstance(decision, dict):
            raise GapRepairReviewError("Gap-repair promotion decision entries must be objects")
        candidate_id = _text(decision.get("candidate_id"))
        if not candidate_id or candidate_id in seen:
            raise GapRepairReviewError(f"Invalid or duplicate gap-repair candidate_id: {candidate_id}")
        seen.add(candidate_id)
        gemini_decision = _text(decision.get("gemini_decision"))
        if gemini_decision not in DECISION_VALUES:
            raise GapRepairReviewError(f"Invalid gap-repair Gemini decision: {candidate_id}")
        promote = bool(decision.get("promote"))
        if promote:
            promoted_count += 1
            if gemini_decision not in PROMOTABLE_DECISIONS:
                raise GapRepairReviewError(f"Unpromotable decision marked promote: {candidate_id}")
            front = _text(decision.get("front_text"))
            back = _text(decision.get("back_text"))
            if not front or not back:
                raise GapRepairReviewError(f"Promoted gap-repair decision missing text: {candidate_id}")
            _category_title(_text(decision.get("category_slug")))
            _assert_safe_text(item_id=candidate_id, fields={"front": front, "back": back})
    if int((payload.get("stats") or {}).get("promoted_count") or 0) != promoted_count:
        raise GapRepairReviewError("Gap-repair promoted_count is stale")
    return payload


def load_gap_repair_promotion_decisions(path: Path) -> dict[str, Any]:
    return validate_gap_repair_promotion_decisions(_load_json(path))


def gap_repair_decisions_to_candidate_payload(decisions_payload: dict[str, Any]) -> dict[str, Any]:
    validate_gap_repair_promotion_decisions(decisions_payload)
    candidates: list[dict[str, Any]] = []
    for decision in _as_list(decisions_payload.get("decisions")):
        if not isinstance(decision, dict) or not decision.get("promote"):
            continue
        candidate_id = _text(decision.get("candidate_id"))
        candidates.append(
            {
                "candidate_id": candidate_id,
                "notebook_slug": _text(decision.get("notebook_slug")),
                "source_path": "gap_repair_review_decisions",
                "source_index": int(decision.get("source_index") or 0),
                "front": _text(decision.get("front_text")),
                "back": _text(decision.get("back_text")),
                "category_slug": _text(decision.get("category_slug")),
                "category_title": _category_title(_text(decision.get("category_slug"))),
                "mapped_theory_ids": _as_str_list(decision.get("mapped_theory_ids")),
                "warnings": [],
                "review_status": "candidate",
                "tags": [
                    "notebooklm-gap-repair",
                    f"gemini:{_text(decision.get('gemini_decision'))}",
                ],
                "content_sha256": hashlib.sha256(
                    f"{candidate_id}\n{decision.get('front_text')}\n{decision.get('back_text')}".encode("utf-8")
                ).hexdigest(),
            }
        )
    if not candidates:
        raise GapRepairReviewError("No promoted gap-repair cards in decisions payload")
    return {
        "version": 1,
        "artifact_type": "personlighedspsykologi_notebooklm_flashcard_candidates",
        "subject_slug": SUBJECT_SLUG,
        "run_id": _text(decisions_payload.get("run_id")) or DEFAULT_GAP_REPAIR_RUN_ID,
        "notebook_slug": "gap-repair-promoted",
        "source_path": "shows/personlighedspsykologi-en/flashcards/coverage/gap_repair_review_decisions.json",
        "stats": {
            "raw_card_count": len(candidates),
            "candidate_count": len(candidates),
            "status_counts": {"candidate": len(candidates)},
        },
        "candidates": candidates,
    }


def write_gap_repair_review_markdown(decisions_payload: dict[str, Any], output_path: Path) -> None:
    stats = decisions_payload.get("stats") if isinstance(decisions_payload.get("stats"), dict) else {}
    lines = [
        "# Gap-Repair Flashcard Review Decisions",
        "",
        f"Run: `{decisions_payload.get('run_id')}`",
        "",
        f"Decision count: {stats.get('decision_count')}",
        f"Promoted: {stats.get('promoted_count')}",
        f"Rejected/deferred: {stats.get('rejected_count')}",
        f"Gemini decision counts: `{stats.get('gemini_decision_counts')}`",
        "",
    ]
    for decision in _as_list(decisions_payload.get("decisions")):
        if not isinstance(decision, dict):
            continue
        lines.extend(
            [
                f"## {decision.get('candidate_id')}",
                "",
                f"Promote: `{bool(decision.get('promote'))}`",
                f"Decision: `{decision.get('gemini_decision')}`",
                f"Notebook: `{decision.get('notebook_slug')}`",
                f"Category: `{decision.get('category_slug')}`",
                "",
                f"Reason: {decision.get('reason')}",
                "",
                f"Target gap assessment: {decision.get('target_gap_assessment')}",
                "",
            ]
        )
        if decision.get("promote"):
            lines.extend(
                [
                    f"Front: {decision.get('front_text')}",
                    "",
                    f"Back: {decision.get('back_text')}",
                    "",
                ]
            )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
