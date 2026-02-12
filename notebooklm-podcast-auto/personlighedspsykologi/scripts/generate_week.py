#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
import shlex


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


WEEK_SELECTOR_PATTERN = re.compile(r"^W0*(\d{1,2})(?:L0*(\d{1,2}))?$", re.IGNORECASE)
WEEK_DIR_PATTERN = re.compile(r"^W0*(\d{1,2})(?:L0*(\d{1,2}))?\b", re.IGNORECASE)


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


def week_has_missing(reading_key: Path, week: str) -> bool:
    # Compare parsed week/lesson tokens so W8L1 and W08L1 map to the same section.
    target = parse_week_selector(week.strip())
    if not target:
        return False

    in_section = False
    for line in reading_key.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("**W"):
            heading = stripped.lstrip("*")
            section = parse_week_dir_label(heading)
            if section:
                if in_section and section != target:
                    break
                in_section = section == target
                continue
        if in_section and "MISSING:" in stripped:
            return True
    return False


WEEK_PREFIX_PATTERN = re.compile(r"^(W0*(\d{1,2})L0*(\d{1,2}))\\b[\\s._-]*", re.IGNORECASE)


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
    normalized = re.sub(r"\\.{2,}", ".", normalized)
    normalized = re.sub(r"\\s+", " ", normalized).strip()
    return normalized or title


def ensure_prompt(_: str, value: str) -> str:
    return value.strip()


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
    "429",
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
    "403",
)
AUTH_COOLDOWN_SECONDS = 3600


def is_rate_limit_error(message: str) -> bool:
    lowered = message.lower()
    return any(token in lowered for token in RATE_LIMIT_TOKENS)


def is_auth_error(message: str) -> bool:
    lowered = message.lower()
    return any(token in lowered for token in AUTH_TOKENS)


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

        error = str(payload.get("error", ""))
        auth = payload.get("auth") if isinstance(payload.get("auth"), dict) else {}
        profile = auth.get("profile") if isinstance(auth, dict) else None
        if profile and is_rate_limit_error(error):
            cooldowns[profile] = max(
                cooldowns.get(profile, 0), now + rate_limit_seconds
            )
        if profile and is_auth_error(error):
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
    allowed = {"audio", "infographic", "quiz"}
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
    allowed = {"easy", "medium", "hard"}
    if normalized not in allowed:
        raise SystemExit(
            f"Unknown quiz difficulty '{value}'. Allowed: {', '.join(sorted(allowed))}."
        )
    return normalized


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
    }
    return mapping[content_type]


