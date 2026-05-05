#!/usr/bin/env python3
"""Audit structural slide-to-lecture mapping for Personlighedspsykologi.

The audit intentionally does not infer mappings from filenames or inspect slide
content. It only validates that the manual slide catalog is internally
consistent and that content_manifest.json expands multi-lecture mappings
correctly.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT_MANIFEST = "shows/personlighedspsykologi-en/content_manifest.json"
DEFAULT_SLIDES_CATALOG = "shows/personlighedspsykologi-en/slides_catalog.json"
DEFAULT_SUBJECT_ROOT = (
    "/Users/oskar/Library/CloudStorage/OneDrive-Personal/onedrive local/"
    "Mine dokumenter 💾/psykologi/Personlighedspsykologi"
)
VALID_SUBCATEGORIES = {"lecture", "seminar", "exercise"}


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"JSON root must be an object: {path}")
    return payload


def _as_key(value: object) -> str:
    return str(value or "").strip().upper()


def _slide_lecture_keys(slide: dict[str, object]) -> list[str]:
    primary = _as_key(slide.get("lecture_key"))
    raw_keys = slide.get("lecture_keys")
    if isinstance(raw_keys, list) and raw_keys:
        keys = [_as_key(item) for item in raw_keys if _as_key(item)]
    else:
        keys = [primary] if primary else []
    return keys


def _manifest_lecture_keys(manifest: dict[str, object]) -> set[str]:
    lectures = manifest.get("lectures")
    if not isinstance(lectures, list):
        raise SystemExit("content_manifest.json is missing a 'lectures' list")
    return {
        lecture_key
        for lecture in lectures
        if isinstance(lecture, dict)
        for lecture_key in [_as_key(lecture.get("lecture_key"))]
        if lecture_key
    }


def _catalog_expectations(
    *,
    catalog: dict[str, object],
    manifest_keys: set[str],
    subject_root: Path,
) -> tuple[dict[tuple[str, str], dict[str, object]], list[str], list[str]]:
    slides = catalog.get("slides")
    if not isinstance(slides, list):
        raise SystemExit("slides_catalog.json is missing a 'slides' list")

    errors: list[str] = []
    multi: list[str] = []
    expected: dict[tuple[str, str], dict[str, object]] = {}
    seen_keys: set[str] = set()

    for index, raw_slide in enumerate(slides, start=1):
        if not isinstance(raw_slide, dict):
            errors.append(f"catalog[{index}] is not an object")
            continue
        slide_key = str(raw_slide.get("slide_key") or "").strip()
        primary = _as_key(raw_slide.get("lecture_key"))
        lecture_keys = _slide_lecture_keys(raw_slide)
        subcategory = str(raw_slide.get("subcategory") or "").strip().lower()
        source_filename = str(raw_slide.get("source_filename") or "").strip()
        relative_path = str(raw_slide.get("relative_path") or "").strip()
        local_relative_path = str(raw_slide.get("local_relative_path") or "").strip()

        if not slide_key:
            errors.append(f"catalog[{index}] has blank slide_key")
            continue
        if slide_key in seen_keys:
            errors.append(f"{slide_key} | duplicate slide_key")
        seen_keys.add(slide_key)
        if not primary:
            errors.append(f"{slide_key} | blank lecture_key")
        elif primary not in manifest_keys:
            errors.append(f"{slide_key} | unknown primary lecture_key {primary}")
        if not lecture_keys:
            errors.append(f"{slide_key} | blank lecture_keys expansion")
        if lecture_keys and lecture_keys[0] != primary:
            errors.append(f"{slide_key} | lecture_keys must start with primary lecture_key {primary}")
        if primary and primary not in lecture_keys:
            errors.append(f"{slide_key} | lecture_keys does not include primary lecture_key {primary}")
        for lecture_key in lecture_keys:
            if lecture_key not in manifest_keys:
                errors.append(f"{slide_key} | unknown lecture_keys entry {lecture_key}")
        if subcategory not in VALID_SUBCATEGORIES:
            errors.append(f"{slide_key} | invalid subcategory {subcategory!r}")
        if not source_filename:
            errors.append(f"{slide_key} | blank source_filename")
        if not local_relative_path:
            errors.append(f"{slide_key} | blank local_relative_path")
        elif not (subject_root / local_relative_path).exists():
            errors.append(f"{slide_key} | missing local source {local_relative_path}")
        expected_relative_path = f"{primary}/{subcategory}/{source_filename}" if primary and subcategory and source_filename else ""
        if expected_relative_path and relative_path != expected_relative_path:
            errors.append(
                f"{slide_key} | relative_path {relative_path!r} does not match expected {expected_relative_path!r}"
            )
        if len(lecture_keys) > 1:
            multi.append(f"{slide_key} | {', '.join(lecture_keys)} | {subcategory} | {source_filename}")
        for lecture_key in lecture_keys:
            pair = (lecture_key, slide_key)
            if pair in expected:
                errors.append(f"{slide_key} | duplicate expansion for {lecture_key}")
            expected[pair] = raw_slide

    return expected, errors, multi


def _manifest_pairs(manifest: dict[str, object]) -> tuple[dict[tuple[str, str], dict[str, object]], list[str]]:
    lectures = manifest.get("lectures")
    if not isinstance(lectures, list):
        raise SystemExit("content_manifest.json is missing a 'lectures' list")
    pairs: dict[tuple[str, str], dict[str, object]] = {}
    errors: list[str] = []
    for lecture in lectures:
        if not isinstance(lecture, dict):
            continue
        lecture_key = _as_key(lecture.get("lecture_key"))
        slides = lecture.get("slides")
        if not isinstance(slides, list):
            continue
        for raw_slide in slides:
            if not isinstance(raw_slide, dict):
                continue
            slide_key = str(raw_slide.get("slide_key") or "").strip()
            if not slide_key:
                errors.append(f"{lecture_key} | manifest slide has blank slide_key")
                continue
            pair = (lecture_key, slide_key)
            if pair in pairs:
                errors.append(f"{lecture_key} | {slide_key} | duplicate manifest slide entry")
            pairs[pair] = raw_slide
    return pairs, errors


def _compare_manifest_to_catalog(
    *,
    expected: dict[tuple[str, str], dict[str, object]],
    manifest_pairs: dict[tuple[str, str], dict[str, object]],
) -> list[str]:
    errors: list[str] = []
    for pair in sorted(set(expected) - set(manifest_pairs)):
        lecture_key, slide_key = pair
        errors.append(f"{lecture_key} | {slide_key} | missing from content_manifest.json")
    for pair in sorted(set(manifest_pairs) - set(expected)):
        lecture_key, slide_key = pair
        errors.append(f"{lecture_key} | {slide_key} | manifest has slide not present in slides_catalog expansion")

    for pair in sorted(set(expected) & set(manifest_pairs)):
        catalog_slide = expected[pair]
        manifest_slide = manifest_pairs[pair]
        slide_key = pair[1]
        for field in ("subcategory", "title", "source_filename", "relative_path"):
            catalog_value = str(catalog_slide.get(field) or "").strip()
            manifest_value = str(manifest_slide.get(field) or "").strip()
            if catalog_value != manifest_value:
                errors.append(
                    f"{pair[0]} | {slide_key} | manifest {field}={manifest_value!r} differs from catalog {catalog_value!r}"
                )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST, help="Path to content_manifest.json.")
    parser.add_argument("--slides-catalog", default=DEFAULT_SLIDES_CATALOG, help="Path to slides_catalog.json.")
    parser.add_argument("--subject-root", default=DEFAULT_SUBJECT_ROOT, help="OneDrive Personlighedspsykologi root.")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).expanduser().resolve()
    catalog_path = Path(args.slides_catalog).expanduser().resolve()
    subject_root = Path(args.subject_root).expanduser().resolve()

    manifest = _load_json(manifest_path)
    catalog = _load_json(catalog_path)
    manifest_keys = _manifest_lecture_keys(manifest)
    expected, catalog_errors, multi = _catalog_expectations(
        catalog=catalog,
        manifest_keys=manifest_keys,
        subject_root=subject_root,
    )
    manifest_expansion, manifest_errors = _manifest_pairs(manifest)
    compare_errors = _compare_manifest_to_catalog(expected=expected, manifest_pairs=manifest_expansion)

    errors = catalog_errors + manifest_errors + compare_errors
    print(f"catalog_slide_entries={len(catalog.get('slides', [])) if isinstance(catalog.get('slides'), list) else 0}")
    print(f"expected_manifest_slide_links={len(expected)}")
    print(f"actual_manifest_slide_links={len(manifest_expansion)}")
    print(f"multi_lecture_slide_entries={len(multi)}")
    if multi:
        print("\n[multi_lecture_slide_entries]")
        for item in multi:
            print(item)
    if errors:
        print("\n[slide_mapping_errors]")
        for error in errors:
            print(error)
        return 1
    print("\nOK: Personlighedspsykologi slide mapping is structurally clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
