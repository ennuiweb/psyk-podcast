#!/usr/bin/env python3
"""Build deterministic cards for remaining personlighedspsykologi coverage gaps."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from notebooklm_queue.json_artifact_utils import write_json_stably
from notebooklm_queue.personlighedspsykologi_coverage_closure_flashcards import (
    DEFAULT_COVERAGE_CLOSURE_JSON,
    DEFAULT_COVERAGE_CLOSURE_MD,
    CoverageClosureError,
    _load_json,
    build_coverage_closure_artifact,
    load_coverage_closure_artifact,
    render_coverage_closure_markdown,
)
from notebooklm_queue.personlighedspsykologi_flashcard_coverage import DEFAULT_OUTPUT_JSON
from notebooklm_queue.personlighedspsykologi_notebooklm_flashcard_lab import DEFAULT_MATRIX_PATH, load_matrix


def _resolve_repo_path(path: Path, repo_root: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--matrix-path", type=Path, default=DEFAULT_MATRIX_PATH)
    parser.add_argument("--coverage-report-path", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_COVERAGE_CLOSURE_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_COVERAGE_CLOSURE_MD)
    parser.add_argument("--dry-run", action="store_true", help="Build and validate without writing files.")
    parser.add_argument("--validate-only", action="store_true", help="Validate generation without writing files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    matrix_path = _resolve_repo_path(args.matrix_path, repo_root)
    coverage_report_path = _resolve_repo_path(args.coverage_report_path, repo_root)
    output_json = _resolve_repo_path(args.output_json, repo_root)
    output_md = _resolve_repo_path(args.output_md, repo_root)
    reused_existing = False
    try:
        artifact = build_coverage_closure_artifact(
            matrix=load_matrix(matrix_path),
            coverage_report=_load_json(coverage_report_path),
        )
    except CoverageClosureError as exc:
        if "No missing or weak coverage units found" not in str(exc) or not output_json.exists():
            raise SystemExit(f"coverage closure flashcard build failed: {exc}") from exc
        try:
            artifact = load_coverage_closure_artifact(output_json)
            reused_existing = True
        except CoverageClosureError as load_exc:
            raise SystemExit(f"coverage closure flashcard build failed: {load_exc}") from load_exc
    except OSError as exc:
        raise SystemExit(f"coverage closure flashcard build failed: {exc}") from exc

    if not args.dry_run and not args.validate_only:
        if not reused_existing:
            artifact, _ = write_json_stably(output_json, artifact)
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(render_coverage_closure_markdown(artifact), encoding="utf-8")

    stats = artifact.get("stats") if isinstance(artifact.get("stats"), dict) else {}
    action = "reused" if reused_existing else "validated" if args.validate_only else "built"
    print(
        f"{action} coverage-closure flashcards "
        f"(cards={stats.get('card_count')}, fields={stats.get('field_counts')})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