def find_profiles_path(repo_root: Path, profiles_file: str | None) -> Path | None:
    if profiles_file:
        path = Path(profiles_file).expanduser()
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
    log_path = output_path.with_suffix(output_path.suffix + ".request.json")
    if not log_path.exists():
        return None
    try:
        payload = json.loads(log_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    auth = payload.get("auth")
    return auth if isinstance(auth, dict) else None


def update_preferred_profile(output_path: Path, current: str | None) -> str | None:
    auth = load_request_auth(output_path)
    if not auth:
        return current
    profile = auth.get("profile")
    if profile:
        return str(profile)
    return current


def load_request_payload(output_path: Path) -> dict | None:
    log_path = output_path.with_suffix(output_path.suffix + ".request.json")
    if not log_path.exists():
        return None
    try:
        payload = json.loads(log_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def should_skip_generation(output_path: Path, skip_existing: bool) -> tuple[bool, str | None]:
    if output_path.exists() and output_path.stat().st_size > 0:
        return True, "output exists"
    if not skip_existing:
        return False, None
    error_log = output_path.with_suffix(output_path.suffix + ".request.error.json")
    if error_log.exists():
        return False, None
    payload = load_request_payload(output_path)
    if not payload:
        return False, None
    artifact_id = payload.get("artifact_id")
    if artifact_id:
        return True, "request log exists"
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
    if not output_path.exists() or not label:
        return output_path

    existing_label = auth_label_from_meta(load_request_auth(output_path))
    if existing_label == label:
        return output_path

    candidate = output_path.with_name(f"{output_path.stem} [{label}]{output_path.suffix}")
    if not candidate.exists():
        return candidate
    if auth_label_from_meta(load_request_auth(candidate)) == label:
        return candidate

    counter = 2
    while True:
        candidate = output_path.with_name(
            f"{output_path.stem} [{label}-{counter}]{output_path.suffix}"
        )
        if not candidate.exists():
            return candidate
        if auth_label_from_meta(load_request_auth(candidate)) == label:
            return candidate
        counter += 1


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
    output_path: Path,
    wait: bool,
    skip_existing: bool,
    source_timeout: float | None,
    generation_timeout: float | None,
    artifact_retries: int | None,
    artifact_retry_backoff: float | None,
    storage: str | None,
    profile: str | None,
    preferred_profile: str | None,
    profile_priority: str | None,
    profiles_file: str | None,
    exclude_profiles: list[str] | None,
    rotate_on_rate_limit: bool,
    ensure_sources_ready: bool,
    append_profile_to_notebook_title: bool,
) -> None:
    cmd = [
        str(python),
        str(script),
        "--notebook-title",
        notebook_title,
        "--reuse-notebook",
        "--instructions",
        instructions,
        "--artifact-type",
        artifact_type,
        "--output",
        str(output_path),
    ]
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
    if language:
        cmd.extend(["--language", language])
    if sources_file:
        cmd.extend(["--sources-file", str(sources_file)])
    if source_path:
        cmd.extend(["--source", str(source_path)])
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
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
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
        help="Single week label, e.g. W01L1 (or W01 to include all W01L* folders).",
    )
    parser.add_argument(
        "--weeks",
        help="Comma-separated week labels, e.g. W01,W02",
    )
    parser.add_argument(
        "--sources-root",
        default="notebooklm-podcast-auto/personlighedspsykologi/sources",
        help="Root folder containing week source folders.",
    )
    parser.add_argument(
        "--reading-key",
        default="notebooklm-podcast-auto/personlighedspsykologi/docs/reading-file-key.md",
        help="Reading key file (for missing checks).",
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
        "--output-root",
        default="notebooklm-podcast-auto/personlighedspsykologi/output",
        help="Where to place generated artifacts.",
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
    reading_key = repo_root / args.reading_key
    prompt_config = repo_root / args.prompt_config
    output_root = repo_root / args.output_root
    rotation_enabled = args.rotate_on_rate_limit and not args.profile and not args.storage
    auto_profile, auto_profiles_path = auto_profile_from_profiles(repo_root, args)
    profile_for_run = None if rotation_enabled else (args.profile or auto_profile)
    profiles_file_for_run = args.profiles_file or (str(auto_profiles_path) if auto_profiles_path else None)
    profile_slug = resolve_profile_slug(profile_for_run, args.storage)
    output_root = apply_profile_subdir(output_root, profile_slug, args.output_profile_subdir)
    auth_label = profile_slug if not rotation_enabled else None
    generator_script = repo_root / "notebooklm-podcast-auto" / "generate_podcast.py"
    notebooklm_cli = repo_root / "notebooklm-podcast-auto" / ".venv" / "bin" / "notebooklm"

    config = read_json(prompt_config)
    content_types = parse_content_types(args.content_types)
    language_variants = build_language_variants(config)
    weekly_cfg = config.get("weekly_overview", {})
    per_cfg = config.get("per_reading", {})
    brief_cfg = config.get("brief", {})
    infographic_defaults = ensure_dict(config.get("infographic"))
    weekly_infographic_cfg = ensure_dict(config.get("weekly_infographic", infographic_defaults))
    per_infographic_cfg = ensure_dict(config.get("per_reading_infographic", infographic_defaults))
    brief_infographic_cfg = ensure_dict(config.get("brief_infographic", infographic_defaults))
    quiz_cfg = ensure_dict(config.get("quiz"))
    quiz_quantity = normalize_quiz_quantity(quiz_cfg.get("quantity"))
    quiz_difficulty = normalize_quiz_difficulty(quiz_cfg.get("difficulty"))
    quiz_format = normalize_quiz_format(quiz_cfg.get("format"))

    request_logs: list[Path] = []
    failures: list[str] = []
    profile_cooldowns: dict[str, float] = {}
    last_excluded: list[str] = []
    preferred_profile: str | None = None
    profile_priority = args.profile_priority

    processed_dirs: set[Path] = set()
    for week_input in week_inputs:
        week_dirs = find_week_dirs(sources_root, week_input)
        if not week_dirs:
            raise SystemExit(f"No week folder found for {week_input} under {sources_root}")
        if len(week_dirs) > 1 and not re.fullmatch(r"W0*\d{1,2}", week_input.upper()):
            names = ", ".join(path.name for path in week_dirs)
            raise SystemExit(f"Multiple week folders match {week_input}: {names}")
        for week_dir in week_dirs:
            if week_dir in processed_dirs:
                continue
            processed_dirs.add(week_dir)
            week_label = week_dir.name.split(" ", 1)[0].upper()

            week_output_dir = output_root / week_label
            week_output_dir.mkdir(parents=True, exist_ok=True)

            sources = list_source_files(week_dir)
            if not sources:
                raise SystemExit(f"No source files found in {week_dir}")

            missing = week_has_missing(reading_key, week_label)

            planned_lines: list[str] = []
            weekly_base = f"{week_label} - Alle kilder"
            if not missing:
                for content_type in content_types:
                    weekly_output = week_output_dir / f"{weekly_base}{output_extension(content_type, quiz_format=quiz_format)}"
                    for variant in language_variants:
                        planned_path = ensure_unique_output_path(
                            apply_path_suffix(weekly_output, variant["suffix"]),
                            auth_label,
                        )
                        planned_lines.append(
                            f"WEEKLY {content_type.upper()} ({variant['code'] or 'default'}): {planned_path}"
                        )
            else:
                for content_type in content_types:
                    weekly_output = week_output_dir / f"{weekly_base}{output_extension(content_type, quiz_format=quiz_format)}"
                    planned_lines.append(
                        f"SKIP WEEKLY {content_type.upper()} (missing readings): {weekly_output}"
                    )

            for source in sources:
                base_name = normalize_episode_title(source.stem, week_label)
                per_base = f"{week_label} - {base_name}"
                for content_type in content_types:
                    per_output = week_output_dir / f"{per_base}{output_extension(content_type, quiz_format=quiz_format)}"
                    for variant in language_variants:
                        planned_path = ensure_unique_output_path(
                            apply_path_suffix(per_output, variant["suffix"]),
                            auth_label,
                        )
                        planned_lines.append(
                            f"READING {content_type.upper()} ({variant['code'] or 'default'}): {planned_path}"
                        )
                if "Grundbog kapitel" in source.name:
                    title_prefix = brief_cfg.get("title_prefix", "[Brief]")
                    brief_base = f"{title_prefix} {week_label} - {base_name}"
                    for content_type in content_types:
                        brief_output = week_output_dir / f"{brief_base}{output_extension(content_type, quiz_format=quiz_format)}"
                        for variant in language_variants:
                            planned_path = ensure_unique_output_path(
                                apply_path_suffix(brief_output, variant["suffix"]),
                                auth_label,
                            )
                            planned_lines.append(
                                f"BRIEF {content_type.upper()} ({variant['code'] or 'default'}): {planned_path}"
                            )

            if args.dry_run:
                print(f"## {week_label}")
                for line in planned_lines:
                    print(line)
                continue

            if not missing:
                weekly_sources_file = week_output_dir / "sources_week.txt"
                weekly_sources_file.write_text(
                    "\n".join(str(p) for p in sources) + "\n",
                    encoding="utf-8",
                )
                for content_type in content_types:
                    weekly_output = week_output_dir / f"{weekly_base}{output_extension(content_type, quiz_format=quiz_format)}"
                    for variant in language_variants:
                        output_path = ensure_unique_output_path(
                            apply_path_suffix(weekly_output, variant["suffix"]),
                            auth_label,
                        )
                        skip, reason = should_skip_generation(output_path, args.skip_existing)
                        if skip:
                            print(f"Skipping generation ({reason}): {output_path}")
                            continue
                        exclude_profiles = (
                            active_cooldowns(profile_cooldowns)
                            if rotation_enabled and args.profile_cooldown > 0
                            else []
                        )
                        if exclude_profiles and exclude_profiles != last_excluded:
                            print(f"Cooling profiles this run: {', '.join(exclude_profiles)}")
                            last_excluded = exclude_profiles
                        if content_type == "audio":
                            instructions = ensure_prompt(
                                "weekly_overview", weekly_cfg.get("prompt", "")
                            )
                            audio_format = weekly_cfg.get("format", "deep-dive")
                            audio_length = weekly_cfg.get("length", "long")
                            infographic_orientation = None
                            infographic_detail = None
                            quiz_quantity_arg = None
                            quiz_difficulty_arg = None
                            quiz_format_arg = None
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
                        else:
                            instructions = ensure_prompt("quiz", quiz_cfg.get("prompt", ""))
                            audio_format = None
                            audio_length = None
                            infographic_orientation = None
                            infographic_detail = None
                            quiz_quantity_arg = quiz_quantity
                            quiz_difficulty_arg = quiz_difficulty
                            quiz_format_arg = quiz_format
                        try:
                            run_generate(
                                Path(sys.executable),
                                generator_script,
                                sources_file=weekly_sources_file,
                                source_path=None,
                                notebook_title=apply_suffix(
                                    f"Personlighedspsykologi {week_label} Alle kilder",
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
                                language=variant["code"],
                                output_path=output_path,
                                wait=args.wait,
                                skip_existing=args.skip_existing,
                                source_timeout=args.source_timeout,
                                generation_timeout=args.generation_timeout,
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
            else:
                print(f"Skipping weekly overview for {week_label} (missing readings).")

            for source in sources:
                base_name = normalize_episode_title(source.stem, week_label)
                per_base = f"{week_label} - {base_name}"
                for content_type in content_types:
                    per_output = week_output_dir / f"{per_base}{output_extension(content_type, quiz_format=quiz_format)}"
                    for variant in language_variants:
                        output_path = ensure_unique_output_path(
                            apply_path_suffix(per_output, variant["suffix"]),
                            auth_label,
                        )
                        skip, reason = should_skip_generation(output_path, args.skip_existing)
                        if skip:
                            print(f"Skipping generation ({reason}): {output_path}")
                            continue
                        exclude_profiles = (
                            active_cooldowns(profile_cooldowns)
                            if rotation_enabled and args.profile_cooldown > 0
                            else []
                        )
                        if exclude_profiles and exclude_profiles != last_excluded:
                            print(f"Cooling profiles this run: {', '.join(exclude_profiles)}")
                            last_excluded = exclude_profiles
                        if content_type == "audio":
                            instructions = ensure_prompt("per_reading", per_cfg.get("prompt", ""))
                            audio_format = per_cfg.get("format", "deep-dive")
                            audio_length = per_cfg.get("length", "default")
                            infographic_orientation = None
                            infographic_detail = None
                            quiz_quantity_arg = None
                            quiz_difficulty_arg = None
                            quiz_format_arg = None
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
                        else:
                            instructions = ensure_prompt("quiz", quiz_cfg.get("prompt", ""))
                            audio_format = None
                            audio_length = None
                            infographic_orientation = None
                            infographic_detail = None
                            quiz_quantity_arg = quiz_quantity
                            quiz_difficulty_arg = quiz_difficulty
                            quiz_format_arg = quiz_format
                        try:
                            run_generate(
                                Path(sys.executable),
                                generator_script,
                                sources_file=None,
                                source_path=source,
                                notebook_title=apply_suffix(
                                    f"Personlighedspsykologi {week_label} {base_name}",
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
                                language=variant["code"],
                                output_path=output_path,
                                wait=args.wait,
                                skip_existing=args.skip_existing,
                                source_timeout=args.source_timeout,
                                generation_timeout=args.generation_timeout,
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

                if "Grundbog kapitel" in source.name:
                    title_prefix = brief_cfg.get("title_prefix", "[Brief]")
                    brief_base = f"{title_prefix} {week_label} - {base_name}"
                    for content_type in content_types:
                        brief_output = week_output_dir / f"{brief_base}{output_extension(content_type, quiz_format=quiz_format)}"
                        for variant in language_variants:
                            output_path = ensure_unique_output_path(
                                apply_path_suffix(brief_output, variant["suffix"]),
                                auth_label,
                            )
                            skip, reason = should_skip_generation(output_path, args.skip_existing)
                            if skip:
                                print(f"Skipping generation ({reason}): {output_path}")
                                continue
                            exclude_profiles = (
                                active_cooldowns(profile_cooldowns)
                                if rotation_enabled and args.profile_cooldown > 0
                                else []
                            )
                            if exclude_profiles and exclude_profiles != last_excluded:
                                print(f"Cooling profiles this run: {', '.join(exclude_profiles)}")
                                last_excluded = exclude_profiles
                            if content_type == "audio":
                                instructions = ensure_prompt("brief", brief_cfg.get("prompt", ""))
                                audio_format = brief_cfg.get("format", "brief")
                                audio_length = None
                                infographic_orientation = None
                                infographic_detail = None
                                quiz_quantity_arg = None
                                quiz_difficulty_arg = None
                                quiz_format_arg = None
                            elif content_type == "infographic":
                                instructions = ensure_prompt(
                                    "brief_infographic", brief_infographic_cfg.get("prompt", "")
                                )
                                audio_format = None
                                audio_length = None
                                infographic_orientation = brief_infographic_cfg.get("orientation")
                                infographic_detail = brief_infographic_cfg.get("detail")
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
                                quiz_difficulty_arg = quiz_difficulty
                                quiz_format_arg = quiz_format
                            try:
                                run_generate(
                                    Path(sys.executable),
                                    generator_script,
                                    sources_file=None,
                                    source_path=source,
                                    notebook_title=apply_suffix(
                                        f"Personlighedspsykologi {week_label} [Brief] {base_name}",
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
                                    language=variant["code"],
                                    output_path=output_path,
                                    wait=args.wait,
                                    skip_existing=args.skip_existing,
                                    source_timeout=args.source_timeout,
                                    generation_timeout=args.generation_timeout,
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
            print("\nNo request logs found. Run without --wait to generate them.")

    if failures:
        print("\nFailures:")
        for item in failures:
            print(f"- {item}")
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
