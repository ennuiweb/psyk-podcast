"""Entry point for the NotebookLM podcast CLI."""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Sequence

from . import VERSION
from .client import NotebookLMClient, NotebookLMError
from .config import AppConfig, ConfigError, ContextConfig, ResolvedProfileConfig, load_config
from . import storage

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="notebooklm",
        description="Automate NotebookLM podcast generation locally via the standalone API.",
    )
    parser.add_argument(
        "--config",
        default="notebooklm_app/config.yaml",
        help="Path to the NotebookLM config file (default: %(default)s).",
    )
    parser.add_argument(
        "--workspace",
        help="Override the workspace root for local artifacts (defaults to the value in config).",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    create_cmd = subparsers.add_parser("create", help="Create a new NotebookLM podcast via the standalone API.")
    _attach_profile_argument(create_cmd)
    create_cmd.add_argument("--focus", help="Override the focus prompt.")
    create_cmd.add_argument("--length", choices=("SHORT", "STANDARD"), help="Override the requested length.")
    create_cmd.add_argument("--language", help="Override the language code.")
    create_cmd.add_argument("--title", help="Override the podcast title.")
    create_cmd.add_argument("--description", help="Override the podcast description.")
    create_cmd.add_argument("--context-text", action="append", dest="context_texts", help="Inline text context to append (can repeat).")
    create_cmd.add_argument("--context-file", action="append", dest="context_files", help="Path to a text file whose contents become context (can repeat).")
    create_cmd.add_argument("--skip-wait", action="store_true", help="Do not poll for completion.")
    create_cmd.add_argument("--poll-interval", type=int, default=30, help="Seconds between status checks.")
    create_cmd.add_argument("--timeout", type=int, default=900, help="Maximum seconds to wait for completion.")

    status_cmd = subparsers.add_parser("status", help="Show the status of a podcast generation operation.")
    _attach_profile_argument(status_cmd)
    status_cmd.add_argument("--json", action="store_true", help="Print raw JSON payload.")
    status_cmd.add_argument("--operation", help="Explicit operation name to inspect (defaults to latest run).")

    download_cmd = subparsers.add_parser("download", help="Download the generated podcast audio locally.")
    _attach_profile_argument(download_cmd)
    download_cmd.add_argument("--output", help="Destination directory (defaults to the profile workspace downloads folder).")
    download_cmd.add_argument("--filename", help="Output filename (defaults to timestamp slug).")
    download_cmd.add_argument("--operation", help="Explicit operation name to download (defaults to latest run).")
    download_cmd.add_argument("--wait", action="store_true", help="Poll until the operation is finished before downloading.")
    download_cmd.add_argument("--poll-interval", type=int, default=30, help="Seconds between status checks when waiting.")
    download_cmd.add_argument("--timeout", type=int, default=900, help="Maximum seconds to wait when --wait is supplied.")

    return parser


def _attach_profile_argument(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--profile", required=True, help="Which NotebookLM profile from the config to use.")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    if args.workspace:
        os.environ["NOTEBOOKLM_WORKSPACE_ROOT"] = args.workspace

    config_path = Path(args.config)
    try:
        app_config = load_config(config_path)
    except ConfigError as exc:
        parser.error(str(exc))

    handler = {
        "create": _cmd_create,
        "status": _cmd_status,
        "download": _cmd_download,
    }[args.command]

    try:
        handler(args, app_config)
    except NotebookLMError as exc:
        logger.error("%s", exc)
        return 2
    except ConfigError as exc:  # Defensive: profile-specific issues
        logger.error("%s", exc)
        return 3
    return 0


def _cmd_create(args, app_config: AppConfig) -> None:
    resolved = app_config.resolve_profile(args.profile)
    profile_dir = _ensure_workspace(resolved)
    client = NotebookLMClient(resolved)
    contexts = _collect_contexts(resolved, args)
    if not contexts:
        raise NotebookLMError("No contexts configured. Add them to the profile or pass --context-* arguments.")
    create_response = client.create_podcast(
        focus=args.focus or resolved.focus,
        length=args.length or resolved.length,
        language_code=args.language or resolved.language_code,
        title=args.title or resolved.title,
        description=args.description or resolved.description,
        contexts=contexts,
    )
    operation_name = create_response.get("name")
    if not operation_name:
        raise NotebookLMError("Create response did not include an operation name.")
    run_slug = storage.timestamp_slug()
    run_payload = {
        "action": "create",
        "profile": resolved.name,
        "request": {
            "focus": args.focus or resolved.focus,
            "length": args.length or resolved.length,
            "language_code": args.language or resolved.language_code,
            "title": args.title or resolved.title,
            "description": args.description or resolved.description,
        },
        "response": create_response,
        "operation_name": operation_name,
    }
    storage.save_run(profile_dir, run_payload, slug=run_slug)
    if args.skip_wait:
        logger.info("Creation request submitted; skipping wait per flag.")
        return
    finished_operation = client.wait_for_operation(
        operation_name,
        poll_interval=args.poll_interval,
        timeout=args.timeout,
    )
    run_payload["operation"] = finished_operation
    storage.save_run(profile_dir, run_payload, slug=run_slug)
    logger.info("Podcast ready for %s (operation %s)", resolved.name, operation_name)


def _cmd_status(args, app_config: AppConfig) -> None:
    resolved = app_config.resolve_profile(args.profile)
    profile_dir = _ensure_workspace(resolved)
    operation_name = args.operation or _latest_operation_name(profile_dir)
    if not operation_name:
        raise NotebookLMError("No operation found. Run 'create' first or pass --operation.")
    client = NotebookLMClient(resolved)
    payload = client.get_operation(operation_name)
    if args.json:
        print(json.dumps(payload, indent=2))
        return
    done = payload.get("done", False)
    print(f"Operation: {operation_name}")
    print(f"Done: {done}")
    if "error" in payload:
        print(f"Error: {payload['error']}")


def _cmd_download(args, app_config: AppConfig) -> None:
    resolved = app_config.resolve_profile(args.profile)
    profile_dir = _ensure_workspace(resolved)
    operation_name = args.operation or _latest_operation_name(profile_dir)
    if not operation_name:
        raise NotebookLMError("No operation found. Run 'create' first or pass --operation.")
    client = NotebookLMClient(resolved)
    if args.wait:
        client.wait_for_operation(operation_name, poll_interval=args.poll_interval, timeout=args.timeout)
    else:
        op_state = client.get_operation(operation_name)
        if not op_state.get("done"):
            raise NotebookLMError("Operation is not finished yet. Re-run with --wait to block until completion.")
    downloads_dir = Path(args.output) if args.output else storage.ensure_download_dir(profile_dir)
    downloads_dir.mkdir(parents=True, exist_ok=True)
    filename = args.filename or f"{storage.timestamp_slug()}.mp3"
    destination = downloads_dir / filename
    client.download_operation_media(operation_name, destination)
    logger.info("Saved podcast audio to %s", destination)


def _ensure_workspace(resolved: ResolvedProfileConfig) -> Path:
    resolved.workspace_dir.mkdir(parents=True, exist_ok=True)
    return resolved.workspace_dir


def _collect_contexts(resolved: ResolvedProfileConfig, args) -> Sequence[ContextConfig]:
    contexts = list(resolved.contexts)
    for text in args.context_texts or []:
        contexts.append(ContextConfig(kind="text", value=text))
    for path_str in args.context_files or []:
        contexts.append(ContextConfig(kind="text_file", path=Path(path_str).expanduser().resolve()))
    return contexts


def _latest_operation_name(profile_root: Path) -> str | None:
    last_run = storage.load_run(profile_root)
    if not last_run:
        return None
    return last_run.get("operation_name")


if __name__ == "__main__":
    raise SystemExit(main())
