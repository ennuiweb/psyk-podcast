#!/usr/bin/env python3
"""Run the recursive Gemini Source Intelligence pipeline for Personlighedspsykologi."""

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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lectures", help="Comma-separated lecture keys, e.g. W05L1,W06L1.")
    parser.add_argument("--all", action="store_true", help="Run all lectures in source_catalog.json.")
    parser.add_argument("--source-catalog", default=str(recursive.DEFAULT_SOURCE_CATALOG))
    parser.add_argument("--policy-path", default=str(recursive.DEFAULT_POLICY_PATH))
    parser.add_argument("--lecture-bundle-dir", default=str(recursive.DEFAULT_LECTURE_BUNDLE_DIR))
    parser.add_argument("--recursive-dir", default=str(recursive.DEFAULT_RECURSIVE_DIR))
    parser.add_argument("--subject-root", default=str(recursive.DEFAULT_SUBJECT_ROOT))
    parser.add_argument(
        "--no-raw-lecture-source-uploads",
        action="store_true",
        help="Do not attach raw lecture source PDFs in the lecture-substrate Gemini calls.",
    )
    parser.add_argument("--source-weighting-path", default=str(recursive.DEFAULT_SOURCE_WEIGHTING_PATH))
    parser.add_argument("--model", default=recursive.DEFAULT_GEMINI_PREPROCESSING_MODEL)
    parser.add_argument("--force", action="store_true", help="Overwrite existing artifacts.")
    parser.add_argument("--skip-existing", dest="skip_existing", action="store_true", default=True)
    parser.add_argument("--no-skip-existing", dest="skip_existing", action="store_false")
    parser.add_argument("--dry-run", action="store_true", help="Plan work without calling Gemini or writing artifacts.")
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


def _print_result(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def main() -> int:
    args = _parse_args()
    source_catalog_path = _resolve(args.source_catalog)
    lecture_keys = _all_lecture_keys(source_catalog_path) if args.all else recursive.normalize_lecture_keys(args.lectures)
    if not lecture_keys:
        raise SystemExit("select --all or --lectures")
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
    if not args.dry_run and not args.skip_preflight:
        try:
            preflight_gemini_json_generation(model=str(args.model))
        except GeminiPreprocessingError as exc:
            raise SystemExit(str(exc)) from exc

    recursive_dir = _resolve(args.recursive_dir)
    source_card_dir = recursive_dir / "source_cards"
    lecture_substrate_dir = recursive_dir / "lecture_substrates"
    revised_dir = recursive_dir / "revised_lecture_substrates"
    podcast_dir = recursive_dir / "podcast_substrates"
    course_synthesis_path = recursive_dir / "course_synthesis.json"
    index_path = recursive_dir / "index.json"
    partial_scope = not args.all

    results: dict[str, Any] = {
        "lecture_keys": lecture_keys,
        "scope": "partial" if partial_scope else "full",
        "dry_run": bool(args.dry_run),
        "stages": {},
    }

    results["stages"]["source_cards"] = recursive.build_source_cards(
        repo_root=REPO_ROOT,
        subject_root=_resolve(args.subject_root),
        source_catalog_path=source_catalog_path,
        policy_path=_resolve(args.policy_path),
        source_card_dir=source_card_dir,
        lecture_keys=lecture_keys,
        force=args.force,
        skip_existing=args.skip_existing,
        dry_run=args.dry_run,
        model=str(args.model),
    )
    results["stages"]["lecture_substrates"] = recursive.build_lecture_substrates(
        repo_root=REPO_ROOT,
        subject_root=None if args.no_raw_lecture_source_uploads else _resolve(args.subject_root),
        lecture_keys=lecture_keys,
        lecture_bundle_dir=_resolve(args.lecture_bundle_dir),
        source_card_dir=source_card_dir,
        lecture_substrate_dir=lecture_substrate_dir,
        source_catalog_path=source_catalog_path,
        force=args.force,
        skip_existing=args.skip_existing,
        dry_run=args.dry_run,
        model=str(args.model),
    )
    results["stages"]["course_synthesis"] = recursive.build_course_synthesis(
        repo_root=REPO_ROOT,
        lecture_keys=lecture_keys,
        lecture_substrate_dir=lecture_substrate_dir,
        output_path=course_synthesis_path,
        source_catalog_path=source_catalog_path,
        force=args.force,
        dry_run=args.dry_run,
        partial_scope=partial_scope,
        model=str(args.model),
    )
    results["stages"]["revised_lecture_substrates"] = recursive.build_revised_lecture_substrates(
        lecture_keys=lecture_keys,
        lecture_substrate_dir=lecture_substrate_dir,
        course_synthesis_path=course_synthesis_path,
        revised_lecture_substrate_dir=revised_dir,
        force=args.force,
        skip_existing=args.skip_existing,
        dry_run=args.dry_run,
        model=str(args.model),
    )
    results["stages"]["podcast_substrates"] = recursive.build_podcast_substrates(
        lecture_keys=lecture_keys,
        source_card_dir=source_card_dir,
        lecture_bundle_dir=_resolve(args.lecture_bundle_dir),
        revised_lecture_substrate_dir=revised_dir,
        course_synthesis_path=course_synthesis_path,
        podcast_substrate_dir=podcast_dir,
        source_weighting_path=_resolve(args.source_weighting_path),
        force=args.force,
        skip_existing=args.skip_existing,
        dry_run=args.dry_run,
        model=str(args.model),
    )
    if not args.dry_run:
        results["index"] = recursive.build_recursive_index(
            repo_root=REPO_ROOT,
            source_catalog_path=source_catalog_path,
            recursive_dir=recursive_dir,
            output_path=index_path,
        )

    _print_result(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
