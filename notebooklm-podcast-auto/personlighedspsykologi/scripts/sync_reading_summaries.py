#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

WEEK_SELECTOR_PATTERN = re.compile(r"^(?:W)?0*(\d{1,2})(?:L0*(\d{1,2}))?$", re.IGNORECASE)
WEEK_DIR_PATTERN = re.compile(r"^W0*(\d{1,2})(?:L0*(\d{1,2}))?\b", re.IGNORECASE)
WEEK_LECTURE_KEY_PATTERN = re.compile(r"\bW0*(\d{1,2})L0*(\d{1,2})\b", re.IGNORECASE)
CFG_TAG_PATTERN = re.compile(
    r"(?:\s+\{[a-z0-9._:+-]+=[^{}\s]+(?:\s+[a-z0-9._:+-]+=[^{}\s]+)*\})+"
    r"(?:\s+\[[^\[\]]+\])?$",
    re.IGNORECASE,
)
WEEKLY_OVERVIEW_PATTERN = re.compile(r"\b(alle kilder|all sources)\b", re.IGNORECASE)
BRIEF_PATTERN = re.compile(r"^\[\s*brief\s*\]\s*", re.IGNORECASE)
TTS_PATTERN = re.compile(r"^\[\s*tts\s*\]\s*|\boplæst\b", re.IGNORECASE)
AUDIO_EXTENSIONS = {".mp3", ".wav"}


def parse_weeks(week: str | None, weeks: str | None) -> list[str]:
    items: list[str] = []
    if week:
        items.append(week)
    if weeks:
        items.extend(part.strip() for part in weeks.split(",") if part.strip())
    return items


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


def _iter_candidate_dirs(root: Path) -> list[Path]:
    candidates: list[Path] = []
    if not root.exists():
        return candidates
    for entry in sorted(root.iterdir(), key=lambda path: path.name.casefold()):
        if not entry.is_dir():
            continue
        candidates.append(entry)
        for child in sorted(entry.iterdir(), key=lambda path: path.name.casefold()):
            if child.is_dir():
                candidates.append(child)
    return candidates


def find_week_dirs(root: Path, week: str) -> list[Path]:
    if not root.exists():
        return []
    selector = parse_week_selector(week)
    candidates = _iter_candidate_dirs(root)
    if selector:
        requested_week, requested_lesson = selector
        matches: list[Path] = []
        seen: set[Path] = set()
        for candidate in candidates:
            label = parse_week_dir_label(candidate.name)
            if not label:
                continue
            week_num, lesson_num = label
            if week_num != requested_week:
                continue
            if requested_lesson is not None and lesson_num != requested_lesson:
                continue
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            matches.append(candidate)
        return sorted(matches, key=lambda path: path.name.casefold())

    week_upper = week.upper()
    exact: list[Path] = []
    prefix: list[Path] = []
    seen_exact: set[Path] = set()
    seen_prefix: set[Path] = set()
    for candidate in candidates:
        name_upper = candidate.name.upper()
        resolved = candidate.resolve()
        if name_upper == week_upper:
            if resolved not in seen_exact:
                seen_exact.add(resolved)
                exact.append(candidate)
            continue
        if name_upper.startswith(week_upper) and resolved not in seen_prefix:
            seen_prefix.add(resolved)
            prefix.append(candidate)
    if exact:
        return sorted(exact, key=lambda path: path.name.casefold())
    return sorted(prefix, key=lambda path: path.name.casefold())


def _resolve_repo_root(start: Path) -> Path:
    for candidate in [start] + list(start.parents):
        if (candidate / "shows").exists() and (candidate / "notebooklm-podcast-auto").exists():
            return candidate
    return start


def _strip_cfg_tag_suffix(value: str) -> str:
    if not value:
        return value
    return CFG_TAG_PATTERN.sub("", value).strip()


def strip_cfg_tag_from_filename(name: str) -> str:
    if not name:
        return name
    path = Path(name)
    suffix = "".join(path.suffixes)
    stem = name[: -len(suffix)] if suffix else name
    return f"{_strip_cfg_tag_suffix(stem)}{suffix}"


def is_weekly_overview_name(name: str) -> bool:
    stem = Path(strip_cfg_tag_from_filename(name)).stem
    return bool(WEEKLY_OVERVIEW_PATTERN.search(stem))


