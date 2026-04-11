#!/usr/bin/env python3
"""Mirror Personlighedspsykologi output subdirectories into Google Drive mount."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List


DEFAULT_SOURCE = "notebooklm-podcast-auto/personlighedspsykologi/output"
DEFAULT_DEST = (
    "/Users/oskar/Library/CloudStorage/GoogleDrive-psykku2025@gmail.com/"
    "My Drive/Personlighedspsykologi-en"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=DEFAULT_SOURCE, help="Output source root.")
    parser.add_argument("--dest", default=DEFAULT_DEST, help="Mirror destination root.")
    parser.add_argument("--dry-run", action="store_true", help="Show actions without creating directories.")
    return parser.parse_args()


def resolve_path(raw: str, repo_root: Path) -> Path:
    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        return candidate
    return (repo_root / candidate).resolve()


def list_relative_dirs(root: Path) -> List[Path]:
    directories: List[Path] = []
    for path in root.rglob("*"):
        if path.is_dir():
            directories.append(path.relative_to(root))
    directories.sort(key=lambda value: value.as_posix())
    return directories


def canonicalize_week_token(value: str) -> str:
    match = re.fullmatch(r"W(?P<week>\d{1,2})L(?P<lecture>\d+)", value, re.IGNORECASE)
    if not match:
        return value
    return f"W{int(match.group('week')):02d}L{int(match.group('lecture'))}"


def validate_canonical_layout(relative_dirs: List[Path]) -> None:
    invalid = []
    for rel in relative_dirs:
        top_level = rel.parts[0] if rel.parts else ""
        if top_level and canonicalize_week_token(top_level) != top_level:
            invalid.append(rel.as_posix())
    if invalid:
        preview = "\n".join(f"  - {path}" for path in invalid[:20])
        more = f"\n  ... and {len(invalid) - 20} more" if len(invalid) > 20 else ""
        raise SystemExit(
            "Source tree contains non-canonical week directories. Normalize it before mirroring.\n"
            f"{preview}{more}"
        )


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    source_root = resolve_path(args.source, repo_root)
    dest_root = resolve_path(args.dest, repo_root)

    if not source_root.exists():
        print(f"Error: source path not found: {source_root}", file=sys.stderr)
        return 1
    if not source_root.is_dir():
        print(f"Error: source path is not a directory: {source_root}", file=sys.stderr)
        return 1
    if dest_root.exists() and not dest_root.is_dir():
        print(f"Error: destination path is not a directory: {dest_root}", file=sys.stderr)
        return 1

    print(f"Source: {source_root}")
    print(f"Destination: {dest_root}")
    if args.dry_run:
        print("Mode: dry-run")

    relative_dirs = list_relative_dirs(source_root)
    validate_canonical_layout(relative_dirs)

    root_created = False
    if not dest_root.exists():
        root_created = True
        print(f"MKDIR   {dest_root}")
        if not args.dry_run:
            dest_root.mkdir(parents=True, exist_ok=True)

    created = 0
    existing = 0
    collisions: List[Path] = []

    for rel in relative_dirs:
        dest_dir = dest_root / rel
        if dest_dir.exists():
            if dest_dir.is_dir():
                existing += 1
                continue
            collisions.append(dest_dir)
            continue

        created += 1
        print(f"MKDIR   {dest_dir}")
        if not args.dry_run:
            dest_dir.mkdir(parents=True, exist_ok=True)

    if collisions:
        print("\nCollision(s) detected; refusing to continue:", file=sys.stderr)
        for path in collisions:
            print(f"  - {path}", file=sys.stderr)
        print(
            "\nSummary: "
            f"source_dirs={len(relative_dirs)} root_created={int(root_created)} "
            f"created={created} existing={existing} collisions={len(collisions)}",
            file=sys.stderr,
        )
        return 2

    print(
        "\nSummary: "
        f"source_dirs={len(relative_dirs)} root_created={int(root_created)} "
        f"created={created} existing={existing} collisions=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
