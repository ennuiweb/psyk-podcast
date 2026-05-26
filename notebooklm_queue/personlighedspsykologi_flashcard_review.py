"""Compare personlighedspsykologi flashcard pools for review.

This module is deliberately diagnostic. It reads existing Freudd decks and
local NotebookLM candidate files, classifies cards into the review architecture,
and writes local reports. It does not promote, edit, or hide learner-facing
cards.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from notebooklm_queue.json_artifact_utils import write_json_stably
from notebooklm_queue.personlighedspsykologi_matrix_flashcards import (
    LEARNER_TEXT_FORBIDDEN_PATTERNS,
    SUBJECT_SLUG,
    validate_flashcard_artifact,
)
from notebooklm_queue.personlighedspsykologi_notebooklm_flashcard_lab import (
    DEFAULT_DECK_PATH,
    DEFAULT_LAB_ROOT,
    DEFAULT_MATRIX_PATH,
    MAX_BACK_CHARS,
    MAX_FRONT_CHARS,
    THEORY_KEYWORDS,
    _safety_warnings,
    duplicate_score,
    load_matrix,
)
from notebooklm_queue.personlighedspsykologi_notebooklm_variant_flashcards import (
    validate_variant_deck,
)

REVIEW_VERSION = 1
REVIEW_ARTIFACT_TYPE = "personlighedspsykologi_flashcard_pool_comparison"
GEMINI_POOL_REVIEW_ARTIFACT_TYPE = "personlighedspsykologi_gemini_flashcard_pool_review"
GEMINI_POOL_REVIEW_BUNDLE_ARTIFACT_TYPE = "personlighedspsykologi_gemini_flashcard_pool_review_bundle"
GEMINI_POOL_REVIEW_PROMPT_VERSION = "personlighedspsykologi-gemini-flashcard-pool-review-v1"
GEMINI_QUALITY_COMPARISON_ARTIFACT_TYPE = "personlighedspsykologi_gemini_flashcard_quality_comparison"
GEMINI_QUALITY_COMPARISON_BUNDLE_ARTIFACT_TYPE = (
    "personlighedspsykologi_gemini_flashcard_quality_comparison_bundle"
)
GEMINI_QUALITY_COMPARISON_PROMPT_VERSION = "personlighedspsykologi-gemini-flashcard-quality-comparison-v1"
DEFAULT_REVIEW_RUN_ID = "flashcard-pool-review-20260526"
FULL_NOTEBOOKLM_RUN_ID = "full-matrix-20260526-notebooklm-independent"

DEFAULT_FLASHCARD_DIR = Path("shows/personlighedspsykologi-en/flashcards")
DEFAULT_ARCHIVED_FLASHCARD_DIR = DEFAULT_FLASHCARD_DIR / "archive" / "retired-live-decks-2026-05-26"
DEFAULT_VARIANT_DECK_PATH = DEFAULT_ARCHIVED_FLASHCARD_DIR / "notebooklm-varianter-personlighedspsykologi.json"
DEFAULT_INDEPENDENT_DECK_PATH = (
    DEFAULT_ARCHIVED_FLASHCARD_DIR / "notebooklm-uafhaengige-varianter-personlighedspsykologi.json"
)
DEFAULT_REPORTS_ROOT = DEFAULT_LAB_ROOT / "reports"

EXPECTED_NOTEBOOK_SLUGS = (
    "global-calibration-synthesis",
    "measurement-development-pathology",
    "psychoanalysis-experience-humanism",
    "critical-sociocultural-narrative",
    "oral-exam-comparison-workshop",
)
EXPECTED_FULL_RUN_CANDIDATE_COUNT = 259

UNKNOWN_TOPIC = "unknown"
UNKNOWN_FAMILY = "unknown"
COMMITTED_SOURCE_POOLS = {
    "canonical_matrix_deck",
    "notebooklm_variant_deck",
    "notebooklm_independent_variant_deck",
}

THEORY_TOPIC_MAP = {
    "trait_and_assessment_psychology": "traekpsykologi",
    "dynamic_personality_development": "traekpsykologi",
    "biosocial_personality_perspectives": "traekpsykologi",
    "personality_functioning_and_pathology": "personlighedsfunktion-og-patologi",
    "psychoanalytic_personality_theory": "psykoanalyse",
    "phenomenological_psychology": "faenomenologi-eksistens-humanisme",
    "existential_psychology": "faenomenologi-eksistens-humanisme",
    "humanistic_psychology": "faenomenologi-eksistens-humanisme",
    "critical_personalism": "kritisk-psykologi-og-personalisme",
    "critical_psychology": "kritisk-psykologi-og-personalisme",
    "sociocultural_poststructural_approaches": "socialkonstruktion-poststrukturalisme-narrativ",
    "narrative_psychology": "socialkonstruktion-poststrukturalisme-narrativ",
    "comparative_theory_analysis": "sammenlignende-eksamenssyntese",
}

REVIEW_FAMILIES = (
    "hovedpointe",
    "historisk-kontekst",
    "personbegreb",
    "begrebsmekanisme",
    "taenkerdistinktion",
    "metode-evidens",
    "orienteringspunkt",
    "akse-sammenligning",
    "mulighed-begraensning",
    "teori-sammenligning",
    "eksamenstrap",
    "svar-konstruktion",
)

THEORY_TOPICS = (
    "traekpsykologi",
    "personlighedsfunktion-og-patologi",
    "psykoanalyse",
    "faenomenologi-eksistens-humanisme",
    "kritisk-psykologi-og-personalisme",
    "socialkonstruktion-poststrukturalisme-narrativ",
    "sammenlignende-eksamenssyntese",
)

MINIMUM_FAMILY_TARGETS = {
    "hovedpointe": 1,
    "personbegreb": 1,
    "begrebsmekanisme": 2,
    "metode-evidens": 1,
    "orienteringspunkt": 4,
    "mulighed-begraensning": 1,
    "eksamenstrap": 1,
    "teori-sammenligning": 2,
}

MAX_SHORTLIST = 80
HARD_MAX_SHORTLIST = 120
PER_CELL_SHORTLIST_CAP = 3
PER_TOPIC_SHORTLIST_CAP = 18
UNKNOWN_RATE_STOP_THRESHOLD = 0.20
GEMINI_POOL_DECISION_VALUES = {"promote", "promote_after_edit", "merge_with_existing", "reject", "defer"}
GEMINI_POOL_WINNER_VALUES = {"candidate", "existing", "hybrid", "neither"}
GEMINI_POOL_CONFIDENCE_VALUES = {"low", "medium", "high"}
GEMINI_QUALITY_VERDICT_VALUES = {"strong", "usable", "needs_edit", "weak"}
GEMINI_VISIBILITY_VALUES = {"main_deck", "supplement", "archive", "raw_material", "do_not_use"}
QUALITY_COMPARISON_POOLS = ("canonical_matrix_deck", "full_notebooklm_candidate")
QUALITY_SAMPLE_TARGETS = {
    "canonical_matrix_deck": 152,
    "full_notebooklm_candidate": EXPECTED_FULL_RUN_CANDIDATE_COUNT,
}

DUPLICATE_EXACT_THRESHOLD = 0.95
DUPLICATE_NEAR_THRESHOLD = 0.72
DUPLICATE_SAME_SLOT_THRESHOLD = 0.42
OVERLONG_FRONT_CHARS = 220
OVERLONG_BACK_CHARS = 900


class FlashcardReviewError(ValueError):
    """Raised when flashcard pool review cannot proceed safely."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_str_list(value: object) -> list[str]:
    return [str(item).strip() for item in _as_list(value) if str(item).strip()]


def _text(value: object) -> str:
    return str(value or "").strip()


def _slug(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _text(value).casefold()).strip("-") or "x"


