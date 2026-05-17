"""Show-specific queue adapters for discovery and command planning."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from .show_config import load_show_config, resolve_show_config_path, serialize_show_config_path

WEEK_LECTURE_PATTERN = re.compile(r"^(W\d+L\d+)\b", re.IGNORECASE)


def _canonical_lecture_key(value: str) -> str | None:
    match = WEEK_LECTURE_PATTERN.match(str(value).strip())
    if not match:
        return None
    return match.group(1).upper()


@dataclass(frozen=True, slots=True)
class DiscoveredLecture:
    lecture_key: str
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class ShowAdapter:
    show_slug: str
    subject_slug: str
    discovery_source: str
    discovery_path: str
    generator_script: str
    downloader_script: str
    show_config_path: str
    output_root: str
    config_paths: tuple[str, ...]
    prompt_config_path: str | None = None
    default_content_types: tuple[str, ...] = ("audio", "infographic", "quiz")
    strict_download_output_root: bool = False
    include_profile_env_args: bool = False
    generate_extra_args: tuple[str, ...] = ()
    download_extra_args: tuple[str, ...] = ()

    def discover_lectures(self, repo_root: Path) -> list[DiscoveredLecture]:
        if self.discovery_source == "auto_spec_rules":
            return _discover_from_auto_spec_rules(repo_root / self.discovery_path)
        if self.discovery_source == "episode_metadata_source_folder":
            return _discover_from_episode_metadata(repo_root / self.discovery_path)
        raise ValueError(f"Unsupported discovery source: {self.discovery_source}")

    def config_hash(self, repo_root: Path, *, show_config_path: str | Path | None = None) -> str:
        digest = hashlib.sha256()
        resolved_override = None
        override_label = None
        if show_config_path is not None:
            resolved_override = resolve_show_config_path(
                repo_root=repo_root,
                default_path=self.show_config_path,
                override_path=show_config_path,
            )
            override_label = serialize_show_config_path(repo_root=repo_root, path=resolved_override)
        for relative in self.config_paths:
            if relative == self.show_config_path and resolved_override is not None:
                path = resolved_override
                label = override_label or relative
            else:
                path = repo_root / relative
                label = relative
            digest.update(label.encode("utf-8"))
            digest.update(b"\0")
            if path.exists():
                digest.update(path.read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()[:16]

    def load_show_config(
        self,
        repo_root: Path,
        *,
        show_config_path: str | Path | None = None,
    ) -> dict[str, object]:
        return load_show_config(
            repo_root=repo_root,
            default_path=self.show_config_path,
            override_path=show_config_path,
        )

    def output_root_path(self, repo_root: Path) -> Path:
        return repo_root / self.output_root

    def build_generate_command(
        self,
        repo_root: Path,
        *,
        lecture_key: str,
        content_types: tuple[str, ...],
        dry_run: bool,
        wait: bool = False,
    ) -> list[str]:
        command = [
            str(repo_root / ".venv" / "bin" / "python"),
            str(repo_root / self.generator_script),
            "--week",
            lecture_key,
            "--content-types",
            ",".join(content_types),
            "--output-root",
            self.output_root,
        ]
        if self.prompt_config_path:
            command.extend(["--prompt-config", self.prompt_config_path])
        command.extend(self.generate_extra_args)
        if self.include_profile_env_args:
            _append_env_arg(
                command,
                option="--profile-priority",
                env_name="NOTEBOOKLM_PROFILE_PRIORITY",
            )
            _append_env_arg(
                command,
                option="--profiles-file",
                env_name="NOTEBOOKLM_PROFILES_FILE",
            )
        if wait:
            command.append("--wait")
        if dry_run:
            command.append("--dry-run")
        return command

    def build_download_command(
        self,
        repo_root: Path,
        *,
        lecture_key: str,
        content_types: tuple[str, ...],
        dry_run: bool,
        timeout_seconds: int | None = None,
        interval_seconds: int | None = None,
    ) -> list[str]:
        command = [
            str(repo_root / ".venv" / "bin" / "python"),
            str(repo_root / self.downloader_script),
            "--week",
            lecture_key,
            "--content-types",
            ",".join(content_types),
            "--output-root",
            self.output_root,
        ]
        if self.strict_download_output_root:
            command.append("--disable-default-extra-roots")
        command.extend(self.download_extra_args)
        if self.include_profile_env_args:
            _append_env_arg(
                command,
                option="--profile-priority",
                env_name="NOTEBOOKLM_PROFILE_PRIORITY",
            )
            _append_env_arg(
                command,
                option="--profiles-file",
                env_name="NOTEBOOKLM_PROFILES_FILE",
            )
        notebooklm_bin = repo_root / ".venv" / "bin" / "notebooklm"
        if notebooklm_bin.exists():
            command.extend(["--notebooklm", str(notebooklm_bin)])
        if timeout_seconds is not None:
            command.extend(["--timeout", str(max(int(timeout_seconds), 1))])
        if interval_seconds is not None:
            command.extend(["--interval", str(max(int(interval_seconds), 1))])
        if dry_run:
            command.append("--dry-run")
        return command


SHOW_ADAPTERS: dict[str, ShowAdapter] = {
    "personlighedspsykologi-en": ShowAdapter(
        show_slug="personlighedspsykologi-en",
        subject_slug="personlighedspsykologi",
        discovery_source="auto_spec_rules",
        discovery_path="shows/personlighedspsykologi-en/auto_spec.json",
        generator_script="notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py",
        downloader_script="notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py",
        show_config_path="shows/personlighedspsykologi-en/config.github.json",
        output_root="notebooklm-podcast-auto/personlighedspsykologi/output",
        prompt_config_path="notebooklm-podcast-auto/personlighedspsykologi/prompt_config.json",
        config_paths=(
            "shows/personlighedspsykologi-en/auto_spec.json",
            "shows/personlighedspsykologi-en/config.github.json",
            "notebooklm-podcast-auto/personlighedspsykologi/prompt_config.json",
        ),
        strict_download_output_root=True,
        include_profile_env_args=True,
    ),
    "personlighedspsykologi-da": ShowAdapter(
        show_slug="personlighedspsykologi-da",
        subject_slug="personlighedspsykologi",
        discovery_source="auto_spec_rules",
        discovery_path="shows/personlighedspsykologi-en/auto_spec.json",
        generator_script="notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py",
        downloader_script="notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py",
        show_config_path="shows/personlighedspsykologi-da/config.github.json",
        output_root="notebooklm-podcast-auto/personlighedspsykologi-da/output",
        prompt_config_path="notebooklm-podcast-auto/personlighedspsykologi-da/prompt_config.json",
        config_paths=(
            "shows/personlighedspsykologi-da/config.github.json",
            "shows/personlighedspsykologi-en/auto_spec.json",
            "shows/personlighedspsykologi-en/episode_metadata.json",
            "notebooklm-podcast-auto/personlighedspsykologi-da/prompt_config.json",
        ),
        default_content_types=("audio",),
        strict_download_output_root=True,
        include_profile_env_args=True,
    ),
    "bioneuro": ShowAdapter(
        show_slug="bioneuro",
        subject_slug="bioneuro",
        discovery_source="episode_metadata_source_folder",
        discovery_path="shows/bioneuro/episode_metadata.json",
        generator_script="notebooklm-podcast-auto/bioneuro/scripts/generate_week.py",
        downloader_script="notebooklm-podcast-auto/bioneuro/scripts/download_week.py",
        show_config_path="shows/bioneuro/config.github.json",
        output_root="notebooklm-podcast-auto/bioneuro/output",
        prompt_config_path="notebooklm-podcast-auto/bioneuro/prompt_config.json",
        config_paths=(
            "shows/bioneuro/auto_spec.json",
            "shows/bioneuro/config.github.json",
            "shows/bioneuro/episode_metadata.json",
            "notebooklm-podcast-auto/bioneuro/prompt_config.json",
        ),
        strict_download_output_root=True,
    ),
}


def _append_env_arg(command: list[str], *, option: str, env_name: str) -> None:
    if option in command:
        return
    value = str(os.environ.get(env_name) or "").strip()
    if value:
        command.extend([option, value])


def get_show_adapter(show_slug: str) -> ShowAdapter:
    adapter = SHOW_ADAPTERS.get(str(show_slug).strip())
    if adapter is None:
        raise KeyError(f"No queue adapter registered for show: {show_slug}")
    return adapter


def _discover_from_auto_spec_rules(path: Path) -> list[DiscoveredLecture]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rules = payload.get("rules") if isinstance(payload, dict) else None
    lectures: dict[str, DiscoveredLecture] = {}
    if isinstance(rules, list):
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            aliases = rule.get("aliases") if isinstance(rule.get("aliases"), list) else []
            canonical = None
            for alias in aliases:
                canonical = _canonical_lecture_key(str(alias))
                if canonical:
                    break
            if not canonical:
                continue
            lectures[canonical] = DiscoveredLecture(
                lecture_key=canonical,
                metadata={
                    "topic": rule.get("topic"),
                    "iso_week": rule.get("iso_week"),
                    "course_week": rule.get("course_week"),
                    "aliases": aliases,
                },
            )
    return [lectures[key] for key in sorted(lectures.keys())]


def _discover_from_episode_metadata(path: Path) -> list[DiscoveredLecture]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    candidates: dict[str, DiscoveredLecture] = {}

    def remember(raw_source_folder: object) -> None:
        lecture_key = _canonical_lecture_key(str(raw_source_folder or ""))
        if not lecture_key:
            return
        candidates.setdefault(
            lecture_key,
            DiscoveredLecture(
                lecture_key=lecture_key,
                metadata={"source_folder": str(raw_source_folder or "")},
            ),
        )

    if isinstance(payload, dict):
        by_id = payload.get("by_id")
        if isinstance(by_id, dict):
            for entry in by_id.values():
                meta = entry.get("meta") if isinstance(entry, dict) else None
                if isinstance(meta, dict):
                    remember(meta.get("source_folder"))
        by_name = payload.get("by_name")
        if isinstance(by_name, dict):
            for entry in by_name.values():
                meta = entry.get("meta") if isinstance(entry, dict) else None
                if isinstance(meta, dict):
                    remember(meta.get("source_folder"))
    return [candidates[key] for key in sorted(candidates.keys())]
