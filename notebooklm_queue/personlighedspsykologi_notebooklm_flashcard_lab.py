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
from notebooklm_queue.personlighedspsykologi_matrix_flashcards import (
    CATEGORIES,
    LEARNER_TEXT_FORBIDDEN_PATTERNS,
    load_matrix,
    validate_flashcard_artifact,
)

LAB_VERSION = 1
SUBJECT_SLUG = "personlighedspsykologi"
DEFAULT_LAB_ROOT = Path("notebooklm-podcast-auto/personlighedspsykologi/flashcard_lab")
DEFAULT_MATRIX_PATH = Path("shows/personlighedspsykologi-en/student_synthesis/exam_theory_matrix.json")
DEFAULT_DECK_PATH = Path("shows/personlighedspsykologi-en/flashcards/eksamensmatrix-personlighedspsykologi.json")
DEFAULT_RUN_ID_PREFIX = "matrix-flashcards"
PILOT_NOTEBOOK_SLUG = "critical-sociocultural-narrative"

MAX_FRONT_CHARS = 280
MAX_BACK_CHARS = 1200
DUPLICATE_REVIEW_THRESHOLD = 0.72
DUPLICATE_REJECT_THRESHOLD = 0.9

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
    include_all_existing_cards: bool = False
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
        include_all_existing_cards=True,
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
    validate_flashcard_artifact(payload, matrix=matrix)
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
            "- Create alternative cards, not duplicates of the existing cards.",
            "- Prioritize oral-exam retrieval, comparison, and misunderstanding prevention.",
            "- Do not cite or mention student note owners, local file paths, source-note IDs, or internal provenance.",
            "- Do not invent source-grounded claims beyond the matrix content in this notebook.",
            "- Prefer compact answer backs: normally 1-4 sentences or 2-4 bullets.",
            "- Avoid generic definition-only cards unless the card forces a useful distinction.",
            "- If the source material is uncertain, make the card about the uncertainty rather than hiding it.",
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
            '  "added_value": "why this is not a duplicate of the current Freudd deck"',
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
    deck: dict[str, Any],
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
        current_cards = cards_for_theory_ids(deck, theory_ids, include_all=spec.include_all_existing_cards)
        files = {
            "00-card-authoring-brief.md": render_authoring_brief(spec),
            "01-orientation-points.md": render_orientation_points(matrix),
            "02-matrix-slice.md": render_matrix_slice(
                matrix,
                theory_ids,
                include_all_digest=spec.include_all_rows_digest,
            ),
            "03-current-freudd-cards.md": render_current_cards(current_cards),
            "04-comparison-targets.md": render_comparisons(
                matrix,
                theory_ids,
                include_all=spec.comparison_workshop or spec.include_all_rows_digest,
            ),
            "05-output-contract.md": render_output_contract(),
        }
        if spec.comparison_workshop:
            files["06-all-theory-orientation-table.md"] = render_all_theory_orientation_table(matrix)
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
                    "instructions": "Generate Danish alternative flashcards that add value beyond the current Freudd cards. Prioritize comparison, exam traps, and oral-exam recall.",
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
        "current_deck": {
            "deck_slug": _text(deck.get("deck_slug")),
            "card_count": int(deck.get("card_count") or 0),
            "fingerprint": semantic_fingerprint(deck),
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
    candidate_tokens = _token_set(front + " " + back)
    if not candidate_tokens:
        return 0.0, None
    best_score = 0.0
    best_id: str | None = None
    for card in existing_cards:
        existing_text = _text(card.get("front_text")) + " " + _text(card.get("back_text"))
        existing_tokens = _token_set(existing_text)
        if not existing_tokens:
            continue
        score = len(candidate_tokens & existing_tokens) / len(candidate_tokens | existing_tokens)
        if _normalize_card_text(front).casefold() == _normalize_card_text(card.get("front_text")).casefold():
            score = max(score, 0.95)
        if score > best_score:
            best_score = score
            best_id = _text(card.get("card_id"))
    return best_score, best_id


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
        dup_score, dup_card_id = duplicate_score(front, back, existing_cards)
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
                f"Front: {candidate.get('front')}",
                "",
                f"Back: {candidate.get('back')}",
                "",
                "Decision: [ ] accept  [ ] edit  [ ] reject",
                "",
                "---",
                "",
            ]
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


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
    deck = load_current_deck(deck_path, matrix)
    manifest = export_notebook_packs(
        matrix=matrix,
        deck=deck,
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
