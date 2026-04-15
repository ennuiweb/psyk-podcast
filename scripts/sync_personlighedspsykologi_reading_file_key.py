#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

DEFAULT_ONEDRIVE_SOURCE = (
    "/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/"
    "Mine dokumenter \U0001F4BE/psykologi/Personlighedspsykologi/.ai/reading-file-key.md"
)
DEFAULT_PRIMARY_TARGET = "shows/personlighedspsykologi-en/docs/reading-file-key.md"
DEFAULT_SECONDARY_TARGET = "notebooklm-podcast-auto/personlighedspsykologi/docs/reading-file-key.md"
GRUNDBOG_CHAPTER_BULLET_RE = re.compile(
    r"^(?P<prefix>\s*-\s*)(?P<title>.+?)\s*→\s*"
    r"(?P<source>Grundbog\s+kapitel\s+\d+\s*-\s*[^.]+\.pdf)"
    r"(?P<suffix>\s*\([^)]*\))?\s*$",
    re.IGNORECASE,
)
SHORT_AND_FULL_NOTE = "(short + full)"


def _sha256_bytes(payload: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(payload)
    return digest.hexdigest()


def _resolve_repo_root(script_path: Path) -> Path:
    for parent in script_path.parents:
        if (parent / ".git").exists():
            return parent
    return script_path.parents[1]


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


def _normalized_source_payload(source: Path) -> tuple[bytes, int]:
    source_payload = source.read_bytes()
    if source.suffix.lower() != ".md":
        return source_payload, 0
    try:
        source_text = source_payload.decode("utf-8")
    except UnicodeDecodeError:
        return source_payload, 0
    normalized_text, changed_count = _normalize_grundbog_bullets(source_text)
    return normalized_text.encode("utf-8"), changed_count


def _status_for_target(source_payload: bytes, target: Path, *, label: str) -> str:
    if not target.exists():
        print(f"{label}_STATUS=missing_target")
        return "missing_target"
    target_payload = target.read_bytes()
    src_hash = _sha256_bytes(source_payload)
    dst_hash = _sha256_bytes(target_payload)
    print(f"{label}_SOURCE_SHA256={src_hash}")
    print(f"{label}_TARGET_SHA256={dst_hash}")
    if src_hash == dst_hash:
        print(f"{label}_STATUS=up_to_date")
        return "up_to_date"
    print(f"{label}_STATUS=out_of_sync")
    return "out_of_sync"


def _copy_file(source_payload: bytes, target: Path, *, label: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source_payload)
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
        help="Deprecated no-op. Backups are no longer created.",
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

    source_payload, normalized_count = _normalized_source_payload(source)
    if normalized_count > 0:
        print(f"SOURCE_NORMALIZED_GRUNDBOG_LINES={normalized_count}")

    statuses: list[tuple[str, Path, str]] = []
    needs_sync = False
    for label, target in target_items:
        status = _status_for_target(source_payload, target, label=label)
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
        _copy_file(source_payload, target, label=label)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
