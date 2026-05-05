#!/usr/bin/env python3
"""Generate printable Gemini reading scaffolds for Personlighedspsykologi."""

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
from notebooklm_queue import personlighedspsykologi_scaffolding as scaffolding
from notebooklm_queue.gemini_preprocessing import (
    GeminiPreprocessingError,
    has_gemini_api_key,
    preflight_gemini_json_generation,
)


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
    parser.add_argument("--source-id", action="append", default=[], help="Generate one source id; repeatable.")
    parser.add_argument("--all", action="store_true", help="Generate scaffolds for all selected source families.")
    parser.add_argument("--source-family", action="append", default=[], help="Source family filter; default: reading.")
    parser.add_argument("--all-families", action="store_true", help="Do not filter by source family.")
    parser.add_argument("--source-catalog", default=str(scaffolding.DEFAULT_SOURCE_CATALOG))
    parser.add_argument("--source-card-dir", default=str(scaffolding.DEFAULT_SOURCE_CARD_DIR))
    parser.add_argument(
        "--revised-lecture-substrate-dir",
        default=str(scaffolding.DEFAULT_REVISED_LECTURE_SUBSTRATE_DIR),
    )
    parser.add_argument("--course-synthesis-path", default=str(scaffolding.DEFAULT_COURSE_SYNTHESIS_PATH))
    parser.add_argument("--subject-root", default=str(scaffolding.DEFAULT_SUBJECT_ROOT))
    parser.add_argument("--output-root", default=str(scaffolding.DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--model", default=scaffolding.DEFAULT_GEMINI_PREPROCESSING_MODEL)
    parser.add_argument("--force", action="store_true", help="Overwrite existing scaffold artifacts.")
    parser.add_argument("--dry-run", action="store_true", help="Plan work without calling Gemini or writing artifacts.")
    parser.add_argument("--continue-on-error", action="store_true", help="Collect per-source errors instead of stopping.")
    parser.add_argument("--no-pdf", action="store_true", help="Write JSON/Markdown only; skip local PDF rendering.")
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Only check that Gemini JSON generation works for the selected model.",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip the small Gemini JSON preflight before a live run.",
    )
    parser.add_argument("--fail-on-missing-key", action="store_true", help="Fail even in dry-run if Gemini key is absent.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if not has_gemini_api_key():
        if args.dry_run and not args.fail_on_missing_key:
            pass
        else:
            raise SystemExit("GEMINI_API_KEY or GOOGLE_API_KEY is not set")
    if args.preflight_only:
        try:
            preflight_gemini_json_generation(model=str(args.model))
        except GeminiPreprocessingError as exc:
            raise SystemExit(str(exc)) from exc
        _print_result({"status": "ok", "model": str(args.model)})
        return 0

    source_catalog_path = _resolve(args.source_catalog)
    lecture_keys = _all_lecture_keys(source_catalog_path) if args.all else recursive.normalize_lecture_keys(args.lectures)
    source_ids = [item.strip() for item in args.source_id if item.strip()]
    if not lecture_keys and not source_ids:
        raise SystemExit("select --all, --lectures, or --source-id")
    if not args.dry_run and not args.skip_preflight:
        try:
            preflight_gemini_json_generation(model=str(args.model))
        except GeminiPreprocessingError as exc:
            raise SystemExit(str(exc)) from exc

    result = scaffolding.build_scaffolds(
        repo_root=REPO_ROOT,
        subject_root=_resolve(args.subject_root),
        source_catalog_path=source_catalog_path,
        source_card_dir=_resolve(args.source_card_dir),
        revised_lecture_substrate_dir=_resolve(args.revised_lecture_substrate_dir),
        course_synthesis_path=_resolve(args.course_synthesis_path),
        output_root=_resolve(args.output_root),
        lecture_keys=lecture_keys,
        source_ids=source_ids,
        source_families=scaffolding.parse_source_families(
            args.source_family,
            all_families=bool(args.all_families),
        ),
        model=str(args.model),
        render_pdf=not args.no_pdf,
        force=args.force,
        dry_run=args.dry_run,
        continue_on_error=args.continue_on_error,
    )
    _print_result(result)
    return 1 if result.get("error_count", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
