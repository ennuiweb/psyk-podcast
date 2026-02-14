#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
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


WEEK_SELECTOR_PATTERN = re.compile(r"^(?:W)?0*(\d{1,2})(?:L0*(\d{1,2}))?$", re.IGNORECASE)
WEEK_DIR_PATTERN = re.compile(r"^W0*(\d{1,2})(?:L0*(\d{1,2}))?\b", re.IGNORECASE)
CFG_TAG_PATTERN = re.compile(
    r"(?:\s+\{[a-z0-9._:+-]+=[^{}\s]+(?:\s+[a-z0-9._:+-]+=[^{}\s]+)*\})+"
    r"(?:\s+\[[^\[\]]+\])?$",
    re.IGNORECASE,
)
MAX_FILENAME_BYTES = 255


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
        parts.append(f"download={normalized_quiz_format}")
        hash_payload["quiz_quantity"] = normalized_quiz_quantity
        hash_payload["quiz_difficulty"] = normalized_quiz_difficulty
        hash_payload["quiz_download_format"] = normalized_quiz_format

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
        help="Single week label, e.g. W01L1/1L1 (or W01/1 to include all W01L* folders).",
    )
    parser.add_argument(
        "--weeks",
        help="Comma-separated week labels, e.g. W01,W02 or 1,2",
    )
    parser.add_argument(
        "--sources-root",
        default="notebooklm-podcast-auto/personlighedspsykologi/sources",
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
    if args.config_tag_len < 1:
        raise SystemExit("--config-tag-len must be >= 1.")
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
        if len(week_dirs) > 1 and not re.fullmatch(r"(?:W)?0*\d{1,2}", week_input.upper()):
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

            planned_lines: list[str] = []
            weekly_base = f"{week_label} - Alle kilder"
            for content_type in content_types:
                weekly_output = week_output_dir / f"{weekly_base}{output_extension(content_type, quiz_format=quiz_format)}"
                for variant in language_variants:
                    if content_type == "audio":
                        planned_instructions = ensure_prompt(
                            "weekly_overview", weekly_cfg.get("prompt", "")
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
                            source_count=len(sources),
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
                            quiz_difficulty=quiz_difficulty,
                            quiz_format=quiz_format,
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
                    planned_lines.append(
                        f"WEEKLY {content_type.upper()} ({variant['code'] or 'default'}): {planned_path}"
                    )

            for source in sources:
                base_name = normalize_episode_title(source.stem, week_label)
                per_base = f"{week_label} - {base_name}"
                for content_type in content_types:
                    per_output = week_output_dir / f"{per_base}{output_extension(content_type, quiz_format=quiz_format)}"
                    for variant in language_variants:
                        if content_type == "audio":
                            planned_instructions = ensure_prompt(
                                "per_reading", per_cfg.get("prompt", "")
                            )
                            planned_tag = build_output_cfg_tag_token(
                                content_type=content_type,
                                language=variant["code"],
                                instructions=planned_instructions,
                                audio_format=per_cfg.get("format", "deep-dive"),
                                audio_length=per_cfg.get("length", "default"),
                                infographic_orientation=None,
                                infographic_detail=None,
                                quiz_quantity=None,
                                quiz_difficulty=None,
                                quiz_format=None,
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
                                quiz_difficulty=quiz_difficulty,
                                quiz_format=quiz_format,
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
                        planned_lines.append(
                            f"READING {content_type.upper()} ({variant['code'] or 'default'}): {planned_path}"
                        )
                if "Grundbog kapitel" in source.name:
                    title_prefix = brief_cfg.get("title_prefix", "[Brief]")
                    brief_base = f"{title_prefix} {week_label} - {base_name}"
                    for content_type in content_types:
                        brief_output = week_output_dir / f"{brief_base}{output_extension(content_type, quiz_format=quiz_format)}"
                        for variant in language_variants:
                            if content_type == "audio":
                                planned_instructions = ensure_prompt("brief", brief_cfg.get("prompt", ""))
                                planned_tag = build_output_cfg_tag_token(
                                    content_type=content_type,
                                    language=variant["code"],
                                    instructions=planned_instructions,
                                    audio_format=brief_cfg.get("format", "brief"),
                                    audio_length=None,
                                    infographic_orientation=None,
                                    infographic_detail=None,
                                    quiz_quantity=None,
                                    quiz_difficulty=None,
                                    quiz_format=None,
                                    source_count=None,
                                hash_len=args.config_tag_len,
                                )
                            elif content_type == "infographic":
                                planned_instructions = ensure_prompt(
                                    "brief_infographic", brief_infographic_cfg.get("prompt", "")
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
                                    quiz_difficulty=quiz_difficulty,
                                    quiz_format=quiz_format,
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
                            planned_lines.append(
                                f"BRIEF {content_type.upper()} ({variant['code'] or 'default'}): {planned_path}"
                            )

            if args.dry_run:
                print(f"## {week_label}")
                for line in planned_lines:
                    print(line)
                continue

            for content_type in content_types:
                weekly_output = week_output_dir / f"{weekly_base}{output_extension(content_type, quiz_format=quiz_format)}"
                for variant in language_variants:
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
                            source_count=len(sources),
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
                    try:
                        run_generate(
                            Path(sys.executable),
                            generator_script,
                            sources_file=None,
                            source_path=None,
                            source_paths=sources,
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

            for source in sources:
                base_name = normalize_episode_title(source.stem, week_label)
                per_base = f"{week_label} - {base_name}"
                for content_type in content_types:
                    per_output = week_output_dir / f"{per_base}{output_extension(content_type, quiz_format=quiz_format)}"
                    for variant in language_variants:
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

                if "Grundbog kapitel" in source.name:
                    title_prefix = brief_cfg.get("title_prefix", "[Brief]")
                    brief_base = f"{title_prefix} {week_label} - {base_name}"
                    for content_type in content_types:
                        brief_output = week_output_dir / f"{brief_base}{output_extension(content_type, quiz_format=quiz_format)}"
                        for variant in language_variants:
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
