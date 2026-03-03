#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


DEFAULT_SOURCES_ROOT = (
    "/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/"
    "Mine dokumenter \U0001F4BE/psykologi/Bioneuro/Readings"
)
DEFAULT_PROMPT_CONFIG = "notebooklm-podcast-auto/bioneuro/prompt_config.json"
DEFAULT_OUTPUT_ROOT = "notebooklm-podcast-auto/bioneuro/output"
BASE_GENERATOR = "notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py"
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
    print("Suggested cleanup:", file=sys.stderr)
    print(
        "  STAMP=\"$(date +%Y%m%d-%H%M%S)\" && "
        "mkdir -p \".ai/quarantine/bioneuro-root-week-dirs-$STAMP\" && "
        "find notebooklm-podcast-auto/bioneuro -mindepth 1 -maxdepth 1 -type d "
        "-regex '.*/W[0-9]+L[0-9]+' -print0 | "
        "while IFS= read -r -d '' d; do "
        "mv \"$d\" \".ai/quarantine/bioneuro-root-week-dirs-$STAMP/\"; done",
        file=sys.stderr,
    )
    return 2


def main() -> int:
    user_args = sys.argv[1:]
    repo_root = Path(__file__).resolve().parents[3]
    legacy_check = ensure_no_legacy_root_week_dirs(repo_root)
    if legacy_check != 0:
        return legacy_check
    generator = repo_root / BASE_GENERATOR

    if not generator.exists():
        print(f"Error: base generator not found: {generator}", file=sys.stderr)
        return 1

    command = [sys.executable, str(generator)]
    if not has_cli_option(user_args, "--sources-root"):
        command.extend(["--sources-root", DEFAULT_SOURCES_ROOT])
    if not has_cli_option(user_args, "--prompt-config"):
        command.extend(["--prompt-config", DEFAULT_PROMPT_CONFIG])
    if not has_cli_option(user_args, "--output-root"):
        command.extend(["--output-root", DEFAULT_OUTPUT_ROOT])
    command.extend(user_args)

    return subprocess.call(command, cwd=repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
