"""Resolve feed-side artifact paths from a show config."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ShowArtifactPaths:
    feed_path: Path
    inventory_path: Path
    quiz_links_path: Path
    spotify_map_path: Path
    content_manifest_path: Path
    media_manifest_path: Path | None


def resolve_show_artifact_paths(
    *,
    repo_root: Path,
    show_slug: str,
    config: Mapping[str, Any],
) -> ShowArtifactPaths:
    show_root = repo_root / "shows" / show_slug
    feed_path = _resolve_config_path(
        repo_root=repo_root,
        config=config,
        raw_value=config.get("output_feed"),
        default_value=show_root / "feeds" / "rss.xml",
    )
    inventory_path = _resolve_config_path(
        repo_root=repo_root,
        config=config,
        raw_value=config.get("output_inventory"),
        default_value=show_root / "episode_inventory.json",
    )
    quiz_cfg = config.get("quiz")
    quiz_links_value = quiz_cfg.get("links_file") if isinstance(quiz_cfg, dict) else None
    quiz_links_path = _resolve_config_path(
        repo_root=repo_root,
        config=config,
        raw_value=quiz_links_value,
        default_value=show_root / "quiz_links.json",
    )
    spotify_map_path = _resolve_config_path(
        repo_root=repo_root,
        config=config,
        raw_value=config.get("spotify_map_file"),
        default_value=show_root / "spotify_map.json",
    )
    content_manifest_path = _resolve_config_path(
        repo_root=repo_root,
        config=config,
        raw_value=config.get("content_manifest_file"),
        default_value=show_root / "content_manifest.json",
    )
    storage = config.get("storage")
    media_manifest_path = None
    if isinstance(storage, dict):
        manifest_value = storage.get("manifest_file")
        if manifest_value:
            media_manifest_path = _resolve_config_path(
                repo_root=repo_root,
                config=config,
                raw_value=manifest_value,
                default_value=None,
            )
    return ShowArtifactPaths(
        feed_path=feed_path,
        inventory_path=inventory_path,
        quiz_links_path=quiz_links_path,
        spotify_map_path=spotify_map_path,
        content_manifest_path=content_manifest_path,
        media_manifest_path=media_manifest_path,
    )


def _resolve_config_path(
    *,
    repo_root: Path,
    config: Mapping[str, Any],
    raw_value: object,
    default_value: Path | None,
) -> Path:
    if raw_value in (None, ""):
        if default_value is None:
            raise ValueError("A default value is required when the config path is missing.")
        return default_value.resolve()
    path = Path(str(raw_value)).expanduser()
    if path.is_absolute():
        return path.resolve()
    if str(raw_value).startswith("shows/"):
        return (repo_root / path).resolve()
    config_path_raw = str(config.get("__config_path__") or "").strip()
    if config_path_raw:
        return (Path(config_path_raw).resolve().parent / path).resolve()
    return (repo_root / path).resolve()
