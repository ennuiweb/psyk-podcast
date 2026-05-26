#!/usr/bin/env python3
"""Run targeted NotebookLM generation for high-priority flashcard coverage gaps."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from notebooklm_queue.json_artifact_utils import write_json_stably
from notebooklm_queue.personlighedspsykologi_notebooklm_flashcard_lab import (
    DEFAULT_LAB_ROOT,
    FlashcardLabError,
    load_current_deck,
    load_matrix,
)
from notebooklm_queue.personlighedspsykologi_notebooklm_gap_repair import (
    DEFAULT_DECK_PATH,
    DEFAULT_GAP_REPAIR_RUN_ID,
    DEFAULT_MATRIX_PATH,
    DEFAULT_OUTPUT_JSON,
    DEFAULT_SOURCE_NOTES_INDEX_PATH,
    DEFAULT_SOURCE_NOTES_REGISTRY_PATH,
    GAP_REPAIR_SPECS,
    GapRepairError,
    export_gap_repair_run,
)
from run_personlighedspsykologi_notebooklm_flashcard_pilot import (
    DEFAULT_NOTEBOOKLM_CLI,
    NotebookLMRunner,
    _process_notebook,
    _repo_relative,
    _resolve_repo_path,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--run-id", default=DEFAULT_GAP_REPAIR_RUN_ID)
    parser.add_argument("--lab-root", type=Path, default=DEFAULT_LAB_ROOT)
    parser.add_argument("--matrix-path", type=Path, default=DEFAULT_MATRIX_PATH)
    parser.add_argument("--deck-path", type=Path, default=DEFAULT_DECK_PATH)
    parser.add_argument("--coverage-report-path", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--source-notes-index-path", type=Path, default=DEFAULT_SOURCE_NOTES_INDEX_PATH)
    parser.add_argument("--source-notes-registry-path", type=Path, default=DEFAULT_SOURCE_NOTES_REGISTRY_PATH)
    parser.add_argument("--notebooklm-cli", type=Path, default=DEFAULT_NOTEBOOKLM_CLI)
    parser.add_argument("--profile", default=None, help="NotebookLM profile to pass with -p.")
    parser.add_argument("--storage", type=Path, default=None, help="NotebookLM storage_state.json to pass with --storage.")
    parser.add_argument(
        "--notebook-slug",
        action="append",
        default=None,
        choices=[spec.slug for spec in GAP_REPAIR_SPECS],
        help="Notebook slug to run. Repeat for multiple. Defaults to all repair notebooks.",
    )
    parser.add_argument(
        "--notebook-id",
        default=None,
        help="Existing notebook ID. Allowed only when exactly one notebook slug is selected.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Export packs and print intended NotebookLM steps only.")
    return parser.parse_args()


def _selected_slugs(args: argparse.Namespace) -> set[str] | None:
    if args.notebook_slug:
        slugs = set(args.notebook_slug)
    else:
        slugs = None
    if args.notebook_id and (slugs is None or len(slugs) != 1):
        raise FlashcardLabError("--notebook-id can only be used when one repair notebook slug is selected")
    return slugs


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    lab_root = _resolve_repo_path(args.lab_root, repo_root)
    notebooklm_cli = _resolve_repo_path(args.notebooklm_cli, repo_root)
    storage = _resolve_repo_path(args.storage, repo_root) if args.storage else None
    try:
        selected_slugs = _selected_slugs(args)
        manifest = export_gap_repair_run(
            run_id=args.run_id,
            lab_root=lab_root,
            matrix_path=_resolve_repo_path(args.matrix_path, repo_root),
            coverage_report_path=_resolve_repo_path(args.coverage_report_path, repo_root),
            source_notes_index_path=_resolve_repo_path(args.source_notes_index_path, repo_root),
            source_notes_registry_path=_resolve_repo_path(args.source_notes_registry_path, repo_root),
            repo_root=repo_root,
            notebook_slugs=selected_slugs,
        )
    except (FlashcardLabError, GapRepairError) as exc:
        raise SystemExit(f"NotebookLM gap-repair setup failed: {exc}") from exc

    run_root = lab_root / "runs" / args.run_id
    downloads_root = run_root / "downloads"
    candidates_root = run_root / "candidates"
    downloads_root.mkdir(parents=True, exist_ok=True)
    candidates_root.mkdir(parents=True, exist_ok=True)

    runner = NotebookLMRunner(
        cli_path=notebooklm_cli,
        profile=args.profile,
        storage=storage,
        repo_root=repo_root,
        dry_run=args.dry_run,
    )
    if not notebooklm_cli.exists() and not args.dry_run:
        raise SystemExit(f"NotebookLM CLI not found: {notebooklm_cli}")

    status: dict[str, object] = {
        "run_id": args.run_id,
        "notebook_slugs": [notebook["slug"] for notebook in manifest["notebooks"]],
        "dry_run": args.dry_run,
        "notebooklm_profile": args.profile,
        "notebooklm_storage": _repo_relative(storage, repo_root) if storage else None,
        "notebooks": [],
    }
    status_path = run_root / "notebooklm_run_status.json"

    try:
        runner.run_json("list", "--json")
        matrix = None
        deck = None
        if not args.dry_run:
            matrix = load_matrix(_resolve_repo_path(args.matrix_path, repo_root))
            deck = load_current_deck(_resolve_repo_path(args.deck_path, repo_root), matrix)
        for notebook in manifest["notebooks"]:
            notebook_status = _process_notebook(
                notebook=notebook,
                runner=runner,
                args=args,
                repo_root=repo_root,
                run_id=args.run_id,
                run_root=run_root,
                downloads_root=downloads_root,
                candidates_root=candidates_root,
                matrix=matrix,
                deck=deck,
            )
            status["notebooks"].append(notebook_status)
            write_json_stably(status_path, status)
    except (subprocess.CalledProcessError, json.JSONDecodeError, ValueError, FlashcardLabError) as exc:
        status["status"] = "blocked_or_failed"
        status["error"] = str(exc)
        write_json_stably(status_path, status)
        raise SystemExit(f"NotebookLM gap-repair generation failed: {exc}") from exc

    status["status"] = "dry_run_complete" if args.dry_run else "complete"
    write_json_stably(status_path, status)
    print(f"NotebookLM gap-repair generation {status['status']} for run {args.run_id}")
    for notebook_status in status["notebooks"]:
        candidates = notebook_status.get("candidates") if isinstance(notebook_status, dict) else None
        if candidates:
            print(f"Candidates ({notebook_status['slug']}): {candidates['json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
