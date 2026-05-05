#!/usr/bin/env python3
"""Build Gemini source-card artifacts for Personlighedspsykologi."""

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


def _all_lecture_keys(source_catalog_path: Path) -> list[str]:
    payload = recursive.load_json(source_catalog_path)
    keys: list[str] = []
    for lecture in payload.get("lectures", []):
        if not isinstance(lecture, dict):
            continue
        key = recursive.normalize_lecture_keys(str(lecture.get("lecture_key") or ""))
        keys.extend(key)
    return keys


def _print_result(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lectures", help="Comma-separated lecture keys, e.g. W05L1,W06L1.")
    parser.add_argument("--source-id", action="append", default=[], help="Build one source id; repeatable.")
    parser.add_argument("--all", action="store_true", help="Build source cards for all catalog sources.")
    parser.add_argument("--source-catalog", default=str(recursive.DEFAULT_SOURCE_CATALOG))
    parser.add_argument("--policy-path", default=str(recursive.DEFAULT_POLICY_PATH))
    parser.add_argument("--source-card-dir", default=str(recursive.DEFAULT_SOURCE_CARD_DIR))
    parser.add_argument("--subject-root", default=str(recursive.DEFAULT_SUBJECT_ROOT))
    parser.add_argument("--model", default=recursive.DEFAULT_GEMINI_PREPROCESSING_MODEL)
    parser.add_argument("--force", action="store_true", help="Overwrite existing source cards.")
    parser.add_argument("--skip-existing", dest="skip_existing", action="store_true", default=True)
    parser.add_argument("--no-skip-existing", dest="skip_existing", action="store_false")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    source_catalog_path = _resolve(args.source_catalog)
    lecture_keys = _all_lecture_keys(source_catalog_path) if args.all else recursive.normalize_lecture_keys(args.lectures)
    source_ids = [item.strip() for item in args.source_id if item.strip()]
    if not lecture_keys and not source_ids:
        raise SystemExit("select --all, --lectures, or --source-id")
    result = recursive.build_source_cards(
        repo_root=REPO_ROOT,
        subject_root=_resolve(args.subject_root),
        source_catalog_path=source_catalog_path,
        policy_path=_resolve(args.policy_path),
        source_card_dir=_resolve(args.source_card_dir),
        lecture_keys=lecture_keys,
        source_ids=source_ids,
        force=args.force,
        skip_existing=args.skip_existing,
        dry_run=args.dry_run,
        model=str(args.model),
    )
    _print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

