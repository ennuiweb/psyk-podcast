#!/usr/bin/env python3
"""Run NotebookLM flashcard generation for one or more lab notebooks end to end.

This script creates or uses NotebookLM notebooks, uploads processed matrix
packs, generates flashcards, downloads JSON/Markdown output, and normalizes the
JSON into review-only candidates. It never deletes NotebookLM notebooks,
sources, artifacts, or Freudd cards.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from notebooklm_queue.json_artifact_utils import write_json_stably
from notebooklm_queue.personlighedspsykologi_notebooklm_flashcard_lab import (
    DEFAULT_DECK_PATH,
    DEFAULT_LAB_ROOT,
    DEFAULT_MATRIX_PATH,
    NOTEBOOK_SPECS,
    PILOT_NOTEBOOK_SLUG,
    FlashcardLabError,
    default_run_id,
    export_lab_run,
    load_current_deck,
    load_matrix,
    load_notebooklm_flashcard_payload,
    normalize_notebooklm_cards,
    write_candidate_review_markdown,
)

DEFAULT_NOTEBOOKLM_CLI = Path("notebooklm-podcast-auto/.venv/bin/notebooklm")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--lab-root", type=Path, default=DEFAULT_LAB_ROOT)
    parser.add_argument("--matrix-path", type=Path, default=DEFAULT_MATRIX_PATH)
    parser.add_argument("--deck-path", type=Path, default=DEFAULT_DECK_PATH)
    parser.add_argument("--notebooklm-cli", type=Path, default=DEFAULT_NOTEBOOKLM_CLI)
    parser.add_argument("--profile", default=None, help="NotebookLM profile to pass with -p.")
    parser.add_argument("--storage", type=Path, default=None, help="NotebookLM storage_state.json to pass with --storage.")
    parser.add_argument(
        "--notebook-slug",
        action="append",
        default=None,
        choices=[spec.slug for spec in NOTEBOOK_SPECS],
        help="Notebook slug to run. Repeat for multiple. Defaults to the pilot slug.",
    )
    parser.add_argument("--all-notebooks", action="store_true", help="Run every configured lab notebook.")
    parser.add_argument(
        "--notebook-id",
        default=None,
        help="Existing notebook ID. Allowed only when exactly one notebook slug is selected.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Export packs and print intended NotebookLM steps only.")
    return parser.parse_args()


def _resolve_repo_path(path: Path, repo_root: Path) -> Path:
    return path if path.is_absolute() else repo_root / path


def _repo_relative(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def _parse_json_output(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        return {}
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        payload = json.loads(stripped[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("NotebookLM CLI JSON output must be an object")
    return payload


class NotebookLMRunner:
    def __init__(
        self,
        *,
        cli_path: Path,
        profile: str | None,
        storage: Path | None,
        repo_root: Path,
        dry_run: bool = False,
    ) -> None:
        self.cli_path = cli_path
        self.profile = profile
        self.storage = storage
        self.repo_root = repo_root
        self.dry_run = dry_run

    def command(self, *parts: str) -> list[str]:
        cmd = [str(self.cli_path)]
        if self.storage:
            cmd.extend(["--storage", str(self.storage)])
        if self.profile:
            cmd.extend(["-p", self.profile])
        cmd.extend(parts)
        return cmd

    def run_json(self, *parts: str) -> dict[str, Any]:
        cmd = self.command(*parts)
        if self.dry_run:
            print("DRY RUN:", " ".join(cmd))
            return {}
        completed = subprocess.run(
            cmd,
            cwd=self.repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
        return _parse_json_output(completed.stdout)

    def run(self, *parts: str) -> None:
        cmd = self.command(*parts)
        if self.dry_run:
            print("DRY RUN:", " ".join(cmd))
            return
        subprocess.run(cmd, cwd=self.repo_root, check=True)


def _notebook_id_from_create(payload: dict[str, Any]) -> str:
    notebook = payload.get("notebook")
    if isinstance(notebook, dict) and notebook.get("id"):
        return str(notebook["id"])
    raise FlashcardLabError("NotebookLM create command did not return notebook.id")


def _source_id_from_add(payload: dict[str, Any]) -> str:
    source = payload.get("source")
    if isinstance(source, dict) and source.get("id"):
        return str(source["id"])
    raise FlashcardLabError("NotebookLM source add command did not return source.id")


def _selected_notebook_slugs(args: argparse.Namespace) -> set[str] | None:
    if args.all_notebooks and args.notebook_slug:
        raise FlashcardLabError("Use either --all-notebooks or --notebook-slug, not both")
    if args.all_notebooks:
        if args.notebook_id:
            raise FlashcardLabError("--notebook-id can only be used when one notebook slug is selected")
        return None
    slugs = set(args.notebook_slug or [PILOT_NOTEBOOK_SLUG])
    if args.notebook_id and len(slugs) != 1:
        raise FlashcardLabError("--notebook-id can only be used when one notebook slug is selected")
    return slugs


def _process_notebook(
    *,
    notebook: dict[str, Any],
    runner: NotebookLMRunner,
    args: argparse.Namespace,
    repo_root: Path,
    run_id: str,
    run_root: Path,
    downloads_root: Path,
    candidates_root: Path,
    matrix: dict[str, Any] | None,
    deck: dict[str, Any] | None,
) -> dict[str, Any]:
    slug = str(notebook["slug"])
    notebook_id = args.notebook_id
    status: dict[str, Any] = {
        "slug": slug,
        "title": notebook.get("title"),
        "purpose": notebook.get("purpose"),
        "notebooklm_notebook_id": notebook_id,
        "uploaded_sources": [],
        "downloads": {},
    }

    if not notebook_id:
        create_payload = runner.run_json("create", f"{notebook['title']} - {run_id}", "--json")
        notebook_id = _notebook_id_from_create(create_payload) if not args.dry_run else f"<created-{slug}-notebook-id>"
        status["notebooklm_notebook_id"] = notebook_id

    source_ids: list[str] = []
    for source in notebook["sources"]:
        path = _resolve_repo_path(Path(str(source["path"])), repo_root)
        add_payload = runner.run_json("source", "add", str(path), "-n", notebook_id, "--json")
        source_id = _source_id_from_add(add_payload) if not args.dry_run else f"<{slug}-source-{len(source_ids) + 1}>"
        source_ids.append(source_id)
        status["uploaded_sources"].append(
            {
                "source_id": source_id,
                "path": _repo_relative(path, repo_root),
                "sha256": source.get("sha256"),
            }
        )
        runner.run_json("source", "wait", source_id, "-n", notebook_id, "--json")

    instructions = notebook["flashcard_generation"]["instructions"]
    generate_args = [
        "generate",
        "flashcards",
        "-n",
        notebook_id,
        "--quantity",
        "more",
        "--difficulty",
        "hard",
        "--wait",
        "--json",
    ]
    for source_id in source_ids:
        generate_args.extend(["--source", source_id])
    generate_args.append(str(instructions))
    status["generation"] = runner.run_json(*generate_args)

    json_download = downloads_root / f"{slug}.flashcards.json"
    md_download = downloads_root / f"{slug}.flashcards.md"
    runner.run("download", "flashcards", str(json_download), "-n", notebook_id, "--format", "json")
    runner.run("download", "flashcards", str(md_download), "-n", notebook_id, "--format", "markdown")
    status["downloads"] = {
        "json": _repo_relative(json_download, repo_root),
        "markdown": _repo_relative(md_download, repo_root),
    }

    if not args.dry_run:
        if matrix is None or deck is None:
            raise FlashcardLabError("Matrix and deck are required for candidate normalization")
        raw_payload = load_notebooklm_flashcard_payload(json_download)
        candidates = normalize_notebooklm_cards(
            notebooklm_payload=raw_payload,
            matrix=matrix,
            current_deck=deck,
            run_id=run_id,
            notebook_slug=slug,
            source_path=_repo_relative(json_download, repo_root),
        )
        candidate_path = candidates_root / f"{slug}.candidates.json"
        review_path = candidates_root / f"{slug}.review.md"
        write_json_stably(candidate_path, candidates)
        write_candidate_review_markdown(candidates, review_path)
        status["candidates"] = {
            "json": _repo_relative(candidate_path, repo_root),
            "review_markdown": _repo_relative(review_path, repo_root),
            "stats": candidates.get("stats"),
        }

    status["status"] = "dry_run_complete" if args.dry_run else "complete"
    write_json_stably(run_root / f"{slug}.status.json", status)
    return status


def main() -> int:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    lab_root = _resolve_repo_path(args.lab_root, repo_root)
    run_id = args.run_id or default_run_id()
    notebooklm_cli = _resolve_repo_path(args.notebooklm_cli, repo_root)
    storage = _resolve_repo_path(args.storage, repo_root) if args.storage else None
    try:
        selected_slugs = _selected_notebook_slugs(args)
    except FlashcardLabError as exc:
        raise SystemExit(str(exc)) from exc
    manifest = export_lab_run(
        run_id=run_id,
        lab_root=lab_root,
        matrix_path=_resolve_repo_path(args.matrix_path, repo_root),
        deck_path=_resolve_repo_path(args.deck_path, repo_root),
        repo_root=repo_root,
        notebook_slugs=selected_slugs,
    )
    run_root = lab_root / "runs" / run_id
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

    status: dict[str, Any] = {
        "run_id": run_id,
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
                run_id=run_id,
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
        raise SystemExit(f"NotebookLM flashcard generation failed: {exc}") from exc

    status["status"] = "dry_run_complete" if args.dry_run else "complete"
    write_json_stably(status_path, status)
    if len(status["notebooks"]) == 1:
        write_json_stably(run_root / "pilot_status.json", status["notebooks"][0])
    print(f"NotebookLM flashcard generation {status['status']} for run {run_id}")
    for notebook_status in status["notebooks"]:
        candidates = notebook_status.get("candidates")
        if candidates:
            print(f"Candidates ({notebook_status['slug']}): {candidates['json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
