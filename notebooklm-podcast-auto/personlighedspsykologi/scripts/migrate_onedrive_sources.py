#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CANONICAL_ROOT = "notebooklm-podcast-auto/personlighedspsykologi/sources"
DEFAULT_ONEDRIVE_ROOT = (
    "/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/"
    "Mine dokumenter \U0001F4BE/psykologi/Personlighedspsykologi/Readings"
)
DEFAULT_QUARANTINE_PARENT = "Alle filer (samlet)/_quarantine_noncanonical"


@dataclass(frozen=True)
class RenameOp:
    week: str
    src: Path
    dst: Path


@dataclass(frozen=True)
class QuarantineOp:
    week: str
    src: Path
    dst: Path


@dataclass(frozen=True)
class CopyNeeded:
    week: str
    canonical_file: Path


@dataclass(frozen=True)
class Conflict:
    week: str
    reason: str
    details: str


def _visible_files(root: Path) -> list[Path]:
    return sorted(
        [entry for entry in root.iterdir() if entry.is_file() and not entry.name.startswith(".")],
        key=lambda path: path.name.casefold(),
    )


def _sha256(path: Path, cache: dict[Path, str]) -> str:
    resolved = path.resolve()
    cached = cache.get(resolved)
    if cached is not None:
        return cached
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    cache[resolved] = value
    return value


def _build_plan(
    canonical_root: Path,
    onedrive_root: Path,
    quarantine_parent: Path,
) -> tuple[int, list[RenameOp], list[QuarantineOp], list[Conflict], list[CopyNeeded]]:
    hash_cache: dict[Path, str] = {}
    renames: list[RenameOp] = []
    quarantines: list[QuarantineOp] = []
    conflicts: list[Conflict] = []
    copy_needed: list[CopyNeeded] = []

    week_dirs = sorted(
        [entry for entry in canonical_root.iterdir() if entry.is_dir() and not entry.name.startswith(".")],
        key=lambda path: path.name.casefold(),
    )

    for canonical_week_dir in week_dirs:
        week = canonical_week_dir.name
        onedrive_week_dir = onedrive_root / week

        if not onedrive_week_dir.exists() or not onedrive_week_dir.is_dir():
            conflicts.append(
                Conflict(
                    week=week,
                    reason="missing_onedrive_week_dir",
                    details=str(onedrive_week_dir),
                )
            )
            continue

        canonical_files = _visible_files(canonical_week_dir)
        onedrive_files = _visible_files(onedrive_week_dir)
        onedrive_by_name = {path.name: path for path in onedrive_files}

        unmatched_canonical: list[Path] = []
        matched_onedrive_names: set[str] = set()

        for canonical_file in canonical_files:
            onedrive_same_name = onedrive_by_name.get(canonical_file.name)
            if onedrive_same_name is None:
                unmatched_canonical.append(canonical_file)
                continue

            canonical_hash = _sha256(canonical_file, hash_cache)
            onedrive_hash = _sha256(onedrive_same_name, hash_cache)
            if canonical_hash != onedrive_hash:
                conflicts.append(
                    Conflict(
                        week=week,
                        reason="exact_name_content_mismatch",
                        details=(
                            f"{onedrive_same_name.name}: canonical_sha={canonical_hash} "
                            f"onedrive_sha={onedrive_hash}"
                        ),
                    )
                )
                continue

            matched_onedrive_names.add(onedrive_same_name.name)

        onedrive_hash_index: dict[tuple[str, str], list[Path]] = {}
        for onedrive_file in onedrive_files:
            if onedrive_file.name in matched_onedrive_names:
                continue
            file_hash = _sha256(onedrive_file, hash_cache)
            key = (onedrive_file.suffix.lower(), file_hash)
            onedrive_hash_index.setdefault(key, []).append(onedrive_file)

        for canonical_file in unmatched_canonical:
            canonical_hash = _sha256(canonical_file, hash_cache)
            key = (canonical_file.suffix.lower(), canonical_hash)
            candidates = sorted(
                onedrive_hash_index.get(key, []),
                key=lambda path: path.name.casefold(),
            )

            if not candidates:
                copy_needed.append(CopyNeeded(week=week, canonical_file=canonical_file))
                continue

            if len(candidates) > 1:
                conflicts.append(
                    Conflict(
                        week=week,
                        reason="multiple_hash_matches",
                        details=(
                            f"canonical={canonical_file.name} candidates="
                            + ", ".join(candidate.name for candidate in candidates)
                        ),
                    )
                )
                continue

            src = candidates[0]
            dst = onedrive_week_dir / canonical_file.name
            if dst.exists() and dst.name != src.name:
                dst_hash = _sha256(dst, hash_cache)
                if dst_hash != canonical_hash:
                    conflicts.append(
                        Conflict(
                            week=week,
                            reason="rename_target_exists_different_content",
                            details=f"target={dst.name} source={src.name}",
                        )
                    )
                    continue

            renames.append(RenameOp(week=week, src=src, dst=dst))
            matched_onedrive_names.add(src.name)

        for onedrive_file in onedrive_files:
            if onedrive_file.name in matched_onedrive_names:
                continue
            quarantine_dst = onedrive_root / quarantine_parent / week / onedrive_file.name
            if quarantine_dst.exists():
                src_hash = _sha256(onedrive_file, hash_cache)
                dst_hash = _sha256(quarantine_dst, hash_cache)
                if src_hash != dst_hash:
                    conflicts.append(
                        Conflict(
                            week=week,
                            reason="quarantine_target_exists_different_content",
                            details=f"source={onedrive_file.name} target={quarantine_dst}",
                        )
                    )
                    continue
                conflicts.append(
                    Conflict(
                        week=week,
                        reason="quarantine_target_already_exists",
                        details=f"source={onedrive_file.name} target={quarantine_dst}",
                    )
                )
                continue

            quarantines.append(QuarantineOp(week=week, src=onedrive_file, dst=quarantine_dst))

    renames.sort(key=lambda op: (op.week.casefold(), op.src.name.casefold(), op.dst.name.casefold()))
    quarantines.sort(key=lambda op: (op.week.casefold(), op.src.name.casefold()))
    conflicts.sort(key=lambda c: (c.week.casefold(), c.reason.casefold(), c.details.casefold()))
    copy_needed.sort(key=lambda item: (item.week.casefold(), item.canonical_file.name.casefold()))
    return len(week_dirs), renames, quarantines, conflicts, copy_needed


