"""Show-specific queue adapters for discovery and command planning."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

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
    generator_script: str
    downloader_script: str
    show_config_path: str
    output_root: str
    config_paths: tuple[str, ...]
    default_content_types: tuple[str, ...] = ("audio", "infographic", "quiz")

    def discover_lectures(self, repo_root: Path) -> list[DiscoveredLecture]:
        if self.discovery_source == "auto_spec_rules":
            return _discover_from_auto_spec_rules(repo_root / "shows" / self.show_slug / "auto_spec.json")
        if self.discovery_source == "episode_metadata_source_folder":
            return _discover_from_episode_metadata(repo_root / "shows" / self.show_slug / "episode_metadata.json")
        raise ValueError(f"Unsupported discovery source: {self.discovery_source}")

    def config_hash(self, repo_root: Path) -> str:
        digest = hashlib.sha256()
        for relative in self.config_paths:
            path = repo_root / relative
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            if path.exists():
                digest.update(path.read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()[:16]

    def load_show_config(self, repo_root: Path) -> dict[str, object]:
        path = repo_root / self.show_config_path
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Expected object config in {path}")
        payload["__config_path__"] = str(path.resolve())
        return payload

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
        ]
        if wait:
            command.append("--wait")
        if dry_run:
            command.append("--dry-run")
        return command

    def build_download_command(self, repo_root: Path, *, lecture_key: str, dry_run: bool) -> list[str]:
        command = [
            str(repo_root / ".venv" / "bin" / "python"),
            str(repo_root / self.downloader_script),
            "--week",
            lecture_key,
        ]
        if dry_run:
            command.append("--dry-run")
        return command


SHOW_ADAPTERS: dict[str, ShowAdapter] = {
    "personlighedspsykologi-en": ShowAdapter(
        show_slug="personlighedspsykologi-en",
        subject_slug="personlighedspsykologi",
        discovery_source="auto_spec_rules",
        generator_script="notebooklm-podcast-auto/personlighedspsykologi/scripts/generate_week.py",
        downloader_script="notebooklm-podcast-auto/personlighedspsykologi/scripts/download_week.py",
        show_config_path="shows/personlighedspsykologi-en/config.github.json",
        output_root="notebooklm-podcast-auto/personlighedspsykologi/output",
        config_paths=(
            "shows/personlighedspsykologi-en/auto_spec.json",
            "shows/personlighedspsykologi-en/config.github.json",
            "notebooklm-podcast-auto/personlighedspsykologi/prompt_config.json",
        ),
    ),
    "bioneuro": ShowAdapter(
        show_slug="bioneuro",
        subject_slug="bioneuro",
        discovery_source="episode_metadata_source_folder",
        generator_script="notebooklm-podcast-auto/bioneuro/scripts/generate_week.py",
        downloader_script="notebooklm-podcast-auto/bioneuro/scripts/download_week.py",
        show_config_path="shows/bioneuro/config.github.json",
        output_root="notebooklm-podcast-auto/bioneuro/output",
        config_paths=(
            "shows/bioneuro/auto_spec.json",
            "shows/bioneuro/config.github.json",
            "shows/bioneuro/episode_metadata.json",
            "notebooklm-podcast-auto/bioneuro/prompt_config.json",
        ),
    ),
}


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
