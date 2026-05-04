"""Compile course-aware lecture context for NotebookLM prompt generation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_COURSE_CONTEXT = {
    "enabled": True,
    "heading": "Course-aware lecture context:",
    "content_manifest": "",
    "course_overview": "",
    "neighbor_window": 1,
    "max_readings": 3,
    "max_points_per_reading": 2,
    "max_slide_titles": 4,
    "max_course_themes": 22,
}


@dataclass(frozen=True)
class CoursePromptContextBundle:
    content_manifest_path: Path
    course_overview_path: Path | None
    lectures: list[dict[str, Any]]
    lecture_index: dict[str, int]
    course_overview_lines: list[str]
    course_theme_titles: list[str]


def _deep_copy_defaults(value: object) -> object:
    if isinstance(value, dict):
        return {key: _deep_copy_defaults(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_deep_copy_defaults(item) for item in value]
    return value


def normalize_course_context(raw: object) -> dict[str, Any]:
    defaults = _deep_copy_defaults(DEFAULT_COURSE_CONTEXT)
    if raw in (None, ""):
        return defaults
    if not isinstance(raw, dict):
        raise SystemExit("course_context must be an object.")

    normalized = defaults
    if "enabled" in raw:
        if not isinstance(raw["enabled"], bool):
            raise SystemExit("course_context.enabled must be true or false.")
        normalized["enabled"] = raw["enabled"]
    for field in ("heading", "content_manifest", "course_overview"):
        if field not in raw:
            continue
        value = raw[field]
        if not isinstance(value, str):
            raise SystemExit(f"course_context.{field} must be a string.")
        normalized[field] = value.strip()
    for field in (
        "neighbor_window",
        "max_readings",
        "max_points_per_reading",
        "max_slide_titles",
        "max_course_themes",
    ):
        if field not in raw:
            continue
        value = raw[field]
        if not isinstance(value, int) or value < 0:
            raise SystemExit(f"course_context.{field} must be an integer >= 0.")
        normalized[field] = value
    if normalized["max_readings"] < 1:
        raise SystemExit("course_context.max_readings must be >= 1.")
    if normalized["max_points_per_reading"] < 1:
        raise SystemExit("course_context.max_points_per_reading must be >= 1.")
    if normalized["max_slide_titles"] < 1:
        raise SystemExit("course_context.max_slide_titles must be >= 1.")
    return normalized


def canonicalize_lecture_key(value: str) -> str:
    match = re.fullmatch(r"\s*W?0*(\d{1,2})L0*(\d{1,2})\s*", value, re.IGNORECASE)
    if not match:
        return value.strip().upper()
    return f"W{int(match.group(1)):02d}L{int(match.group(2))}"


def resolve_course_context_paths(
    *,
    repo_root: Path,
    config: dict[str, Any],
    slides_catalog_path: Path | None,
) -> tuple[Path | None, Path | None]:
    show_dir: Path | None = None
    if slides_catalog_path is not None:
        show_dir = slides_catalog_path.resolve().parent

    def _resolve_path(value: str, default_path: Path | None) -> Path | None:
        if value:
            candidate = Path(value).expanduser()
            if not candidate.is_absolute():
                candidate = repo_root / candidate
            return candidate.resolve()
        if default_path is None:
            return None
        return default_path.resolve()

    content_manifest_path = _resolve_path(
        str(config.get("content_manifest") or "").strip(),
        (show_dir / "content_manifest.json") if show_dir is not None else None,
    )
    course_overview_path = _resolve_path(
        str(config.get("course_overview") or "").strip(),
        (show_dir / "docs" / "overblik.md") if show_dir is not None else None,
    )
    return content_manifest_path, course_overview_path


def load_course_prompt_context_bundle(
    *,
    repo_root: Path,
    config: dict[str, Any],
    slides_catalog_path: Path | None,
) -> CoursePromptContextBundle | None:
    if not config.get("enabled", False):
        return None

    content_manifest_path, course_overview_path = resolve_course_context_paths(
        repo_root=repo_root,
        config=config,
        slides_catalog_path=slides_catalog_path,
    )
    if content_manifest_path is None:
        return None
    if not content_manifest_path.exists() or not content_manifest_path.is_file():
        raise RuntimeError(f"content manifest not found: {content_manifest_path}")

    try:
        manifest_payload = json.loads(content_manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"unable to parse content manifest: {content_manifest_path}") from exc
    raw_lectures = manifest_payload.get("lectures")
    if not isinstance(raw_lectures, list):
        raise RuntimeError(f"content manifest is missing a lectures list: {content_manifest_path}")

    lectures: list[dict[str, Any]] = []
    lecture_index: dict[str, int] = {}
    for raw_lecture in raw_lectures:
        if not isinstance(raw_lecture, dict):
            continue
        lecture_key = canonicalize_lecture_key(str(raw_lecture.get("lecture_key") or ""))
        if not re.fullmatch(r"W\d{2}L\d+", lecture_key):
            continue
        lecture_copy = dict(raw_lecture)
        lecture_copy["lecture_key"] = lecture_key
        lectures.append(lecture_copy)
        lecture_index[lecture_key] = len(lectures) - 1

    course_overview_lines: list[str] = []
    course_theme_titles: list[str] = []
    if course_overview_path is not None and course_overview_path.exists() and course_overview_path.is_file():
        try:
            text = course_overview_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise RuntimeError(f"unable to read course overview: {course_overview_path}") from exc
        course_overview_lines = _course_overview_lines(text)
        course_theme_titles = _course_theme_titles_from_overview(text)
    if not course_theme_titles:
        course_theme_titles = _fallback_course_theme_titles(lectures)

    return CoursePromptContextBundle(
        content_manifest_path=content_manifest_path,
        course_overview_path=course_overview_path if course_overview_lines else None,
        lectures=lectures,
        lecture_index=lecture_index,
        course_overview_lines=course_overview_lines,
        course_theme_titles=course_theme_titles,
    )


def _course_overview_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        cleaned = raw_line.strip()
        if not cleaned:
            continue
        cleaned = re.sub(r"^\s*[-*]\s*", "", cleaned)
        cleaned = re.sub(r"^\s*#+\s*", "", cleaned)
        cleaned = re.sub(r"\[(.*?)\]\([^)]*\)", r"\1", cleaned)
        cleaned = cleaned.strip()
        if cleaned:
            lines.append(cleaned)
    return lines


def _clean_lecture_theme(value: str) -> str:
    cleaned = str(value or "").strip()
    cleaned = re.sub(r"\s*\([^)]*\)\s*$", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned


def _course_theme_titles_from_overview(text: str) -> list[str]:
    themes: list[str] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        if not re.fullmatch(r"W0*\d{1,2}", cells[0], re.IGNORECASE):
            continue
        theme = _clean_lecture_theme(cells[2])
        if not theme:
            continue
        match_key = theme.casefold()
        if match_key in seen:
            continue
        seen.add(match_key)
        themes.append(theme)
    return themes


def _fallback_course_theme_titles(lectures: list[dict[str, Any]]) -> list[str]:
    themes: list[str] = []
    seen: set[str] = set()
    for lecture in lectures:
        theme = _clean_lecture_theme(str(lecture.get("lecture_title") or ""))
        if not theme:
            continue
        match_key = theme.casefold()
        if match_key in seen:
            continue
        seen.add(match_key)
        themes.append(theme)
    return themes


def _format_course_arc_titles(titles: list[str], *, max_items: int) -> str:
    if max_items <= 0 or not titles:
        return ""
    selected = titles[:max_items]
    if len(selected) <= 5:
        return "; ".join(selected)
    return "; ".join([*selected[:3], "...", *selected[-2:]])


def _normalize_match_key(value: str) -> str:
    cleaned = str(value or "").strip().casefold()
    cleaned = re.sub(r"^w\d+l\d+\s*[-–:._ ]*\s*", "", cleaned)
    cleaned = re.sub(r"^(slide)\s+(lecture|seminar|exercise)\s*:\s*", "", cleaned)
    cleaned = re.sub(r"\.(pdf|mp3|json|md|txt)$", "", cleaned)
    cleaned = re.sub(r"[^a-z0-9æøå]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _semantic_artifact_paths(bundle: CoursePromptContextBundle) -> dict[str, Path]:
    show_dir = bundle.content_manifest_path.parent
    return {
        "course_glossary": show_dir / "course_glossary.json",
        "course_theory_map": show_dir / "course_theory_map.json",
        "source_weighting": show_dir / "source_weighting.json",
        "course_concept_graph": show_dir / "course_concept_graph.json",
    }


def _lecture_semantic_context_lines(
    *,
    bundle: CoursePromptContextBundle,
    lecture_key: str,
    max_items: int,
) -> list[str]:
    paths = _semantic_artifact_paths(bundle)
    glossary_payload = _load_optional_json(paths["course_glossary"])
    theory_map_payload = _load_optional_json(paths["course_theory_map"])
    weighting_payload = _load_optional_json(paths["source_weighting"])
    concept_graph_payload = _load_optional_json(paths["course_concept_graph"])

    lines: list[str] = []
    if isinstance(weighting_payload, dict):
        weighting_lectures = weighting_payload.get("lectures")
        if isinstance(weighting_lectures, list):
            for lecture in weighting_lectures:
                if not isinstance(lecture, dict):
                    continue
                if canonicalize_lecture_key(str(lecture.get("lecture_key") or "")) != lecture_key:
                    continue
                ranked = lecture.get("ranked_sources")
                if not isinstance(ranked, list):
                    break
                ranked_lines = []
                for item in ranked[:max_items]:
                    if not isinstance(item, dict):
                        continue
                    title = str(item.get("title") or item.get("source_id") or "").strip()
                    band = str(item.get("weight_band") or "").strip()
                    if title:
                        ranked_lines.append(f"{title} [{band}]")
                if ranked_lines:
                    lines.append("- Ranked source emphasis: " + "; ".join(ranked_lines) + ".")
                break

    if isinstance(glossary_payload, dict):
        terms = glossary_payload.get("terms")
        if isinstance(terms, list):
            lecture_terms = [
                term
                for term in terms
                if isinstance(term, dict)
                and lecture_key in [canonicalize_lecture_key(item) for item in term.get("lecture_keys", [])]
            ]
            lecture_terms.sort(key=lambda item: -int(item.get("salience_score") or 0))
            if lecture_terms:
                selected = lecture_terms[:max_items]
                lines.append(
                    "- Course concepts in play: "
                    + "; ".join(
                        f"{str(term.get('label') or '').strip()} ({str(term.get('category') or '').strip()})"
                        for term in selected
                        if str(term.get("label") or "").strip()
                    )
                    + "."
                )

    if isinstance(theory_map_payload, dict):
        theories = theory_map_payload.get("theories")
        if isinstance(theories, list):
            lecture_theories = [
                theory
                for theory in theories
                if isinstance(theory, dict)
                and lecture_key in [canonicalize_lecture_key(item) for item in theory.get("lecture_keys", [])]
            ]
            lecture_theories.sort(key=lambda item: -int(item.get("salience_score") or 0))
            if lecture_theories:
                selected = lecture_theories[:max_items]
                lines.append(
                    "- Theory frame: "
                    + "; ".join(str(theory.get("label") or "").strip() for theory in selected if str(theory.get("label") or "").strip())
                    + "."
                )

    if isinstance(concept_graph_payload, dict):
        distinctions = concept_graph_payload.get("distinctions")
        if isinstance(distinctions, list):
            lecture_distinctions = [
                distinction
                for distinction in distinctions
                if isinstance(distinction, dict)
                and lecture_key in [canonicalize_lecture_key(item) for item in distinction.get("lecture_keys", [])]
            ]
            lecture_distinctions.sort(key=lambda item: -int(item.get("importance") or 0))
            if lecture_distinctions:
                selected = lecture_distinctions[: max(1, min(2, max_items))]
                lines.append(
                    "- Cross-lecture tensions to keep explicit: "
                    + "; ".join(str(distinction.get("label") or "").strip() for distinction in selected if str(distinction.get("label") or "").strip())
                    + "."
                )

    return lines


def _summary_lines(entry: dict[str, Any] | None) -> list[str]:
    if not isinstance(entry, dict):
        return []
    result: list[str] = []
    for field in ("summary_lines", "key_points"):
        values = entry.get(field)
        if not isinstance(values, list):
            continue
        for value in values:
            cleaned = str(value or "").strip()
            if cleaned:
                result.append(cleaned)
    return result


def _reading_summary_points(reading: dict[str, Any], *, max_points: int) -> list[str]:
    points = _summary_lines(reading.get("summary") if isinstance(reading.get("summary"), dict) else None)
    return points[:max_points]


def _course_stage(sequence_index: int, total: int) -> str:
    if total <= 0:
        return "unknown"
    position = sequence_index / total
    if position <= 0.33:
        return "early/foundational"
    if position >= 0.67:
        return "late/integrative"
    return "middle/transitional"


def _slide_titles_by_subcategory(
    lecture: dict[str, Any],
    *,
    max_slide_titles: int,
) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {
        "lecture": [],
        "seminar": [],
        "exercise": [],
    }
    for slide in lecture.get("slides") or []:
        if not isinstance(slide, dict):
            continue
        subcategory = str(slide.get("subcategory") or "").strip().lower()
        if subcategory not in grouped:
            continue
        title = str(slide.get("title") or "").strip()
        if not title:
            continue
        if title not in grouped[subcategory]:
            grouped[subcategory].append(title)
    return {
        key: value[:max_slide_titles]
        for key, value in grouped.items()
        if value
    }


def _find_matching_reading(lecture: dict[str, Any], source_item: object) -> dict[str, Any] | None:
    source_path = getattr(source_item, "path", None)
    source_stem = source_path.stem if isinstance(source_path, Path) else ""
    source_name = getattr(source_item, "base_name", "")
    candidates = {
        _normalize_match_key(source_stem),
        _normalize_match_key(source_path.name if isinstance(source_path, Path) else ""),
        _normalize_match_key(source_name),
    }
    candidates.discard("")
    for reading in lecture.get("readings") or []:
        if not isinstance(reading, dict):
            continue
        keys = {
            _normalize_match_key(str(reading.get("reading_title") or "")),
            _normalize_match_key(str(reading.get("source_filename") or "")),
            _normalize_match_key(Path(str(reading.get("source_filename") or "")).stem),
        }
        keys.discard("")
        if candidates & keys:
            return reading
    return None


def _find_matching_slide(lecture: dict[str, Any], source_item: object) -> dict[str, Any] | None:
    slide_key = str(getattr(source_item, "slide_key", "") or "").strip().lower()
    source_name = getattr(source_item, "base_name", "")
    candidates = {
        slide_key,
        _normalize_match_key(source_name),
    }
    source_path = getattr(source_item, "path", None)
    if isinstance(source_path, Path):
        candidates.add(_normalize_match_key(source_path.stem))
        candidates.add(_normalize_match_key(source_path.name))
    candidates.discard("")
    for slide in lecture.get("slides") or []:
        if not isinstance(slide, dict):
            continue
        keys = {
            str(slide.get("slide_key") or "").strip().lower(),
            _normalize_match_key(str(slide.get("title") or "")),
            _normalize_match_key(str(slide.get("source_filename") or "")),
            _normalize_match_key(Path(str(slide.get("source_filename") or "")).stem),
        }
        keys.discard("")
        if candidates & keys:
            return slide
    return None


def _overview_excerpt(bundle: CoursePromptContextBundle, lecture_key: str) -> str | None:
    if not bundle.course_overview_lines:
        return None
    target_key = canonicalize_lecture_key(lecture_key)
    for index, line in enumerate(bundle.course_overview_lines):
        line_key_match = re.search(r"\bW0*(\d{1,2})L0*(\d{1,2})\b", line, re.IGNORECASE)
        if not line_key_match:
            continue
        line_key = canonicalize_lecture_key(line_key_match.group(0))
        if line_key != target_key:
            continue
        start = max(0, index - 1)
        end = min(len(bundle.course_overview_lines), index + 2)
        return " | ".join(bundle.course_overview_lines[start:end])
    return None


def _source_character_lines(lecture: dict[str, Any], source_item: object | None) -> list[str]:
    if source_item is None:
        return [
            "- Treat this as a lecture-block synthesis across multiple readings, informed by teaching framing rather than as one uniform text."
        ]

    source_type = str(getattr(source_item, "source_type", "") or "").strip().lower()
    if source_type == "slide":
        slide = _find_matching_slide(lecture, source_item)
        title = str((slide or {}).get("title") or getattr(source_item, "base_name", "")).strip()
        subcategory = str((slide or {}).get("subcategory") or "").strip().lower() or "slide"
        if subcategory == "lecture":
            return [
                f"- This is a lecture slide deck: fragmentary teaching scaffolding for the theme '{title}'.",
                "- Treat the deck as a guide to sequence, emphasis, and framing rather than as a complete prose source.",
            ]
        if subcategory == "seminar":
            return [
                f"- This is a seminar slide deck: application- and discussion-oriented teaching material for '{title}'.",
                "- Expect prompts, exercises, and simplifications that presuppose the lecture and readings.",
            ]
        if subcategory == "exercise":
            return [
                f"- This is an exercise slide deck: practice-oriented material for '{title}'.",
                "- Use it to reconstruct what is being trained or clarified, not as a standalone theory text.",
            ]
        return [
            "- This is a slide deck rather than a full prose source.",
            "- Reconstruct structure and emphasis without overstating what the slides explicitly say.",
        ]

    reading = _find_matching_reading(lecture, source_item)
    title = str((reading or {}).get("reading_title") or getattr(source_item, "base_name", "")).strip()
    if "grundbog kapitel" in title.casefold():
        return [
            f"- This is a textbook chapter: an orienting or field-mapping text for '{title}'.",
            "- Use it to frame the lecture theme, key concepts, and major distinctions rather than expecting one narrow empirical claim.",
        ]
    return [
        f"- This is an assigned article or chapter centered on the specific contribution '{title}'.",
        "- Treat it as one perspective on the lecture theme, with its own argument, emphasis, and delimitations.",
    ]


def build_course_prompt_context_note(
    *,
    bundle: CoursePromptContextBundle | None,
    config: dict[str, Any] | None,
    lecture_key: str,
    prompt_type: str,
    source_item: object | None = None,
) -> str:
    if bundle is None or not config or not config.get("enabled", False):
        return ""
    canonical_key = canonicalize_lecture_key(lecture_key)
    lecture_position = bundle.lecture_index.get(canonical_key)
    if lecture_position is None:
        return ""

    lecture = bundle.lectures[lecture_position]
    total_lectures = len(bundle.lectures)
    sequence_index = int(lecture.get("sequence_index") or lecture_position + 1)
    lecture_title = str(lecture.get("lecture_title") or canonical_key).strip() or canonical_key
    stage = _course_stage(sequence_index, total_lectures)
    neighbor_window = max(0, int(config.get("neighbor_window", 1)))
    reading_limit = max(1, int(config.get("max_readings", 3)))
    point_limit = max(1, int(config.get("max_points_per_reading", 2)))
    slide_limit = max(1, int(config.get("max_slide_titles", 4)))
    course_theme_limit = max(0, int(config.get("max_course_themes", 22)))
    if prompt_type == "short":
        reading_limit = min(reading_limit, 2)
        point_limit = 1
        course_theme_limit = min(course_theme_limit, 8)

    sections: list[str] = []
    lecture_theme = _clean_lecture_theme(lecture_title) or lecture_title

    frame_lines = [
        f"- Current lecture: {canonical_key} - {lecture_title}.",
        f"- Current lecture theme: {lecture_theme}.",
        (
            f"- Course position: lecture {sequence_index} of {total_lectures}; "
            f"this sits in the {stage} portion of the course."
        ),
    ]
    previous_lectures = []
    next_lectures = []
    for offset in range(1, neighbor_window + 1):
        previous_index = lecture_position - offset
        next_index = lecture_position + offset
        if previous_index >= 0:
            prev_lecture = bundle.lectures[previous_index]
            previous_lectures.append(
                f"{prev_lecture.get('lecture_key')} - {str(prev_lecture.get('lecture_title') or '').strip()}"
            )
        if next_index < total_lectures:
            next_lecture = bundle.lectures[next_index]
            next_lectures.append(
                f"{next_lecture.get('lecture_key')} - {str(next_lecture.get('lecture_title') or '').strip()}"
            )
    if previous_lectures:
        frame_lines.append(f"- It builds on: {', '.join(previous_lectures)}.")
    if next_lectures:
        frame_lines.append(f"- It leads into: {', '.join(next_lectures)}.")
    if bundle.course_theme_titles and course_theme_limit > 0:
        course_arc = _format_course_arc_titles(
            bundle.course_theme_titles,
            max_items=course_theme_limit,
        )
        if course_arc:
            frame_lines.append(f"- Broader course arc in play: {course_arc}.")
    overview_excerpt = _overview_excerpt(bundle, canonical_key)
    if overview_excerpt:
        frame_lines.append(f"- Course overview excerpt: {overview_excerpt}.")
    sections.append("## Course and lecture frame\n" + "\n".join(frame_lines))

    source_character_lines = _source_character_lines(lecture, source_item)
    if source_character_lines:
        sections.append("## Source character\n" + "\n".join(source_character_lines))

    lecture_summary = lecture.get("summary") if isinstance(lecture.get("summary"), dict) else None
    summary_lines = _summary_lines(lecture_summary)
    if summary_lines:
        sections.append(
            "## Lecture synthesis\n"
            + "\n".join(f"- {line}" for line in summary_lines[: max(4, point_limit + 1)])
        )

    slide_titles = _slide_titles_by_subcategory(lecture, max_slide_titles=slide_limit)
    if slide_titles:
        slide_lines: list[str] = []
        if slide_titles.get("lecture"):
            slide_lines.append(
                "- Forelaesning slides frame the lecture through: "
                + "; ".join(slide_titles["lecture"])
                + "."
            )
        if slide_titles.get("seminar"):
            slide_lines.append(
                "- Seminar slides operationalize or test the material through: "
                + "; ".join(slide_titles["seminar"])
                + "."
            )
        if slide_titles.get("exercise"):
            slide_lines.append(
                "- Exercise slides reinforce the block through: "
                + "; ".join(slide_titles["exercise"])
                + "."
            )
        if slide_lines:
            sections.append("## Teaching context\n" + "\n".join(slide_lines))

    reading_lines: list[str] = []
    for reading in lecture.get("readings") or []:
        if not isinstance(reading, dict):
            continue
        title = str(reading.get("reading_title") or "").strip()
        if not title:
            continue
        summary_points = _reading_summary_points(reading, max_points=point_limit)
        if summary_points:
            reading_lines.append(f"- {title}: {' '.join(summary_points)}")
        else:
            reading_lines.append(f"- {title}.")
        if len(reading_lines) >= reading_limit:
            break
    if reading_lines:
        sections.append("## Reading map\n" + "\n".join(reading_lines))

    semantic_lines = _lecture_semantic_context_lines(
        bundle=bundle,
        lecture_key=canonical_key,
        max_items=3 if prompt_type != "short" else 2,
    )
    if semantic_lines:
        sections.append("## Semantic guidance\n" + "\n".join(semantic_lines))

    target_lines: list[str] = []
    if source_item is not None:
        source_type = str(getattr(source_item, "source_type", "") or "").strip().lower()
        if source_type == "reading":
            reading = _find_matching_reading(lecture, source_item)
            if reading is not None:
                title = str(reading.get("reading_title") or getattr(source_item, "base_name", "")).strip()
                summary_points = _reading_summary_points(reading, max_points=max(2, point_limit))
                if title:
                    target_lines.append(f"- Target source: {title}.")
                for point in summary_points:
                    target_lines.append(f"- Use this reading as one contribution to the lecture block, not as the whole block.")
                    target_lines.append(f"- Source-specific emphasis: {point}")
                    break
        elif source_type == "slide":
            slide = _find_matching_slide(lecture, source_item)
            if slide is not None:
                title = str(slide.get("title") or getattr(source_item, "base_name", "")).strip()
                subcategory = str(slide.get("subcategory") or "").strip().lower() or "slide"
                target_lines.append(
                    f"- Target source: {subcategory} slide deck '{title}'. Treat it as teaching structure, not as a complete statement of the theory."
                )
                target_lines.append(
                    "- Reconstruct the lecturer's sequencing and emphasis, then anchor substantive claims in the lecture block and readings where possible."
                )
    if target_lines:
        sections.append("## Target source fit\n" + "\n".join(target_lines))

    sections.append(
        "## Grounding rules\n"
        "- Treat lecture-level and course-level framing as prioritization aids rather than replacement for what the source explicitly says.\n"
        "- Let slide framing help decide emphasis and likely misunderstandings, but keep claims anchored in the supplied source material.\n"
        "- Use slide titles and neighboring lectures to orient the explanation, but do not attribute unsupported claims to authors or lecturers."
    )
    return "\n\n".join(section for section in sections if section.strip())
