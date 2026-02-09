#!/usr/bin/env python3
"""
Normalize Personlighedspsykologi output filenames.

This repo uses padded week tokens (W##L#). Some generated NotebookLM outputs
include unpadded tokens like "W6L1" inside otherwise padded filenames.
Those unpadded tokens are ambiguous and can collide with "w6" style week
matching.

This script renames files in-place by converting any token matching
"W{1,2 digits}L{digits}" into a padded week form "W##L#".
"""

from __future__ import annotations

import argparse
import re
import uuid
from pathlib import Path


TOKEN_RE = re.compile(r"\bW(?P<week>\d{1,2})L(?P<lecture>\d+)\b")


def _normalized_name(name: str) -> str:
    def repl(match: re.Match[str]) -> str:
        week = match.group("week").zfill(2)
        lecture = match.group("lecture")
        return f"W{week}L{lecture}"

    return TOKEN_RE.sub(repl, name)


def _iter_files(root: Path) -> list[Path]:
    return sorted([p for p in root.rglob("*") if p.is_file() and p.name != ".DS_Store"])


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

    root = Path(args.root)
    if not root.exists():
        raise SystemExit(f"Root does not exist: {root}")
    if not root.is_dir():
        raise SystemExit(f"Root is not a directory: {root}")

    planned: list[tuple[Path, Path]] = []
    for path in _iter_files(root):
        new_name = _normalized_name(path.name)
        if new_name != path.name:
            planned.append((path, path.with_name(new_name)))

    if not planned and not (args.apply and args.rewrite_request_json):
        print("No renames needed.")
        return 0

    # Detect collisions on target paths.
    targets = [dst for _, dst in planned]
    if len(set(targets)) != len(targets):
        raise SystemExit("Rename collision: multiple sources map to the same destination.")

    if not args.apply:
        print(f"Planned renames: {len(planned)}")
        for src, dst in planned[:200]:
            print(f"- {src} -> {dst}")
        if len(planned) > 200:
            print(f"... plus {len(planned) - 200} more")
        return 0

    # Two-phase rename to avoid ordering issues.
    tmp_map: list[tuple[Path, Path]] = []
    for src, dst in planned:
        tmp = src.with_name(f"{src.name}.rename_tmp_{uuid.uuid4().hex}")
        if tmp.exists():
            raise SystemExit(f"Unexpected temp path exists: {tmp}")
        src.rename(tmp)
        tmp_map.append((tmp, dst))

    # Now move temps into final destinations, ensuring we don't overwrite.
    for tmp, dst in tmp_map:
        if dst.exists():
            raise SystemExit(f"Destination already exists: {dst}")
        tmp.rename(dst)

    rewritten = 0
    if args.rewrite_request_json:
        output_root = str(root.resolve()) + "/"
        for json_path in sorted(root.rglob("*.request.json")):
            try:
                data = json_path.read_text(encoding="utf-8")
            except Exception:
                continue
            try:
                obj = __import__("json").loads(data)
            except Exception:
                continue
            output_path = obj.get("output_path") if isinstance(obj, dict) else None
            if not isinstance(output_path, str) or not output_path.startswith(output_root):
                continue
            updated = _normalized_name(output_path)
            if updated == output_path:
                continue
            obj["output_path"] = updated
            json_path.write_text(
                __import__("json").dumps(obj, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            rewritten += 1

    print(f"Renamed files: {len(planned)}")
    if args.rewrite_request_json:
        print(f"Rewritten request JSON: {rewritten}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
