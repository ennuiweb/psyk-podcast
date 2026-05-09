#!/usr/bin/env python3
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from notebooklm_queue import prompt_localization
from notebooklm_queue import course_context as course_context_helpers
from notebooklm_queue import prompting

DEFAULT_BASE_CONFIG = (
    REPO_ROOT / "notebooklm-podcast-auto" / "personlighedspsykologi" / "prompt_config.json"
)
DEFAULT_PROMPT_OVERRIDES = (
    REPO_ROOT / "notebooklm-podcast-auto" / "personlighedspsykologi" / "locales" / "da.prompt.json"
)
DEFAULT_COURSE_CONTEXT_TRANSLATIONS = (
    REPO_ROOT
    / "notebooklm-podcast-auto"
    / "personlighedspsykologi"
    / "locales"
    / "da.course_context.json"
)
DEFAULT_SHOW_DIR = REPO_ROOT / "shows" / "personlighedspsykologi-en"

STATIC_ROOT_KEYS = {
    "audio_prompt_strategy",
    "audio_prompt_framework",
    "report_prompt_strategy",
    "study_context",
    "exam_focus",
    "meta_prompting",
    "course_context",
    "report",
    "weekly_report",
    "per_reading_report",
    "per_slide_report",
    "short_report",
}
STATIC_EXCLUDED_KEYS = {
    "content_manifest",
    "course_overview",
    "base_path",
    "provider",
    "model",
    "format",
    "length",
    "orientation",
    "detail",
    "difficulty",
    "quantity",
    "per_source_suffixes",
    "weekly_sidecars",
    "default_per_source_output_suffix",
    "default_weekly_output_name",
}
SUBSTRATE_ITEM_KEYS = {
    "point",
    "priority",
    "concept",
    "tension",
    "angle",
    "claim",
    "summary",
    "why",
    "role",
    "stakes",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _collect_static_prompt_strings(value: Any, *, path: str = "") -> dict[str, str]:
    result: dict[str, str] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            if key in STATIC_EXCLUDED_KEYS:
                continue
            child_path = f"{path}.{key}" if path else key
            result.update(_collect_static_prompt_strings(item, path=child_path))
        return result
    if isinstance(value, list):
        for index, item in enumerate(value):
            child_path = f"{path}[{index}]"
            result.update(_collect_static_prompt_strings(item, path=child_path))
        return result
    if isinstance(value, str) and value.strip():
        result[path] = value.strip()
    return result


def collect_static_prompt_sources(base_config: dict[str, Any]) -> dict[str, str]:
    normalized_sections = {
        "audio_prompt_strategy": prompting.normalize_audio_prompt_strategy(
            base_config.get("audio_prompt_strategy")
        ),
        "audio_prompt_framework": prompting.normalize_audio_prompt_framework(
            base_config.get("audio_prompt_framework")
        ),
        "report_prompt_strategy": prompting.normalize_report_prompt_strategy(
            base_config.get("report_prompt_strategy")
        ),
        "study_context": prompting.normalize_study_context(base_config.get("study_context")),
        "exam_focus": prompting.normalize_exam_focus(base_config.get("exam_focus")),
        "meta_prompting": prompting.normalize_meta_prompting(base_config.get("meta_prompting")),
        "course_context": course_context_helpers.normalize_course_context(
            base_config.get("course_context")
        ),
        "report": base_config.get("report") or {},
        "weekly_report": base_config.get("weekly_report") or {},
        "per_reading_report": base_config.get("per_reading_report") or {},
        "per_slide_report": base_config.get("per_slide_report") or {},
        "short_report": base_config.get("short_report") or {},
    }
    result: dict[str, str] = {}
    for key, section in normalized_sections.items():
        result.update(_collect_static_prompt_strings(section, path=key))
    return result


def _add_if_english(found: set[str], value: object, *, allow_short_label: bool = False) -> None:
    cleaned = " ".join(str(value or "").split())
    is_short_label = (
        allow_short_label
        and cleaned == cleaned.lower()
        and 0 < len(cleaned.split()) <= 4
        and all(ord(char) < 128 for char in cleaned)
    )
    if cleaned and (prompt_localization.looks_english(cleaned) or is_short_label):
        found.add(cleaned)


def _collect_substrate_items(value: object, *, found: set[str]) -> None:
    if isinstance(value, list):
        for item in value:
            _collect_substrate_items(item, found=found)
        return
    if isinstance(value, str):
        _add_if_english(found, value)
        return
    if not isinstance(value, dict):
        return
    for key in SUBSTRATE_ITEM_KEYS:
        if key in value:
            _add_if_english(found, value.get(key))


def collect_course_context_sources(show_dir: Path) -> set[str]:
    found: set[str] = set()
    content_manifest_path = show_dir / "content_manifest.json"
    if content_manifest_path.exists():
        payload = read_json(content_manifest_path)
        for lecture in payload.get("lectures", []) if isinstance(payload, dict) else []:
            if not isinstance(lecture, dict):
                continue
            summary = lecture.get("summary")
            if isinstance(summary, dict):
                for key in ("summary_lines", "key_points"):
                    for item in summary.get(key, []) if isinstance(summary.get(key), list) else []:
                        _add_if_english(found, item)
            for reading in lecture.get("readings", []) if isinstance(lecture.get("readings"), list) else []:
                if not isinstance(reading, dict):
                    continue
                reading_summary = reading.get("summary")
                if not isinstance(reading_summary, dict):
                    continue
                for key in ("summary_lines", "key_points"):
                    for item in reading_summary.get(key, []) if isinstance(reading_summary.get(key), list) else []:
                        _add_if_english(found, item)

    glossary_path = show_dir / "course_glossary.json"
    if glossary_path.exists():
        payload = read_json(glossary_path)
        for term in payload.get("terms", []) if isinstance(payload, dict) else []:
            if not isinstance(term, dict):
                continue
            _add_if_english(found, term.get("label"), allow_short_label=True)
            _add_if_english(found, term.get("category"), allow_short_label=True)

    theory_map_path = show_dir / "course_theory_map.json"
    if theory_map_path.exists():
        payload = read_json(theory_map_path)
        for theory in payload.get("theories", []) if isinstance(payload, dict) else []:
            if isinstance(theory, dict):
                _add_if_english(found, theory.get("label"), allow_short_label=True)

    source_weighting_path = show_dir / "source_weighting.json"
    if source_weighting_path.exists():
        payload = read_json(source_weighting_path)
        for lecture in payload.get("lectures", []) if isinstance(payload, dict) else []:
            if not isinstance(lecture, dict):
                continue
            for ranked in lecture.get("ranked_sources", []) if isinstance(lecture.get("ranked_sources"), list) else []:
                if isinstance(ranked, dict):
                    _add_if_english(found, ranked.get("weight_band"), allow_short_label=True)

    concept_graph_path = show_dir / "course_concept_graph.json"
    if concept_graph_path.exists():
        payload = read_json(concept_graph_path)
        for distinction in payload.get("distinctions", []) if isinstance(payload, dict) else []:
            if isinstance(distinction, dict):
                _add_if_english(found, distinction.get("label"), allow_short_label=True)

    substrate_dir = show_dir / "source_intelligence" / "podcast_substrates"
    if substrate_dir.exists():
        for path in sorted(substrate_dir.glob("W*.json")):
            payload = read_json(path)
            podcast = payload.get("podcast") if isinstance(payload, dict) else None
            if not isinstance(podcast, dict):
                continue
            for key in (
                "weekly",
                "short",
                "selected_concepts",
                "selected_tensions",
                "source_selection",
                "grounding_notes",
            ):
                if key in podcast:
                    _collect_substrate_items(podcast.get(key), found=found)
            for section_key in ("per_reading", "per_slide"):
                section_items = podcast.get(section_key)
                if isinstance(section_items, list):
                    for item in section_items:
                        _collect_substrate_items(item, found=found)
    return found


def load_prompt_overrides(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise SystemExit(f"prompt override file must be an object: {path}")
    return payload


def load_course_context_translations(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"translations": {}}
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise SystemExit(f"course-context translation file must be an object: {path}")
    translations = payload.get("translations")
    if translations is None:
        payload["translations"] = {}
        translations = payload["translations"]
    if not isinstance(translations, dict):
        raise SystemExit(f"course-context translations must be an object: {path}")
    return payload


def compare_static_prompt_paths(
    *,
    source_paths: dict[str, str],
    override_paths: dict[str, str],
) -> tuple[list[str], list[str]]:
    missing = sorted(path for path in source_paths if path not in override_paths)
    unused = sorted(path for path in override_paths if path not in source_paths)
    return missing, unused


def machine_translate_missing_texts(
    missing_texts: list[str],
    *,
    batch_size: int = 25,
    max_workers: int = 6,
) -> dict[str, str]:
    translations: dict[str, str] = {}
    for start in range(0, len(missing_texts), max(1, batch_size)):
        batch = missing_texts[start : start + max(1, batch_size)]
        with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(batch)))) as executor:
            futures = {
                executor.submit(_translate_text_via_google_gtx, text): text
                for text in batch
            }
            for future in as_completed(futures):
                text = futures[future]
                try:
                    translated = str(future.result() or "").strip()
                except Exception:
                    translated = ""
                if translated:
                    translations[text] = translated
    return translations


