#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import shlex
from typing import NamedTuple

REPO_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[3]
if str(REPO_ROOT_FOR_IMPORTS) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORTS))

from notebooklm_queue import course_context as course_context_helpers, prompting


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


WEEK_SELECTOR_PATTERN = re.compile(r"^(?:W)?0*(\d{1,2})(?:L0*(\d{1,2}))?$", re.IGNORECASE)
WEEK_DIR_PATTERN = re.compile(r"^W0*(\d{1,2})(?:L0*(\d{1,2}))?\b", re.IGNORECASE)
OUTPUT_TITLE_PREFIX_PATTERN = re.compile(
    r"^((?:\[(?:Short|Brief)\]\s+)?W\d+L\d+\s+-\s+)(.+)$",
    re.IGNORECASE,
)
CFG_TAG_PATTERN = re.compile(
    r"(?:\s+\{[a-z0-9._:+-]+=[^{}\s]+(?:\s+[a-z0-9._:+-]+=[^{}\s]+)*\})+"
    r"(?:\s+\[[^\[\]]+\])?$",
    re.IGNORECASE,
)
MAX_FILENAME_BYTES = 255
DEFAULT_SOURCES_ROOT = (
    "/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/"
    "Mine dokumenter \U0001F4BE/psykologi/Personlighedspsykologi/Readings"
)
DEFAULT_OUTPUT_ROOT = "notebooklm-podcast-auto/personlighedspsykologi/output"
OUTPUT_ROOT_ENV_VAR = "PERSONLIGHEDSPSYKOLOGI_OUTPUT_ROOT"
PROFILES_FILE_ENV_VAR = "NOTEBOOKLM_PROFILES_FILE"
PROFILE_PRIORITY_ENV_VAR = "NOTEBOOKLM_PROFILE_PRIORITY"
WEEKLY_OVERVIEW_TITLE = "Alle kilder (undtagen slides)"
LEGACY_WEEKLY_OVERVIEW_TITLES = ("Alle kilder",)
SLIDE_SUBCATEGORY_ORDER = {"lecture": 0, "seminar": 1, "exercise": 2}
SLIDE_SUBCATEGORY_LABELS = {
    "lecture": "Slide lecture",
    "seminar": "Slide seminar",
    "exercise": "Slide exercise",
}
INCLUDED_SLIDE_SUBCATEGORIES = {"lecture", "exercise"}
BRIEF_APPLY_TO_VALUES = {
    "all",
    "none",
    "grundbog_only",
    "reading_only",
    "slides_only",
    "lecture_slides_only",
    "readings_and_lecture_slides",
}
BRIEF_SUPPORTED_CONTENT_TYPES = {"audio", "infographic", "report"}
SHORT_PREFIX_GLOBS = ("[[]Short[]]*", "[[]Brief[]]*")
AUDIO_FORMAT_VALUES = prompting.AUDIO_FORMAT_VALUES
AUDIO_LENGTH_VALUES = prompting.AUDIO_LENGTH_VALUES
REPORT_FORMAT_VALUES = prompting.REPORT_FORMAT_VALUES
PER_SLIDE_OVERRIDE_KEYS = {"format", "length", "prompt"}
SLIDE_AUDIO_QUARANTINE_ROOT = Path(".ai/quarantine/slide-audio-overrides")
TEXT_SOURCE_EXTENSIONS = {".txt", ".md", ".markdown", ".html", ".htm", ".json", ".csv"}
PROMPT_SIDECAR_SUFFIXES = prompting.PROMPT_SIDECAR_SUFFIXES
WEEK_PROMPT_SIDECAR_NAMES = prompting.WEEK_PROMPT_SIDECAR_NAMES
AUDIO_PROMPT_TYPES = prompting.AUDIO_PROMPT_TYPES
GEMINI_META_PROMPT_MODEL = prompting.GEMINI_META_PROMPT_MODEL
GEMINI_FILE_POLL_INTERVAL_SECONDS = 2
GEMINI_FILE_POLL_TIMEOUT_SECONDS = 60
DEFAULT_AUDIO_PROMPT_STRATEGY = prompting.DEFAULT_AUDIO_PROMPT_STRATEGY
DEFAULT_EXAM_FOCUS = prompting.DEFAULT_EXAM_FOCUS
DEFAULT_STUDY_CONTEXT = prompting.DEFAULT_STUDY_CONTEXT
DEFAULT_META_PROMPTING = prompting.DEFAULT_META_PROMPTING
DEFAULT_AUDIO_PROMPT_FRAMEWORK = prompting.DEFAULT_AUDIO_PROMPT_FRAMEWORK
DEFAULT_REPORT_PROMPT_STRATEGY = prompting.DEFAULT_REPORT_PROMPT_STRATEGY
DEFAULT_COURSE_CONTEXT = course_context_helpers.DEFAULT_COURSE_CONTEXT
META_PROMPT_MAX_RESPONSE_TOKENS = 1400
META_PROMPT_WARNING_MESSAGES: set[str] = set()


class SourceItem(NamedTuple):
    path: Path
    base_name: str
    source_type: str
    slide_key: str | None = None
    slide_subcategory: str | None = None


class MetaPromptJob(NamedTuple):
    prompt_type: str
    output_path: Path
    label: str
    source_items: tuple[SourceItem, ...]
    week_label: str | None = None


class MetaPromptBackend(NamedTuple):
    provider: str
    client: object
    support: object | None = None


class MetaPromptInputError(RuntimeError):
    pass


class GeminiUploadedFile(NamedTuple):
    name: str
    uri: str
    mime_type: str


class ReviewManifestFilter(NamedTuple):
    weekly_lectures: set[str]
    per_reading_paths: set[str]
    per_slide_keys: set[str]
    short_reading_paths: set[str]
    short_slide_keys: set[str]
    output_keys_by_type: dict[str, set[str]]


def default_output_root() -> str:
    override = str(os.getenv(OUTPUT_ROOT_ENV_VAR) or "").strip()
    return override or DEFAULT_OUTPUT_ROOT


def resolve_output_root(path: Path) -> Path:
    candidate = path.expanduser()
    if candidate.exists() and candidate.is_dir():
        return candidate.resolve()
    if sys.platform == "darwin" and candidate.exists() and candidate.is_file():
        resolved = resolve_macos_alias(candidate)
        if resolved is not None and resolved.is_dir():
            return resolved.resolve()
    return candidate.resolve()


