#!/usr/bin/env python3
"""Generate substrate-backed background overlays for the live personality deck."""

from __future__ import annotations

import argparse
import html
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
    DEFAULT_FLASHCARD_BACKGROUND_QA_MD,
    DEFAULT_FLASHCARD_BACKGROUND_SUBSTRATES_JSON,
    FlashcardBackgroundError,
    render_flashcard_background_markdown,
    validate_flashcard_background_payload,
)
from notebooklm_queue.personlighedspsykologi_full_notebooklm_flashcards import FULL_NOTEBOOKLM_DECK_SLUG
from notebooklm_queue.personlighedspsykologi_notebooklm_flashcard_lab import utc_now_iso

DEFAULT_DECK_PATH = Path("shows/personlighedspsykologi-en/flashcards") / f"{FULL_NOTEBOOKLM_DECK_SLUG}.json"
DEFAULT_MATRIX_PATH = Path("shows/personlighedspsykologi-en/student_synthesis/exam_theory_matrix.json")
DEFAULT_THEORY_MAP_PATH = Path("shows/personlighedspsykologi-en/course_theory_map.json")
DEFAULT_CONCEPT_GRAPH_PATH = Path("shows/personlighedspsykologi-en/course_concept_graph.json")
DEFAULT_SOURCE_CARDS_DIR = Path("shows/personlighedspsykologi-en/source_intelligence/source_cards")
DEFAULT_REVISED_LECTURE_DIR = Path("shows/personlighedspsykologi-en/source_intelligence/revised_lecture_substrates")