def _repo_relative(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FlashcardReviewError(f"Unable to read JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise FlashcardReviewError(f"JSON root must be an object: {path}")
    return payload


def _git_revision(repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return completed.stdout.strip() or "unknown"


def _candidate_files(lab_root: Path, full_run_id: str) -> list[Path]:
    candidates_root = lab_root / "runs" / full_run_id / "candidates"
    return [candidates_root / f"{slug}.candidates.json" for slug in EXPECTED_NOTEBOOK_SLUGS]


def _is_ignored(path: Path, repo_root: Path) -> bool:
    try:
        subprocess.run(["git", "check-ignore", "-q", str(path)], cwd=repo_root, check=True)
    except subprocess.CalledProcessError:
        return False
    except OSError:
        return False
    return True


def _input_entry(path: Path, repo_root: Path, *, label: str) -> dict[str, Any]:
    return {
        "label": label,
        "path": _repo_relative(path, repo_root),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
    }


def validate_review_inputs(
    *,
    repo_root: Path,
    matrix_path: Path,
    matrix_deck_path: Path,
    variant_deck_path: Path,
    independent_deck_path: Path,
    lab_root: Path,
    full_run_id: str,
    reports_root: Path,
    allow_count_drift: bool = False,
    allow_unignored_report_output: bool = False,
) -> dict[str, Any]:
    matrix = load_matrix(matrix_path)
    matrix_deck = _load_json(matrix_deck_path)
    validate_flashcard_artifact(matrix_deck, matrix=matrix)
    variant_deck = _load_json(variant_deck_path)
    validate_variant_deck(variant_deck, expected_deck_slug="notebooklm-varianter-personlighedspsykologi")
    independent_deck = _load_json(independent_deck_path)
    validate_variant_deck(
        independent_deck,
        expected_deck_slug="notebooklm-uafhaengige-varianter-personlighedspsykologi",
    )

    candidate_files = _candidate_files(lab_root, full_run_id)
    missing = [path for path in candidate_files if not path.exists()]
    if missing:
        rendered = ", ".join(_repo_relative(path, repo_root) for path in missing)
        raise FlashcardReviewError(
            "Missing full-run NotebookLM candidate files. Regenerate or restore the run before review: "
            + rendered
        )

    candidate_count = 0
    candidate_stats: dict[str, Any] = {}
    for path in candidate_files:
        payload = _load_json(path)
        count = len([item for item in _as_list(payload.get("candidates")) if isinstance(item, dict)])
        candidate_count += count
        candidate_stats[path.stem.replace(".candidates", "")] = {
            "candidate_count": count,
            "stats": payload.get("stats") if isinstance(payload.get("stats"), dict) else {},
        }
    if candidate_count != EXPECTED_FULL_RUN_CANDIDATE_COUNT and not allow_count_drift:
        raise FlashcardReviewError(
            f"Expected {EXPECTED_FULL_RUN_CANDIDATE_COUNT} full-run candidates, found {candidate_count}. "
            "Pass --allow-count-drift only if this drift is intentional."
        )

    reports_root.mkdir(parents=True, exist_ok=True)
    probe = reports_root / "__ignore_probe__"
    if not allow_unignored_report_output and not _is_ignored(probe, repo_root):
        raise FlashcardReviewError(
            f"Report output is not gitignored: {_repo_relative(reports_root, repo_root)}. "
            "Add a .gitignore rule before generating reports."
        )

    return {
        "matrix": matrix,
        "decks": {
            "canonical_matrix_deck": matrix_deck,
            "notebooklm_variant_deck": variant_deck,
            "notebooklm_independent_variant_deck": independent_deck,
        },
        "candidate_files": candidate_files,
        "candidate_count": candidate_count,
        "candidate_stats": candidate_stats,
    }


def _theory_ids_from_tags(tags: list[str], matrix: dict[str, Any]) -> list[str]:
    known = {
        _text(row.get("theory_id"))
        for row in _as_list(matrix.get("rows"))
        if isinstance(row, dict) and _text(row.get("theory_id"))
    }
    theory_ids = []
    for tag in tags:
        if tag in known:
            theory_ids.append(tag)
    return sorted(set(theory_ids))


def _infer_theory_ids(front: str, back: str, matrix: dict[str, Any]) -> list[str]:
    text = f"{front} {back}".casefold()
    matches: list[tuple[int, str]] = []
    for row in _as_list(matrix.get("rows")):
        if not isinstance(row, dict):
            continue
        theory_id = _text(row.get("theory_id"))
        if not theory_id:
            continue
        needles = {_text(row.get("label")).casefold(), theory_id.replace("_", " ").casefold()}
        needles.update(alias.casefold() for alias in _as_str_list(row.get("aliases")))
        keywords = THEORY_KEYWORDS.get(theory_id, ())
        score = sum(4 for needle in needles if needle and needle in text)
        score += sum(3 for keyword in keywords if keyword and keyword.casefold() in text)
        score += sum(1 for concept in _as_str_list(row.get("central_concepts"))[:10] if concept.casefold() in text)
        if score:
            matches.append((score, theory_id))
    matches.sort(key=lambda item: (-item[0], item[1]))
    return [theory_id for _, theory_id in matches[:4]]


def classify_topic(theory_ids: list[str], *, front: str, back: str, category_slug: str) -> dict[str, Any]:
    topics = sorted({THEORY_TOPIC_MAP.get(theory_id, UNKNOWN_TOPIC) for theory_id in theory_ids})
    topics = [topic for topic in topics if topic != UNKNOWN_TOPIC]
    text = f"{front} {back}".casefold()
    evidence: list[str] = []
    if "sammenlign" in text or "forskel" in text or "kontrast" in text or category_slug == "sammenligninger":
        evidence.append("comparison_language_or_category")
    if "comparative_theory_analysis" in theory_ids:
        evidence.append("comparative_theory_analysis_tag")
        return {
            "theory_topic": "sammenlignende-eksamenssyntese",
            "classification_confidence": "high",
            "classification_evidence": evidence,
        }
    if len(topics) > 1:
        evidence.append("multiple_theory_topics")
        return {
            "theory_topic": "sammenlignende-eksamenssyntese",
            "classification_confidence": "medium",
            "classification_evidence": evidence,
        }
    if topics:
        evidence.append("mapped_theory_id")
        return {
            "theory_topic": topics[0],
            "classification_confidence": "high" if theory_ids else "medium",
            "classification_evidence": evidence,
        }
    return {
        "theory_topic": UNKNOWN_TOPIC,
        "classification_confidence": "low",
        "classification_evidence": ["no_theory_match"],
    }


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def classify_family(
    *,
    front: str,
    back: str,
    category_slug: str,
    tags: list[str],
) -> dict[str, Any]:
    text = f"{front} {back}".casefold()
    tag_set = set(tags)
    evidence: list[str] = []

    if "comparison" in tag_set or category_slug == "sammenligninger":
        evidence.append("comparison_tag_or_category")
        if _contains_any(text, ("essens", "kontekst", "determination", "agency", "agens", "historicitet")):
            return _family("akse-sammenligning", "high", evidence + ["orientation_axis_terms"])
        if _contains_any(text, ("bygge et svar", "mundtlig", "eksamen", "svar")):
            return _family("svar-konstruktion", "medium", evidence + ["answer_construction_terms"])
        return _family("teori-sammenligning", "high", evidence)
    if "orientation" in tag_set or category_slug == "orienteringspunkter":
        evidence.append("orientation_tag_or_category")
        if _contains_any(text, ("adskiller", "sammenlign", "forskel", "versus", " vs ")):
            return _family("akse-sammenligning", "high", evidence + ["comparison_language"])
        return _family("orienteringspunkt", "high", evidence)
    if "trap" in tag_set or category_slug == "eksamenstraps":
        return _family("eksamenstrap", "high", ["trap_tag_or_category"])
    if "method" in tag_set or category_slug == "metode-og-evidens":
        return _family("metode-evidens", "high", ["method_tag_or_category"])
    if "affordance-limit" in tag_set or category_slug == "styrker-og-begraensninger":
        return _family("mulighed-begraensning", "high", ["affordance_limit_tag_or_category"])
    if "model" in tag_set:
        return _family("personbegreb", "high", ["model_tag"])

    if _contains_any(text, ("hovedpointe", "kernepointe", "grundpointe")):
        return _family("hovedpointe", "high", ["hovedpointe_keyword"])
    if _contains_any(text, ("faghistorisk", "historisk", "opstod", "reaktion mod", "reagerer mod")):
        return _family("historisk-kontekst", "medium", ["historical_keyword"])
    if _contains_any(text, ("freud", "lacan", "laplanche", "rogers", "maslow", "foucault", "gergen", "bruner", "mcadams", "raggatt")):
        if _contains_any(text, ("forskel", "adskiller", "hvordan forskyder", "versus")):
            return _family("taenkerdistinktion", "medium", ["thinker_and_distinction_keywords"])
    if _contains_any(text, ("personbegreb", "subjekt", "subjektivitet", "personlighed", "selv")):
        return _family("personbegreb", "medium", ["person_subject_keywords"])
    if _contains_any(text, ("begreb", "funktion", "hvordan fungerer", "hvilken funktion", "mekanisme")):
        return _family("begrebsmekanisme", "medium", ["concept_mechanism_keywords"])
    if _contains_any(text, ("metode", "evidens", "faktoranalyse", "klinisk", "genealogisk", "fænomenologisk analyse")):
        return _family("metode-evidens", "medium", ["method_keywords"])
    if _contains_any(text, ("mulighed", "begrænsning", "begrænsninger", "styrke", "svaghed", "kritik")):
        return _family("mulighed-begraensning", "medium", ["affordance_limit_keywords"])
    return _family(UNKNOWN_FAMILY, "low", ["no_family_rule"])


def _family(family: str, confidence: str, evidence: list[str]) -> dict[str, Any]:
    return {
        "review_family": family,
        "classification_confidence": confidence,
        "classification_evidence": evidence,
    }


def _review_card_key(source_pool: str, source_id: str) -> str:
    return f"{source_pool}:{source_id}"


def _normalize_deck_cards(
    *,
    deck: dict[str, Any],
    source_pool: str,
    source_path: Path,
    repo_root: Path,
    matrix: dict[str, Any],
) -> list[dict[str, Any]]:
    cards = []
    for index, card in enumerate(_as_list(deck.get("cards")), start=1):
        if not isinstance(card, dict):
            continue
        front = _text(card.get("front_text"))
        back = _text(card.get("back_text"))
        tags = _as_str_list(card.get("tags"))
        theory_ids = _theory_ids_from_tags(tags, matrix)
        if not theory_ids:
            theory_ids = _infer_theory_ids(front, back, matrix)
        category_slug = _text(card.get("category_slug"))
        cards.append(
            _base_review_card(
                source_pool=source_pool,
                source_path=_repo_relative(source_path, repo_root),
                source_index=index,
                source_id=_text(card.get("card_id")) or str(index),
                front=front,
                back=back,
                category_slug=category_slug,
                category_title=_text(card.get("category_title")),
                tags=tags,
                theory_ids=theory_ids,
                review_status="committed",
                original_card_id=_text(card.get("card_id")),
                candidate_id="",
                notebook_slug="",
                warnings=[],
                matrix=matrix,
            )
        )
    return cards


def _normalize_candidate_cards(
    *,
    payload: dict[str, Any],
    source_path: Path,
    repo_root: Path,
    matrix: dict[str, Any],
) -> list[dict[str, Any]]:
    cards = []
    for candidate in _as_list(payload.get("candidates")):
        if not isinstance(candidate, dict):
            continue
        front = _text(candidate.get("front"))
        back = _text(candidate.get("back"))
        candidate_id = _text(candidate.get("candidate_id"))
        theory_ids = _as_str_list(candidate.get("mapped_theory_ids"))
        if not theory_ids:
            theory_ids = _infer_theory_ids(front, back, matrix)
        warnings = sorted(set(_as_str_list(candidate.get("warnings")) + _safety_warnings(front, back)))
        cards.append(
            _base_review_card(
                source_pool="full_notebooklm_candidate",
                source_path=_repo_relative(source_path, repo_root),
                source_index=int(candidate.get("source_index") or 0),
                source_id=candidate_id,
                front=front,
                back=back,
                category_slug=_text(candidate.get("category_slug")),
                category_title=_text(candidate.get("category_title")),
                tags=[],
                theory_ids=theory_ids,
                review_status=_text(candidate.get("review_status")),
                original_card_id="",
                candidate_id=candidate_id,
                notebook_slug=_text(candidate.get("notebook_slug")),
                warnings=warnings,
                matrix=matrix,
            )
        )
    return cards


def _base_review_card(
    *,
    source_pool: str,
    source_path: str,
    source_index: int,
    source_id: str,
    front: str,
    back: str,
    category_slug: str,
    category_title: str,
    tags: list[str],
    theory_ids: list[str],
    review_status: str,
    original_card_id: str,
    candidate_id: str,
    notebook_slug: str,
    warnings: list[str],
    matrix: dict[str, Any],
) -> dict[str, Any]:
    topic = classify_topic(theory_ids, front=front, back=back, category_slug=category_slug)
    family = classify_family(front=front, back=back, category_slug=category_slug, tags=tags)
    shape_warnings = list(warnings)
    if len(front) > OVERLONG_FRONT_CHARS:
        shape_warnings.append("review_front_overlong")
    if len(back) > OVERLONG_BACK_CHARS:
        shape_warnings.append("review_back_overlong")
    for pattern in LEARNER_TEXT_FORBIDDEN_PATTERNS:
        if pattern.search(front + "\n" + back):
            shape_warnings.append("unsafe_learner_text")
            break
    return {
        "card_key": _review_card_key(source_pool, source_id or str(source_index)),
        "source_pool": source_pool,
        "source_path": source_path,
        "source_index": source_index,
        "source_id": source_id,
        "original_card_id": original_card_id,
        "candidate_id": candidate_id,
        "notebook_slug": notebook_slug,
        "front": front,
        "back": back,
        "front_chars": len(front),
        "back_chars": len(back),
        "category_slug": category_slug,
        "category_title": category_title,
        "tags": tags,
        "matrix_theory_ids": sorted(set(theory_ids)),
        "theory_topic": topic["theory_topic"],
        "theory_topic_confidence": topic["classification_confidence"],
        "theory_topic_evidence": topic["classification_evidence"],
        "review_family": family["review_family"],
        "review_family_confidence": family["classification_confidence"],
        "review_family_evidence": family["classification_evidence"],
        "review_status": review_status,
        "warnings": sorted(set(shape_warnings)),
    }


def _attach_duplicate_analysis(cards: list[dict[str, Any]]) -> None:
    for card in cards:
        nearest_score = 0.0
        nearest_key = ""
        nearest_pool = ""
        duplicate_kind = "none"
        for other in cards:
            if other is card:
                continue
            score, _ = duplicate_score(
                _text(card.get("front")),
                _text(card.get("back")),
                [
                    {
                        "card_id": _text(other.get("card_key")),
                        "front_text": _text(other.get("front")),
                        "back_text": _text(other.get("back")),
                    }
                ],
            )
            if score > nearest_score:
                nearest_score = score
                nearest_key = _text(other.get("card_key"))
                nearest_pool = _text(other.get("source_pool"))
        if nearest_score >= DUPLICATE_EXACT_THRESHOLD:
            duplicate_kind = "exact_or_front_match"
        elif nearest_score >= DUPLICATE_NEAR_THRESHOLD:
            duplicate_kind = "near_duplicate"
        elif (
            nearest_score >= DUPLICATE_SAME_SLOT_THRESHOLD
            and card.get("theory_topic") != UNKNOWN_TOPIC
            and card.get("review_family") != UNKNOWN_FAMILY
        ):
            duplicate_kind = "same_slot_collision"
        card["duplicate"] = {
            "nearest_card_key": nearest_key,
            "nearest_source_pool": nearest_pool,
            "score": round(nearest_score, 4),
            "kind": duplicate_kind,
        }


def _coverage(cards: list[dict[str, Any]]) -> dict[str, Any]:
    grid: dict[str, dict[str, dict[str, int]]] = {
        topic: {
            family: {"total": 0, "committed": 0, "candidates": 0}
            for family in REVIEW_FAMILIES
        }
        for topic in THEORY_TOPICS
    }
    unknown = {"topic": 0, "family": 0}
    for card in cards:
        topic = _text(card.get("theory_topic"))
        family = _text(card.get("review_family"))
        if topic == UNKNOWN_TOPIC:
            unknown["topic"] += 1
            continue
        if family == UNKNOWN_FAMILY:
            unknown["family"] += 1
            continue
        if topic not in grid or family not in grid[topic]:
            continue
        bucket = grid[topic][family]
        bucket["total"] += 1
        if card.get("source_pool") in COMMITTED_SOURCE_POOLS:
            bucket["committed"] += 1
        else:
            bucket["candidates"] += 1
    missing = []
    overcrowded = []
    for topic, families in grid.items():
        if topic == "sammenlignende-eksamenssyntese":
            target_families = {"teori-sammenligning": 3, "akse-sammenligning": 2, "eksamenstrap": 2, "svar-konstruktion": 1}
        else:
            target_families = MINIMUM_FAMILY_TARGETS
        for family, target in target_families.items():
            committed = families.get(family, {}).get("committed", 0)
            total = families.get(family, {}).get("total", 0)
            if total < target:
                missing.append({"theory_topic": topic, "review_family": family, "target": target, "total": total, "committed": committed})
        for family, counts in families.items():
            if counts["total"] >= 8:
                overcrowded.append({"theory_topic": topic, "review_family": family, **counts})
    return {"grid": grid, "unknown_counts": unknown, "missing_cells": missing, "overcrowded_cells": overcrowded}


def _shortlist(cards: list[dict[str, Any]], missing_cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    missing = {(item["theory_topic"], item["review_family"]) for item in missing_cells}
    selected: list[dict[str, Any]] = []
    per_cell: Counter[tuple[str, str]] = Counter()
    per_topic: Counter[str] = Counter()
    candidates = [card for card in cards if card.get("source_pool") == "full_notebooklm_candidate"]

    def score(card: dict[str, Any]) -> tuple[int, float, int, int, int]:
        cell = (_text(card.get("theory_topic")), _text(card.get("review_family")))
        duplicate = card.get("duplicate") if isinstance(card.get("duplicate"), dict) else {}
        duplicate_score_value = float(duplicate.get("score") or 0.0)
        high_family = 1 if card.get("review_family") in {
            "teori-sammenligning",
            "akse-sammenligning",
            "eksamenstrap",
            "begrebsmekanisme",
            "svar-konstruktion",
        } else 0
        clean_shape = 1 if not ({"review_front_overlong", "review_back_overlong", "unsafe_learner_text"} & set(_as_str_list(card.get("warnings")))) else 0
        warning_penalty = len(_as_str_list(card.get("warnings")))
        return (
            1 if cell in missing else 0,
            -duplicate_score_value,
            high_family,
            clean_shape,
            -warning_penalty,
        )

    for card in sorted(candidates, key=score, reverse=True):
        if card.get("review_status") == "auto_rejected":
            continue
        if card.get("theory_topic") == UNKNOWN_TOPIC or card.get("review_family") == UNKNOWN_FAMILY:
            continue
        duplicate = card.get("duplicate") if isinstance(card.get("duplicate"), dict) else {}
        if duplicate.get("kind") in {"exact_or_front_match", "near_duplicate"}:
            continue
        cell = (_text(card.get("theory_topic")), _text(card.get("review_family")))
        if per_cell[cell] >= PER_CELL_SHORTLIST_CAP or per_topic[cell[0]] >= PER_TOPIC_SHORTLIST_CAP:
            continue
        selected.append(
            {
                "card_key": card["card_key"],
                "candidate_id": card.get("candidate_id"),
                "notebook_slug": card.get("notebook_slug"),
                "theory_topic": card.get("theory_topic"),
                "review_family": card.get("review_family"),
                "front": card.get("front"),
                "back": card.get("back"),
                "category_slug": card.get("category_slug"),
                "duplicate": card.get("duplicate"),
                "warnings": card.get("warnings"),
                "selection_reasons": _selection_reasons(card, cell in missing),
            }
        )
        per_cell[cell] += 1
        per_topic[cell[0]] += 1
        if len(selected) >= MAX_SHORTLIST:
            break
    return selected[:HARD_MAX_SHORTLIST]


def _selection_reasons(card: dict[str, Any], fills_missing: bool) -> list[str]:
    reasons = []
    if fills_missing:
        reasons.append("fills_missing_or_weak_cell")
    duplicate = card.get("duplicate") if isinstance(card.get("duplicate"), dict) else {}
    if float(duplicate.get("score") or 0.0) < DUPLICATE_SAME_SLOT_THRESHOLD:
        reasons.append("low_duplicate_overlap")
    if card.get("review_family") in {"teori-sammenligning", "akse-sammenligning", "eksamenstrap", "begrebsmekanisme", "svar-konstruktion"}:
        reasons.append("high_exam_use_family")
    if not card.get("warnings"):
        reasons.append("no_warnings")
    return reasons or ["ranked_candidate"]


def build_comparison_report(
    *,
    repo_root: Path,
    review_run_id: str = DEFAULT_REVIEW_RUN_ID,
    matrix_path: Path = DEFAULT_MATRIX_PATH,
    matrix_deck_path: Path = DEFAULT_DECK_PATH,
    variant_deck_path: Path = DEFAULT_VARIANT_DECK_PATH,
    independent_deck_path: Path = DEFAULT_INDEPENDENT_DECK_PATH,
    lab_root: Path = DEFAULT_LAB_ROOT,
    full_run_id: str = FULL_NOTEBOOKLM_RUN_ID,
    reports_root: Path = DEFAULT_REPORTS_ROOT,
    allow_count_drift: bool = False,
    allow_unignored_report_output: bool = False,
    generated_at: str | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    inputs = validate_review_inputs(
        repo_root=repo_root,
        matrix_path=matrix_path,
        matrix_deck_path=matrix_deck_path,
        variant_deck_path=variant_deck_path,
        independent_deck_path=independent_deck_path,
        lab_root=lab_root,
        full_run_id=full_run_id,
        reports_root=reports_root,
        allow_count_drift=allow_count_drift,
        allow_unignored_report_output=allow_unignored_report_output,
    )
    matrix = inputs["matrix"]
    cards: list[dict[str, Any]] = []
    for source_pool, deck in inputs["decks"].items():
        path = {
            "canonical_matrix_deck": matrix_deck_path,
            "notebooklm_variant_deck": variant_deck_path,
            "notebooklm_independent_variant_deck": independent_deck_path,
        }[source_pool]
        cards.extend(
            _normalize_deck_cards(
                deck=deck,
                source_pool=source_pool,
                source_path=path,
                repo_root=repo_root,
                matrix=matrix,
            )
        )
    for path in inputs["candidate_files"]:
        cards.extend(
            _normalize_candidate_cards(
                payload=_load_json(path),
                source_path=path,
                repo_root=repo_root,
                matrix=matrix,
            )
        )
    _attach_duplicate_analysis(cards)
    coverage = _coverage(cards)
    shortlist = _shortlist(cards, coverage["missing_cells"])
    source_counts = Counter(_text(card.get("source_pool")) for card in cards)
    family_counts = Counter(_text(card.get("review_family")) for card in cards)
    topic_counts = Counter(_text(card.get("theory_topic")) for card in cards)
    non_auto = [card for card in cards if card.get("review_status") != "auto_rejected"]
    unknown_non_auto = [
        card
        for card in non_auto
        if card.get("theory_topic") == UNKNOWN_TOPIC or card.get("review_family") == UNKNOWN_FAMILY
    ]
    unknown_rate = round(len(unknown_non_auto) / len(non_auto), 4) if non_auto else 0.0
    stop_gates = {
        "unknown_rate": unknown_rate,
        "unknown_rate_threshold": UNKNOWN_RATE_STOP_THRESHOLD,
        "unknown_rate_blocks_gemini": unknown_rate > UNKNOWN_RATE_STOP_THRESHOLD,
        "committed_unclassified_count": sum(
            1
            for card in cards
            if card.get("source_pool") in COMMITTED_SOURCE_POOLS
            and (card.get("theory_topic") == UNKNOWN_TOPIC or card.get("review_family") == UNKNOWN_FAMILY)
        ),
    }
    duplicate_counts = Counter(
        _text((card.get("duplicate") if isinstance(card.get("duplicate"), dict) else {}).get("kind"))
        for card in cards
    )
    recommendations = _recommendations(
        cards=cards,
        shortlist=shortlist,
        coverage=coverage,
        stop_gates=stop_gates,
        duplicate_counts=duplicate_counts,
    )
    report = {
        "version": REVIEW_VERSION,
        "artifact_type": REVIEW_ARTIFACT_TYPE,
        "subject_slug": SUBJECT_SLUG,
        "review_run_id": review_run_id,
        "generated_at": generated_at or utc_now_iso(),
        "manifest": {
            "git_revision": _git_revision(repo_root),
            "inputs": [
                _input_entry(matrix_path, repo_root, label="exam_theory_matrix"),
                _input_entry(matrix_deck_path, repo_root, label="canonical_matrix_deck"),
                _input_entry(variant_deck_path, repo_root, label="notebooklm_variant_deck"),
                _input_entry(independent_deck_path, repo_root, label="notebooklm_independent_variant_deck"),
                *[
                    _input_entry(path, repo_root, label=f"full_notebooklm_candidate:{path.stem.replace('.candidates', '')}")
                    for path in inputs["candidate_files"]
                ],
            ],
            "thresholds": {
                "unknown_rate_stop_threshold": UNKNOWN_RATE_STOP_THRESHOLD,
                "duplicate_exact_threshold": DUPLICATE_EXACT_THRESHOLD,
                "duplicate_near_threshold": DUPLICATE_NEAR_THRESHOLD,
                "duplicate_same_slot_threshold": DUPLICATE_SAME_SLOT_THRESHOLD,
                "max_shortlist": MAX_SHORTLIST,
                "hard_max_shortlist": HARD_MAX_SHORTLIST,
            },
            "full_run_id": full_run_id,
        },
        "stats": {
            "card_count": len(cards),
            "source_counts": dict(sorted(source_counts.items())),
            "review_family_counts": dict(sorted(family_counts.items())),
            "theory_topic_counts": dict(sorted(topic_counts.items())),
            "duplicate_kind_counts": dict(sorted(duplicate_counts.items())),
            "candidate_count": inputs["candidate_count"],
            "candidate_stats": inputs["candidate_stats"],
        },
        "stop_gates": stop_gates,
        "coverage": coverage,
        "shortlist": shortlist,
        "recommendations": recommendations,
        "cards": cards,
    }
    return report


def _recommendations(
    *,
    cards: list[dict[str, Any]],
    shortlist: list[dict[str, Any]],
    coverage: dict[str, Any],
    stop_gates: dict[str, Any],
    duplicate_counts: Counter[str],
) -> list[str]:
    recommendations = []
    if stop_gates.get("unknown_rate_blocks_gemini"):
        recommendations.append("Stop before Gemini: unknown classification rate is above threshold.")
    if stop_gates.get("committed_unclassified_count"):
        recommendations.append("Fix committed-deck classification before promotion planning.")
    if not shortlist:
        recommendations.append("No Gemini call recommended yet: deterministic shortlist is empty.")
    elif not stop_gates.get("unknown_rate_blocks_gemini"):
        recommendations.append(f"Gemini review can proceed on the bounded shortlist ({len(shortlist)} cards).")
    if len(coverage.get("missing_cells", [])) > 20:
        recommendations.append("Many coverage gaps remain; consider deterministic matrix-deck improvements after review.")
    near = duplicate_counts.get("near_duplicate", 0) + duplicate_counts.get("exact_or_front_match", 0)
    if near:
        recommendations.append(f"Review duplicate pressure carefully: {near} exact/near duplicate cards detected.")
    recommendations.append("Do not mutate learner-facing decks until a promotion decision artifact exists.")
    return recommendations


def _cards_by_key(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        _text(card.get("card_key")): card
        for card in _as_list(report.get("cards"))
        if isinstance(card, dict) and _text(card.get("card_key"))
    }


def _pool_review_card_for_gemini(shortlist_item: dict[str, Any], cards_by_key: dict[str, dict[str, Any]]) -> dict[str, Any]:
    card_key = _text(shortlist_item.get("card_key"))
    card = cards_by_key.get(card_key, {})
    duplicate = card.get("duplicate") if isinstance(card.get("duplicate"), dict) else {}
    nearest_key = _text(duplicate.get("nearest_card_key"))
    nearest = cards_by_key.get(nearest_key, {}) if nearest_key else {}
    nearest_entry: dict[str, Any] | None = None
    if nearest:
        nearest_entry = {
            "card_key": nearest_key,
            "source_pool": _text(nearest.get("source_pool")),
            "front": _text(nearest.get("front")),
            "back": _text(nearest.get("back")),
            "category_slug": _text(nearest.get("category_slug")),
            "theory_topic": _text(nearest.get("theory_topic")),
            "review_family": _text(nearest.get("review_family")),
            "duplicate_score": float(duplicate.get("score") or 0.0),
            "duplicate_kind": _text(duplicate.get("kind")),
        }
    return {
        "card_key": card_key,
        "candidate_id": _text(card.get("candidate_id")),
        "notebook_slug": _text(card.get("notebook_slug")),
        "source_path": _text(card.get("source_path")),
        "source_index": card.get("source_index"),
        "front": _text(card.get("front")),
        "back": _text(card.get("back")),
        "category_slug": _text(card.get("category_slug")),
        "matrix_theory_ids": _as_str_list(card.get("matrix_theory_ids")),
        "theory_topic": _text(card.get("theory_topic")),
        "review_family": _text(card.get("review_family")),
        "review_status": _text(card.get("review_status")),
        "warnings": _as_str_list(card.get("warnings")),
        "selection_reasons": _as_str_list(shortlist_item.get("selection_reasons")),
        "nearest_existing_or_pool_card": nearest_entry,
    }


def build_gemini_pool_review_bundle(
    *,
    comparison_report: dict[str, Any],
    model: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    if comparison_report.get("artifact_type") != REVIEW_ARTIFACT_TYPE:
        raise FlashcardReviewError("Gemini pool review requires a flashcard pool comparison report")
    stop_gates = comparison_report.get("stop_gates") if isinstance(comparison_report.get("stop_gates"), dict) else {}
    if stop_gates.get("unknown_rate_blocks_gemini"):
        raise FlashcardReviewError("Gemini pool review is blocked by the comparison report unknown-rate gate")
    shortlist = [item for item in _as_list(comparison_report.get("shortlist")) if isinstance(item, dict)]
    if not shortlist:
        raise FlashcardReviewError("Gemini pool review needs a non-empty shortlist")
    if len(shortlist) > HARD_MAX_SHORTLIST:
        raise FlashcardReviewError(f"Gemini pool review shortlist exceeds hard cap: {len(shortlist)} > {HARD_MAX_SHORTLIST}")
    cards_by_key = _cards_by_key(comparison_report)
    if any(_text(item.get("card_key")) not in cards_by_key for item in shortlist):
        raise FlashcardReviewError("Gemini pool review shortlist references unknown cards")
    coverage = comparison_report.get("coverage") if isinstance(comparison_report.get("coverage"), dict) else {}
    stats = comparison_report.get("stats") if isinstance(comparison_report.get("stats"), dict) else {}
    return {
        "version": REVIEW_VERSION,
        "artifact_type": GEMINI_POOL_REVIEW_BUNDLE_ARTIFACT_TYPE,
        "subject_slug": SUBJECT_SLUG,
        "review_run_id": _text(comparison_report.get("review_run_id")),
        "generated_at": generated_at or utc_now_iso(),
        "model": model,
        "prompt_version": GEMINI_POOL_REVIEW_PROMPT_VERSION,
        "input_fingerprints": {
            "comparison_report": hashlib.sha256(json.dumps(comparison_report, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
        },
        "review_contract": {
            "task": "Evaluate the bounded NotebookLM candidate shortlist against the existing Freudd personlighedspsykologi flashcard pools.",
            "decision_values": sorted(GEMINI_POOL_DECISION_VALUES),
            "winner_values": sorted(GEMINI_POOL_WINNER_VALUES),
            "quality_dimensions": [
                "course coverage",
                "oral-exam usefulness",
                "psychological precision",
                "Danish wording clarity",
                "atomic retrieval shape",
                "duplicate pressure against existing cards",
                "safety: no student names, local paths, internal IDs, or hidden provenance",
            ],
            "decision_rules": [
                "promote only when the candidate is already learner-ready and materially improves the deck",
                "promote_after_edit when the idea is valuable but wording or precision needs repair",
                "merge_with_existing when the candidate mainly improves an existing Freudd card",
                "reject when the candidate is redundant, vague, misleading, unsafe, or not worth adding",
                "defer when the candidate needs source checking or a product decision before promotion",
                "never recommend direct deck mutation; this review is advisory",
            ],
        },
        "pool_context": {
            "source_counts": stats.get("source_counts") if isinstance(stats.get("source_counts"), dict) else {},
            "review_family_counts": stats.get("review_family_counts") if isinstance(stats.get("review_family_counts"), dict) else {},
            "theory_topic_counts": stats.get("theory_topic_counts") if isinstance(stats.get("theory_topic_counts"), dict) else {},
            "duplicate_kind_counts": stats.get("duplicate_kind_counts") if isinstance(stats.get("duplicate_kind_counts"), dict) else {},
            "unknown_rate": stop_gates.get("unknown_rate"),
            "missing_cells": _as_list(coverage.get("missing_cells"))[:60],
            "overcrowded_cells": _as_list(coverage.get("overcrowded_cells"))[:60],
            "deterministic_recommendations": _as_str_list(comparison_report.get("recommendations")),
        },
        "shortlist": [_pool_review_card_for_gemini(item, cards_by_key) for item in shortlist],
    }


def gemini_pool_review_system_instruction() -> str:
    return "\n".join(
        [
            "You are a strict Danish university psychology flashcard quality reviewer.",
            "Return only valid JSON matching the requested schema.",
            "Compare NotebookLM candidate cards against existing Freudd flashcard pools.",
            "Reward exam-useful, precise, atomic cards; penalize generic, redundant, vague, or source-risky cards.",
            "Prefer merge or reject over adding near-duplicates.",
            "Do not invent course claims beyond the supplied card text and pool context.",
            "Do not approve learner-facing text that leaks student names, local paths, source-note IDs, or internal provenance.",
        ]
    )


def gemini_pool_review_user_prompt(bundle: dict[str, Any]) -> str:
    return "\n".join(
        [
            "Review every card in the shortlist.",
            "",
            "Return exactly one decision for every card_key. Use Danish for edited_front, edited_back, reason, added_value, and implementation_note.",
            "Keep edited_front and edited_back empty unless decision is promote_after_edit.",
            "Score each quality dimension from 1 to 5. The final recommendation should be conservative: only promote cards that clearly improve Freudd.",
            "",
            "Input bundle:",
            "",
            json.dumps(bundle, ensure_ascii=False, sort_keys=True, indent=2),
        ]
    )


def gemini_pool_review_response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "review_summary": {
                "type": "object",
                "properties": {
                    "overall_assessment": {"type": "string"},
                    "best_pool": {"type": "string"},
                    "candidate_count": {"type": "integer"},
                    "promote_count": {"type": "integer"},
                    "promote_after_edit_count": {"type": "integer"},
                    "merge_with_existing_count": {"type": "integer"},
                    "reject_count": {"type": "integer"},
                    "defer_count": {"type": "integer"},
                    "main_risks": {"type": "array", "items": {"type": "string"}},
                    "implementation_priorities": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "overall_assessment",
                    "best_pool",
                    "candidate_count",
                    "promote_count",
                    "promote_after_edit_count",
                    "merge_with_existing_count",
                    "reject_count",
                    "defer_count",
                    "main_risks",
                    "implementation_priorities",
                ],
            },
            "decisions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "card_key": {"type": "string"},
                        "decision": {"type": "string", "enum": sorted(GEMINI_POOL_DECISION_VALUES)},
                        "winner": {"type": "string", "enum": sorted(GEMINI_POOL_WINNER_VALUES)},
                        "confidence": {"type": "string", "enum": sorted(GEMINI_POOL_CONFIDENCE_VALUES)},
                        "coverage_score": {"type": "integer"},
                        "exam_usefulness_score": {"type": "integer"},
                        "precision_score": {"type": "integer"},
                        "wording_score": {"type": "integer"},
                        "duplicate_risk_score": {"type": "integer"},
                        "reason": {"type": "string"},
                        "added_value": {"type": "string"},
                        "implementation_note": {"type": "string"},
                        "edited_front": {"type": "string"},
                        "edited_back": {"type": "string"},
                        "safety_flags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "card_key",
                        "decision",
                        "winner",
                        "confidence",
                        "coverage_score",
                        "exam_usefulness_score",
                        "precision_score",
                        "wording_score",
                        "duplicate_risk_score",
                        "reason",
                        "added_value",
                        "implementation_note",
                        "edited_front",
                        "edited_back",
                        "safety_flags",
                    ],
                },
            },
        },
        "required": ["review_summary", "decisions"],
    }


def _validate_score(value: object, *, field: str, card_key: str) -> int:
    original_value = value
    if not isinstance(value, (int, float)):
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
        match = re.search(r"\b([1-5])\b", rendered)
        if match:
            value = match.group(1)
    try:
        score = int(value)
    except (TypeError, ValueError) as exc:
        raise FlashcardReviewError(
            f"Gemini review score must be an integer for {card_key}: {field}; got {original_value!r}"
        ) from exc
    if 6 <= score <= 10:
        score = max(1, min(5, round(score / 2)))
    if score < 1 or score > 5:
        raise FlashcardReviewError(f"Gemini review score must be 1-5 for {card_key}: {field}; got {original_value!r}")
    return score


def validate_gemini_pool_review(
    review_payload: dict[str, Any],
    *,
    bundle: dict[str, Any],
    model: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    raw_decisions = review_payload.get("decisions")
    if not isinstance(raw_decisions, list):
        raise FlashcardReviewError("Gemini pool review payload must contain decisions list")
    expected_keys = {
        _text(item.get("card_key"))
        for item in _as_list(bundle.get("shortlist"))
        if isinstance(item, dict) and _text(item.get("card_key"))
    }
    decisions: list[dict[str, Any]] = []
    seen: set[str] = set()
    decision_counts: Counter[str] = Counter()
    for raw in raw_decisions:
        if not isinstance(raw, dict):
            raise FlashcardReviewError("Gemini pool review decisions must be objects")
        card_key = _text(raw.get("card_key"))
        if card_key not in expected_keys:
            raise FlashcardReviewError(f"Gemini pool review returned unknown card_key: {card_key}")
        if card_key in seen:
            raise FlashcardReviewError(f"Gemini pool review returned duplicate card_key: {card_key}")
        seen.add(card_key)
        decision = _text(raw.get("decision"))
        winner = _text(raw.get("winner"))
        confidence = _text(raw.get("confidence"))
        if decision not in GEMINI_POOL_DECISION_VALUES:
            raise FlashcardReviewError(f"Invalid Gemini pool review decision for {card_key}: {decision}")
        if winner not in GEMINI_POOL_WINNER_VALUES:
            raise FlashcardReviewError(f"Invalid Gemini pool review winner for {card_key}: {winner}")
        if confidence not in GEMINI_POOL_CONFIDENCE_VALUES:
            raise FlashcardReviewError(f"Invalid Gemini pool review confidence for {card_key}: {confidence}")
        edited_front = _text(raw.get("edited_front"))
        edited_back = _text(raw.get("edited_back"))
        validation_warnings = []
        if decision == "promote_after_edit" and (not edited_front or not edited_back):
            raise FlashcardReviewError(f"Gemini edit recommendation must include edited text: {card_key}")
        if decision != "promote_after_edit" and (edited_front or edited_back):
            validation_warnings.append("discarded_edited_text_for_non_edit_decision")
            edited_front = ""
            edited_back = ""
        if len(edited_front) > MAX_FRONT_CHARS:
            raise FlashcardReviewError(f"Gemini edited front too long: {card_key}")
        if len(edited_back) > MAX_BACK_CHARS:
            raise FlashcardReviewError(f"Gemini edited back too long: {card_key}")
        safety_text = "\n".join(
            [
                edited_front,
                edited_back,
                _text(raw.get("reason")),
                _text(raw.get("added_value")),
                _text(raw.get("implementation_note")),
            ]
        )
        for pattern in LEARNER_TEXT_FORBIDDEN_PATTERNS:
            if pattern.search(safety_text):
                raise FlashcardReviewError(f"Gemini pool review leaks forbidden learner-facing provenance: {card_key}")
        decision_counts[decision] += 1
        decisions.append(
            {
                "card_key": card_key,
                "decision": decision,
                "winner": winner,
                "confidence": confidence,
                "quality_scores": {
                    "coverage": _validate_score(raw.get("coverage_score"), field="coverage_score", card_key=card_key),
                    "exam_usefulness": _validate_score(
                        raw.get("exam_usefulness_score"),
                        field="exam_usefulness_score",
                        card_key=card_key,
                    ),
                    "precision": _validate_score(raw.get("precision_score"), field="precision_score", card_key=card_key),
                    "wording": _validate_score(raw.get("wording_score"), field="wording_score", card_key=card_key),
                    "duplicate_risk": _validate_score(
                        raw.get("duplicate_risk_score"),
                        field="duplicate_risk_score",
                        card_key=card_key,
                    ),
                },
                "reason": _text(raw.get("reason")),
                "added_value": _text(raw.get("added_value")),
                "implementation_note": _text(raw.get("implementation_note")),
                "edited_front": edited_front,
                "edited_back": edited_back,
                "safety_flags": _as_str_list(raw.get("safety_flags")),
                "validation_warnings": validation_warnings,
            }
        )
    missing = expected_keys - seen
    if missing:
        raise FlashcardReviewError("Gemini pool review missing card decisions: " + ", ".join(sorted(missing)[:10]))
    summary = review_payload.get("review_summary") if isinstance(review_payload.get("review_summary"), dict) else {}
    return {
        "version": REVIEW_VERSION,
        "artifact_type": GEMINI_POOL_REVIEW_ARTIFACT_TYPE,
        "subject_slug": SUBJECT_SLUG,
        "review_run_id": _text(bundle.get("review_run_id")),
        "generated_at": generated_at or utc_now_iso(),
        "model": model,
        "prompt_version": GEMINI_POOL_REVIEW_PROMPT_VERSION,
        "input_fingerprints": bundle.get("input_fingerprints"),
        "stats": {
            "candidate_count": len(expected_keys),
            "decision_counts": dict(sorted(decision_counts.items())),
        },
        "review_summary": {
            "overall_assessment": _text(summary.get("overall_assessment")),
            "best_pool": _text(summary.get("best_pool")),
            "main_risks": _as_str_list(summary.get("main_risks")),
            "implementation_priorities": _as_str_list(summary.get("implementation_priorities")),
        },
        "decisions": decisions,
    }


def write_gemini_pool_review_markdown(review_payload: dict[str, Any], output_path: Path) -> None:
    summary = review_payload.get("review_summary") if isinstance(review_payload.get("review_summary"), dict) else {}
    lines = [
        "# Gemini Flashcard Pool Review",
        "",
        f"Review run: `{review_payload.get('review_run_id')}`",
        f"Model: `{review_payload.get('model')}`",
        f"Prompt: `{review_payload.get('prompt_version')}`",
        "",
        f"Summary: {_text(summary.get('overall_assessment'))}",
        "",
        f"Best pool: {_text(summary.get('best_pool'))}",
        "",
        f"Decision counts: {review_payload.get('stats', {}).get('decision_counts')}",
        "",
    ]
    risks = _as_str_list(summary.get("main_risks"))
    if risks:
        lines.extend(["## Main Risks", "", *[f"- {risk}" for risk in risks], ""])
    priorities = _as_str_list(summary.get("implementation_priorities"))
    if priorities:
        lines.extend(["## Implementation Priorities", "", *[f"- {priority}" for priority in priorities], ""])
    lines.extend(["## Decisions", ""])
    for decision in _as_list(review_payload.get("decisions")):
        if not isinstance(decision, dict):
            continue
        scores = decision.get("quality_scores") if isinstance(decision.get("quality_scores"), dict) else {}
        lines.extend(
            [
                f"### `{decision.get('card_key')}`",
                "",
                f"- Decision: `{decision.get('decision')}`",
                f"- Winner: `{decision.get('winner')}`",
                f"- Confidence: `{decision.get('confidence')}`",
                (
                    "- Scores: "
                    f"coverage {scores.get('coverage')}, "
                    f"exam {scores.get('exam_usefulness')}, "
                    f"precision {scores.get('precision')}, "
                    f"wording {scores.get('wording')}, "
                    f"duplicate risk {scores.get('duplicate_risk')}"
                ),
                "",
                f"Reason: {decision.get('reason')}",
                "",
                f"Added value: {decision.get('added_value')}",
                "",
                f"Implementation note: {decision.get('implementation_note')}",
                "",
                f"Safety flags: {', '.join(_as_str_list(decision.get('safety_flags'))) or 'none'}",
                f"Validation warnings: {', '.join(_as_str_list(decision.get('validation_warnings'))) or 'none'}",
                "",
            ]
        )
        if decision.get("decision") == "promote_after_edit":
            lines.extend(
                [
                    "Edited front:",
                    "",
                    _text(decision.get("edited_front")),
                    "",
                    "Edited back:",
                    "",
                    _text(decision.get("edited_back")),
                    "",
                ]
            )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _pool_quality_stats(cards: list[dict[str, Any]]) -> dict[str, Any]:
    by_pool: dict[str, dict[str, Any]] = {}
    for pool in sorted({_text(card.get("source_pool")) for card in cards if _text(card.get("source_pool"))}):
        pool_cards = [card for card in cards if card.get("source_pool") == pool]
        warning_counts = Counter(warning for card in pool_cards for warning in _as_str_list(card.get("warnings")))
        front_lengths = [int(card.get("front_chars") or 0) for card in pool_cards]
        back_lengths = [int(card.get("back_chars") or 0) for card in pool_cards]
        by_pool[pool] = {
            "card_count": len(pool_cards),
            "review_status_counts": dict(sorted(Counter(_text(card.get("review_status")) for card in pool_cards).items())),
            "theory_topic_counts": dict(sorted(Counter(_text(card.get("theory_topic")) for card in pool_cards).items())),
            "review_family_counts": dict(sorted(Counter(_text(card.get("review_family")) for card in pool_cards).items())),
            "warning_counts": dict(sorted(warning_counts.items())),
            "average_front_chars": round(sum(front_lengths) / len(front_lengths), 1) if front_lengths else 0,
            "average_back_chars": round(sum(back_lengths) / len(back_lengths), 1) if back_lengths else 0,
            "unknown_cards": sum(
                1
                for card in pool_cards
                if card.get("theory_topic") == UNKNOWN_TOPIC or card.get("review_family") == UNKNOWN_FAMILY
            ),
        }
    return by_pool


def _sample_pool_cards(cards: list[dict[str, Any]], *, pool: str, limit: int) -> list[dict[str, Any]]:
    pool_cards = [card for card in cards if card.get("source_pool") == pool]
    selected: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    def add(card: dict[str, Any]) -> None:
        key = _text(card.get("card_key"))
        if key and key not in seen_keys and len(selected) < limit:
            selected.append(card)
            seen_keys.add(key)

    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for card in pool_cards:
        groups[(_text(card.get("theory_topic")), _text(card.get("review_family")))].append(card)
    for cell in sorted(groups):
        ranked = sorted(
            groups[cell],
            key=lambda card: (
                _text(card.get("review_status")) == "auto_rejected",
                len(_as_str_list(card.get("warnings"))),
                int(card.get("source_index") or 0),
                _text(card.get("card_key")),
            ),
        )
        if ranked:
            add(ranked[0])
    for card in sorted(
        pool_cards,
        key=lambda card: (
            _text(card.get("theory_topic")),
            _text(card.get("review_family")),
            _text(card.get("review_status")) == "auto_rejected",
            int(card.get("source_index") or 0),
            _text(card.get("card_key")),
        ),
    ):
        add(card)
    return selected


def _quality_card_for_gemini(card: dict[str, Any]) -> dict[str, Any]:
    return {
        "card_key": _text(card.get("card_key")),
        "source_pool": _text(card.get("source_pool")),
        "candidate_id": _text(card.get("candidate_id")),
        "notebook_slug": _text(card.get("notebook_slug")),
        "front": _text(card.get("front")),
        "back": _text(card.get("back")),
        "front_chars": int(card.get("front_chars") or 0),
        "back_chars": int(card.get("back_chars") or 0),
        "category_slug": _text(card.get("category_slug")),
        "matrix_theory_ids": _as_str_list(card.get("matrix_theory_ids")),
        "theory_topic": _text(card.get("theory_topic")),
        "review_family": _text(card.get("review_family")),
        "review_status": _text(card.get("review_status")),
        "warnings": _as_str_list(card.get("warnings")),
    }


def build_gemini_quality_comparison_bundle(
    *,
    comparison_report: dict[str, Any],
    model: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    if comparison_report.get("artifact_type") != REVIEW_ARTIFACT_TYPE:
        raise FlashcardReviewError("Quality comparison requires a flashcard pool comparison report")
    cards = [card for card in _as_list(comparison_report.get("cards")) if isinstance(card, dict)]
    if not cards:
        raise FlashcardReviewError("Quality comparison needs normalized cards in the comparison report")
    pool_stats = _pool_quality_stats(cards)
    missing_pools = [pool for pool in QUALITY_COMPARISON_POOLS if pool not in pool_stats]
    if missing_pools:
        raise FlashcardReviewError("Quality comparison missing source pools: " + ", ".join(missing_pools))
    sample_cards: list[dict[str, Any]] = []
    sample_counts: dict[str, int] = {}
    for pool in QUALITY_COMPARISON_POOLS:
        limit = QUALITY_SAMPLE_TARGETS[pool]
        selected = _sample_pool_cards(cards, pool=pool, limit=limit)
        sample_counts[pool] = len(selected)
        sample_cards.extend(selected)
    coverage = comparison_report.get("coverage") if isinstance(comparison_report.get("coverage"), dict) else {}
    stats = comparison_report.get("stats") if isinstance(comparison_report.get("stats"), dict) else {}
    return {
        "version": REVIEW_VERSION,
        "artifact_type": GEMINI_QUALITY_COMPARISON_BUNDLE_ARTIFACT_TYPE,
        "subject_slug": SUBJECT_SLUG,
        "review_run_id": _text(comparison_report.get("review_run_id")),
        "generated_at": generated_at or utc_now_iso(),
        "model": model,
        "prompt_version": GEMINI_QUALITY_COMPARISON_PROMPT_VERSION,
        "input_fingerprints": {
            "comparison_report": hashlib.sha256(
                json.dumps(comparison_report, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest(),
        },
        "review_contract": {
            "task": "Compare flashcard pools as learning material in their own right, not as promotion candidates.",
            "critical_boundary": (
                "Do not evaluate novelty relative to other pools. Judge each card and pool by its own learning "
                "quality, and allow broad matrix restatements when they are clear and accurate."
            ),
            "quality_dimensions": [
                "matrix fidelity",
                "course coverage",
                "oral-exam usefulness",
                "psychological precision",
                "Danish wording clarity",
                "atomic retrieval shape",
                "overall learning value",
            ],
            "allowed_strengths": [
                "clear broad restatement of a matrix row",
                "simple rehearsal cue for a central theory point",
                "standalone card that supports course coverage without needing to be novel",
            ],
            "penalize_only": [
                "incorrect or unsupported claims",
                "vague or buzzword-heavy wording",
                "too sprawling or non-atomic cards",
                "bad Danish or question-answer mismatch",
                "weak oral-exam usefulness",
                "unsafe leakage of student names, local paths, internal IDs, or hidden provenance",
            ],
        },
        "pool_context": {
            "source_counts": {
                pool: (stats.get("source_counts") or {}).get(pool, 0)
                for pool in QUALITY_COMPARISON_POOLS
            }
            if isinstance(stats.get("source_counts"), dict)
            else {},
            "pool_quality_stats": {pool: pool_stats[pool] for pool in QUALITY_COMPARISON_POOLS},
            "coverage_unknown_counts": coverage.get("unknown_counts") if isinstance(coverage.get("unknown_counts"), dict) else {},
            "missing_cells": _as_list(coverage.get("missing_cells"))[:80],
            "overcrowded_cells": _as_list(coverage.get("overcrowded_cells"))[:80],
            "sample_counts": sample_counts,
        },
        "sample_cards": [_quality_card_for_gemini(card) for card in sample_cards],
    }


def gemini_quality_comparison_system_instruction() -> str:
    return "\n".join(
        [
            "You are a strict Danish university psychology flashcard quality reviewer.",
            "Return only valid JSON matching the requested schema.",
            "Evaluate flashcard pools as learning material in their own right.",
            "Do not evaluate novelty relative to other pools; judge the supplied card text on its own learning quality.",
            "Do not mention overlap, redundancy, duplicates, or whether a card adds something new.",
            "Reward matrix-faithful, clear, useful rehearsal cards even when they cover already-known material.",
            "Penalize only weak fidelity, weak precision, unclear Danish, poor card shape, unsafe text, or low exam usefulness.",
        ]
    )


def gemini_quality_comparison_user_prompt(bundle: dict[str, Any]) -> str:
    return "\n".join(
        [
            "Compare these flashcard pools for independent learning quality.",
            "",
            "Important: this is not a promotion or novelty review. Do not try to infer whether a card is new relative to another pool.",
            "Do not use or mention overlap, redundancy, duplicate status, novelty, or 'adds something new' as a criterion.",
            "Broad restatements of the matrix are allowed when they are accurate, clear, and useful for rehearsal.",
            "",
            "Return one pool assessment for every source_pool and one card observation for every sampled card_key.",
            "For the supplied sample_cards, card_observations must contain every card_key exactly once.",
            "Do not summarize the cards and do not choose examples; review every supplied card.",
            "Use Danish for all explanations. Keep per-card reasons extremely short so every supplied card can fit.",
            "If output limits force prioritization, preserve the pool assessments and return as many card observations as feasible.",
            "",
            "Input bundle:",
            "",
            json.dumps(bundle, ensure_ascii=False, sort_keys=True, indent=2),
        ]
    )


def gemini_quality_comparison_response_schema() -> dict[str, Any]:
    score_property = {"type": "integer"}
    return {
        "type": "object",
        "properties": {
            "review_summary": {
                "type": "object",
                "properties": {
                    "overall_assessment": {"type": "string"},
                    "best_overall_pool": {"type": "string"},
                    "best_for_matrix_rehearsal": {"type": "string"},
                    "best_for_exam_preparation": {"type": "string"},
                    "main_risks": {"type": "array", "items": {"type": "string"}},
                    "recommended_next_action": {"type": "string"},
                },
                "required": [
                    "overall_assessment",
                    "best_overall_pool",
                    "best_for_matrix_rehearsal",
                    "best_for_exam_preparation",
                    "main_risks",
                    "recommended_next_action",
                ],
            },
            "pool_assessments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_pool": {"type": "string"},
                        "coverage_score": score_property,
                        "matrix_fidelity_score": score_property,
                        "exam_usefulness_score": score_property,
                        "precision_score": score_property,
                        "wording_score": score_property,
                        "atomicity_score": score_property,
                        "learning_value_score": score_property,
                        "recommended_visibility": {"type": "string", "enum": sorted(GEMINI_VISIBILITY_VALUES)},
                        "strengths": {"type": "array", "items": {"type": "string"}},
                        "weaknesses": {"type": "array", "items": {"type": "string"}},
                        "best_use_case": {"type": "string"},
                    },
                    "required": [
                        "source_pool",
                        "coverage_score",
                        "matrix_fidelity_score",
                        "exam_usefulness_score",
                        "precision_score",
                        "wording_score",
                        "atomicity_score",
                        "learning_value_score",
                        "recommended_visibility",
                        "strengths",
                        "weaknesses",
                        "best_use_case",
                    ],
                },
            },
            "card_observations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "card_key": {"type": "string"},
                        "quality_verdict": {"type": "string", "enum": sorted(GEMINI_QUALITY_VERDICT_VALUES)},
                        "matrix_fidelity_score": score_property,
                        "exam_usefulness_score": score_property,
                        "precision_score": score_property,
                        "wording_score": score_property,
                        "atomicity_score": score_property,
                        "learning_value_score": score_property,
                        "reason": {"type": "string"},
                        "edit_needed": {"type": "boolean"},
                        "safety_flags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "card_key",
                        "quality_verdict",
                        "matrix_fidelity_score",
                        "exam_usefulness_score",
                        "precision_score",
                        "wording_score",
                        "atomicity_score",
                        "learning_value_score",
                        "reason",
                        "edit_needed",
                        "safety_flags",
                    ],
                },
            },
            "comparison_conclusion": {
                "type": "object",
                "properties": {
                    "original_cards_assessment": {"type": "string"},
                    "newest_notebooklm_assessment": {"type": "string"},
                    "variant_decks_assessment": {"type": "string"},
                    "freudd_visibility_recommendation": {"type": "string"},
                },
                "required": [
                    "original_cards_assessment",
                    "newest_notebooklm_assessment",
                    "variant_decks_assessment",
                    "freudd_visibility_recommendation",
                ],
            },
        },
        "required": ["review_summary", "pool_assessments", "card_observations", "comparison_conclusion"],
    }


def gemini_quality_observation_system_instruction() -> str:
    return "\n".join(
        [
            "You are a strict Danish university psychology flashcard quality reviewer.",
            "Return only valid JSON matching the requested schema.",
            "Review every supplied card_key exactly once.",
            "Do not compare against other decks. Do not mention overlap, redundancy, duplicates, or novelty.",
            "Judge only matrix fidelity, exam usefulness, precision, wording, atomicity, and learning value.",
        ]
    )


def gemini_quality_observation_user_prompt(bundle: dict[str, Any]) -> str:
    return "\n".join(
        [
            "Review every flashcard in sample_cards.",
            "Return card_observations with exactly every supplied card_key once.",
            "Use Danish. Keep reason to at most 12 words.",
            "Scores are integers 1-5.",
            "",
            "Input bundle:",
            "",
            json.dumps(
                {
                    "review_contract": bundle.get("review_contract"),
                    "batch": bundle.get("batch"),
                    "sample_cards": bundle.get("sample_cards"),
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            ),
        ]
    )


def gemini_quality_observation_response_schema() -> dict[str, Any]:
    score_property = {"type": "integer"}
    return {
        "type": "object",
        "properties": {
            "card_observations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "card_key": {"type": "string"},
                        "quality_verdict": {"type": "string", "enum": sorted(GEMINI_QUALITY_VERDICT_VALUES)},
                        "matrix_fidelity_score": score_property,
                        "exam_usefulness_score": score_property,
                        "precision_score": score_property,
                        "wording_score": score_property,
                        "atomicity_score": score_property,
                        "learning_value_score": score_property,
                        "reason": {"type": "string"},
                        "edit_needed": {"type": "boolean"},
                        "safety_flags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "card_key",
                        "quality_verdict",
                        "matrix_fidelity_score",
                        "exam_usefulness_score",
                        "precision_score",
                        "wording_score",
                        "atomicity_score",
                        "learning_value_score",
                        "reason",
                        "edit_needed",
                        "safety_flags",
                    ],
                },
            },
        },
        "required": ["card_observations"],
    }


