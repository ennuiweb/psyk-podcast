"""Configuration loading for the NotebookLM tooling."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, MutableMapping, Optional

import yaml


class ConfigError(RuntimeError):
    """Raised when the NotebookLM config file is invalid."""


@dataclass(slots=True, frozen=True)
class ShowSettings:
    name: str
    notebook_id: Optional[str] = None
    drive_folder_id: Optional[str] = None
    episode_focus: Optional[str] = None
    language_code: Optional[str] = None


@dataclass(slots=True, frozen=True)
class ResolvedShowConfig:
    name: str
    project_number: str
    location: str
    endpoint_prefix: str
    podcast_parent: str
    notebook_id: str
    language_code: str
    episode_focus: Optional[str]
    drive_folder_id: str
    drive_upload_root: str
    service_account_file: Path

    @property
    def endpoint(self) -> str:
        prefix = self.endpoint_prefix or ""
        if prefix and not prefix.endswith("-"):
            prefix = f"{prefix}-"
        return f"https://{prefix}discoveryengine.googleapis.com"

    @property
    def podcast_base(self) -> str:
        return self.podcast_parent.rstrip("/")

    @property
    def notebooks_base(self) -> str:
        return f"{self.podcast_base}/notebooks"


@dataclass(slots=True, frozen=True)
class AppConfig:
    project_number: str
    location: str
    endpoint_prefix: str
    podcast_parent: str
    default_notebook_id: str
    language_code: str
    drive_upload_root: str
    service_account_file: Path
    shows: Dict[str, ShowSettings]

    def resolve_show(self, show_name: str) -> ResolvedShowConfig:
        if show_name not in self.shows:
            raise ConfigError(f"Show '{show_name}' not present in config (available: {', '.join(self.shows)})")
        show = self.shows[show_name]
        notebook_id = show.notebook_id or self.default_notebook_id
        if not notebook_id:
            raise ConfigError(f"Show '{show_name}' is missing notebook_id and no default is configured.")
        drive_folder_id = show.drive_folder_id or self.drive_upload_root
        if not drive_folder_id:
            raise ConfigError(f"Show '{show_name}' is missing drive_folder_id and no drive_upload_root fallback is set.")
        service_file = self.service_account_file.expanduser().resolve()
        return ResolvedShowConfig(
            name=show_name,
            project_number=self.project_number,
            location=self.location,
            endpoint_prefix=self.endpoint_prefix,
            podcast_parent=self.podcast_parent,
            notebook_id=notebook_id,
            language_code=show.language_code or self.language_code,
            episode_focus=show.episode_focus,
            drive_folder_id=drive_folder_id,
            drive_upload_root=self.drive_upload_root,
            service_account_file=service_file,
        )


ENV_OVERRIDES = {
    "project_number": "NOTEBOOKLM_PROJECT_NUMBER",
    "location": "NOTEBOOKLM_LOCATION",
    "endpoint_prefix": "NOTEBOOKLM_ENDPOINT_PREFIX",
    "podcast_parent": "NOTEBOOKLM_PODCAST_PARENT",
    "default_notebook_id": "NOTEBOOKLM_DEFAULT_NOTEBOOK",
    "language_code": "NOTEBOOKLM_LANGUAGE",
    "drive_upload_root": "NOTEBOOKLM_DRIVE_UPLOAD_ROOT",
    "service_account_file": "NOTEBOOKLM_SERVICE_ACCOUNT",
}


def _apply_env_overrides(raw: MutableMapping[str, object]) -> None:
    for key, env_name in ENV_OVERRIDES.items():
        value = os.environ.get(env_name)
        if value:
            raw[key] = value


def _parse_shows(data: Mapping[str, object]) -> Dict[str, ShowSettings]:
    shows: Dict[str, ShowSettings] = {}
    for name, payload in data.items():
        if not isinstance(payload, Mapping):
            raise ConfigError(f"Show '{name}' must be a mapping.")
        shows[name] = ShowSettings(
            name=name,
            notebook_id=payload.get("notebook_id"),
            drive_folder_id=payload.get("drive_folder_id"),
            episode_focus=payload.get("episode_focus"),
            language_code=payload.get("language_code"),
        )
    return shows


def load_config(path: Path) -> AppConfig:
    if not path.exists():
        raise ConfigError(f"Config file '{path}' not found.")
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, MutableMapping):
        raise ConfigError("Config root must be a mapping.")
    _apply_env_overrides(raw)
    try:
        shows_raw = raw.pop("shows")
    except KeyError as exc:
        raise ConfigError("Config missing 'shows' section.") from exc
    shows = _parse_shows(shows_raw)
    podcast_parent = raw.get("podcast_parent") or f"projects/{raw.get('project_number')}/locations/{raw.get('location')}"
    service_account_file = Path(raw["service_account_file"])
    return AppConfig(
        project_number=str(raw["project_number"]),
        location=str(raw["location"]),
        endpoint_prefix=str(raw.get("endpoint_prefix", "")),
        podcast_parent=podcast_parent,
        default_notebook_id=str(raw.get("default_notebook_id", "")),
        language_code=str(raw.get("language_code", "en-US")),
        drive_upload_root=str(raw.get("drive_upload_root", "")),
        service_account_file=service_account_file,
        shows=shows,
    )