AXIS_LABELS = {
    "essence_context": "essens/kontekst",
    "determination": "determination",
    "agency": "agency",
    "historicity": "historicitet",
}
CATEGORY_FIELD_MAP = {
    "personbegreb": ["model_of_person", "personality_or_subjectivity_model", "central_concepts"],
    "metode-og-evidens": ["method_evidence_style", "model_of_person"],
    "orienteringspunkter": ["orientation_points", "model_of_person"],
    "styrker-og-begraensninger": ["strengths", "limitations"],
    "eksamenstraps": ["likely_misunderstandings", "limitations"],
    "sammenligninger": ["comparison_targets", "course_summary", "model_of_person"],
}
PROFILE_OVERRIDES = {
    "trait_and_assessment_psychology": {
        "name": "Trækpsykologi",
        "concepts": ["træk", "Big Five", "måling"],
        "focus": "relativt stabile træk, individuelle forskelle og måling på tværs af personer",
        "method": "spørgeskemaer, observatørrapporter og faktoranalytiske modeller",
    },
    "dynamic_personality_development": {
        "name": "Dynamisk personlighedsudvikling",
        "concepts": ["situation", "forandring", "stabilitet"],
        "focus": "samspillet mellem stabile mønstre, situationer og personlighedsforandring over tid",
        "method": "longitudinelle undersøgelser og analyser af person-situation-processer",
    },
    "biosocial_personality_perspectives": {
        "name": "Biosociale perspektiver",
        "concepts": ["genetik", "evolution", "kultur"],
        "focus": "genetik, evolution og socioøkologisk tilpasning som forklaringer på personlighed",
        "method": "biologiske, evolutionære og kulturkomparative forklaringsmodeller",
    },
    "personality_functioning_and_pathology": {
        "name": "Personlighedsfunktion og patologi",
        "concepts": ["funktion", "patologi", "relationer"],
        "focus": "selvfunktion, interpersonel funktion og grænsen mellem normalitet og patologi",
        "method": "klinisk vurdering af selv, relationer, identitet og funktionsniveau",
    },
    "psychoanalytic_personality_theory": {
        "name": "Psykoanalyse",
        "concepts": ["ubevidste", "forsvar", "begær"],
        "focus": "ubevidst konflikt, forsvar, begær og tidlige relationer",
        "method": "klinisk fortolkning, cases, frie associationer og symptomlæsning",
    },
    "phenomenological_psychology": {
        "name": "Fænomenologi",
        "concepts": ["livsverden", "oplevelse", "mening"],
        "focus": "førstepersonsperspektiv, livsverden og oplevet mening",
        "method": "beskrivelse af erfaring, oplevelse og meningsdannelse",
    },
    "existential_psychology": {
        "name": "Eksistentiel psykologi",
        "concepts": ["frihed", "ansvar", "valg"],
        "focus": "frihed, ansvar, valg og eksistentielle grundvilkår",
        "method": "fortolkning af valg, angst, ansvar og eksistentielle dilemmaer",
    },
    "humanistic_psychology": {
        "name": "Humanistisk psykologi",
        "concepts": ["vækst", "behov", "selvrealisering"],
        "focus": "vækst, behov, autenticitet og selvrealisering",
        "method": "personcentreret forståelse af ressourcer, relationer og udviklingsbetingelser",
    },
    "critical_personalism": {
        "name": "Kritisk personalisme",
        "concepts": ["person", "værdier", "livssammenhæng"],
        "focus": "personens konkrete livssammenhæng, værdier og handlemuligheder",
        "method": "personorienteret analyse af værdier, ansvar og konkret livsførelse",
    },
    "critical_psychology": {
        "name": "Kritisk psykologi",
        "concepts": ["deltagelse", "betingelser", "daglig livsførelse"],
        "focus": "daglig livsførelse, deltagelse og sociale betingelser",
        "method": "praksisforskning og analyse af handlemuligheder i hverdagslivet",
    },
    "sociocultural_poststructural_approaches": {
        "name": "Socialkonstruktionisme",
        "concepts": ["diskurs", "magt", "subjektivering"],
        "focus": "sprog, kategorier, magt, normer og subjektpositioner",
        "method": "diskursanalyse, genealogisk kritik og analyse af kategorisering",
    },
    "narrative_psychology": {
        "name": "Narrativ psykologi",
        "concepts": ["fortælling", "identitet", "livshistorie"],
        "focus": "livshistorie, mening, kulturelle fortællinger og identitet over tid",
        "method": "narrativ analyse af livshistorier, selvfortællinger og kulturelle fortælleformer",
    },
    "comparative_theory_analysis": {
        "name": "Tværgående teorisammenligning",
        "concepts": ["orienteringspunkter", "sammenligning", "personbegreb"],
        "focus": "systematisk sammenligning af personbegreb, metode og orienteringspunkter",
        "method": "tværgående begrebsanalyse på tværs af teorier",
    },
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


def _words(value: str) -> list[str]:
    return re.findall(r"\w+", value, flags=re.UNICODE)


def _clip(value: object, *, words: int = 18) -> str:
    text = re.sub(r"\s+", " ", _text(value)).strip()
    parts = re.findall(r"\S+", text)
    if len(parts) <= words:
        return text.rstrip(" .")
    return " ".join(parts[:words]).rstrip(".,;:")


def _sentence(value: object, *, words: int = 18) -> str:
    text = _clip(value, words=words)
    if not text:
        return ""
    return text if text.endswith((".", "?", "!")) else f"{text}."


def _join_terms(terms: list[str], *, max_terms: int = 2) -> str:
    compact: list[str] = []
    seen: set[str] = set()
    for term in terms:
        clean = _text(term)
        key = clean.casefold()
        if not clean or key in seen:
            continue
        compact.append(clean)
        seen.add(key)
        if len(compact) >= max_terms:
            break
    if not compact:
        return "centrale begreber"
    if len(compact) == 1:
        return compact[0]
    return f"{compact[0]} og {compact[1]}"


def _theory_ids_for_card(card: dict[str, Any], theory_ids: set[str]) -> list[str]:
    return sorted({tag for tag in _as_str_list(card.get("tags")) if tag in theory_ids})


def _display_name(row: dict[str, Any], card_text: str) -> str:
    override_name = _text(PROFILE_OVERRIDES.get(_text(row.get("theory_id")), {}).get("name"))
    if override_name:
        return override_name
    labels = _as_str_list(row.get("student_note_labels")) + _as_str_list(row.get("aliases"))
    for label in labels:
        if label and label.casefold() in card_text.casefold():
            return label
    return labels[0] if labels else _text(row.get("label")) or _text(row.get("theory_id"))


def _profile(row: dict[str, Any]) -> dict[str, Any]:
    theory_id = _text(row.get("theory_id"))
    override = PROFILE_OVERRIDES.get(theory_id, {})
    concepts = _as_str_list(override.get("concepts")) or _as_str_list(row.get("central_concepts"))[:3]
    return {
        "concepts": concepts,
        "focus": _text(override.get("focus")) or _clip(row.get("model_of_person"), words=16),
        "method": _text(override.get("method")) or _clip(row.get("method_evidence_style"), words=18),
    }


def _axis_for_card(card: dict[str, Any]) -> str:
    text = f"{card.get('front_text')} {card.get('back_text')}".casefold()
    checks = [
        ("essence_context", ("essens", "kontekst", "context")),
        ("determination", ("determination", "determiner", "årsag", "kausal")),
        ("agency", ("agency", "handle", "aktør", "valg", "frihed")),
        ("historicity", ("historicitet", "histor", "tid", "udvikling")),
    ]
    for axis, needles in checks:
        if any(needle in text for needle in needles):
            return axis
    return ""


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
    terms: list[str] = []
    source_ids = _as_str_list((row.get("source_grounding") or {}).get("representative_source_ids"))
    for source_id in source_ids[:4]:
        source_card = source_cards.get(source_id)
        analysis = source_card.get("analysis") if isinstance(source_card, dict) else {}
        if not isinstance(analysis, dict):
            continue
        for concept in _as_list(analysis.get("key_concepts")):
            term = _text(concept.get("term")) if isinstance(concept, dict) else ""
            if term and not re.search(r"\b(?:source|matrix|substrat|kilde)\b", term, flags=re.IGNORECASE):
                terms.append(term)
            if len(terms) >= 3:
                return terms
    return terms


def _concept_graph_distinctions(card: dict[str, Any], concept_graph: dict[str, Any]) -> list[dict[str, str]]:
    text = f"{card.get('front_text')} {card.get('back_text')}".casefold()
    matches: list[dict[str, str]] = []
    for distinction in _as_list(concept_graph.get("distinctions")):
        if not isinstance(distinction, dict):
            continue
        labels = [_text(distinction.get("label")), *_as_str_list(distinction.get("term_labels"))]
        if any(label and label.casefold() in text for label in labels):
            matches.append(
                {
                    "distinction_id": _text(distinction.get("distinction_id")),
                    "label": _text(distinction.get("label")),
                    "summary": _clip(distinction.get("summary"), words=20),
                }
            )
    return matches[:3]


def _support_for_substrate(
    *,
    row_entries: list[dict[str, Any]],
    source_cards: dict[str, dict[str, Any]],
    lecture_substrates: dict[str, dict[str, Any]],
    concept_distinctions: list[dict[str, str]],
    category_fields: list[str],
) -> list[dict[str, Any]]:
    support: list[dict[str, Any]] = []
    for entry in row_entries:
        row = entry["row"]
        theory_id = _text(row.get("theory_id"))
        for field in category_fields:
            support.append({"type": "matrix_field", "theory_id": theory_id, "field": field})
        for source_id in _as_str_list((row.get("source_grounding") or {}).get("representative_source_ids")):
            if source_id in source_cards:
                support.append(
                    {
                        "type": "source_card",
                        "source_id": source_id,
                        "fields": ["key_concepts", "distinctions", "likely_misunderstandings"],
                    }
                )
                break
        for lecture_key in _as_str_list(row.get("lecture_keys"))[:1]:
            if lecture_key in lecture_substrates:
                support.append(
                    {
                        "type": "lecture_substrate",
                        "lecture_key": lecture_key,
                        "fields": ["what_matters_more", "warnings", "top_down_course_relevance"],
                    }
                )
    if concept_distinctions:
        support.append(
            {
                "type": "concept_graph",
                "distinction_ids": [
                    distinction["distinction_id"] for distinction in concept_distinctions if distinction["distinction_id"]
                ],
            }
        )
    if len(row_entries) > 1:
        support.append({"type": "course_synthesis", "fields": ["theory_tradition_map", "distinction_map"]})
    return support


def _category_fields(card: dict[str, Any]) -> list[str]:
    category = _text(card.get("category_slug"))
    fields = list(CATEGORY_FIELD_MAP.get(category, ["course_summary"]))
    if category == "orienteringspunkter" and (axis := _axis_for_card(card)):
        fields = [f"orientation_points:{axis}", "model_of_person"]
    return fields


def _row_field_excerpt(row: dict[str, Any], field: str) -> object:
    if field.startswith("orientation_points:"):
        _, axis = field.split(":", 1)
        orientation_points = row.get("orientation_points") if isinstance(row.get("orientation_points"), dict) else {}
        return orientation_points.get(axis) if isinstance(orientation_points, dict) else None
    return row.get(field)


def _field_snapshot(row: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for field in fields:
        value = _row_field_excerpt(row, field)
        if value:
            snapshot[field] = value
    return snapshot


def _build_substrates(
    *,
    deck: dict[str, Any],
    matrix: dict[str, Any],
    source_cards: dict[str, dict[str, Any]],
    lecture_substrates: dict[str, dict[str, Any]],
    concept_graph: dict[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    rows_by_id = {
        _text(row.get("theory_id")): row
        for row in _as_list(matrix.get("rows"))
        if isinstance(row, dict) and _text(row.get("theory_id"))
    }
    substrates: list[dict[str, Any]] = []
    omissions: list[dict[str, str]] = []
    category_counts: Counter[str] = Counter()
    for card in _as_list(deck.get("cards")):
        if not isinstance(card, dict):
            continue
        card_text = f"{card.get('front_text')} {card.get('back_text')}"
        theory_ids = _theory_ids_for_card(card, set(rows_by_id))
        if len(theory_ids) > 1 and "comparative_theory_analysis" in theory_ids:
            theory_ids = [theory_id for theory_id in theory_ids if theory_id != "comparative_theory_analysis"]
        if not theory_ids:
            omissions.append({"card_id": _text(card.get("card_id")), "reason": "no mapped theory row"})
            continue
        fields = _category_fields(card)
        row_entries: list[dict[str, Any]] = []
        concept_terms: list[str] = []
        source_terms: list[str] = []
        for theory_id in theory_ids:
            row = rows_by_id[theory_id]
            profile = _profile(row)
            display_name = _display_name(row, card_text)
            row_concepts = _as_str_list(profile.get("concepts"))
            concept_terms.extend(row_concepts[:2])
            source_terms.extend(_source_terms_for_row(row, source_cards)[:2])
            row_entries.append(
                {
                    "theory_id": theory_id,
                    "theory_name": display_name,
                    "profile": profile,
                    "fields": _field_snapshot(row, fields),
                    "row": row,
                }
            )
        concept_distinctions = _concept_graph_distinctions(card, concept_graph)
        if concept_distinctions:
            concept_terms.extend(
                _text(distinction.get("label"))
                for distinction in concept_distinctions
                if _text(distinction.get("label"))
            )
        support = _support_for_substrate(
            row_entries=row_entries,
            source_cards=source_cards,
            lecture_substrates=lecture_substrates,
            concept_distinctions=concept_distinctions,
            category_fields=fields,
        )
        category = _text(card.get("category_slug"))
        category_counts[category] += 1
        substrates.append(
            {
                "card_id": _text(card.get("card_id")),
                "old_front_text": _text(card.get("front_text")),
                "old_back_text": _text(card.get("back_text")),
                "category_slug": category,
                "theory_ids": theory_ids,
                "theory_names": [entry["theory_name"] for entry in row_entries],
                "concept_terms": list(dict.fromkeys([term for term in concept_terms if term]))[:6],
                "source_card_terms": list(dict.fromkeys([term for term in source_terms if term]))[:4],
                "concept_distinctions": concept_distinctions,
                "field_support": [
                    {
                        "theory_id": entry["theory_id"],
                        "theory_name": entry["theory_name"],
                        "fields": entry["fields"],
                    }
                    for entry in row_entries
                ],
                "support": support,
                "confidence": "high" if any(item.get("type") == "source_card" for item in support) else "medium",
            }
        )
    return {
        "version": 1,
        "artifact_type": "personlighedspsykologi_flashcard_background_substrates",
        "subject_slug": "personlighedspsykologi",
        "generated_at": generated_at,
        "source_policy": {
            "raw_student_notes_used": False,
            "raw_source_files_used": False,
            "processed_matrix_used": True,
            "processed_course_intelligence_used": True,
        },
        "stats": {
            "deck_card_count": int(deck.get("card_count") or 0),
            "substrate_count": len(substrates),
            "omitted_count": len(omissions),
            "category_counts": dict(sorted(category_counts.items())),
        },
        "substrates": substrates,
        "omissions": omissions,
    }


def _first_field(entry: dict[str, Any], field_name: str) -> object:
    fields = entry.get("fields") if isinstance(entry.get("fields"), dict) else {}
    value = fields.get(field_name)
    if value:
        return value
    for key, candidate in fields.items():
        if str(key).startswith(field_name):
            return candidate
    return None


def _orientation_phrase(entry: dict[str, Any]) -> str:
    return _entry_focus(entry)


def _entry_focus(entry: dict[str, Any]) -> str:
    profile = entry.get("profile") if isinstance(entry.get("profile"), dict) else {}
    return _text(profile.get("focus")) or _clip(_first_field(entry, "model_of_person"), words=16)


def _entry_method(entry: dict[str, Any]) -> str:
    profile = entry.get("profile") if isinstance(entry.get("profile"), dict) else {}
    return _text(profile.get("method")) or _clip(_first_field(entry, "method_evidence_style"), words=16)


def _entry_concepts(entry: dict[str, Any]) -> list[str]:
    profile = entry.get("profile") if isinstance(entry.get("profile"), dict) else {}
    return _as_str_list(profile.get("concepts"))


def _clean_background(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    cleaned = re.sub(r"\s+([?.!,;:])", r"\1", cleaned)
    return cleaned


def _single_background(substrate: dict[str, Any], entry: dict[str, Any]) -> str:
    category = _text(substrate.get("category_slug"))
    name = _text(entry.get("theory_name"))
    focus = _entry_focus(entry)
    method = _entry_method(entry)
    concepts = _join_terms(_entry_concepts(entry))
    model = _clip(_first_field(entry, "model_of_person"), words=18) or focus
    personality_model = _clip(_first_field(entry, "personality_or_subjectivity_model"), words=18) or focus
    if category == "orienteringspunkter":
        axis = _axis_for_card({"front_text": substrate.get("old_front_text"), "back_text": substrate.get("old_back_text")})
        orientation = _orientation_phrase(entry) or focus
        return _clean_background(
            f"{name} placerer {AXIS_LABELS.get(axis, 'orienteringspunktet')} gennem {orientation}. "
            f"Begreber som {concepts} viser, om teorien vægter indre dynamik, social kontekst, handlemulighed eller historisk formning. "
            f"Derfor hænger orienteringspunktet direkte sammen med personbegrebet."
        )
    if category == "metode-og-evidens":
        return _clean_background(
            f"{name} bruger {method}, fordi personlighed her forstås gennem {focus}. "
            f"Metoden er derfor en del af teorien: den afgør, om {concepts} bliver noget, man måler, fortolker eller analyserer i praksis."
        )
    if category == "styrker-og-begraensninger":
        return _clean_background(
            f"{name}s styrke følger af fokus på {focus}. Teorien kan gøre {concepts} tydelige, men samme fokus kan også gøre andre forklaringer mindre synlige. "
            f"Afvejningen er vigtig, fordi teorien både åbner og afgrænser, hvad personlighed kan forklares som."
        )
    if category == "eksamenstraps":
        return _clean_background(
            f"Misforståelsen opstår, når {name} gøres for enkel. Traditionen bør forstås gennem {focus}, ikke som en løs påstand uden personbegreb. "
            f"{concepts} hjælper med at holde både teoriens pointe og dens begrænsning synlig."
        )
    return _clean_background(
        f"{name} forstår personlighed gennem {focus}. Derfor er {concepts} ikke løse etiketter; de markerer, hvor teorien placerer personens stabilitet, forandring og handlemuligheder. "
        f"Det giver forklaringen en bestemt retning."
    )


def _comparison_background(substrate: dict[str, Any], entries: list[dict[str, Any]]) -> str:
    names = [_text(entry.get("theory_name")) for entry in entries]
    concepts = [_join_terms(_entry_concepts(entry), max_terms=1) for entry in entries]
    if len(entries) == 2:
        first, second = entries
        first_name, second_name = names
        shared_language = "fællesnævner" in (
            f"{substrate.get('old_front_text')} {substrate.get('old_back_text')}".casefold()
        )
        relation = "Fællesnævneren" if shared_language else "Kontrasten"
        return _clean_background(
            f"{first_name} forklarer personlighed gennem {_entry_focus(first)}. "
            f"{second_name} flytter tyngden til {_entry_focus(second)}. "
            f"{relation} ligger i, hvor personen placeres: {concepts[0]} hos {first_name} over for {concepts[1]} hos {second_name}."
        )
    compact = "; ".join(
        f"{name}: {_entry_focus(entry)}"
        for name, entry in zip(names[:3], entries[:3], strict=False)
    )
    concept_text = _join_terms([term for entry in entries for term in _entry_concepts(entry)], max_terms=2)
    return _clean_background(
        f"Sammenligningen samler flere forklaringspunkter: {compact}. "
        f"Forskellen ligger i, om personlighed forstås via {concept_text}, konkrete handlinger eller historiske betingelser. "
        f"Det holder personbegreb, metode og orienteringspunkt adskilt."
    )


def _background_from_substrate(substrate: dict[str, Any]) -> str:
    entries = [
        {
            "theory_id": support.get("theory_id"),
            "theory_name": support.get("theory_name"),
            "fields": support.get("fields"),
            "profile": PROFILE_OVERRIDES.get(str(support.get("theory_id") or ""), {}),
        }
        for support in _as_list(substrate.get("field_support"))
        if isinstance(support, dict)
    ]
    if not entries:
        raise FlashcardBackgroundError(f"No field support for {substrate.get('card_id')}")
    if len(entries) > 1 or _text(substrate.get("category_slug")) == "sammenligninger":
        return _comparison_background(substrate, entries)
    return _single_background(substrate, entries[0])


def build_background_payload(*, substrate_payload: dict[str, Any], generated_at: str) -> dict[str, Any]:
    backgrounds: list[dict[str, Any]] = []
    confidence_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    rejected: list[dict[str, str]] = []
    for substrate in _as_list(substrate_payload.get("substrates")):
        if not isinstance(substrate, dict):
            continue
        try:
            background_text = _background_from_substrate(substrate)
        except FlashcardBackgroundError as exc:
            rejected.append({"card_id": _text(substrate.get("card_id")), "reason": str(exc)})
            continue
        confidence = _text(substrate.get("confidence")) or "medium"
        category_counts[_text(substrate.get("category_slug"))] += 1
        confidence_counts[confidence] += 1
        backgrounds.append(
            {
                "card_id": _text(substrate.get("card_id")),
                "old_front_text": _text(substrate.get("old_front_text")),
                "old_back_text": _text(substrate.get("old_back_text")),
                "background_text": background_text,
                "theory_names": _as_str_list(substrate.get("theory_names")),
                "concept_terms": _as_str_list(substrate.get("concept_terms"))[:6],
                "support": _as_list(substrate.get("support")),
                "confidence": confidence,
            }
        )
    payload = {
        "version": 1,
        "artifact_type": "personlighedspsykologi_flashcard_background_overlays",
        "subject_slug": "personlighedspsykologi",
        "generated_at": generated_at,
        "scope": "Optional substrate-backed background explanations for live personality flashcards.",
        "source_policy": {
            "learner_facing_sources_named": False,
            "matrix_support_required": True,
            "source_intelligence_used_as_support": True,
            "raw_student_notes_used": False,
            "raw_source_files_used": False,
        },
        "quality_policy": {
            "generic_card_meta_rejected": True,
            "comparison_theory_names_required": True,
            "concept_term_required": True,
            "backgrounds_are_optional": True,
        },
        "stats": {
            "background_count": len(backgrounds),
            "deck_card_count": int((substrate_payload.get("stats") or {}).get("deck_card_count") or 0),
            "substrate_count": int((substrate_payload.get("stats") or {}).get("substrate_count") or 0),
            "rejected_count": len(rejected),
            "category_counts": dict(sorted(category_counts.items())),
            "confidence_counts": dict(sorted(confidence_counts.items())),
        },
        "backgrounds": backgrounds,
        "rejected": rejected,
    }
    validate_flashcard_background_payload(payload)
    return payload


def render_quality_report(*, substrate_payload: dict[str, Any], background_payload: dict[str, Any]) -> str:
    stats = background_payload.get("stats") if isinstance(background_payload.get("stats"), dict) else {}
    lines = [
        "# Flashcard Background Quality Report",
        "",
        f"Generated: `{background_payload.get('generated_at')}`",
        "",
        "## Rubric",
        "",
        "- Explains the conceptual reason behind the answer, not the purpose of the card.",
        "- Uses at least one concrete concept from the substrate.",
        "- Comparison cards name the compared theories and state the contrast or common axis.",
        "- Does not expose hidden generation provenance or local/source-note details.",
        "- Rejects generic study-coaching phrases such as `kortet træner` and `mundtligt svar`.",
        "",
        "## Deterministic Gate",
        "",
        f"- Deck cards: {stats.get('deck_card_count')}",
        f"- Substrates: {stats.get('substrate_count')}",
        f"- Backgrounds accepted: {stats.get('background_count')}",
        f"- Backgrounds rejected: {stats.get('rejected_count')}",
        f"- Confidence counts: `{stats.get('confidence_counts')}`",
        f"- Category counts: `{stats.get('category_counts')}`",
        "",
        "## Accepted Examples",
        "",
    ]
    for background in _as_list(background_payload.get("backgrounds"))[:20]:
        if not isinstance(background, dict):
            continue
        lines.extend(
            [
                f"### {html.escape(_text(background.get('card_id')))}",
                "",
                f"Question: {html.escape(_text(background.get('old_front_text')))}",
                "",
                f"Answer: {html.escape(_text(background.get('old_back_text')))}",
                "",
                f"Background: {html.escape(_text(background.get('background_text')))}",
                "",
            ]
        )
    rejected = _as_list(background_payload.get("rejected"))
    omissions = _as_list(substrate_payload.get("omissions"))
    if rejected or omissions:
        lines.extend(["## Omitted Or Rejected", ""])
        for item in rejected[:50]:
            if isinstance(item, dict):
                lines.append(f"- `{item.get('card_id')}`: {item.get('reason')}")
        for item in omissions[:50]:
            if isinstance(item, dict):
                lines.append(f"- `{item.get('card_id')}`: {item.get('reason')}")
        lines.append("")
    lines.extend(
        [
            "## Gemini Review Plan",
            "",
            "Use the same rubric above for the Gemini review. Gemini should judge factual usefulness,",
            "answer-specificity, wording, and whether `Baggrund` should be shown, revised, or omitted.",
            "Duplication with other decks is not a rejection criterion.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--deck-path", type=Path, default=DEFAULT_DECK_PATH)
    parser.add_argument("--matrix-path", type=Path, default=DEFAULT_MATRIX_PATH)
    parser.add_argument("--theory-map-path", type=Path, default=DEFAULT_THEORY_MAP_PATH)
    parser.add_argument("--concept-graph-path", type=Path, default=DEFAULT_CONCEPT_GRAPH_PATH)
    parser.add_argument("--source-cards-dir", type=Path, default=DEFAULT_SOURCE_CARDS_DIR)
    parser.add_argument("--revised-lecture-dir", type=Path, default=DEFAULT_REVISED_LECTURE_DIR)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_FLASHCARD_BACKGROUNDS_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_FLASHCARD_BACKGROUNDS_MD)
    parser.add_argument("--substrates-json", type=Path, default=DEFAULT_FLASHCARD_BACKGROUND_SUBSTRATES_JSON)
    parser.add_argument("--quality-report-md", type=Path, default=DEFAULT_FLASHCARD_BACKGROUND_QA_MD)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    generated_at = utc_now_iso()
    deck = _load_json(_resolve(args.deck_path, repo_root))
    matrix = _load_json(_resolve(args.matrix_path, repo_root))
    concept_graph = _load_json(_resolve(args.concept_graph_path, repo_root))
    # The theory map is loaded as a freshness/input check; row details come from the validated matrix.
    _load_json(_resolve(args.theory_map_path, repo_root))
    source_cards = _source_lookup(_resolve(args.source_cards_dir, repo_root))
    lecture_substrates = _lecture_lookup(_resolve(args.revised_lecture_dir, repo_root))
    substrate_payload = _build_substrates(
        deck=deck,
        matrix=matrix,
        source_cards=source_cards,
        lecture_substrates=lecture_substrates,
        concept_graph=concept_graph,
        generated_at=generated_at,
    )
    background_payload = build_background_payload(substrate_payload=substrate_payload, generated_at=generated_at)
    markdown = render_flashcard_background_markdown(background_payload)
    quality_report = render_quality_report(
        substrate_payload=substrate_payload,
        background_payload=background_payload,
    )
    if not args.dry_run:
        write_json_stably(_resolve(args.substrates_json, repo_root), substrate_payload)
        write_json_stably(_resolve(args.output_json, repo_root), background_payload)
        _resolve(args.output_md, repo_root).write_text(markdown + "\n", encoding="utf-8")
        _resolve(args.quality_report_md, repo_root).write_text(quality_report + "\n", encoding="utf-8")
    stats = background_payload["stats"]
    print(
        "generated substrate-backed flashcard backgrounds "
        f"(accepted={stats['background_count']}, rejected={stats['rejected_count']}, "
        f"confidence={stats['confidence_counts']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