def resolve_macos_alias(path: Path) -> Path | None:
    if sys.platform != "darwin":
        return None
    try:
        result = subprocess.run(
            [
                "osascript",
                "-e",
                'tell application "Finder"',
                "-e",
                f'set f to (POSIX file "{path.resolve()}") as alias',
                "-e",
                "set targetItem to original item of f",
                "-e",
                "return POSIX path of (targetItem as text)",
                "-e",
                "end tell",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    resolved = result.stdout.strip()
    if not resolved:
        return None
    return Path(resolved).expanduser()


def canonicalize_lecture_key(value: str) -> str:
    match = re.fullmatch(r"\s*W?0*(\d{1,2})L0*(\d{1,2})\s*", value, re.IGNORECASE)
    if not match:
        return value.strip().upper()
    return f"W{int(match.group(1)):02d}L{int(match.group(2))}"


def canonical_week_label_from_dir(week_dir: Path) -> str:
    raw_label = week_dir.name.split(" ", 1)[0].upper()
    return canonicalize_lecture_key(raw_label)


def ensure_unique_canonical_week_dirs(week_dirs: list[Path], *, week_input: str) -> list[Path]:
    grouped: dict[str, list[Path]] = {}
    for week_dir in week_dirs:
        canonical_label = canonical_week_label_from_dir(week_dir)
        grouped.setdefault(canonical_label, []).append(week_dir)

    duplicates = {
        label: paths
        for label, paths in grouped.items()
        if len({path.resolve() for path in paths}) > 1
    }
    if duplicates:
        details = "; ".join(
            f"{label}: {', '.join(path.name for path in sorted(paths, key=lambda item: item.name.casefold()))}"
            for label, paths in sorted(duplicates.items())
        )
        raise SystemExit(
            "Multiple source week folders collapse to the same canonical lecture key "
            f"for {week_input}: {details}"
        )

    unique: list[Path] = []
    seen: set[Path] = set()
    for week_dir in sorted(week_dirs, key=lambda item: item.name.casefold()):
        resolved = week_dir.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(week_dir)
    return unique


def slide_catalog_lecture_keys(raw_slide: dict[str, object]) -> list[str]:
    lecture_keys: list[str] = []

    primary_lecture_key = canonicalize_lecture_key(str(raw_slide.get("lecture_key") or ""))
    if re.fullmatch(r"W\d{2}L\d+", primary_lecture_key):
        lecture_keys.append(primary_lecture_key)

    raw_lecture_keys = raw_slide.get("lecture_keys")
    if isinstance(raw_lecture_keys, list):
        for value in raw_lecture_keys:
            lecture_key = canonicalize_lecture_key(str(value or ""))
            if re.fullmatch(r"W\d{2}L\d+", lecture_key) and lecture_key not in lecture_keys:
                lecture_keys.append(lecture_key)

    return lecture_keys


def parse_week_selector(value: str) -> tuple[int, int | None] | None:
    match = WEEK_SELECTOR_PATTERN.fullmatch(value.strip())
    if not match:
        return None
    week_num = int(match.group(1))
    lesson_num = int(match.group(2)) if match.group(2) else None
    return week_num, lesson_num


def parse_week_dir_label(value: str) -> tuple[int, int | None] | None:
    match = WEEK_DIR_PATTERN.match(value.strip())
    if not match:
        return None
    week_num = int(match.group(1))
    lesson_num = int(match.group(2)) if match.group(2) else None
    return week_num, lesson_num


def find_week_dirs(root: Path, week: str) -> list[Path]:
    if not root.exists():
        return []
    selector = parse_week_selector(week)
    if selector:
        requested_week, requested_lesson = selector
        matches: list[Path] = []
        for entry in root.iterdir():
            if not entry.is_dir():
                continue
            label = parse_week_dir_label(entry.name)
            if not label:
                continue
            week_num, lesson_num = label
            if week_num != requested_week:
                continue
            if requested_lesson is not None and lesson_num != requested_lesson:
                continue
            matches.append(entry)
        return sorted(matches, key=lambda path: path.name)

    week_upper = week.upper()
    exact: list[Path] = []
    prefix: list[Path] = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        name_upper = entry.name.upper()
        if name_upper == week_upper:
            exact.append(entry)
        elif name_upper.startswith(week_upper):
            prefix.append(entry)
    if exact:
        return exact
    return sorted(prefix, key=lambda path: path.name)


def list_source_files(week_dir: Path) -> list[Path]:
    files = []
    for entry in sorted(week_dir.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.is_file():
            files.append(entry)
    return files


def is_prompt_sidecar_file(path: Path, meta_prompting: dict | None = None) -> bool:
    return prompting.is_prompt_sidecar_file(path, meta_prompting)


def _slides_catalog_entries_for_lecture(
    *,
    slides_catalog_path: Path | None,
    slides_source_root: Path | None,
    lecture_key: str,
) -> list[SourceItem]:
    if slides_catalog_path is None or slides_source_root is None:
        return []
    if not slides_catalog_path.exists():
        return []

    try:
        payload = read_json(slides_catalog_path)
    except (OSError, json.JSONDecodeError):
        print(f"Warning: unable to read slides catalog: {slides_catalog_path}")
        return []

    expected_subject_slug = str(payload.get("subject_slug") or "").strip().lower()
    if expected_subject_slug:
        _ = expected_subject_slug

    raw_slides = payload.get("slides")
    if not isinstance(raw_slides, list):
        return []

    requested_lecture_key = canonicalize_lecture_key(lecture_key)
    items: list[SourceItem] = []
    for raw_slide in raw_slides:
        if not isinstance(raw_slide, dict):
            continue
        raw_lecture_keys = slide_catalog_lecture_keys(raw_slide)
        if requested_lecture_key not in raw_lecture_keys:
            continue
        subcategory = str(raw_slide.get("subcategory") or "").strip().lower()
        if subcategory not in INCLUDED_SLIDE_SUBCATEGORIES:
            continue
        title = str(raw_slide.get("title") or "").strip()
        source_filename = str(raw_slide.get("source_filename") or "").strip()
        if not title and not source_filename:
            continue
        local_source_path = str(raw_slide.get("local_source_path") or "").strip()
        local_relative_path = str(raw_slide.get("local_relative_path") or "").strip()
        if local_source_path:
            slide_path = Path(local_source_path).expanduser()
        elif local_relative_path:
            slide_path = (slides_source_root / local_relative_path).resolve()
        else:
            relative_path = str(raw_slide.get("relative_path") or "").strip()
            candidate = local_relative_path or relative_path or source_filename
            slide_path = (slides_source_root / candidate).resolve()
        if not slide_path.exists() or not slide_path.is_file():
            print(
                f"Warning: skipping slide source for {lecture_key} because file is missing: {slide_path}"
            )
            continue
        display_title = title or slide_path.stem
        base_name = f"{SLIDE_SUBCATEGORY_LABELS[subcategory]}: {display_title}"
        items.append(
            SourceItem(
                path=slide_path,
                base_name=base_name,
                source_type="slide",
                slide_key=str(raw_slide.get("slide_key") or "").strip().lower() or None,
                slide_subcategory=subcategory,
            )
        )

    return sorted(
        items,
        key=lambda item: (
            SLIDE_SUBCATEGORY_ORDER.get(str(item.slide_subcategory or ""), 99),
            item.base_name.casefold(),
            str(item.path),
        ),
    )


def cleanup_disallowed_slide_outputs(week_output_dir: Path) -> list[Path]:
    if not week_output_dir.exists():
        return []

    removed: list[Path] = []
    for subcategory, label in SLIDE_SUBCATEGORY_LABELS.items():
        if subcategory in INCLUDED_SLIDE_SUBCATEGORIES:
            continue
        for entry in sorted(week_output_dir.glob(f"* - {label}: *"), key=lambda path: path.name):
            if not entry.is_file():
                continue
            entry.unlink()
            removed.append(entry)
    return removed


def slide_brief_subcategory_allowed(subcategory: str, *, brief_cfg: dict) -> bool:
    apply_to = resolve_brief_apply_to(brief_cfg)
    if subcategory == "seminar":
        return False
    if apply_to in {"all", "slides_only"}:
        return subcategory == "lecture" or subcategory == "exercise"
    if apply_to in {"lecture_slides_only", "readings_and_lecture_slides"}:
        return subcategory == "lecture"
    return False


def brief_content_types(content_types: list[str]) -> list[str]:
    return [item for item in content_types if item in BRIEF_SUPPORTED_CONTENT_TYPES]


def cleanup_disallowed_slide_brief_outputs(week_output_dir: Path, *, brief_cfg: dict) -> list[Path]:
    if not week_output_dir.exists():
        return []

    removed: list[Path] = []
    for subcategory, label in SLIDE_SUBCATEGORY_LABELS.items():
        if slide_brief_subcategory_allowed(subcategory, brief_cfg=brief_cfg):
            continue
        for prefix_glob in SHORT_PREFIX_GLOBS:
            for entry in sorted(
                week_output_dir.glob(f"{prefix_glob} - {label}: *"),
                key=lambda path: path.name,
            ):
                if not entry.is_file():
                    continue
                entry.unlink()
                removed.append(entry)
    return removed


def cleanup_disallowed_brief_quiz_outputs(week_output_dir: Path) -> list[Path]:
    if not week_output_dir.exists():
        return []

    removed: list[Path] = []
    for prefix_glob in SHORT_PREFIX_GLOBS:
        for entry in sorted(week_output_dir.glob(prefix_glob), key=lambda path: path.name):
            if not entry.is_file():
                continue
            if "type=quiz" not in entry.name.lower():
                continue
            entry.unlink()
            removed.append(entry)
    return removed


def build_source_items(
    *,
    week_dir: Path,
    week_label: str,
    slides_catalog_path: Path | None,
    slides_source_root: Path | None,
    meta_prompting: dict | None = None,
) -> tuple[list[SourceItem], list[SourceItem]]:
    canonical_week_label = canonicalize_lecture_key(week_label)
    reading_sources = [
        SourceItem(
            path=path,
            base_name=normalize_episode_title(path.stem, canonical_week_label),
            source_type="reading",
        )
        for path in list_source_files(week_dir)
        if not is_prompt_sidecar_file(path, meta_prompting)
    ]
    slide_sources = _slides_catalog_entries_for_lecture(
        slides_catalog_path=slides_catalog_path,
        slides_source_root=slides_source_root,
        lecture_key=canonical_week_label,
    )
    return reading_sources, [*reading_sources, *slide_sources]


def per_source_audio_settings(
    source_item: SourceItem,
    *,
    course_title: str | None = None,
    per_reading_cfg: dict,
    per_slide_cfg: dict,
    per_slide_overrides: dict[str, dict] | None = None,
    prompt_strategy: dict | None = None,
    exam_focus: dict | None = None,
    study_context: dict | None = None,
    prompt_framework: dict | None = None,
    meta_prompting: dict | None = None,
    meta_note_overrides: dict[Path, str] | None = None,
    course_context_bundle: course_context_helpers.CoursePromptContextBundle | None = None,
    course_context_cfg: dict | None = None,
    lecture_key: str | None = None,
) -> tuple[str, str, str, str]:
    if source_item.source_type == "slide":
        slide_cfg = {
            "format": str(per_slide_cfg.get("format", "deep-dive")).strip().lower(),
            "length": str(per_slide_cfg.get("length", "default")).strip().lower(),
            "prompt": per_slide_cfg.get("prompt", ""),
        }
        override = None
        if source_item.slide_key:
            overrides = per_slide_overrides
            if overrides is None:
                overrides = parse_per_slide_overrides(per_slide_cfg)
            override = overrides.get(normalize_slide_key(source_item.slide_key))
        if override:
            slide_cfg.update(override)
        course_context_note = build_course_context_note(
            course_context_bundle=course_context_bundle,
            course_context_cfg=course_context_cfg,
            lecture_key=lecture_key,
            prompt_type="single_slide",
            source_item=source_item,
        )
        return (
            "per_slide",
            build_audio_prompt(
                prompt_type="single_slide",
                prompt_strategy=prompt_strategy,
                exam_focus=exam_focus,
                study_context=study_context,
                prompt_framework=prompt_framework,
                meta_prompting=meta_prompting,
                course_title=course_title,
                course_context_note=course_context_note,
                course_context_heading=course_context_cfg.get("heading") if course_context_cfg else None,
                meta_note_overrides=meta_note_overrides,
                custom_prompt=slide_cfg.get("prompt", ""),
                audio_format=slide_cfg.get("format", "deep-dive"),
                audio_length=slide_cfg.get("length", "default"),
                source_item=source_item,
            ),
            slide_cfg.get("format", "deep-dive"),
            slide_cfg.get("length", "default"),
        )
    course_context_note = build_course_context_note(
        course_context_bundle=course_context_bundle,
        course_context_cfg=course_context_cfg,
        lecture_key=lecture_key,
        prompt_type="single_reading",
        source_item=source_item,
    )
    return (
        "per_reading",
        build_audio_prompt(
            prompt_type="single_reading",
            prompt_strategy=prompt_strategy,
            exam_focus=exam_focus,
            study_context=study_context,
            prompt_framework=prompt_framework,
            meta_prompting=meta_prompting,
            course_title=course_title,
            course_context_note=course_context_note,
            course_context_heading=course_context_cfg.get("heading") if course_context_cfg else None,
            meta_note_overrides=meta_note_overrides,
            custom_prompt=per_reading_cfg.get("prompt", ""),
            audio_format=per_reading_cfg.get("format", "deep-dive"),
            audio_length=per_reading_cfg.get("length", "default"),
            source_item=source_item,
        ),
        per_reading_cfg.get("format", "deep-dive"),
        per_reading_cfg.get("length", "default"),
    )


def per_source_report_settings(
    source_item: SourceItem,
    *,
    per_reading_cfg: dict,
    per_slide_cfg: dict,
    prompt_strategy: dict | None = None,
    study_context: dict | None = None,
    meta_prompting: dict | None = None,
    meta_note_overrides: dict[Path, str] | None = None,
    course_context_bundle: course_context_helpers.CoursePromptContextBundle | None = None,
    course_context_cfg: dict | None = None,
    lecture_key: str | None = None,
) -> tuple[str, str, str]:
    prompt_type = "single_slide" if source_item.source_type == "slide" else "single_reading"
    cfg = per_slide_cfg if source_item.source_type == "slide" else per_reading_cfg
    course_context_note = build_course_context_note(
        course_context_bundle=course_context_bundle,
        course_context_cfg=course_context_cfg,
        lecture_key=lecture_key,
        prompt_type=prompt_type,
        source_item=source_item,
    )
    return (
        "per_slide" if source_item.source_type == "slide" else "per_reading",
        build_report_prompt(
            prompt_type=prompt_type,
            prompt_strategy=prompt_strategy,
            course_context_note=course_context_note,
            course_context_heading=course_context_cfg.get("heading") if course_context_cfg else None,
            study_context=study_context,
            meta_prompting=meta_prompting,
            meta_note_overrides=meta_note_overrides,
            custom_prompt=cfg.get("prompt", ""),
            source_item=source_item,
        ),
        normalize_report_format(cfg.get("format")),
    )


def resolve_brief_apply_to(brief_cfg: dict) -> str:
    raw_value = str(brief_cfg.get("apply_to") or "grundbog_only").strip().lower()
    if raw_value in BRIEF_APPLY_TO_VALUES:
        return raw_value
    allowed = ", ".join(sorted(BRIEF_APPLY_TO_VALUES))
    raise SystemExit(
        f"Unknown short.apply_to '{raw_value}'. Allowed values: {allowed}."
    )


def is_lecture_slide_source(source_item: SourceItem) -> bool:
    return source_item.source_type == "slide" and source_item.slide_subcategory == "lecture"


def should_generate_brief_for_source(source_item: SourceItem, *, brief_cfg: dict) -> bool:
    apply_to = resolve_brief_apply_to(brief_cfg)
    if apply_to == "none":
        return False
    if apply_to == "all":
        return True
    if apply_to == "slides_only":
        return source_item.source_type == "slide"
    if apply_to == "lecture_slides_only":
        return is_lecture_slide_source(source_item)
    if apply_to == "reading_only":
        return source_item.source_type == "reading"
    if apply_to == "readings_and_lecture_slides":
        return source_item.source_type == "reading" or is_lecture_slide_source(source_item)
    return source_item.source_type == "reading" and "grundbog kapitel" in source_item.path.name.casefold()


def should_generate_weekly_overview(source_count: int) -> bool:
    if source_count < 0:
        raise ValueError("source_count must be >= 0")
    return source_count > 1


def normalize_review_output_key(value: str) -> str:
    name = Path(str(value)).name.strip()
    stem = Path(name).stem if name.lower().endswith(".mp3") else name
    stem = CFG_TAG_PATTERN.sub("", stem).strip()
    stem = re.sub(r"\s+", " ", stem)
    return stem.casefold()


def _review_source_paths(entry: dict) -> list[str]:
    paths: list[str] = []
    source_context = entry.get("source_context") or {}
    for value in source_context.get("source_files") or []:
        raw = str(value).strip()
        if not raw:
            continue
        path = Path(raw).expanduser()
        paths.append(str(path.resolve()) if path.is_absolute() else raw)
    return paths


def load_review_manifest_filter(path: Path) -> ReviewManifestFilter:
    payload = read_json(path)
    weekly_lectures: set[str] = set()
    per_reading_paths: set[str] = set()
    per_slide_keys: set[str] = set()
    short_reading_paths: set[str] = set()
    short_slide_keys: set[str] = set()
    output_keys_by_type: dict[str, set[str]] = {
        "weekly_readings_only": set(),
        "single_reading": set(),
        "single_slide": set(),
        "short": set(),
    }

    for entry in payload.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        prompt_type = str(entry.get("prompt_type") or "").strip()
        if prompt_type not in output_keys_by_type:
            continue
        lecture_key = str(entry.get("lecture_key") or "").strip()
        if lecture_key:
            lecture_key = canonicalize_lecture_key(lecture_key)
        baseline = entry.get("baseline") or {}
        source_name = str(baseline.get("source_name") or "").strip()
        if source_name:
            output_keys_by_type[prompt_type].add(normalize_review_output_key(source_name))

        if prompt_type == "weekly_readings_only":
            if lecture_key:
                weekly_lectures.add(lecture_key)
            continue

        source_context = entry.get("source_context") or {}
        catalog_match = source_context.get("catalog_match") or {}
        slide_key = normalize_slide_key(str(catalog_match.get("slide_key") or ""))
        source_paths = _review_source_paths(entry)
        if prompt_type == "single_reading":
            per_reading_paths.update(source_paths)
        elif prompt_type == "single_slide":
            if slide_key:
                per_slide_keys.add(slide_key)
        elif prompt_type == "short":
            if slide_key:
                short_slide_keys.add(slide_key)
            else:
                short_reading_paths.update(source_paths)

    return ReviewManifestFilter(
        weekly_lectures=weekly_lectures,
        per_reading_paths=per_reading_paths,
        per_slide_keys=per_slide_keys,
        short_reading_paths=short_reading_paths,
        short_slide_keys=short_slide_keys,
        output_keys_by_type=output_keys_by_type,
    )


def review_source_path_key(path: Path) -> str:
    return str(path.expanduser().resolve())


def review_filter_includes_weekly(
    review_filter: ReviewManifestFilter | None,
    week_label: str,
) -> bool:
    if review_filter is None:
        return True
    return canonicalize_lecture_key(week_label) in review_filter.weekly_lectures


def review_filter_includes_source(
    review_filter: ReviewManifestFilter | None,
    source_item: SourceItem,
) -> bool:
    if review_filter is None:
        return True
    if source_item.source_type == "slide":
        slide_key = normalize_slide_key(source_item.slide_key or "")
        return slide_key in review_filter.per_slide_keys or slide_key in review_filter.short_slide_keys
    source_key = review_source_path_key(source_item.path)
    return source_key in review_filter.per_reading_paths or source_key in review_filter.short_reading_paths


def review_filter_includes_short_source(
    review_filter: ReviewManifestFilter | None,
    source_item: SourceItem,
) -> bool:
    if review_filter is None:
        return True
    if source_item.source_type == "slide":
        return normalize_slide_key(source_item.slide_key or "") in review_filter.short_slide_keys
    return review_source_path_key(source_item.path) in review_filter.short_reading_paths


def review_filter_includes_output(
    review_filter: ReviewManifestFilter | None,
    prompt_type: str,
    output_path: Path,
) -> bool:
    if review_filter is None:
        return True
    return normalize_review_output_key(output_path.name) in review_filter.output_keys_by_type.get(prompt_type, set())


# Keep this as a raw regex with single escapes (\b, \s) so week-prefix stripping works.
WEEK_PREFIX_PATTERN = re.compile(r"^(W0*(\d{1,2})L0*(\d{1,2}))\b[\s._-]*", re.IGNORECASE)


def parse_week_label(week_label: str) -> tuple[int, int] | None:
    match = WEEK_PREFIX_PATTERN.match(week_label.strip())
    if not match:
        return None
    return int(match.group(2)), int(match.group(3))


def strip_week_prefix_from_title(title: str, week_label: str) -> str:
    if not title:
        return title
    match = WEEK_PREFIX_PATTERN.match(title.strip())
    if not match:
        return title
    week_parts = parse_week_label(week_label)
    if not week_parts:
        return title
    if (int(match.group(2)), int(match.group(3))) != week_parts:
        return title
    stripped = title[match.end() :].strip()
    return stripped or title


def normalize_episode_title(title: str, week_label: str) -> str:
    if not title:
        return title
    normalized = strip_week_prefix_from_title(title, week_label)
    normalized = strip_week_prefix_from_title(normalized, week_label)
    normalized = re.sub(r"\.{2,}", ".", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized or title


def _deep_copy_prompt_defaults(value: object) -> object:
    return prompting._deep_copy_prompt_defaults(value)


def _normalize_string_list(section: str, field: str, value: object) -> list[str]:
    return prompting._normalize_string_list(section, field, value)


def normalize_audio_prompt_strategy(raw: object) -> dict:
    return prompting.normalize_audio_prompt_strategy(raw)


def normalize_exam_focus(raw: object) -> dict:
    return prompting.normalize_exam_focus(raw)


def normalize_study_context(raw: object) -> dict:
    return prompting.normalize_study_context(raw)


def normalize_meta_prompting(raw: object) -> dict:
    return prompting.normalize_meta_prompting(raw)


def normalize_audio_prompt_framework(raw: object) -> dict:
    return prompting.normalize_audio_prompt_framework(raw)


def normalize_course_context(raw: object) -> dict:
    return course_context_helpers.normalize_course_context(raw)


def normalize_report_prompt_strategy(raw: object) -> dict:
    return prompting.normalize_report_prompt_strategy(raw)


def ensure_prompt(_: str, value: str) -> str:
    return prompting.ensure_prompt(_, value)


def _format_bullets(items: list[str]) -> str:
    return prompting._format_bullets(items)


def _source_prompt_sidecar_candidates(source_path: Path, meta_prompting: dict) -> list[Path]:
    return prompting._source_prompt_sidecar_candidates(source_path, meta_prompting)


def _week_prompt_sidecar_candidates(week_dir: Path, week_label: str | None, meta_prompting: dict) -> list[Path]:
    return prompting._week_prompt_sidecar_candidates(week_dir, week_label, meta_prompting)


def _warn_meta_prompt_once(message: str) -> None:
    if message in META_PROMPT_WARNING_MESSAGES:
        return
    META_PROMPT_WARNING_MESSAGES.add(message)
    print(f"Warning: {message}")


def _canonical_source_sidecar_path(source_path: Path, meta_prompting: dict) -> Path:
    suffix = str(meta_prompting["automatic"]["default_per_source_output_suffix"]).strip()
    stem_base = source_path.with_suffix("")
    return stem_base.parent / f"{stem_base.name}{suffix}"


def _canonical_week_sidecar_path(week_dir: Path, meta_prompting: dict) -> Path:
    filename = str(meta_prompting["automatic"]["default_weekly_output_name"]).strip()
    return week_dir / filename


def _read_prompt_sidecars(
    candidates: list[Path],
    meta_note_overrides: dict[Path, str] | None = None,
) -> str:
    return prompting._read_prompt_sidecars(
        candidates,
        meta_note_overrides=meta_note_overrides,
    )


def _strip_markdown_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        parts = stripped.split("\n", 1)
        if len(parts) == 2:
            stripped = parts[1]
        stripped = stripped.rsplit("```", 1)[0].strip()
    return stripped


def _extract_text_file_for_meta_prompt(path: Path, max_chars: int) -> str | None:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"failed to read text from {path.name}: {exc}") from exc
    if not text:
        return None
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n[...truncated...]"
    return text


def _extract_source_excerpt_for_meta_prompt(path: Path, max_chars: int) -> str | None:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        raise MetaPromptInputError(
            f"local PDF extraction is disabled for meta prompting ({path.name}); send PDFs directly to Gemini"
        )
    if suffix in TEXT_SOURCE_EXTENSIONS:
        return _extract_text_file_for_meta_prompt(path, max_chars)
    return _extract_text_file_for_meta_prompt(path, max_chars)


def _meta_prompt_sections(prompt_type: str) -> tuple[str, list[str]]:
    if prompt_type == "single_slide":
        return (
            "The source is a slide deck. Reconstruct the lecture logic and use the teaching framing to identify what matters most to understand.",
            [
                "## Lecture logic",
                "## High-priority distinctions",
                "## Likely simplifications or gaps",
                "## Productive tensions or limitations",
            ],
        )
    if prompt_type == "weekly_readings_only":
        return (
            "The sources belong to one lecture block and should be read together, with slide-informed teaching framing helping prioritize the explanation.",
            [
                "## Shared problem",
                "## Cross-reading distinctions and tensions",
                "## Likely misunderstandings",
                "## What to prioritize",
            ],
        )
    if prompt_type == "mixed_sources":
        return (
            "The sources mix slides and readings. Use slides for structure and prioritization, and readings for nuance and argument depth.",
            [
                "## Lecture frame",
                "## Distinctions and tensions across source types",
                "## Likely misunderstandings",
                "## What to prioritize",
            ],
        )
    return (
        "The source is a reading. Prioritize distinctions, argument structure, and what a student is likely to get wrong.",
        [
            "## Core distinctions",
            "## Tensions, corrections, or qualifications",
            "## Likely misunderstandings",
            "## What to carry forward",
        ],
    )


def _build_meta_prompt_source_payload(job: MetaPromptJob, meta_prompting: dict) -> str:
    automatic = meta_prompting["automatic"]
    max_chars_per_source = int(automatic["max_chars_per_source"])
    max_total_chars = int(automatic["max_total_chars"])
    sections: list[str] = []
    total_chars = 0

    for source_item in job.source_items:
        excerpt = _extract_source_excerpt_for_meta_prompt(source_item.path, max_chars_per_source)
        if not excerpt:
            continue
        remaining = max_total_chars - total_chars
        if remaining <= 0:
            break
        if len(excerpt) > remaining:
            excerpt = excerpt[:remaining].rstrip() + "\n[...truncated...]"
        total_chars += len(excerpt)
        sections.append(
            "\n".join(
                [
                    f"### Source: {source_item.base_name}",
                    f"- type: {source_item.source_type}",
                    f"- filename: {source_item.path.name}",
                    "",
                    excerpt,
                ]
            )
        )

    if not sections:
        raise RuntimeError(f"no usable inline text source found for {job.label}")
    return "\n\n".join(sections)


def _build_meta_prompt_request(
    *,
    job: MetaPromptJob,
    course_title: str,
    source_payload: str,
) -> tuple[str, str]:
    scenario_instruction, section_headings = _meta_prompt_sections(job.prompt_type)
    system_prompt = (
        "You write concise Markdown pre-analysis notes for a NotebookLM deep-dive audio prompt. "
        "Do not summarize mechanically. Surface distinctions, tensions, corrections, misunderstandings, "
        "and the material that matters most to understand. Return Markdown only, with the requested headings and short bullets."
    )
    user_prompt = "\n".join(
        [
            f"Course: {course_title}",
            f"Scenario: {job.prompt_type}",
            f"Label: {job.label}",
            scenario_instruction,
            "",
            "Write a short analysis note that will steer NotebookLM away from generic summarization.",
            "Under each heading, use 2-4 concrete bullets grounded in the supplied material.",
            "Do not add any preamble or conclusion outside the headings.",
            "",
            "Use exactly these headings:",
            "\n".join(section_headings),
            "",
            "Source material excerpt(s):",
            source_payload,
        ]
    )
    return system_prompt, user_prompt


def _build_text_meta_prompt_request(
    *,
    job: MetaPromptJob,
    course_title: str,
    meta_prompting: dict,
) -> tuple[str, str]:
    return _build_meta_prompt_request(
        job=job,
        course_title=course_title,
        source_payload=_build_meta_prompt_source_payload(job, meta_prompting),
    )


def _infer_meta_prompt_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix in {".md", ".markdown", ".txt"}:
        return "text/plain"
    if suffix in {".html", ".htm"}:
        return "text/html"
    if suffix == ".json":
        return "application/json"
    if suffix == ".csv":
        return "text/csv"
    return "application/octet-stream"


def _stage_gemini_upload_path(path: Path) -> tuple[Path, Path]:
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", path.stem).strip("._") or "source"
    staged_dir = Path(tempfile.mkdtemp(prefix="gemini-upload-"))
    staged_path = staged_dir / f"{safe_stem}{path.suffix.lower() or '.bin'}"
    shutil.copy2(path, staged_path)
    return staged_path, staged_dir


def _wait_for_gemini_file_ready(client: object, uploaded: object, path: Path) -> GeminiUploadedFile:
    file_name = str(getattr(uploaded, "name", "") or "").strip()
    if not file_name:
        raise MetaPromptInputError(f"Gemini upload returned no file name for PDF {path.name}")

    def ready_file(file_obj: object) -> GeminiUploadedFile:
        file_uri = str(getattr(file_obj, "uri", "") or "").strip()
        mime_type = str(getattr(file_obj, "mime_type", "") or "").strip() or _infer_meta_prompt_mime_type(path)
        if not file_uri:
            raise MetaPromptInputError(f"Gemini upload returned no URI for PDF {path.name}")
        return GeminiUploadedFile(name=file_name, uri=file_uri, mime_type=mime_type)

    state = getattr(uploaded, "state", None)
    if state is None:
        return ready_file(uploaded)

    deadline = time.time() + GEMINI_FILE_POLL_TIMEOUT_SECONDS
    latest = uploaded
    while True:
        state = getattr(latest, "state", None)
        if state is None:
            return ready_file(latest)
        if str(state).endswith("ACTIVE"):
            return ready_file(latest)
        if str(state).endswith("FAILED"):
            error = getattr(latest, "error", None)
            detail = f": {error}" if error else ""
            raise MetaPromptInputError(f"Gemini could not process PDF {path.name}{detail}")
        if time.time() >= deadline:
            raise MetaPromptInputError(
                f"Gemini timed out while preparing PDF {path.name} for meta prompting"
            )
        time.sleep(GEMINI_FILE_POLL_INTERVAL_SECONDS)
        try:
            latest = client.files.get(name=file_name)
        except Exception as exc:
            raise MetaPromptInputError(
                f"failed to poll Gemini file state for PDF {path.name}: {exc}"
            ) from exc


def _delete_gemini_uploaded_files(client: object, uploaded_files: list[GeminiUploadedFile]) -> None:
    for uploaded in uploaded_files:
        try:
            client.files.delete(name=uploaded.name)
        except Exception as exc:
            _warn_meta_prompt_once(
                f"automatic meta-prompting could not delete Gemini upload {uploaded.name}: {exc}"
            )


def _build_gemini_meta_prompt_inputs(
    *,
    job: MetaPromptJob,
    course_title: str,
    meta_prompting: dict,
    backend: MetaPromptBackend,
) -> tuple[str, list[object], list[GeminiUploadedFile]]:
    automatic = meta_prompting["automatic"]
    max_chars_per_source = int(automatic["max_chars_per_source"])
    max_total_chars = int(automatic["max_total_chars"])
    total_chars = 0
    inline_sections: list[str] = []
    uploaded_files: list[GeminiUploadedFile] = []
    uploaded_files_by_path: dict[Path, GeminiUploadedFile] = {}
    try:
        for source_item in job.source_items:
            if source_item.path.suffix.lower() == ".pdf":
                if not source_item.path.exists():
                    raise MetaPromptInputError(f"source PDF does not exist: {source_item.path}")
                try:
                    staged_path, staged_dir = _stage_gemini_upload_path(source_item.path)
                except OSError as exc:
                    raise MetaPromptInputError(
                        f"failed to stage PDF {source_item.path.name} for Gemini upload: {exc}"
                    ) from exc
                try:
                    uploaded = backend.client.files.upload(
                        file=str(staged_path),
                        config={"mime_type": "application/pdf"},
                    )
                except Exception as exc:
                    raise MetaPromptInputError(
                        f"failed to upload PDF {source_item.path.name} to Gemini: {exc}"
                    ) from exc
                finally:
                    shutil.rmtree(staged_dir, ignore_errors=True)
                ready_file = _wait_for_gemini_file_ready(backend.client, uploaded, source_item.path)
                uploaded_files.append(ready_file)
                uploaded_files_by_path[source_item.path] = ready_file
                continue

            excerpt = _extract_source_excerpt_for_meta_prompt(source_item.path, max_chars_per_source)
            if not excerpt:
                continue
            remaining = max_total_chars - total_chars
            if remaining <= 0:
                break
            if len(excerpt) > remaining:
                excerpt = excerpt[:remaining].rstrip() + "\n[...truncated...]"
            total_chars += len(excerpt)
            inline_sections.append(
                "\n".join(
                    [
                        f"### Source: {source_item.base_name}",
                        f"- type: {source_item.source_type}",
                        f"- filename: {source_item.path.name}",
                        "",
                        excerpt,
                    ]
                )
            )

        source_payload_sections: list[str] = []
        if uploaded_files:
            source_payload_sections.append(
                "Attached source file(s) to inspect directly in Gemini:\n"
                + "\n".join(
                    f"- {source_item.base_name} ({source_item.path.name})"
                    for source_item in job.source_items
                    if source_item.path.suffix.lower() == ".pdf"
                )
            )
        if inline_sections:
            source_payload_sections.append(
                "Inline source material excerpt(s):\n" + "\n\n".join(inline_sections)
            )
        if not source_payload_sections:
            raise RuntimeError(f"no usable source material found for {job.label}")

        system_prompt, user_prompt = _build_meta_prompt_request(
            job=job,
            course_title=course_title,
            source_payload="\n\n".join(source_payload_sections),
        )
        contents: list[object] = [backend.support.Part.from_text(text=user_prompt)]
        for source_item in job.source_items:
            if source_item.path.suffix.lower() != ".pdf":
                continue
            uploaded = uploaded_files_by_path[source_item.path]
            contents.append(
                backend.support.Part.from_text(
                    text=(
                        f"Source file: {source_item.base_name}\n"
                        f"Type: {source_item.source_type}\n"
                        f"Filename: {source_item.path.name}"
                    )
                )
            )
            contents.append(
                backend.support.Part.from_uri(file_uri=uploaded.uri, mime_type=uploaded.mime_type)
            )
        return system_prompt, contents, uploaded_files
    except Exception:
        if uploaded_files:
            _delete_gemini_uploaded_files(backend.client, uploaded_files)
        raise


def _gemini_api_key() -> str:
    return str(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or "").strip()


def _meta_prompt_backend_for_automatic(meta_prompting: dict) -> MetaPromptBackend:
    provider = str(meta_prompting["automatic"]["provider"]).strip().lower()
    if provider == "gemini":
        api_key = _gemini_api_key()
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY or GOOGLE_API_KEY is not set")
        try:
            from google import genai
            from google.genai import types as genai_types
        except ImportError as exc:
            raise RuntimeError("google-genai package not installed — pip install google-genai") from exc
        return MetaPromptBackend(
            provider="gemini",
            client=genai.Client(api_key=api_key),
            support=genai_types,
        )

    if provider == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError("anthropic package not installed — pip install anthropic") from exc
        return MetaPromptBackend(
            provider="anthropic",
            client=anthropic.Anthropic(),
            support=anthropic,
        )

    raise RuntimeError(f"Unsupported meta-prompting provider: {provider}")


def _is_meta_prompt_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).strip().lower()
    return any(
        token in text
        for token in (
            "rate limit",
            "resource_exhausted",
            "resource exhausted",
            "quota",
            "too many requests",
            "429",
        )
    )


def _extract_gemini_text(response: object) -> str:
    text = str(getattr(response, "text", "") or "").strip()
    if text:
        return text
    parts: list[str] = []
    for candidate in getattr(response, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", []) or []:
            value = getattr(part, "text", "")
            if value:
                parts.append(str(value))
    return "\n".join(parts).strip()


def generate_meta_prompt_markdown(
    *,
    job: MetaPromptJob,
    course_title: str,
    meta_prompting: dict,
    backend: MetaPromptBackend,
) -> str:
    uploaded_files: list[GeminiUploadedFile] = []
    try:
        if backend.provider == "gemini":
            system_prompt, gemini_contents, uploaded_files = _build_gemini_meta_prompt_inputs(
                job=job,
                course_title=course_title,
                meta_prompting=meta_prompting,
                backend=backend,
            )
            anthropic_user_prompt = ""
        else:
            system_prompt, anthropic_user_prompt = _build_text_meta_prompt_request(
                job=job,
                course_title=course_title,
                meta_prompting=meta_prompting,
            )
            gemini_contents = []
        for attempt in range(2):
            try:
                if backend.provider == "gemini":
                    response = backend.client.models.generate_content(
                        model=str(meta_prompting["automatic"]["model"]).strip(),
                        contents=gemini_contents,
                        config=backend.support.GenerateContentConfig(
                            system_instruction=system_prompt,
                            max_output_tokens=META_PROMPT_MAX_RESPONSE_TOKENS,
                        ),
                    )
                    content = _strip_markdown_fence(_extract_gemini_text(response))
                elif backend.provider == "anthropic":
                    message = backend.client.messages.create(
                        model=str(meta_prompting["automatic"]["model"]).strip(),
                        max_tokens=META_PROMPT_MAX_RESPONSE_TOKENS,
                        system=system_prompt,
                        messages=[{"role": "user", "content": anthropic_user_prompt}],
                    )
                    parts = [
                        getattr(part, "text", "")
                        for part in getattr(message, "content", [])
                        if getattr(part, "type", "") == "text"
                    ]
                    content = _strip_markdown_fence("\n".join(parts).strip())
                else:
                    raise RuntimeError(f"Unsupported meta-prompting provider: {backend.provider}")
                if not content:
                    raise RuntimeError(f"empty response while generating meta prompt for {job.label}")
                return content
            except Exception as exc:
                if _is_meta_prompt_rate_limit_error(exc):
                    if attempt == 0:
                        print(
                            f"Meta prompt generation hit a {backend.provider} rate limit; "
                            "waiting 60s before retrying."
                        )
                        time.sleep(60)
                        continue
                    raise RuntimeError(f"rate-limited while generating meta prompt for {job.label}") from exc
                raise RuntimeError(f"meta prompt generation failed for {job.label}: {exc}") from exc
    finally:
        if uploaded_files:
            _delete_gemini_uploaded_files(backend.client, uploaded_files)


def build_auto_meta_prompt_jobs(
    *,
    week_dir: Path,
    week_label: str,
    reading_sources: list[SourceItem],
    generation_sources: list[SourceItem],
    generate_weekly_overview: bool,
    meta_prompting: dict,
) -> list[MetaPromptJob]:
    if not meta_prompting.get("enabled", False):
        return []
    automatic = meta_prompting.get("automatic") or {}
    if not automatic.get("enabled", False):
        return []

    jobs: list[MetaPromptJob] = []
    if generate_weekly_overview and reading_sources:
        candidates = _week_prompt_sidecar_candidates(week_dir, week_label, meta_prompting)
        if not any(path.exists() and path.is_file() for path in candidates):
            jobs.append(
                MetaPromptJob(
                    prompt_type="weekly_readings_only",
                    output_path=_canonical_week_sidecar_path(week_dir, meta_prompting),
                    label=f"{week_label} weekly overview",
                    source_items=tuple(reading_sources),
                    week_label=week_label,
                )
            )

    for source_item in generation_sources:
        candidates = _source_prompt_sidecar_candidates(source_item.path, meta_prompting)
        if any(path.exists() and path.is_file() for path in candidates):
            continue
        jobs.append(
            MetaPromptJob(
                prompt_type="single_slide" if source_item.source_type == "slide" else "single_reading",
                output_path=_canonical_source_sidecar_path(source_item.path, meta_prompting),
                label=source_item.base_name,
                source_items=(source_item,),
                week_label=week_label,
            )
        )
    return jobs


def prepare_auto_meta_prompt_overrides(
    *,
    course_title: str,
    week_dir: Path,
    week_label: str,
    reading_sources: list[SourceItem],
    generation_sources: list[SourceItem],
    generate_weekly_overview: bool,
    meta_prompting: dict,
    dry_run: bool,
) -> tuple[dict[Path, str], list[str]]:
    jobs = build_auto_meta_prompt_jobs(
        week_dir=week_dir,
        week_label=week_label,
        reading_sources=reading_sources,
        generation_sources=generation_sources,
        generate_weekly_overview=generate_weekly_overview,
        meta_prompting=meta_prompting,
    )
    if not jobs:
        return {}, []

    automatic = meta_prompting["automatic"]
    try:
        backend = _meta_prompt_backend_for_automatic(meta_prompting)
    except RuntimeError as exc:
        if automatic.get("fail_open", True):
            _warn_meta_prompt_once(f"automatic meta-prompting is disabled for this run: {exc}")
            return {}, []
        raise SystemExit(f"automatic meta-prompting failed before generation: {exc}") from exc

    overrides: dict[Path, str] = {}
    messages: list[str] = []
    for job in jobs:
        try:
            content = generate_meta_prompt_markdown(
                job=job,
                course_title=course_title,
                meta_prompting=meta_prompting,
                backend=backend,
            )
        except MetaPromptInputError as exc:
            raise SystemExit(
                f"automatic meta-prompting failed for {job.label}: {exc}"
            ) from exc
        except RuntimeError as exc:
            if automatic.get("fail_open", True):
                _warn_meta_prompt_once(f"automatic meta-prompting skipped {job.label}: {exc}")
                continue
            raise SystemExit(f"automatic meta-prompting failed for {job.label}: {exc}") from exc

        if dry_run:
            overrides[job.output_path] = content
        else:
            try:
                job.output_path.write_text(content.rstrip() + "\n", encoding="utf-8")
            except OSError as exc:
                if automatic.get("fail_open", True):
                    _warn_meta_prompt_once(
                        f"automatic meta-prompting could not write {job.output_path.name}: {exc}"
                    )
                    continue
                raise SystemExit(
                    f"automatic meta-prompting could not write {job.output_path}: {exc}"
                ) from exc
            overrides[job.output_path] = content
        status = "META WOULD GENERATE" if dry_run else "META GENERATED"
        messages.append(f"{status}: {job.output_path}")
    return overrides, messages


def build_prompt_debug_lines(label: str, prompt: str) -> list[str]:
    lines = [f"PROMPT {label}:"]
    for line in prompt.splitlines():
        lines.append(f"    {line}" if line else "    ")
    return lines


def build_audio_prompt(
    *,
    prompt_type: str,
    prompt_strategy: dict | None,
    exam_focus: dict | None,
    study_context: dict | None,
    prompt_framework: dict | None,
    meta_prompting: dict | None,
    course_title: str | None = None,
    course_context_note: str | None = None,
    course_context_heading: str | None = None,
    meta_note_overrides: dict[Path, str] | None = None,
    custom_prompt: str,
    audio_format: str | None = None,
    audio_length: str | None = None,
    source_item: SourceItem | None = None,
    source_items: list[SourceItem] | None = None,
    week_dir: Path | None = None,
    week_label: str | None = None,
) -> str:
    return prompting.build_audio_prompt(
        prompt_type=prompt_type,
        prompt_strategy=prompt_strategy,
        exam_focus=exam_focus,
        study_context=study_context,
        prompt_framework=prompt_framework,
        meta_prompting=meta_prompting,
        course_title=course_title,
        course_context_note=course_context_note,
        course_context_heading=course_context_heading,
        meta_note_overrides=meta_note_overrides,
        custom_prompt=custom_prompt,
        audio_format=audio_format,
        audio_length=audio_length,
        source_item=source_item,
        source_items=source_items,
        week_dir=week_dir,
        week_label=week_label,
    )


def build_report_prompt(
    *,
    prompt_type: str,
    prompt_strategy: dict | None,
    course_context_note: str | None,
    course_context_heading: str | None,
    study_context: dict | None,
    meta_prompting: dict | None,
    meta_note_overrides: dict[Path, str] | None = None,
    custom_prompt: str,
    source_item: SourceItem | None = None,
    source_items: list[SourceItem] | None = None,
    week_dir: Path | None = None,
    week_label: str | None = None,
) -> str:
    return prompting.build_report_prompt(
        prompt_type=prompt_type,
        prompt_strategy=prompt_strategy,
        course_context_note=course_context_note,
        course_context_heading=course_context_heading,
        study_context=study_context,
        meta_prompting=meta_prompting,
        meta_note_overrides=meta_note_overrides,
        custom_prompt=custom_prompt,
        source_item=source_item,
        source_items=source_items,
        week_dir=week_dir,
        week_label=week_label,
    )


def build_course_context_note(
    *,
    course_context_bundle: course_context_helpers.CoursePromptContextBundle | None,
    course_context_cfg: dict | None,
    lecture_key: str | None,
    prompt_type: str,
    source_item: SourceItem | None = None,
) -> str:
    if course_context_bundle is None or not course_context_cfg or not lecture_key:
        return ""
    return course_context_helpers.build_course_prompt_context_note(
        bundle=course_context_bundle,
        config=course_context_cfg,
        lecture_key=lecture_key,
        prompt_type=prompt_type,
        source_item=source_item,
    )


def normalize_slide_key(value: object) -> str:
    return str(value or "").strip().lower()


def parse_slide_key_filter(value: str | None) -> set[str]:
    if not value:
        return set()
    keys = {normalize_slide_key(part) for part in value.split(",")}
    keys.discard("")
    if not keys:
        raise SystemExit("--only-slide did not contain any valid slide keys.")
    return keys


def validate_audio_choice(
    section: str,
    field: str,
    value: object,
    allowed: set[str],
) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise SystemExit(
            f"Unknown {section}.{field} '{value}'. Allowed values: {allowed_values}."
        )
    return normalized


def parse_per_slide_overrides(per_slide_cfg: dict) -> dict[str, dict]:
    raw_overrides = per_slide_cfg.get("overrides")
    if raw_overrides in (None, ""):
        return {}
    if not isinstance(raw_overrides, dict):
        raise SystemExit("per_slide.overrides must be an object keyed by slide_key.")

    overrides: dict[str, dict] = {}
    for raw_key, raw_override in raw_overrides.items():
        slide_key = normalize_slide_key(raw_key)
        if not slide_key:
            raise SystemExit("per_slide.overrides contains an empty slide key.")
        if slide_key in overrides:
            raise SystemExit(f"Duplicate per_slide override key after normalization: {slide_key}")
        if not isinstance(raw_override, dict):
            raise SystemExit(f"per_slide.overrides.{slide_key} must be an object.")

        unknown_keys = sorted(set(raw_override) - PER_SLIDE_OVERRIDE_KEYS)
        if unknown_keys:
            allowed = ", ".join(sorted(PER_SLIDE_OVERRIDE_KEYS))
            raise SystemExit(
                f"Unknown per_slide override field(s) for {slide_key}: "
                f"{', '.join(unknown_keys)}. Allowed fields: {allowed}."
            )

        override = dict(raw_override)
        if "format" in override:
            override["format"] = validate_audio_choice(
                f"per_slide.overrides.{slide_key}",
                "format",
                override["format"],
                AUDIO_FORMAT_VALUES,
            )
        if "length" in override:
            override["length"] = validate_audio_choice(
                f"per_slide.overrides.{slide_key}",
                "length",
                override["length"],
                AUDIO_LENGTH_VALUES,
            )
        if "prompt" in override and not isinstance(override["prompt"], str):
            raise SystemExit(f"per_slide.overrides.{slide_key}.prompt must be a string.")
        overrides[slide_key] = override
    return overrides


def validate_per_slide_audio_config(per_slide_cfg: dict) -> dict[str, dict]:
    if "format" in per_slide_cfg:
        validate_audio_choice("per_slide", "format", per_slide_cfg["format"], AUDIO_FORMAT_VALUES)
    if "length" in per_slide_cfg:
        validate_audio_choice("per_slide", "length", per_slide_cfg["length"], AUDIO_LENGTH_VALUES)
    if "prompt" in per_slide_cfg and not isinstance(per_slide_cfg["prompt"], str):
        raise SystemExit("per_slide.prompt must be a string.")
    return parse_per_slide_overrides(per_slide_cfg)


def build_language_variants(config: dict) -> list[dict]:
    variants: list[dict] = []
    raw = config.get("languages")
    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, str):
                code = entry.strip()
                if code:
                    variants.append({"code": code, "suffix": "", "title_suffix": ""})
                continue
            if not isinstance(entry, dict):
                continue
            code = (entry.get("code") or "").strip()
            if not code:
                continue
            suffix = (entry.get("suffix") or "").strip()
            title_suffix = (entry.get("title_suffix") or suffix).strip()
            variants.append({"code": code, "suffix": suffix, "title_suffix": title_suffix})

    if not variants:
        code = (config.get("language") or "").strip()
        variants.append({"code": code or None, "suffix": "", "title_suffix": ""})

    return variants


def apply_suffix(name: str, suffix: str) -> str:
    return f"{name} {suffix}".strip() if suffix else name


def apply_path_suffix(path: Path, suffix: str) -> Path:
    if not suffix:
        return path
    return path.with_name(f"{path.stem} {suffix}{path.suffix}")


def compute_config_tag(config: dict, tag_len: int) -> str:
    if tag_len < 1:
        raise ValueError("config tag length must be >= 1")
    canonical = json.dumps(
        config,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return digest[:tag_len]


def strip_cfg_tag_stem(stem: str) -> str:
    cleaned = CFG_TAG_PATTERN.sub("", stem)
    return cleaned.rstrip()


def _normalize_tag_value(value: str | None, default: str = "default") -> str:
    if value is None:
        return default
    cleaned = str(value).strip().lower()
    if not cleaned:
        return default
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = re.sub(r"[^a-z0-9._:+-]", "-", cleaned)
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned or default


def build_output_cfg_tag_token(
    *,
    content_type: str,
    language: str | None,
    instructions: str,
    audio_format: str | None,
    audio_length: str | None,
    infographic_orientation: str | None,
    infographic_detail: str | None,
    quiz_quantity: str | None,
    quiz_difficulty: str | None,
    quiz_format: str | None,
    report_format: str | None = None,
    source_count: int | None,
    hash_len: int,
) -> str:
    normalized_content_type = _normalize_tag_value(content_type)
    normalized_language = _normalize_tag_value(language, default="default")
    normalized_audio_format = _normalize_tag_value(audio_format, default="deep-dive")
    normalized_audio_length = _normalize_tag_value(audio_length, default="default")
    normalized_infographic_orientation = _normalize_tag_value(
        infographic_orientation, default="default"
    )
    normalized_infographic_detail = _normalize_tag_value(infographic_detail, default="default")
    normalized_quiz_quantity = _normalize_tag_value(quiz_quantity, default="default")
    normalized_quiz_difficulty = _normalize_tag_value(quiz_difficulty, default="default")
    normalized_quiz_format = _normalize_tag_value(quiz_format, default="json")
    normalized_report_format = _normalize_tag_value(report_format, default="study-guide")

    parts = [
        f"type={normalized_content_type}",
        f"lang={normalized_language}",
    ]
    hash_payload: dict[str, str | int | None] = {
        "schema_version": 1,
        "content_type": normalized_content_type,
        "language": normalized_language,
        "instructions": instructions or "",
    }
    if content_type == "audio":
        parts.append(f"format={normalized_audio_format}")
        parts.append(f"length={normalized_audio_length}")
        hash_payload["audio_format"] = normalized_audio_format
        hash_payload["audio_length"] = normalized_audio_length
        if source_count is not None:
            if source_count < 0:
                raise ValueError("source_count must be >= 0")
            parts.append(f"sources={source_count}")
            hash_payload["source_count"] = source_count
    elif content_type == "infographic":
        parts.append(f"orientation={normalized_infographic_orientation}")
        parts.append(f"detail={normalized_infographic_detail}")
        hash_payload["infographic_orientation"] = normalized_infographic_orientation
        hash_payload["infographic_detail"] = normalized_infographic_detail
    elif content_type == "quiz":
        parts.append(f"quantity={normalized_quiz_quantity}")
        parts.append(f"difficulty={normalized_quiz_difficulty}")
        if normalized_quiz_format != "html":
            parts.append(f"download={normalized_quiz_format}")
        hash_payload["quiz_quantity"] = normalized_quiz_quantity
        hash_payload["quiz_difficulty"] = normalized_quiz_difficulty
        hash_payload["quiz_download_format"] = normalized_quiz_format
    elif content_type == "report":
        parts.append(f"format={normalized_report_format}")
        hash_payload["report_format"] = normalized_report_format

    effective_hash = compute_config_tag(hash_payload, hash_len)
    parts.append(f"hash={effective_hash}")
    return " {" + " ".join(parts) + "}"


def _truncate_utf8(value: str, max_bytes: int) -> str:
    if max_bytes <= 0:
        return ""
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    truncated = encoded[:max_bytes]
    while truncated:
        try:
            return truncated.decode("utf-8")
        except UnicodeDecodeError:
            truncated = truncated[:-1]
    return ""


def apply_config_tag(path: Path, cfg_tag_token: str | None) -> Path:
    if not cfg_tag_token:
        return path
    if len((cfg_tag_token + path.suffix).encode("utf-8")) >= MAX_FILENAME_BYTES:
        raise SystemExit(
            "Config tag is too long for filename safety. "
            "Use a smaller --config-tag-len value."
        )

    base_stem = strip_cfg_tag_stem(path.stem)
    tagged_stem = f"{base_stem}{cfg_tag_token}"
    tagged_name = f"{tagged_stem}{path.suffix}"
    if len(tagged_name.encode("utf-8")) <= MAX_FILENAME_BYTES:
        return path.with_name(tagged_name)

    tail = f"{cfg_tag_token}{path.suffix}"
    allowed_stem_bytes = MAX_FILENAME_BYTES - len(tail.encode("utf-8"))
    truncated = _truncate_utf8(base_stem, allowed_stem_bytes).rstrip()
    if not truncated:
        truncated = _truncate_utf8("output", allowed_stem_bytes).rstrip() or "o"
    tagged_stem = f"{truncated}{cfg_tag_token}"
    tagged_name = f"{tagged_stem}{path.suffix}"
    while len(tagged_name.encode("utf-8")) > MAX_FILENAME_BYTES and truncated:
        truncated = truncated[:-1].rstrip()
        tagged_stem = f"{truncated or 'o'}{cfg_tag_token}"
        tagged_name = f"{tagged_stem}{path.suffix}"

    print(
        "Warning: output filename exceeded 255-byte limit; truncated stem for tagged output: "
        f"{path.name} -> {tagged_name}"
    )
    return path.with_name(tagged_name)


def _unique_quarantine_path(target: Path) -> Path:
    if not target.exists():
        return target
    for index in range(2, 1000):
        candidate = target.with_name(f"{target.stem} [{index}]{target.suffix}")
        if not candidate.exists():
            return candidate
    raise SystemExit(f"Unable to find unique quarantine path for {target}")


def _slide_audio_sidecar_paths(output_path: Path) -> list[Path]:
    return [
        output_path.with_suffix(output_path.suffix + ".request.json"),
        output_path.with_suffix(output_path.suffix + ".request.error.json"),
    ]


def quarantine_stale_slide_audio_outputs(
    *,
    repo_root: Path,
    week_output_dir: Path,
    canonical_output_path: Path,
    timestamp: str,
) -> list[tuple[Path, Path]]:
    if not week_output_dir.exists():
        return []

    base_stem = strip_cfg_tag_stem(canonical_output_path.stem)
    moved: list[tuple[Path, Path]] = []
    candidates: list[Path] = []
    for entry in sorted(week_output_dir.iterdir(), key=lambda path: path.name):
        if not entry.is_file():
            continue
        if entry == canonical_output_path:
            continue
        if entry.suffix.casefold() != canonical_output_path.suffix.casefold():
            continue
        if "{type=audio" not in entry.name.casefold():
            continue
        if strip_cfg_tag_stem(entry.stem) != base_stem:
            continue
        candidates.append(entry)

    if not candidates:
        return []

    quarantine_dir = repo_root / SLIDE_AUDIO_QUARANTINE_ROOT / timestamp / week_output_dir.name
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    for entry in candidates:
        target = _unique_quarantine_path(quarantine_dir / entry.name)
        entry.rename(target)
        moved.append((entry, target))
        for sidecar in _slide_audio_sidecar_paths(entry):
            if not sidecar.exists() or not sidecar.is_file():
                continue
            sidecar_target = _unique_quarantine_path(quarantine_dir / sidecar.name)
            sidecar.rename(sidecar_target)
            moved.append((sidecar, sidecar_target))
    return moved


def resolve_profile_slug(profile: str | None, storage: str | None) -> str | None:
    if profile:
        return profile
    if storage:
        return Path(storage).stem
    return None


def apply_profile_subdir(output_root: Path, slug: str | None, enabled: bool) -> Path:
    if not enabled or not slug:
        return output_root
    safe_slug = re.sub(r"[^A-Za-z0-9._-]+", "_", slug).strip("_")
    return output_root / (safe_slug or slug)


RATE_LIMIT_TOKENS = (
    "rate limit",
    "quota exceeded",
    "resource_exhausted",
    "too many requests",
)
AUTH_TOKENS = (
    "authentication expired",
    "auth expired",
    "auth invalid",
    "invalid authentication",
    "not logged in",
    "run 'notebooklm login'",
    "redirected to",
)
PROFILE_ERROR_TOKENS = (
    "no result found for rpc id: ccqfvf",
    "rpc ccqfvf returned null result data",
    "profile-scoped notebook creation failure",
    "profile-scoped notebooklm rpc failure",
)
AUTH_COOLDOWN_SECONDS = 3600


def is_rate_limit_error(message: str) -> bool:
    lowered = message.lower()
    return any(token in lowered for token in RATE_LIMIT_TOKENS) or _has_status_code_context(
        lowered,
        429,
        extra_phrases=("too many requests",),
    )


def is_auth_error(message: str) -> bool:
    lowered = message.lower()
    return any(token in lowered for token in AUTH_TOKENS) or _has_status_code_context(
        lowered,
        401,
        extra_phrases=("unauthorized",),
    ) or _has_status_code_context(
        lowered,
        403,
        extra_phrases=("forbidden",),
    )


def is_profile_error(message: str) -> bool:
    lowered = message.lower()
    return any(token in lowered for token in PROFILE_ERROR_TOKENS)


def _has_status_code_context(message: str, code: int, *, extra_phrases: tuple[str, ...] = ()) -> bool:
    code_pattern = rf"(?:http|status|code|rpc[_ ]code)\s*[:=]?\s*{code}\b"
    if re.search(code_pattern, message):
        return True
    return any(f"{code} {phrase}" in message for phrase in extra_phrases)


def update_profile_cooldowns(
    output_path: Path,
    cooldowns: dict[str, float],
    rate_limit_seconds: float,
    auth_seconds: float,
) -> None:
    now = time.time()
    log_paths = [
        output_path.with_suffix(output_path.suffix + ".request.json"),
        output_path.with_suffix(output_path.suffix + ".request.error.json"),
    ]
    for log_path in log_paths:
        if not log_path.exists():
            continue
        payload = json.loads(log_path.read_text(encoding="utf-8"))
        rotation_attempts = payload.get("rotation_attempts")
        if isinstance(rotation_attempts, list):
            for attempt in rotation_attempts:
                if not isinstance(attempt, dict):
                    continue
                profile = attempt.get("profile")
                error = str(attempt.get("error", ""))
                error_type = str(attempt.get("error_type", ""))
                if profile and (error_type == "rate_limit" or is_rate_limit_error(error)):
                    cooldowns[profile] = max(
                        cooldowns.get(profile, 0), now + rate_limit_seconds
                    )
                if profile and (error_type == "auth" or is_auth_error(error)):
                    cooldowns[profile] = max(
                        cooldowns.get(profile, 0), now + auth_seconds
                    )
                if profile and (error_type == "profile_error" or is_profile_error(error)):
                    cooldowns[profile] = max(
                        cooldowns.get(profile, 0), now + auth_seconds
                    )

        error = str(payload.get("error", ""))
        error_type = str(payload.get("error_type", ""))
        auth = payload.get("auth") if isinstance(payload.get("auth"), dict) else {}
        profile = auth.get("profile") if isinstance(auth, dict) else None
        if profile and (error_type == "rate_limit" or is_rate_limit_error(error)):
            cooldowns[profile] = max(
                cooldowns.get(profile, 0), now + rate_limit_seconds
            )
        if profile and (error_type == "auth" or is_auth_error(error)):
            cooldowns[profile] = max(cooldowns.get(profile, 0), now + auth_seconds)
        if profile and (error_type == "profile_error" or is_profile_error(error)):
            cooldowns[profile] = max(cooldowns.get(profile, 0), now + auth_seconds)
        break


def active_cooldowns(cooldowns: dict[str, float]) -> list[str]:
    now = time.time()
    return sorted([profile for profile, until in cooldowns.items() if until > now])


def maybe_sleep(seconds: float | None) -> None:
    if seconds and seconds > 0:
        time.sleep(seconds)


def ensure_dict(value: object | None) -> dict:
    return value if isinstance(value, dict) else {}


def parse_content_types(value: str | None) -> list[str]:
    if not value:
        return ["audio"]
    allowed = {"audio", "infographic", "quiz", "report"}
    items: list[str] = []
    for raw in value.split(","):
        item = raw.strip().lower()
        if not item:
            continue
        if item not in allowed:
            raise SystemExit(
                f"Unknown content type '{item}'. Allowed: {', '.join(sorted(allowed))}."
            )
        if item not in items:
            items.append(item)
    if not items:
        raise SystemExit("No valid content types provided.")
    return items


def normalize_quiz_quantity(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    allowed = {"fewer", "standard", "more"}
    if normalized not in allowed:
        raise SystemExit(
            f"Unknown quiz quantity '{value}'. Allowed: {', '.join(sorted(allowed))}."
        )
    return normalized


def normalize_quiz_difficulty(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    allowed = {"easy", "medium", "hard", "all"}
    if normalized not in allowed:
        raise SystemExit(
            f"Unknown quiz difficulty '{value}'. Allowed: {', '.join(sorted(allowed))}."
        )
    return normalized


def quiz_difficulty_values(content_type: str, configured_difficulty: str | None) -> list[str | None]:
    if content_type != "quiz":
        return [None]
    if configured_difficulty == "all":
        return ["easy", "medium", "hard"]
    return [configured_difficulty]


def normalize_quiz_format(value: str | None) -> str:
    if not value:
        return "json"
    normalized = value.strip().lower()
    allowed = {"json", "markdown", "html"}
    if normalized not in allowed:
        raise SystemExit(
            f"Unknown quiz format '{value}'. Allowed: {', '.join(sorted(allowed))}."
        )
    return normalized


def normalize_report_format(value: str | None) -> str:
    if not value:
        return "study-guide"
    normalized = str(value).strip().lower()
    if normalized not in REPORT_FORMAT_VALUES:
        raise SystemExit(
            f"Unknown report format '{value}'. Allowed: {', '.join(sorted(REPORT_FORMAT_VALUES))}."
        )
    return normalized


def output_extension(content_type: str, *, quiz_format: str | None = None) -> str:
    if content_type == "quiz":
        mapping = {
            "json": ".json",
            "markdown": ".md",
            "html": ".html",
        }
        return mapping[normalize_quiz_format(quiz_format)]
    mapping = {
        "audio": ".mp3",
        "infographic": ".png",
        "report": ".md",
    }
    return mapping[content_type]


def find_profiles_path(repo_root: Path, profiles_file: str | None) -> Path | None:
    effective_profiles_file = profiles_file or str(os.environ.get(PROFILES_FILE_ENV_VAR) or "").strip() or None
    if effective_profiles_file:
        path = Path(effective_profiles_file).expanduser()
        return path if path.exists() else None
    candidates = [
        Path.cwd() / "profiles.json",
        repo_root / "notebooklm-podcast-auto" / "profiles.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def default_storage_path() -> Path:
    home_override = os.environ.get("NOTEBOOKLM_HOME")
    if home_override:
        return (Path(home_override).expanduser() / "storage_state.json").resolve()
    return (Path.home() / ".notebooklm" / "storage_state.json").resolve()


def load_profiles(path: Path) -> dict[str, str]:
    raw = read_json(path)
    if isinstance(raw, dict) and isinstance(raw.get("profiles"), dict):
        raw = raw["profiles"]
    if not isinstance(raw, dict):
        return {}
    profiles: dict[str, str] = {}
    base_dir = path.parent
    for name, value in raw.items():
        if not isinstance(name, str):
            continue
        if value is None:
            continue
        raw_path = Path(str(value)).expanduser()
        if not raw_path.is_absolute():
            raw_path = (base_dir / raw_path).resolve()
        else:
            raw_path = raw_path.resolve()
        profiles[name] = str(raw_path)
    return profiles


def auto_profile_from_profiles(
    repo_root: Path, args: argparse.Namespace
) -> tuple[str | None, Path | None]:
    if args.profile or args.storage:
        return None, None
    profiles_path = find_profiles_path(repo_root, args.profiles_file)
    if not profiles_path:
        return None, None
    profiles = load_profiles(profiles_path)
    if not profiles:
        return None, None
    if "default" in profiles:
        return "default", profiles_path
    if len(profiles) == 1:
        return next(iter(profiles)), profiles_path
    default_path = default_storage_path()
    matches = [name for name, path in profiles.items() if Path(path).resolve() == default_path]
    if len(matches) == 1:
        print(
            "Warning: multiple profiles found; "
            f"auto-selecting '{matches[0]}' (matches default storage path)."
        )
        return matches[0], profiles_path
    name = sorted(profiles)[0]
    print(
        "Warning: multiple profiles found and no default set; "
        f"auto-selecting '{name}'. Consider adding a 'default' entry to profiles.json."
    )
    return name, profiles_path

def load_request_auth(output_path: Path) -> dict | None:
    for candidate in iter_output_aliases(output_path):
        log_path = candidate.with_suffix(candidate.suffix + ".request.json")
        if not log_path.exists():
            continue
        try:
            payload = json.loads(log_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        auth = payload.get("auth")
        if isinstance(auth, dict):
            return auth
    return None


def update_preferred_profile(output_path: Path, current: str | None) -> str | None:
    auth = load_request_auth(output_path)
    if not auth:
        return current
    profile = auth.get("profile")
    if profile:
        return str(profile)
    return current


def load_request_payload(output_path: Path) -> dict | None:
    for candidate in iter_output_aliases(output_path):
        payload = _load_request_payload_for_candidate(candidate)
        if payload:
            return payload
    return None


def request_log_has_artifact(output_path: Path) -> bool:
    payload = load_request_payload(output_path)
    if not payload:
        return False
    return bool(str(payload.get("artifact_id") or "").strip())


def legacy_weekly_overview_aliases(output_path: Path) -> list[Path]:
    new_marker = f" - {WEEKLY_OVERVIEW_TITLE}"
    if new_marker not in output_path.name:
        return []
    aliases: list[Path] = []
    for legacy_title in LEGACY_WEEKLY_OVERVIEW_TITLES:
        legacy_name = output_path.name.replace(new_marker, f" - {legacy_title}", 1)
        if legacy_name != output_path.name:
            aliases.append(output_path.with_name(legacy_name))
    return aliases


def legacy_prefixed_reading_aliases(output_path: Path) -> list[Path]:
    match = OUTPUT_TITLE_PREFIX_PATTERN.match(output_path.name)
    if not match:
        return []
    prefix, remainder = match.groups()
    if remainder.startswith("X "):
        return []
    if remainder.startswith(WEEKLY_OVERVIEW_TITLE) or any(
        remainder.startswith(title) for title in LEGACY_WEEKLY_OVERVIEW_TITLES
    ):
        return []
    if any(remainder.startswith(f"{label}: ") for label in SLIDE_SUBCATEGORY_LABELS.values()):
        return []
    return [output_path.with_name(f"{prefix}X {remainder}")]


def iter_output_aliases(output_path: Path) -> list[Path]:
    candidates = [output_path]
    seen = {output_path.name}
    for alias in [*legacy_weekly_overview_aliases(output_path), *legacy_prefixed_reading_aliases(output_path)]:
        if alias.name in seen:
            continue
        seen.add(alias.name)
        candidates.append(alias)
    return candidates


def _load_request_payload_for_candidate(output_path: Path) -> dict | None:
    log_path = output_path.with_suffix(output_path.suffix + ".request.json")
    if not log_path.exists():
        return None
    try:
        payload = json.loads(log_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def migrate_legacy_weekly_overview_outputs(week_output_dir: Path) -> list[tuple[Path, Path]]:
    if not week_output_dir.exists():
        return []

    migrated: list[tuple[Path, Path]] = []
    new_marker = f" - {WEEKLY_OVERVIEW_TITLE}"
    for entry in sorted(week_output_dir.iterdir(), key=lambda path: path.name):
        if not entry.is_file() or new_marker in entry.name:
            continue
        target: Path | None = None
        for legacy_title in LEGACY_WEEKLY_OVERVIEW_TITLES:
            legacy_marker = f" - {legacy_title}"
            if legacy_marker not in entry.name:
                continue
            candidate = entry.with_name(entry.name.replace(legacy_marker, new_marker, 1))
            if candidate != entry:
                target = candidate
                break
        if target is None or target.exists():
            continue
        entry.rename(target)
        migrated.append((entry, target))
    return migrated


def migrate_legacy_prefixed_reading_outputs(week_output_dir: Path) -> list[tuple[Path, Path]]:
    if not week_output_dir.exists():
        return []

    migrated: list[tuple[Path, Path]] = []
    for entry in sorted(week_output_dir.iterdir(), key=lambda path: path.name):
        if not entry.is_file():
            continue
        match = OUTPUT_TITLE_PREFIX_PATTERN.match(entry.name)
        if not match:
            continue
        prefix, remainder = match.groups()
        if not remainder.startswith("X "):
            continue
        if any(remainder.startswith(f"X {title}") for title in LEGACY_WEEKLY_OVERVIEW_TITLES):
            continue
        if remainder.startswith(f"X {WEEKLY_OVERVIEW_TITLE}"):
            continue
        if any(remainder.startswith(f"X {label}: ") for label in SLIDE_SUBCATEGORY_LABELS.values()):
            continue
        target = entry.with_name(f"{prefix}{remainder[2:]}")
        if target.exists():
            continue
        entry.rename(target)
        migrated.append((entry, target))
    return migrated


def should_skip_generation(output_path: Path, skip_existing: bool) -> tuple[bool, str | None]:
    for candidate in iter_output_aliases(output_path):
        if candidate.exists() and candidate.stat().st_size > 0:
            return True, "output exists"
    if not skip_existing:
        return False, None

    saw_error = False
    for candidate in iter_output_aliases(output_path):
        request_log = candidate.with_suffix(candidate.suffix + ".request.json")
        error_log = candidate.with_suffix(candidate.suffix + ".request.error.json")
        payload = _load_request_payload_for_candidate(candidate)
        artifact_id = payload.get("artifact_id") if payload else None
        has_request = bool(artifact_id)
        has_error = error_log.exists()

        if has_request and has_error:
            # Keep the newest status signal: a newer request means "already queued",
            # while a newer error means "last attempt failed; retry".
            request_mtime = request_log.stat().st_mtime if request_log.exists() else 0.0
            error_mtime = error_log.stat().st_mtime
            if request_mtime >= error_mtime:
                return True, "newer request log exists"
            saw_error = True
            continue

        if has_request:
            return True, "request log exists"

        if has_error:
            saw_error = True

    if saw_error:
        return False, None

    return False, None


def auth_label_from_meta(auth: dict | None) -> str | None:
    if not auth:
        return None
    profile = auth.get("profile")
    if profile:
        return str(profile)
    storage_path = auth.get("storage_path")
    if storage_path:
        return Path(str(storage_path)).stem
    return None


def ensure_unique_output_path(output_path: Path, label: str | None) -> Path:
    _ = label
    return output_path


def run_generate(
    python: Path,
    script: Path,
    *,
    sources_file: Path | None,
    source_path: Path | None,
    notebook_title: str,
    instructions: str,
    artifact_type: str,
    audio_format: str | None,
    audio_length: str | None,
    infographic_orientation: str | None,
    infographic_detail: str | None,
    language: str | None,
    quiz_quantity: str | None,
    quiz_difficulty: str | None,
    quiz_format: str | None,
    report_format: str | None = None,
    output_path: Path,
    wait: bool,
    skip_existing: bool,
    source_timeout: float | None,
    generation_timeout: float | None,
    artifact_retries: int | None,
    artifact_retry_backoff: float | None,
    generator_timeout: float | None,
    storage: str | None,
    profile: str | None,
    preferred_profile: str | None,
    profile_priority: str | None,
    profiles_file: str | None,
    exclude_profiles: list[str] | None,
    rotate_on_rate_limit: bool,
    ensure_sources_ready: bool,
    append_profile_to_notebook_title: bool,
    reuse_notebook: bool,
    source_paths: list[Path] | None = None,
) -> None:
    cmd = [
        str(python),
        str(script),
        "--notebook-title",
        notebook_title,
        "--instructions",
        instructions,
        "--artifact-type",
        artifact_type,
        "--output",
        str(output_path),
    ]
    if reuse_notebook:
        cmd.append("--reuse-notebook")
    if artifact_type == "audio":
        if audio_format:
            cmd.extend(["--audio-format", audio_format])
        if audio_length:
            cmd.extend(["--audio-length", audio_length])
    elif artifact_type == "infographic":
        if infographic_orientation:
            cmd.extend(["--infographic-orientation", infographic_orientation])
        if infographic_detail:
            cmd.extend(["--infographic-detail", infographic_detail])
    elif artifact_type == "quiz":
        if quiz_quantity:
            cmd.extend(["--quiz-quantity", quiz_quantity])
        if quiz_difficulty:
            cmd.extend(["--quiz-difficulty", quiz_difficulty])
        if quiz_format:
            cmd.extend(["--quiz-format", quiz_format])
    elif artifact_type == "report":
        if report_format:
            cmd.extend(["--report-format", report_format])
    if language:
        cmd.extend(["--language", language])
    if sources_file:
        cmd.extend(["--sources-file", str(sources_file)])
    if source_path:
        cmd.extend(["--source", str(source_path)])
    if source_paths:
        for source in source_paths:
            cmd.extend(["--source", str(source)])
    if wait:
        cmd.append("--wait")
    if skip_existing:
        cmd.append("--skip-existing")
    if source_timeout is not None:
        cmd.extend(["--source-timeout", str(source_timeout)])
    if generation_timeout is not None:
        cmd.extend(["--generation-timeout", str(generation_timeout)])
    if artifact_retries is not None:
        cmd.extend(["--artifact-retries", str(artifact_retries)])
    if artifact_retry_backoff is not None:
        cmd.extend(["--artifact-retry-backoff", str(artifact_retry_backoff)])
    if storage:
        cmd.extend(["--storage", storage])
    if profile:
        cmd.extend(["--profile", profile])
    if preferred_profile:
        cmd.extend(["--preferred-profile", preferred_profile])
    if profile_priority:
        cmd.extend(["--profile-priority", profile_priority])
    if profiles_file:
        cmd.extend(["--profiles-file", profiles_file])
    if exclude_profiles:
        cmd.extend(["--exclude-profiles", ",".join(exclude_profiles)])
    if not rotate_on_rate_limit:
        cmd.append("--no-rotate-on-rate-limit")
    if not ensure_sources_ready:
        cmd.append("--no-ensure-sources-ready")
    if not append_profile_to_notebook_title:
        cmd.append("--no-append-profile-to-notebook-title")
    try:
        result = subprocess.run(cmd, check=False, timeout=generator_timeout)
    except subprocess.TimeoutExpired as exc:
        if request_log_has_artifact(output_path):
            print(
                "Generator subprocess timed out after "
                f"{generator_timeout:g}s, but request log exists with artifact_id; "
                f"continuing: {output_path}"
            )
            return
        raise RuntimeError(
            "Generator timed out before writing a usable request log "
            f"for {output_path}"
        ) from exc
    if result.returncode != 0:
        if request_log_has_artifact(output_path):
            print(
                "Generator exited non-zero, but request log exists with artifact_id; "
                f"continuing so download can recover it later: {output_path}"
            )
            return
        raise RuntimeError(f"Generator failed with exit code {result.returncode}")


def find_repo_root(start: Path) -> Path:
    for candidate in [start] + list(start.parents):
        if (candidate / "requirements.txt").exists() and (candidate / "shows").exists():
            return candidate
    return start


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate all episodes for a given week.")
    parser.add_argument(
        "--week",
        help="Single week label, e.g. W01L1/1L1 (or W01/1 to include all W01L* folders).",
    )
    parser.add_argument(
        "--weeks",
        help="Comma-separated week labels, e.g. W01,W02 or 1,2",
    )
    parser.add_argument(
        "--sources-root",
        default=DEFAULT_SOURCES_ROOT,
        help="Root folder containing week source folders.",
    )
    parser.add_argument(
        "--prompt-config",
        default="notebooklm-podcast-auto/personlighedspsykologi/prompt_config.json",
        help="Prompt configuration JSON.",
    )
    parser.add_argument(
        "--content-types",
        help="Comma-separated content types to generate (audio, infographic, quiz). Default: audio.",
    )
    parser.add_argument(
        "--only-slide",
        help=(
            "Comma-separated slide_key values to generate. "
            "Filters per-source generation to those slides and skips weekly/short outputs."
        ),
    )
    parser.add_argument(
        "--review-manifest",
        help=(
            "Optional episode A/B review manifest. When set, generation is filtered to "
            "the baseline sample entries in that manifest."
        ),
    )
    parser.add_argument(
        "--output-root",
        default=default_output_root(),
        help=(
            "Where to place generated artifacts. "
            f"Default: ${OUTPUT_ROOT_ENV_VAR} or {DEFAULT_OUTPUT_ROOT}."
        ),
    )
    parser.add_argument(
        "--output-profile-subdir",
        action="store_true",
        help="If set, nest output under a profile-based subdirectory.",
    )
    parser.add_argument("--wait", action="store_true", help="Wait for generation to finish.")
    parser.add_argument(
        "--skip-existing",
        dest="skip_existing",
        action="store_true",
        default=True,
        help="Skip generation when output file already exists (default).",
    )
    parser.add_argument(
        "--no-skip-existing",
        dest="skip_existing",
        action="store_false",
        help="Force re-generation even if output file already exists.",
    )
    parser.add_argument(
        "--print-skips",
        action="store_true",
        default=False,
        help="Print per-file skip messages when outputs already exist (default: off).",
    )
    parser.add_argument(
        "--source-timeout",
        type=float,
        help="Seconds to wait for each source (passed through).",
    )
    parser.add_argument(
        "--no-ensure-sources-ready",
        dest="ensure_sources_ready",
        action="store_false",
        help="Disable waiting for sources to appear and become ready before generation.",
    )
    parser.set_defaults(ensure_sources_ready=True)
    parser.add_argument(
        "--generation-timeout",
        type=float,
        help="Seconds to wait for generation (passed through).",
    )
    parser.add_argument(
        "--generator-timeout",
        type=float,
        default=420.0,
        help=(
            "Seconds to wait for each generate_podcast.py subprocess. "
            "If a request log with artifact_id exists after timeout, continue as queued "
            "(default: 420)."
        ),
    )
    parser.add_argument(
        "--storage",
        help="Path to storage_state.json (passed through).",
    )
    parser.add_argument(
        "--profile",
        help="Profile name from profiles.json (passed through).",
    )
    parser.add_argument(
        "--profile-priority",
        help="Comma-separated profile names to try first (passed through).",
    )
    parser.add_argument(
        "--profiles-file",
        help="Path to profiles.json (passed through).",
    )
    parser.add_argument(
        "--no-rotate-on-rate-limit",
        dest="rotate_on_rate_limit",
        action="store_false",
        help="Disable rotating profiles on rate-limit/auth errors.",
    )
    parser.set_defaults(rotate_on_rate_limit=True)
    parser.add_argument(
        "--no-append-profile-to-notebook-title",
        dest="append_profile_to_notebook_title",
        action="store_false",
        help="Disable appending the profile label to notebook titles when rotating.",
    )
    parser.set_defaults(append_profile_to_notebook_title=True)
    parser.add_argument(
        "--artifact-retries",
        type=int,
        default=1,
        help="Retry artifact generation (passed through, default: 1).",
    )
    parser.add_argument(
        "--artifact-retry-backoff",
        type=float,
        default=5.0,
        help="Base backoff for artifact retries (passed through).",
    )
    parser.add_argument(
        "--sleep-between",
        type=float,
        default=2.0,
        help="Seconds to sleep between generation requests (default: 2).",
    )
    parser.add_argument(
        "--profile-cooldown",
        type=float,
        default=300.0,
        help="Seconds to avoid reusing rate-limited profiles within this run (default: 300).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned outputs and exit without generating artifacts.",
    )
    parser.add_argument(
        "--print-resolved-prompts",
        action="store_true",
        help="Print the fully resolved audio prompts during dry-run and generation.",
    )
    parser.add_argument(
        "--print-downloads",
        dest="print_downloads",
        action="store_true",
        default=True,
        help="Print commands to wait and download artifacts for this run (default; non-blocking only).",
    )
    parser.add_argument(
        "--no-print-downloads",
        dest="print_downloads",
        action="store_false",
        help="Disable printing wait/download commands.",
    )
    parser.add_argument(
        "--config-tagging",
        dest="config_tagging",
        action="store_true",
        default=True,
        help="Append human-readable {...} tag with output options to generated filenames (default).",
    )
    parser.add_argument(
        "--no-config-tagging",
        dest="config_tagging",
        action="store_false",
        help="Disable config tag suffix on generated output filenames.",
    )
    parser.add_argument(
        "--config-tag-len",
        type=int,
        default=8,
        help="Hex length for prompt hash inside {...} tag (default: 8).",
    )
    args = parser.parse_args()

    if not args.week and not args.weeks:
        raise SystemExit("Provide --week or --weeks.")

    week_inputs: list[str] = []
    if args.week:
        week_inputs.append(args.week)
    if args.weeks:
        week_inputs.extend(part.strip() for part in args.weeks.split(",") if part.strip())
    if not week_inputs:
        raise SystemExit("No valid weeks provided.")

    repo_root = find_repo_root(Path(__file__).resolve())
    sources_root = repo_root / args.sources_root
    prompt_config = repo_root / args.prompt_config
    output_root = resolve_output_root(repo_root / args.output_root)
    rotation_enabled = args.rotate_on_rate_limit and not args.profile and not args.storage
    auto_profile, auto_profiles_path = auto_profile_from_profiles(repo_root, args)
    profile_for_run = None if rotation_enabled else (args.profile or auto_profile)
    profiles_file_for_run = args.profiles_file or (str(auto_profiles_path) if auto_profiles_path else None)
    if not profiles_file_for_run:
        profiles_file_for_run = str(os.environ.get(PROFILES_FILE_ENV_VAR) or "").strip() or None
    profile_slug = resolve_profile_slug(profile_for_run, args.storage)
    output_root = apply_profile_subdir(output_root, profile_slug, args.output_profile_subdir)
    if output_root.exists() and not output_root.is_dir():
        raise SystemExit(f"Output root exists but is not a directory: {output_root}")
    auth_label = profile_slug if not rotation_enabled else None
    generator_script = repo_root / "notebooklm-podcast-auto" / "generate_podcast.py"
    notebooklm_cli = repo_root / "notebooklm-podcast-auto" / ".venv" / "bin" / "notebooklm"

    config = read_json(prompt_config)
    if args.config_tag_len < 1:
        raise SystemExit("--config-tag-len must be >= 1.")
    course_title = str(config.get("course_title") or "Personlighedspsykologi").strip() or "Personlighedspsykologi"
    slides_catalog_raw = str(config.get("slides_catalog") or "").strip()
    slides_source_root_raw = str(config.get("slides_source_root") or "").strip()
    slides_catalog_path = (repo_root / slides_catalog_raw) if slides_catalog_raw else None
    slides_source_root = None
    if slides_source_root_raw:
        slide_root_candidate = Path(slides_source_root_raw).expanduser()
        if not slide_root_candidate.is_absolute():
            slide_root_candidate = repo_root / slide_root_candidate
        slides_source_root = slide_root_candidate.resolve()
    content_types = parse_content_types(args.content_types)
    brief_types = brief_content_types(content_types)
    only_slide_keys = parse_slide_key_filter(args.only_slide)
    language_variants = build_language_variants(config)
    weekly_cfg = config.get("weekly_overview", {})
    per_cfg = config.get("per_reading", {})
    per_slide_cfg = ensure_dict(config.get("per_slide", per_cfg))
    per_slide_overrides = validate_per_slide_audio_config(per_slide_cfg)
    audio_prompt_strategy = normalize_audio_prompt_strategy(config.get("audio_prompt_strategy"))
    exam_focus = normalize_exam_focus(config.get("exam_focus"))
    study_context = normalize_study_context(config.get("study_context"))
    audio_prompt_framework = normalize_audio_prompt_framework(config.get("audio_prompt_framework"))
    report_prompt_strategy = normalize_report_prompt_strategy(config.get("report_prompt_strategy"))
    meta_prompting = normalize_meta_prompting(config.get("meta_prompting"))
    course_context_cfg = normalize_course_context(config.get("course_context"))
    brief_cfg = ensure_dict(config.get("short", config.get("brief", {})))
    report_defaults = ensure_dict(config.get("report"))
    weekly_report_cfg = ensure_dict(config.get("weekly_report", report_defaults))
    per_report_cfg = ensure_dict(config.get("per_reading_report", report_defaults))
    per_slide_report_cfg = ensure_dict(config.get("per_slide_report", per_report_cfg))
    short_report_cfg = ensure_dict(config.get("short_report", report_defaults))
    infographic_defaults = ensure_dict(config.get("infographic"))
    weekly_infographic_cfg = ensure_dict(config.get("weekly_infographic", infographic_defaults))
    per_infographic_cfg = ensure_dict(config.get("per_reading_infographic", infographic_defaults))
    brief_infographic_cfg = ensure_dict(
        config.get("short_infographic", config.get("brief_infographic", infographic_defaults))
    )
    quiz_cfg = ensure_dict(config.get("quiz"))
    quiz_quantity = normalize_quiz_quantity(quiz_cfg.get("quantity"))
    quiz_difficulty = normalize_quiz_difficulty(quiz_cfg.get("difficulty"))
    quiz_format = normalize_quiz_format(quiz_cfg.get("format"))
    if "quiz" in content_types and quiz_difficulty == "all" and not args.config_tagging:
        raise SystemExit(
            "quiz.difficulty=all requires config-tagged filenames. "
            "Enable --config-tagging (default) or remove --no-config-tagging."
        )
    review_filter = (
        load_review_manifest_filter(Path(args.review_manifest).expanduser().resolve())
        if args.review_manifest
        else None
    )
    try:
        course_context_bundle = course_context_helpers.load_course_prompt_context_bundle(
            repo_root=repo_root,
            config=course_context_cfg,
            slides_catalog_path=slides_catalog_path,
        )
    except RuntimeError as exc:
        print(f"Warning: course-aware lecture context disabled for this run: {exc}")
        course_context_bundle = None

    request_logs: list[Path] = []
    failures: list[str] = []
    profile_cooldowns: dict[str, float] = {}
    last_excluded: list[str] = []
    preferred_profile: str | None = None
    profile_priority = args.profile_priority or str(os.environ.get(PROFILE_PRIORITY_ENV_VAR) or "").strip() or None
    total_sources_read = 0
    total_missing_outputs = 0
    matched_only_slide_keys: set[str] = set()
    quarantine_timestamp = time.strftime("%Y%m%d-%H%M%S")

    processed_dirs: set[Path] = set()
    for week_input in week_inputs:
        week_dirs = find_week_dirs(sources_root, week_input)
        if not week_dirs:
            raise SystemExit(f"No week folder found for {week_input} under {sources_root}")
        week_dirs = ensure_unique_canonical_week_dirs(week_dirs, week_input=week_input)
        if len(week_dirs) > 1 and not re.fullmatch(r"(?:W)?0*\d{1,2}", week_input.upper()):
            names = ", ".join(path.name for path in week_dirs)
            raise SystemExit(f"Multiple week folders match {week_input}: {names}")
        for week_dir in week_dirs:
            if week_dir in processed_dirs:
                continue
            processed_dirs.add(week_dir)
            week_label = canonical_week_label_from_dir(week_dir)

            week_output_dir = output_root / week_label
            week_output_dir.mkdir(parents=True, exist_ok=True)
            if not args.dry_run:
                removed_disallowed_slide_outputs = cleanup_disallowed_slide_outputs(week_output_dir)
                if removed_disallowed_slide_outputs:
                    print(
                        f"{week_label}: deleted {len(removed_disallowed_slide_outputs)} stale "
                        "seminar-slide outputs"
                    )
                removed_disallowed_slide_briefs = cleanup_disallowed_slide_brief_outputs(
                    week_output_dir,
                    brief_cfg=brief_cfg,
                )
                if removed_disallowed_slide_briefs:
                    print(
                        f"{week_label}: deleted {len(removed_disallowed_slide_briefs)} stale "
                        "slide short outputs"
                    )
                removed_disallowed_brief_quiz_outputs = cleanup_disallowed_brief_quiz_outputs(
                    week_output_dir
                )
                if removed_disallowed_brief_quiz_outputs:
                    print(
                        f"{week_label}: deleted {len(removed_disallowed_brief_quiz_outputs)} stale "
                        "short quiz outputs"
                    )
                migrated_outputs = migrate_legacy_weekly_overview_outputs(week_output_dir)
                if migrated_outputs:
                    print(
                        f"{week_label}: renamed {len(migrated_outputs)} legacy "
                        "Alle kilder outputs to the canonical '(undtagen slides)' title"
                    )
                migrated_prefixed_outputs = migrate_legacy_prefixed_reading_outputs(week_output_dir)
                if migrated_prefixed_outputs:
                    print(
                        f"{week_label}: renamed {len(migrated_prefixed_outputs)} legacy "
                        "reading outputs that still used a leading 'X ' prefix"
                    )

            reading_sources, generation_sources = build_source_items(
                week_dir=week_dir,
                week_label=week_label,
                slides_catalog_path=slides_catalog_path,
                slides_source_root=slides_source_root,
                meta_prompting=meta_prompting,
            )
            if only_slide_keys:
                generation_sources = [
                    item
                    for item in generation_sources
                    if item.source_type == "slide"
                    and normalize_slide_key(item.slide_key) in only_slide_keys
                ]
                matched_only_slide_keys.update(
                    normalize_slide_key(item.slide_key)
                    for item in generation_sources
                    if item.slide_key
                )
            if review_filter is not None:
                generation_sources = [
                    item
                    for item in generation_sources
                    if review_filter_includes_source(review_filter, item)
                ]
            if not generation_sources:
                if only_slide_keys:
                    continue
                if not review_filter_includes_weekly(review_filter, week_label):
                    continue
                if not reading_sources:
                    raise SystemExit(f"No source files found in {week_dir}")
            reading_source_count = len(reading_sources)
            generation_source_count = len(generation_sources)
            generation_reading_count = sum(
                1 for item in generation_sources if item.source_type == "reading"
            )
            generation_slide_count = sum(
                1 for item in generation_sources if item.source_type == "slide"
            )
            total_sources_read += generation_source_count
            generate_weekly_overview = (
                False
                if only_slide_keys
                else (
                    should_generate_weekly_overview(reading_source_count)
                    and review_filter_includes_weekly(review_filter, week_label)
                )
            )
            if not generate_weekly_overview:
                if only_slide_keys:
                    print(f"{week_label}: skipping Alle kilder generation (--only-slide)")
                elif review_filter is not None:
                    print(f"{week_label}: skipping Alle kilder generation (--review-manifest)")
                else:
                    print(
                        f"{week_label}: skipping Alle kilder generation "
                        f"(only {reading_source_count} reading source file)"
                    )

            auto_meta_note_overrides, auto_meta_lines = prepare_auto_meta_prompt_overrides(
                course_title=course_title,
                week_dir=week_dir,
                week_label=week_label,
                reading_sources=reading_sources,
                generation_sources=generation_sources if "audio" in content_types else [],
                generate_weekly_overview=generate_weekly_overview and "audio" in content_types,
                meta_prompting=meta_prompting,
                dry_run=args.dry_run,
            )
            if not args.dry_run:
                for line in auto_meta_lines:
                    print(line)

            planned_lines: list[str] = []
            planned_lines.extend(auto_meta_lines)
            missing_outputs = 0
            weekly_base = f"{week_label} - {WEEKLY_OVERVIEW_TITLE}"
            if generate_weekly_overview:
                for content_type in content_types:
                    weekly_output = week_output_dir / f"{weekly_base}{output_extension(content_type, quiz_format=quiz_format)}"
                    for variant in language_variants:
                        for quiz_difficulty_value in quiz_difficulty_values(content_type, quiz_difficulty):
                            if content_type == "audio":
                                weekly_course_context_note = build_course_context_note(
                                    course_context_bundle=course_context_bundle,
                                    course_context_cfg=course_context_cfg,
                                    lecture_key=week_label,
                                    prompt_type="weekly_readings_only",
                                )
                                planned_instructions = build_audio_prompt(
                                    prompt_type="weekly_readings_only",
                                    prompt_strategy=audio_prompt_strategy,
                                    exam_focus=exam_focus,
                                    study_context=study_context,
                                    prompt_framework=audio_prompt_framework,
                                    meta_prompting=meta_prompting,
                                    course_title=course_title,
                                    course_context_note=weekly_course_context_note,
                                    course_context_heading=course_context_cfg.get("heading"),
                                    meta_note_overrides=auto_meta_note_overrides,
                                    custom_prompt=weekly_cfg.get("prompt", ""),
                                    audio_format=weekly_cfg.get("format", "deep-dive"),
                                    audio_length=weekly_cfg.get("length", "long"),
                                    source_items=reading_sources,
                                    week_dir=week_dir,
                                    week_label=week_label,
                                )
                                planned_tag = build_output_cfg_tag_token(
                                    content_type=content_type,
                                    language=variant["code"],
                                    instructions=planned_instructions,
                                    audio_format=weekly_cfg.get("format", "deep-dive"),
                                    audio_length=weekly_cfg.get("length", "long"),
                                    infographic_orientation=None,
                                    infographic_detail=None,
                                    quiz_quantity=None,
                                    quiz_difficulty=None,
                                    quiz_format=None,
                                    report_format=None,
                                    source_count=reading_source_count,
                                    hash_len=args.config_tag_len,
                                )
                            elif content_type == "infographic":
                                planned_instructions = ensure_prompt(
                                    "weekly_infographic", weekly_infographic_cfg.get("prompt", "")
                                )
                                planned_tag = build_output_cfg_tag_token(
                                    content_type=content_type,
                                    language=variant["code"],
                                    instructions=planned_instructions,
                                    audio_format=None,
                                    audio_length=None,
                                    infographic_orientation=weekly_infographic_cfg.get("orientation"),
                                    infographic_detail=weekly_infographic_cfg.get("detail"),
                                    quiz_quantity=None,
                                    quiz_difficulty=None,
                                    quiz_format=None,
                                    report_format=None,
                                    source_count=None,
                                    hash_len=args.config_tag_len,
                                )
                            elif content_type == "report":
                                weekly_course_context_note = build_course_context_note(
                                    course_context_bundle=course_context_bundle,
                                    course_context_cfg=course_context_cfg,
                                    lecture_key=week_label,
                                    prompt_type="weekly_readings_only",
                                )
                                planned_instructions = build_report_prompt(
                                    prompt_type="weekly_readings_only",
                                    prompt_strategy=report_prompt_strategy,
                                    course_context_note=weekly_course_context_note,
                                    course_context_heading=course_context_cfg.get("heading"),
                                    study_context=study_context,
                                    meta_prompting=meta_prompting,
                                    meta_note_overrides=auto_meta_note_overrides,
                                    custom_prompt=weekly_report_cfg.get("prompt", ""),
                                    source_items=reading_sources,
                                    week_dir=week_dir,
                                    week_label=week_label,
                                )
                                planned_tag = build_output_cfg_tag_token(
                                    content_type=content_type,
                                    language=variant["code"],
                                    instructions=planned_instructions,
                                    audio_format=None,
                                    audio_length=None,
                                    infographic_orientation=None,
                                    infographic_detail=None,
                                    quiz_quantity=None,
                                    quiz_difficulty=None,
                                    quiz_format=None,
                                    report_format=normalize_report_format(weekly_report_cfg.get("format")),
                                    source_count=None,
                                    hash_len=args.config_tag_len,
                                )
                            else:
                                planned_instructions = ensure_prompt("quiz", quiz_cfg.get("prompt", ""))
                                planned_tag = build_output_cfg_tag_token(
                                    content_type=content_type,
                                    language=variant["code"],
                                    instructions=planned_instructions,
                                    audio_format=None,
                                    audio_length=None,
                                    infographic_orientation=None,
                                    infographic_detail=None,
                                    quiz_quantity=quiz_quantity,
                                    quiz_difficulty=quiz_difficulty_value,
                                    quiz_format=quiz_format,
                                    report_format=None,
                                    source_count=None,
                                    hash_len=args.config_tag_len,
                                )
                            weekly_candidate = apply_config_tag(
                                apply_path_suffix(weekly_output, variant["suffix"]),
                                planned_tag if args.config_tagging else None,
                            )
                            planned_path = ensure_unique_output_path(
                                weekly_candidate,
                                auth_label,
                            )
                            if not review_filter_includes_output(
                                review_filter,
                                "weekly_readings_only",
                                planned_path,
                            ):
                                continue
                            planned_lines.append(
                                f"WEEKLY {content_type.upper()} ({variant['code'] or 'default'}): {planned_path}"
                            )
                            if args.print_resolved_prompts and content_type == "audio":
                                planned_lines.extend(
                                    build_prompt_debug_lines(planned_path.name, planned_instructions)
                                )
                            should_skip, _ = should_skip_generation(planned_path, args.skip_existing)
                            if not should_skip:
                                missing_outputs += 1

            for source_item in generation_sources:
                source = source_item.path
                base_name = source_item.base_name
                per_base = f"{week_label} - {base_name}"
                for content_type in content_types:
                    per_output = week_output_dir / f"{per_base}{output_extension(content_type, quiz_format=quiz_format)}"
                    for variant in language_variants:
                        for quiz_difficulty_value in quiz_difficulty_values(content_type, quiz_difficulty):
                            if content_type == "audio":
                                _, planned_instructions, per_audio_format, per_audio_length = per_source_audio_settings(
                                    source_item,
                                    course_title=course_title,
                                    per_reading_cfg=per_cfg,
                                    per_slide_cfg=per_slide_cfg,
                                    per_slide_overrides=per_slide_overrides,
                                    prompt_strategy=audio_prompt_strategy,
                                    exam_focus=exam_focus,
                                    study_context=study_context,
                                    prompt_framework=audio_prompt_framework,
                                    meta_prompting=meta_prompting,
                                    meta_note_overrides=auto_meta_note_overrides,
                                    course_context_bundle=course_context_bundle,
                                    course_context_cfg=course_context_cfg,
                                    lecture_key=week_label,
                                )
                                planned_tag = build_output_cfg_tag_token(
                                    content_type=content_type,
                                    language=variant["code"],
                                    instructions=planned_instructions,
                                    audio_format=per_audio_format,
                                    audio_length=per_audio_length,
                                    infographic_orientation=None,
                                    infographic_detail=None,
                                    quiz_quantity=None,
                                    quiz_difficulty=None,
                                    quiz_format=None,
                                    report_format=None,
                                    source_count=None,
                                    hash_len=args.config_tag_len,
                                )
                            elif content_type == "infographic":
                                planned_instructions = ensure_prompt(
                                    "per_reading_infographic", per_infographic_cfg.get("prompt", "")
                                )
                                planned_tag = build_output_cfg_tag_token(
                                    content_type=content_type,
                                    language=variant["code"],
                                    instructions=planned_instructions,
                                    audio_format=None,
                                    audio_length=None,
                                    infographic_orientation=per_infographic_cfg.get("orientation"),
                                    infographic_detail=per_infographic_cfg.get("detail"),
                                    quiz_quantity=None,
                                    quiz_difficulty=None,
                                    quiz_format=None,
                                    report_format=None,
                                    source_count=None,
                                    hash_len=args.config_tag_len,
                                )
                            elif content_type == "report":
                                _, planned_instructions, planned_report_format = (
                                    per_source_report_settings(
                                        source_item,
                                        per_reading_cfg=per_report_cfg,
                                        per_slide_cfg=per_slide_report_cfg,
                                        prompt_strategy=report_prompt_strategy,
                                        study_context=study_context,
                                        meta_prompting=meta_prompting,
                                        meta_note_overrides=auto_meta_note_overrides,
                                        course_context_bundle=course_context_bundle,
                                        course_context_cfg=course_context_cfg,
                                        lecture_key=week_label,
                                    )
                                )
                                planned_tag = build_output_cfg_tag_token(
                                    content_type=content_type,
                                    language=variant["code"],
                                    instructions=planned_instructions,
                                    audio_format=None,
                                    audio_length=None,
                                    infographic_orientation=None,
                                    infographic_detail=None,
                                    quiz_quantity=None,
                                    quiz_difficulty=None,
                                    quiz_format=None,
                                    report_format=planned_report_format,
                                    source_count=None,
                                    hash_len=args.config_tag_len,
                                )
                            else:
                                planned_instructions = ensure_prompt("quiz", quiz_cfg.get("prompt", ""))
                                planned_tag = build_output_cfg_tag_token(
                                    content_type=content_type,
                                    language=variant["code"],
                                    instructions=planned_instructions,
                                    audio_format=None,
                                    audio_length=None,
                                    infographic_orientation=None,
                                    infographic_detail=None,
                                    quiz_quantity=quiz_quantity,
                                    quiz_difficulty=quiz_difficulty_value,
                                    quiz_format=quiz_format,
                                    report_format=None,
                                    source_count=None,
                                    hash_len=args.config_tag_len,
                                )
                            per_candidate = apply_config_tag(
                                apply_path_suffix(per_output, variant["suffix"]),
                                planned_tag if args.config_tagging else None,
                            )
                            planned_path = ensure_unique_output_path(
                                per_candidate,
                                auth_label,
                            )
                            per_prompt_type = (
                                "single_slide"
                                if source_item.source_type == "slide"
                                else "single_reading"
                            )
                            if not review_filter_includes_output(
                                review_filter,
                                per_prompt_type,
                                planned_path,
                            ):
                                continue
                            planned_source_kind = (
                                "SLIDE" if source_item.source_type == "slide" else "READING"
                            )
                            planned_lines.append(
                                f"{planned_source_kind} {content_type.upper()} ({variant['code'] or 'default'}): {planned_path}"
                            )
                            if args.print_resolved_prompts and content_type == "audio":
                                planned_lines.extend(
                                    build_prompt_debug_lines(planned_path.name, planned_instructions)
                                )
                            should_skip, _ = should_skip_generation(planned_path, args.skip_existing)
                            if not should_skip:
                                missing_outputs += 1
                if (
                    not only_slide_keys
                    and review_filter_includes_short_source(review_filter, source_item)
                    and should_generate_brief_for_source(source_item, brief_cfg=brief_cfg)
                ):
                    title_prefix = brief_cfg.get("title_prefix", "[Short]")
                    brief_base = f"{title_prefix} {week_label} - {base_name}"
                    for content_type in brief_types:
                        brief_output = week_output_dir / f"{brief_base}{output_extension(content_type, quiz_format=quiz_format)}"
                        for variant in language_variants:
                            for quiz_difficulty_value in quiz_difficulty_values(content_type, quiz_difficulty):
                                if content_type == "audio":
                                    brief_course_context_note = build_course_context_note(
                                        course_context_bundle=course_context_bundle,
                                        course_context_cfg=course_context_cfg,
                                        lecture_key=week_label,
                                        prompt_type="short",
                                        source_item=source_item,
                                    )
                                    planned_instructions = build_audio_prompt(
                                        prompt_type="short",
                                        prompt_strategy=audio_prompt_strategy,
                                        exam_focus=exam_focus,
                                        study_context=study_context,
                                        prompt_framework=audio_prompt_framework,
                                        meta_prompting=meta_prompting,
                                        course_title=course_title,
                                        course_context_note=brief_course_context_note,
                                        course_context_heading=course_context_cfg.get("heading"),
                                        meta_note_overrides=auto_meta_note_overrides,
                                        custom_prompt=brief_cfg.get("prompt", ""),
                                        audio_format=brief_cfg.get("format", "deep-dive"),
                                        audio_length=brief_cfg.get("length", "long"),
                                        source_item=source_item,
                                    )
                                    planned_tag = build_output_cfg_tag_token(
                                        content_type=content_type,
                                        language=variant["code"],
                                        instructions=planned_instructions,
                                        audio_format=brief_cfg.get("format", "deep-dive"),
                                        audio_length=brief_cfg.get("length", "long"),
                                        infographic_orientation=None,
                                        infographic_detail=None,
                                        quiz_quantity=None,
                                        quiz_difficulty=None,
                                        quiz_format=None,
                                        report_format=None,
                                        source_count=None,
                                        hash_len=args.config_tag_len,
                                    )
                                elif content_type == "infographic":
                                    planned_instructions = ensure_prompt(
                                        "short_infographic", brief_infographic_cfg.get("prompt", "")
                                    )
                                    planned_tag = build_output_cfg_tag_token(
                                        content_type=content_type,
                                        language=variant["code"],
                                        instructions=planned_instructions,
                                        audio_format=None,
                                        audio_length=None,
                                        infographic_orientation=brief_infographic_cfg.get("orientation"),
                                        infographic_detail=brief_infographic_cfg.get("detail"),
                                        quiz_quantity=None,
                                        quiz_difficulty=None,
                                        quiz_format=None,
                                        report_format=None,
                                        source_count=None,
                                        hash_len=args.config_tag_len,
                                    )
                                elif content_type == "report":
                                    brief_course_context_note = build_course_context_note(
                                        course_context_bundle=course_context_bundle,
                                        course_context_cfg=course_context_cfg,
                                        lecture_key=week_label,
                                        prompt_type="short",
                                        source_item=source_item,
                                    )
                                    planned_instructions = build_report_prompt(
                                        prompt_type="short",
                                        prompt_strategy=report_prompt_strategy,
                                        course_context_note=brief_course_context_note,
                                        course_context_heading=course_context_cfg.get("heading"),
                                        study_context=study_context,
                                        meta_prompting=meta_prompting,
                                        meta_note_overrides=auto_meta_note_overrides,
                                        custom_prompt=short_report_cfg.get("prompt", ""),
                                        source_item=source_item,
                                    )
                                    planned_tag = build_output_cfg_tag_token(
                                        content_type=content_type,
                                        language=variant["code"],
                                        instructions=planned_instructions,
                                        audio_format=None,
                                        audio_length=None,
                                        infographic_orientation=None,
                                        infographic_detail=None,
                                        quiz_quantity=None,
                                        quiz_difficulty=None,
                                        quiz_format=None,
                                        report_format=normalize_report_format(
                                            short_report_cfg.get("format")
                                        ),
                                        source_count=None,
                                        hash_len=args.config_tag_len,
                                    )
                                else:
                                    planned_instructions = ensure_prompt("quiz", quiz_cfg.get("prompt", ""))
                                    planned_tag = build_output_cfg_tag_token(
                                        content_type=content_type,
                                        language=variant["code"],
                                        instructions=planned_instructions,
                                        audio_format=None,
                                        audio_length=None,
                                        infographic_orientation=None,
                                        infographic_detail=None,
                                        quiz_quantity=quiz_quantity,
                                        quiz_difficulty=quiz_difficulty_value,
                                        quiz_format=quiz_format,
                                        report_format=None,
                                        source_count=None,
                                        hash_len=args.config_tag_len,
                                    )
                                brief_candidate = apply_config_tag(
                                    apply_path_suffix(brief_output, variant["suffix"]),
                                    planned_tag if args.config_tagging else None,
                                )
                                planned_path = ensure_unique_output_path(
                                    brief_candidate,
                                    auth_label,
                                )
                                if not review_filter_includes_output(
                                    review_filter,
                                    "short",
                                    planned_path,
                                ):
                                    continue
                                planned_lines.append(
                                    f"SHORT {content_type.upper()} ({variant['code'] or 'default'}): {planned_path}"
                                )
                                if args.print_resolved_prompts and content_type == "audio":
                                    planned_lines.extend(
                                        build_prompt_debug_lines(planned_path.name, planned_instructions)
                                    )
                                should_skip, _ = should_skip_generation(planned_path, args.skip_existing)
                                if not should_skip:
                                    missing_outputs += 1

            total_missing_outputs += missing_outputs
            print(
                f"{week_label}: read {generation_source_count} sources "
                f"({generation_reading_count} readings, {generation_slide_count} slides), "
                f"found {missing_outputs} missing outputs"
            )

            if args.dry_run:
                print(f"## {week_label}")
                for line in planned_lines:
                    print(line)
                continue

            if generate_weekly_overview:
                for content_type in content_types:
                    weekly_output = week_output_dir / f"{weekly_base}{output_extension(content_type, quiz_format=quiz_format)}"
                    for variant in language_variants:
                        for quiz_difficulty_value in quiz_difficulty_values(content_type, quiz_difficulty):
                            if content_type == "audio":
                                weekly_course_context_note = build_course_context_note(
                                    course_context_bundle=course_context_bundle,
                                    course_context_cfg=course_context_cfg,
                                    lecture_key=week_label,
                                    prompt_type="weekly_readings_only",
                                )
                                instructions = build_audio_prompt(
                                    prompt_type="weekly_readings_only",
                                    prompt_strategy=audio_prompt_strategy,
                                    exam_focus=exam_focus,
                                    study_context=study_context,
                                    prompt_framework=audio_prompt_framework,
                                    meta_prompting=meta_prompting,
                                    course_title=course_title,
                                    course_context_note=weekly_course_context_note,
                                    course_context_heading=course_context_cfg.get("heading"),
                                    meta_note_overrides=auto_meta_note_overrides,
                                    custom_prompt=weekly_cfg.get("prompt", ""),
                                    audio_format=weekly_cfg.get("format", "deep-dive"),
                                    audio_length=weekly_cfg.get("length", "long"),
                                    source_items=reading_sources,
                                    week_dir=week_dir,
                                    week_label=week_label,
                                )
                                audio_format = weekly_cfg.get("format", "deep-dive")
                                audio_length = weekly_cfg.get("length", "long")
                                infographic_orientation = None
                                infographic_detail = None
                                quiz_quantity_arg = None
                                quiz_difficulty_arg = None
                                quiz_format_arg = None
                                report_format_arg = None
                            elif content_type == "infographic":
                                instructions = ensure_prompt(
                                    "weekly_infographic", weekly_infographic_cfg.get("prompt", "")
                                )
                                audio_format = None
                                audio_length = None
                                infographic_orientation = weekly_infographic_cfg.get("orientation")
                                infographic_detail = weekly_infographic_cfg.get("detail")
                                quiz_quantity_arg = None
                                quiz_difficulty_arg = None
                                quiz_format_arg = None
                                report_format_arg = None
                            elif content_type == "report":
                                weekly_course_context_note = build_course_context_note(
                                    course_context_bundle=course_context_bundle,
                                    course_context_cfg=course_context_cfg,
                                    lecture_key=week_label,
                                    prompt_type="weekly_readings_only",
                                )
                                instructions = build_report_prompt(
                                    prompt_type="weekly_readings_only",
                                    prompt_strategy=report_prompt_strategy,
                                    course_context_note=weekly_course_context_note,
                                    course_context_heading=course_context_cfg.get("heading"),
                                    study_context=study_context,
                                    meta_prompting=meta_prompting,
                                    meta_note_overrides=auto_meta_note_overrides,
                                    custom_prompt=weekly_report_cfg.get("prompt", ""),
                                    source_items=reading_sources,
                                    week_dir=week_dir,
                                    week_label=week_label,
                                )
                                audio_format = None
                                audio_length = None
                                infographic_orientation = None
                                infographic_detail = None
                                quiz_quantity_arg = None
                                quiz_difficulty_arg = None
                                quiz_format_arg = None
                                report_format_arg = normalize_report_format(
                                    weekly_report_cfg.get("format")
                                )
                            else:
                                instructions = ensure_prompt("quiz", quiz_cfg.get("prompt", ""))
                                audio_format = None
                                audio_length = None
                                infographic_orientation = None
                                infographic_detail = None
                                quiz_quantity_arg = quiz_quantity
                                quiz_difficulty_arg = quiz_difficulty_value
                                quiz_format_arg = quiz_format
                                report_format_arg = None
                            weekly_tag = (
                                build_output_cfg_tag_token(
                                    content_type=content_type,
                                    language=variant["code"],
                                    instructions=instructions,
                                    audio_format=audio_format,
                                    audio_length=audio_length,
                                    infographic_orientation=infographic_orientation,
                                    infographic_detail=infographic_detail,
                                    quiz_quantity=quiz_quantity_arg,
                                    quiz_difficulty=quiz_difficulty_arg,
                                    quiz_format=quiz_format_arg,
                                    report_format=report_format_arg,
                                    source_count=reading_source_count,
                                    hash_len=args.config_tag_len,
                                )
                                if args.config_tagging
                                else None
                            )
                            weekly_candidate = apply_config_tag(
                                apply_path_suffix(weekly_output, variant["suffix"]),
                                weekly_tag,
                            )
                            output_path = ensure_unique_output_path(
                                weekly_candidate,
                                auth_label,
                            )
                            if not review_filter_includes_output(
                                review_filter,
                                "weekly_readings_only",
                                output_path,
                            ):
                                continue
                            skip, reason = should_skip_generation(output_path, args.skip_existing)
                            if skip:
                                if args.print_skips:
                                    print(f"Skipping generation ({reason}): {output_path}")
                                continue
                            if args.print_resolved_prompts and content_type == "audio":
                                for line in build_prompt_debug_lines(output_path.name, instructions):
                                    print(line)
                            exclude_profiles = (
                                active_cooldowns(profile_cooldowns)
                                if rotation_enabled and args.profile_cooldown > 0
                                else []
                            )
                            if exclude_profiles and exclude_profiles != last_excluded:
                                print(f"Cooling profiles this run: {', '.join(exclude_profiles)}")
                                last_excluded = exclude_profiles
                            try:
                                run_generate(
                                    Path(sys.executable),
                                    generator_script,
                                    sources_file=None,
                                    source_path=None,
                                    source_paths=[item.path for item in reading_sources],
                                    notebook_title=apply_suffix(
                                        f"{course_title} {week_label} {WEEKLY_OVERVIEW_TITLE}",
                                        variant["title_suffix"],
                                    ),
                                    instructions=instructions,
                                    artifact_type=content_type,
                                    audio_format=audio_format,
                                    audio_length=audio_length,
                                    infographic_orientation=infographic_orientation,
                                    infographic_detail=infographic_detail,
                                    quiz_quantity=quiz_quantity_arg,
                                    quiz_difficulty=quiz_difficulty_arg,
                                    quiz_format=quiz_format_arg,
                                    report_format=report_format_arg,
                                    language=variant["code"],
                                    output_path=output_path,
                                    wait=args.wait,
                                    skip_existing=args.skip_existing,
                                    source_timeout=args.source_timeout,
                                    generation_timeout=args.generation_timeout,
                                    generator_timeout=args.generator_timeout,
                                    artifact_retries=args.artifact_retries,
                                    artifact_retry_backoff=args.artifact_retry_backoff,
                                    storage=args.storage,
                                    profile=profile_for_run,
                                    preferred_profile=preferred_profile,
                                    profile_priority=profile_priority,
                                    profiles_file=profiles_file_for_run,
                                    exclude_profiles=exclude_profiles or None,
                                    rotate_on_rate_limit=args.rotate_on_rate_limit,
                                    ensure_sources_ready=args.ensure_sources_ready,
                                    append_profile_to_notebook_title=args.append_profile_to_notebook_title,
                                    reuse_notebook=False,
                                )
                            except Exception as exc:
                                failures.append(f"{output_path}: {exc}")
                                continue
                            else:
                                if rotation_enabled:
                                    preferred_profile = update_preferred_profile(
                                        output_path, preferred_profile
                                    )
                            finally:
                                if rotation_enabled and args.profile_cooldown > 0:
                                    update_profile_cooldowns(
                                        output_path,
                                        profile_cooldowns,
                                        args.profile_cooldown,
                                        AUTH_COOLDOWN_SECONDS,
                                    )
                                maybe_sleep(args.sleep_between)
                            request_logs.append(
                                output_path.with_suffix(output_path.suffix + ".request.json")
                            )

            for source_item in generation_sources:
                source = source_item.path
                base_name = source_item.base_name
                per_base = f"{week_label} - {base_name}"
                for content_type in content_types:
                    per_output = week_output_dir / f"{per_base}{output_extension(content_type, quiz_format=quiz_format)}"
                    for variant in language_variants:
                        for quiz_difficulty_value in quiz_difficulty_values(content_type, quiz_difficulty):
                            if content_type == "audio":
                                _, instructions, audio_format, audio_length = per_source_audio_settings(
                                    source_item,
                                    course_title=course_title,
                                    per_reading_cfg=per_cfg,
                                    per_slide_cfg=per_slide_cfg,
                                    per_slide_overrides=per_slide_overrides,
                                    prompt_strategy=audio_prompt_strategy,
                                    exam_focus=exam_focus,
                                    study_context=study_context,
                                    prompt_framework=audio_prompt_framework,
                                    meta_prompting=meta_prompting,
                                    meta_note_overrides=auto_meta_note_overrides,
                                    course_context_bundle=course_context_bundle,
                                    course_context_cfg=course_context_cfg,
                                    lecture_key=week_label,
                                )
                                infographic_orientation = None
                                infographic_detail = None
                                quiz_quantity_arg = None
                                quiz_difficulty_arg = None
                                quiz_format_arg = None
                                report_format_arg = None
                            elif content_type == "infographic":
                                instructions = ensure_prompt(
                                    "per_reading_infographic", per_infographic_cfg.get("prompt", "")
                                )
                                audio_format = None
                                audio_length = None
                                infographic_orientation = per_infographic_cfg.get("orientation")
                                infographic_detail = per_infographic_cfg.get("detail")
                                quiz_quantity_arg = None
                                quiz_difficulty_arg = None
                                quiz_format_arg = None
                                report_format_arg = None
                            elif content_type == "report":
                                _, instructions, report_format_arg = per_source_report_settings(
                                    source_item,
                                    per_reading_cfg=per_report_cfg,
                                    per_slide_cfg=per_slide_report_cfg,
                                    prompt_strategy=report_prompt_strategy,
                                    study_context=study_context,
                                    meta_prompting=meta_prompting,
                                    meta_note_overrides=auto_meta_note_overrides,
                                    course_context_bundle=course_context_bundle,
                                    course_context_cfg=course_context_cfg,
                                    lecture_key=week_label,
                                )
                                audio_format = None
                                audio_length = None
                                infographic_orientation = None
                                infographic_detail = None
                                quiz_quantity_arg = None
                                quiz_difficulty_arg = None
                                quiz_format_arg = None
                            else:
                                instructions = ensure_prompt("quiz", quiz_cfg.get("prompt", ""))
                                audio_format = None
                                audio_length = None
                                infographic_orientation = None
                                infographic_detail = None
                                quiz_quantity_arg = quiz_quantity
                                quiz_difficulty_arg = quiz_difficulty_value
                                quiz_format_arg = quiz_format
                                report_format_arg = None
                            per_tag = (
                                build_output_cfg_tag_token(
                                    content_type=content_type,
                                    language=variant["code"],
                                    instructions=instructions,
                                    audio_format=audio_format,
                                    audio_length=audio_length,
                                    infographic_orientation=infographic_orientation,
                                    infographic_detail=infographic_detail,
                                    quiz_quantity=quiz_quantity_arg,
                                    quiz_difficulty=quiz_difficulty_arg,
                                    quiz_format=quiz_format_arg,
                                    report_format=report_format_arg,
                                    source_count=None,
                                    hash_len=args.config_tag_len,
                                )
                                if args.config_tagging
                                else None
                            )
                            per_candidate = apply_config_tag(
                                apply_path_suffix(per_output, variant["suffix"]),
                                per_tag,
                            )
                            output_path = ensure_unique_output_path(
                                per_candidate,
                                auth_label,
                            )
                            per_prompt_type = (
                                "single_slide"
                                if source_item.source_type == "slide"
                                else "single_reading"
                            )
                            if not review_filter_includes_output(
                                review_filter,
                                per_prompt_type,
                                output_path,
                            ):
                                continue
                            if (
                                only_slide_keys
                                and content_type == "audio"
                                and source_item.source_type == "slide"
                            ):
                                quarantined = quarantine_stale_slide_audio_outputs(
                                    repo_root=repo_root,
                                    week_output_dir=week_output_dir,
                                    canonical_output_path=output_path,
                                    timestamp=quarantine_timestamp,
                                )
                                if quarantined:
                                    print(
                                        f"{week_label}: quarantined {len(quarantined)} stale "
                                        f"slide audio file(s)/sidecar(s) for {base_name}"
                                    )
                            skip, reason = should_skip_generation(output_path, args.skip_existing)
                            if skip:
                                if args.print_skips:
                                    print(f"Skipping generation ({reason}): {output_path}")
                                continue
                            if args.print_resolved_prompts and content_type == "audio":
                                for line in build_prompt_debug_lines(output_path.name, instructions):
                                    print(line)
                            exclude_profiles = (
                                active_cooldowns(profile_cooldowns)
                                if rotation_enabled and args.profile_cooldown > 0
                                else []
                            )
                            if exclude_profiles and exclude_profiles != last_excluded:
                                print(f"Cooling profiles this run: {', '.join(exclude_profiles)}")
                                last_excluded = exclude_profiles
                            try:
                                run_generate(
                                    Path(sys.executable),
                                    generator_script,
                                    sources_file=None,
                                    source_path=source,
                                    notebook_title=apply_suffix(
                                        f"{course_title} {week_label} {base_name}",
                                        variant["title_suffix"],
                                    ),
                                    instructions=instructions,
                                    artifact_type=content_type,
                                    audio_format=audio_format,
                                    audio_length=audio_length,
                                    infographic_orientation=infographic_orientation,
                                    infographic_detail=infographic_detail,
                                    quiz_quantity=quiz_quantity_arg,
                                    quiz_difficulty=quiz_difficulty_arg,
                                    quiz_format=quiz_format_arg,
                                    report_format=report_format_arg,
                                    language=variant["code"],
                                    output_path=output_path,
                                    wait=args.wait,
                                    skip_existing=args.skip_existing,
                                    source_timeout=args.source_timeout,
                                    generation_timeout=args.generation_timeout,
                                    generator_timeout=args.generator_timeout,
                                    artifact_retries=args.artifact_retries,
                                    artifact_retry_backoff=args.artifact_retry_backoff,
                                    storage=args.storage,
                                    profile=profile_for_run,
                                    preferred_profile=preferred_profile,
                                    profile_priority=profile_priority,
                                    profiles_file=profiles_file_for_run,
                                    exclude_profiles=exclude_profiles or None,
                                    rotate_on_rate_limit=args.rotate_on_rate_limit,
                                    ensure_sources_ready=args.ensure_sources_ready,
                                    append_profile_to_notebook_title=args.append_profile_to_notebook_title,
                                    reuse_notebook=True,
                                )
                            except Exception as exc:
                                failures.append(f"{output_path}: {exc}")
                                continue
                            else:
                                if rotation_enabled:
                                    preferred_profile = update_preferred_profile(
                                        output_path, preferred_profile
                                    )
                            finally:
                                if rotation_enabled and args.profile_cooldown > 0:
                                    update_profile_cooldowns(
                                        output_path,
                                        profile_cooldowns,
                                        args.profile_cooldown,
                                        AUTH_COOLDOWN_SECONDS,
                                    )
                                maybe_sleep(args.sleep_between)
                            request_logs.append(output_path.with_suffix(output_path.suffix + ".request.json"))

                if (
                    not only_slide_keys
                    and review_filter_includes_short_source(review_filter, source_item)
                    and should_generate_brief_for_source(source_item, brief_cfg=brief_cfg)
                ):
                    title_prefix = brief_cfg.get("title_prefix", "[Short]")
                    brief_base = f"{title_prefix} {week_label} - {base_name}"
                    for content_type in brief_types:
                        brief_output = week_output_dir / f"{brief_base}{output_extension(content_type, quiz_format=quiz_format)}"
                        for variant in language_variants:
                            for quiz_difficulty_value in quiz_difficulty_values(content_type, quiz_difficulty):
                                if content_type == "audio":
                                    brief_course_context_note = build_course_context_note(
                                        course_context_bundle=course_context_bundle,
                                        course_context_cfg=course_context_cfg,
                                        lecture_key=week_label,
                                        prompt_type="short",
                                        source_item=source_item,
                                    )
                                    instructions = build_audio_prompt(
                                        prompt_type="short",
                                        prompt_strategy=audio_prompt_strategy,
                                        exam_focus=exam_focus,
                                        study_context=study_context,
                                        prompt_framework=audio_prompt_framework,
                                        meta_prompting=meta_prompting,
                                        course_title=course_title,
                                        course_context_note=brief_course_context_note,
                                        course_context_heading=course_context_cfg.get("heading"),
                                        meta_note_overrides=auto_meta_note_overrides,
                                        custom_prompt=brief_cfg.get("prompt", ""),
                                        audio_format=brief_cfg.get("format", "deep-dive"),
                                        audio_length=brief_cfg.get("length", "long"),
                                        source_item=source_item,
                                    )
                                    audio_format = brief_cfg.get("format", "deep-dive")
                                    audio_length = brief_cfg.get("length", "long")
                                    infographic_orientation = None
                                    infographic_detail = None
                                    quiz_quantity_arg = None
                                    quiz_difficulty_arg = None
                                    quiz_format_arg = None
                                    report_format_arg = None
                                elif content_type == "infographic":
                                    instructions = ensure_prompt(
                                        "short_infographic", brief_infographic_cfg.get("prompt", "")
                                    )
                                    audio_format = None
                                    audio_length = None
                                    infographic_orientation = brief_infographic_cfg.get("orientation")
                                    infographic_detail = brief_infographic_cfg.get("detail")
                                    quiz_quantity_arg = None
                                    quiz_difficulty_arg = None
                                    quiz_format_arg = None
                                    report_format_arg = None
                                elif content_type == "report":
                                    brief_course_context_note = build_course_context_note(
                                        course_context_bundle=course_context_bundle,
                                        course_context_cfg=course_context_cfg,
                                        lecture_key=week_label,
                                        prompt_type="short",
                                        source_item=source_item,
                                    )
                                    instructions = build_report_prompt(
                                        prompt_type="short",
                                        prompt_strategy=report_prompt_strategy,
                                        course_context_note=brief_course_context_note,
                                        course_context_heading=course_context_cfg.get("heading"),
                                        study_context=study_context,
                                        meta_prompting=meta_prompting,
                                        meta_note_overrides=auto_meta_note_overrides,
                                        custom_prompt=short_report_cfg.get("prompt", ""),
                                        source_item=source_item,
                                    )
                                    audio_format = None
                                    audio_length = None
                                    infographic_orientation = None
                                    infographic_detail = None
                                    quiz_quantity_arg = None
                                    quiz_difficulty_arg = None
                                    quiz_format_arg = None
                                    report_format_arg = normalize_report_format(
                                        short_report_cfg.get("format")
                                    )
                                else:
                                    instructions = ensure_prompt("quiz", quiz_cfg.get("prompt", ""))
                                    audio_format = None
                                    audio_length = None
                                    infographic_orientation = None
                                    infographic_detail = None
                                    quiz_quantity_arg = quiz_quantity
                                    quiz_difficulty_arg = quiz_difficulty_value
                                    quiz_format_arg = quiz_format
                                    report_format_arg = None
                                brief_tag = (
                                    build_output_cfg_tag_token(
                                        content_type=content_type,
                                        language=variant["code"],
                                        instructions=instructions,
                                        audio_format=audio_format,
                                        audio_length=audio_length,
                                        infographic_orientation=infographic_orientation,
                                        infographic_detail=infographic_detail,
                                        quiz_quantity=quiz_quantity_arg,
                                        quiz_difficulty=quiz_difficulty_arg,
                                        quiz_format=quiz_format_arg,
                                        report_format=report_format_arg,
                                        source_count=None,
                                        hash_len=args.config_tag_len,
                                    )
                                    if args.config_tagging
                                    else None
                                )
                                brief_candidate = apply_config_tag(
                                    apply_path_suffix(brief_output, variant["suffix"]),
                                    brief_tag,
                                )
                                output_path = ensure_unique_output_path(
                                    brief_candidate,
                                    auth_label,
                                )
                                if not review_filter_includes_output(
                                    review_filter,
                                    "short",
                                    output_path,
                                ):
                                    continue
                                skip, reason = should_skip_generation(output_path, args.skip_existing)
                                if skip:
                                    if args.print_skips:
                                        print(f"Skipping generation ({reason}): {output_path}")
                                    continue
                                if args.print_resolved_prompts and content_type == "audio":
                                    for line in build_prompt_debug_lines(output_path.name, instructions):
                                        print(line)
                                exclude_profiles = (
                                    active_cooldowns(profile_cooldowns)
                                    if rotation_enabled and args.profile_cooldown > 0
                                    else []
                                )
                                if exclude_profiles and exclude_profiles != last_excluded:
                                    print(f"Cooling profiles this run: {', '.join(exclude_profiles)}")
                                    last_excluded = exclude_profiles
                                try:
                                    run_generate(
                                        Path(sys.executable),
                                        generator_script,
                                        sources_file=None,
                                        source_path=source,
                                        notebook_title=apply_suffix(
                                            f"{course_title} {week_label} [Short] {base_name}",
                                            variant["title_suffix"],
                                        ),
                                        instructions=instructions,
                                        artifact_type=content_type,
                                        audio_format=audio_format,
                                        audio_length=audio_length,
                                        infographic_orientation=infographic_orientation,
                                        infographic_detail=infographic_detail,
                                        quiz_quantity=quiz_quantity_arg,
                                        quiz_difficulty=quiz_difficulty_arg,
                                        quiz_format=quiz_format_arg,
                                        report_format=report_format_arg,
                                        language=variant["code"],
                                        output_path=output_path,
                                        wait=args.wait,
                                        skip_existing=args.skip_existing,
                                        source_timeout=args.source_timeout,
                                        generation_timeout=args.generation_timeout,
                                        generator_timeout=args.generator_timeout,
                                        artifact_retries=args.artifact_retries,
                                        artifact_retry_backoff=args.artifact_retry_backoff,
                                        storage=args.storage,
                                        profile=profile_for_run,
                                        preferred_profile=preferred_profile,
                                        profile_priority=profile_priority,
                                        profiles_file=profiles_file_for_run,
                                        exclude_profiles=exclude_profiles or None,
                                        rotate_on_rate_limit=args.rotate_on_rate_limit,
                                        ensure_sources_ready=args.ensure_sources_ready,
                                        append_profile_to_notebook_title=args.append_profile_to_notebook_title,
                                        reuse_notebook=True,
                                    )
                                except Exception as exc:
                                    failures.append(f"{output_path}: {exc}")
                                    continue
                                else:
                                    if rotation_enabled:
                                        preferred_profile = update_preferred_profile(
                                            output_path, preferred_profile
                                        )
                                finally:
                                    if rotation_enabled and args.profile_cooldown > 0:
                                        update_profile_cooldowns(
                                            output_path,
                                            profile_cooldowns,
                                            args.profile_cooldown,
                                            AUTH_COOLDOWN_SECONDS,
                                        )
                                    maybe_sleep(args.sleep_between)
                                request_logs.append(
                                    output_path.with_suffix(output_path.suffix + ".request.json")
                                )

    if only_slide_keys:
        missing_slide_keys = sorted(only_slide_keys - matched_only_slide_keys)
        if missing_slide_keys:
            raise SystemExit(
                "No generated slide source matched --only-slide key(s): "
                + ", ".join(missing_slide_keys)
            )

    if args.print_downloads:
        commands: list[str] = []
        for log_path in request_logs:
            if not log_path.exists():
                continue
            payload = json.loads(log_path.read_text(encoding="utf-8"))
            notebook_id = payload.get("notebook_id")
            artifact_id = payload.get("artifact_id")
            output_path = payload.get("output_path")
            artifact_type = payload.get("artifact_type") or "audio"
            if not (notebook_id and artifact_id and output_path):
                continue
            if artifact_type not in {"audio", "infographic", "quiz"}:
                continue
            cli = shlex.quote(str(notebooklm_cli))
            out = shlex.quote(str(output_path))
            quiz_format = payload.get("quiz_format")
            commands.append(
                f"{cli} artifact wait {artifact_id} -n {notebook_id}"
            )
            download_cmd = f"{cli} download {artifact_type} {out} -a {artifact_id} -n {notebook_id}"
            if artifact_type == "quiz" and quiz_format:
                download_cmd = f"{download_cmd} --format {quiz_format}"
            commands.append(download_cmd)

        if commands:
            print("\n# Wait + download commands")
            for cmd in commands:
                print(cmd)
        else:
            print("\nNo successful request logs were written during this run.")

    if len(processed_dirs) > 1:
        print(
            f"\nSummary: read {total_sources_read} sources, found "
            f"{total_missing_outputs} missing outputs"
        )

    if failures:
        print("\nFailures:")
        for item in failures:
            print(f"- {item}")
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
