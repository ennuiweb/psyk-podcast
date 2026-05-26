"""NotebookLM flashcard-candidate lab for personlighedspsykologi.

This module deliberately keeps NotebookLM output out of the canonical Freudd
deck. NotebookLM can propose alternative cards; repo-owned validation and human
review decide whether any candidates become learner-facing cards later.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from notebooklm_queue.json_artifact_utils import render_json, semantic_fingerprint, write_json_stably
from notebooklm_queue.gemini_preprocessing import DEFAULT_GEMINI_PREPROCESSING_MODEL
from notebooklm_queue.personlighedspsykologi_matrix_flashcards import (
    CATEGORIES,
    LEARNER_TEXT_FORBIDDEN_PATTERNS,
    MatrixFlashcardBuildError,
    load_matrix,
    validate_flashcard_artifact,
)

LAB_VERSION = 1
SUBJECT_SLUG = "personlighedspsykologi"
DEFAULT_LAB_ROOT = Path("notebooklm-podcast-auto/personlighedspsykologi/flashcard_lab")
DEFAULT_MATRIX_PATH = Path("shows/personlighedspsykologi-en/student_synthesis/exam_theory_matrix.json")
DEFAULT_DECK_PATH = Path(
    "shows/personlighedspsykologi-en/flashcards/archive/retired-live-decks-2026-05-26/"
    "eksamensmatrix-personlighedspsykologi.json"
)
DEFAULT_RUN_ID_PREFIX = "matrix-flashcards"
PILOT_NOTEBOOK_SLUG = "critical-sociocultural-narrative"
DEFAULT_GEMINI_FLASHCARD_REVIEW_MODEL = DEFAULT_GEMINI_PREPROCESSING_MODEL
GEMINI_FLASHCARD_REVIEW_PROMPT_VERSION = "personlighedspsykologi-gemini-flashcard-review-v1"
GEMINI_FLASHCARD_REVIEW_ARTIFACT_TYPE = "personlighedspsykologi_gemini_flashcard_review"

MAX_FRONT_CHARS = 280
MAX_BACK_CHARS = 1200
DUPLICATE_REVIEW_THRESHOLD = 0.72
DUPLICATE_REJECT_THRESHOLD = 0.9
MANUAL_CARD_OVERLAP_REVIEW_THRESHOLD = 0.42

CATEGORY_KEYWORDS = {
    "orienteringspunkter": (
        "essens",
        "kontekst",
        "determination",
        "agency",
        "agens",
        "historicitet",
        "ontogen",
        "sociogen",
        "fylogen",
    ),
    "personbegreb": ("personbegreb", "person", "subjekt", "subjektivitet", "selv", "personlighed"),
    "metode-og-evidens": ("metode", "evidens", "empiri", "data", "forskning", "analyse", "måling"),
    "styrker-og-begraensninger": (
        "styrke",
        "begrænsning",
        "synlig",
        "skjule",
        "kritik",
        "mulighed",
        "risiko",
    ),
    "sammenligninger": ("sammenlign", "kontrast", "adskiller", "forskel", "kritiser", "versus"),
    "eksamenstraps": ("trap", "misforstå", "for simpelt", "reducere", "undgå", "faldgrube"),
}

VAGUE_FRONT_PATTERNS = (
    re.compile(r"^hvad er [^?]{0,80}\?$", re.IGNORECASE),
    re.compile(r"^defin[ée]r [^?]{0,80}\.?$", re.IGNORECASE),
    re.compile(r"^what is [^?]{0,80}\?$", re.IGNORECASE),
)

THEORY_KEYWORDS = {
    "critical_personalism": (
        "kritisk personalisme",
        "critical personalism",
        "personkritik",
        "personalisme",
        "lamiell",
    ),
    "critical_psychology": (
        "kritisk psykologi",
        "critical psychology",
        "holzkamp",
        "dreier",
        "handleevne",
        "livsbetingelse",
        "livsbetingelser",
        "daglig livsførelse",
        "ekspansiv",
        "restriktiv",
    ),
    "sociocultural_poststructural_approaches": (
        "poststrukturalisme",
        "poststrukturalistisk",
        "poststrukturalistiske",
        "postpsykologi",
        "postpsykologisk",
        "sociokulturel",
        "sociokulturelle",
        "socialkonstruktion",
        "socialkonstruktionisme",
        "socialkonstruktivisme",
        "diskurs",
        "diskursive",
        "subjektposition",
        "subjektpositioner",
        "subjektivering",
        "genealogi",
        "genealogisk",
        "anti-essentialisme",
        "looping effect",
        "hacking",
        "magt",
        "foucault",
        "davies",
        "gergen",
    ),
    "narrative_psychology": (
        "narrativ",
        "narrative",
        "fortælling",
        "fortællinger",
        "livshistorie",
        "selvnarrativ",
        "mcadams",
        "bruner",
        "raggatt",
    ),
    "humanistic_psychology": ("humanistisk", "humanistiske", "maslow", "rogers", "selvrealisering"),
    "existential_psychology": ("eksistentiel", "existential", "may", "boss", "ansvar", "valg"),
    "phenomenological_psychology": ("fænomenologi", "fænomenologisk", "giorgi", "oplevelse"),
    "psychoanalytic_personality_theory": ("psykoanalyse", "psykoanalytisk", "freud", "lacan", "laplanche"),
    "trait_and_assessment_psychology": (
        "trækteori",
        "trækpsykologi",
        "big five",
        "personlighedstræk",
        "personlighedstest",
    ),
    "personality_functioning_and_pathology": ("personlighedsforstyrrelse", "patologi", "personlighedsfunktion"),
}


class FlashcardLabError(ValueError):
    """Raised when the NotebookLM flashcard lab cannot safely proceed."""


@dataclass(frozen=True)
class NotebookSpec:
    slug: str
    title: str
    theory_ids: tuple[str, ...]
    purpose: str
    include_all_rows_digest: bool = False
    comparison_workshop: bool = False


NOTEBOOK_SPECS: tuple[NotebookSpec, ...] = (
    NotebookSpec(
        slug="global-calibration-synthesis",
        title="Freudd personlighedspsykologi flashcard lab - global calibration",
        theory_ids=(
            "trait_and_assessment_psychology",
            "dynamic_personality_development",
            "biosocial_personality_perspectives",
            "personality_functioning_and_pathology",
            "psychoanalytic_personality_theory",
            "phenomenological_psychology",
            "existential_psychology",
            "humanistic_psychology",
            "critical_personalism",
            "critical_psychology",
            "sociocultural_poststructural_approaches",
            "narrative_psychology",
            "comparative_theory_analysis",
        ),
        purpose="Calibrate style and generate course-wide comparison cards.",
        include_all_rows_digest=True,
    ),
    NotebookSpec(
        slug="measurement-development-pathology",
        title="Freudd personlighedspsykologi flashcard lab - measurement development pathology",
        theory_ids=(
            "trait_and_assessment_psychology",
            "dynamic_personality_development",
            "biosocial_personality_perspectives",
            "personality_functioning_and_pathology",
        ),
        purpose="Alternative cards for measurement, development, biology, and pathology rows.",
    ),
    NotebookSpec(
        slug="psychoanalysis-experience-humanism",
        title="Freudd personlighedspsykologi flashcard lab - psychoanalysis experience humanism",
        theory_ids=(
            "psychoanalytic_personality_theory",
            "phenomenological_psychology",
            "existential_psychology",
            "humanistic_psychology",
        ),
        purpose="Alternative cards for psychoanalysis, experience, existence, and humanism.",
    ),
    NotebookSpec(
        slug=PILOT_NOTEBOOK_SLUG,
        title="Freudd personlighedspsykologi flashcard lab - critical sociocultural narrative",
        theory_ids=(
            "critical_personalism",
            "critical_psychology",
            "sociocultural_poststructural_approaches",
            "narrative_psychology",
        ),
        purpose="Pilot cluster for critical, sociocultural, poststructural, and narrative comparison cards.",
    ),
    NotebookSpec(
        slug="oral-exam-comparison-workshop",
        title="Freudd personlighedspsykologi flashcard lab - oral exam comparison workshop",
        theory_ids=("comparative_theory_analysis",),
        purpose="Generate oral-exam comparison and exam-trap candidates across the whole course.",
        include_all_rows_digest=True,
        comparison_workshop=True,
    ),
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_run_id(now: str | None = None) -> str:
    stamp = (now or utc_now_iso()).replace("-", "").replace(":", "").replace("Z", "Z").replace("T", "-")
    return f"{DEFAULT_RUN_ID_PREFIX}-{stamp}"


def _as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_str_list(value: object) -> list[str]:
    return [str(item).strip() for item in _as_list(value) if str(item).strip()]


def _text(value: object) -> str:
    return str(value or "").strip()


def _slug(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().casefold()).strip("-") or "x"


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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
        raise FlashcardLabError(f"Unable to read JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise FlashcardLabError(f"JSON root must be an object: {path}")
    return payload


def load_current_deck(path: Path, matrix: dict[str, Any]) -> dict[str, Any]:
    payload = _load_json(path)
    try:
        validate_flashcard_artifact(payload, matrix=matrix)
    except MatrixFlashcardBuildError:
        from notebooklm_queue.personlighedspsykologi_notebooklm_variant_flashcards import validate_variant_deck

        validate_variant_deck(payload, expected_deck_slug=None)
    return payload


def rows_by_id(matrix: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("theory_id") or "").strip(): row
        for row in _as_list(matrix.get("rows"))
        if isinstance(row, dict) and str(row.get("theory_id") or "").strip()
    }


def cards_for_theory_ids(deck: dict[str, Any], theory_ids: set[str], *, include_all: bool = False) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for card in _as_list(deck.get("cards")):
        if not isinstance(card, dict):
            continue
        tags = set(_as_str_list(card.get("tags")))
        if include_all or tags & theory_ids:
            cards.append(card)
    return cards


def comparison_rows_for_theory_ids(
    matrix: dict[str, Any],
    theory_ids: set[str],
    *,
    include_all: bool = False,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for row in _as_list(matrix.get("rows")):
        if not isinstance(row, dict):
            continue
        source_id = _text(row.get("theory_id"))
        for target in _as_list(row.get("comparison_targets")):
            if not isinstance(target, dict):
                continue
            target_id = _text(target.get("target_theory_id"))
            if include_all or source_id in theory_ids or target_id in theory_ids:
                pairs.append((row, target))
    return pairs


def render_authoring_brief(spec: NotebookSpec) -> str:
    return "\n".join(
        [
            "# Card-authoring brief",
            "",
            f"Notebook: {spec.title}",
            f"Purpose: {spec.purpose}",
            "",
            "You are proposing alternative Freudd flashcards for a Danish university course in personality psychology.",
            "",
            "Hard rules:",
            "",
            "- Write learner-facing fronts and backs in Danish.",
            "- Generate independently from the processed matrix material in this notebook.",
            "- Prioritize oral-exam retrieval, comparison, and misunderstanding prevention.",
            "- Do not cite or mention student note owners, local file paths, source-note IDs, or internal provenance.",
            "- Do not invent source-grounded claims beyond the matrix content in this notebook.",
            "- Prefer compact answer backs: normally 1-4 sentences or 2-4 bullets.",
            "- Avoid generic definition-only cards unless the card forces a useful distinction.",
            "- If the source material is uncertain, make the card about the uncertainty rather than hiding it.",
            "- Do not assume you have seen the current Freudd deck; duplicate detection happens after NotebookLM generation.",
            "",
            "Useful card families:",
            "",
            "- orientation: essens/kontekst, determination, agency, historicitet",
            "- personbegreb: what model of person/personality/subjectivity is assumed",
            "- method: what evidence or method the theory trusts",
            "- affordance_limit: what the theory makes visible and what it hides",
            "- comparison: contrast, critique, extension, or translation between theories",
            "- exam_trap: correct a likely oversimplification",
            "",
            "Return/generated cards should be useful even if later imported into a separate Freudd variants deck.",
        ]
    ) + "\n"


def render_orientation_points(matrix: dict[str, Any]) -> str:
    lines = ["# Orientation points", ""]
    for item in _as_list(matrix.get("orientation_points")):
        if not isinstance(item, dict):
            continue
        lines.extend(
            [
                f"## {_text(item.get('label'))}",
                "",
                _text(item.get("question")),
                "",
                f"ID: `{_text(item.get('orientation_point_id'))}`",
                "",
            ]
        )
    return "\n".join(lines)


def render_matrix_slice(matrix: dict[str, Any], theory_ids: set[str], *, include_all_digest: bool = False) -> str:
    lookup = rows_by_id(matrix)
    selected = [lookup[theory_id] for theory_id in theory_ids if theory_id in lookup]
    if include_all_digest:
        selected = [row for row in _as_list(matrix.get("rows")) if isinstance(row, dict)]
    lines = ["# Matrix slice", ""]
    for row in selected:
        theory_id = _text(row.get("theory_id"))
        lines.extend(
            [
                f"## {_text(row.get('label'))}",
                "",
                f"ID: `{theory_id}`",
                f"Lectures: {', '.join(_as_str_list(row.get('lecture_keys')))}",
                "",
                f"Course role: {_text(row.get('course_role'))}",
                "",
                f"Course summary: {_text(row.get('course_summary'))}",
                "",
                f"Model of person: {_text(row.get('model_of_person'))}",
                "",
                "Personality/subjektivitet:",
                "",
                _text(row.get("personality_or_subjectivity_model")),
                "",
                f"Method/evidence: {_text(row.get('method_evidence_style'))}",
                "",
                "Central concepts: " + "; ".join(_as_str_list(row.get("central_concepts"))),
                "",
                "Orientation points:",
                "",
            ]
        )
        orientation = row.get("orientation_points") if isinstance(row.get("orientation_points"), dict) else {}
        for point_id, point in orientation.items():
            if not isinstance(point, dict):
                continue
            lines.append(f"- `{point_id}`: {_text(point.get('placement'))} - {_text(point.get('summary'))}")
        lines.extend(
            [
                "",
                "Strengths:",
                "",
                *[f"- {item}" for item in _as_str_list(row.get("strengths"))],
                "",
                "Limitations:",
                "",
                *[f"- {item}" for item in _as_str_list(row.get("limitations"))],
                "",
                "Likely misunderstandings:",
                "",
                *[f"- {item}" for item in _as_str_list(row.get("likely_misunderstandings"))],
                "",
                f"Student-synthesis exam note: {_text(row.get('student_synthesis_notes'))}",
                "",
                "---",
                "",
            ]
        )
    return "\n".join(lines)


def render_current_cards(cards: list[dict[str, Any]]) -> str:
    lines = ["# Current Freudd cards to avoid duplicating", ""]
    for index, card in enumerate(cards, start=1):
        lines.extend(
            [
                f"## Existing card {index}",
                "",
                f"Card ID: `{_text(card.get('card_id'))}`",
                f"Category: {_text(card.get('category_title'))}",
                f"Tags: {', '.join(_as_str_list(card.get('tags')))}",
                "",
                f"Front: {_text(card.get('front_text'))}",
                "",
                f"Back: {_text(card.get('back_text'))}",
                "",
                "---",
                "",
            ]
        )
    return "\n".join(lines)


def render_comparisons(matrix: dict[str, Any], theory_ids: set[str], *, include_all: bool = False) -> str:
    lookup = rows_by_id(matrix)
    lines = ["# Comparison targets", ""]
    for row, target in comparison_rows_for_theory_ids(matrix, theory_ids, include_all=include_all):
        source_label = _text(row.get("label"))
        target_id = _text(target.get("target_theory_id"))
        target_label = _text((lookup.get(target_id) or {}).get("label")) or target_id
        lines.extend(
            [
                f"## {source_label} -> {target_label}",
                "",
                f"Relation: {_text(target.get('relation')).replace('_', ' ')}",
                "",
                f"Rationale: {_text(target.get('rationale'))}",
                "",
            ]
        )
    return "\n".join(lines)


def render_output_contract() -> str:
    categories = "\n".join(f"- `{item['slug']}`: {item['title']}" for item in CATEGORIES)
    return "\n".join(
        [
            "# Output contract for candidate cards",
            "",
            "NotebookLM may generate flashcards in its native format. The repo will later normalize them to this candidate shape:",
            "",
            "```json",
            "{",
            '  "front": "Danish question text",',
            '  "back": "Danish answer text",',
            '  "category_slug": "one of the allowed categories",',
            '  "theory_ids": ["matrix_theory_id"],',
            '  "card_family": "orientation|personbegreb|method|affordance_limit|comparison|exam_trap",',
            '  "added_value": "why this helps oral-exam recall or comparison"',
            "}",
            "```",
            "",
            "Allowed categories:",
            "",
            categories,
            "",
            "Good cards should be short enough for recall practice and specific enough for oral-exam preparation.",
        ]
    ) + "\n"


def render_all_theory_orientation_table(matrix: dict[str, Any]) -> str:
    lines = ["# All-theory orientation table", ""]
    header = "| Theory | Essence/context | Determination | Agency | Historicity |"
    lines.extend([header, "|---|---|---|---|---|"])
    for row in _as_list(matrix.get("rows")):
        if not isinstance(row, dict):
            continue
        orientation = row.get("orientation_points") if isinstance(row.get("orientation_points"), dict) else {}
        values = []
        for point_id in ("essence_context", "determination", "agency", "historicity"):
            point = orientation.get(point_id) if isinstance(orientation, dict) else {}
            values.append(_text((point or {}).get("placement")).replace("|", "/"))
        lines.append(f"| {_text(row.get('label'))} | " + " | ".join(values) + " |")
    return "\n".join(lines) + "\n"


def _source_entry(path: Path, repo_root: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    return {
        "path": _repo_relative(path, repo_root),
        "sha256": _hash_text(text),
        "bytes": len(text.encode("utf-8")),
    }


def export_notebook_packs(
    *,
    matrix: dict[str, Any],
    run_id: str,
    lab_root: Path,
    repo_root: Path,
    notebook_slugs: set[str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at or utc_now_iso()
    run_root = lab_root / "runs" / run_id
    packs_root = run_root / "packs"
    selected_specs = [
        spec for spec in NOTEBOOK_SPECS if notebook_slugs is None or spec.slug in notebook_slugs
    ]
    if not selected_specs:
        raise FlashcardLabError("No notebook specs selected")

    notebooks: list[dict[str, Any]] = []
    for spec in selected_specs:
        theory_ids = set(spec.theory_ids)
        pack_dir = packs_root / spec.slug
        pack_dir.mkdir(parents=True, exist_ok=True)
        for stale_markdown in pack_dir.glob("*.md"):
            stale_markdown.unlink()
        files = {
            "00-card-authoring-brief.md": render_authoring_brief(spec),
            "01-orientation-points.md": render_orientation_points(matrix),
            "02-matrix-slice.md": render_matrix_slice(
                matrix,
                theory_ids,
                include_all_digest=spec.include_all_rows_digest,
            ),
            "03-comparison-targets.md": render_comparisons(
                matrix,
                theory_ids,
                include_all=spec.comparison_workshop or spec.include_all_rows_digest,
            ),
            "04-output-contract.md": render_output_contract(),
        }
        if spec.comparison_workshop:
            files["05-all-theory-orientation-table.md"] = render_all_theory_orientation_table(matrix)
        for filename, content in files.items():
            (pack_dir / filename).write_text(content, encoding="utf-8")
        source_entries = [_source_entry(pack_dir / filename, repo_root) for filename in sorted(files)]
        notebooks.append(
            {
                "slug": spec.slug,
                "title": spec.title,
                "purpose": spec.purpose,
                "theory_ids": list(spec.theory_ids),
                "pack_dir": _repo_relative(pack_dir, repo_root),
                "sources": source_entries,
                "source_count": len(source_entries),
                "status": "pack_exported",
                "notebooklm_notebook_id": None,
                "flashcard_generation": {
                    "quantity": "more",
                    "difficulty": "hard",
                    "instructions": "Generate Danish oral-exam flashcard candidates from the uploaded processed matrix material. Prioritize comparison, exam traps, and precise recall; avoid generic definition cards.",
                },
            }
        )

    manifest = {
        "version": LAB_VERSION,
        "artifact_type": "personlighedspsykologi_notebooklm_flashcard_lab_manifest",
        "subject_slug": SUBJECT_SLUG,
        "run_id": run_id,
        "generated_at": generated_at,
        "lab_root": _repo_relative(lab_root, repo_root),
        "matrix": {
            "row_count": len(_as_list(matrix.get("rows"))),
            "fingerprint": semantic_fingerprint(matrix),
        },
        "freudd_deck_policy": {
            "included_as_notebook_source": False,
            "dedupe_stage": "after NotebookLM generation, during normalization and Gemini review",
        },
        "notebooks": notebooks,
    }
    write_json_stably(run_root / "manifest.json", manifest)
    return manifest


def _normalize_card_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _token_set(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-ZæøåÆØÅ0-9]+", value.casefold())
        if len(token) >= 3
    }


def duplicate_score(front: str, back: str, existing_cards: list[dict[str, Any]]) -> tuple[float, str | None]:
    review = manual_card_review(front=front, back=back, existing_cards=existing_cards, warnings=[], theory_ids=[])
    nearest = review.get("nearest_existing_card") if isinstance(review.get("nearest_existing_card"), dict) else {}
    return float(review.get("duplicate_score") or 0.0), _text(nearest.get("card_id")) or None


def _card_brief(card: dict[str, Any] | None) -> dict[str, Any] | None:
    if not card:
        return None
    return {
        "card_id": _text(card.get("card_id")),
        "category_slug": _text(card.get("category_slug")),
        "category_title": _text(card.get("category_title")),
        "tags": _as_str_list(card.get("tags")),
        "front_text": _text(card.get("front_text")),
        "back_text": _text(card.get("back_text")),
    }


def manual_card_review(
    *,
    front: str,
    back: str,
    existing_cards: list[dict[str, Any]],
    warnings: list[str],
    theory_ids: list[str],
) -> dict[str, Any]:
    candidate_tokens = _token_set(front + " " + back)
    if not candidate_tokens:
        return {
            "duplicate_score": 0.0,
            "nearest_existing_card": None,
            "shared_terms": [],
            "suggested_decision": "reject",
            "rationale": "Candidate has no usable token content.",
        }
    best_score = 0.0
    best_card: dict[str, Any] | None = None
    best_shared_terms: set[str] = set()
    for card in existing_cards:
        existing_text = _text(card.get("front_text")) + " " + _text(card.get("back_text"))
        existing_tokens = _token_set(existing_text)
        if not existing_tokens:
            continue
        shared_terms = candidate_tokens & existing_tokens
        score = len(candidate_tokens & existing_tokens) / len(candidate_tokens | existing_tokens)
        if _normalize_card_text(front).casefold() == _normalize_card_text(card.get("front_text")).casefold():
            score = max(score, 0.95)
        if score > best_score:
            best_score = score
            best_card = card
            best_shared_terms = shared_terms

    hard_warnings = {"unsafe_provenance_or_path", "front_too_long", "back_too_long"}
    if hard_warnings & set(warnings):
        decision = "reject"
        rationale = "Reject before content review because the candidate fails a hard safety/shape gate."
    elif not theory_ids:
        decision = "reject"
        rationale = "Reject or remap manually because the card is not grounded to a matrix theory row."
    elif best_score >= DUPLICATE_REJECT_THRESHOLD:
        decision = "merge_with_existing"
        rationale = "Very high overlap with an existing Freudd card; only merge if the wording improves that card."
    elif best_score >= DUPLICATE_REVIEW_THRESHOLD:
        decision = "merge_with_existing"
        rationale = "High overlap with an existing Freudd card; review as a possible wording improvement, not a new card."
    elif best_score >= MANUAL_CARD_OVERLAP_REVIEW_THRESHOLD:
        decision = "edit"
        rationale = "Moderate overlap with an existing Freudd card; keep only if it adds a distinct oral-exam retrieval cue."
    elif warnings:
        decision = "edit"
        rationale = "Potentially useful, but warnings need human cleanup before promotion."
    else:
        decision = "accept"
        rationale = "Low overlap with existing Freudd cards and no automatic warnings; review for content quality before promotion."

    return {
        "duplicate_score": round(best_score, 4),
        "nearest_existing_card": _card_brief(best_card),
        "shared_terms": sorted(best_shared_terms)[:24],
        "suggested_decision": decision,
        "rationale": rationale,
    }


def infer_theory_ids(front: str, back: str, matrix: dict[str, Any]) -> list[str]:
    text = (front + " " + back).casefold()
    matches: list[tuple[int, str]] = []
    for row in _as_list(matrix.get("rows")):
        if not isinstance(row, dict):
            continue
        theory_id = _text(row.get("theory_id"))
        needles = {_text(row.get("label")).casefold(), theory_id.replace("_", " ").casefold()}
        needles.update(alias.casefold() for alias in _as_str_list(row.get("aliases")))
        keywords = THEORY_KEYWORDS.get(theory_id, ())
        score = sum(3 for needle in needles if needle and needle in text)
        score += sum(2 for keyword in keywords if keyword and keyword.casefold() in text)
        score += sum(1 for concept in _as_str_list(row.get("central_concepts"))[:8] if concept.casefold() in text)
        if score:
            matches.append((score, theory_id))
    matches.sort(key=lambda item: (-item[0], item[1]))
    return [theory_id for _, theory_id in matches[:3]]


def infer_category(front: str, back: str) -> str:
    text = (front + " " + back).casefold()
    scores: Counter[str] = Counter()
    for slug, keywords in CATEGORY_KEYWORDS.items():
        scores[slug] = sum(1 for keyword in keywords if keyword.casefold() in text)
    if scores:
        slug, score = scores.most_common(1)[0]
        if score > 0:
            return slug
    return "sammenligninger" if " vs " in text or "forskel" in text else "eksamenstraps"


def _candidate_id(*, run_id: str, notebook_slug: str, front: str, back: str) -> str:
    digest = _hash_text(f"{run_id}\n{notebook_slug}\n{front}\n{back}")[:16]
    return f"nlm-{_slug(notebook_slug)}-{digest}"


def _safety_warnings(front: str, back: str) -> list[str]:
    text = front + "\n" + back
    warnings: list[str] = []
    for pattern in LEARNER_TEXT_FORBIDDEN_PATTERNS:
        if pattern.search(text):
            warnings.append("unsafe_provenance_or_path")
            break
    if len(front) > MAX_FRONT_CHARS:
        warnings.append("front_too_long")
    if len(back) > MAX_BACK_CHARS:
        warnings.append("back_too_long")
    if any(pattern.search(front) for pattern in VAGUE_FRONT_PATTERNS):
        warnings.append("possibly_generic_definition_card")
    if not front.endswith("?"):
        warnings.append("front_not_question")
    return warnings


def _review_status(warnings: list[str], duplicate: float, theory_ids: list[str]) -> str:
    hard = {"unsafe_provenance_or_path", "front_too_long", "back_too_long"}
    if hard & set(warnings) or duplicate >= DUPLICATE_REJECT_THRESHOLD or not theory_ids:
        return "auto_rejected"
    if warnings or duplicate >= DUPLICATE_REVIEW_THRESHOLD:
        return "needs_review"
    return "candidate"


def normalize_notebooklm_cards(
    *,
    notebooklm_payload: dict[str, Any],
    matrix: dict[str, Any],
    current_deck: dict[str, Any],
    run_id: str,
    notebook_slug: str,
    source_path: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    raw_cards = notebooklm_payload.get("cards")
    if not isinstance(raw_cards, list):
        raise FlashcardLabError("NotebookLM flashcard payload must contain cards list")
    existing_cards = [card for card in _as_list(current_deck.get("cards")) if isinstance(card, dict)]
    candidates: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for index, raw in enumerate(raw_cards, start=1):
        if not isinstance(raw, dict):
            continue
        front = _normalize_card_text(raw.get("front") or raw.get("f"))
        back = _normalize_card_text(raw.get("back") or raw.get("b"))
        if not front or not back:
            continue
        pair = (front.casefold(), back.casefold())
        warnings = _safety_warnings(front, back)
        if pair in seen_pairs:
            warnings.append("duplicate_within_notebooklm_payload")
        seen_pairs.add(pair)
        theory_ids = infer_theory_ids(front, back, matrix)
        category_slug = infer_category(front, back)
        manual_review = manual_card_review(
            front=front,
            back=back,
            existing_cards=existing_cards,
            warnings=warnings,
            theory_ids=theory_ids,
        )
        dup_score = float(manual_review.get("duplicate_score") or 0.0)
        nearest_card = manual_review.get("nearest_existing_card")
        dup_card_id = _text(nearest_card.get("card_id")) if isinstance(nearest_card, dict) else None
        status = _review_status(warnings, dup_score, theory_ids)
        candidates.append(
            {
                "candidate_id": _candidate_id(
                    run_id=run_id,
                    notebook_slug=notebook_slug,
                    front=front,
                    back=back,
                ),
                "notebook_slug": notebook_slug,
                "source_path": source_path,
                "source_index": index,
                "front": front,
                "back": back,
                "category_slug": category_slug,
                "category_title": next(
                    (item["title"] for item in CATEGORIES if item["slug"] == category_slug),
                    category_slug,
                ),
                "mapped_theory_ids": theory_ids,
                "duplicate": {
                    "score": round(dup_score, 4),
                    "nearest_card_id": dup_card_id,
                },
                "manual_card_review": manual_review,
                "warnings": sorted(set(warnings)),
                "review_status": status,
            }
        )
    status_counts = Counter(str(item["review_status"]) for item in candidates)
    return {
        "version": LAB_VERSION,
        "artifact_type": "personlighedspsykologi_notebooklm_flashcard_candidates",
        "subject_slug": SUBJECT_SLUG,
        "run_id": run_id,
        "notebook_slug": notebook_slug,
        "generated_at": generated_at or utc_now_iso(),
        "source_path": source_path,
        "raw_title": _text(notebooklm_payload.get("title")),
        "stats": {
            "raw_card_count": len(raw_cards),
            "candidate_count": len(candidates),
            "status_counts": dict(sorted(status_counts.items())),
        },
        "candidates": candidates,
    }


def load_notebooklm_flashcard_payload(path: Path) -> dict[str, Any]:
    payload = _load_json(path)
    if isinstance(payload.get("cards"), list):
        return payload
    flashcards = payload.get("flashcards")
    if isinstance(flashcards, list):
        normalized = dict(payload)
        normalized["cards"] = flashcards
        return normalized
    data = payload.get("data")
    if isinstance(data, dict):
        nested = data.get("cards") or data.get("flashcards")
        if isinstance(nested, list):
            normalized = dict(data)
            normalized["cards"] = nested
            normalized.setdefault("title", payload.get("title"))
            return normalized
    raise FlashcardLabError(f"NotebookLM flashcard JSON has no cards list: {path}")


def write_candidate_review_markdown(candidates_payload: dict[str, Any], output_path: Path) -> None:
    lines = [
        f"# NotebookLM flashcard candidates: {candidates_payload.get('notebook_slug')}",
        "",
        f"Run: `{candidates_payload.get('run_id')}`",
        "",
        "Review statuses are automatic pre-review labels. Do not import without human approval.",
        "",
    ]
    for candidate in _as_list(candidates_payload.get("candidates")):
        if not isinstance(candidate, dict):
            continue
        lines.extend(
            [
                f"## {candidate.get('candidate_id')}",
                "",
                f"Status: `{candidate.get('review_status')}`",
                f"Category: `{candidate.get('category_slug')}`",
                f"Theories: {', '.join(_as_str_list(candidate.get('mapped_theory_ids')))}",
                f"Duplicate: {candidate.get('duplicate')}",
                f"Warnings: {', '.join(_as_str_list(candidate.get('warnings'))) or 'none'}",
                "",
                "Suggested decision: "
                f"`{_text((candidate.get('manual_card_review') or {}).get('suggested_decision'))}`",
                "",
                f"Review rationale: {_text((candidate.get('manual_card_review') or {}).get('rationale'))}",
                "",
                f"Front: {candidate.get('front')}",
                "",
                f"Back: {candidate.get('back')}",
                "",
                "Nearest existing Freudd card:",
                "",
                _format_nearest_card_for_review(candidate),
                "",
                "Decision: [ ] accept  [ ] edit  [ ] merge with existing  [ ] reject",
                "",
                "---",
                "",
            ]
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


DECISION_VALUES = {"accept", "edit", "merge_with_existing", "reject"}
CONFIDENCE_VALUES = {"low", "medium", "high"}


def matrix_review_rows(matrix: dict[str, Any], theory_ids: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _as_list(matrix.get("rows")):
        if not isinstance(row, dict):
            continue
        theory_id = _text(row.get("theory_id"))
        if theory_id not in theory_ids:
            continue
        rows.append(
            {
                "theory_id": theory_id,
                "label": _text(row.get("label")),
                "course_role": _text(row.get("course_role")),
                "course_summary": _text(row.get("course_summary")),
                "model_of_person": _text(row.get("model_of_person")),
                "personality_or_subjectivity_model": _text(row.get("personality_or_subjectivity_model")),
                "method_evidence_style": _text(row.get("method_evidence_style")),
                "central_concepts": _as_str_list(row.get("central_concepts"))[:12],
                "strengths": _as_str_list(row.get("strengths")),
                "limitations": _as_str_list(row.get("limitations")),
                "likely_misunderstandings": _as_str_list(row.get("likely_misunderstandings")),
            }
        )
    return rows


def _candidate_for_gemini(candidate: dict[str, Any]) -> dict[str, Any]:
    manual_review = candidate.get("manual_card_review") if isinstance(candidate.get("manual_card_review"), dict) else {}
    nearest = manual_review.get("nearest_existing_card") if isinstance(manual_review.get("nearest_existing_card"), dict) else None
    return {
        "candidate_id": _text(candidate.get("candidate_id")),
        "source_index": candidate.get("source_index"),
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
    }


def build_gemini_flashcard_review_bundle(
    *,
    candidates_payload: dict[str, Any],
    matrix: dict[str, Any],
    current_deck: dict[str, Any],
    model: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    candidates = [item for item in _as_list(candidates_payload.get("candidates")) if isinstance(item, dict)]
    if not candidates:
        raise FlashcardLabError("Gemini review bundle needs at least one candidate")
    candidate_ids = [_text(item.get("candidate_id")) for item in candidates]
    if any(not candidate_id for candidate_id in candidate_ids) or len(set(candidate_ids)) != len(candidate_ids):
        raise FlashcardLabError("Gemini review bundle candidate IDs must be non-empty and unique")
    theory_ids = {
        theory_id
        for item in candidates
        for theory_id in _as_str_list(item.get("mapped_theory_ids"))
        if theory_id != "comparative_theory_analysis"
    }
    return {
        "version": LAB_VERSION,
        "artifact_type": "personlighedspsykologi_gemini_flashcard_review_bundle",
        "subject_slug": SUBJECT_SLUG,
        "run_id": _text(candidates_payload.get("run_id")),
        "notebook_slug": _text(candidates_payload.get("notebook_slug")),
        "generated_at": generated_at or utc_now_iso(),
        "model": model,
        "prompt_version": GEMINI_FLASHCARD_REVIEW_PROMPT_VERSION,
        "input_fingerprints": {
            "candidates": semantic_fingerprint(candidates_payload),
            "matrix": semantic_fingerprint(matrix),
            "current_deck": semantic_fingerprint(current_deck),
        },
        "review_contract": {
            "task": "Review NotebookLM flashcard candidates against the existing Freudd deck.",
            "decisions": sorted(DECISION_VALUES),
            "decision_rules": [
                "accept only if the card adds a distinct oral-exam retrieval cue beyond the existing Freudd deck",
                "edit when the idea is useful but wording, precision, category, or evidence grounding needs cleanup",
                "merge_with_existing when the candidate mostly improves or duplicates the nearest existing Freudd card",
                "reject when the card is generic, unsafe, ungrounded, misleading, or redundant without wording improvement",
                "never approve cards that mention student note owners, local file paths, internal IDs, or hidden provenance",
            ],
            "promotion_boundary": "This review is advisory. It must not create or modify Freudd cards directly.",
        },
        "matrix_rows": matrix_review_rows(matrix, theory_ids),
        "current_deck": {
            "deck_slug": _text(current_deck.get("deck_slug")),
            "card_count": int(current_deck.get("card_count") or 0),
        },
        "candidates": [_candidate_for_gemini(candidate) for candidate in candidates],
    }


def gemini_flashcard_review_system_instruction() -> str:
    return "\n".join(
        [
            "You are a strict Danish university psychology flashcard reviewer.",
            "Return only valid JSON matching the requested schema.",
            "Review NotebookLM candidate cards against the existing Freudd deck context.",
            "Prefer rejecting or merging over accepting near-duplicates.",
            "Do not invent course claims beyond the supplied matrix rows and candidate text.",
            "Do not approve learner-facing text that leaks student note owners, local paths, source-note IDs, or internal provenance.",
        ]
    )


def gemini_flashcard_review_user_prompt(bundle: dict[str, Any]) -> str:
    return "\n".join(
        [
            "Review every candidate in this JSON bundle.",
            "",
            "Return one decision per candidate_id. Keep edited_front and edited_back empty unless decision is edit.",
            "Use Danish for edited_front and edited_back. Keep reasons concise but specific.",
            "",
            "Input bundle:",
            "",
            render_json(bundle),
        ]
    )


def gemini_flashcard_review_response_schema() -> dict[str, Any]:
    decision_enum = sorted(DECISION_VALUES)
    confidence_enum = sorted(CONFIDENCE_VALUES)
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
                        "decision": {"type": "string", "enum": decision_enum},
                        "confidence": {"type": "string", "enum": confidence_enum},
                        "reason": {"type": "string"},
                        "added_value": {"type": "string"},
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


def validate_gemini_flashcard_review(
    review_payload: dict[str, Any],
    *,
    bundle: dict[str, Any],
    model: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    raw_decisions = review_payload.get("decisions")
    if not isinstance(raw_decisions, list):
        raise FlashcardLabError("Gemini review payload must contain decisions list")
    candidate_ids = [_text(item.get("candidate_id")) for item in _as_list(bundle.get("candidates")) if isinstance(item, dict)]
    expected_ids = set(candidate_ids)
    decisions: list[dict[str, Any]] = []
    seen: set[str] = set()
    status_counts: Counter[str] = Counter()
    candidates_by_id = {
        _text(item.get("candidate_id")): item
        for item in _as_list(bundle.get("candidates"))
        if isinstance(item, dict)
    }
    for raw in raw_decisions:
        if not isinstance(raw, dict):
            raise FlashcardLabError("Gemini review decisions must be objects")
        candidate_id = _text(raw.get("candidate_id"))
        if candidate_id not in expected_ids:
            raise FlashcardLabError(f"Gemini review returned unknown candidate_id: {candidate_id}")
        if candidate_id in seen:
            raise FlashcardLabError(f"Gemini review returned duplicate candidate_id: {candidate_id}")
        seen.add(candidate_id)
        decision = _text(raw.get("decision"))
        confidence = _text(raw.get("confidence"))
        if decision not in DECISION_VALUES:
            raise FlashcardLabError(f"Invalid Gemini review decision for {candidate_id}: {decision}")
        if confidence not in CONFIDENCE_VALUES:
            raise FlashcardLabError(f"Invalid Gemini review confidence for {candidate_id}: {confidence}")
        edited_front = _normalize_card_text(raw.get("edited_front"))
        edited_back = _normalize_card_text(raw.get("edited_back"))
        if decision == "edit" and (not edited_front or not edited_back):
            raise FlashcardLabError(f"Gemini edit decision must include edited text: {candidate_id}")
        if len(edited_front) > MAX_FRONT_CHARS:
            raise FlashcardLabError(f"Gemini edited front too long: {candidate_id}")
        if len(edited_back) > MAX_BACK_CHARS:
            raise FlashcardLabError(f"Gemini edited back too long: {candidate_id}")
        safety_text = "\n".join([edited_front, edited_back, _text(raw.get("reason")), _text(raw.get("added_value"))])
        for pattern in LEARNER_TEXT_FORBIDDEN_PATTERNS:
            if pattern.search(safety_text):
                raise FlashcardLabError(f"Gemini review leaks forbidden learner-facing provenance: {candidate_id}")
        candidate = candidates_by_id[candidate_id]
        if decision == "accept" and (
            candidate.get("automatic_review_status") == "auto_rejected" or _as_str_list(candidate.get("warnings"))
        ):
            raise FlashcardLabError(f"Gemini cannot accept auto-rejected/warned candidate without edit: {candidate_id}")
        status_counts[decision] += 1
        decisions.append(
            {
                "candidate_id": candidate_id,
                "decision": decision,
                "confidence": confidence,
                "reason": _text(raw.get("reason")),
                "added_value": _text(raw.get("added_value")),
                "nearest_existing_card_assessment": _text(raw.get("nearest_existing_card_assessment")),
                "edited_front": edited_front,
                "edited_back": edited_back,
                "safety_flags": _as_str_list(raw.get("safety_flags")),
                "local_suggested_decision": _text(candidate.get("local_suggested_decision")),
                "automatic_review_status": _text(candidate.get("automatic_review_status")),
            }
        )
    missing = expected_ids - seen
    if missing:
        raise FlashcardLabError("Gemini review missing candidate decisions: " + ", ".join(sorted(missing)[:10]))
    summary = review_payload.get("review_summary") if isinstance(review_payload.get("review_summary"), dict) else {}
    return {
        "version": LAB_VERSION,
        "artifact_type": GEMINI_FLASHCARD_REVIEW_ARTIFACT_TYPE,
        "subject_slug": SUBJECT_SLUG,
        "run_id": _text(bundle.get("run_id")),
        "notebook_slug": _text(bundle.get("notebook_slug")),
        "generated_at": generated_at or utc_now_iso(),
        "model": model,
        "prompt_version": GEMINI_FLASHCARD_REVIEW_PROMPT_VERSION,
        "input_fingerprints": bundle.get("input_fingerprints"),
        "stats": {
            "candidate_count": len(candidate_ids),
            "decision_counts": dict(sorted(status_counts.items())),
        },
        "review_summary": {
            "overall_assessment": _text(summary.get("overall_assessment")),
            "main_risks": _as_str_list(summary.get("main_risks")),
        },
        "decisions": decisions,
    }


def write_gemini_flashcard_review_markdown(review_payload: dict[str, Any], output_path: Path) -> None:
    lines = [
        f"# Gemini flashcard review: {review_payload.get('notebook_slug')}",
        "",
        f"Run: `{review_payload.get('run_id')}`",
        f"Model: `{review_payload.get('model')}`",
        f"Prompt: `{review_payload.get('prompt_version')}`",
        "",
        f"Summary: {_text((review_payload.get('review_summary') or {}).get('overall_assessment'))}",
        "",
        f"Decision counts: {review_payload.get('stats', {}).get('decision_counts')}",
        "",
    ]
    risks = _as_str_list((review_payload.get("review_summary") or {}).get("main_risks"))
    if risks:
        lines.extend(["Main risks:", "", *[f"- {risk}" for risk in risks], ""])
    for decision in _as_list(review_payload.get("decisions")):
        if not isinstance(decision, dict):
            continue
        lines.extend(
            [
                f"## {decision.get('candidate_id')}",
                "",
                f"Decision: `{decision.get('decision')}`",
                f"Confidence: `{decision.get('confidence')}`",
                f"Automatic status: `{decision.get('automatic_review_status')}`",
                f"Local suggestion: `{decision.get('local_suggested_decision')}`",
                "",
                f"Reason: {decision.get('reason')}",
                "",
                f"Added value: {decision.get('added_value')}",
                "",
                f"Nearest-card assessment: {decision.get('nearest_existing_card_assessment')}",
                "",
                f"Safety flags: {', '.join(_as_str_list(decision.get('safety_flags'))) or 'none'}",
                "",
            ]
        )
        if decision.get("decision") == "edit":
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
        lines.extend(["---", ""])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _format_nearest_card_for_review(candidate: dict[str, Any]) -> str:
    review = candidate.get("manual_card_review") if isinstance(candidate.get("manual_card_review"), dict) else {}
    nearest = review.get("nearest_existing_card") if isinstance(review.get("nearest_existing_card"), dict) else None
    if not nearest:
        return "No existing Freudd card found."
    shared = ", ".join(_as_str_list(review.get("shared_terms"))) or "none"
    return "\n".join(
        [
            f"- Card ID: `{nearest.get('card_id')}`",
            f"- Category: `{nearest.get('category_slug')}`",
            f"- Tags: {', '.join(_as_str_list(nearest.get('tags')))}",
            f"- Shared terms: {shared}",
            f"- Existing front: {nearest.get('front_text')}",
            f"- Existing back: {nearest.get('back_text')}",
        ]
    )


def write_manifest_readme(run_root: Path, manifest: dict[str, Any]) -> None:
    lines = [
        f"# NotebookLM Flashcard Lab Run {manifest.get('run_id')}",
        "",
        "This run contains processed Markdown packs for NotebookLM. Generated NotebookLM artifacts and candidates are local review outputs.",
        "",
        "Notebook packs:",
        "",
    ]
    for notebook in _as_list(manifest.get("notebooks")):
        if not isinstance(notebook, dict):
            continue
        lines.append(f"- `{notebook.get('slug')}`: {notebook.get('purpose')} ({notebook.get('source_count')} sources)")
    lines.extend(
        [
            "",
            "Safety contract:",
            "",
            "- Do not import NotebookLM cards directly into Freudd.",
            "- Normalize and QA downloaded flashcards first.",
            "- Keep accepted NotebookLM variants in a separate Freudd deck unless explicitly merged later.",
        ]
    )
    (run_root / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def export_lab_run(
    *,
    run_id: str,
    lab_root: Path,
    matrix_path: Path,
    deck_path: Path,
    repo_root: Path,
    notebook_slugs: set[str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    matrix = load_matrix(matrix_path)
    manifest = export_notebook_packs(
        matrix=matrix,
        run_id=run_id,
        lab_root=lab_root,
        repo_root=repo_root,
        notebook_slugs=notebook_slugs,
        generated_at=generated_at,
    )
    write_manifest_readme(lab_root / "runs" / run_id, manifest)
    return manifest


def manifest_digest(manifest: dict[str, Any]) -> str:
    return _hash_text(render_json(manifest))
