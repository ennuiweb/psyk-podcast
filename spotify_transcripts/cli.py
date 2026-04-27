"""CLI entrypoint for Spotify transcript tooling."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .constants import DEFAULT_TIMEOUT_MS
from .discovery import load_show_sources
from .paths import get_path_info
from .playwright_client import download_episode_transcript, get_auth_status, login_via_browser
from .service import sync_show_transcripts
from .store import TranscriptStore


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _load_manifest(show_slug: str, repo_root: Path) -> dict[str, Any]:
    show_root = (repo_root / "shows" / show_slug).resolve()
    return TranscriptStore(show_root).load_manifest()


def _report_manifest(show_slug: str, repo_root: Path) -> dict[str, Any]:
    manifest = _load_manifest(show_slug, repo_root)
    episodes = manifest.get("episodes") if isinstance(manifest.get("episodes"), list) else []
    counter = Counter()
    for entry in episodes:
        if not isinstance(entry, dict):
            continue
        counter[str(entry.get("status") or "unknown")] += 1
    return {
        "show_slug": show_slug,
        "episode_count": len([entry for entry in episodes if isinstance(entry, dict)]),
        "status_counts": dict(sorted(counter.items())),
        "manifest_path": str((repo_root / "shows" / show_slug / "spotify_transcripts" / "manifest.json").resolve()),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("login", help="Open Spotify in a persistent Playwright profile and save auth state.")
    subparsers.add_parser("auth-status", help="Show resolved auth/profile paths and current cookie state.")

    report_parser = subparsers.add_parser("report", help="Summarize transcript manifest state for one show.")
    report_parser.add_argument("--show-slug", required=True)
    report_parser.add_argument("--repo-root", type=Path, default=_repo_root())

    sync_parser = subparsers.add_parser("sync", help="Download Spotify transcripts for a mapped show.")
    sync_parser.add_argument("--show-slug", required=True)
    sync_parser.add_argument("--repo-root", type=Path, default=_repo_root())
    sync_parser.add_argument("--episode-key", action="append", default=[], help="Limit sync to one or more episode keys.")
    sync_parser.add_argument("--limit", type=int, default=None, help="Process at most N episodes after filtering.")
    sync_parser.add_argument("--force", action="store_true", help="Re-attempt episodes that already have downloaded artifacts.")
    sync_parser.add_argument("--headless", action="store_true", help="Run Playwright headless. Default is headed for reliability.")
    sync_parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_MS // 1000)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "login":
        storage_path = login_via_browser()
        print(f"Saved Spotify auth state to {storage_path}")
        return 0

    if args.command == "auth-status":
        payload = {
            **get_path_info(),
            **get_auth_status(),
        }
        _print_json(payload)
        return 0

    if args.command == "report":
        _print_json(_report_manifest(args.show_slug, Path(args.repo_root).resolve()))
        return 0

    if args.command == "sync":
        repo_root = Path(args.repo_root).resolve()
        sources = load_show_sources(repo_root=repo_root, show_slug=args.show_slug)
        store = TranscriptStore(sources.show_root)
        summary = sync_show_transcripts(
            sources=sources,
            store=store,
            downloader=download_episode_transcript,
            episode_keys=args.episode_key,
            limit=args.limit,
            force=bool(args.force),
            headless=bool(args.headless),
            timeout_ms=max(int(args.timeout_seconds), 1) * 1000,
        )
        _print_json(
            {
                "show_slug": summary.show_slug,
                "attempted": summary.attempted,
                "downloaded": summary.downloaded,
                "skipped_downloaded": summary.skipped_downloaded,
                "missing_mapping": summary.missing_mapping,
                "failed": summary.failed,
                "report": _report_manifest(args.show_slug, repo_root),
            }
        )
        return 0

    parser.error(f"Unhandled command: {args.command}")
    return 2