def _translate_text_via_google_gtx(text: str) -> str:
    params = urllib.parse.urlencode(
        {
            "client": "gtx",
            "sl": "en",
            "tl": "da",
            "dt": "t",
            "q": text,
        }
    )
    url = f"https://translate.googleapis.com/translate_a/single?{params}"
    with urllib.request.urlopen(url, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    segments = payload[0] if isinstance(payload, list) and payload else []
    translated = "".join(
        str(segment[0] or "")
        for segment in segments
        if isinstance(segment, list) and segment
    ).strip()
    return translated


def main() -> int:
    parser = argparse.ArgumentParser(description="Check or sync Danish prompt-localization assets.")
    parser.add_argument("--base-config", default=str(DEFAULT_BASE_CONFIG))
    parser.add_argument("--prompt-overrides", default=str(DEFAULT_PROMPT_OVERRIDES))
    parser.add_argument("--course-context-translations", default=str(DEFAULT_COURSE_CONTEXT_TRANSLATIONS))
    parser.add_argument("--show-dir", default=str(DEFAULT_SHOW_DIR))
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write-course-context-stubs", action="store_true")
    parser.add_argument("--prune-unused-course-context", action="store_true")
    parser.add_argument("--machine-translate-missing-course-context", action="store_true")
    args = parser.parse_args()

    base_config_path = Path(args.base_config).expanduser().resolve()
    prompt_overrides_path = Path(args.prompt_overrides).expanduser().resolve()
    course_context_translations_path = Path(args.course_context_translations).expanduser().resolve()
    show_dir = Path(args.show_dir).expanduser().resolve()

    base_config = read_json(base_config_path)
    prompt_overrides = load_prompt_overrides(prompt_overrides_path)
    static_sources = collect_static_prompt_sources(base_config)
    static_overrides = collect_static_prompt_sources(prompt_overrides)
    missing_static, unused_static = compare_static_prompt_paths(
        source_paths=static_sources,
        override_paths=static_overrides,
    )

    course_context_sources = collect_course_context_sources(show_dir)
    course_context_payload = load_course_context_translations(course_context_translations_path)
    translations = course_context_payload["translations"]
    missing_course_context = sorted(
        text for text in course_context_sources if not str(translations.get(text) or "").strip()
    )
    unused_course_context = sorted(text for text in translations if text not in course_context_sources)

    if args.write_course_context_stubs:
        for text in missing_course_context:
            translations.setdefault(text, "")
        if args.prune_unused_course_context:
            for text in unused_course_context:
                translations.pop(text, None)
        course_context_translations_path.write_text(
            json.dumps(course_context_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if args.machine_translate_missing_course_context and missing_course_context:
        translated = machine_translate_missing_texts(missing_course_context)
        for text, translation in translated.items():
            translations[text] = translation
        course_context_translations_path.write_text(
            json.dumps(course_context_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        missing_course_context = sorted(
            text for text in course_context_sources if not str(translations.get(text) or "").strip()
        )

    if missing_static:
        print("Missing static Danish prompt overrides:")
        for path in missing_static:
            print(f"  - {path}")
    if unused_static:
        print("Unused static Danish prompt overrides:")
        for path in unused_static:
            print(f"  - {path}")
    if missing_course_context:
        print("Missing Danish course-context translations:")
        for text in missing_course_context[:50]:
            print(f"  - {text}")
        if len(missing_course_context) > 50:
            print(f"  ... and {len(missing_course_context) - 50} more")
    if unused_course_context:
        print("Unused Danish course-context translations:")
        for text in unused_course_context[:50]:
            print(f"  - {text}")
        if len(unused_course_context) > 50:
            print(f"  ... and {len(unused_course_context) - 50} more")

    if args.check and (missing_static or missing_course_context):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
