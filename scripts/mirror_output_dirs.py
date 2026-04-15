#!/usr/bin/env python3
"""Mirror NotebookLM output files into subject-specific Drive mounts."""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, Iterable, List, TextIO

PERSONLIGHEDSPSYKOLOGI_OUTPUT_ROOT_ENV_VAR = "PERSONLIGHEDSPSYKOLOGI_OUTPUT_ROOT"

SUBJECT_DEFAULTS: Dict[str, Dict[str, str]] = {
    "bioneuro": {
        "source": "notebooklm-podcast-auto/bioneuro/output",
        "dest": (
            "/Users/oskar/Library/CloudStorage/GoogleDrive-nopeeeh@gmail.com/"
            "My Drive/podcasts/bioneuro"
        ),
    },
    "personlighedspsykologi": {
        "source": "notebooklm-podcast-auto/personlighedspsykologi/output",
        "dest": (
            "/Users/oskar/Library/CloudStorage/GoogleDrive-psykku2025@gmail.com/"
            "My Drive/Personlighedspsykologi-en"
        ),
    },
}

REQUEST_JSON_TOKEN = ".request"
REQUEST_JSON_SUFFIX = ".json"
CFG_HASH_TOKEN_RE = re.compile(r"\{[^{}]*\bhash=[^{}\s]+\b[^{}]*\}")


class SyncSummary:
    def __init__(self, subject: str) -> None:
        self.subject = subject
        self.source_files = 0
        self.dest_files_seen = 0
        self.ignored_source = 0
        self.ignored_dest = 0
        self.copied = 0
        self.updated = 0
        self.unchanged = 0
        self.deleted = 0
        self.dirs_created = 0
        self.dirs_removed = 0
        self.root_created = False
        self.collisions = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--subject",
        required=True,
        choices=sorted([*SUBJECT_DEFAULTS.keys(), "all"]),
        help="Subject to mirror, or 'all' for all configured subjects.",
    )
    parser.add_argument("--source", default="", help="Optional source root override.")
    parser.add_argument("--dest", default="", help="Optional destination root override.")
    parser.add_argument("--dry-run", action="store_true", help="Show actions without writing changes.")
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete destination files that are missing in source (ignored files are never deleted).",
    )
    parser.add_argument(
        "--checksum",
        action="store_true",
        help="Use sha256 checksum comparison instead of size+mtime for change detection.",
    )
    return parser.parse_args()


def resolve_path(raw: str, repo_root: Path) -> Path:
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        return candidate
    return (repo_root / candidate).resolve()


def subject_defaults(subject: str) -> Dict[str, str]:
    defaults = dict(SUBJECT_DEFAULTS[subject])
    if subject == "personlighedspsykologi":
        output_root = str(os.getenv(PERSONLIGHEDSPSYKOLOGI_OUTPUT_ROOT_ENV_VAR) or "").strip()
        if output_root:
            defaults["source"] = output_root
    return defaults


def is_request_json(rel_path: Path) -> bool:
    lower = rel_path.name.lower()
    return lower.endswith(REQUEST_JSON_SUFFIX) and REQUEST_JSON_TOKEN in lower


def list_files(root: Path) -> tuple[Dict[Path, Path], int]:
    files: Dict[Path, Path] = {}
    ignored = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if rel.name == ".DS_Store":
            ignored += 1
            continue
        if rel.name == "quiz_json_manifest.json":
            ignored += 1
            continue
        if is_request_json(rel):
            ignored += 1
            continue
        files[rel] = path
    return files, ignored


def canonicalize_week_token(value: str) -> str:
    match = re.fullmatch(r"W(?P<week>\d{1,2})L(?P<lecture>\d+)", value, re.IGNORECASE)
    if not match:
        return value
    return f"W{int(match.group('week')):02d}L{int(match.group('lecture'))}"


