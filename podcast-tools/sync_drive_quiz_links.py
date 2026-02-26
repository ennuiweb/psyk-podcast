#!/usr/bin/env python3
"""Sync quiz JSON exports from Google Drive and update quiz_links.json."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive"]
RETRYABLE_STATUS_CODES = {500, 502, 503, 504, 429}
RETRYABLE_REASONS = {
    "internalError",
    "backendError",
    "rateLimitExceeded",
    "userRateLimitExceeded",
}
WEEK_TOKEN_RE = re.compile(r"\bW(?P<week>\d{1,2})L(?P<lecture>\d+)\b", re.IGNORECASE)
CFG_TAG_RE = re.compile(
    r"(?:\s+\{[a-z0-9._:+-]+=[^{}\s]+(?:\s+[a-z0-9._:+-]+=[^{}\s]+)*\})+"
    r"(?:\s+\[[^\[\]]+\])?$",
    re.IGNORECASE,
)
QUIZ_DIFFICULTY_RE = re.compile(
    r"\{[^{}]*\btype=quiz\b[^{}]*\bdifficulty=(?P<difficulty>[a-z0-9._:+-]+)\b[^{}]*\}",
    re.IGNORECASE,
)
QUIZ_TYPE_RE = re.compile(r"\{[^{}]*\btype=quiz\b[^{}]*\}", re.IGNORECASE)
DUPLICATE_WEEK_PREFIX_RE = re.compile(r"^(W\d{2}L\d+)\s*-\s*\1\b", re.IGNORECASE)
MISSING_TOKEN_RE = re.compile(r"\bMISSING\b", re.IGNORECASE)
SUBJECT_SLUG_RE = re.compile(r"^[a-z0-9-]+$")
QUIZ_DIFFICULTY_SORT_ORDER = {"easy": 0, "medium": 1, "hard": 2}
QUIZ_PRIMARY_DIFFICULTY_SORT_ORDER = {"medium": 0, "easy": 1, "hard": 2}


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_drive_service(credentials_path: Path):
    credentials = service_account.Credentials.from_service_account_file(
        str(credentials_path), scopes=SCOPES
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def _should_retry_http_error(exc: HttpError) -> bool:
    status = getattr(exc.resp, "status", None)
    if status in RETRYABLE_STATUS_CODES:
        return True
    try:
        content = exc.content.decode("utf-8", errors="ignore") if isinstance(exc.content, bytes) else exc.content
        payload = json.loads(content or "")
    except (TypeError, ValueError, UnicodeDecodeError):
        return False
    details = payload.get("error") or {}
    if details.get("code") in RETRYABLE_STATUS_CODES:
        return True
    for error in details.get("errors", []):
        if error.get("reason") in RETRYABLE_REASONS:
            return True
    return False


def _execute_with_retry(request, *, max_attempts: int = 5, base_delay: float = 1.0):
    for attempt in range(1, max_attempts + 1):
        try:
            return request.execute()
        except HttpError as exc:
            if attempt == max_attempts or not _should_retry_http_error(exc):
                raise
            sleep_for = min(base_delay * (2 ** (attempt - 1)), 30.0)
            time.sleep(sleep_for)


def _drive_list(
    service,
    *,
    query: str,
    fields: str,
    drive_id: Optional[str],
    supports_all_drives: bool,
) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    page_token: Optional[str] = None
    while True:
        params: Dict[str, Any] = {
            "q": query,
            "spaces": "drive",
            "pageToken": page_token,
            "pageSize": 100,
            "fields": fields,
            "orderBy": "createdTime desc",
        }
        if supports_all_drives or drive_id:
            params.update(
                {
                    "supportsAllDrives": True,
                    "includeItemsFromAllDrives": True,
                }
            )
        if drive_id:
            params.update({"driveId": drive_id, "corpora": "drive"})
        response = _execute_with_retry(service.files().list(**params))
        entries.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return entries


def _build_mime_query(filters: Optional[Iterable[str]]) -> str:
    terms = [term for term in (filters or []) if term]
    if not terms:
        return "mimeType != 'application/vnd.google-apps.folder'"
    clauses: List[str] = []
    for term in terms:
        sanitized = term.replace("'", "\\'")
        if term.endswith("/"):
            clauses.append(f"mimeType contains '{sanitized}'")
        else:
            clauses.append(f"mimeType = '{sanitized}'")
    return "(" + " or ".join(clauses) + ")"


def list_drive_files(
    service,
    folder_id: str,
    *,
    drive_id: Optional[str] = None,
    supports_all_drives: bool = False,
    mime_type_filters: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    files: List[Dict[str, Any]] = []
    pending: List[str] = [folder_id]
    seen: set[str] = set()
    file_fields = "nextPageToken, files(id,name,mimeType,parents,modifiedTime,createdTime)"
    folder_fields = "nextPageToken, files(id,name)"
    mime_clause = _build_mime_query(mime_type_filters)

    while pending:
        current_folder = pending.pop(0)
        if current_folder in seen:
            continue
        seen.add(current_folder)

        query = f"'{current_folder}' in parents and {mime_clause} and trashed = false"
        files.extend(
            _drive_list(
                service,
                query=query,
                fields=file_fields,
                drive_id=drive_id,
                supports_all_drives=supports_all_drives,
            )
        )

        folder_query = (
            f"'{current_folder}' in parents and mimeType = 'application/vnd.google-apps.folder' "
            "and trashed = false"
        )
        subfolders = _drive_list(
            service,
            query=folder_query,
            fields=folder_fields,
            drive_id=drive_id,
            supports_all_drives=supports_all_drives,
        )
        for folder in subfolders:
            folder_id_value = folder.get("id")
            if folder_id_value and folder_id_value not in seen:
                pending.append(folder_id_value)

    return files


def get_folder_metadata(
    service,
    folder_id: str,
    cache: Dict[str, Dict[str, Any]],
    *,
    supports_all_drives: bool,
) -> Dict[str, Any]:
    if folder_id in cache:
        return cache[folder_id]
    params: Dict[str, Any] = {"fileId": folder_id, "fields": "id,name,parents"}
    if supports_all_drives:
        params["supportsAllDrives"] = True
    metadata = _execute_with_retry(service.files().get(**params))
    cache[folder_id] = metadata
    return metadata


def build_folder_path(
    service,
    folder_id: str,
    cache: Dict[str, Dict[str, Any]],
    path_cache: Dict[str, List[str]],
    *,
    root_folder_id: str,
    supports_all_drives: bool,
) -> List[str]:
    if folder_id == root_folder_id:
        return []
    if folder_id in path_cache:
        return path_cache[folder_id]

    metadata = get_folder_metadata(
        service,
        folder_id,
        cache,
        supports_all_drives=supports_all_drives,
    )
    parents = metadata.get("parents") or []
    if parents:
        parent_id = parents[0]
        if parent_id == root_folder_id:
            path = [metadata["name"]]
        else:
            parent_path = build_folder_path(
                service,
                parent_id,
                cache,
                path_cache,
                root_folder_id=root_folder_id,
                supports_all_drives=supports_all_drives,
            )
            path = parent_path + [metadata["name"]]
    else:
        path = [metadata["name"]]

    path_cache[folder_id] = path
    return path


def download_drive_file(
    service,
    file_id: str,
    destination: Path,
    *,
    supports_all_drives: bool,
) -> None:
    request = service.files().get_media(fileId=file_id, supportsAllDrives=supports_all_drives)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()


def normalize_week_tokens(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        week = match.group("week").zfill(2)
        lecture = match.group("lecture")
        return f"W{week}L{lecture}"

    return WEEK_TOKEN_RE.sub(repl, text)


def strip_cfg_tag_suffix(text: str) -> str:
    return CFG_TAG_RE.sub("", text).strip()


def extract_quiz_difficulty(value: str) -> str | None:
    match = QUIZ_DIFFICULTY_RE.search(value)
    if not match:
        return None
    difficulty = match.group("difficulty").strip().lower()
    return difficulty or None


def matches_quiz_difficulty(value: str, expected: str | None) -> bool:
    if not expected:
        return True
    actual = extract_quiz_difficulty(value)
    if actual is None:
        # Backward-compatibility: historical quiz exports were implicitly medium.
        return expected == "medium"
    return actual == expected


def has_quiz_cfg_tag(value: str) -> bool:
    return QUIZ_TYPE_RE.search(value) is not None


def is_excluded_quiz_json_name(name: str) -> bool:
    normalized = name.strip().lower()
    if ".html.request" in normalized and normalized.endswith(".json"):
        return True
    if normalized == "quiz_json_manifest.json":
        return True
    return normalized.endswith(("-manifest.json", "_manifest.json"))


def to_public_quiz_relative_path(source_relative_path: str) -> str:
    return str(Path(source_relative_path).with_suffix(".html")).replace("\\", "/")


def to_source_quiz_json_relative_path(public_relative_path: str) -> str:
    return str(Path(public_relative_path).with_suffix(".json")).replace("\\", "/")


def canonical_key(stem: str) -> str:
    name = stem.replace("–", "-").replace("—", "-")
    name = strip_cfg_tag_suffix(name)
    name = normalize_week_tokens(name)
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"\.{2,}", ".", name)
    prefix = ""
    if name.lower().startswith("[brief]"):
        prefix = "[Brief] "
        name = name[len("[brief]") :].lstrip()
    match = re.match(r"^(W\d{2}L\d+)\b(?:\s*-\s*)?(.*)$", name, re.IGNORECASE)
    if not match:
        return f"{prefix}{name}".strip()
    week = match.group(1).upper()
    rest = match.group(2).strip()
    if rest:
        rest = re.sub(
            rf"^{re.escape(week)}\b(?:\s*-\s*)?",
            "",
            rest,
            flags=re.IGNORECASE,
        ).strip()
    if rest:
        return f"{prefix}{week} - {rest}".strip()
    return f"{prefix}{week}".strip()


def audio_candidate_rank(stem: str) -> tuple[int, int, int, str]:
    name = stem.replace("–", "-").replace("—", "-")
    name = strip_cfg_tag_suffix(name)
    name = normalize_week_tokens(name)
    name = re.sub(r"\s+", " ", name).strip()
    name = re.sub(r"\.{2,}", ".", name)
    if name.lower().startswith("[brief]"):
        name = name[len("[brief]") :].lstrip()
    duplicate_week_prefix = 1 if DUPLICATE_WEEK_PREFIX_RE.match(name) else 0
    has_missing_token = 1 if MISSING_TOKEN_RE.search(name) else 0
    return (duplicate_week_prefix, has_missing_token, len(name), name.casefold())


def select_audio_candidate(candidates: List[str]) -> str | None:
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    ranked = [
        (audio_candidate_rank(Path(candidate_name).stem), candidate_name)
        for candidate_name in candidates
    ]
    ranked.sort(key=lambda item: (item[0], item[1].casefold()))
    best_rank = ranked[0][0]
    best = [candidate_name for rank, candidate_name in ranked if rank == best_rank]
    if len(best) == 1:
        return best[0]
    return None


def normalize_quiz_difficulty(value: str | None) -> str:
    difficulty = (value or "").strip().lower()
    return difficulty or "medium"


def build_flat_quiz_relative_path(
    audio_name: str,
    difficulty: str | None,
    flat_id_len: int,
) -> tuple[str, str]:
    if flat_id_len < 1:
        raise ValueError("--flat-id-len must be >= 1.")
    normalized_difficulty = normalize_quiz_difficulty(difficulty)
    seed = f"{canonical_key(Path(audio_name).stem)}|{normalized_difficulty}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    return f"{digest[:flat_id_len]}.html", seed


def ensure_unique_flat_quiz_relative_path(
    registry: Dict[str, str],
    relative_path: str,
    seed: str,
    *,
    context: str,
) -> None:
    existing = registry.get(relative_path)
    if existing is None:
        registry[relative_path] = seed
        return
    if existing != seed:
        raise ValueError(
            f"Short quiz ID collision for '{relative_path}' while mapping '{context}'. "
            "Increase --flat-id-len."
        )


def quiz_link_sort_key(link: Dict[str, str]) -> tuple[int, str, str]:
    difficulty = normalize_quiz_difficulty(link.get("difficulty"))
    rel_path = str(link.get("relative_path") or "")
    return (QUIZ_DIFFICULTY_SORT_ORDER.get(difficulty, 99), difficulty, rel_path)


def select_primary_quiz_link(links: List[Dict[str, str]]) -> Dict[str, str] | None:
    if not links:
        return None
    ranked = sorted(
        links,
        key=lambda link: (
            QUIZ_PRIMARY_DIFFICULTY_SORT_ORDER.get(
                normalize_quiz_difficulty(link.get("difficulty")),
                99,
            ),
            quiz_link_sort_key(link),
        ),
    )
    return ranked[0] if ranked else None


def build_mapping_entry(links: List[Dict[str, str]], subject_slug: str) -> Dict[str, Any] | None:
    if not links:
        return None
    normalized_links: List[Dict[str, str]] = []
    seen_difficulties: set[str] = set()
    for raw_link in sorted(links, key=quiz_link_sort_key):
        rel_path = str(raw_link.get("relative_path") or "").strip()
        if not rel_path:
            continue
        difficulty = normalize_quiz_difficulty(raw_link.get("difficulty"))
        if difficulty in seen_difficulties:
            continue
        seen_difficulties.add(difficulty)
        normalized_links.append(
            {
                "relative_path": rel_path,
                "format": str(raw_link.get("format") or "html"),
                "difficulty": difficulty,
                "subject_slug": subject_slug,
            }
        )
    if not normalized_links:
        return None
    primary = select_primary_quiz_link(normalized_links)
    if not primary:
        return None
    mapping_entry: Dict[str, Any] = {
        "relative_path": primary["relative_path"],
        "format": primary["format"],
        "difficulty": primary["difficulty"],
        "subject_slug": subject_slug,
    }
    if len(normalized_links) > 1:
        mapping_entry["links"] = normalized_links
    return mapping_entry


def matches_language(name: str, tag: Optional[str]) -> bool:
    if not tag:
        return True
    return tag in name


def build_audio_index(
    audio_files: List[Dict[str, Any]],
    language_tag: Optional[str],
) -> Dict[str, List[str]]:
    index: Dict[str, List[str]] = {}
    for item in audio_files:
        name = item.get("name")
        if not name or not matches_language(name, language_tag):
            continue
        key = canonical_key(Path(name).stem)
        index.setdefault(key, []).append(name)
    return index


def write_mapping(path: Path, mapping: Dict[str, Dict[str, Any]]) -> None:
    payload = {"by_name": mapping}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)


def run_rsync(
    source_root: Path,
    remote_root: str,
    host: str,
    user: str,
    ssh_key: Optional[str],
) -> None:
    src = str(source_root) + "/"
    dest = f"{user}@{host}:{remote_root.rstrip('/')}/"
    cmd = [
        "rsync",
        "-av",
        "--delete",
        "--chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r",
        "--include",
        "*/",
        "--include",
        "*.html",
        "--include",
        "*.json",
        "--exclude",
        "*",
    ]
    if ssh_key:
        cmd.extend(["-e", f"ssh -i {ssh_key}"])
    cmd.extend([src, dest])
    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, text=True)
    if result.returncode != 0:
        raise SystemExit(f"rsync failed with exit code {result.returncode}")


def resolve_links_path(config_path: Path, quiz_cfg: Dict[str, Any], override: Optional[str]) -> Path:
    if override:
        override_path = Path(override).expanduser()
        if override_path.is_absolute():
            return override_path
        candidates = [override_path, config_path.parent / override_path]
        resolved = next((path for path in candidates if path.exists()), None)
        if resolved is not None:
            return resolved.resolve()
        if str(override_path).startswith("shows/"):
            return override_path.resolve()
        return (config_path.parent / override_path).resolve()
    links_file = quiz_cfg.get("links_file")
    if not links_file:
        raise SystemExit("quiz.links_file is missing in the show config.")
    links_path = Path(str(links_file)).expanduser()
    if links_path.is_absolute():
        return links_path
    candidates = [links_path, config_path.parent / links_path]
    resolved = next((path for path in candidates if path.exists()), None)
    if resolved is not None:
        return resolved.resolve()
    if str(links_path).startswith("shows/"):
        return links_path.resolve()
    return (config_path.parent / links_path).resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path, help="Show config JSON path.")
    parser.add_argument(
        "--download-root",
        type=Path,
        help="Local folder to download quiz JSON files into.",
    )
    parser.add_argument(
        "--links-file",
        help="Override quiz_links.json path (defaults to config quiz.links_file).",
    )
    parser.add_argument(
        "--subject-slug",
        help=(
            "Subject slug for quiz_links entries. "
            "Defaults to quiz.subject_slug in config, otherwise personlighedspsykologi."
        ),
    )
    parser.add_argument(
        "--language-tag",
        default="[EN]",
        help="Only include files containing this tag (set empty to include all).",
    )
    parser.add_argument(
        "--quiz-difficulty",
        default="any",
        choices=("easy", "medium", "hard", "any"),
        help=(
            "Only map quiz JSON files for this difficulty. "
            "Use 'any' to include all difficulties. Default: any."
        ),
    )
    parser.add_argument(
        "--quiz-path-mode",
        default="flat-id",
        choices=("legacy", "flat-id"),
        help=(
            "Quiz relative path mode. "
            "'legacy' keeps folder/filename paths; 'flat-id' maps to deterministic IDs."
        ),
    )
    parser.add_argument(
        "--flat-id-len",
        type=int,
        default=8,
        help="Hex length for deterministic flat quiz IDs in flat-id mode (default: 8).",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload downloaded quizzes to the droplet.",
    )
    parser.add_argument(
        "--host",
        default="64.226.79.109",
        help="Droplet host.",
    )
    parser.add_argument(
        "--user",
        default="root",
        help="Droplet SSH user.",
    )
    parser.add_argument(
        "--ssh-key",
        help="SSH key path for rsync (required for upload).",
    )
    parser.add_argument(
        "--remote-root",
        default="/var/www/quizzes/personlighedspsykologi",
        help="Droplet directory for quizzes.",
    )
    parser.add_argument(
        "--json-mime-prefix",
        action="append",
        default=["application/json"],
        help="Drive mime type or prefix to scan for quiz JSON files (default: application/json).",
    )
    args = parser.parse_args()

    config_path = args.config
    config = load_json(config_path)
    quiz_cfg = config.get("quiz")
    if not isinstance(quiz_cfg, dict):
        raise SystemExit("Show config is missing quiz settings.")
    configured_subject_slug = str(quiz_cfg.get("subject_slug") or "").strip().lower()
    subject_slug = str(args.subject_slug or configured_subject_slug or "personlighedspsykologi").strip().lower()
    if not SUBJECT_SLUG_RE.match(subject_slug):
        raise SystemExit("--subject-slug must match ^[a-z0-9-]+$")
    links_path = resolve_links_path(config_path, quiz_cfg, args.links_file)

    language_tag = args.language_tag or None
    quiz_difficulty = None if args.quiz_difficulty == "any" else args.quiz_difficulty
    if args.flat_id_len < 1:
        raise SystemExit("--flat-id-len must be >= 1.")
    service_account_path = Path(config["service_account_file"])
    drive_service = build_drive_service(service_account_path)
    folder_id = config["drive_folder_id"]
    drive_id = config.get("shared_drive_id") or None
    supports_all_drives = bool(config.get("include_items_from_all_drives", drive_id is not None))

    audio_files = list_drive_files(
        drive_service,
        folder_id,
        drive_id=drive_id,
        supports_all_drives=supports_all_drives,
        mime_type_filters=["audio/"],
    )
    json_files = list_drive_files(
        drive_service,
        folder_id,
        drive_id=drive_id,
        supports_all_drives=supports_all_drives,
        mime_type_filters=args.json_mime_prefix,
    )

    json_files = [
        item
        for item in json_files
        if item.get("name")
        and str(item["name"]).lower().endswith(".json")
        and not is_excluded_quiz_json_name(str(item["name"]))
        and has_quiz_cfg_tag(Path(str(item["name"])).stem)
        and matches_language(str(item["name"]), language_tag)
        and matches_quiz_difficulty(str(item["name"]), quiz_difficulty)
    ]

    if not json_files:
        raise SystemExit(
            "No valid quiz JSON files found in Drive "
            f"(difficulty={quiz_difficulty or 'any'})."
        )
    if not audio_files:
        print("No audio files found in Drive; skipping quiz mapping.")
        return 0

    audio_index = build_audio_index(audio_files, language_tag)
    mapping_links: Dict[str, List[Dict[str, str]]] = {}
    unmatched: List[str] = []
    ambiguous: List[str] = []
    duplicate_targets: List[str] = []
    flat_id_registry: Dict[str, str] = {}
    download_jobs: Dict[str, str] = {}

    folder_metadata_cache: Dict[str, Dict[str, Any]] = {}
    folder_path_cache: Dict[str, List[str]] = {}

    for item in json_files:
        name = str(item["name"])
        difficulty = normalize_quiz_difficulty(extract_quiz_difficulty(name))
        key = canonical_key(Path(name).stem)
        candidates = audio_index.get(key, [])
        if len(candidates) == 0:
            unmatched.append(name)
            continue
        selected_candidate = select_audio_candidate(candidates)
        if selected_candidate is None:
            ambiguous.append(name)
            continue
        audio_name = selected_candidate
        if args.quiz_path_mode == "flat-id":
            try:
                relative_path, flat_seed = build_flat_quiz_relative_path(
                    audio_name,
                    difficulty,
                    args.flat_id_len,
                )
                ensure_unique_flat_quiz_relative_path(
                    flat_id_registry,
                    relative_path,
                    flat_seed,
                    context=name,
                )
            except ValueError as exc:
                raise SystemExit(str(exc))
        else:
            parents = item.get("parents") or []
            folder_names = build_folder_path(
                drive_service,
                parents[0],
                folder_metadata_cache,
                folder_path_cache,
                root_folder_id=folder_id,
                supports_all_drives=supports_all_drives,
            ) if parents else []
            source_relative_parts = [*folder_names, name]
            source_relative_path = "/".join(source_relative_parts)
            relative_path = to_public_quiz_relative_path(source_relative_path)
        links = mapping_links.setdefault(audio_name, [])
        if any(normalize_quiz_difficulty(link.get("difficulty")) == difficulty for link in links):
            duplicate_targets.append(name)
            continue
        links.append(
            {
                "relative_path": relative_path,
                "format": "html",
                "difficulty": difficulty,
            }
        )
        if args.download_root:
            file_id = str(item["id"])
            source_relative_path = to_source_quiz_json_relative_path(relative_path)
            existing_file_id = download_jobs.get(source_relative_path)
            if existing_file_id is not None and existing_file_id != file_id:
                raise SystemExit(
                    f"Multiple Drive files map to '{source_relative_path}' "
                    f"({existing_file_id} vs {file_id})."
                )
            download_jobs[source_relative_path] = file_id

    sorted_mapping: Dict[str, Dict[str, Any]] = {}
    mapped_quiz_links = 0
    for key in sorted(mapping_links):
        mapping_entry = build_mapping_entry(mapping_links[key], subject_slug)
        if not mapping_entry:
            continue
        sorted_mapping[key] = mapping_entry
        links = mapping_entry.get("links")
        if isinstance(links, list):
            mapped_quiz_links += len(links)
        else:
            mapped_quiz_links += 1
    write_mapping(links_path, sorted_mapping)

    if args.download_root:
        for relative_path in sorted(download_jobs):
            destination = args.download_root / relative_path
            download_drive_file(
                drive_service,
                download_jobs[relative_path],
                destination,
                supports_all_drives=supports_all_drives,
            )

    print(f"Quiz difficulty filter: {quiz_difficulty or 'any'}")
    print(f"Quiz JSON files: {len(json_files)}")
    print(f"Mapped episode quizzes: {len(sorted_mapping)}")
    print(f"Mapped quiz links: {mapped_quiz_links}")
    if unmatched:
        print(f"Unmatched quizzes: {len(unmatched)}")
        for name in unmatched[:20]:
            print(f"- {name}")
        if len(unmatched) > 20:
            print(f"... and {len(unmatched) - 20} more")
    if ambiguous:
        print(f"Ambiguous quizzes: {len(ambiguous)}")
        for name in ambiguous[:20]:
            print(f"- {name}")
        if len(ambiguous) > 20:
            print(f"... and {len(ambiguous) - 20} more")
    if duplicate_targets:
        print(f"Duplicate quiz difficulty mappings: {len(duplicate_targets)}")
        for name in duplicate_targets[:20]:
            print(f"- {name}")
        if len(duplicate_targets) > 20:
            print(f"... and {len(duplicate_targets) - 20} more")

    if args.upload:
        if not args.download_root:
            raise SystemExit("--upload requires --download-root to be set.")
        if not args.ssh_key:
            print("Warning: --upload requested but no --ssh-key provided; skipping upload.")
        else:
            run_rsync(
                source_root=args.download_root,
                remote_root=args.remote_root,
                host=args.host,
                user=args.user,
                ssh_key=args.ssh_key,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
