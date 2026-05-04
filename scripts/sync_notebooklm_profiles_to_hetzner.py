#!/usr/bin/env python3
"""Sync local NotebookLM profile storage states to the Hetzner queue host."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path


DEFAULT_PROFILES_FILE = "notebooklm-podcast-auto/profiles.json"
DEFAULT_HOST = "hetzner-ennui-vps-01-root"
DEFAULT_REMOTE_DIR = "/etc/podcasts/notebooklm-queue/profiles"
DEFAULT_REMOTE_PROFILES_FILE = "/etc/podcasts/notebooklm-queue/profiles.host.json"
DEFAULT_REMOTE_STAGING_DIR = "/tmp/notebooklm-profiles-sync"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Copy local NotebookLM storage_state profile files to the Hetzner queue host "
            "and write a host-local profiles JSON bundle."
        )
    )
    parser.add_argument(
        "--profiles-file",
        default=DEFAULT_PROFILES_FILE,
        help=f"Source profiles.json path (default: {DEFAULT_PROFILES_FILE})",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"SSH host alias for Hetzner (default: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--remote-dir",
        default=DEFAULT_REMOTE_DIR,
        help=f"Remote directory for copied storage state files (default: {DEFAULT_REMOTE_DIR})",
    )
    parser.add_argument(
        "--remote-profiles-file",
        default=DEFAULT_REMOTE_PROFILES_FILE,
        help=(
            "Remote JSON file mapping profile names to host-local storage files "
            f"(default: {DEFAULT_REMOTE_PROFILES_FILE})"
        ),
    )
    parser.add_argument(
        "--remote-staging-dir",
        default=DEFAULT_REMOTE_STAGING_DIR,
        help=f"Remote temporary upload directory (default: {DEFAULT_REMOTE_STAGING_DIR})",
    )
    parser.add_argument(
        "--profile",
        action="append",
        default=[],
        help="Specific profile name to sync. Repeat or pass a comma-separated list.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved sync plan without copying files.",
    )
    return parser.parse_args()


def load_profiles(path: Path) -> dict[str, Path]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict) and isinstance(raw.get("profiles"), dict):
        raw = raw["profiles"]
    if not isinstance(raw, dict):
        raise SystemExit(
            "Profiles file must be a JSON object of {profile_name: storage_path} "
            'or {"profiles": {...}}.'
        )

    profiles: dict[str, Path] = {}
    for name, value in raw.items():
        if not isinstance(name, str) or value is None:
            continue
        source = Path(str(value)).expanduser()
        if not source.is_absolute():
            source = (path.parent / source).resolve()
        else:
            source = source.resolve()
        profiles[name] = source
    if not profiles:
        raise SystemExit(f"No valid profiles found in {path}")
    return profiles


def selected_profile_names(available: dict[str, Path], requested: list[str]) -> list[str]:
    if not requested:
        return sorted(available)
    names: list[str] = []
    seen: set[str] = set()
    for entry in requested:
        for item in entry.split(","):
            name = item.strip()
            if not name or name in seen:
                continue
            if name not in available:
                raise SystemExit(
                    f"Profile '{name}' not found in source profiles file. "
                    f"Available: {', '.join(sorted(available))}"
                )
            seen.add(name)
            names.append(name)
    return names


def remote_filename(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip("-")
    slug = slug or "profile"
    return f"{slug}.json"


def run(cmd: list[str], *, dry_run: bool) -> None:
    print("+", " ".join(cmd))
    if dry_run:
        return
    subprocess.run(cmd, check=True)


def ssh_bash_command(host: str, script: str) -> list[str]:
    return ["ssh", host, f"bash -lc {shlex.quote(script)}"]


def main() -> int:
    args = parse_args()
    profiles_path = Path(args.profiles_file).expanduser().resolve()
    profiles = load_profiles(profiles_path)
    names = selected_profile_names(profiles, args.profile)

    missing = [name for name in names if not profiles[name].exists()]
    if missing:
        raise SystemExit(
            "Selected profiles are missing storage files: "
            + ", ".join(f"{name} -> {profiles[name]}" for name in missing)
        )

    bundle: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="notebooklm-profiles-") as tmp_dir_raw:
        tmp_dir = Path(tmp_dir_raw)
        for name in names:
            target_name = remote_filename(name)
            shutil.copy2(profiles[name], tmp_dir / target_name)
            bundle[name] = f"{args.remote_dir.rstrip('/')}/{target_name}"
        bundle_path = tmp_dir / "profiles.host.json"
        bundle_path.write_text(
            json.dumps({"profiles": bundle}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        print(f"Source profiles file: {profiles_path}")
        for name in names:
            print(f"- {name}: {profiles[name]} -> {bundle[name]}")
        print(f"- bundle: {args.remote_profiles_file}")

        run(
            ssh_bash_command(
                args.host,
                f"rm -rf {args.remote_staging_dir} && mkdir -p {args.remote_staging_dir}",
            ),
            dry_run=args.dry_run,
        )
        run(
            [
                "scp",
                "-r",
                f"{tmp_dir}/.",
                f"{args.host}:{args.remote_staging_dir}/",
            ],
            dry_run=args.dry_run,
        )
        install_script = f"""
set -euo pipefail
install -d -m 700 {args.remote_dir}
find {args.remote_staging_dir} -maxdepth 1 -type f -name '*.json' ! -name 'profiles.host.json' -print0 | \\
  while IFS= read -r -d '' file; do
    install -m 600 "$file" {args.remote_dir}/"$(basename "$file")"
  done
install -m 600 {args.remote_staging_dir}/profiles.host.json {args.remote_profiles_file}
rm -rf {args.remote_staging_dir}
"""
        run(
            ssh_bash_command(args.host, install_script),
            dry_run=args.dry_run,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
