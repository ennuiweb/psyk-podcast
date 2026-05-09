"""Locale-aware prompt rendering helpers for NotebookLM generation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_PROMPT_LOCALIZATION = {
    "enabled": False,
    "default_locale": "en",
    "locales": {},
}

_DEFAULT_LOCALE_ENTRY = {
    "prompt_overrides_path": "",
    "course_context_translations_path": "",
    "omit_untranslated_course_context": False,
    "fail_on_missing_course_context_translations": False,
}

PROMPT_UI_STRINGS = {
    "en": {
        "audio_intro_template": "Create an audio overview for {audience}.",
        "course_label": "Course",
        "course_context_heading_default": "Course-aware lecture context:",
        "course_context_rules_heading_default": "Course understanding usage:",
        "interpretive_roles_heading": "Interpretive roles:",
        "reading_primary_role": (
            "Reading: Use this reading for the actual claims, distinctions, evidence, "
            "and qualifications."
        ),
        "lecture_slides_label": "Lecture slides",
        "seminar_slides_label": "Seminar slides",
        "readings_label": "Readings",
        "target_slide_role_lecture": (
            "Target slide deck: Use it to reconstruct sequence, framing, and what "
            "the lecture is emphasizing."
        ),
        "target_slide_role_seminar": (
            "Target slide deck: Use it to reconstruct application, clarification, "
            "and discussion priorities."
        ),
        "target_slide_role_exercise": (
            "Target slide deck: Use it to reconstruct what is being practiced, "
            "clarified, or stress-tested."
        ),
        "target_source_short_slide": (
            "Target source: Compress around the one or two ideas the slide framing "
            "makes most important."
        ),
        "target_source_short_other": (
            "Target source: Compress around the one or two ideas this source "
            "contributes most decisively."
        ),
        "focus_heading": "Focus on:",
        "tone_label": "Tone",
        "additional_instructions_heading": "Additional instructions:",
        "external_pre_analysis_heading_default": "External pre-analysis:",
        "slide_short_reconstruct": (
            "Because the source is a slide deck, reconstruct the argumentative line "
            "instead of paraphrasing bullet fragments."
        ),
        "report_output_requirements_heading": "Output requirements:",
        "report_output_requirements_items": [
            "Keep the main explanatory body to roughly one page.",
            "Explain structure before detail so the student can orient themselves quickly.",
            (
                "Use short quotes sparingly and only when they genuinely help the "
                "student locate key moments in the original."
            ),
            "Do not fabricate quotations or page references.",
        ],
    },
    "da": {
        "audio_intro_template": "Lav en lydgennemgang til {audience}.",
        "course_label": "Kursus",
        "course_context_heading_default": "Kursusbevidst forelaesningskontekst:",
        "course_context_rules_heading_default": "Saadan bruges kursuskonteksten:",
        "interpretive_roles_heading": "Fortolkningsroller:",
        "reading_primary_role": (
            "Laesning: Brug denne laesning til de faktiske paastande, distinktioner, "
            "belaeg og kvalifikationer."
        ),
        "lecture_slides_label": "Forelaesningsslides",
        "seminar_slides_label": "Seminarslides",
        "readings_label": "Laesninger",
        "target_slide_role_lecture": (
            "Det relevante slidedeck: Brug det til at rekonstruere raekkefolge, "
            "indramning og hvad forelaesningen laegger vaegt paa."
        ),
        "target_slide_role_seminar": (
            "Det relevante slidedeck: Brug det til at rekonstruere anvendelse, "
            "afklaring og diskussionsprioriteter."
        ),
        "target_slide_role_exercise": (
            "Det relevante slidedeck: Brug det til at rekonstruere hvad der oeves, "
            "afklares eller stresstestes."
        ),
        "target_source_short_slide": (
            "Maal-kilde: Komprimer omkring den ene eller to ideer som slideframing "
            "goer vigtigst."
        ),
        "target_source_short_other": (
            "Maal-kilde: Komprimer omkring den ene eller to ideer som denne kilde "
            "bidrager mest afgoerende med."
        ),
        "focus_heading": "Fokuser paa:",
        "tone_label": "Tone",
        "additional_instructions_heading": "Yderligere instruktioner:",
        "external_pre_analysis_heading_default": "Ekstern foranalyse:",
        "slide_short_reconstruct": (
            "Fordi kilden er et slidedeck, skal du rekonstruere argumentationslinjen "
            "i stedet for at parafrasere fragmenterede punktnedslag."
        ),
        "report_output_requirements_heading": "Krav til output:",
        "report_output_requirements_items": [
            "Hold den centrale forklarende hoveddel paa omtrent en side.",
            "Forklar struktur foer detalje, saa den studerende hurtigt kan orientere sig.",
            (
                "Brug korte citater sparsomt og kun naar de reelt hjaelper den "
                "studerende med at finde vigtige steder i originalen."
            ),
            "Opfind ikke citater eller sidetalshenvisninger.",
        ],
    },
}

COURSE_CONTEXT_UI_STRINGS = {
    "en": {
        "section_course_frame": "## Course and lecture frame",
        "section_source_character": "## Source character",
        "section_lecture_synthesis": "## Lecture synthesis",
        "section_teaching_context": "## Teaching context",
        "section_reading_map": "## Reading map",
        "section_semantic_guidance": "## Semantic guidance",
        "section_podcast_substrate": "## Podcast substrate",
        "section_target_source_fit": "## Target source fit",
        "section_grounding_rules": "## Grounding rules",
        "current_lecture_template": "- Current lecture: {lecture}.",
        "current_lecture_theme_template": "- Current lecture theme: {theme}.",
        "course_position_template": (
            "- Course position: lecture {sequence_index} of {total_lectures}; this "
            "sits in the {stage} portion of the course."
        ),
        "builds_on_template": "- It builds on: {items}.",
        "leads_into_template": "- It leads into: {items}.",
        "broader_course_arc_template": "- Broader course arc in play: {items}.",
        "course_overview_excerpt_template": "- Course overview excerpt: {excerpt}.",
        "slide_lecture_template": "- Forelaesning slides frame the lecture through: {items}.",
        "slide_seminar_template": (
            "- Seminar slides operationalize or test the material through: {items}."
        ),
        "slide_exercise_template": "- Exercise slides reinforce the block through: {items}.",
        "ranked_source_emphasis_template": "- Ranked source emphasis: {items}.",
        "course_concepts_template": "- Course concepts in play: {items}.",
        "theory_frame_template": "- Theory frame: {items}.",
        "cross_lecture_tensions_template": "- Cross-lecture tensions to keep explicit: {items}.",
        "podcast_angle_template": "- Podcast angle: {text}",
        "must_cover_template": "- Must cover: {items}.",
        "avoid_template": "- Avoid: {items}.",
        "grounding_template": "- Grounding: {items}.",
        "selected_concepts_template": "- Selected concepts: {items}.",
        "selected_tensions_template": "- Selected tensions: {items}.",
        "source_selection_template": "- Source selection: {items}.",
        "substrate_grounding_notes_template": "- Substrate grounding notes: {items}.",
        "no_source_character_line": (
            "- Treat this as a lecture-block synthesis across multiple readings, "
            "informed by teaching framing rather than as one uniform text."
        ),
        "lecture_slide_source_line_1": (
            "- This is a lecture slide deck: fragmentary teaching scaffolding for "
            "the theme '{title}'."
        ),
        "lecture_slide_source_line_2": (
            "- Treat the deck as a guide to sequence, emphasis, and framing rather "
            "than as a complete prose source."
        ),
        "seminar_slide_source_line_1": (
            "- This is a seminar slide deck: application- and discussion-oriented "
            "teaching material for '{title}'."
        ),
        "seminar_slide_source_line_2": (
            "- Expect prompts, exercises, and simplifications that presuppose the "
            "lecture and readings."
        ),
        "exercise_slide_source_line_1": (
            "- This is an exercise slide deck: practice-oriented material for '{title}'."
        ),
        "exercise_slide_source_line_2": (
            "- Use it to reconstruct what is being trained or clarified, not as a "
            "standalone theory text."
        ),
        "generic_slide_source_line_1": "- This is a slide deck rather than a full prose source.",
        "generic_slide_source_line_2": (
            "- Reconstruct structure and emphasis without overstating what the slides "
            "explicitly say."
        ),
        "textbook_source_line_1": (
            "- This is a textbook chapter: an orienting or field-mapping text for '{title}'."
        ),
        "textbook_source_line_2": (
            "- Use it to frame the lecture theme, key concepts, and major distinctions "
            "rather than expecting one narrow empirical claim."
        ),
        "article_source_line_1": (
            "- This is an assigned article or chapter centered on the specific "
            "contribution '{title}'."
        ),
        "article_source_line_2": (
            "- Treat it as one perspective on the lecture theme, with its own "
            "argument, emphasis, and delimitations."
        ),
        "target_reading_template": "- Target source: {title}.",
        "target_reading_scope_line": (
            "- Use this reading as one contribution to the lecture block, not as the whole block."
        ),
        "target_reading_emphasis_template": "- Source-specific emphasis: {text}",
        "target_slide_template": (
            "- Target source: {subcategory} slide deck '{title}'. Treat it as teaching "
            "structure, not as a complete statement of the theory."
        ),
        "target_slide_followup": (
            "- Reconstruct the lecturer's sequencing and emphasis, then anchor "
            "substantive claims in the lecture block and readings where possible."
        ),
        "grounding_rules": [
            (
                "- Treat lecture-level and course-level framing as prioritization aids "
                "rather than replacement for what the source explicitly says."
            ),
            (
                "- Let slide framing help decide emphasis and likely misunderstandings, "
                "but keep claims anchored in the supplied source material."
            ),
            (
                "- Use slide titles and neighboring lectures to orient the explanation, "
                "but do not attribute unsupported claims to authors or lecturers."
            ),
        ],
    },
    "da": {
        "section_course_frame": "## Kursus- og forelaesningsramme",
        "section_source_character": "## Kildekarakter",
        "section_lecture_synthesis": "## Forelaesningssyntese",
        "section_teaching_context": "## Undervisningskontekst",
        "section_reading_map": "## Laesekort",
        "section_semantic_guidance": "## Semantisk vejledning",
        "section_podcast_substrate": "## Podcastsubstrat",
        "section_target_source_fit": "## Maal-kildens placering",
        "section_grounding_rules": "## Grounding-regler",
        "current_lecture_template": "- Aktuel forelaesning: {lecture}.",
        "current_lecture_theme_template": "- Aktuelt forelaesningstema: {theme}.",
        "course_position_template": (
            "- Kursusposition: forelaesning {sequence_index} af {total_lectures}; "
            "den ligger i den {stage} del af kurset."
        ),
        "builds_on_template": "- Bygger videre paa: {items}.",
        "leads_into_template": "- Leder videre til: {items}.",
        "broader_course_arc_template": "- Bredere kursusbue i spil: {items}.",
        "course_overview_excerpt_template": "- Uddrag fra kursusoversigt: {excerpt}.",
        "slide_lecture_template": "- Forelaesningsslides indrammer forelaesningen gennem: {items}.",
        "slide_seminar_template": "- Seminarslides operationaliserer eller afproever materialet gennem: {items}.",
        "slide_exercise_template": "- Oevelsesslides understoetter blokken gennem: {items}.",
        "ranked_source_emphasis_template": "- Rangordnet kildevaegt: {items}.",
        "course_concepts_template": "- Kursusbegreber i spil: {items}.",
        "theory_frame_template": "- Teoriramme: {items}.",
        "cross_lecture_tensions_template": "- Tvaerforelaesningsspaendinger der boer holdes tydelige: {items}.",
        "podcast_angle_template": "- Podcastvinkel: {text}",
        "must_cover_template": "- Skal daekkes: {items}.",
        "avoid_template": "- Undgaa: {items}.",
        "grounding_template": "- Grounding: {items}.",
        "selected_concepts_template": "- Udvalgte begreber: {items}.",
        "selected_tensions_template": "- Udvalgte spaendinger: {items}.",
        "source_selection_template": "- Kildeudvaelgelse: {items}.",
        "substrate_grounding_notes_template": "- Grounding-noter fra substratet: {items}.",
        "no_source_character_line": (
            "- Behandl dette som en syntese af en forelaesningsblok paa tvaers af "
            "flere laesninger, informeret af undervisningsframing snarere end som "
            "en ensartet tekst."
        ),
        "lecture_slide_source_line_1": (
            "- Dette er et forelaesningsslidedeck: fragmentarisk undervisningsstillas "
            "for temaet '{title}'."
        ),
        "lecture_slide_source_line_2": (
            "- Behandl decket som en guide til raekkefolge, vaegtlaegning og framing "
            "snarere end som en fuldstaendig prosakilde."
        ),
        "seminar_slide_source_line_1": (
            "- Dette er et seminarslidedeck: anvendelses- og diskussionsorienteret "
            "undervisningsmateriale til '{title}'."
        ),
        "seminar_slide_source_line_2": (
            "- Forvent prompts, oevelser og forenklinger som forudsaetter "
            "forelaesningen og laesningerne."
        ),
        "exercise_slide_source_line_1": (
            "- Dette er et oevelsesslidedeck: praksisorienteret materiale til '{title}'."
        ),
        "exercise_slide_source_line_2": (
            "- Brug det til at rekonstruere hvad der traenes eller afklares, ikke "
            "som en selvstaendig teoritekst."
        ),
        "generic_slide_source_line_1": "- Dette er et slidedeck snarere end en fuld prosakilde.",
        "generic_slide_source_line_2": (
            "- Rekonstruer struktur og vaegtlaegning uden at overdrive hvad slidesene "
            "udtrykkeligt siger."
        ),
        "textbook_source_line_1": (
            "- Dette er et grundbogskapitel: en orienterende eller feltkortlaeggende "
            "tekst for '{title}'."
        ),
        "textbook_source_line_2": (
            "- Brug det til at indramme forelaesningstemaet, centrale begreber og "
            "store distinktioner frem for at forvente en snaever empirisk paastand."
        ),
        "article_source_line_1": (
            "- Dette er en tildelt artikel eller et kapitel centreret om det "
            "specifikke bidrag '{title}'."
        ),
        "article_source_line_2": (
            "- Behandl den som et perspektiv paa forelaesningstemaet med sin egen "
            "argumentation, vaegtlaegning og afgraensning."
        ),
        "target_reading_template": "- Maal-kilde: {title}.",
        "target_reading_scope_line": (
            "- Brug denne laesning som et bidrag til forelaesningsblokken, ikke som hele blokken."
        ),
        "target_reading_emphasis_template": "- Kildespecifik vaegtlaegning: {text}",
        "target_slide_template": (
            "- Maal-kilde: {subcategory}-slidedecket '{title}'. Behandl det som "
            "undervisningsstruktur, ikke som en fuldstaendig udlaegning af teorien."
        ),
        "target_slide_followup": (
            "- Rekonstruer underviserens sekvensering og vaegtlaegning, og forankr "
            "derefter substantielle paastande i forelaesningsblokken og laesningerne "
            "hvor det er muligt."
        ),
        "grounding_rules": [
            (
                "- Behandl framing paa forelaesnings- og kursusniveau som "
                "prioriteringshjaelp frem for en erstatning for hvad kilden "
                "udtrykkeligt siger."
            ),
            (
                "- Lad slideframing hjaelpe med at afgoere vaegt og sandsynlige "
                "misforstaaelser, men hold paastande forankret i det leverede kildemateriale."
            ),
            (
                "- Brug slidetitler og naerliggende forelaesninger til at orientere "
                "forklaringen, men tilskriv ikke forfattere eller undervisere "
                "udokumenterede paastande."
            ),
        ],
    },
}

_ENGLISH_HINT_WORDS = {
    "the",
    "and",
    "with",
    "from",
    "that",
    "this",
    "these",
    "those",
    "into",
    "through",
    "across",
    "between",
    "rather",
    "than",
    "not",
    "what",
    "where",
    "which",
    "because",
    "student",
    "students",
    "lecture",
    "reading",
    "readings",
    "course",
    "slides",
    "slide",
    "source",
    "sources",
    "material",
    "theory",
    "trait",
    "traits",
    "state",
    "states",
    "personality",
    "psychology",
    "development",
    "construct",
    "context",
    "grounding",
    "selected",
    "avoid",
    "frame",
    "overview",
}

_DANISH_HINT_WORDS = {
    "og",
    "det",
    "der",
    "som",
    "skal",
    "ikke",
    "den",
    "de",
    "forelaesning",
    "forelaesningen",
    "laesning",
    "laesninger",
    "kursus",
    "kilde",
    "slides",
    "slide",
    "materialet",
    "teori",
    "teorier",
    "personlighed",
    "psykologi",
    "udvikling",
    "begreb",
    "forankring",
    "undgaa",
    "oversigt",
}


@dataclass(frozen=True)
class PromptLocalization:
    locale: str
    prompt_ui: dict[str, Any]
    course_context_ui: dict[str, Any]
    prompt_overrides: dict[str, Any]
    course_context_translations: dict[str, str]
    omit_untranslated_course_context: bool
    fail_on_missing_course_context_translations: bool


def _deep_copy(value: object) -> object:
    if isinstance(value, dict):
        return {key: _deep_copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_deep_copy(item) for item in value]
    return value


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(dict(merged[key]), value)
        else:
            merged[key] = _deep_copy(value)
    return merged


def normalize_prompt_localization(raw: object) -> dict[str, Any]:
    normalized = _deep_copy(DEFAULT_PROMPT_LOCALIZATION)
    if raw in (None, ""):
        return normalized
    if not isinstance(raw, dict):
        raise SystemExit("prompt_localization must be an object.")

    if "enabled" in raw:
        if not isinstance(raw["enabled"], bool):
            raise SystemExit("prompt_localization.enabled must be true or false.")
        normalized["enabled"] = raw["enabled"]
    if "default_locale" in raw:
        default_locale = str(raw["default_locale"] or "").strip().lower()
        if not default_locale:
            raise SystemExit("prompt_localization.default_locale must be a non-empty string.")
        normalized["default_locale"] = default_locale

    locales_raw = raw.get("locales")
    if locales_raw in (None, ""):
        return normalized
    if not isinstance(locales_raw, dict):
        raise SystemExit("prompt_localization.locales must be an object keyed by locale.")

    locales: dict[str, dict[str, Any]] = {}
    for raw_locale, raw_entry in locales_raw.items():
        locale = str(raw_locale or "").strip().lower()
        if not locale:
            raise SystemExit("prompt_localization.locales contains an empty locale key.")
        if not isinstance(raw_entry, dict):
            raise SystemExit(f"prompt_localization.locales.{locale} must be an object.")
        entry = _deep_copy(_DEFAULT_LOCALE_ENTRY)
        for field in ("prompt_overrides_path", "course_context_translations_path"):
            if field in raw_entry:
                value = raw_entry[field]
                if not isinstance(value, str):
                    raise SystemExit(f"prompt_localization.locales.{locale}.{field} must be a string.")
                entry[field] = value.strip()
        for field in (
            "omit_untranslated_course_context",
            "fail_on_missing_course_context_translations",
        ):
            if field in raw_entry:
                value = raw_entry[field]
                if not isinstance(value, bool):
                    raise SystemExit(f"prompt_localization.locales.{locale}.{field} must be true or false.")
                entry[field] = value
        locales[locale] = entry
    normalized["locales"] = locales
    return normalized


def _resolve_config_path(*, repo_root: Path, prompt_config_path: Path, value: str) -> Path | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    candidate = Path(cleaned).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    config_relative = (prompt_config_path.parent / candidate).resolve()
    if config_relative.exists():
        return config_relative
    return (repo_root / candidate).resolve()


def _read_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"unable to parse localization file: {path}") from exc


def _load_prompt_overrides(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    if not path.exists() or not path.is_file():
        raise RuntimeError(f"prompt localization overrides not found: {path}")
    payload = _read_json_file(path)
    if not isinstance(payload, dict):
        raise RuntimeError(f"prompt localization overrides must be an object: {path}")
    return payload


def _load_course_context_translations(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    if not path.exists() or not path.is_file():
        raise RuntimeError(f"course-context translations not found: {path}")
    payload = _read_json_file(path)
    raw_map = payload.get("translations") if isinstance(payload, dict) else None
    if raw_map is None and isinstance(payload, dict):
        raw_map = payload
    if not isinstance(raw_map, dict):
        raise RuntimeError(f"course-context translations must be an object: {path}")

    translations: dict[str, str] = {}
    for raw_source, raw_value in raw_map.items():
        source = " ".join(str(raw_source or "").split())
        if not source:
            continue
        if isinstance(raw_value, dict):
            translated = str(raw_value.get("translation") or "").strip()
        else:
            translated = str(raw_value or "").strip()
        if translated:
            translations[source] = translated
    return translations


def resolve_prompt_localization(
    *,
    repo_root: Path,
    prompt_config_path: Path,
    config: dict[str, Any],
    prompt_locale: str | None,
) -> PromptLocalization:
    locale = str(prompt_locale or config.get("default_locale") or "en").strip().lower() or "en"
    locale_cfg = config.get("locales", {}).get(locale, {}) if config.get("enabled", False) else {}

    prompt_ui = _deep_copy(PROMPT_UI_STRINGS.get(locale, PROMPT_UI_STRINGS["en"]))
    course_context_ui = _deep_copy(COURSE_CONTEXT_UI_STRINGS.get(locale, COURSE_CONTEXT_UI_STRINGS["en"]))
    prompt_overrides = _load_prompt_overrides(
        _resolve_config_path(
            repo_root=repo_root,
            prompt_config_path=prompt_config_path,
            value=str(locale_cfg.get("prompt_overrides_path") or ""),
        )
    )
    course_context_translations = _load_course_context_translations(
        _resolve_config_path(
            repo_root=repo_root,
            prompt_config_path=prompt_config_path,
            value=str(locale_cfg.get("course_context_translations_path") or ""),
        )
    )

    return PromptLocalization(
        locale=locale,
        prompt_ui=prompt_ui,
        course_context_ui=course_context_ui,
        prompt_overrides=prompt_overrides,
        course_context_translations=course_context_translations,
        omit_untranslated_course_context=bool(
            locale_cfg.get("omit_untranslated_course_context", False)
        ),
        fail_on_missing_course_context_translations=bool(
            locale_cfg.get("fail_on_missing_course_context_translations", False)
        ),
    )


def localize_sections(
    base_sections: dict[str, Any],
    localization: PromptLocalization | None,
) -> dict[str, Any]:
    localized = {key: _deep_copy(value) for key, value in base_sections.items()}
    if localization is None or not localization.prompt_overrides:
        return localized
    for key, override in localization.prompt_overrides.items():
        if key in localized and isinstance(localized[key], dict) and isinstance(override, dict):
            localized[key] = _deep_merge(dict(localized[key]), override)
        else:
            localized[key] = _deep_copy(override)
    return localized


def prompt_ui_strings(localization: PromptLocalization | None) -> dict[str, Any]:
    if localization is None:
        return _deep_copy(PROMPT_UI_STRINGS["en"])
    return dict(localization.prompt_ui)


def course_context_ui_strings(localization: PromptLocalization | None) -> dict[str, Any]:
    if localization is None:
        return _deep_copy(COURSE_CONTEXT_UI_STRINGS["en"])
    return dict(localization.course_context_ui)


def localize_stage(value: str, localization: PromptLocalization | None) -> str:
    normalized = str(value or "").strip().lower()
    if localization is None or localization.locale == "en":
        return normalized or "unknown"
    stage_map = {
        "early/foundational": "tidlige/fundamentale",
        "middle/transitional": "midterste/overgangspraegede",
        "late/integrative": "sene/integrerende",
        "unknown": "ukendte",
    }
    return stage_map.get(normalized, normalized or "ukendte")


def looks_english(text: str) -> bool:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return False
    lowered = cleaned.lower()
    if any(char in lowered for char in "æøå"):
        return False
    tokens = re.findall(r"[A-Za-z][A-Za-z'-]*", lowered)
    if not tokens:
        return False
    english_hits = sum(token in _ENGLISH_HINT_WORDS for token in tokens)
    danish_hits = sum(token in _DANISH_HINT_WORDS for token in tokens)
    return english_hits > 0 and english_hits >= danish_hits


def localize_course_context_text(
    text: object,
    *,
    localization: PromptLocalization | None,
    missing_texts: set[str] | None = None,
) -> str:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return ""
    if localization is None or localization.locale == "en":
        return cleaned
    translated = localization.course_context_translations.get(cleaned)
    if translated:
        return translated
    if not looks_english(cleaned):
        return cleaned
    if missing_texts is not None:
        missing_texts.add(cleaned)
    if localization.fail_on_missing_course_context_translations:
        raise RuntimeError(
            f"missing {localization.locale} course-context translation for: {cleaned}"
        )
    if localization.omit_untranslated_course_context:
        return ""
    return cleaned
