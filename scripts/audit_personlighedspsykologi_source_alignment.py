#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from sync_personlighedspsykologi_readings_to_droplet import (  # noqa: E402
    DEFAULT_READING_KEY,
    DEFAULT_SOURCE_ROOT,
    index_week_dirs,
    parse_reading_key,
    resolve_entries,
)

DEFAULT_MANIFEST = "shows/personlighedspsykologi-en/content_manifest.json"
DEFAULT_SLIDES_CATALOG = "shows/personlighedspsykologi-en/slides_catalog.json"
DEFAULT_SUBJECT_ROOT = (
    "/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/"
    "Mine dokumenter 💾/psykologi/Personlighedspsykologi"
)
IGNORED_UNMAPPED_DIR_NAMES = {"alle filer (samlet)", "chatgpt indlæring"}


def _load_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _manifest_reading_records(path: Path) -> list[tuple[str, str, str, str]]:
    payload = _load_json(path)
    if not isinstance(payload, dict):
        raise SystemExit(f"Manifest must be a JSON object: {path}")
    lectures = payload.get("lectures")
    if not isinstance(lectures, list):
        raise SystemExit(f"Manifest is missing a 'lectures' list: {path}")

    records: list[tuple[str, str, str, str]] = []
    for lecture in lectures:
        if not isinstance(lecture, dict):
            continue
        lecture_key = str(lecture.get("lecture_key") or "").strip().upper()
        readings = lecture.get("readings")
        if not lecture_key or not isinstance(readings, list):
            continue
        for item in readings:
            if not isinstance(item, dict) or item.get("is_missing"):
                continue
            reading_key = str(item.get("reading_key") or "").strip()
            title = str(item.get("reading_title") or "").strip()
            source_filename = str(item.get("source_filename") or "").strip()
            if reading_key and title and source_filename:
                records.append((lecture_key, reading_key, title, source_filename))
    return records


def _slides_with_missing_local_sources(path: Path, *, subject_root: Path) -> list[tuple[str, str, str]]:
    payload = _load_json(path)
    if not isinstance(payload, dict):
        raise SystemExit(f"Slides catalog must be a JSON object: {path}")
    slides = payload.get("slides")
    if not isinstance(slides, list):
        raise SystemExit(f"Slides catalog is missing a 'slides' list: {path}")

    missing: list[tuple[str, str, str]] = []
    for item in slides:
        if not isinstance(item, dict):
            continue
        lecture_key = str(item.get("lecture_key") or "").strip().upper()
        subcategory = str(item.get("subcategory") or "").strip().lower()
        local_relative_path = str(item.get("local_relative_path") or "").strip()
        if not lecture_key or not subcategory or not local_relative_path:
            continue
        if not (subject_root / local_relative_path).exists():
            missing.append((lecture_key, subcategory, local_relative_path))
    return missing


def _unexpected_unmapped_reading_pdfs(
    *,
    week_dir_index: dict[str, list[Path]],
    resolved_source_paths: set[Path],
) -> list[Path]:
    unexpected: list[Path] = []
    for week_dirs in week_dir_index.values():
        for week_dir in week_dirs:
            for file_path in sorted(week_dir.rglob("*.pdf"), key=lambda item: str(item).casefold()):
                if any(part.casefold() in IGNORED_UNMAPPED_DIR_NAMES for part in file_path.parts):
                    continue
                if file_path.resolve() not in resolved_source_paths:
                    unexpected.append(file_path)
    return unexpected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reading-key", default=DEFAULT_READING_KEY, help="Path to reading-file-key markdown.")
    parser.add_argument("--source-root", default=DEFAULT_SOURCE_ROOT, help="OneDrive readings source root.")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST, help="Path to content_manifest.json.")
    parser.add_argument("--slides-catalog", default=DEFAULT_SLIDES_CATALOG, help="Path to slides_catalog.json.")
    parser.add_argument("--subject-root", default=DEFAULT_SUBJECT_ROOT, help="OneDrive Personlighedspsykologi root.")
    args = parser.parse_args()

    reading_key_path = Path(args.reading_key).expanduser().resolve()
    source_root = Path(args.source_root).expanduser().resolve()
    manifest_path = Path(args.manifest).expanduser().resolve()
    slides_catalog_path = Path(args.slides_catalog).expanduser().resolve()
    subject_root = Path(args.subject_root).expanduser().resolve()

    reading_entries = parse_reading_key(reading_key_path)
    reading_records = {
        (entry.lecture_key, entry.reading_key, entry.title, entry.source_filename)
        for entry in reading_entries
    }
    manifest_records = set(_manifest_reading_records(manifest_path))

    week_dir_index = index_week_dirs(source_root)
    resolutions, unresolved = resolve_entries(reading_entries, week_dir_index)
    resolved_source_paths = {item.source_path.resolve() for item in resolutions}
    missing_slides = _slides_with_missing_local_sources(slides_catalog_path, subject_root=subject_root)
    unexpected_unmapped = _unexpected_unmapped_reading_pdfs(
        week_dir_index=week_dir_index,
        resolved_source_paths=resolved_source_paths,
    )

    manifest_without_key = sorted(manifest_records - reading_records)
    key_without_manifest = sorted(reading_records - manifest_records)

    print(f"reading_key_entries={len(reading_entries)}")
    print(f"manifest_non_missing_readings={len(manifest_records)}")
    print(f"resolved_readings={len(resolutions)}")
    print(f"unresolved_readings={len(unresolved)}")
    print(f"manifest_without_reading_key={len(manifest_without_key)}")
    print(f"reading_key_without_manifest={len(key_without_manifest)}")
    print(f"missing_slide_sources={len(missing_slides)}")
    print(f"unexpected_unmapped_reading_pdfs={len(unexpected_unmapped)}")

    failures = False

    if unresolved:
        failures = True
        print("\n[unresolved_readings]")
        for item in unresolved:
            print(item)

    if manifest_without_key:
        failures = True
        print("\n[manifest_without_reading_key]")
        for lecture_key, reading_key, title, source_filename in manifest_without_key:
            print(f"{lecture_key} | {reading_key} | {title} | {source_filename}")

    if key_without_manifest:
        failures = True
        print("\n[reading_key_without_manifest]")
        for lecture_key, reading_key, title, source_filename in key_without_manifest:
            print(f"{lecture_key} | {reading_key} | {title} | {source_filename}")

    if missing_slides:
        failures = True
        print("\n[missing_slide_sources]")
        for lecture_key, subcategory, local_relative_path in missing_slides:
            print(f"{lecture_key} | {subcategory} | {local_relative_path}")

    if unexpected_unmapped:
        failures = True
        print("\n[unexpected_unmapped_reading_pdfs]")
        for file_path in unexpected_unmapped:
            print(file_path)

    if failures:
        return 1

    print("\nOK: Personlighedspsykologi source alignment is clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
