#!/usr/bin/env python3
"""Generate validated background overlays for the live personlighedspsykologi deck."""

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
    render_flashcard_background_markdown,
    validate_flashcard_background_payload,
)
from notebooklm_queue.personlighedspsykologi_full_notebooklm_flashcards import FULL_NOTEBOOKLM_DECK_SLUG
from notebooklm_queue.personlighedspsykologi_notebooklm_flashcard_lab import utc_now_iso

DEFAULT_DECK_PATH = Path("shows/personlighedspsykologi-en/flashcards") / f"{FULL_NOTEBOOKLM_DECK_SLUG}.json"
DEFAULT_MATRIX_PATH = Path("shows/personlighedspsykologi-en/student_synthesis/exam_theory_matrix.json")
DEFAULT_SOURCE_CARDS_DIR = Path("shows/personlighedspsykologi-en/source_intelligence/source_cards")
DEFAULT_REVISED_LECTURE_DIR = Path("shows/personlighedspsykologi-en/source_intelligence/revised_lecture_substrates")
DEFAULT_COURSE_SYNTHESIS_PATH = Path("shows/personlighedspsykologi-en/source_intelligence/course_synthesis.json")
AXIS_LABELS = {
    "essence_context": "essens/kontekst",
    "determination": "determination",
    "agency": "agency",
    "historicity": "historicitet",
}
CATEGORY_FIELD_MAP = {
    "personbegreb": ["model_of_person", "personality_or_subjectivity_model", "central_concepts"],
    "metode-og-evidens": ["method_evidence_style"],
    "orienteringspunkter": ["orientation_points"],
    "styrker-og-begraensninger": ["strengths", "limitations"],
    "eksamenstraps": ["likely_misunderstandings", "limitations"],
    "sammenligninger": ["comparison_targets", "course_summary"],
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


def _clip(value: object, *, words: int = 24) -> str:
    text = re.sub(r"\s+", " ", _text(value))
    parts = re.findall(r"\S+", text)
    if len(parts) <= words:
        return text.rstrip(".")
    return " ".join(parts[:words]).rstrip(".,;:") + "..."


def _sentence(value: object, *, words: int = 24) -> str:
    text = _clip(value, words=words)
    if not text:
        return ""
    return text if text.endswith((".", "?", "!")) else f"{text}."


def _theory_name(row: dict[str, Any]) -> str:
    labels = _as_str_list(row.get("student_note_labels"))
    return labels[0] if labels else _text(row.get("label")) or _text(row.get("theory_id"))


def _theory_ids_for_card(card: dict[str, Any], theory_ids: set[str]) -> list[str]:
    return sorted({tag for tag in _as_str_list(card.get("tags")) if tag in theory_ids})


def _axis_for_card(card: dict[str, Any]) -> str:
    text = f"{card.get('front_text')} {card.get('back_text')}".casefold()
    checks = [
        ("essence_context", ("essens", "kontekst", "context")),
        ("determination", ("determination", "determiner", "årsag", "kausal")),
        ("agency", ("agency", "handle", "aktør", "valg")),
        ("historicity", ("historicitet", "histor", "tid")),
    ]
    for axis, needles in checks:
        if any(needle in text for needle in needles):
            return axis
    return ""


def _first(values: object) -> str:
    items = _as_str_list(values)
    return items[0] if items else ""


def _source_lookup(source_cards_dir: Path) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    if not source_cards_dir.exists():
        return lookup
    for path in sorted(source_cards_dir.glob("*.json")):
        payload = _load_json(path)
        source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
        source_id = _text(source.get("source_id"))
        if source_id:
            lookup[source_id] = payload
    return lookup


def _lecture_lookup(revised_lecture_dir: Path) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    if not revised_lecture_dir.exists():
        return lookup
    for path in sorted(revised_lecture_dir.glob("*.json")):
        payload = _load_json(path)
        lecture = payload.get("lecture") if isinstance(payload.get("lecture"), dict) else {}
        lecture_key = _text(lecture.get("lecture_key"))
        if lecture_key:
            lookup[lecture_key] = payload
    return lookup


def _source_terms_for_row(row: dict[str, Any], source_cards: dict[str, dict[str, Any]]) -> list[str]:
    source_ids = _as_str_list((row.get("source_grounding") or {}).get("representative_source_ids"))
    terms: list[str] = []
    for source_id in source_ids[:3]:
        source_card = source_cards.get(source_id)
        if not source_card:
            continue
        analysis = source_card.get("analysis") if isinstance(source_card.get("analysis"), dict) else {}
        for concept in _as_list(analysis.get("key_concepts")):
            term = _text(concept.get("term")) if isinstance(concept, dict) else ""
            if term and not re.search(r"\b(?:source|matrix|substrat|kilde)\b", term, flags=re.IGNORECASE):
                terms.append(term)
            if len(terms) >= 3:
                return terms
    return terms


def _concept_clause(row: dict[str, Any], source_cards: dict[str, dict[str, Any]]) -> str:
    terms = _source_terms_for_row(row, source_cards)
    if terms:
        return f" Fagligt hænger det sammen med begreber som {', '.join(terms[:2])}."
    concepts = _as_str_list(row.get("central_concepts"))
    concepts = [concept for concept in concepts if not re.search(r"\b(?:source|matrix|substrat|kilde)\b", concept, flags=re.IGNORECASE)]
    if concepts:
        return f" Fagligt hænger det sammen med begreber som {', '.join(concepts[:2])}."
    return ""


def _support_for_card(
    *,
    card: dict[str, Any],
    rows: list[dict[str, Any]],
    source_cards: dict[str, dict[str, Any]],
    lecture_substrates: dict[str, dict[str, Any]],
    category_fields: list[str],
) -> tuple[list[dict[str, Any]], str]:
    support: list[dict[str, Any]] = []
    confidence = "high"
    for row in rows:
        theory_id = _text(row.get("theory_id"))
        for field in category_fields:
            support.append({"type": "matrix_field", "theory_id": theory_id, "field": field})
        source_ids = _as_str_list((row.get("source_grounding") or {}).get("representative_source_ids"))
        for source_id in source_ids:
            if source_id in source_cards:
                support.append(
                    {
                        "type": "source_card",
                        "source_id": source_id,
                        "fields": ["central_claims", "key_concepts", "distinctions", "likely_misunderstandings"],
                    }
                )
                break
        lecture_key = _first(row.get("lecture_keys"))
        if lecture_key in lecture_substrates:
            support.append(
                {
                    "type": "lecture_substrate",
                    "lecture_key": lecture_key,
                    "fields": ["what_matters_more", "warnings", "top_down_course_relevance"],
                }
            )
    if len(rows) > 1 or _text(card.get("category_slug")) == "sammenligninger":
        support.append({"type": "course_synthesis", "fields": ["theory_tradition_map", "distinction_map"]})
    if not any(entry["type"] == "source_card" for entry in support):
        confidence = "medium"
    return support, confidence


def _single_theory_background(card: dict[str, Any], row: dict[str, Any], source_cards: dict[str, dict[str, Any]]) -> str:
    category = _text(card.get("category_slug"))
    name = _theory_name(row)
    concept_clause = _concept_clause(row, source_cards)
    if category == "orienteringspunkter":
        axis = _axis_for_card(card)
        return (
            f"Baggrunden er placeringen af {name} på aksen {AXIS_LABELS.get(axis, 'orienteringspunktet')}. "
            f"Svaret viser, hvor teorien lægger tyngden: i indre mønstre, kontekst, handlemuligheder eller historisk formning. "
            f"Det gør kortet brugbart, fordi du kan sammenligne traditioner systematisk frem for kun at gengive løse definitioner.{concept_clause}"
        )
    if category == "metode-og-evidens":
        return (
            f"Baggrunden er teoriens måde at begrunde viden på. I {name} hænger metode og personbegreb sammen: "
            f"det, man accepterer som evidens, bestemmer også hvilken slags personlighedsforklaring der bliver mulig. "
            f"Derfor hjælper kortet dig med at forbinde metode, styrke og begrænsning i samme svar."
        )
    if category == "styrker-og-begraensninger":
        return (
            f"Baggrunden er spændet mellem teoriens gevinst og blinde plet. {name} gør bestemte sider af personlighed tydelige, "
            f"men overser eller nedtoner også noget andet. Det er netop den dobbelthed kortet træner, så du kan vurdere teorien "
            f"i stedet for kun at beskrive den."
        )
    if category == "eksamenstraps":
        return (
            f"Fælden opstår, når {name} gøres for enkel. Det sikre svar fastholder både traditionens hovedpointe og dens begrænsning, "
            f"så du ikke reducerer teorien til en karikatur. Kortet træner derfor præcision: hvad teorien faktisk siger, og hvad den ikke siger."
        )
    if category == "sammenligninger":
        return (
            f"Baggrunden er, at {name} fungerer som et sammenligningspunkt i kurset. "
            f"Sammenligningen bliver stærkest, når du viser, hvad teorien gør synligt, og hvad en anden tradition flytter fokus imod. "
            f"Det hjælper dig med at bygge et svar omkring forskelle i personbegreb, forklaringsniveau og metode."
        )
    return (
        f"Baggrunden er personbegrebet i {name}. Svaret viser, hvilken slags person, personlighed eller subjekt teorien overhovedet kan forklare. "
        f"Når du har det på plads, bliver det også lettere at se, hvorfor traditionen prioriterer bestemte begreber, metoder og begrænsninger.{concept_clause}"
    )


def _comparison_background(card: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    names = [_theory_name(row) for row in rows]
    if len(rows) == 2:
        return (
            f"Baggrunden er forskellen mellem {names[0]} og {names[1]}. "
            f"Kortet træner ikke bare to definitioner, men forskellen i forklaringsniveau: hvad den ene tradition gør synligt, "
            f"og hvad den anden flytter opmærksomheden over på. Det er den slags kontrast, der gør et mundtligt svar skarpere."
        )
    joined = ", ".join(names[:-1]) + f" og {names[-1]}"
    return (
        f"Baggrunden er en flerleddet teorisammenligning mellem {joined}. "
        f"Pointen er at vise, hvordan flere traditioner placerer personlighed forskelligt på akser som kontekst, agency og historicitet. "
        f"Det er særligt eksamensnyttigt, fordi du kan bygge et svar på tværs frem for at gengive teorierne enkeltvis."
    )


def build_background_payload(
    *,
    deck: dict[str, Any],
    matrix: dict[str, Any],
    source_cards: dict[str, dict[str, Any]],
    lecture_substrates: dict[str, dict[str, Any]],
    course_synthesis: dict[str, Any] | None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    rows_by_id = {
        _text(row.get("theory_id")): row
        for row in _as_list(matrix.get("rows"))
        if isinstance(row, dict) and _text(row.get("theory_id"))
    }
    backgrounds: list[dict[str, Any]] = []
    confidence_counts: Counter[str] = Counter()
    for card in _as_list(deck.get("cards")):
        if not isinstance(card, dict):
            continue
        theory_ids = _theory_ids_for_card(card, set(rows_by_id))
        rows = [rows_by_id[theory_id] for theory_id in theory_ids if theory_id in rows_by_id]
        if not rows:
            continue
        category = _text(card.get("category_slug"))
        fields = list(CATEGORY_FIELD_MAP.get(category, ["course_summary"]))
        if category == "orienteringspunkter" and (axis := _axis_for_card(card)):
            fields = [f"orientation_points:{axis}"]
        support, confidence = _support_for_card(
            card=card,
            rows=rows,
            source_cards=source_cards,
            lecture_substrates=lecture_substrates,
            category_fields=fields,
        )
        if len(rows) > 1:
            background_text = _comparison_background(card, rows)
        else:
            background_text = _single_theory_background(card, rows[0], source_cards)
        if category == "sammenligninger" and course_synthesis:
            confidence = "high"
        confidence_counts[confidence] += 1
        backgrounds.append(
            {
                "card_id": _text(card.get("card_id")),
                "old_front_text": _text(card.get("front_text")),
                "old_back_text": _text(card.get("back_text")),
                "background_text": background_text,
                "support": support,
                "confidence": confidence,
            }
        )

    payload = {
        "version": 1,
        "artifact_type": "personlighedspsykologi_flashcard_background_overlays",
        "subject_slug": "personlighedspsykologi",
        "generated_at": generated_at or utc_now_iso(),
        "scope": "All live full-matrix NotebookLM cards with deterministic matrix/source-intelligence context.",
        "source_policy": {
            "learner_facing_sources_named": False,
            "matrix_support_required": True,
            "source_intelligence_used_as_support": True,
            "raw_student_notes_used": False,
        },
        "stats": {
            "background_count": len(backgrounds),
            "deck_card_count": int(deck.get("card_count") or 0),
            "confidence_counts": dict(sorted(confidence_counts.items())),
        },
        "backgrounds": backgrounds,
    }
    validate_flashcard_background_payload(payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--deck-path", type=Path, default=DEFAULT_DECK_PATH)
    parser.add_argument("--matrix-path", type=Path, default=DEFAULT_MATRIX_PATH)
    parser.add_argument("--source-cards-dir", type=Path, default=DEFAULT_SOURCE_CARDS_DIR)
    parser.add_argument("--revised-lecture-dir", type=Path, default=DEFAULT_REVISED_LECTURE_DIR)
    parser.add_argument("--course-synthesis-path", type=Path, default=DEFAULT_COURSE_SYNTHESIS_PATH)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_FLASHCARD_BACKGROUNDS_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_FLASHCARD_BACKGROUNDS_MD)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    deck = _load_json(_resolve(args.deck_path, repo_root))
    matrix = _load_json(_resolve(args.matrix_path, repo_root))
    source_cards = _source_lookup(_resolve(args.source_cards_dir, repo_root))
    lecture_substrates = _lecture_lookup(_resolve(args.revised_lecture_dir, repo_root))
    course_synthesis_path = _resolve(args.course_synthesis_path, repo_root)
    course_synthesis = _load_json(course_synthesis_path) if course_synthesis_path.exists() else None
    payload = build_background_payload(
        deck=deck,
        matrix=matrix,
        source_cards=source_cards,
        lecture_substrates=lecture_substrates,
        course_synthesis=course_synthesis,
    )
    markdown = render_flashcard_background_markdown(payload)
    if not args.dry_run:
        write_json_stably(_resolve(args.output_json, repo_root), payload)
        _resolve(args.output_md, repo_root).write_text(markdown + "\n", encoding="utf-8")
    print(
        "generated flashcard backgrounds "
        f"(count={payload['stats']['background_count']}, confidence={payload['stats']['confidence_counts']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