def validate_canonical_week_layout(subject: str, source_files: Iterable[Path]) -> None:
    if subject != "personlighedspsykologi":
        return

    invalid: list[str] = []
    for rel in source_files:
        top_level = rel.parts[0] if rel.parts else ""
        canonical = canonicalize_week_token(top_level)
        if canonical != top_level:
            invalid.append(rel.as_posix())

    if invalid:
        preview = "\n".join(f"  - {path}" for path in invalid[:20])
        more = ""
        if len(invalid) > 20:
            more = f"\n  ... and {len(invalid) - 20} more"
        raise SystemExit(
            "Source tree contains non-canonical week directories. "
            "Normalize notebooklm-podcast-auto/personlighedspsykologi/output before mirroring.\n"
            f"{preview}{more}"
        )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def has_cfg_hash_token(path: Path) -> bool:
    return CFG_HASH_TOKEN_RE.search(path.name) is not None


def files_identical(src: Path, dest: Path, use_checksum: bool) -> bool:
    src_stat = src.stat()
    dest_stat = dest.stat()
    if src_stat.st_size != dest_stat.st_size:
        return False
    if not use_checksum and src.name == dest.name and has_cfg_hash_token(src):
        return True
    if not use_checksum and src_stat.st_mtime_ns == dest_stat.st_mtime_ns:
        return True
    if use_checksum:
        return sha256_file(src) == sha256_file(dest)
    return False


def maybe_copy(src: Path, dest: Path, dry_run: bool) -> None:
    if dry_run:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def maybe_unlink(path: Path, dry_run: bool) -> None:
    if dry_run:
        return
    path.unlink()


def remove_empty_parents(path: Path, stop_at: Path, dry_run: bool) -> int:
    removed = 0
    current = path
    while current != stop_at and current.exists():
        try:
            if any(current.iterdir()):
                break
        except OSError:
            break
        if dry_run:
            removed += 1
            current = current.parent
            continue
        try:
            current.rmdir()
        except OSError:
            break
        removed += 1
        current = current.parent
    return removed


def detect_collisions(source_files: Iterable[Path], dest_root: Path) -> List[Path]:
    collisions: List[Path] = []
    for rel in source_files:
        dest_path = dest_root / rel
        if dest_path.is_dir():
            collisions.append(dest_path)
        for parent in rel.parents:
            if parent == Path("."):
                continue
            parent_path = dest_root / parent
            if parent_path.is_file():
                collisions.append(parent_path)
    return collisions


