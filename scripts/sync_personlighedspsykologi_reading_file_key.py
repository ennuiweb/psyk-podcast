#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ONEDRIVE_SOURCE = (
    "/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/"
    "Mine dokumenter \U0001F4BE/psykologi/Personlighedspsykologi/.ai/reading-file-key.md"
)
DEFAULT_REPO_TARGET = "shows/personlighedspsykologi-en/docs/reading-file-key.md"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_repo_root(script_path: Path) -> Path:
    for parent in script_path.parents:
        if (parent / ".git").exists():
            return parent
    return script_path.parents[1]


def _print_status(source: Path, target: Path) -> tuple[bool, str]:
    source_exists = source.exists()
    target_exists = target.exists()
    if not source_exists and not target_exists:
        print("STATUS=missing_both")
        return False, "missing_both"
    if not source_exists:
        print("STATUS=missing_source")
        return False, "missing_source"
    if not target_exists:
        print("STATUS=missing_target")
        return True, "missing_target"
    src_hash = _sha256(source)
    dst_hash = _sha256(target)
    print(f"SOURCE_SHA256={src_hash}")
    print(f"TARGET_SHA256={dst_hash}")
    if src_hash == dst_hash:
        print("STATUS=up_to_date")
        return False, "up_to_date"
    print("STATUS=out_of_sync")
    return True, "out_of_sync"


def _backup_path(target: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    return target.with_name(f"{target.name}.bak-{stamp}")


def _copy_file(source: Path, target: Path, *, backup_on_change: bool) -> None:
    if target.exists() and backup_on_change:
        src_hash = _sha256(source)
        dst_hash = _sha256(target)
        if src_hash != dst_hash:
            backup = _backup_path(target)
            target.replace(backup)
            print(f"BACKUP_CREATED={backup}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    print(f"SYNCED={target}")


def _bootstrap_source(source: Path, target: Path, *, apply: bool) -> int:
    if source.exists():
        print(f"SOURCE_ALREADY_EXISTS={source}")
        return 0
    if not target.exists():
        print(f"BOOTSTRAP_FAILED_TARGET_MISSING={target}")
        return 1
    print(f"BOOTSTRAP_SOURCE_FROM_REPO={target} -> {source}")
    if not apply:
        print("DRY_RUN_ONLY: no changes applied.")
        return 0
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(target.read_bytes())
    print(f"BOOTSTRAPPED_SOURCE={source}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Sync Personlighedspsykologi reading-file-key from OneDrive source into repo canonical path."
        )
    )
    parser.add_argument(
        "--source",
        default=DEFAULT_ONEDRIVE_SOURCE,
        help="Absolute OneDrive source markdown path.",
    )
    parser.add_argument(
        "--target",
        default=DEFAULT_REPO_TARGET,
        help="Repo target markdown path (relative to repo root unless absolute).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes. Default is dry-run.",
    )
    parser.add_argument(
        "--bootstrap-source-from-repo",
        action="store_true",
        help="If source is missing, create it from the current repo target.",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create a .bak-<timestamp> file when overwriting changed target content.",
    )
    args = parser.parse_args()

    repo_root = _resolve_repo_root(Path(__file__).resolve())
    source = Path(args.source).expanduser()
    target = Path(args.target).expanduser()
    if not target.is_absolute():
        target = (repo_root / target).resolve()
    source = source.resolve()

    print(f"SOURCE={source}")
    print(f"TARGET={target}")

    if args.bootstrap_source_from_repo:
        return _bootstrap_source(source, target, apply=args.apply)

    should_sync, status = _print_status(source, target)
    if status == "missing_source":
        print("ABORTED: source missing. Create it in OneDrive or run --bootstrap-source-from-repo.")
        return 1
    if not should_sync:
        print("NO_CHANGES_NEEDED")
        return 0
    if not args.apply:
        print("DRY_RUN_ONLY: no changes applied.")
        return 0

    _copy_file(source, target, backup_on_change=not args.no_backup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
