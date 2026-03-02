#!/usr/bin/env python3
from __future__ import annotations

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


def has_cli_option(args: list[str], option: str) -> bool:
    prefix = f"{option}="
    return any(arg == option or arg.startswith(prefix) for arg in args)


def main() -> int:
    user_args = sys.argv[1:]
    repo_root = Path(__file__).resolve().parents[3]
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
