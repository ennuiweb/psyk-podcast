#!/usr/bin/env python3
"""Bootstrap a printout review run without touching production outputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import scaffold_engine
from notebooklm_queue import personlighedspsykologi_recursive as recursive
from notebooklm_queue.source_intelligence_schemas import utc_now_iso

DEFAULT_EVALUATION_ROOT = REPO_ROOT / "notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review"
DEFAULT_CANONICAL_OUTPUT_ROOT = REPO_ROOT / "notebooklm-podcast-auto/personlighedspsykologi/output"
DEFAULT_VARIANT_KEY = "problem_driven_v1"
DEFAULT_VARIANT_PROMPT_PATH = (
    REPO_ROOT
    / "notebooklm-podcast-auto/personlighedspsykologi/evaluation/printout_review/prompts/problem-driven-v1.md"
)


def _resolve(path_value: str | Path) -> Path:
    path = Path(path_value).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _all_lecture_keys(source_catalog_path: Path) -> list[str]:
    payload = recursive.load_json(source_catalog_path)
    keys: list[str] = []
    for lecture in payload.get("lectures", []):
        if isinstance(lecture, dict):
            keys.extend(recursive.normalize_lecture_keys(str(lecture.get("lecture_key") or "")))
    return keys


def _relative_to(base: Path, target: Path) -> str:
    try:
        return str(target.relative_to(base))
    except ValueError:
        return str(target)


def _note_stub(entry: dict[str, Any]) -> str:
    source_id = str(entry.get("source_id") or "")
    lecture_key = str(entry.get("lecture_key") or "")
    title = str(entry.get("title") or "")
    return "\n".join(
        [
            f"# {source_id}",
            "",
            f"- Lecture: `{lecture_key}`",
            f"- Title: `{title}`",
            f"- Baseline JSON: `{entry['baseline']['json_path']}`",
            f"- Candidate JSON: `{entry['candidate']['json_path']}`",
            "",
            "## Review Notes",
            "",
            "- Start friction:",
            "- Best reward loop moment:",
            "- Places attention likely drops:",
            "- Strong sections:",
            "- Weak sections:",
            "- Comparison to baseline:",
            "- Recommendation:",
            "",
        ]
    )


def _build_manifest(
    *,
    run_name: str,
    run_dir: Path,
    candidate_output_root: Path,
    canonical_output_root: Path,
    variant_prompt_path: Path,
    selection_summary: dict[str, Any],
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    now = utc_now_iso()
    entries: list[dict[str, Any]] = []
    for source in sources:
        source_id = str(source.get("source_id") or "").strip()
        baseline_dir = scaffold_engine.output_dir_for_source(canonical_output_root, source)
        candidate_dir = scaffold_engine.output_dir_for_source(candidate_output_root, source)
        note_rel = f"notes/{source_id}.md"
        entry = {
            "source_id": source_id,
            "lecture_key": str(source.get("lecture_key") or ""),
            "title": str(source.get("title") or ""),
            "source_family": str(source.get("source_family") or ""),
            "baseline": {
                "output_dir": str(baseline_dir.resolve()),
                "json_path": str((baseline_dir / "reading-scaffolds.json").resolve()),
                "exists": (baseline_dir / "reading-scaffolds.json").exists(),
            },
            "candidate": {
                "status": "pending",
                "output_dir": _relative_to(run_dir, candidate_dir),
                "json_path": _relative_to(run_dir, candidate_dir / "reading-scaffolds.json"),
                "markdown_paths": [],
                "pdf_paths": [],
                "prompt_capture_paths": {
                    "system": f"prompts/{source_id}.system.txt",
                    "user": f"prompts/{source_id}.user.txt",
                },
                "error": "",
            },
            "review": {
                "notes_path": note_rel,
            },
        }
        entries.append(entry)
        note_path = run_dir / note_rel
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(_note_stub(entry) + "\n", encoding="utf-8")
    return {
        "schema_version": 1,
        "run_name": run_name,
        "variant": DEFAULT_VARIANT_KEY,
        "variant_prompt_path": _relative_to(REPO_ROOT, variant_prompt_path),
        "created_at": now,
        "updated_at": now,
        "status": "planned",
        "candidate_output_root": str(candidate_output_root.resolve()),
        "canonical_output_root": str(canonical_output_root.resolve()),
        "selection": selection_summary,
        "summary": {
            "source_count": len(entries),
            "written_count": 0,
            "rerendered_count": 0,
            "skipped_count": 0,
            "error_count": 0,
        },
        "entries": entries,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-name", required=True, help="Name of the review run directory.")
    parser.add_argument("--lectures", help="Comma-separated lecture keys, e.g. W05L1,W06L1.")
    parser.add_argument("--source-id", action="append", default=[], help="Select one source id; repeatable.")
    parser.add_argument("--all", action="store_true", help="Select all sources across chosen families.")
    parser.add_argument("--source-family", action="append", default=[], help="Source family filter; default: reading.")
    parser.add_argument("--all-families", action="store_true", help="Do not filter by source family.")
    parser.add_argument("--evaluation-root", default=str(DEFAULT_EVALUATION_ROOT))
    parser.add_argument("--source-catalog", default=str(scaffold_engine.DEFAULT_SOURCE_CATALOG))
    parser.add_argument("--canonical-output-root", default=str(DEFAULT_CANONICAL_OUTPUT_ROOT))
    parser.add_argument("--variant-prompt", default=str(DEFAULT_VARIANT_PROMPT_PATH))
    parser.add_argument("--force", action="store_true", help="Overwrite an existing manifest and note files.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    evaluation_root = _resolve(args.evaluation_root)
    run_dir = evaluation_root / "runs" / args.run_name
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists() and not args.force:
        raise SystemExit(f"manifest already exists: {manifest_path}")
    source_catalog_path = _resolve(args.source_catalog)
    lecture_keys = _all_lecture_keys(source_catalog_path) if args.all else recursive.normalize_lecture_keys(args.lectures)
    source_ids = [item.strip() for item in args.source_id if item.strip()]
    if not lecture_keys and not source_ids:
        raise SystemExit("select --all, --lectures, or --source-id")
    sources = scaffold_engine.select_sources(
        source_catalog_path=source_catalog_path,
        lecture_keys=lecture_keys,
        source_ids=source_ids,
        source_families=scaffold_engine.parse_source_families(
            args.source_family,
            all_families=bool(args.all_families),
        ),
    )
    candidate_output_root = run_dir / "candidate_output"
    manifest = _build_manifest(
        run_name=args.run_name,
        run_dir=run_dir,
        candidate_output_root=candidate_output_root,
        canonical_output_root=_resolve(args.canonical_output_root),
        variant_prompt_path=_resolve(args.variant_prompt),
        selection_summary={
            "lectures": lecture_keys,
            "source_ids": source_ids,
            "all": bool(args.all),
            "source_families": sorted(
                scaffold_engine.parse_source_families(
                    args.source_family,
                    all_families=bool(args.all_families),
                )
                or []
            ),
        },
        sources=sources,
    )
    _write_json(manifest_path, manifest)
    print(
        json.dumps(
            {
                "status": "planned",
                "run_name": args.run_name,
                "source_count": len(sources),
                "manifest_path": str(manifest_path),
                "candidate_output_root": str(candidate_output_root),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
