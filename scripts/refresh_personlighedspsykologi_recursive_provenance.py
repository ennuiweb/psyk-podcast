#!/usr/bin/env python3
"""Refresh dependency provenance for existing recursive Source Intelligence artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) in sys.path:
    sys.path.remove(str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT))

from notebooklm_queue import personlighedspsykologi_recursive as recursive


def _resolve(path_value: str | Path) -> Path:
    path = Path(path_value).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject-root", default=str(recursive.DEFAULT_SUBJECT_ROOT))
    parser.add_argument("--source-catalog", default=str(recursive.DEFAULT_SOURCE_CATALOG))
    parser.add_argument("--recursive-dir", default=str(recursive.DEFAULT_RECURSIVE_DIR))
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = recursive.refresh_recursive_provenance(
        repo_root=REPO_ROOT,
        subject_root=_resolve(args.subject_root),
        source_catalog_path=_resolve(args.source_catalog),
        recursive_dir=_resolve(args.recursive_dir),
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if result.get("error_count") else 0


if __name__ == "__main__":
    raise SystemExit(main())
