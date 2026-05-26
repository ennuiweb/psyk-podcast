#!/usr/bin/env python3
"""Export NotebookLM source packs for high-priority flashcard coverage gaps."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from notebooklm_queue.json_artifact_utils import write_json_stably
from notebooklm_queue.personlighedspsykologi_notebooklm_gap_repair import (
    DEFAULT_GAP_REPAIR_RUN_ID,
    DEFAULT_PLAN_JSON,
    DEFAULT_PLAN_MD,
    DEFAULT_SOURCE_NOTES_INDEX_PATH,
    DEFAULT_SOURCE_NOTES_REGISTRY_PATH,
    DEFAULT_OUTPUT_JSON,
    DEFAULT_MATRIX_PATH,
    DEFAULT_LAB_ROOT,
    GAP_REPAIR_SPECS,
    GapRepairError,
    build_gap_repair_plan,
    export_gap_repair_run,
    render_gap_repair_plan_markdown,
    _load_json,
)
from notebooklm_queue.personlighedspsykologi_notebooklm_flashcard_lab import load_matrix, manifest_digest


def _resolve_repo_path(path: Path, repo_root: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--run-id", default=DEFAULT_GAP_REPAIR_RUN_ID)
    parser.add_argument("--lab-root", type=Path, default=DEFAULT_LAB_ROOT)
    parser.add_argument("--matrix-path", type=Path, default=DEFAULT_MATRIX_PATH)
    parser.add_argument("--coverage-report-path", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--source-notes-index-path", type=Path, default=DEFAULT_SOURCE_NOTES_INDEX_PATH)
    parser.add_argument("--source-notes-registry-path", type=Path, default=DEFAULT_SOURCE_NOTES_REGISTRY_PATH)
    parser.add_argument("--plan-json", type=Path, default=DEFAULT_PLAN_JSON)
    parser.add_argument("--plan-md", type=Path, default=DEFAULT_PLAN_MD)
    parser.add_argument(
        "--notebook-slug",
        action="append",
        default=[],
        choices=[spec.slug for spec in GAP_REPAIR_SPECS],
        help="Export only a selected repair notebook. Repeatable.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Build and validate without writing committed plan files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    matrix_path = _resolve_repo_path(args.matrix_path, repo_root)
    coverage_report_path = _resolve_repo_path(args.coverage_report_path, repo_root)
    source_notes_index_path = _resolve_repo_path(args.source_notes_index_path, repo_root)
    source_notes_registry_path = _resolve_repo_path(args.source_notes_registry_path, repo_root)
    lab_root = _resolve_repo_path(args.lab_root, repo_root)
    try:
        matrix = load_matrix(matrix_path)
        coverage_report = _load_json(coverage_report_path)
        source_notes_index = _load_json(source_notes_index_path)
        source_notes_registry = _load_json(source_notes_registry_path)
        plan = build_gap_repair_plan(
            matrix=matrix,
            coverage_report=coverage_report,
            notes_index=source_notes_index,
            notes_registry=source_notes_registry,
            run_id=args.run_id,
        )
        manifest = export_gap_repair_run(
            run_id=args.run_id,
            lab_root=lab_root,
            matrix_path=matrix_path,
            coverage_report_path=coverage_report_path,
            source_notes_index_path=source_notes_index_path,
            source_notes_registry_path=source_notes_registry_path,
            repo_root=repo_root,
            notebook_slugs=set(args.notebook_slug) or None,
        )
    except (GapRepairError, OSError) as exc:
        raise SystemExit(f"NotebookLM gap-repair export failed: {exc}") from exc
    if not args.dry_run:
        plan_json = _resolve_repo_path(args.plan_json, repo_root)
        plan_md = _resolve_repo_path(args.plan_md, repo_root)
        plan, _ = write_json_stably(plan_json, plan)
        plan_md.parent.mkdir(parents=True, exist_ok=True)
        plan_md.write_text(render_gap_repair_plan_markdown(plan), encoding="utf-8")
    print(
        f"exported {len(manifest.get('notebooks', []))} NotebookLM gap-repair pack(s) "
        f"for run {manifest.get('run_id')} (digest={manifest_digest(manifest)[:12]})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
