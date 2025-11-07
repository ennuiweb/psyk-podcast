"""Entry point for the NotebookLM podcast CLI."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

from . import VERSION
from .client import NotebookLMClient, NotebookLMError
from .config import AppConfig, ConfigError, ResolvedShowConfig, load_config
from .drive_sync import upload_audio_asset
from . import storage

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="notebooklm",
        description="Automate NotebookLM podcast creation for the psyk-podcast shows.",
    )
    parser.add_argument(
        "--config",
        default="notebooklm_app/config.yaml",
        help="Path to the NotebookLM config file (default: %(default)s).",
    )
    parser.add_argument(
        "--shows-root",
        default="shows",
        help="Directory that contains show folders (default: %(default)s).",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    create_cmd = subparsers.add_parser("create", help="Create a new NotebookLM audio overview.")
    _attach_show_argument(create_cmd)
    create_cmd.add_argument("--source-id", action="append", dest="source_ids", help="Limit to specific source IDs.")
    create_cmd.add_argument("--episode-focus", help="Episode focus text sent to NotebookLM.")
    create_cmd.add_argument("--language", help="Override the language code.")
    create_cmd.add_argument("--replace-existing", action="store_true", help="Delete any existing overview before creating a new one.")
    create_cmd.add_argument("--skip-wait", action="store_true", help="Do not poll for completion.")
    create_cmd.add_argument("--poll-interval", type=int, default=30, help="Seconds between status checks.")
    create_cmd.add_argument("--timeout", type=int, default=900, help="Maximum seconds to wait for completion.")

    status_cmd = subparsers.add_parser("status", help="Show the current overview status.")
    _attach_show_argument(status_cmd)
    status_cmd.add_argument("--json", action="store_true", help="Print raw JSON payload.")

    download_cmd = subparsers.add_parser("download", help="Download the generated audio file to the repo.")
    _attach_show_argument(download_cmd)
    download_cmd.add_argument("--output", help="Destination directory (defaults to shows/<show>/notebooklm/downloads).")
    download_cmd.add_argument("--filename", help="Output filename (defaults to timestamp slug).")

    sync_cmd = subparsers.add_parser("sync-drive", help="Upload a downloaded audio file into Google Drive.")
    _attach_show_argument(sync_cmd)
    sync_cmd.add_argument("--file", help="Local audio file to upload (defaults to latest download).")
    sync_cmd.add_argument("--title", help="Override Drive filename.")

    return parser


def _attach_show_argument(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--show", required=True, help="Which show config to use.")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    config_path = Path(args.config)
    shows_root = Path(args.shows_root)
    try:
        app_config = load_config(config_path)
    except ConfigError as exc:
        parser.error(str(exc))

    handler = {
        "create": _cmd_create,
        "status": _cmd_status,
        "download": _cmd_download,
        "sync-drive": _cmd_sync_drive,
    }[args.command]

    try:
        handler(args, app_config, shows_root)
    except NotebookLMError as exc:
        logger.error("%s", exc)
        return 2
    except ConfigError as exc:  # Defensive: show-specific issues
        logger.error("%s", exc)
        return 3
    return 0


def _cmd_create(args, app_config: AppConfig, shows_root: Path) -> None:
    resolved = app_config.resolve_show(args.show)
    show_dir = _ensure_show_root(shows_root, resolved.name)
    client = NotebookLMClient(resolved)
    if args.replace_existing:
        logger.info("Deleting existing overview (if any) before creating a new one.")
        try:
            client.delete_audio_overview()
        except NotebookLMError:
            logger.info("No existing overview to delete.")
    create_response = client.create_audio_overview(
        source_ids=args.source_ids,
        episode_focus=args.episode_focus or resolved.episode_focus,
        language_code=args.language or resolved.language_code,
    )
    run_slug = storage.timestamp_slug()
    run_payload = {
        "action": "create",
        "show": resolved.name,
        "request": {
            "source_ids": args.source_ids,
            "episode_focus": args.episode_focus or resolved.episode_focus,
            "language_code": args.language or resolved.language_code,
        },
        "response": create_response,
    }
    storage.save_run(show_dir, run_payload, slug=run_slug)
    if args.skip_wait:
        logger.info("Creation request submitted; skipping wait per flag.")
        return
    ready_payload = client.wait_for_ready(
        poll_interval=args.poll_interval,
        timeout=args.timeout,
    )
    run_payload["final_state"] = ready_payload
    audio_uri = NotebookLMClient.extract_audio_uri(ready_payload)
    if audio_uri:
        run_payload["audio_uri"] = audio_uri
    storage.save_run(show_dir, run_payload, slug=run_slug)
    logger.info("Audio overview ready for %s", resolved.name)


def _cmd_status(args, app_config: AppConfig, shows_root: Path) -> None:
    resolved = app_config.resolve_show(args.show)
    _ensure_show_root(shows_root, resolved.name)
    client = NotebookLMClient(resolved)
    payload = client.get_audio_overview()
    if args.json:
        print(json.dumps(payload, indent=2))
        return
    overview = payload.get("audioOverview") or payload
    status = overview.get("status")
    audio_uri = overview.get("audioUri") or overview.get("downloadUri")
    print(f"Status: {status}")
    if audio_uri:
        print(f"Audio URI: {audio_uri}")


def _cmd_download(args, app_config: AppConfig, shows_root: Path) -> None:
    resolved = app_config.resolve_show(args.show)
    show_dir = _ensure_show_root(shows_root, resolved.name)
    client = NotebookLMClient(resolved)
    payload = client.get_audio_overview()
    audio_uri = NotebookLMClient.extract_audio_uri(payload)
    if not audio_uri:
        raise NotebookLMError("Audio overview is not ready or missing audio URI.")
    downloads_dir = Path(args.output) if args.output else storage.ensure_download_dir(show_dir)
    downloads_dir.mkdir(parents=True, exist_ok=True)
    filename = args.filename or f"{storage.timestamp_slug()}.mp3"
    destination = downloads_dir / filename
    _download_file(client, audio_uri, destination)
    logger.info("Saved audio to %s", destination)


def _cmd_sync_drive(args, app_config: AppConfig, shows_root: Path) -> None:
    resolved = app_config.resolve_show(args.show)
    show_dir = _ensure_show_root(shows_root, resolved.name)
    file_path = Path(args.file) if args.file else _latest_download(show_dir)
    if not file_path or not file_path.exists():
        raise NotebookLMError("No local audio file found to upload. Use the download command first or pass --file.")
    result = upload_audio_asset(
        service_account_file=resolved.service_account_file,
        folder_id=resolved.drive_folder_id,
        local_path=file_path,
        title=args.title or file_path.name,
    )
    logger.info("Uploaded %s to Drive (file ID: %s)", file_path, result.get("id"))


def _ensure_show_root(shows_root: Path, show_name: str) -> Path:
    show_dir = shows_root / show_name
    show_dir.mkdir(parents=True, exist_ok=True)
    return show_dir


def _latest_download(show_root: Path) -> Optional[Path]:
    downloads_dir = storage.ensure_download_dir(show_root)
    files = sorted(downloads_dir.glob("*"))
    return files[-1] if files else None


def _download_file(client: NotebookLMClient, url: str, destination: Path, chunk_size: int = 1024 * 1024) -> None:
    response = client.session.get(url, stream=True)
    if response.status_code != 200:
        raise NotebookLMError(f"Failed to download audio ({response.status_code}): {response.text}")
    with destination.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                handle.write(chunk)


if __name__ == "__main__":
    raise SystemExit(main())
