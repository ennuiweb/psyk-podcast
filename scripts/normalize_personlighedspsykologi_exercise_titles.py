#!/usr/bin/env python3
"""Replace generic 'Exercise text' reading titles with filename-derived titles."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


DEFAULT_KEY_PATH = (
    "/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/"
    "Mine dokumenter \U0001F4BE/psykologi/Personlighedspsykologi/.ai/reading-file-key.md"
)

EXERCISE_LINE_RE = re.compile(
    r"^(?P<prefix>\s*-\s+)Exercise text(?P<mid>\s*→\s*)(?P<source>.+?)\s*$",
    re.IGNORECASE,
)
GENERIC_BULLET_RE = re.compile(
    r"^(?P<prefix>\s*-\s+)(?P<title>.+?)(?P<mid>\s*→\s*)(?P<source>.+?)\s*$"
)
LECTURE_PREFIX_RE = re.compile(r"^W0*\d{1,2}L0*\d+\s*(?:-\s*)?", re.IGNORECASE)
X_SOURCE_RE = re.compile(r"^W0*\d{1,2}L0*\d+\s+X\b", re.IGNORECASE)


def _title_from_source_filename(source: str) -> str:
    raw = str(source or "").strip()
    stem = re.sub(r"\.[A-Za-z0-9]{2,6}\s*$", "", raw).strip()
    if not stem:
        return "Exercise text"
    normalized = LECTURE_PREFIX_RE.sub("", stem).strip()
    return normalized or stem


def normalize_exercise_titles(text: str) -> tuple[str, list[tuple[int, str, str]]]:
    updated_lines: list[str] = []
    changes: list[tuple[int, str, str]] = []

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line
        match = EXERCISE_LINE_RE.match(line)
        if match:
            source = str(match.group("source") or "").strip()
            replacement_title = _title_from_source_filename(source)
            new_line = f"{match.group('prefix')}{replacement_title}{match.group('mid')}{source}"
            if new_line != line:
                changes.append((line_number, line, new_line))
                line = new_line
        else:
            generic_match = GENERIC_BULLET_RE.match(line)
            if generic_match:
                source = str(generic_match.group("source") or "").strip()
                source_no_annotation = re.sub(r"\s+\([^)]*\)\s*$", "", source).strip()
                if X_SOURCE_RE.match(source_no_annotation):
                    replacement_title = _title_from_source_filename(source_no_annotation)
                    new_line = (
                        f"{generic_match.group('prefix')}{replacement_title}"
                        f"{generic_match.group('mid')}{source}"
                    )
                    if new_line != line:
                        changes.append((line_number, line, new_line))
                        line = new_line
        updated_lines.append(line)

    output = "\n".join(updated_lines)
    if text.endswith("\n"):
        output += "\n"
    return output, changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--key-path",
        default=DEFAULT_KEY_PATH,
        help="Path to reading-file-key.md to normalize.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes to file. Default is dry-run.",
    )
    args = parser.parse_args()

    key_path = Path(args.key_path).expanduser().resolve()
    if not key_path.exists():
        raise SystemExit(f"Reading key not found: {key_path}")

    original = key_path.read_text(encoding="utf-8")
    normalized, changes = normalize_exercise_titles(original)

    print(f"KEY_PATH={key_path}")
    print(f"EXERCISE_TITLE_CHANGES={len(changes)}")
    for line_number, old_line, new_line in changes:
        print(f"LINE {line_number}: {old_line}")
        print(f"  -> {new_line}")

    if not changes:
        print("NO_CHANGES_NEEDED")
        return 0
    if not args.apply:
        print("DRY_RUN_ONLY: no changes applied.")
        return 0

    key_path.write_text(normalized, encoding="utf-8")
    print("APPLIED=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
