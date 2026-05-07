#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CANONICAL_PATH = "shows/personlighedspsykologi-en/docs/reading-file-key.md"
DEFAULT_PRIMARY_TARGET = (
    "/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/"
    "Mine dokumenter \U0001F4BE/psykologi/Personlighedspsykologi/.ai/reading-file-key.md"
)
DEFAULT_SECONDARY_TARGET = ""
GRUNDBOG_CHAPTER_BULLET_RE = re.compile(
    r"^(?P<prefix>\s*-\s*)(?P<title>.+?)\s*→\s*"
    r"(?P<source>Grundbog\s+kapitel\s+\d+\s*-\s*[^.]+\.pdf)"
    r"(?P<suffix>\s*\([^)]*\))?\s*$",
    re.IGNORECASE,
)
SHORT_AND_FULL_NOTE = "(short + full)"


@dataclass(frozen=True)
class SyncStatus:
    label: str
    path: Path
    status: str


def _sha256_bytes(payload: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(payload)
    return digest.hexdigest()


def _resolve_repo_root(script_path: Path) -> Path:
    for parent in script_path.parents:
        if (parent / ".git").exists():
            return parent
    return script_path.parents[1]


def _resolve_path(repo_root: Path, raw_path: str) -> Path:
    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (repo_root / candidate).resolve()


def _normalize_grundbog_bullets(markdown_text: str) -> tuple[str, int]:
    normalized_lines: list[str] = []
    changed_count = 0
    for raw_line in markdown_text.splitlines():
        match = GRUNDBOG_CHAPTER_BULLET_RE.match(raw_line)
        if not match:
            normalized_lines.append(raw_line)
            continue

        source_filename = str(match.group("source") or "").strip()
        if not source_filename.lower().endswith(".pdf"):
            normalized_lines.append(raw_line)
            continue

        chapter_title = source_filename[:-4].strip()
        suffix_text = str(match.group("suffix") or "").strip()
        if not suffix_text:
            normalized_suffix = SHORT_AND_FULL_NOTE
        elif "short + full" in suffix_text.lower() or "brief + full" in suffix_text.lower():
            normalized_suffix = SHORT_AND_FULL_NOTE
        else:
            normalized_suffix = f"{suffix_text} {SHORT_AND_FULL_NOTE}"

        rewritten = f"{match.group('prefix')}{chapter_title} → {source_filename}"
        if normalized_suffix:
            rewritten = f"{rewritten} {normalized_suffix}"
        if rewritten != raw_line:
            changed_count += 1
        normalized_lines.append(rewritten)

    normalized = "\n".join(normalized_lines)
    if markdown_text.endswith("\n") and not normalized.endswith("\n"):
        normalized += "\n"
    return normalized, changed_count


def _normalized_payload(path: Path) -> tuple[bytes, int]:
    payload = path.read_bytes()
    if path.suffix.lower() != ".md":
        return payload, 0
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return payload, 0
    normalized_text, changed_count = _normalize_grundbog_bullets(text)
    return normalized_text.encode("utf-8"), changed_count


def _status_for_target(source_payload: bytes, target: Path, *, label: str) -> SyncStatus:
    if not target.exists():
        print(f"{label}_STATUS=missing_target")
        return SyncStatus(label=label, path=target, status="missing_target")
    target_payload = target.read_bytes()
    source_sha = _sha256_bytes(source_payload)
    target_sha = _sha256_bytes(target_payload)
    print(f"{label}_SOURCE_SHA256={source_sha}")
    print(f"{label}_TARGET_SHA256={target_sha}")
    if source_sha == target_sha:
        print(f"{label}_STATUS=up_to_date")
        return SyncStatus(label=label, path=target, status="up_to_date")
    print(f"{label}_STATUS=out_of_sync")
    return SyncStatus(label=label, path=target, status="out_of_sync")


def _copy_payload(payload: bytes, target: Path, *, label: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    print(f"{label}_SYNCED={target}")


def _export_canonical_to_targets(
    *,
    canonical_path: Path,
    target_items: list[tuple[str, Path]],
    apply: bool,
    fail_on_drift: bool,
    strict_source: bool,
) -> int:
    print("MODE=export")
    print(f"CANONICAL_PATH={canonical_path}")
    for label, target in target_items:
        print(f"{label}_PATH={target}")

    if not canonical_path.exists():
        print(f"CANONICAL_STATUS=missing_source:{canonical_path}")
        if strict_source:
            print("ABORTED: canonical repo reading-file-key is missing.")
            return 1
        print("ABORTED: canonical repo reading-file-key is missing.")
        return 1

    source_payload, normalized_count = _normalized_payload(canonical_path)
    print(f"CANONICAL_SHA256={_sha256_bytes(source_payload)}")
    if normalized_count > 0:
        print(f"CANONICAL_NORMALIZED_GRUNDBOG_LINES={normalized_count}")

    statuses: list[SyncStatus] = []
    has_drift = False
    for label, target in target_items:
        status = _status_for_target(source_payload, target, label=label)
        statuses.append(status)
        if status.status != "up_to_date":
            has_drift = True

    if not has_drift:
        print("NO_CHANGES_NEEDED")
        return 0

    if not apply:
        print("DRY_RUN_ONLY: no changes applied.")
        return 1 if fail_on_drift else 0

    for status in statuses:
        if status.status == "up_to_date":
            continue
        print(f"{status.label}_ACTION=export_from_canonical")
        _copy_payload(source_payload, status.path, label=status.label)
    return 0


def _import_target_to_canonical(
    *,
    canonical_path: Path,
    primary_target: Path,
    apply: bool,
    fail_on_drift: bool,
) -> int:
    print("MODE=import")
    print("IMPORT_MODE_WARNING=use_only_for_explicit_recovery_from_external_mirror")
    print(f"CANONICAL_PATH={canonical_path}")
    print(f"TARGET1_PATH={primary_target}")

    if not primary_target.exists():
        print(f"TARGET1_STATUS=missing_target:{primary_target}")
        print("ABORTED: primary mirror target is missing, nothing to import.")
        return 1

    mirror_payload, normalized_count = _normalized_payload(primary_target)
    print(f"TARGET1_SHA256={_sha256_bytes(mirror_payload)}")
    if normalized_count > 0:
        print(f"TARGET1_NORMALIZED_GRUNDBOG_LINES={normalized_count}")

    status = _status_for_target(mirror_payload, canonical_path, label="CANONICAL")
    if status.status == "up_to_date":
        print("NO_CHANGES_NEEDED")
        return 0

    if not apply:
        print("DRY_RUN_ONLY: no changes applied.")
        return 1 if fail_on_drift else 0

    print("CANONICAL_ACTION=import_from_primary_target")
    _copy_payload(mirror_payload, canonical_path, label="CANONICAL")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Sync Personlighedspsykologi reading-file-key ownership. "
            "Default behavior audits or exports the canonical repo file to the OneDrive mirror."
        )
    )
    parser.add_argument(
        "--mode",
        choices=("export", "import"),
        default="export",
        help=(
            "export = canonical repo file -> mirror targets. "
            "import = primary mirror target -> canonical repo file (recovery only)."
        ),
    )
    parser.add_argument(
        "--canonical-path",
        default=DEFAULT_CANONICAL_PATH,
        help="Canonical repo-owned reading-file-key path (relative to repo root unless absolute).",
    )
    parser.add_argument(
        "--source",
        dest="canonical_path_alias",
        help="Deprecated alias for --canonical-path.",
    )
    parser.add_argument(
        "--target",
        default=DEFAULT_PRIMARY_TARGET,
        help="Primary mirror target path. Defaults to the OneDrive mirror.",
    )
    parser.add_argument(
        "--secondary-target",
        default=DEFAULT_SECONDARY_TARGET,
        help=(
            "Optional second mirror target path "
            "(relative to repo root unless absolute). Disabled by default."
        ),
    )
    parser.add_argument(
        "--no-secondary-target",
        action="store_true",
        help="Disable syncing the secondary mirror target.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes. Default is dry-run audit only.",
    )
    parser.add_argument(
        "--fail-on-drift",
        action="store_true",
        help="Exit with status 1 in dry-run mode when any mirror drift is detected.",
    )
    parser.add_argument(
        "--strict-source",
        action="store_true",
        help="Fail if the canonical repo file is missing.",
    )
    parser.add_argument(
        "--bootstrap-source-from-repo",
        action="store_true",
        help=(
            "Deprecated no-op alias. Export mode already writes missing mirror targets from the "
            "canonical repo file when --apply is used."
        ),
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Deprecated no-op. Backups are no longer created.",
    )
    args = parser.parse_args()

    repo_root = _resolve_repo_root(Path(__file__).resolve())
    canonical_value = args.canonical_path_alias or args.canonical_path
    canonical_path = _resolve_path(repo_root, canonical_value)
    primary_target = _resolve_path(repo_root, args.target)
    target_items: list[tuple[str, Path]] = [("TARGET1", primary_target)]
    if not args.no_secondary_target and args.secondary_target:
        secondary_target = _resolve_path(repo_root, args.secondary_target)
        if secondary_target != primary_target:
            target_items.append(("TARGET2", secondary_target))

    if args.mode == "import":
        if len(target_items) > 1:
            print("ABORTED: import mode supports only the primary target.")
            return 1
        return _import_target_to_canonical(
            canonical_path=canonical_path,
            primary_target=primary_target,
            apply=args.apply,
            fail_on_drift=args.fail_on_drift,
        )

    return _export_canonical_to_targets(
        canonical_path=canonical_path,
        target_items=target_items,
        apply=args.apply,
        fail_on_drift=args.fail_on_drift,
        strict_source=args.strict_source,
    )


if __name__ == "__main__":
    raise SystemExit(main())
