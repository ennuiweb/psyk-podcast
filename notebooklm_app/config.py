"""Configuration loading for the NotebookLM tooling."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Mapping, MutableMapping, Optional, Sequence

import yaml


class ConfigError(RuntimeError):
    """Raised when the NotebookLM config file is invalid."""


@dataclass(slots=True, frozen=True)
class ContextConfig:
    kind: str  # text | text_file | blob_file
    value: Optional[str] = None
    path: Optional[Path] = None
    mime_type: Optional[str] = None


@dataclass(slots=True, frozen=True)
class ProfileSettings:
    name: str
    title: Optional[str] = None
    description: Optional[str] = None
    focus: Optional[str] = None
    length: Optional[str] = None
    language_code: Optional[str] = None
    contexts: Sequence[ContextConfig] = ()


@dataclass(slots=True, frozen=True)
class ResolvedProfileConfig:
    name: str
    project_id: str
    location: str
    endpoint: str
    project_path: str
    title: Optional[str]
    description: Optional[str]
    focus: Optional[str]
    length: str
    language_code: str
    service_account_file: Path
    workspace_dir: Path
    contexts: Sequence[ContextConfig]

    @property
    def podcast_collection(self) -> str:
        return f"{self.project_path}/podcasts"


@dataclass(slots=True, frozen=True)
class AppConfig:
    project_id: str
    location: str
    endpoint: str
    language_code: str
    default_length: str
    service_account_file: Path
    workspace_root: Path
    profiles: Dict[str, ProfileSettings]

    def resolve_profile(self, profile_name: str) -> ResolvedProfileConfig:
        if profile_name not in self.profiles:
            raise ConfigError(f"Profile '{profile_name}' not present in config (available: {', '.join(self.profiles)})")
        profile = self.profiles[profile_name]
        service_file = self.service_account_file.expanduser().resolve()
        workspace_dir = (self.workspace_root / profile_name).expanduser().resolve()
        length = profile.length or self.default_length
        if length not in {"SHORT", "STANDARD"}:
            raise ConfigError(f"Profile '{profile_name}' length must be SHORT or STANDARD (got '{length}').")
        project_path = f"projects/{self.project_id}/locations/{self.location}"
        return ResolvedProfileConfig(
            name=profile_name,
            project_id=self.project_id,
            location=self.location,
            endpoint=self.endpoint,
            project_path=project_path,
            title=profile.title,
            description=profile.description,
            focus=profile.focus,
            length=length,
            language_code=profile.language_code or self.language_code,
            service_account_file=service_file,
            workspace_dir=workspace_dir,
            contexts=profile.contexts,
        )


ENV_OVERRIDES = {
    "project_id": "NOTEBOOKLM_PROJECT_ID",
    "location": "NOTEBOOKLM_LOCATION",
    "language_code": "NOTEBOOKLM_LANGUAGE",
    "default_length": "NOTEBOOKLM_DEFAULT_LENGTH",
    "endpoint": "NOTEBOOKLM_ENDPOINT",
    "service_account_file": "NOTEBOOKLM_SERVICE_ACCOUNT",
    "workspace_root": "NOTEBOOKLM_WORKSPACE_ROOT",
}


def load_config(path: Path) -> AppConfig:
    if not path.exists():
        raise ConfigError(f"Config file '{path}' not found.")
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    if not isinstance(raw, MutableMapping):
        raise ConfigError("Config root must be a mapping.")
    _apply_env_overrides(raw)
    try:
        profiles_raw = raw.pop("profiles")
    except KeyError as exc:
        raise ConfigError("Config missing 'profiles' section.") from exc
    base_dir = path.parent
    profiles = _parse_profiles(profiles_raw, base_dir=base_dir)
    service_account_file = _resolve_path(base_dir, Path(raw["service_account_file"]))
    workspace_root = _resolve_path(base_dir, Path(raw.get("workspace_root", "notebooklm_app/workspace")))
    endpoint = raw.get("endpoint") or "https://discoveryengine.googleapis.com"
    return AppConfig(
        project_id=str(raw["project_id"]),
        location=str(raw["location"]),
        endpoint=str(endpoint),
        language_code=str(raw.get("language_code", "en-US")),
        default_length=str(raw.get("default_length", "STANDARD")),
        service_account_file=service_account_file,
        workspace_root=workspace_root,
        profiles=profiles,
    )


def _apply_env_overrides(raw: MutableMapping[str, object]) -> None:
    for key, env_name in ENV_OVERRIDES.items():
        value = os.environ.get(env_name)
        if value:
            raw[key] = value


def _parse_profiles(data: Mapping[str, object], *, base_dir: Path) -> Dict[str, ProfileSettings]:
    profiles: Dict[str, ProfileSettings] = {}
    for name, payload in data.items():
        if not isinstance(payload, Mapping):
            raise ConfigError(f"Profile '{name}' must be a mapping.")
        contexts = _parse_contexts(payload.get("contexts", []) or [], base_dir=base_dir)
        profiles[name] = ProfileSettings(
            name=name,
            title=payload.get("title"),
            description=payload.get("description"),
            focus=payload.get("focus"),
            length=payload.get("length"),
            language_code=payload.get("language_code"),
            contexts=contexts,
        )
    return profiles


def _parse_contexts(raw_contexts: Iterable[object], *, base_dir: Path) -> Sequence[ContextConfig]:
    contexts: list[ContextConfig] = []
    for entry in raw_contexts:
        if not isinstance(entry, Mapping):
            raise ConfigError("Each context must be a mapping.")
        kind = entry.get("type")
        if kind not in {"text", "text_file", "blob_file"}:
            raise ConfigError(f"Unsupported context type '{kind}'.")
        if kind == "text":
            value = entry.get("value")
            if not isinstance(value, str):
                raise ConfigError("text context requires 'value'.")
            contexts.append(ContextConfig(kind="text", value=value))
        elif kind == "text_file":
            path_value = entry.get("path")
            if not isinstance(path_value, str):
                raise ConfigError("text_file context requires 'path'.")
            contexts.append(ContextConfig(kind="text_file", path=_resolve_path(base_dir, Path(path_value))))
        else:
            path_value = entry.get("path")
            if not isinstance(path_value, str):
                raise ConfigError("blob_file context requires 'path'.")
            contexts.append(
                ContextConfig(
                    kind="blob_file",
                    path=_resolve_path(base_dir, Path(path_value)),
                    mime_type=entry.get("mime_type"),
                )
            )
    return tuple(contexts)


def _resolve_path(base_dir: Path, path: Path) -> Path:
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def render_context_payload(context: ContextConfig) -> Dict[str, str]:
    if context.kind == "text":
        return {"text": context.value or ""}
    if context.kind == "text_file":
        if not context.path:
            raise ConfigError("text_file context missing path.")
        text = context.path.read_text(encoding="utf-8")
        return {"text": text}
    if context.kind == "blob_file":
        if not context.path:
            raise ConfigError("blob_file context missing path.")
        data = context.path.read_bytes()
        encoded = base64.b64encode(data).decode("ascii")
        payload = {"blob": encoded}
        if context.mime_type:
            payload["mimeType"] = context.mime_type
        return payload
    raise ConfigError(f"Unknown context kind '{context.kind}'.")

