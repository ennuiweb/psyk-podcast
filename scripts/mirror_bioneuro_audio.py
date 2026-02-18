#!/usr/bin/env python3
"""Mirror Bioneuro audio files from OneDrive Readings into Google Drive mount."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


DEFAULT_SOURCE = (
    "/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/"
    "Mine dokumenter 💾/psykologi/Bioneuro/Readings"
)
DEFAULT_DEST = (
    "/Users/oskar/Library/CloudStorage/GoogleDrive-nopeeeh@gmail.com/"
    "My Drive/podcasts/bioneuro"
)
DEFAULT_EXTS = ".mp3,.m4a,.wav,.aac,.flac"
WEEK_DIR_RE = re.compile(r"^W\d+", re.IGNORECASE)


@dataclass
class Candidate:
    src: Path
    dest: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="Readings source root.")
    parser.add_argument("--dest", default=DEFAULT_DEST, help="Mirror destination root.")
    parser.add_argument(
        "--exts",
        default=DEFAULT_EXTS,
        help="Comma-separated extensions to include (default: .mp3,.m4a,.wav,.aac,.flac).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show actions without copying.")
    return parser.parse_args()


def normalize_exts(raw: str) -> Tuple[str, ...]:
    exts: List[str] = []
    for part in raw.split(","):
        token = part.strip().lower()
        if not token:
            continue
        if not token.startswith("."):
            token = f".{token}"
        exts.append(token)
    deduped = tuple(dict.fromkeys(exts))
    if not deduped:
        raise ValueError("No valid extensions provided.")
    return deduped


def is_under_week_folder(rel_path: Path) -> bool:
    parts = rel_path.parts
    if not parts:
        return False
    return bool(WEEK_DIR_RE.match(parts[0]))


def build_candidates(source_root: Path, dest_root: Path, exts: Iterable[str]) -> Tuple[List[Candidate], int]:
    ext_set = set(exts)
    scanned = 0
    candidates: List[Candidate] = []
    for src in source_root.rglob("*"):
        if not src.is_file():
            continue
        scanned += 1
        rel = src.relative_to(source_root)
        if not is_under_week_folder(rel):
            continue
        if src.suffix.lower() not in ext_set:
            continue
        week_dir = rel.parts[0]
        dest = dest_root / week_dir / src.name
        candidates.append(Candidate(src=src, dest=dest))
    return candidates, scanned


def find_collisions(candidates: Iterable[Candidate]) -> Dict[Path, List[Path]]:
    collisions: Dict[Path, List[Path]] = {}
    by_dest: Dict[Path, List[Path]] = {}
    for item in candidates:
        by_dest.setdefault(item.dest, []).append(item.src)
    for dest, sources in by_dest.items():
        unique_sources = sorted(set(sources))
        if len(unique_sources) > 1:
            collisions[dest] = unique_sources
    return collisions


def files_identical(src: Path, dest: Path) -> bool:
    src_stat = src.stat()
    dest_stat = dest.stat()
    if src_stat.st_size != dest_stat.st_size:
        return False
    return src_stat.st_mtime_ns == dest_stat.st_mtime_ns


def copy_file(src: Path, dest: Path, dry_run: bool) -> None:
    if dry_run:
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def main() -> int:
    args = parse_args()
    source_root = Path(args.source).expanduser()
    dest_root = Path(args.dest).expanduser()

    try:
        exts = normalize_exts(args.exts)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not source_root.exists():
        print(f"Error: source path not found: {source_root}", file=sys.stderr)
        return 1
    if not source_root.is_dir():
        print(f"Error: source path is not a directory: {source_root}", file=sys.stderr)
        return 1
    if not dest_root.exists() and not args.dry_run:
        try:
            dest_root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(f"Error: failed to create destination root {dest_root}: {exc}", file=sys.stderr)
            return 1

    print(f"Source: {source_root}")
    print(f"Destination: {dest_root}")
    print(f"Extensions: {', '.join(exts)}")
    if args.dry_run:
        print("Mode: dry-run")

    candidates, scanned = build_candidates(source_root, dest_root, exts)
    collisions = find_collisions(candidates)
    if collisions:
        print("\nCollision(s) detected; refusing to continue:", file=sys.stderr)
        for dest, sources in sorted(collisions.items(), key=lambda pair: str(pair[0])):
            print(f"  - {dest}", file=sys.stderr)
            for src in sources:
                print(f"      <- {src}", file=sys.stderr)
        print(f"\nSummary: scanned={scanned} eligible={len(candidates)} collisions={len(collisions)}", file=sys.stderr)
        return 2

    copied = 0
    updated = 0
    unchanged = 0

    for item in candidates:
        if not item.dest.exists():
            copied += 1
            print(f"COPY    {item.src} -> {item.dest}")
            copy_file(item.src, item.dest, args.dry_run)
            continue

        if files_identical(item.src, item.dest):
            unchanged += 1
            continue

        updated += 1
        print(f"UPDATE  {item.src} -> {item.dest}")
        copy_file(item.src, item.dest, args.dry_run)

    skipped = scanned - len(candidates)
    print(
        "\nSummary: "
        f"scanned={scanned} eligible={len(candidates)} copied={copied} "
        f"updated={updated} unchanged={unchanged} collisions=0 skipped={skipped}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
