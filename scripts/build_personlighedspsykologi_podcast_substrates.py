#!/usr/bin/env python3
"""Build compact NotebookLM podcast substrates for Personlighedspsykologi."""

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
        if isinstance(lecture, dict):
            keys.extend(recursive.normalize_lecture_keys(str(lecture.get("lecture_key") or "")))
    return keys


def _print_result(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lectures", help="Comma-separated lecture keys, e.g. W05L1,W06L1.")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--source-catalog", default=str(recursive.DEFAULT_SOURCE_CATALOG))
    parser.add_argument("--source-card-dir", default=str(recursive.DEFAULT_SOURCE_CARD_DIR))
    parser.add_argument("--lecture-bundle-dir", default=str(recursive.DEFAULT_LECTURE_BUNDLE_DIR))
    parser.add_argument("--revised-lecture-substrate-dir", default=str(recursive.DEFAULT_REVISED_LECTURE_SUBSTRATE_DIR))
    parser.add_argument("--course-synthesis-path", default=str(recursive.DEFAULT_COURSE_SYNTHESIS_PATH))
    parser.add_argument("--podcast-substrate-dir", default=str(recursive.DEFAULT_PODCAST_SUBSTRATE_DIR))
    parser.add_argument("--source-weighting-path", default=str(recursive.DEFAULT_SOURCE_WEIGHTING_PATH))
    parser.add_argument("--model", default=recursive.DEFAULT_GEMINI_PREPROCESSING_MODEL)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-existing", dest="skip_existing", action="store_true", default=True)
    parser.add_argument("--no-skip-existing", dest="skip_existing", action="store_false")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true", help="Collect per-lecture errors instead of stopping at the first failure.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    source_catalog_path = _resolve(args.source_catalog)
    lecture_keys = _all_lecture_keys(source_catalog_path) if args.all else recursive.normalize_lecture_keys(args.lectures)
    if not lecture_keys:
        raise SystemExit("select --all or --lectures")
    result = recursive.build_podcast_substrates(
        lecture_keys=lecture_keys,
        source_card_dir=_resolve(args.source_card_dir),
        lecture_bundle_dir=_resolve(args.lecture_bundle_dir),
        revised_lecture_substrate_dir=_resolve(args.revised_lecture_substrate_dir),
        course_synthesis_path=_resolve(args.course_synthesis_path),
        podcast_substrate_dir=_resolve(args.podcast_substrate_dir),
        source_weighting_path=_resolve(args.source_weighting_path),
        force=args.force,
        skip_existing=args.skip_existing,
        dry_run=args.dry_run,
        continue_on_error=args.continue_on_error,
        model=str(args.model),
    )
    _print_result(result)
    return 1 if result.get("error_count", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
