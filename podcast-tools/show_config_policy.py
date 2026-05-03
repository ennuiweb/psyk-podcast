"""Resolve show-level storage and publication policy from config.github.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_STORAGE_PROVIDER = "drive"
DEFAULT_PUBLICATION_OWNER = "legacy_workflow"
VALID_STORAGE_PROVIDERS = {"drive", "r2"}
VALID_PUBLICATION_OWNERS = {DEFAULT_PUBLICATION_OWNER, "queue"}


def load_show_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object config in {path}")
    return payload


def resolve_storage_provider(config: dict[str, Any]) -> str:
    storage = config.get("storage") if isinstance(config.get("storage"), dict) else {}
    provider = str(storage.get("provider") or DEFAULT_STORAGE_PROVIDER).strip().lower() or DEFAULT_STORAGE_PROVIDER
    if provider not in VALID_STORAGE_PROVIDERS:
        raise ValueError(f"Unsupported storage provider: {provider}")
    return provider


def resolve_publication_owner(config: dict[str, Any]) -> str:
    publication = config.get("publication") if isinstance(config.get("publication"), dict) else {}
    owner = str(publication.get("owner") or DEFAULT_PUBLICATION_OWNER).strip().lower() or DEFAULT_PUBLICATION_OWNER
    if owner not in VALID_PUBLICATION_OWNERS:
        raise ValueError(f"Unsupported publication.owner: {owner}")
    return owner


def resolve_show_policy(path: Path) -> dict[str, str]:
    config = load_show_config(path)
    storage_provider = resolve_storage_provider(config)
    publication_owner = resolve_publication_owner(config)
    workflow_writer_enabled = "true" if publication_owner == DEFAULT_PUBLICATION_OWNER else "false"
    return {
        "storage_provider": storage_provider,
        "publication_owner": publication_owner,
        "workflow_writer_enabled": workflow_writer_enabled,
    }


def _write_github_output(path: Path, payload: dict[str, str]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for key, value in payload.items():
            handle.write(f"{key}={value}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    resolve = subparsers.add_parser("resolve", help="Resolve storage/publication policy for one show config.")
    resolve.add_argument("--config", required=True, type=Path)
    resolve.add_argument("--github-output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "resolve":
        payload = resolve_show_policy(args.config)
        if args.github_output:
            _write_github_output(args.github_output, payload)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    parser.error(f"Unhandled command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
