#!/usr/bin/env python3
"""Generate problem-driven evaluation scaffolds for Personlighedspsykologi."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from notebooklm_queue import personlighedspsykologi_problem_driven_scaffolding as problem_scaffolding
from notebooklm_queue import personlighedspsykologi_recursive as recursive
from notebooklm_queue import personlighedspsykologi_scaffolding as canonical_scaffolding
from notebooklm_queue.gemini_preprocessing import (
    GeminiPreprocessingError,
    has_gemini_api_key,
    preflight_gemini_json_generation,
)
from notebooklm_queue.source_intelligence_schemas import utc_now_iso


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


def _relative_to(base: Path, target: Path) -> str:
    try:
        return str(target.relative_to(base))
    except ValueError:
        return str(target)


def _candidate_output_root(args: argparse.Namespace, evaluation_root: Path) -> Path:
    if args.output_root:
        return _resolve(args.output_root)
    return evaluation_root / "runs" / args.run_name / "candidate_output"


def _build_manifest(
    *,
    manifest_path: Path,
    run_name: str,
    candidate_output_root: Path,
    canonical_output_root: Path,
    sources: list[dict[str, Any]],
    result: dict[str, Any],
    selection_summary: dict[str, Any],
) -> dict[str, Any]:
    existing = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    now = utc_now_iso()
    result_by_source_id = {
        str(item.get("source_id") or ""): item
        for item in result.get("results", [])
        if isinstance(item, dict)
    }
    error_by_source_id = {
        str(item.get("source_id") or ""): item
        for item in result.get("errors", [])
        if isinstance(item, dict)
    }
    run_dir = manifest_path.parent
    entries: list[dict[str, Any]] = []
    for source in sources:
        source_id = str(source.get("source_id") or "").strip()
        baseline_dir = canonical_scaffolding.output_dir_for_source(canonical_output_root, source)
        baseline_json = baseline_dir / "reading-scaffolds.json"
        candidate_dir = canonical_scaffolding.output_dir_for_source(candidate_output_root, source)
        candidate_json = candidate_dir / "reading-scaffolds.json"
        candidate_result = result_by_source_id.get(source_id, {})
        candidate_error = error_by_source_id.get(source_id, {})
        entries.append(
            {
                "source_id": source_id,
                "lecture_key": str(source.get("lecture_key") or ""),
                "title": str(source.get("title") or ""),
                "source_family": str(source.get("source_family") or ""),
                "baseline": {
                    "output_dir": str(baseline_dir.resolve()),
                    "json_path": str(baseline_json.resolve()),
                    "exists": baseline_json.exists(),
                },
                "candidate": {
                    "status": str(candidate_result.get("status") or ("planned" if result.get("status") == "planned" else "pending")),
                    "output_dir": _relative_to(run_dir, candidate_dir),
                    "json_path": _relative_to(run_dir, candidate_json),
                    "markdown_paths": [
                        _relative_to(run_dir, Path(path))
                        for path in candidate_result.get("markdown_paths", [])
                    ],
                    "pdf_paths": [
                        _relative_to(run_dir, Path(path))
                        for path in candidate_result.get("pdf_paths", [])
                    ],
                    "error": str(candidate_error.get("error") or ""),
                },
            }
        )
    status = "planned" if result.get("status") == "planned" else "error" if result.get("error_count") else "generated"
    return {
        "schema_version": 1,
        "run_name": run_name,
        "variant": problem_scaffolding.VARIANT_KEY,
        "created_at": existing.get("created_at") or now,
        "updated_at": now,
        "status": status,
        "candidate_output_root": str(candidate_output_root.resolve()),
        "canonical_output_root": str(canonical_output_root.resolve()),
        "selection": selection_summary,
        "summary": {
            "source_count": len(sources),
            "written_count": int(result.get("written_count", 0) or 0),
            "rerendered_count": int(result.get("rerendered_count", 0) or 0),
            "skipped_count": int(result.get("skipped_count", 0) or 0),
            "error_count": int(result.get("error_count", 0) or 0),
        },
        "entries": entries,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", required=True, help="Name of the evaluation run directory.")
    parser.add_argument("--lectures", help="Comma-separated lecture keys, e.g. W05L1,W06L1.")
    parser.add_argument("--source-id", action="append", default=[], help="Generate one source id; repeatable.")
    parser.add_argument("--all", action="store_true", help="Generate scaffolds for all selected source families.")
    parser.add_argument("--source-family", action="append", default=[], help="Source family filter; default: reading.")
    parser.add_argument("--all-families", action="store_true", help="Do not filter by source family.")
    parser.add_argument("--evaluation-root", default=str(problem_scaffolding.DEFAULT_EVALUATION_ROOT))
    parser.add_argument("--source-catalog", default=str(problem_scaffolding.DEFAULT_SOURCE_CATALOG))
    parser.add_argument("--source-card-dir", default=str(problem_scaffolding.DEFAULT_SOURCE_CARD_DIR))
    parser.add_argument(
        "--revised-lecture-substrate-dir",
        default=str(problem_scaffolding.DEFAULT_REVISED_LECTURE_SUBSTRATE_DIR),
    )
    parser.add_argument("--course-synthesis-path", default=str(problem_scaffolding.DEFAULT_COURSE_SYNTHESIS_PATH))
    parser.add_argument("--subject-root", default=str(problem_scaffolding.DEFAULT_SUBJECT_ROOT))
    parser.add_argument(
        "--canonical-output-root",
        default=str(canonical_scaffolding.DEFAULT_OUTPUT_ROOT),
        help="Canonical scaffold output root used for baseline references in the manifest.",
    )
    parser.add_argument(
        "--output-root",
        help="Optional override for candidate output root; default is <evaluation-root>/runs/<run-name>/candidate_output.",
    )
    parser.add_argument("--model", default=problem_scaffolding.DEFAULT_GEMINI_PREPROCESSING_MODEL)
    parser.add_argument("--force", action="store_true", help="Overwrite existing candidate scaffold artifacts.")
    parser.add_argument(
        "--rerender-existing",
        action="store_true",
        help="Normalize and rerender existing candidate JSON artifacts without calling Gemini unless --force is also set.",
    )
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
    live_generation = not args.dry_run and not (args.rerender_existing and not args.force)
    if live_generation and not has_gemini_api_key():
        if args.dry_run and not args.fail_on_missing_key:
            pass
        else:
            raise SystemExit("GEMINI_API_KEY or GOOGLE_API_KEY is not set")
    if args.preflight_only:
        try:
            preflight_gemini_json_generation(model=str(args.model))
        except GeminiPreprocessingError as exc:
            raise SystemExit(str(exc)) from exc
        _print_result({"status": "ok", "model": str(args.model), "variant": problem_scaffolding.VARIANT_KEY})
        return 0

    evaluation_root = _resolve(args.evaluation_root)
    source_catalog_path = _resolve(args.source_catalog)
    candidate_output_root = _candidate_output_root(args, evaluation_root)
    manifest_path = evaluation_root / "runs" / args.run_name / "manifest.json"
    lecture_keys = _all_lecture_keys(source_catalog_path) if args.all else recursive.normalize_lecture_keys(args.lectures)
    source_ids = [item.strip() for item in args.source_id if item.strip()]
    if not lecture_keys and not source_ids:
        raise SystemExit("select --all, --lectures, or --source-id")
    if live_generation and not args.skip_preflight:
        try:
            preflight_gemini_json_generation(model=str(args.model))
        except GeminiPreprocessingError as exc:
            raise SystemExit(str(exc)) from exc

    selected_sources = problem_scaffolding.select_sources(
        source_catalog_path=source_catalog_path,
        lecture_keys=lecture_keys,
        source_ids=source_ids,
        source_families=problem_scaffolding.parse_source_families(
            args.source_family,
            all_families=bool(args.all_families),
        ),
    )
    result = problem_scaffolding.build_scaffolds(
        repo_root=REPO_ROOT,
        subject_root=_resolve(args.subject_root),
        source_catalog_path=source_catalog_path,
        source_card_dir=_resolve(args.source_card_dir),
        revised_lecture_substrate_dir=_resolve(args.revised_lecture_substrate_dir),
        course_synthesis_path=_resolve(args.course_synthesis_path),
        output_root=candidate_output_root,
        lecture_keys=lecture_keys,
        source_ids=source_ids,
        source_families=problem_scaffolding.parse_source_families(
            args.source_family,
            all_families=bool(args.all_families),
        ),
        model=str(args.model),
        render_pdf=not args.no_pdf,
        force=args.force,
        rerender_existing=args.rerender_existing,
        dry_run=args.dry_run,
        continue_on_error=args.continue_on_error,
    )
    manifest = _build_manifest(
        manifest_path=manifest_path,
        run_name=args.run_name,
        candidate_output_root=candidate_output_root,
        canonical_output_root=_resolve(args.canonical_output_root),
        sources=selected_sources,
        result=result,
        selection_summary={
            "lectures": lecture_keys,
            "source_ids": source_ids,
            "all": bool(args.all),
            "source_families": sorted(
                problem_scaffolding.parse_source_families(
                    args.source_family,
                    all_families=bool(args.all_families),
                )
                or []
            ),
        },
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    result["manifest_path"] = str(manifest_path)
    result["candidate_output_root"] = str(candidate_output_root)
    _print_result(result)
    return 1 if result.get("error_count", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