def validate_gemini_quality_observations(
    review_payload: dict[str, Any],
    *,
    bundle: dict[str, Any],
) -> dict[str, Any]:
    raw_observations = review_payload.get("card_observations")
    if not isinstance(raw_observations, list):
        raise FlashcardReviewError("Gemini quality observations payload must contain card_observations list")
    sample_cards = [item for item in _as_list(bundle.get("sample_cards")) if isinstance(item, dict)]
    expected_keys = {_text(item.get("card_key")) for item in sample_cards if _text(item.get("card_key"))}
    observations: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    verdict_counts: Counter[str] = Counter()
    for raw in raw_observations:
        if not isinstance(raw, dict):
            raise FlashcardReviewError("Gemini quality observations must be objects")
        card_key = _text(raw.get("card_key"))
        if card_key not in expected_keys:
            raise FlashcardReviewError(f"Gemini quality observations returned unknown card_key: {card_key}")
        if card_key in seen_keys:
            raise FlashcardReviewError(f"Gemini quality observations returned duplicate card_key: {card_key}")
        seen_keys.add(card_key)
        verdict = _text(raw.get("quality_verdict"))
        if verdict not in GEMINI_QUALITY_VERDICT_VALUES:
            raise FlashcardReviewError(f"Invalid quality verdict for {card_key}: {verdict}")
        safety_text = "\n".join([_text(raw.get("reason")), " ".join(_as_str_list(raw.get("safety_flags")))])
        for pattern in LEARNER_TEXT_FORBIDDEN_PATTERNS:
            if pattern.search(safety_text):
                raise FlashcardReviewError(f"Gemini quality observations leak forbidden provenance: {card_key}")
        verdict_counts[verdict] += 1
        observations.append(
            {
                "card_key": card_key,
                "quality_verdict": verdict,
                "scores": {
                    "matrix_fidelity": _validate_score(
                        raw.get("matrix_fidelity_score"),
                        field="matrix_fidelity_score",
                        card_key=card_key,
                    ),
                    "exam_usefulness": _validate_score(
                        raw.get("exam_usefulness_score"),
                        field="exam_usefulness_score",
                        card_key=card_key,
                    ),
                    "precision": _validate_score(raw.get("precision_score"), field="precision_score", card_key=card_key),
                    "wording": _validate_score(raw.get("wording_score"), field="wording_score", card_key=card_key),
                    "atomicity": _validate_score(raw.get("atomicity_score"), field="atomicity_score", card_key=card_key),
                    "learning_value": _validate_score(
                        raw.get("learning_value_score"),
                        field="learning_value_score",
                        card_key=card_key,
                    ),
                },
                "reason": _text(raw.get("reason")),
                "edit_needed": bool(raw.get("edit_needed")),
                "safety_flags": _as_str_list(raw.get("safety_flags")),
            }
        )
    missing_keys = expected_keys - seen_keys
    if not observations:
        raise FlashcardReviewError("Gemini quality observations returned no card observations")
    return {
        "card_observations": observations,
        "stats": {
            "sample_card_count": len(expected_keys),
            "observed_sample_card_count": len(seen_keys),
            "missing_sample_card_count": len(missing_keys),
            "quality_verdict_counts": dict(sorted(verdict_counts.items())),
        },
        "validation_warnings": (
            ["partial_card_observations_due_to_model_output_limit"] if missing_keys else []
        ),
        "missing_card_keys": sorted(missing_keys),
    }