def run_subject(
    *,
    subject: str,
    source_root: Path,
    dest_root: Path,
    dry_run: bool,
    delete: bool,
    checksum: bool,
) -> int:
    if not source_root.exists():
        print(f"Error: source path not found: {source_root}", file=sys.stderr)
        return 1
    if not source_root.is_dir():
        print(f"Error: source path is not a directory: {source_root}", file=sys.stderr)
        return 1
    if dest_root.exists() and not dest_root.is_dir():
        print(f"Error: destination path is not a directory: {dest_root}", file=sys.stderr)
        return 1

    source_files, ignored_source = list_files(source_root)
    validate_canonical_week_layout(subject, source_files.keys())
    if dest_root.exists():
        dest_files, ignored_dest = list_files(dest_root)
    else:
        dest_files, ignored_dest = {}, 0

    summary = SyncSummary(subject=subject)
    summary.source_files = len(source_files)
    summary.dest_files_seen = len(dest_files)
    summary.ignored_source = ignored_source
    summary.ignored_dest = ignored_dest

    print(f"\nSubject: {subject}")
    print(f"Source: {source_root}")
    print(f"Destination: {dest_root}")
    print(f"Ignore rule: *{REQUEST_JSON_TOKEN}*{REQUEST_JSON_SUFFIX}")
    if dry_run:
        print("Mode: dry-run")
    if delete:
        print("Delete mode: enabled")
    if checksum:
        print("Comparison mode: checksum")
    else:
        print("Comparison mode: size+mtime")

    if not dest_root.exists():
        summary.root_created = True
        summary.dirs_created += 1
        print(f"MKDIR   {dest_root}")
        if not dry_run:
            dest_root.mkdir(parents=True, exist_ok=True)

    planned_dirs: set[Path] = set()
    if not dest_root.exists():
        planned_dirs.add(dest_root)

    collisions = detect_collisions(source_files.keys(), dest_root)
    if collisions:
        unique = sorted(set(collisions))
        summary.collisions = len(unique)
        print("\nCollision(s) detected; refusing to continue:", file=sys.stderr)
        for path in unique:
            print(f"  - {path}", file=sys.stderr)
        print_subject_summary(summary, stream=sys.stderr)
        return 2

    for rel in sorted(source_files.keys(), key=lambda value: value.as_posix()):
        src = source_files[rel]
        dest = dest_root / rel
        if dest.exists():
            if dest.is_dir():
                summary.collisions += 1
                print(f"COLLIDE {dest} (destination is a directory)", file=sys.stderr)
                continue
            if files_identical(src, dest, checksum):
                summary.unchanged += 1
                continue
            summary.updated += 1
            print(f"UPDATE  {src} -> {dest}")
            maybe_copy(src, dest, dry_run)
            continue

        if not dest.parent.exists() and dest.parent not in planned_dirs:
            summary.dirs_created += 1
            print(f"MKDIR   {dest.parent}")
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
            planned_dirs.add(dest.parent)
        summary.copied += 1
        print(f"COPY    {src} -> {dest}")
        maybe_copy(src, dest, dry_run)

    if delete:
        stale_rel_paths = sorted(set(dest_files.keys()) - set(source_files.keys()), key=lambda value: value.as_posix())
        for rel in stale_rel_paths:
            stale = dest_root / rel
            summary.deleted += 1
            print(f"DELETE  {stale}")
            maybe_unlink(stale, dry_run)
            summary.dirs_removed += remove_empty_parents(stale.parent, dest_root, dry_run)

    if summary.collisions:
        print_subject_summary(summary, stream=sys.stderr)
        return 2

    print_subject_summary(summary)
    return 0


def print_subject_summary(summary: SyncSummary, stream: TextIO = sys.stdout) -> None:
    print(
        "\nSummary: "
        f"subject={summary.subject} source_files={summary.source_files} "
        f"dest_files_seen={summary.dest_files_seen} copied={summary.copied} "
        f"updated={summary.updated} unchanged={summary.unchanged} "
        f"deleted={summary.deleted} dirs_created={summary.dirs_created} "
        f"dirs_removed={summary.dirs_removed} "
        f"root_created={int(summary.root_created)} ignored_source={summary.ignored_source} "
        f"ignored_dest={summary.ignored_dest} collisions={summary.collisions}",
        file=stream,
    )


def run_all_subjects(args: argparse.Namespace, repo_root: Path) -> int:
    exit_code = 0
    for subject in sorted(SUBJECT_DEFAULTS.keys()):
        defaults = subject_defaults(subject)
        source_root = resolve_path(defaults["source"], repo_root)
        dest_root = resolve_path(defaults["dest"], repo_root)
        subject_exit = run_subject(
            subject=subject,
            source_root=source_root,
            dest_root=dest_root,
            dry_run=args.dry_run,
            delete=args.delete,
            checksum=args.checksum,
        )
        if subject_exit != 0:
            exit_code = subject_exit
    return exit_code


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]

    if args.subject == "all":
        if args.source or args.dest:
            print("Error: --source/--dest cannot be used with --subject all.", file=sys.stderr)
            return 1
        return run_all_subjects(args, repo_root)

    defaults = subject_defaults(args.subject)
    source_raw = args.source or defaults["source"]
    dest_raw = args.dest or defaults["dest"]
    source_root = resolve_path(source_raw, repo_root)
    dest_root = resolve_path(dest_raw, repo_root)

    return run_subject(
        subject=args.subject,
        source_root=source_root,
        dest_root=dest_root,
        dry_run=args.dry_run,
        delete=args.delete,
        checksum=args.checksum,
    )


if __name__ == "__main__":
    raise SystemExit(main())
