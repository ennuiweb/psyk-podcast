#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

WEEK_SELECTOR_PATTERN = re.compile(r"^(?:W)?0*(\d{1,2})(?:L0*(\d{1,2}))?$", re.IGNORECASE)
WEEK_DIR_PATTERN = re.compile(r"^W0*(\d{1,2})(?:L0*(\d{1,2}))?\b", re.IGNORECASE)
CFG_TAG_PATTERN = re.compile(
    r"(?:\s+\{[a-z0-9._:+-]+=[^{}\s]+(?:\s+[a-z0-9._:+-]+=[^{}\s]+)*\})+"
    r"(?:\s+\[[^\[\]]+\])?$",
    re.IGNORECASE,
)
WEEKLY_OVERVIEW_PATTERN = re.compile(r"\b(alle kilder|all sources)\b", re.IGNORECASE)
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")
MARKDOWN_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def parse_weeks(week: str | None, weeks: str | None) -> list[str]:
    if not week and not weeks:
        raise SystemExit("Provide --week or --weeks.")
    items: list[str] = []
    if week:
        items.append(week)
    if weeks:
        items.extend(part.strip() for part in weeks.split(",") if part.strip())
    if not items:
        raise SystemExit("No valid weeks provided.")
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


def _resolve_repo_root(start: Path) -> Path:
    for candidate in [start] + list(start.parents):
        if (candidate / "shows").exists() and (candidate / "notebooklm-podcast-auto").exists():
            return candidate
    return start


def _default_profiles_paths(repo_root: Path) -> list[Path]:
    return [
        Path.cwd() / "profiles.json",
        repo_root / "notebooklm-podcast-auto" / "profiles.json",
    ]


def _resolve_profiles_path(repo_root: Path, profiles_file: str | None) -> Path | None:
    if profiles_file:
        path = Path(profiles_file).expanduser()
        if not path.exists():
            raise SystemExit(f"Profiles file not found: {path}")
        return path
    for candidate in _default_profiles_paths(repo_root):
        if candidate.exists():
            return candidate
    return None


def _load_profiles(path: Path) -> dict[str, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and isinstance(raw.get("profiles"), dict):
        raw = raw["profiles"]
    if not isinstance(raw, dict):
        raise SystemExit(
            "Profiles file must be a JSON object of {profile_name: storage_path} "
            "or {\"profiles\": {...}}"
        )

    profiles: dict[str, str] = {}
    base_dir = path.parent
    for name, value in raw.items():
        if not isinstance(name, str) or value is None:
            continue
        raw_path = Path(str(value)).expanduser()
        if not raw_path.is_absolute():
            raw_path = (base_dir / raw_path).resolve()
        else:
            raw_path = raw_path.resolve()
        profiles[name] = str(raw_path)

    if not profiles:
        raise SystemExit("Profiles file did not contain any valid profile entries.")
    return profiles


def resolve_storage_path(
    repo_root: Path,
    *,
    storage: str | None,
    profile: str | None,
    profiles_file: str | None,
) -> str | None:
    if storage and profile:
        raise SystemExit("Use either --storage or --profile, not both.")
    if storage:
        return str(Path(storage).expanduser().resolve())
    if not profile:
        return None
    profiles_path = _resolve_profiles_path(repo_root, profiles_file)
    if not profiles_path:
        raise SystemExit("Profiles file not found. Provide --profiles-file.")
    profiles = _load_profiles(profiles_path)
    if profile not in profiles:
        raise SystemExit(
            f"Profile '{profile}' not found in {profiles_path}. "
            f"Available: {', '.join(sorted(profiles))}"
        )
    return str(Path(profiles[profile]).expanduser().resolve())


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


def _is_audio_reading_request(payload: dict[str, Any]) -> bool:
    artifact_type = str(payload.get("artifact_type") or "audio").lower()
    if artifact_type != "audio":
        return False
    output_path = payload.get("output_path")
    if not isinstance(output_path, str) or not output_path.strip():
        return False
    return not is_weekly_overview_name(Path(output_path).name)


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


def _parse_command_json(text: str) -> dict[str, Any]:
    raw = text.strip()
    if not raw:
        raise RuntimeError("Command returned empty output.")
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    first_obj = raw.find("{")
    last_obj = raw.rfind("}")
    if first_obj != -1 and last_obj > first_obj:
        snippet = raw[first_obj : last_obj + 1]
        payload = json.loads(snippet)
        if isinstance(payload, dict):
            return payload
    raise RuntimeError("Unable to parse JSON output from command.")


def _run_notebooklm_json(
    notebooklm_cli: Path,
    *,
    storage_path: str | None,
    args: list[str],
) -> dict[str, Any]:
    cmd = [str(notebooklm_cli)]
    if storage_path:
        cmd.extend(["--storage", storage_path])
    cmd.extend(args)
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        detail = stderr or stdout or f"exit code {result.returncode}"
        raise RuntimeError(f"NotebookLM command failed: {' '.join(cmd)} :: {detail}")
    return _parse_command_json(result.stdout)


def _source_match_key(source_entry: dict[str, Any]) -> tuple[str, str] | None:
    kind = str(source_entry.get("kind") or "").strip().lower()
    if kind == "url":
        value = str(source_entry.get("value") or "").strip()
        return ("url", value) if value else None
    if kind == "file":
        value = str(source_entry.get("value") or "").strip()
        if not value:
            return None
        return ("title", Path(value).name.strip().lower())
    if kind == "text":
        title = str(source_entry.get("title") or "").strip()
        return ("title", title.lower()) if title else None
    return None


def _find_source_from_notebook(
    payload_sources: list[dict[str, Any]],
    notebook_sources: list[dict[str, Any]],
) -> dict[str, Any] | None:
    expected_keys: list[tuple[str, str]] = []
    for source_entry in payload_sources:
        if not isinstance(source_entry, dict):
            continue
        key = _source_match_key(source_entry)
        if key and key not in expected_keys:
            expected_keys.append(key)

    if expected_keys:
        for key_type, key_value in expected_keys:
            for source in notebook_sources:
                source_title = str(source.get("title") or "").strip().lower()
                source_url = str(source.get("url") or "").strip()
                if key_type == "title" and source_title == key_value:
                    return source
                if key_type == "url" and source_url == key_value:
                    return source

    if len(notebook_sources) == 1:
        return notebook_sources[0]
    return None


def _strip_markdown(value: str) -> str:
    text = MARKDOWN_FENCE_PATTERN.sub("", value.strip())
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"^\s*[-*]\s+", "", text)
    return text.strip()


