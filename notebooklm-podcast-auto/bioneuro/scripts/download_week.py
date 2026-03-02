#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


DEFAULT_OUTPUT_ROOT = "notebooklm-podcast-auto/bioneuro/output"
DEFAULT_NOTEBOOKLM = "notebooklm-podcast-auto/.venv/bin/notebooklm"
BASE_DOWNLOADER = "notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py"


def has_cli_option(args: list[str], option: str) -> bool:
    prefix = f"{option}="
    return any(arg == option or arg.startswith(prefix) for arg in args)


def main() -> int:
    user_args = sys.argv[1:]
    repo_root = Path(__file__).resolve().parents[3]
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