def _print_report(
    week_dir_count: int,
    renames: list[RenameOp],
    quarantines: list[QuarantineOp],
    conflicts: list[Conflict],
    copy_needed: list[CopyNeeded],
) -> None:
    print(f"WEEK_DIRS={week_dir_count}")
    print(f"RENAMES={len(renames)}")
    print(f"EXTRAS={len(quarantines)}")
    print(f"CONFLICTS={len(conflicts)}")
    print(f"COPY_NEEDED={len(copy_needed)}")

    for op in renames:
        print(f"RENAME\t{op.week}\t{op.src.name}\t=>\t{op.dst.name}")
    for op in quarantines:
        print(f"QUARANTINE\t{op.week}\t{op.src.name}\t=>\t{op.dst}")
    for issue in conflicts:
        print(f"CONFLICT\t{issue.week}\t{issue.reason}\t{issue.details}")
    for missing in copy_needed:
        print(f"COPY_NEEDED\t{missing.week}\t{missing.canonical_file.name}")


def _apply_changes(renames: list[RenameOp], quarantines: list[QuarantineOp]) -> None:
    for op in renames:
        op.src.rename(op.dst)
    for op in quarantines:
        op.dst.parent.mkdir(parents=True, exist_ok=True)
        op.src.rename(op.dst)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Canonicalize OneDrive readings filenames against repo-local canonical sources, "
            "and quarantine non-canonical extras."
        )
    )
    parser.add_argument(
        "--canonical-root",
        default=DEFAULT_CANONICAL_ROOT,
        help="Canonical source tree used as filename/content reference.",
    )
    parser.add_argument(
        "--onedrive-root",
        default=DEFAULT_ONEDRIVE_ROOT,
        help="OneDrive readings root to mutate.",
    )
    parser.add_argument(
        "--quarantine-parent",
        default=DEFAULT_QUARANTINE_PARENT,
        help="Relative folder (under --onedrive-root) used for non-canonical extras.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply renames/quarantine moves (default is dry-run report only).",
    )
    args = parser.parse_args()

    canonical_root = Path(args.canonical_root).expanduser().resolve()
    onedrive_root = Path(args.onedrive_root).expanduser().resolve()
    quarantine_parent = Path(args.quarantine_parent)

    if not canonical_root.exists() or not canonical_root.is_dir():
        raise SystemExit(f"Canonical root not found: {canonical_root}")
    if not onedrive_root.exists() or not onedrive_root.is_dir():
        raise SystemExit(f"OneDrive root not found: {onedrive_root}")

    week_dir_count, renames, quarantines, conflicts, copy_needed = _build_plan(
        canonical_root=canonical_root,
        onedrive_root=onedrive_root,
        quarantine_parent=quarantine_parent,
    )

    _print_report(week_dir_count, renames, quarantines, conflicts, copy_needed)

    if conflicts or copy_needed:
        print("ABORTED: unsafe migration state detected; no changes applied.")
        return 1

    if not args.apply:
        print("DRY_RUN_ONLY: no changes applied.")
        return 0

    _apply_changes(renames, quarantines)
    print(f"APPLIED_RENAMES={len(renames)}")
    print(f"APPLIED_QUARANTINES={len(quarantines)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
