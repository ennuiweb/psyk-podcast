#!/usr/bin/env python3
"""Sync Personlighedspsykologi reading files from OneDrive to droplet."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import shutil
import subprocess
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path


DEFAULT_READING_KEY = "shows/personlighedspsykologi-en/docs/reading-file-key.md"
DEFAULT_SOURCE_ROOT = (
    "/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/"
    "Mine dokumenter 💾/psykologi/Personlighedspsykologi/Readings"
)
DEFAULT_HOST = "64.226.79.109"
DEFAULT_USER = "root"
DEFAULT_SSH_KEY = "~/.ssh/digitalocean_ed25519"
DEFAULT_REMOTE_ROOT = "/var/www/readings/personlighedspsykologi"
DEFAULT_SUBJECT_SLUG = "personlighedspsykologi"
DEFAULT_EXCLUSIONS_CONFIG = "shows/personlighedspsykologi-en/reading_download_exclusions.json"

LECTURE_HEADING_RE = re.compile(r"^\*\*(?P<key>W\d{2}L\d+)\b")
READING_BULLET_RE = re.compile(r"^-\s+(?P<title>.+?)(?:\s*→\s*(?P<source>.+))?$")
MISSING_RE = re.compile(r"^MISSING:\s*", re.IGNORECASE)
BRIEF_SUFFIX_RE = re.compile(r"\s*\([^)]*\bbrief\b[^)]*\)\s*$", re.IGNORECASE)
LECTURE_DIR_RE = re.compile(r"^W0*(?P<week>\d{1,2})L0*(?P<lecture>\d+)\b", re.IGNORECASE)
SUBJECT_SLUG_RE = re.compile(r"^[a-z0-9-]+$")
READING_KEY_RE = re.compile(r"^[a-z0-9-]+$")
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
MULTISPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class ReadingEntry:
    lecture_key: str
    reading_key: str
    title: str
    source_filename: str


@dataclass(frozen=True)
class Resolution:
    entry: ReadingEntry
    source_path: Path
    target_relative: Path


def _canonical_lecture_key(value: str) -> str | None:
    match = LECTURE_DIR_RE.match(str(value or "").strip())
    if not match:
        return None
    week = int(match.group("week"))
    lecture = int(match.group("lecture"))
    return f"W{week:02d}L{lecture}"


def _normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower().replace("&", " and ")
    normalized = normalized.replace("–", "-").replace("—", "-").replace("/", " ").replace("_", " ")
    normalized = re.sub(r"\bgrundbog\s+kapitel\s+0*(\d+)\b", r"grundbog kapitel \1", normalized)
    normalized = NON_ALNUM_RE.sub(" ", normalized)
    normalized = MULTISPACE_RE.sub(" ", normalized).strip()
    normalized = re.sub(r"^w\d{1,2}l\d+\s*", "", normalized)
    return normalized.strip()


def _reading_key(lecture_key: str, reading_title: str) -> str:
    normalized = _normalize_name(reading_title)
    slug = NON_ALNUM_RE.sub("-", normalized).strip("-")[:48] or "reading"
    digest = hashlib.sha1(f"{lecture_key}|{normalized}".encode("utf-8")).hexdigest()[:8]
    return f"{lecture_key.lower()}-{slug}-{digest}"


def _clean_source_filename(value: str) -> str:
    return BRIEF_SUFFIX_RE.sub("", str(value or "").strip()).strip()


def _load_excluded_reading_keys(config_path: Path, *, subject_slug: str) -> set[str]:
    slug = str(subject_slug or "").strip().lower()
    if not config_path.exists() or not SUBJECT_SLUG_RE.match(slug):
        return set()
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise SystemExit(f"Unable to read exclusions config: {config_path}")
    if not isinstance(payload, dict):
        return set()

    excluded: set[str] = set()
    subjects = payload.get("subjects")
    if isinstance(subjects, dict):
        entry = subjects.get(slug)
        if isinstance(entry, dict):
            values = entry.get("excluded_reading_keys")
            if isinstance(values, list):
                excluded.update(
                    str(item or "").strip().lower()
                    for item in values
                    if READING_KEY_RE.match(str(item or "").strip().lower())
                )

    single_slug = str(payload.get("subject_slug") or "").strip().lower()
    single_values = payload.get("excluded_reading_keys")
    if single_slug == slug and isinstance(single_values, list):
        excluded.update(
            str(item or "").strip().lower()
            for item in single_values
            if READING_KEY_RE.match(str(item or "").strip().lower())
        )
    return excluded


def parse_reading_key(path: Path) -> list[ReadingEntry]:
    if not path.exists():
        raise SystemExit(f"Reading key not found: {path}")
    entries: list[ReadingEntry] = []
    current_lecture: str | None = None
    lecture_key_counts: dict[str, int] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        lecture_match = LECTURE_HEADING_RE.match(line)
        if lecture_match:
            current_lecture = lecture_match.group("key").upper()
            lecture_key_counts = {}
            continue
        if not current_lecture or not line.startswith("- "):
            continue

        bullet = line[2:].strip()
        if not bullet or MISSING_RE.match(bullet):
            continue
        reading_match = READING_BULLET_RE.match(line)
        if not reading_match:
            continue
        title = str(reading_match.group("title") or "").strip()
        source = _clean_source_filename(str(reading_match.group("source") or "").strip())
        if not title or not source:
            continue
        base_key = _reading_key(current_lecture, title)
        occurrence = lecture_key_counts.get(base_key, 0) + 1
        lecture_key_counts[base_key] = occurrence
        reading_key = base_key if occurrence == 1 else f"{base_key}-{occurrence}"
        entries.append(
            ReadingEntry(
                lecture_key=current_lecture,
                reading_key=reading_key,
                title=title,
                source_filename=source,
            )
        )
    return entries


def index_week_dirs(source_root: Path) -> dict[str, list[Path]]:
    if not source_root.exists() or not source_root.is_dir():
        raise SystemExit(f"Source root not found: {source_root}")
    by_lecture: dict[str, list[Path]] = {}
    for entry in sorted(source_root.iterdir(), key=lambda item: item.name.casefold()):
        if not entry.is_dir():
            continue
        lecture_key = _canonical_lecture_key(entry.name)
        if not lecture_key:
            continue
        by_lecture.setdefault(lecture_key, []).append(entry)
    return by_lecture


def _candidate_files_for_entry(entry: ReadingEntry, week_dirs: list[Path]) -> list[Path]:
    target_path = Path(entry.source_filename)
    target_suffix = target_path.suffix.lower()
    target_norm = _normalize_name(target_path.stem)
    if not target_norm:
        return []

    candidates: list[Path] = []
    for week_dir in week_dirs:
        for file_path in sorted(week_dir.rglob("*"), key=lambda item: str(item).casefold()):
            if not file_path.is_file():
                continue
            if target_suffix and file_path.suffix.lower() != target_suffix:
                continue
            candidate_norm = _normalize_name(file_path.stem)
            if not candidate_norm:
                continue
            candidates.append(file_path)

    exact = [path for path in candidates if _normalize_name(path.stem) == target_norm]
    if len(exact) == 1:
        return exact
    if len(exact) > 1:
        return exact

    target_tokens = set(target_norm.split())
    fuzzy: list[Path] = []
    for path in candidates:
        candidate_norm = _normalize_name(path.stem)
        candidate_tokens = set(candidate_norm.split())
        if target_norm in candidate_norm or candidate_norm in target_norm:
            fuzzy.append(path)
            continue
        if target_tokens and (target_tokens.issubset(candidate_tokens) or candidate_tokens.issubset(target_tokens)):
            fuzzy.append(path)
    return fuzzy


def resolve_entries(entries: list[ReadingEntry], week_dir_index: dict[str, list[Path]]) -> tuple[list[Resolution], list[str]]:
    resolved: list[Resolution] = []
    unresolved: list[str] = []
    target_registry: dict[Path, Path] = {}

    for entry in entries:
        week_dirs = week_dir_index.get(entry.lecture_key, [])
        if not week_dirs:
            unresolved.append(
                f"{entry.lecture_key} | {entry.reading_key} | {entry.title} | no source week dir"
            )
            continue
        matches = _candidate_files_for_entry(entry, week_dirs)
        unique_matches = sorted({path.resolve() for path in matches}, key=lambda item: str(item).casefold())
        if len(unique_matches) == 0:
            unresolved.append(
                f"{entry.lecture_key} | {entry.reading_key} | {entry.title} | no file match for {entry.source_filename}"
            )
            continue
        if len(unique_matches) > 1:
            match_names = ", ".join(path.name for path in unique_matches[:4])
            unresolved.append(
                f"{entry.lecture_key} | {entry.reading_key} | {entry.title} | ambiguous match for {entry.source_filename}: {match_names}"
            )
            continue

        source_path = unique_matches[0]
        target_relative = Path(entry.lecture_key) / entry.source_filename
        existing_source = target_registry.get(target_relative)
        if existing_source is not None and existing_source != source_path:
            unresolved.append(
                f"{entry.lecture_key} | {entry.reading_key} | {entry.title} | duplicate target collision for {target_relative}"
            )
            continue
        target_registry[target_relative] = source_path
        resolved.append(
            Resolution(
                entry=entry,
                source_path=source_path,
                target_relative=target_relative,
            )
        )

    return resolved, unresolved


def _run(cmd: list[str], *, dry_run: bool) -> None:
    print("Running:", " ".join(cmd))
    if dry_run:
        return
    result = subprocess.run(cmd, text=True)
    if result.returncode != 0:
        raise SystemExit(f"Command failed with exit code {result.returncode}: {' '.join(cmd)}")


def sync_to_droplet(
    resolutions: list[Resolution],
    *,
    host: str,
    user: str,
    ssh_key: str | None,
    remote_root: str,
    dry_run: bool,
) -> None:
    if not resolutions:
        raise SystemExit("No resolved readings to sync; aborting to avoid destructive rsync.")

    with tempfile.TemporaryDirectory(prefix="reading-sync-") as tmpdir:
        stage_root = Path(tmpdir)
        for item in resolutions:
            destination = stage_root / item.target_relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item.source_path, destination)

        remote_clean = remote_root.rstrip("/") or "/"
        ssh_cmd = ["ssh"]
        if ssh_key:
            ssh_cmd.extend(["-i", ssh_key])
        ssh_cmd.extend(
            [
                f"{user}@{host}",
                f"mkdir -p {shlex.quote(remote_clean)}",
            ]
        )
        _run(ssh_cmd, dry_run=dry_run)

        # Avoid carrying restrictive local ownership/mode bits to the server.
        rsync_cmd = [
            "rsync",
            "-av",
            "--delete",
            "--no-owner",
            "--no-group",
            "--chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r",
        ]
        if ssh_key:
            rsync_cmd.extend(["-e", f"ssh -i {ssh_key}"])
        rsync_cmd.extend([f"{stage_root}/", f"{user}@{host}:{remote_clean}/"])
        _run(rsync_cmd, dry_run=dry_run)

        # Ensure web-serving user can always traverse/read synced files.
        perm_cmd = [
            "ssh",
        ]
        if ssh_key:
            perm_cmd.extend(["-i", ssh_key])
        remote_quoted = shlex.quote(remote_clean)
        perm_cmd.extend(
            [
                f"{user}@{host}",
                (
                    f"chmod 755 {remote_quoted} && "
                    f"find {remote_quoted} -type d -exec chmod 755 {{}} + && "
                    f"find {remote_quoted} -type f -exec chmod 644 {{}} +"
                ),
            ]
        )
        _run(perm_cmd, dry_run=dry_run)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reading-key", default=DEFAULT_READING_KEY, help="Path to reading-file-key markdown.")
    parser.add_argument("--source-root", default=DEFAULT_SOURCE_ROOT, help="OneDrive readings source root.")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Droplet host.")
    parser.add_argument("--user", default=DEFAULT_USER, help="Droplet SSH user.")
    parser.add_argument("--ssh-key", default=DEFAULT_SSH_KEY, help="SSH private key path.")
    parser.add_argument("--remote-root", default=DEFAULT_REMOTE_ROOT, help="Remote destination root.")
    parser.add_argument(
        "--subject-slug",
        default=DEFAULT_SUBJECT_SLUG,
        help="Subject slug used for exclusion config lookup.",
    )
    parser.add_argument(
        "--exclusions-config",
        default=DEFAULT_EXCLUSIONS_CONFIG,
        help="Path to reading download exclusion config (JSON). Use empty value to disable.",
    )
    parser.add_argument("--allow-unresolved", action="store_true", help="Continue sync even when some readings are unresolved.")
    parser.add_argument("--dry-run", action="store_true", help="Print plan and commands without copying or uploading.")
    args = parser.parse_args()

    reading_key_path = Path(args.reading_key).expanduser().resolve()
    source_root = Path(args.source_root).expanduser().resolve()
    ssh_key = str(Path(args.ssh_key).expanduser()) if args.ssh_key else None

    entries = parse_reading_key(reading_key_path)
    excluded_keys: set[str] = set()
    exclusions_value = str(args.exclusions_config or "").strip()
    if exclusions_value:
        exclusions_path = Path(exclusions_value).expanduser().resolve()
        excluded_keys = _load_excluded_reading_keys(
            exclusions_path,
            subject_slug=args.subject_slug,
        )
    filtered_entries = [entry for entry in entries if entry.reading_key not in excluded_keys]

    week_index = index_week_dirs(source_root)
    resolutions, unresolved = resolve_entries(filtered_entries, week_index)

    print(f"Entries parsed: {len(entries)}")
    print(f"Excluded by config: {len(entries) - len(filtered_entries)}")
    print(f"Entries after exclusions: {len(filtered_entries)}")
    print(f"Resolved: {len(resolutions)}")
    print(f"Unresolved: {len(unresolved)}")
    if unresolved:
        for item in unresolved[:40]:
            print(f"- {item}")
        if len(unresolved) > 40:
            print(f"... and {len(unresolved) - 40} more")

    if unresolved and not args.allow_unresolved:
        raise SystemExit("Unresolved readings found; rerun with --allow-unresolved to sync only resolved files.")
    if not filtered_entries:
        print("No readings left to sync after exclusions; skipping rsync.")
        return 0

    sync_to_droplet(
        resolutions,
        host=args.host,
        user=args.user,
        ssh_key=ssh_key,
        remote_root=args.remote_root,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
