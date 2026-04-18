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
