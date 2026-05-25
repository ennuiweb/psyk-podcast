#!/usr/bin/env python3
"""Export processed source packs for NotebookLM flashcard-candidate notebooks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from notebooklm_queue.json_artifact_utils import render_json
from notebooklm_queue.personlighedspsykologi_notebooklm_flashcard_lab import (
    DEFAULT_DECK_PATH,
    DEFAULT_LAB_ROOT,
    DEFAULT_MATRIX_PATH,
    PILOT_NOTEBOOK_SLUG,
    FlashcardLabError,
    default_run_id,
    export_lab_run,
    manifest_digest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--run-id", default=None, help="Stable run ID. Defaults to a timestamped ID.")
    parser.add_argument("--lab-root", type=Path, default=DEFAULT_LAB_ROOT)
    parser.add_argument("--matrix-path", type=Path, default=DEFAULT_MATRIX_PATH)
    parser.add_argument("--deck-path", type=Path, default=DEFAULT_DECK_PATH)
    parser.add_argument(
        "--notebook-slug",
        action="append",
        default=[],
        help="Export one NotebookLM pack by slug. Repeatable.",
    )
    parser.add_argument(
        "--pilot-only",
        action="store_true",
        help=f"Export only the pilot notebook ({PILOT_NOTEBOOK_SLUG}).",
    )
    parser.add_argument("--print-manifest", action="store_true", help="Print full manifest JSON.")
    return parser.parse_args()


def _resolve_repo_path(path: Path, repo_root: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    slugs = set(args.notebook_slug)
    if args.pilot_only:
        slugs.add(PILOT_NOTEBOOK_SLUG)
    try:
        manifest = export_lab_run(
            run_id=args.run_id or default_run_id(),
            lab_root=_resolve_repo_path(args.lab_root, repo_root),
            matrix_path=_resolve_repo_path(args.matrix_path, repo_root),
            deck_path=_resolve_repo_path(args.deck_path, repo_root),
            repo_root=repo_root,
            notebook_slugs=slugs or None,
        )
    except FlashcardLabError as exc:
        raise SystemExit(f"NotebookLM flashcard pack export failed: {exc}") from exc
    if args.print_manifest:
        print(render_json(manifest), end="")
    else:
        print(
            f"exported {len(manifest.get('notebooks', []))} NotebookLM flashcard pack(s) "
            f"for run {manifest.get('run_id')} (digest={manifest_digest(manifest)[:12]})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
