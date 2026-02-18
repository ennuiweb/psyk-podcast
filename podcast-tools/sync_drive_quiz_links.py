#!/usr/bin/env python3
"""Sync quiz HTML exports from Google Drive and update quiz_links.json."""

from __future__ import annotations

import argparse
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


def write_mapping(path: Path, mapping: Dict[str, Dict[str, str]]) -> None:
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
        help="Local folder to download quiz HTML files into.",
    )
    parser.add_argument(
        "--links-file",
        help="Override quiz_links.json path (defaults to config quiz.links_file).",
    )
    parser.add_argument(
        "--language-tag",
        default="[EN]",
        help="Only include files containing this tag (set empty to include all).",
    )
    parser.add_argument(
        "--quiz-difficulty",
        default="medium",
        choices=("easy", "medium", "hard", "any"),
        help=(
            "Only map quiz HTML files for this difficulty. "
            "Use 'any' to include all difficulties. Default: medium."
        ),
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
        "--html-mime-prefix",
        action="append",
        default=["text/"],
        help="Drive mime prefix to scan for quiz HTML files (default: text/).",
    )
    args = parser.parse_args()

    config_path = args.config
    config = load_json(config_path)
    quiz_cfg = config.get("quiz")
    if not isinstance(quiz_cfg, dict):
        raise SystemExit("Show config is missing quiz settings.")
    links_path = resolve_links_path(config_path, quiz_cfg, args.links_file)

    language_tag = args.language_tag or None
    quiz_difficulty = None if args.quiz_difficulty == "any" else args.quiz_difficulty
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
    html_files = list_drive_files(
        drive_service,
        folder_id,
        drive_id=drive_id,
        supports_all_drives=supports_all_drives,
        mime_type_filters=args.html_mime_prefix,
    )

    html_files = [
        item
        for item in html_files
        if item.get("name")
        and str(item["name"]).lower().endswith(".html")
        and matches_language(str(item["name"]), language_tag)
        and matches_quiz_difficulty(str(item["name"]), quiz_difficulty)
    ]

    if not html_files:
        print(
            "No quiz HTML files found in Drive; skipping quiz sync "
            f"(difficulty={quiz_difficulty or 'any'})."
        )
        return 0
    if not audio_files:
        print("No audio files found in Drive; skipping quiz mapping.")
        return 0

    audio_index = build_audio_index(audio_files, language_tag)
    mapping: Dict[str, Dict[str, str]] = {}
    unmatched: List[str] = []
    ambiguous: List[str] = []
    duplicate_targets: List[str] = []

    folder_metadata_cache: Dict[str, Dict[str, Any]] = {}
    folder_path_cache: Dict[str, List[str]] = {}

    if args.download_root:
        for item in html_files:
            name = str(item["name"])
            parents = item.get("parents") or []
            folder_names: List[str] = []
            if parents:
                folder_names = build_folder_path(
                    drive_service,
                    parents[0],
                    folder_metadata_cache,
                    folder_path_cache,
                    root_folder_id=folder_id,
                    supports_all_drives=supports_all_drives,
                )
            relative_parts = [*folder_names, name]
            relative_path = "/".join(relative_parts)
            destination = args.download_root / relative_path
            download_drive_file(
                drive_service,
                item["id"],
                destination,
                supports_all_drives=supports_all_drives,
            )

    for item in html_files:
        name = str(item["name"])
        key = canonical_key(Path(name).stem)
        candidates = audio_index.get(key, [])
        if len(candidates) == 0:
            unmatched.append(name)
            continue
        if len(candidates) > 1:
            ambiguous.append(name)
            continue
        audio_name = candidates[0]
        if audio_name in mapping:
            duplicate_targets.append(name)
            continue
        parents = item.get("parents") or []
        folder_names = build_folder_path(
            drive_service,
            parents[0],
            folder_metadata_cache,
            folder_path_cache,
            root_folder_id=folder_id,
            supports_all_drives=supports_all_drives,
        ) if parents else []
        relative_parts = [*folder_names, name]
        relative_path = "/".join(relative_parts)
        mapping[audio_name] = {"relative_path": relative_path, "format": "html"}

    sorted_mapping = {key: mapping[key] for key in sorted(mapping)}
    write_mapping(links_path, sorted_mapping)

    print(f"Quiz difficulty filter: {quiz_difficulty or 'any'}")
    print(f"Quiz HTML files: {len(html_files)}")
    print(f"Mapped quizzes: {len(sorted_mapping)}")
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
        print(f"Duplicate mappings: {len(duplicate_targets)}")
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
