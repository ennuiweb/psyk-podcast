#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

WEEK_SELECTOR_PATTERN = re.compile(r"^(?:W)?0*(\d{1,2})(?:L0*(\d{1,2}))?$", re.IGNORECASE)
WEEK_DIR_PATTERN = re.compile(r"^W0*(\d{1,2})(?:L0*(\d{1,2}))?\b", re.IGNORECASE)
CFG_TAG_PATTERN = re.compile(
    r"(?:\s+\{[a-z0-9._:+-]+=[^{}\s]+(?:\s+[a-z0-9._:+-]+=[^{}\s]+)*\})+"
    r"(?:\s+\[[^\[\]]+\])?$",
    re.IGNORECASE,
)
WEEKLY_OVERVIEW_PATTERN = re.compile(r"\b(alle kilder|all sources)\b", re.IGNORECASE)
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


def _extract_non_empty_text_list(entry: dict[str, Any], field: str) -> list[str]:
    value = entry.get(field, [])
    if value is None:
        return []
    if not isinstance(value, list):
        raise RuntimeError(f"reading_summaries entry field '{field}' must be a list.")
    output: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise RuntimeError(f"reading_summaries entry field '{field}' must contain only strings.")
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
    parser.add_argument("--dry-run", action="store_true", help="Preview updates without writing.")
    parser.add_argument("--validate-only", action="store_true", help="Validate coverage without writing.")
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
    episode_keys, duplicate_keys = discover_episode_keys(output_root, week_inputs)
    if duplicate_keys:
        print("Warning: duplicate episode keys found across local outputs; keeping first occurrence.")
        _print_issue_block("duplicate_keys", duplicate_keys)
    if not episode_keys:
        print("No local reading/brief/tts episode files found for the selected scope.")
        return 0

    try:
        summaries_payload = _validate_summaries_schema(_load_summaries_payload(summaries_path))
    except RuntimeError as exc:
        raise SystemExit(str(exc))
    by_name = summaries_payload["by_name"]

    if args.validate_only:
        run_validation(
            by_name,
            episode_keys,
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

    print(f"Episodes discovered: {len(episode_keys)}")
    print(f"Missing entries added: {len(added_keys)}")
    if args.dry_run:
        if added_keys:
            print("Dry-run: would add summary placeholders for:")
            for key in added_keys[:50]:
                print(f"- {key}")
            if len(added_keys) > 50:
                print(f"... and {len(added_keys) - 50} more")
        else:
            print("Dry-run: no placeholder updates needed.")
        return 0

    if added_keys:
        _save_json(summaries_path, summaries_payload)
        print(f"Wrote {len(added_keys)} new entr{'y' if len(added_keys) == 1 else 'ies'} to {summaries_path}")
    else:
        print("No placeholder updates needed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
