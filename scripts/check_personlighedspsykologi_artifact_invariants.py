#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

SHOW_DIR = Path("shows/personlighedspsykologi-en")
NOTEBOOKLM_DIR = Path("notebooklm-podcast-auto/personlighedspsykologi")

CANONICAL_CONFIG = SHOW_DIR / "config.github.json"
COMPAT_CONFIG = SHOW_DIR / "config.local.json"
PRIMARY_READING_KEY = SHOW_DIR / "docs" / "reading-file-key.md"
LEGACY_READING_KEY = NOTEBOOKLM_DIR / "docs" / "reading-file-key.md"
PRIMARY_OVERBLIK = SHOW_DIR / "docs" / "overblik.md"
LEGACY_OVERBLIK = NOTEBOOKLM_DIR / "docs" / "overblik.md"
SOURCE_CATALOG = SHOW_DIR / "source_catalog.json"
LECTURE_BUNDLES_DIR = SHOW_DIR / "lecture_bundles"
LECTURE_BUNDLE_INDEX = LECTURE_BUNDLES_DIR / "index.json"
CONTENT_MANIFEST = SHOW_DIR / "content_manifest.json"

REFERENCE_FILES = [
    SHOW_DIR / "README.md",
    SHOW_DIR / "docs" / "README.md",
    SHOW_DIR / "docs" / "plan.md",
    SHOW_DIR / "docs" / "podcast-flow-artifacts.md",
    SHOW_DIR / "docs" / "podcast-flow-operations.md",
    SHOW_DIR / "docs" / "reading-name-sources-report-2026-03-05.md",
    NOTEBOOKLM_DIR / "README.md",
    NOTEBOOKLM_DIR / "docs" / "quiz-difficulty-overview-plan.md",
    "TECHNICAL.md",
]

