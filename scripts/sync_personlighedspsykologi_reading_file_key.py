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
DEFAULT_PRIMARY_TARGET = "shows/personlighedspsykologi-en/docs/reading-file-key.md"
DEFAULT_SECONDARY_TARGET = "notebooklm-podcast-auto/personlighedspsykologi/docs/reading-file-key.md"


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


def _status_for_target(source: Path, target: Path, *, label: str) -> str:
    if not target.exists():
        print(f"{label}_STATUS=missing_target")
        return "missing_target"
    src_hash = _sha256(source)
    dst_hash = _sha256(target)
    print(f"{label}_SOURCE_SHA256={src_hash}")
    print(f"{label}_TARGET_SHA256={dst_hash}")
    if src_hash == dst_hash:
        print(f"{label}_STATUS=up_to_date")
        return "up_to_date"
    print(f"{label}_STATUS=out_of_sync")
    return "out_of_sync"


def _backup_path(target: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    return target.with_name(f"{target.name}.bak-{stamp}")


def _copy_file(source: Path, target: Path, *, backup_on_change: bool, label: str) -> None:
    if target.exists() and backup_on_change:
        src_hash = _sha256(source)
        dst_hash = _sha256(target)
        if src_hash != dst_hash:
            backup = _backup_path(target)
            target.replace(backup)
            print(f"{label}_BACKUP_CREATED={backup}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    print(f"{label}_SYNCED={target}")


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
            "Sync Personlighedspsykologi reading-file-key into repo mirrors "
            "(OneDrive source with repo fallback)."
        )
    )
    parser.add_argument(
        "--source",
        default=DEFAULT_ONEDRIVE_SOURCE,
        help=(
            "Source markdown path. Defaults to OneDrive master. "
            "When missing, script falls back to primary target unless --strict-source is set."
        ),
    )
    parser.add_argument(
        "--target",
        default=DEFAULT_PRIMARY_TARGET,
        help="Primary repo target markdown path (relative to repo root unless absolute).",
    )
    parser.add_argument(
        "--secondary-target",
        default=DEFAULT_SECONDARY_TARGET,
        help="Secondary repo mirror target markdown path (relative to repo root unless absolute).",
    )
    parser.add_argument(
        "--no-secondary-target",
        action="store_true",
        help="Disable syncing the secondary repo mirror target.",
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
    parser.add_argument(
        "--strict-source",
        action="store_true",
        help="Fail if configured source path is missing (disable primary-target fallback).",
    )
    args = parser.parse_args()

    repo_root = _resolve_repo_root(Path(__file__).resolve())
    configured_source = Path(args.source).expanduser()
    if not configured_source.is_absolute():
        configured_source = (repo_root / configured_source).resolve()
    else:
        configured_source = configured_source.resolve()
    primary_target = Path(args.target).expanduser()
    if not primary_target.is_absolute():
        primary_target = (repo_root / primary_target).resolve()
    target_items: list[tuple[str, Path]] = [("TARGET1", primary_target)]
    if not args.no_secondary_target and args.secondary_target:
        secondary_target = Path(args.secondary_target).expanduser()
        if not secondary_target.is_absolute():
            secondary_target = (repo_root / secondary_target).resolve()
        if secondary_target != primary_target:
            target_items.append(("TARGET2", secondary_target))

    print(f"CONFIGURED_SOURCE={configured_source}")
    for label, target in target_items:
        print(f"{label}_PATH={target}")

    if args.bootstrap_source_from_repo:
        return _bootstrap_source(configured_source, primary_target, apply=args.apply)

    source = configured_source
    source_mode = "configured_source"
    if not source.exists():
        print(f"SOURCE_STATUS=missing_source:{source}")
        if primary_target.exists() and not args.strict_source:
            source = primary_target
            source_mode = "fallback_primary_target"
            print(f"SOURCE_FALLBACK={source}")
        else:
            print("ABORTED: source missing. Create it in OneDrive or run --bootstrap-source-from-repo.")
            return 1
    print(f"SOURCE={source}")
    print(f"SOURCE_MODE={source_mode}")

    statuses: list[tuple[str, Path, str]] = []
    needs_sync = False
    for label, target in target_items:
        status = _status_for_target(source, target, label=label)
        statuses.append((label, target, status))
        if status in {"missing_target", "out_of_sync"}:
            needs_sync = True

    if not needs_sync:
        print("NO_CHANGES_NEEDED")
        return 0
    if not args.apply:
        print("DRY_RUN_ONLY: no changes applied.")
        return 0

    for label, target, status in statuses:
        if status not in {"missing_target", "out_of_sync"}:
            continue
        _copy_file(source, target, backup_on_change=not args.no_backup, label=label)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
