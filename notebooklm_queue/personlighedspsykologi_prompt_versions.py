"""Canonical prompt/setup version config for Personlighedspsykologi."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SHOW_SLUG = "personlighedspsykologi-en"
PROMPT_VERSION_CONFIG_NAME = "prompt_versions.json"

SETUP_VERSION_ENV = "PERSONLIGHEDSPSYKOLOGI_SETUP_VERSION"
PODCAST_SETUP_VERSION_ENV = "PERSONLIGHEDSPSYKOLOGI_PODCAST_SETUP_VERSION"
PRINTOUT_SETUP_VERSION_ENV = "PERSONLIGHEDSPSYKOLOGI_PRINTOUT_SETUP_VERSION"

DEFAULT_PROMPT_VERSIONS = {
    "source_card": "personlighedspsykologi-source-card-v1",
    "lecture_substrate": "personlighedspsykologi-lecture-substrate-v2",
    "course_synthesis": "personlighedspsykologi-course-synthesis-v3",
    "revised_lecture_substrate": "personlighedspsykologi-downward-revision-v3",
    "podcast_substrate": "personlighedspsykologi-podcast-substrate-v2",
    "reading_printouts": "personlighedspsykologi-reading-printouts-v3",
}


def normalize_text(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def prompt_version_config_path(*, repo_root: Path | None = None, show_root: Path | None = None) -> Path:
    if show_root is not None:
        return show_root / PROMPT_VERSION_CONFIG_NAME
    root = repo_root if repo_root is not None else REPO_ROOT
    return root / "shows" / SHOW_SLUG / PROMPT_VERSION_CONFIG_NAME


def load_prompt_version_config(*, repo_root: Path | None = None, show_root: Path | None = None) -> dict[str, Any]:
    path = prompt_version_config_path(repo_root=repo_root, show_root=show_root)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Invalid prompt version config payload: {path}")
    return payload


def configured_prompt_versions(*, repo_root: Path | None = None, show_root: Path | None = None) -> dict[str, str]:
    versions = dict(DEFAULT_PROMPT_VERSIONS)
    payload = load_prompt_version_config(repo_root=repo_root, show_root=show_root)
    raw_versions = payload.get("prompt_versions")
    if not isinstance(raw_versions, dict):
        return versions
    for key, value in raw_versions.items():
        normalized = normalize_text(value)
        if normalized:
            versions[str(key)] = normalized
    return versions


def configured_setup_versions(*, repo_root: Path | None = None, show_root: Path | None = None) -> dict[str, str | None]:
    payload = load_prompt_version_config(repo_root=repo_root, show_root=show_root)
    raw_versions = payload.get("setup_versions")
    if not isinstance(raw_versions, dict):
        return {"default": None, "podcast": None, "printout": None}
    return {
        "default": normalize_text(raw_versions.get("default")),
        "podcast": normalize_text(raw_versions.get("podcast")),
        "printout": normalize_text(raw_versions.get("printout")),
    }


def resolve_setup_versions(
    *,
    repo_root: Path | None = None,
    show_root: Path | None = None,
    explicit_default: str | None = None,
    explicit_podcast: str | None = None,
    explicit_printout: str | None = None,
) -> dict[str, str | None]:
    configured = configured_setup_versions(repo_root=repo_root, show_root=show_root)
    shared_override = normalize_text(explicit_default) or normalize_text(os.environ.get(SETUP_VERSION_ENV))
    default = shared_override or configured["default"]
    podcast = (
        normalize_text(explicit_podcast)
        or normalize_text(os.environ.get(PODCAST_SETUP_VERSION_ENV))
        or shared_override
        or configured["podcast"]
        or default
    )
    printout = (
        normalize_text(explicit_printout)
        or normalize_text(os.environ.get(PRINTOUT_SETUP_VERSION_ENV))
        or shared_override
        or configured["printout"]
        or default
    )
    return {
        "default": default,
        "podcast": podcast,
        "printout": printout,
    }
