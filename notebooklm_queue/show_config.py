"""Helpers for resolving queue-bound show config paths."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


class ShowConfigSelectionError(RuntimeError):
    """Raised when queue stages disagree about which show config to use."""


def resolve_show_config_path(
    *,
    repo_root: Path,
    default_path: str,
    override_path: str | Path | None = None,
) -> Path:
    raw = default_path if override_path is None else override_path
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def serialize_show_config_path(*, repo_root: Path, path: Path) -> str:
    resolved_repo_root = repo_root.resolve()
    resolved_path = path.resolve()
    try:
        return str(resolved_path.relative_to(resolved_repo_root))
    except ValueError:
        return str(resolved_path)


def load_show_config(
    *,
    repo_root: Path,
    default_path: str,
    override_path: str | Path | None = None,
) -> dict[str, Any]:
    path = resolve_show_config_path(repo_root=repo_root, default_path=default_path, override_path=override_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object config in {path}")
    payload["__config_path__"] = str(path.resolve())
    return payload


def manifest_show_config_path(manifest: Mapping[str, Any] | None) -> str | None:
    if not isinstance(manifest, Mapping):
        return None
    show_config = manifest.get("show_config")
    if not isinstance(show_config, Mapping):
        return None
    value = str(show_config.get("path") or "").strip()
    return value or None


def resolve_manifest_bound_show_config_path(
    *,
    repo_root: Path,
    default_path: str,
    manifest: Mapping[str, Any] | None = None,
    override_path: str | Path | None = None,
) -> Path:
    manifest_path = manifest_show_config_path(manifest)
    resolved_manifest = None
    if manifest_path:
        resolved_manifest = resolve_show_config_path(
            repo_root=repo_root,
            default_path=default_path,
            override_path=manifest_path,
        )
    if override_path is None:
        return resolved_manifest or resolve_show_config_path(
            repo_root=repo_root,
            default_path=default_path,
            override_path=None,
        )
    resolved_override = resolve_show_config_path(
        repo_root=repo_root,
        default_path=default_path,
        override_path=override_path,
    )
    if resolved_manifest is not None and resolved_override != resolved_manifest:
        raise ShowConfigSelectionError(
            f"Explicit show config {resolved_override} does not match the manifest-bound show config {resolved_manifest}."
        )
    return resolved_manifest or resolved_override