FORBIDDEN_REFERENCES = {
    str(LEGACY_READING_KEY): "legacy NotebookLM reading-file-key mirror reference",
    str(LEGACY_OVERBLIK): "legacy NotebookLM overblik mirror reference",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _failures(repo_root: Path) -> list[str]:
    failures: list[str] = []
    canonical_config = repo_root / CANONICAL_CONFIG
    compat_config = repo_root / COMPAT_CONFIG
    primary_reading_key = repo_root / PRIMARY_READING_KEY
    legacy_reading_key = repo_root / LEGACY_READING_KEY
    primary_overblik = repo_root / PRIMARY_OVERBLIK
    legacy_overblik = repo_root / LEGACY_OVERBLIK
    source_catalog = repo_root / SOURCE_CATALOG
    lecture_bundle_index = repo_root / LECTURE_BUNDLE_INDEX
    lecture_bundles_dir = repo_root / LECTURE_BUNDLES_DIR
    content_manifest = repo_root / CONTENT_MANIFEST

    if not canonical_config.exists():
        failures.append(f"Missing canonical config: {CANONICAL_CONFIG}")
    if not compat_config.exists():
        failures.append(f"Missing compatibility config: {COMPAT_CONFIG}")
    if canonical_config.exists() and compat_config.exists():
        if _load_json(canonical_config) != _load_json(compat_config):
            failures.append(
                "Compatibility config diverged from canonical config: "
                f"{COMPAT_CONFIG} != {CANONICAL_CONFIG}"
            )

    if not primary_reading_key.exists():
        failures.append(f"Missing canonical reading-file-key mirror: {PRIMARY_READING_KEY}")
    if legacy_reading_key.exists():
        failures.append(f"Legacy reading-file-key mirror should be absent: {LEGACY_READING_KEY}")

    if not primary_overblik.exists():
        failures.append(f"Missing canonical overblik doc: {PRIMARY_OVERBLIK}")
    if legacy_overblik.exists():
        failures.append(f"Legacy overblik mirror should be absent: {LEGACY_OVERBLIK}")

    if not source_catalog.exists():
        failures.append(f"Missing source catalog: {SOURCE_CATALOG}")
    if not lecture_bundles_dir.exists():
        failures.append(f"Missing lecture bundles directory: {LECTURE_BUNDLES_DIR}")
    if not lecture_bundle_index.exists():
        failures.append(f"Missing lecture bundle index: {LECTURE_BUNDLE_INDEX}")

    if source_catalog.exists() and lecture_bundle_index.exists() and content_manifest.exists():
        source_catalog_payload = _load_json(source_catalog)
        lecture_bundle_index_payload = _load_json(lecture_bundle_index)
        content_manifest_payload = _load_json(content_manifest)

        source_catalog_lectures = source_catalog_payload.get("lectures") if isinstance(source_catalog_payload, dict) else None
        manifest_lectures = content_manifest_payload.get("lectures") if isinstance(content_manifest_payload, dict) else None
        bundle_entries = lecture_bundle_index_payload.get("bundles") if isinstance(lecture_bundle_index_payload, dict) else None
        bundle_stats = lecture_bundle_index_payload.get("stats") if isinstance(lecture_bundle_index_payload, dict) else None

        if not isinstance(source_catalog_lectures, list):
            failures.append(f"Source catalog lectures missing or invalid in {SOURCE_CATALOG}")
        if not isinstance(manifest_lectures, list):
            failures.append(f"Content manifest lectures missing or invalid in {CONTENT_MANIFEST}")
        if not isinstance(bundle_entries, list):
            failures.append(f"Lecture bundle index bundles missing or invalid in {LECTURE_BUNDLE_INDEX}")
        if not isinstance(bundle_stats, dict):
            failures.append(f"Lecture bundle index stats missing or invalid in {LECTURE_BUNDLE_INDEX}")

        if (
            isinstance(source_catalog_lectures, list)
            and isinstance(manifest_lectures, list)
            and isinstance(bundle_entries, list)
            and isinstance(bundle_stats, dict)
        ):
            expected_lecture_count = len(manifest_lectures)
            if len(source_catalog_lectures) != expected_lecture_count:
                failures.append(
                    "Source catalog lecture count diverged from content manifest: "
                    f"{len(source_catalog_lectures)} != {expected_lecture_count}"
                )
            if int(bundle_stats.get("lecture_count") or 0) != expected_lecture_count:
                failures.append(
                    "Lecture bundle index lecture count diverged from content manifest: "
                    f"{bundle_stats.get('lecture_count')} != {expected_lecture_count}"
                )
            ready_count = sum(1 for entry in bundle_entries if isinstance(entry, dict) and entry.get("bundle_status") == "ready")
            partial_count = sum(1 for entry in bundle_entries if isinstance(entry, dict) and entry.get("bundle_status") != "ready")
            if int(bundle_stats.get("ready_bundle_count") or 0) != ready_count:
                failures.append(
                    "Lecture bundle index ready count is inconsistent with bundle entries: "
                    f"{bundle_stats.get('ready_bundle_count')} != {ready_count}"
                )
            if int(bundle_stats.get("partial_bundle_count") or 0) != partial_count:
                failures.append(
                    "Lecture bundle index partial count is inconsistent with bundle entries: "
                    f"{bundle_stats.get('partial_bundle_count')} != {partial_count}"
                )
            for entry in bundle_entries:
                if not isinstance(entry, dict):
                    failures.append(f"Invalid lecture bundle entry in {LECTURE_BUNDLE_INDEX}")
                    continue
                lecture_key = str(entry.get("lecture_key") or "").strip()
                relative_path = str(entry.get("relative_path") or "").strip()
                if not lecture_key:
                    failures.append(f"Lecture bundle entry missing lecture_key in {LECTURE_BUNDLE_INDEX}")
                    continue
                expected_bundle_path = lecture_bundles_dir / f"{lecture_key}.json"
                if relative_path and relative_path != expected_bundle_path.name:
                    failures.append(
                        "Lecture bundle entry path mismatch: "
                        f"{lecture_key} -> {relative_path} != {expected_bundle_path.name}"
                    )
                if not expected_bundle_path.exists():
                    failures.append(f"Missing lecture bundle file: {LECTURE_BUNDLES_DIR / expected_bundle_path.name}")

    for relative_path in REFERENCE_FILES:
        path = repo_root / relative_path
        if not path.exists():
            failures.append(f"Reference file missing: {relative_path}")
            continue
        content = path.read_text(encoding="utf-8")
        for forbidden, description in FORBIDDEN_REFERENCES.items():
            if forbidden in content:
                failures.append(f"{description} still present in {relative_path}")

    return failures


def main() -> int:
    repo_root = _repo_root()
    failures = _failures(repo_root)
    if failures:
        for item in failures:
            print(f"FAIL: {item}")
        return 1
    print("OK: Personlighedspsykologi artifact invariants hold.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
