#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


DEFAULT_OUTPUT_ROOT = "notebooklm-podcast-auto/bioneuro/output"
DEFAULT_NOTEBOOKLM = ".venv/bin/notebooklm"
BASE_DOWNLOADER = "notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py"
WEEK_DIR_PATTERN = re.compile(r"^W\d+L\d+$", re.IGNORECASE)


def has_cli_option(args: list[str], option: str) -> bool:
    prefix = f"{option}="
    return any(arg == option or arg.startswith(prefix) for arg in args)


def find_root_week_dirs_with_files(bioneuro_root: Path) -> list[Path]:
    week_dirs: list[Path] = []
    for entry in sorted(bioneuro_root.iterdir(), key=lambda path: path.name):
        if not entry.is_dir() or not WEEK_DIR_PATTERN.fullmatch(entry.name):
            continue
        if any(path.is_file() for path in entry.rglob("*")):
            week_dirs.append(entry)
    return week_dirs


def ensure_no_legacy_root_week_dirs(repo_root: Path) -> int:
    if os.environ.get("BIONEURO_ALLOW_ROOT_WEEK_DIRS") == "1":
        return 0

    bioneuro_root = repo_root / "notebooklm-podcast-auto" / "bioneuro"
    legacy_dirs = find_root_week_dirs_with_files(bioneuro_root)
    if not legacy_dirs:
        return 0

    print(
        "Error: found legacy outputs under notebooklm-podcast-auto/bioneuro/W#L#.",
        file=sys.stderr,
    )
    print("Canonical output root is notebooklm-podcast-auto/bioneuro/output.", file=sys.stderr)
    print("Move or remove these directories before running this wrapper:", file=sys.stderr)
    for path in legacy_dirs:
        print(f"  - {path.relative_to(repo_root)}", file=sys.stderr)
    print("Temporary bypass: BIONEURO_ALLOW_ROOT_WEEK_DIRS=1", file=sys.stderr)
    return 2


def main() -> int:
    user_args = sys.argv[1:]
    repo_root = Path(__file__).resolve().parents[3]
    legacy_check = ensure_no_legacy_root_week_dirs(repo_root)
    if legacy_check != 0:
        return legacy_check
    downloader = repo_root / BASE_DOWNLOADER

    if not downloader.exists():
        print(f"Error: base downloader not found: {downloader}", file=sys.stderr)
        return 1

    command = [sys.executable, str(downloader)]
    if not has_cli_option(user_args, "--output-root"):
        command.extend(["--output-root", DEFAULT_OUTPUT_ROOT])
    if not has_cli_option(user_args, "--notebooklm"):
        command.extend(["--notebooklm", DEFAULT_NOTEBOOKLM])
    command.extend(user_args)

    return subprocess.call(command, cwd=repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
