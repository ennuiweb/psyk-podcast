#!/usr/bin/env python3
"""
Normalize Personlighedspsykologi output paths.

This repo uses padded lecture keys (`W##L#`). Historical output trees contain a
mix of unpadded (`W1L1`) and padded (`W01L1`) directories and filenames. This
script migrates the entire tree into the canonical padded layout.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import NamedTuple


TOKEN_RE = re.compile(r"\bW(?P<week>\d{1,2})L(?P<lecture>\d+)\b")


class PlannedMove(NamedTuple):
    source: Path
    destination: Path
    identical: bool


def _normalized_name(name: str) -> str:
    def repl(match: re.Match[str]) -> str:
        week = match.group("week").zfill(2)
        lecture = match.group("lecture")
        return f"W{week}L{lecture}"

    return TOKEN_RE.sub(repl, name)


def normalized_relative_path(path: Path) -> Path:
    if path == Path("."):
        return path
    parts = [_normalized_name(part) for part in path.parts]
    return Path(*parts)


def _iter_files(root: Path) -> list[Path]:
    return sorted(
        [path for path in root.rglob("*") if path.is_file() and path.name != ".DS_Store"],
        key=lambda item: (len(item.relative_to(root).parts), item.relative_to(root).as_posix()),
    )


def _files_identical(left: Path, right: Path) -> bool:
    if left.stat().st_size != right.stat().st_size:
        return False
    with left.open("rb") as left_handle, right.open("rb") as right_handle:
        while True:
            left_chunk = left_handle.read(1024 * 1024)
            right_chunk = right_handle.read(1024 * 1024)
            if left_chunk != right_chunk:
                return False
            if not left_chunk:
                return True


def plan_file_moves(root: Path) -> list[PlannedMove]:
    planned: list[PlannedMove] = []
    destination_sources: dict[Path, Path] = {}

    for source in _iter_files(root):
        relative_source = source.relative_to(root)
        relative_destination = normalized_relative_path(relative_source)
        destination = root / relative_destination
        if destination == source:
            continue

        prior_source = destination_sources.get(destination)
        if prior_source is not None and prior_source != source:
            if not _files_identical(prior_source, source):
                raise SystemExit(
                    "Rename collision: multiple files map to the same destination with "
                    f"different content: {prior_source} vs {source} -> {destination}"
                )
            continue

        identical = destination.exists() and destination.is_file() and _files_identical(source, destination)
        if destination.exists() and not destination.is_file():
            raise SystemExit(f"Destination exists and is not a file: {destination}")
        if destination.exists() and not identical:
            raise SystemExit(
                f"Destination already exists with different content: {source} -> {destination}"
            )

        destination_sources[destination] = source
        planned.append(PlannedMove(source=source, destination=destination, identical=identical))

    return planned


def _remove_empty_dirs(root: Path) -> int:
    removed = 0
    directories = sorted(
        [path for path in root.rglob("*") if path.is_dir()],
        key=lambda item: (-len(item.relative_to(root).parts), item.as_posix()),
    )
    for directory in directories:
        if directory == root:
            continue
        try:
            entries = list(directory.iterdir())
        except OSError:
            continue

        removable_files = [entry for entry in entries if entry.is_file() and entry.name == ".DS_Store"]
        retained_entries = [entry for entry in entries if entry not in removable_files]
        for entry in removable_files:
            entry.unlink()

        if retained_entries:
            continue
        try:
            directory.rmdir()
            removed += 1
        except OSError:
            continue
    return removed


def apply_planned_moves(root: Path, planned: list[PlannedMove]) -> tuple[int, int, int]:
    moved = 0
    removed_duplicates = 0

    for item in planned:
        item.destination.parent.mkdir(parents=True, exist_ok=True)
        if item.identical:
            item.source.unlink()
            removed_duplicates += 1
            continue
        shutil.move(str(item.source), str(item.destination))
        moved += 1

    removed_dirs = _remove_empty_dirs(root)
    return moved, removed_duplicates, removed_dirs


def rewrite_request_json_paths(root: Path) -> int:
    rewritten = 0
    output_root = str(root.resolve()) + "/"
    for json_path in sorted(root.rglob("*.request.json")):
        try:
            obj = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(obj, dict):
            continue
        output_path = obj.get("output_path")
        if not isinstance(output_path, str) or not output_path.startswith(output_root):
            continue
        normalized_output_path = _normalized_name(output_path)
        if normalized_output_path == output_path:
            continue
        obj["output_path"] = normalized_output_path
        json_path.write_text(
            json.dumps(obj, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        rewritten += 1
    return rewritten


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default="notebooklm-podcast-auto/personlighedspsykologi/output",
        help="Root folder containing per-week output directories.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply renames (default is dry-run).",
    )
    parser.add_argument(
        "--rewrite-request-json",
        action="store_true",
        help="Rewrite output_path fields in *.request.json files after renaming.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        raise SystemExit(f"Root does not exist: {root}")
    if not root.is_dir():
        raise SystemExit(f"Root is not a directory: {root}")

    planned = plan_file_moves(root)
    if not planned and not (args.apply and args.rewrite_request_json):
        print("No path normalization needed.")
        return 0

    if not args.apply:
        print(f"Planned file moves: {len(planned)}")
        for item in planned[:200]:
            action = "delete-duplicate" if item.identical else "move"
            print(f"- [{action}] {item.source} -> {item.destination}")
        if len(planned) > 200:
            print(f"... plus {len(planned) - 200} more")
        return 0

    moved, removed_duplicates, removed_dirs = apply_planned_moves(root, planned)
    rewritten = rewrite_request_json_paths(root) if args.rewrite_request_json else 0

    print(f"Moved files: {moved}")
    print(f"Removed duplicate files: {removed_duplicates}")
    print(f"Removed empty dirs: {removed_dirs}")
    if args.rewrite_request_json:
        print(f"Rewritten request JSON: {rewritten}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