def validate_gemini_quality_comparison(
    review_payload: dict[str, Any],
    *,
    bundle: dict[str, Any],
    model: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    sample_cards = [item for item in _as_list(bundle.get("sample_cards")) if isinstance(item, dict)]
    expected_pools = {
        _text(item.get("source_pool"))
        for item in sample_cards
        if _text(item.get("source_pool"))
    } or set(QUALITY_COMPARISON_POOLS)
    raw_pools = review_payload.get("pool_assessments")
    if not isinstance(raw_pools, list):
        raise FlashcardReviewError("Gemini quality comparison payload must contain pool_assessments list")
    pool_assessments: list[dict[str, Any]] = []
    seen_pools: set[str] = set()
    for raw in raw_pools:
        if not isinstance(raw, dict):
            raise FlashcardReviewError("Gemini quality comparison pool assessments must be objects")
        pool = _text(raw.get("source_pool"))
        if pool not in expected_pools:
            raise FlashcardReviewError(f"Gemini quality comparison returned unknown source_pool: {pool}")
        if pool in seen_pools:
            raise FlashcardReviewError(f"Gemini quality comparison returned duplicate source_pool: {pool}")
        seen_pools.add(pool)
        visibility = _text(raw.get("recommended_visibility"))
        if visibility not in GEMINI_VISIBILITY_VALUES:
            raise FlashcardReviewError(f"Invalid quality comparison visibility for {pool}: {visibility}")
        pool_assessments.append(
            {
                "source_pool": pool,
                "scores": {
                    "coverage": _validate_score(raw.get("coverage_score"), field="coverage_score", card_key=pool),
                    "matrix_fidelity": _validate_score(
                        raw.get("matrix_fidelity_score"),
                        field="matrix_fidelity_score",
                        card_key=pool,
                    ),
                    "exam_usefulness": _validate_score(
                        raw.get("exam_usefulness_score"),
                        field="exam_usefulness_score",
                        card_key=pool,
                    ),
                    "precision": _validate_score(raw.get("precision_score"), field="precision_score", card_key=pool),
                    "wording": _validate_score(raw.get("wording_score"), field="wording_score", card_key=pool),
                    "atomicity": _validate_score(raw.get("atomicity_score"), field="atomicity_score", card_key=pool),
                    "learning_value": _validate_score(
                        raw.get("learning_value_score"),
                        field="learning_value_score",
                        card_key=pool,
                    ),
                },
                "recommended_visibility": visibility,
                "strengths": _as_str_list(raw.get("strengths")),
                "weaknesses": _as_str_list(raw.get("weaknesses")),
                "best_use_case": _text(raw.get("best_use_case")),
            }
        )
    missing_pools = expected_pools - seen_pools
    if missing_pools:
        raise FlashcardReviewError("Gemini quality comparison missing pool assessments: " + ", ".join(sorted(missing_pools)))

    raw_observations = review_payload.get("card_observations")
    if not isinstance(raw_observations, list):
        raise FlashcardReviewError("Gemini quality comparison payload must contain card_observations list")
    expected_keys = {
        _text(item.get("card_key"))
        for item in sample_cards
        if _text(item.get("card_key"))
    }
    observations: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    verdict_counts: Counter[str] = Counter()
    for raw in raw_observations:
        if not isinstance(raw, dict):
            raise FlashcardReviewError("Gemini quality comparison card observations must be objects")
        card_key = _text(raw.get("card_key"))
        if card_key not in expected_keys:
            raise FlashcardReviewError(f"Gemini quality comparison returned unknown card_key: {card_key}")
        if card_key in seen_keys:
            raise FlashcardReviewError(f"Gemini quality comparison returned duplicate card_key: {card_key}")
        seen_keys.add(card_key)
        verdict = _text(raw.get("quality_verdict"))
        if verdict not in GEMINI_QUALITY_VERDICT_VALUES:
            raise FlashcardReviewError(f"Invalid quality verdict for {card_key}: {verdict}")
        safety_text = "\n".join([_text(raw.get("reason")), " ".join(_as_str_list(raw.get("safety_flags")))])
        for pattern in LEARNER_TEXT_FORBIDDEN_PATTERNS:
            if pattern.search(safety_text):
                raise FlashcardReviewError(f"Gemini quality comparison leaks forbidden provenance: {card_key}")
        verdict_counts[verdict] += 1
        observations.append(
            {
                "card_key": card_key,
                "quality_verdict": verdict,
                "scores": {
                    "matrix_fidelity": _validate_score(
                        raw.get("matrix_fidelity_score"),
                        field="matrix_fidelity_score",
                        card_key=card_key,
                    ),
                    "exam_usefulness": _validate_score(
                        raw.get("exam_usefulness_score"),
                        field="exam_usefulness_score",
                        card_key=card_key,
                    ),
                    "precision": _validate_score(raw.get("precision_score"), field="precision_score", card_key=card_key),
                    "wording": _validate_score(raw.get("wording_score"), field="wording_score", card_key=card_key),
                    "atomicity": _validate_score(raw.get("atomicity_score"), field="atomicity_score", card_key=card_key),
                    "learning_value": _validate_score(
                        raw.get("learning_value_score"),
                        field="learning_value_score",
                        card_key=card_key,
                    ),
                },
                "reason": _text(raw.get("reason")),
                "edit_needed": bool(raw.get("edit_needed")),
                "safety_flags": _as_str_list(raw.get("safety_flags")),
            }
        )
    missing_keys = expected_keys - seen_keys
    if not observations:
        raise FlashcardReviewError("Gemini quality comparison returned no card observations")
    summary = review_payload.get("review_summary") if isinstance(review_payload.get("review_summary"), dict) else {}
    conclusion = (
        review_payload.get("comparison_conclusion")
        if isinstance(review_payload.get("comparison_conclusion"), dict)
        else {}
    )
    return {
        "version": REVIEW_VERSION,
        "artifact_type": GEMINI_QUALITY_COMPARISON_ARTIFACT_TYPE,
        "subject_slug": SUBJECT_SLUG,
        "review_run_id": _text(bundle.get("review_run_id")),
        "generated_at": generated_at or utc_now_iso(),
        "model": model,
        "prompt_version": GEMINI_QUALITY_COMPARISON_PROMPT_VERSION,
        "input_fingerprints": bundle.get("input_fingerprints"),
        "stats": {
            "sample_card_count": len(expected_keys),
            "observed_sample_card_count": len(seen_keys),
            "missing_sample_card_count": len(missing_keys),
            "pool_count": len(expected_pools),
            "quality_verdict_counts": dict(sorted(verdict_counts.items())),
        },
        "validation_warnings": (
            [
                "partial_card_observations_due_to_model_output_limit",
            ]
            if missing_keys
            else []
        ),
        "missing_card_keys": sorted(missing_keys),
        "review_summary": {
            "overall_assessment": _text(summary.get("overall_assessment")),
            "best_overall_pool": _text(summary.get("best_overall_pool")),
            "best_for_matrix_rehearsal": _text(summary.get("best_for_matrix_rehearsal")),
            "best_for_exam_preparation": _text(summary.get("best_for_exam_preparation")),
            "main_risks": _as_str_list(summary.get("main_risks")),
            "recommended_next_action": _text(summary.get("recommended_next_action")),
        },
        "pool_assessments": pool_assessments,
        "card_observations": observations,
        "comparison_conclusion": {
            "original_cards_assessment": _text(conclusion.get("original_cards_assessment")),
            "newest_notebooklm_assessment": _text(conclusion.get("newest_notebooklm_assessment")),
            "variant_decks_assessment": _text(conclusion.get("variant_decks_assessment")),
            "freudd_visibility_recommendation": _text(conclusion.get("freudd_visibility_recommendation")),
        },
    }


def write_gemini_quality_comparison_markdown(review_payload: dict[str, Any], output_path: Path) -> None:
    summary = review_payload.get("review_summary") if isinstance(review_payload.get("review_summary"), dict) else {}
    conclusion = (
        review_payload.get("comparison_conclusion")
        if isinstance(review_payload.get("comparison_conclusion"), dict)
        else {}
    )
    lines = [
        "# Gemini Flashcard Quality Comparison",
        "",
        f"Review run: `{review_payload.get('review_run_id')}`",
        f"Model: `{review_payload.get('model')}`",
        f"Prompt: `{review_payload.get('prompt_version')}`",
        "",
        "## Summary",
        "",
        f"Overall: {_text(summary.get('overall_assessment'))}",
        "",
        f"- Best overall pool: `{_text(summary.get('best_overall_pool'))}`",
        f"- Best for matrix rehearsal: `{_text(summary.get('best_for_matrix_rehearsal'))}`",
        f"- Best for exam preparation: `{_text(summary.get('best_for_exam_preparation'))}`",
        f"- Recommended next action: {_text(summary.get('recommended_next_action'))}",
        "",
        f"Quality verdict counts: {review_payload.get('stats', {}).get('quality_verdict_counts')}",
        f"Observed sampled cards: {review_payload.get('stats', {}).get('observed_sample_card_count')} / {review_payload.get('stats', {}).get('sample_card_count')}",
        "",
    ]
    warnings = _as_str_list(review_payload.get("validation_warnings"))
    if warnings:
        lines.extend(["Validation warnings:", "", *[f"- {warning}" for warning in warnings], ""])
    risks = _as_str_list(summary.get("main_risks"))
    if risks:
        lines.extend(["## Main Risks", "", *[f"- {risk}" for risk in risks], ""])
    lines.extend(
        [
            "## Comparison Conclusion",
            "",
            f"- Original cards: {_text(conclusion.get('original_cards_assessment'))}",
            f"- Newest NotebookLM: {_text(conclusion.get('newest_notebooklm_assessment'))}",
            f"- Variant decks: {_text(conclusion.get('variant_decks_assessment'))}",
            f"- Freudd visibility: {_text(conclusion.get('freudd_visibility_recommendation'))}",
            "",
            "## Pool Assessments",
            "",
        ]
    )
    for pool in _as_list(review_payload.get("pool_assessments")):
        if not isinstance(pool, dict):
            continue
        scores = pool.get("scores") if isinstance(pool.get("scores"), dict) else {}
        lines.extend(
            [
                f"### `{pool.get('source_pool')}`",
                "",
                (
                    "- Scores: "
                    f"coverage {scores.get('coverage')}, "
                    f"fidelity {scores.get('matrix_fidelity')}, "
                    f"exam {scores.get('exam_usefulness')}, "
                    f"precision {scores.get('precision')}, "
                    f"wording {scores.get('wording')}, "
                    f"atomicity {scores.get('atomicity')}, "
                    f"learning value {scores.get('learning_value')}"
                ),
                f"- Recommended visibility: `{pool.get('recommended_visibility')}`",
                f"- Best use case: {pool.get('best_use_case')}",
                "",
                "Strengths:",
                "",
                *[f"- {item}" for item in _as_str_list(pool.get("strengths"))],
                "",
                "Weaknesses:",
                "",
                *[f"- {item}" for item in _as_str_list(pool.get("weaknesses"))],
                "",
            ]
        )
    lines.extend(["## Card Observations", ""])
    for observation in _as_list(review_payload.get("card_observations")):
        if not isinstance(observation, dict):
            continue
        scores = observation.get("scores") if isinstance(observation.get("scores"), dict) else {}
        lines.extend(
            [
                f"### `{observation.get('card_key')}`",
                "",
                f"- Verdict: `{observation.get('quality_verdict')}`",
                (
                    "- Scores: "
                    f"fidelity {scores.get('matrix_fidelity')}, "
                    f"exam {scores.get('exam_usefulness')}, "
                    f"precision {scores.get('precision')}, "
                    f"wording {scores.get('wording')}, "
                    f"atomicity {scores.get('atomicity')}, "
                    f"learning value {scores.get('learning_value')}"
                ),
                f"- Edit needed: {observation.get('edit_needed')}",
                f"- Safety flags: {', '.join(_as_str_list(observation.get('safety_flags'))) or 'none'}",
                "",
                f"Reason: {observation.get('reason')}",
                "",
            ]
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_comparison_report(report: dict[str, Any], *, output_json: Path, output_markdown: Path) -> None:
    write_json_stably(output_json, report)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.write_text(render_markdown_report(report), encoding="utf-8")


def render_markdown_report(report: dict[str, Any]) -> str:
    stats = report.get("stats") if isinstance(report.get("stats"), dict) else {}
    coverage = report.get("coverage") if isinstance(report.get("coverage"), dict) else {}
    stop_gates = report.get("stop_gates") if isinstance(report.get("stop_gates"), dict) else {}
    lines = [
        "# Flashcard Pool Comparison",
        "",
        f"Review run: `{report.get('review_run_id')}`",
        "",
        "## Executive Summary",
        "",
        f"- Total normalized cards: {stats.get('card_count', 0)}",
        f"- Full-run NotebookLM candidates: {stats.get('candidate_count', 0)}",
        f"- Unknown non-auto-rejected rate: {stop_gates.get('unknown_rate', 0)}",
        f"- Gemini blocked by unknown rate: {stop_gates.get('unknown_rate_blocks_gemini')}",
        f"- Shortlist size: {len(_as_list(report.get('shortlist')))}",
        "",
        "## Recommendations",
        "",
    ]
    lines.extend(f"- {item}" for item in _as_str_list(report.get("recommendations")))
    lines.extend(["", "## Pool Counts", ""])
    for key, value in (stats.get("source_counts") or {}).items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Coverage Grid", ""])
    grid = coverage.get("grid") if isinstance(coverage.get("grid"), dict) else {}
    header = "| Theory topic | " + " | ".join(REVIEW_FAMILIES) + " |"
    separator = "|---" * (len(REVIEW_FAMILIES) + 1) + "|"
    lines.extend([header, separator])
    for topic in THEORY_TOPICS:
        families = grid.get(topic, {}) if isinstance(grid.get(topic), dict) else {}
        cells = []
        for family in REVIEW_FAMILIES:
            counts = families.get(family, {}) if isinstance(families.get(family), dict) else {}
            cells.append(f"{counts.get('committed', 0)}/{counts.get('candidates', 0)}")
        lines.append(f"| `{topic}` | " + " | ".join(cells) + " |")
    lines.extend(["", "Cell format: `committed/candidate`.", ""])
    lines.extend(["## Missing Cells", ""])
    for item in _as_list(coverage.get("missing_cells"))[:80]:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"- `{item.get('theory_topic')}` x `{item.get('review_family')}`: "
            f"{item.get('total', 0)}/{item.get('target', 0)} total"
        )
    lines.extend(["", "## Overcrowded Cells", ""])
    for item in _as_list(coverage.get("overcrowded_cells"))[:80]:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"- `{item.get('theory_topic')}` x `{item.get('review_family')}`: "
            f"{item.get('total', 0)} total ({item.get('committed', 0)} committed, {item.get('candidates', 0)} candidates)"
        )
    lines.extend(["", "## Duplicate Summary", ""])
    for key, value in (stats.get("duplicate_kind_counts") or {}).items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Candidate Shortlist", ""])
    for item in _as_list(report.get("shortlist"))[:MAX_SHORTLIST]:
        if not isinstance(item, dict):
            continue
        duplicate = item.get("duplicate") if isinstance(item.get("duplicate"), dict) else {}
        lines.extend(
            [
                f"### `{item.get('card_key')}`",
                "",
                f"- Topic: `{item.get('theory_topic')}`",
                f"- Family: `{item.get('review_family')}`",
                f"- Duplicate: `{duplicate.get('kind')}` score `{duplicate.get('score')}`",
                f"- Reasons: {', '.join(_as_str_list(item.get('selection_reasons')))}",
                "",
                f"Front: {item.get('front')}",
                "",
                f"Back: {item.get('back')}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"