def _split_text_units(value: str) -> list[str]:
    clean = _strip_markdown(value)
    if not clean:
        return []
    units: list[str] = []
    for line in clean.splitlines():
        candidate = _strip_markdown(line)
        if not candidate:
            continue
        for sentence in SENTENCE_SPLIT_PATTERN.split(candidate):
            normalized = sentence.strip()
            if normalized:
                units.append(normalized)
    if not units and clean:
        units.append(clean)
    return units


def _dedupe(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def normalize_summary_lines(
    raw: Any,
    *,
    min_count: int,
    max_count: int,
    source_title: str,
) -> list[str]:
    candidates: list[str] = []
    if isinstance(raw, list):
        for value in raw:
            if isinstance(value, str):
                candidates.extend(_split_text_units(value))
    elif isinstance(raw, str):
        candidates.extend(_split_text_units(raw))
    candidates = _dedupe(value.strip() for value in candidates if value.strip())
    fallback = [
        f"This reading focuses on {source_title}.",
        "The episode summarizes the central argument and supporting evidence.",
        "It connects the main concepts to the broader personality psychology context.",
        "You get a concise walkthrough of what matters most for the course.",
    ]
    while len(candidates) < min_count and fallback:
        candidates.append(fallback.pop(0))
    return candidates[:max_count]


def normalize_key_points(
    raw: Any,
    *,
    min_count: int,
    max_count: int,
    source_title: str,
    summary_lines: list[str],
) -> list[str]:
    candidates: list[str] = []
    if isinstance(raw, list):
        for value in raw:
            if isinstance(value, str):
                candidates.extend(_split_text_units(value))
    elif isinstance(raw, str):
        candidates.extend(_split_text_units(raw))
    candidates = _dedupe(value.strip().rstrip(".") for value in candidates if value.strip())

    summary_based = [line.strip().rstrip(".") for line in summary_lines if line.strip()]
    for item in summary_based:
        if len(candidates) >= min_count:
            break
        if item.casefold() not in {entry.casefold() for entry in candidates}:
            candidates.append(item)

    fallback = [
        f"Scope and framing of {source_title}",
        "Core concepts and terminology",
        "Main argument and evidence",
        "Implications for understanding personality",
    ]
    while len(candidates) < min_count and fallback:
        candidates.append(fallback.pop(0))
    return candidates[:max_count]


def _extract_json_from_answer(answer: str) -> dict[str, Any] | None:
    cleaned = _strip_markdown(answer)
    try:
        payload = json.loads(cleaned)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        pass

    first = cleaned.find("{")
    last = cleaned.rfind("}")
    if first != -1 and last > first:
        try:
            payload = json.loads(cleaned[first : last + 1])
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None
    return None


def parse_ask_summary_payload(ask_response: dict[str, Any]) -> tuple[Any, Any] | None:
    answer = ask_response.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        return None
    parsed = _extract_json_from_answer(answer)
    if not parsed:
        return None
    return parsed.get("summary_lines"), parsed.get("key_points")


def derive_from_guide_payload(
    guide_response: dict[str, Any],
    *,
    min_summary: int,
    max_summary: int,
    min_points: int,
    max_points: int,
    source_title: str,
) -> tuple[list[str], list[str]]:
    summary_lines = normalize_summary_lines(
        guide_response.get("summary"),
        min_count=min_summary,
        max_count=max_summary,
        source_title=source_title,
    )
    key_points = normalize_key_points(
        guide_response.get("keywords"),
        min_count=min_points,
        max_count=max_points,
        source_title=source_title,
        summary_lines=summary_lines,
    )
    return summary_lines, key_points


def build_structured_prompt(
    *,
    min_summary: int,
    max_summary: int,
    min_points: int,
    max_points: int,
) -> str:
    return (
        "Return ONLY valid JSON, no markdown, no extra text. "
        "Schema: {\"summary_lines\": string[], \"key_points\": string[]}. "
        f"summary_lines: {min_summary}-{max_summary} concise lines in English. "
        f"key_points: {min_points}-{max_points} short points in English. "
        "Each item should be self-contained and based only on the selected source."
    )


def collect_reading_requests(week_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    candidates: list[tuple[Path, dict[str, Any]]] = []
    for log_path in sorted(week_dir.glob("*.request.json")):
        try:
            payload = _load_json_file(log_path)
        except RuntimeError as exc:
            print(f"Warning: {exc}", file=sys.stderr)
            continue
        if not _is_audio_reading_request(payload):
            continue
        candidates.append((log_path, payload))
    return candidates


def _build_summary_entry(
    *,
    notebooklm_cli: Path,
    storage_path: str | None,
    payload: dict[str, Any],
    min_summary: int,
    max_summary: int,
    min_points: int,
    max_points: int,
) -> tuple[str, dict[str, Any]]:
    output_path = payload.get("output_path")
    if not isinstance(output_path, str) or not output_path.strip():
        raise RuntimeError("Request payload missing output_path.")
    output_name = Path(output_path).name
    cache_key = strip_cfg_tag_from_filename(output_name)

    notebook_id = payload.get("notebook_id")
    if not isinstance(notebook_id, str) or not notebook_id.strip():
        raise RuntimeError("Request payload missing notebook_id.")

    source_list = _run_notebooklm_json(
        notebooklm_cli,
        storage_path=storage_path,
        args=["source", "list", "-n", notebook_id, "--json"],
    )
    notebook_sources = source_list.get("sources")
    if not isinstance(notebook_sources, list) or not notebook_sources:
        raise RuntimeError(f"No notebook sources found for notebook {notebook_id}.")

    payload_sources = payload.get("sources")
    payload_sources_list = payload_sources if isinstance(payload_sources, list) else []
    source = _find_source_from_notebook(payload_sources_list, notebook_sources)
    if not source:
        raise RuntimeError(
            f"Unable to match request payload sources to notebook source for {output_name}."
        )
    source_id = source.get("id")
    if not isinstance(source_id, str) or not source_id.strip():
        raise RuntimeError("Resolved source is missing source id.")
    source_title = str(source.get("title") or output_name).strip()

    prompt = build_structured_prompt(
        min_summary=min_summary,
        max_summary=max_summary,
        min_points=min_points,
        max_points=max_points,
    )

    method = "ask_json_with_guide_fallback_v1"
    ask_summary_lines: Any = None
    ask_key_points: Any = None
    try:
        ask_response = _run_notebooklm_json(
            notebooklm_cli,
            storage_path=storage_path,
            args=["ask", prompt, "--new", "-n", notebook_id, "-s", source_id, "--json"],
        )
        parsed = parse_ask_summary_payload(ask_response)
        if parsed:
            ask_summary_lines, ask_key_points = parsed
    except Exception:
        parsed = None

    if ask_summary_lines is None or ask_key_points is None:
        guide_response = _run_notebooklm_json(
            notebooklm_cli,
            storage_path=storage_path,
            args=["source", "guide", source_id, "-n", notebook_id, "--json"],
        )
        summary_lines, key_points = derive_from_guide_payload(
            guide_response,
            min_summary=min_summary,
            max_summary=max_summary,
            min_points=min_points,
            max_points=max_points,
            source_title=source_title,
        )
        method = "source_guide_fallback_v1"
    else:
        summary_lines = normalize_summary_lines(
            ask_summary_lines,
            min_count=min_summary,
            max_count=max_summary,
            source_title=source_title,
        )
        key_points = normalize_key_points(
            ask_key_points,
            min_count=min_points,
            max_count=max_points,
            source_title=source_title,
            summary_lines=summary_lines,
        )

    entry = {
        "summary_lines": summary_lines,
        "key_points": key_points,
        "meta": {
            "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
                "+00:00", "Z"
            ),
            "notebook_id": notebook_id,
            "source_id": source_id,
            "source_title": source_title,
            "method": method,
        },
    }
    return cache_key, entry


def _coerce_path(repo_root: Path, raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate and cache reading summaries/key points from NotebookLM request logs."
    )
    parser.add_argument("--week", help="Single week label, e.g. W01L1 or W01.")
    parser.add_argument("--weeks", help="Comma-separated week labels, e.g. W01,W02L1.")
    parser.add_argument(
        "--output-root",
        default="notebooklm-podcast-auto/personlighedspsykologi/output",
        help="Root folder containing week output directories.",
    )
    parser.add_argument(
        "--summaries-file",
        default="shows/personlighedspsykologi-en/reading_summaries.json",
        help="Path to reading summaries JSON cache.",
    )
    parser.add_argument(
        "--notebooklm-cli",
        default="notebooklm-podcast-auto/.venv/bin/notebooklm",
        help="Path to notebooklm CLI executable.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview updates without writing.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Regenerate summaries even when an entry already exists.",
    )
    parser.add_argument(
        "--profile",
        help="Profile name from profiles.json (resolves to a storage file).",
    )
    parser.add_argument(
        "--profiles-file",
        help="Custom profiles.json path used with --profile.",
    )
    parser.add_argument(
        "--storage",
        help="Path to storage_state.json passed through to notebooklm CLI.",
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
    notebooklm_cli = _coerce_path(repo_root, args.notebooklm_cli)
    if not notebooklm_cli.exists():
        raise SystemExit(f"notebooklm CLI not found: {notebooklm_cli}")

    storage_path = resolve_storage_path(
        repo_root,
        storage=args.storage,
        profile=args.profile,
        profiles_file=args.profiles_file,
    )

    week_dirs: list[Path] = []
    seen_dirs: set[Path] = set()
    for week_input in week_inputs:
        matches = find_week_dirs(output_root, week_input)
        if not matches:
            print(f"Warning: no output week folder found for {week_input} under {output_root}")
            continue
        for week_dir in matches:
            if week_dir in seen_dirs:
                continue
            seen_dirs.add(week_dir)
            week_dirs.append(week_dir)

    if not week_dirs:
        raise SystemExit("No matching week output folders found.")

    summaries_payload = _load_summaries_payload(summaries_path)
    by_name = summaries_payload.setdefault("by_name", {})
    if not isinstance(by_name, dict):
        raise SystemExit("Invalid summaries schema: by_name must be an object.")

    updates: dict[str, dict[str, Any]] = {}
    skipped_existing = 0
    failures = 0
    scanned = 0

    for week_dir in sorted(week_dirs, key=lambda path: path.name):
        for _, payload in collect_reading_requests(week_dir):
            scanned += 1
            output_path = payload.get("output_path")
            if not isinstance(output_path, str) or not output_path.strip():
                failures += 1
                print(f"Warning: invalid output_path in request payload from {week_dir}", file=sys.stderr)
                continue
            key = strip_cfg_tag_from_filename(Path(output_path).name)
            if not args.refresh and key in by_name:
                skipped_existing += 1
                continue
            try:
                cache_key, entry = _build_summary_entry(
                    notebooklm_cli=notebooklm_cli,
                    storage_path=storage_path,
                    payload=payload,
                    min_summary=args.summary_lines_min,
                    max_summary=args.summary_lines_max,
                    min_points=args.key_points_min,
                    max_points=args.key_points_max,
                )
            except Exception as exc:
                failures += 1
                print(f"Warning: failed to build summary for {key}: {exc}", file=sys.stderr)
                continue
            updates[cache_key] = entry

    if updates:
        for key, value in updates.items():
            by_name[key] = value
        summaries_payload["by_name"] = dict(sorted(by_name.items(), key=lambda item: item[0].casefold()))
        if args.dry_run:
            print("Dry-run: planned reading summary updates:")
            for key in sorted(updates):
                print(f"- {key}")
        else:
            _save_json(summaries_path, summaries_payload)
            print(f"Wrote {len(updates)} summary entr{'y' if len(updates) == 1 else 'ies'} to {summaries_path}")
    elif args.dry_run:
        print("Dry-run: no summary updates needed.")
    else:
        print("No summary updates needed.")

    print(
        f"Scanned={scanned} Updated={len(updates)} SkippedExisting={skipped_existing} Failures={failures}"
    )
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
