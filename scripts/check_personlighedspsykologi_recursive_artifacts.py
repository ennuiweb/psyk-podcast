#!/usr/bin/env python3
"""Validate recursive Source Intelligence artifacts and rebuild the coverage index."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from notebooklm_queue import personlighedspsykologi_recursive as recursive


def _resolve(path_value: str | Path) -> Path:
    path = Path(path_value).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-catalog", default=str(recursive.DEFAULT_SOURCE_CATALOG))
    parser.add_argument("--recursive-dir", default=str(recursive.DEFAULT_RECURSIVE_DIR))
    parser.add_argument("--output-path", default=str(recursive.DEFAULT_RECURSIVE_INDEX_PATH))
    parser.add_argument("--allow-partial", action="store_true", help="Do not fail if coverage is incomplete.")
    return parser.parse_args()


def _print_result(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def main() -> int:
    args = _parse_args()
    index = recursive.build_recursive_index(
        repo_root=REPO_ROOT,
        source_catalog_path=_resolve(args.source_catalog),
        recursive_dir=_resolve(args.recursive_dir),
        output_path=_resolve(args.output_path),
    )
    _print_result(index)
    if index["errors"]:
        return 1
    if index.get("fresh", {}).get("stale_artifact_count", 0):
        return 1
    if not args.allow_partial and not all(index["complete"].values()):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