def extract_lecture_key(value: str) -> str | None:
    match = WEEK_LECTURE_KEY_PATTERN.search(value)
    if not match:
        return None
    week_num = int(match.group(1))
    lecture_num = int(match.group(2))
    return f"W{week_num}L{lecture_num}"


def _load_json_file(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except FileNotFoundError as exc:
        raise RuntimeError(f"File not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object in {path}.")
    return payload


def _load_summaries_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"by_name": {}}
    payload = _load_json_file(path)
    by_name = payload.get("by_name")
    if by_name is None:
        payload["by_name"] = {}
    elif not isinstance(by_name, dict):
        raise RuntimeError(f"Invalid summaries schema in {path}: by_name must be an object.")
    return payload


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp_path.replace(path)


def _coerce_path(repo_root: Path, raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


def _is_audio_file(path: Path) -> bool:
    return path.suffix.lower() in AUDIO_EXTENSIONS


def _list_week_dirs(root: Path) -> list[Path]:
    matches: list[Path] = []
    seen: set[Path] = set()
    for candidate in _iter_candidate_dirs(root):
        if not parse_week_dir_label(candidate.name):
            continue
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        matches.append(candidate)
    return sorted(matches, key=lambda path: str(path))


def _select_week_dirs(output_root: Path, week_inputs: list[str]) -> list[Path]:
    if not output_root.exists():
        raise SystemExit(f"Output root not found: {output_root}")
    if not week_inputs:
        return _list_week_dirs(output_root)

    selected: list[Path] = []
    seen: set[Path] = set()
    for week_input in week_inputs:
        matches = find_week_dirs(output_root, week_input)
        if not matches:
            print(f"Warning: no output week folder found for {week_input} under {output_root}")
            continue
        for path in matches:
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            selected.append(path)
    return sorted(selected, key=lambda path: str(path))


def discover_episode_keys(output_root: Path, week_inputs: list[str]) -> tuple[list[str], list[str]]:
    week_dirs = _select_week_dirs(output_root, week_inputs)
    if not week_dirs:
        return [], []

    keys: list[str] = []
    seen_keys: set[str] = set()
    duplicates: list[str] = []
    seen_files: set[Path] = set()
    for week_dir in week_dirs:
        for file_path in sorted(week_dir.rglob("*")):
            if not file_path.is_file():
                continue
            resolved_file = file_path.resolve()
            if resolved_file in seen_files:
                continue
            seen_files.add(resolved_file)
            if not _is_audio_file(file_path):
                continue
            if is_weekly_overview_name(file_path.name):
                continue
            key = strip_cfg_tag_from_filename(file_path.name)
            if key in seen_keys:
                duplicates.append(key)
                continue
            seen_keys.add(key)
            keys.append(key)
    return sorted(keys, key=str.casefold), sorted(set(duplicates), key=str.casefold)


def discover_weekly_overview_keys(output_root: Path, week_inputs: list[str]) -> tuple[list[str], list[str]]:
    week_dirs = _select_week_dirs(output_root, week_inputs)
    if not week_dirs:
        return [], []

    keys: list[str] = []
    seen_keys: set[str] = set()
    duplicates: list[str] = []
    seen_files: set[Path] = set()
    for week_dir in week_dirs:
        for file_path in sorted(week_dir.rglob("*")):
            if not file_path.is_file():
                continue
            resolved_file = file_path.resolve()
            if resolved_file in seen_files:
                continue
            seen_files.add(resolved_file)
            if not _is_audio_file(file_path):
                continue
            if not is_weekly_overview_name(file_path.name):
                continue
            key = strip_cfg_tag_from_filename(file_path.name)
            if key in seen_keys:
                duplicates.append(key)
                continue
            seen_keys.add(key)
            keys.append(key)
    return sorted(keys, key=str.casefold), sorted(set(duplicates), key=str.casefold)


def _extract_non_empty_text_list(
    entry: dict[str, Any], field: str, *, cache_label: str = "reading_summaries"
) -> list[str]:
    value = entry.get(field, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise RuntimeError(f"{cache_label} entry field '{field}' must be a list.")
    output: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise RuntimeError(f"{cache_label} entry field '{field}' must contain only strings.")
        cleaned = item.strip()
        if cleaned:
            output.append(cleaned)
    return output


def _validate_summaries_schema(payload: dict[str, Any]) -> dict[str, Any]:
    by_name = payload.get("by_name")
    if not isinstance(by_name, dict):
        raise RuntimeError("Invalid summaries schema: by_name must be an object.")
    for key, entry in by_name.items():
        if not isinstance(key, str) or not key.strip():
            raise RuntimeError("Invalid summaries schema: by_name keys must be non-empty strings.")
        if not isinstance(entry, dict):
            raise RuntimeError(f"Invalid summaries schema: entry '{key}' must be an object.")
        _extract_non_empty_text_list(entry, "summary_lines")
        _extract_non_empty_text_list(entry, "key_points")
    return payload


def _load_weekly_summaries_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"by_name": {}}
    payload = _load_json_file(path)
    by_name = payload.get("by_name")
    if by_name is None:
        payload["by_name"] = {}
    elif not isinstance(by_name, dict):
        raise RuntimeError(
            f"Invalid weekly_overview_summaries schema in {path}: by_name must be an object."
        )
    return payload


def _validate_weekly_summaries_schema(payload: dict[str, Any]) -> dict[str, Any]:
    by_name = payload.get("by_name")
    if not isinstance(by_name, dict):
        raise RuntimeError("Invalid weekly_overview_summaries schema: by_name must be an object.")
    for key, entry in by_name.items():
        if not isinstance(key, str) or not key.strip():
            raise RuntimeError(
                "Invalid weekly_overview_summaries schema: by_name keys must be non-empty strings."
            )
        if not isinstance(entry, dict):
            raise RuntimeError(
                f"Invalid weekly_overview_summaries schema: entry '{key}' must be an object."
            )
        _extract_non_empty_text_list(entry, "summary_lines", cache_label="weekly_overview_summaries")
        _extract_non_empty_text_list(entry, "key_points", cache_label="weekly_overview_summaries")
    return payload


def _build_validation_report(
    by_name: dict[str, Any],
    episode_keys: list[str],
    *,
    summary_lines_min: int,
    key_points_min: int,
) -> dict[str, list[str]]:
    missing_entry: list[str] = []
    incomplete_summary: list[str] = []
    incomplete_key_points: list[str] = []

    for key in episode_keys:
        entry = by_name.get(key)
        if not isinstance(entry, dict):
            missing_entry.append(key)
            continue
        summary_lines = _extract_non_empty_text_list(entry, "summary_lines")
        key_points = _extract_non_empty_text_list(entry, "key_points")
        if len(summary_lines) < summary_lines_min:
            incomplete_summary.append(key)
        if len(key_points) < key_points_min:
            incomplete_key_points.append(key)

    return {
        "missing_entry": missing_entry,
        "incomplete_summary": incomplete_summary,
        "incomplete_key_points": incomplete_key_points,
    }


def _print_issue_block(label: str, items: list[str], *, max_items: int = 20) -> None:
    print(f"{label}: {len(items)}")
    if not items:
        return
    for item in items[:max_items]:
        print(f"- {item}")
    if len(items) > max_items:
        print(f"... and {len(items) - max_items} more")


def run_validation(
    by_name: dict[str, Any],
    episode_keys: list[str],
    *,
    summary_lines_min: int,
    key_points_min: int,
) -> dict[str, list[str]]:
    report = _build_validation_report(
        by_name,
        episode_keys,
        summary_lines_min=summary_lines_min,
        key_points_min=key_points_min,
    )
    print("Reading summaries validation (warn-only):")
    print(f"Episodes discovered: {len(episode_keys)}")
    _print_issue_block("missing_entry", report["missing_entry"])
    _print_issue_block("incomplete_summary", report["incomplete_summary"])
    _print_issue_block("incomplete_key_points", report["incomplete_key_points"])
    return report


def _source_variant_priority(name: str) -> int:
    if BRIEF_PATTERN.search(name):
        return 1
    if TTS_PATTERN.search(name):
        return 2
    return 0


def _canonical_source_file_path(path_value: str, *, repo_root: Path) -> str:
    path = Path(path_value).expanduser()
    resolved = (repo_root / path).resolve() if not path.is_absolute() else path.resolve()
    try:
        return str(resolved.relative_to(repo_root))
    except ValueError:
        return str(resolved)


def _expected_source_files_for_lecture(
    sources_root: Path, lecture_key: str, *, repo_root: Path
) -> list[str]:
    lecture_match = WEEK_LECTURE_KEY_PATTERN.search(lecture_key)
    if not lecture_match:
        return []
    week_num = int(lecture_match.group(1))
    lecture_num = int(lecture_match.group(2))
    candidates = [
        directory
        for directory in sorted(sources_root.iterdir(), key=lambda path: path.name.casefold())
        if directory.is_dir() and parse_week_dir_label(directory.name) == (week_num, lecture_num)
    ]
    if not candidates:
        return []
    selected = candidates[0]
    return [
        _canonical_source_file_path(str(path), repo_root=repo_root)
        for path in sorted(selected.iterdir(), key=lambda item: item.name.casefold())
        if path.is_file() and path.suffix.lower() == ".pdf"
    ]


def _build_weekly_draft_from_reading_summaries(
    reading_by_name: dict[str, Any],
    lecture_key: str,
    *,
    summary_lines_max: int,
    key_points_max: int,
    repo_root: Path,
) -> tuple[list[str], list[str], list[str]]:
    best_by_source: dict[str, tuple[int, str, dict[str, Any]]] = {}
    for episode_key, entry in reading_by_name.items():
        if not isinstance(episode_key, str) or not isinstance(entry, dict):
            continue
        if is_weekly_overview_name(episode_key):
            continue
        if extract_lecture_key(episode_key) != lecture_key:
            continue
        meta = entry.get("meta")
        source_file = meta.get("source_file") if isinstance(meta, dict) else None
        if not isinstance(source_file, str) or not source_file.strip():
            continue
        source_file = _canonical_source_file_path(source_file, repo_root=repo_root)
        priority = _source_variant_priority(episode_key)
        current = best_by_source.get(source_file)
        candidate = (priority, episode_key.casefold(), entry)
        if current is None or candidate < current:
            best_by_source[source_file] = candidate

    source_files = sorted(best_by_source.keys(), key=str.casefold)
    summary_lines: list[str] = []
    key_points: list[str] = []
    seen_lines: set[str] = set()
    seen_points: set[str] = set()
    for source_file in source_files:
        entry = best_by_source[source_file][2]
        for line in _extract_non_empty_text_list(entry, "summary_lines"):
            normalized = line.casefold()
            if normalized in seen_lines:
                continue
            seen_lines.add(normalized)
            summary_lines.append(line)
            if len(summary_lines) >= summary_lines_max:
                break
        for point in _extract_non_empty_text_list(entry, "key_points"):
            normalized = point.casefold()
            if normalized in seen_points:
                continue
            seen_points.add(normalized)
            key_points.append(point)
            if len(key_points) >= key_points_max:
                break
        if len(summary_lines) >= summary_lines_max and len(key_points) >= key_points_max:
            break
    return source_files, summary_lines, key_points


def sync_weekly_overview_cache(
    weekly_by_name: dict[str, Any],
    weekly_keys: list[str],
    reading_by_name: dict[str, Any],
    *,
    sources_root: Path,
    summary_lines_max: int,
    key_points_max: int,
    repo_root: Path,
) -> tuple[list[str], list[str], list[str]]:
    added: list[str] = []
    updated: list[str] = []
    missing_lecture_key: list[str] = []

    for weekly_key in weekly_keys:
        lecture_key = extract_lecture_key(weekly_key)
        if not lecture_key:
            missing_lecture_key.append(weekly_key)
            continue
        expected_source_files = _expected_source_files_for_lecture(
            sources_root, lecture_key, repo_root=repo_root
        )
        covered_source_files, draft_lines, draft_points = _build_weekly_draft_from_reading_summaries(
            reading_by_name,
            lecture_key,
            summary_lines_max=summary_lines_max,
            key_points_max=key_points_max,
            repo_root=repo_root,
        )
        expected_set = set(expected_source_files)
        covered_set = set(covered_source_files)
        missing_source_files = sorted(expected_set - covered_set, key=str.casefold)

        existing_entry = weekly_by_name.get(weekly_key)
        was_new = not isinstance(existing_entry, dict)
        if not isinstance(existing_entry, dict):
            existing_entry = {}
        existing_summary_lines = _extract_non_empty_text_list(
            existing_entry, "summary_lines", cache_label="weekly_overview_summaries"
        )
        existing_key_points = _extract_non_empty_text_list(
            existing_entry, "key_points", cache_label="weekly_overview_summaries"
        )
        existing_meta = existing_entry.get("meta")
        merged_meta = dict(existing_meta) if isinstance(existing_meta, dict) else {}
        merged_meta.update(
            {
                "status": merged_meta.get("status", "todo_manual_da"),
                "lecture_key": lecture_key,
                "source_count_expected": len(expected_source_files),
                "source_count_covered": len(covered_source_files),
                "source_files_expected": expected_source_files,
                "source_files_covered": covered_source_files,
                "missing_source_files": missing_source_files,
                "draft_from_reading_summaries": {
                    "summary_lines": draft_lines,
                    "key_points": draft_points,
                },
                "method": merged_meta.get("method", "aggregate_reading_then_manual_da_v1"),
            }
        )
        weekly_by_name[weekly_key] = {
            "summary_lines": existing_summary_lines,
            "key_points": existing_key_points,
            "meta": merged_meta,
        }
        if was_new:
            added.append(weekly_key)
        else:
            updated.append(weekly_key)
    return sorted(added, key=str.casefold), sorted(updated, key=str.casefold), sorted(
        missing_lecture_key, key=str.casefold
    )


def _is_likely_danish_text(value: str) -> bool:
    words = re.findall(r"[a-zA-ZæøåÆØÅ]+", value.casefold())
    if len(words) < 8:
        return False
    da_markers = {
        "og",
        "det",
        "den",
        "til",
        "af",
        "for",
        "ikke",
        "som",
        "med",
        "på",
        "er",
        "en",
        "at",
        "de",
        "i",
    }
    en_markers = {"the", "and", "for", "with", "that", "this", "from", "is", "are", "to", "of", "in"}
    da_hits = sum(1 for word in words if word in da_markers)
    en_hits = sum(1 for word in words if word in en_markers)
    return da_hits >= 4 and da_hits >= (en_hits * 1.2)


def _build_weekly_validation_report(
    weekly_by_name: dict[str, Any],
    weekly_keys: list[str],
    *,
    summary_lines_min: int,
    key_points_min: int,
) -> dict[str, list[str]]:
    weekly_missing_entry: list[str] = []
    weekly_incomplete_summary: list[str] = []
    weekly_incomplete_key_points: list[str] = []
    weekly_non_danish: list[str] = []
    weekly_source_coverage_gap: list[str] = []

    for key in weekly_keys:
        entry = weekly_by_name.get(key)
        if not isinstance(entry, dict):
            weekly_missing_entry.append(key)
            continue
        summary_lines = _extract_non_empty_text_list(
            entry, "summary_lines", cache_label="weekly_overview_summaries"
        )
        key_points = _extract_non_empty_text_list(
            entry, "key_points", cache_label="weekly_overview_summaries"
        )
        if len(summary_lines) < summary_lines_min:
            weekly_incomplete_summary.append(key)
        if len(key_points) < key_points_min:
            weekly_incomplete_key_points.append(key)
        combined = "\n".join(summary_lines + key_points)
        if combined and not _is_likely_danish_text(combined):
            weekly_non_danish.append(key)

        meta = entry.get("meta")
        if isinstance(meta, dict):
            expected = meta.get("source_count_expected")
            covered = meta.get("source_count_covered")
            if isinstance(expected, int) and isinstance(covered, int) and expected > 0 and covered < expected:
                weekly_source_coverage_gap.append(f"{key} ({covered}/{expected})")

    return {
        "weekly_missing_entry": weekly_missing_entry,
        "weekly_incomplete_summary": weekly_incomplete_summary,
        "weekly_incomplete_key_points": weekly_incomplete_key_points,
        "weekly_non_danish": weekly_non_danish,
        "weekly_source_coverage_gap": weekly_source_coverage_gap,
    }


def run_weekly_validation(
    weekly_by_name: dict[str, Any],
    weekly_keys: list[str],
    *,
    summary_lines_min: int,
    key_points_min: int,
) -> dict[str, list[str]]:
    report = _build_weekly_validation_report(
        weekly_by_name,
        weekly_keys,
        summary_lines_min=summary_lines_min,
        key_points_min=key_points_min,
    )
    print("Alle kilder (per lecture) summaries validation (warn-only):")
    print(f"Alle kilder episodes discovered: {len(weekly_keys)}")
    _print_issue_block("weekly_missing_entry", report["weekly_missing_entry"])
    _print_issue_block("weekly_incomplete_summary", report["weekly_incomplete_summary"])
    _print_issue_block("weekly_incomplete_key_points", report["weekly_incomplete_key_points"])
    _print_issue_block("weekly_non_danish", report["weekly_non_danish"])
    _print_issue_block("weekly_source_coverage_gap", report["weekly_source_coverage_gap"])
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scaffold and validate repo-local reading summaries from local episode files."
    )
    parser.add_argument("--week", help="Optional single week label, e.g. W01L1 or W01.")
    parser.add_argument("--weeks", help="Optional comma-separated week labels, e.g. W01,W02L1.")
    parser.add_argument(
        "--output-root",
        default="notebooklm-podcast-auto/personlighedspsykologi/output",
        help="Root folder containing local episode outputs.",
    )
    parser.add_argument(
        "--summaries-file",
        default="shows/personlighedspsykologi-en/reading_summaries.json",
        help="Path to reading summaries JSON cache.",
    )
    parser.add_argument(
        "--weekly-summaries-file",
        default="shows/personlighedspsykologi-en/weekly_overview_summaries.json",
        help="Path to weekly overview summaries JSON cache.",
    )
    parser.add_argument(
        "--sources-root",
        default="notebooklm-podcast-auto/personlighedspsykologi/sources",
        help="Root folder containing lecture source PDFs.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview updates without writing.")
    parser.add_argument("--validate-only", action="store_true", help="Validate coverage without writing.")
    parser.add_argument(
        "--sync-weekly-overview",
        action="store_true",
        help="Scaffold/update per-lecture Alle kilder cache from reading summaries coverage + drafts.",
    )
    parser.add_argument(
        "--validate-weekly",
        action="store_true",
        help="Include weekly overview summaries validation in output.",
    )
    parser.add_argument("--summary-lines-min", type=int, default=2)
    parser.add_argument("--summary-lines-max", type=int, default=4)
    parser.add_argument("--key-points-min", type=int, default=3)
    parser.add_argument("--key-points-max", type=int, default=5)
    args = parser.parse_args()

    if args.summary_lines_min < 1 or args.key_points_min < 1:
        raise SystemExit("Minimum counts must be >= 1.")
    if args.summary_lines_max < args.summary_lines_min:
        raise SystemExit("--summary-lines-max must be >= --summary-lines-min.")
    if args.key_points_max < args.key_points_min:
        raise SystemExit("--key-points-max must be >= --key-points-min.")

    week_inputs = parse_weeks(args.week, args.weeks)
    repo_root = _resolve_repo_root(Path(__file__).resolve())
    output_root = _coerce_path(repo_root, args.output_root)
    summaries_path = _coerce_path(repo_root, args.summaries_file)
    weekly_summaries_path = _coerce_path(repo_root, args.weekly_summaries_file)
    sources_root = _coerce_path(repo_root, args.sources_root)
    episode_keys, duplicate_keys = discover_episode_keys(output_root, week_inputs)
    weekly_keys, weekly_duplicate_keys = discover_weekly_overview_keys(output_root, week_inputs)
    if duplicate_keys:
        print("Warning: duplicate episode keys found across local outputs; keeping first occurrence.")
        _print_issue_block("duplicate_keys", duplicate_keys)
    if weekly_duplicate_keys:
        print("Warning: duplicate weekly overview keys found across local outputs; keeping first occurrence.")
        _print_issue_block("weekly_duplicate_keys", weekly_duplicate_keys)
    if not episode_keys:
        print("No local reading/brief/tts episode files found for the selected scope.")
    if (args.sync_weekly_overview or args.validate_weekly) and not weekly_keys:
        print("No local Alle kilder / All sources audio files found for the selected scope.")
    if not episode_keys and not weekly_keys:
        return 0

    try:
        summaries_payload = _validate_summaries_schema(_load_summaries_payload(summaries_path))
    except RuntimeError as exc:
        raise SystemExit(str(exc))
    by_name = summaries_payload["by_name"]

    weekly_payload: dict[str, Any] = {"by_name": {}}
    weekly_by_name: dict[str, Any] = {}
    if args.sync_weekly_overview or args.validate_weekly:
        try:
            weekly_payload = _validate_weekly_summaries_schema(
                _load_weekly_summaries_payload(weekly_summaries_path)
            )
        except RuntimeError as exc:
            raise SystemExit(str(exc))
        weekly_by_name = weekly_payload["by_name"]

    if args.validate_only:
        if episode_keys:
            run_validation(
                by_name,
                episode_keys,
                summary_lines_min=args.summary_lines_min,
                key_points_min=args.key_points_min,
            )
        if args.validate_weekly and weekly_keys:
            run_weekly_validation(
                weekly_by_name,
                weekly_keys,
                summary_lines_min=args.summary_lines_min,
                key_points_min=args.key_points_min,
            )
        return 0

    added_keys: list[str] = []
    for key in episode_keys:
        if key in by_name:
            continue
        by_name[key] = {
            "summary_lines": [],
            "key_points": [],
        }
        added_keys.append(key)
    summaries_payload["by_name"] = dict(sorted(by_name.items(), key=lambda item: item[0].casefold()))

    added_weekly: list[str] = []
    updated_weekly: list[str] = []
    missing_weekly_lecture_key: list[str] = []
    if args.sync_weekly_overview and weekly_keys:
        if not sources_root.exists():
            print(f"Warning: sources root not found: {sources_root}")
        added_weekly, updated_weekly, missing_weekly_lecture_key = sync_weekly_overview_cache(
            weekly_by_name,
            weekly_keys,
            by_name,
            sources_root=sources_root,
            summary_lines_max=args.summary_lines_max,
            key_points_max=args.key_points_max,
            repo_root=repo_root,
        )
        weekly_payload["by_name"] = dict(sorted(weekly_by_name.items(), key=lambda item: item[0].casefold()))

    print(f"Episodes discovered: {len(episode_keys)}")
    print(f"Missing reading entries added: {len(added_keys)}")
    if args.sync_weekly_overview:
        print(f"Alle kilder episodes discovered: {len(weekly_keys)}")
        print(f"Alle kilder entries added: {len(added_weekly)}")
        print(f"Alle kilder entries metadata refreshed: {len(updated_weekly)}")
        if missing_weekly_lecture_key:
            _print_issue_block("weekly_missing_lecture_key", missing_weekly_lecture_key)
    if args.dry_run:
        if added_keys:
            print("Dry-run: would add summary placeholders for:")
            for key in added_keys[:50]:
                print(f"- {key}")
            if len(added_keys) > 50:
                print(f"... and {len(added_keys) - 50} more")
        else:
            print("Dry-run: no placeholder updates needed.")
        if args.sync_weekly_overview:
            if added_weekly:
                print("Dry-run: would add Alle kilder entries for:")
                for key in added_weekly[:50]:
                    print(f"- {key}")
                if len(added_weekly) > 50:
                    print(f"... and {len(added_weekly) - 50} more")
            else:
                print("Dry-run: no new Alle kilder entries needed.")
        return 0

    if added_keys:
        _save_json(summaries_path, summaries_payload)
        print(
            f"Wrote {len(added_keys)} new reading entr{'y' if len(added_keys) == 1 else 'ies'} "
            f"to {summaries_path}"
        )
    else:
        print("No placeholder updates needed.")
    if args.sync_weekly_overview:
        if added_weekly or updated_weekly:
            _save_json(weekly_summaries_path, weekly_payload)
            print(
                f"Wrote Alle kilder summaries cache to {weekly_summaries_path} "
                f"(added={len(added_weekly)}, updated={len(updated_weekly)})."
            )
        else:
            print("No Alle kilder cache updates needed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
