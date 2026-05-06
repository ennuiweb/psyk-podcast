#!/usr/bin/env python3
"""Build the Personlighedspsykologi learning-material regeneration registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from regeneration_identity import canonical_source_name, parse_config_tags  # noqa: E402


DEFAULT_SHOW_ROOT = "shows/personlighedspsykologi-en"
DEFAULT_OUTPUT_ROOT = "notebooklm-podcast-auto/personlighedspsykologi/output"
DEFAULT_REGISTRY = "shows/personlighedspsykologi-en/learning_material_regeneration_registry.json"
SETUP_VERSION_ENV = "PERSONLIGHEDSPSYKOLOGI_SETUP_VERSION"
PODCAST_SETUP_VERSION_ENV = "PERSONLIGHEDSPSYKOLOGI_PODCAST_SETUP_VERSION"
PRINTOUT_SETUP_VERSION_ENV = "PERSONLIGHEDSPSYKOLOGI_PRINTOUT_SETUP_VERSION"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Record learner-facing Personlighedspsykologi outputs regenerated from "
            "the current Course Understanding / prompt stack."
        )
    )
    parser.add_argument("--repo-root", default=".", help="Repository root.")
    parser.add_argument("--show-root", default=DEFAULT_SHOW_ROOT, help="Show root directory.")
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT, help="Generation output root.")
    parser.add_argument("--registry", default=DEFAULT_REGISTRY, help="Registry JSON path to write.")
    parser.add_argument("--campaign", help="Optional regeneration campaign label.")
    parser.add_argument("--queue-job-id", help="Optional queue job id for the current run.")
    parser.add_argument("--lecture-key", help="Optional lecture key for the current run.")
    parser.add_argument(
        "--setup-version",
        help=(
            "Optional human setup version to attach to both podcast and printout "
            "materials unless a family-specific version is supplied."
        ),
    )
    parser.add_argument(
        "--podcast-setup-version",
        help=f"Optional human podcast setup version. Falls back to ${PODCAST_SETUP_VERSION_ENV}.",
    )
    parser.add_argument(
        "--printout-setup-version",
        help=f"Optional human printout setup version. Falls back to ${PRINTOUT_SETUP_VERSION_ENV}.",
    )
    parser.add_argument("--generated-at", help="Override registry generated_at timestamp.")
    parser.add_argument("--dry-run", action="store_true", help="Print JSON instead of writing it.")
    return parser.parse_args()


def utc_now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def maybe_load_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    return load_json(path)


def write_json_if_changed(path: Path, payload: dict[str, Any]) -> bool:
    rendered = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == rendered:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    return True


def relpath(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_json(value: Any) -> str:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_text(rendered)


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(*parts: str) -> str:
    raw = "\n".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def short_hash(value: str, length: int = 16) -> str:
    return value[:length]


def normalize_lecture_key(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"\bW(\d{1,2})L(\d)\b", value, flags=re.IGNORECASE)
    if not match:
        return None
    return f"W{int(match.group(1)):02d}L{int(match.group(2))}"


def normalize_optional_text(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def resolve_setup_version(
    *,
    explicit: str | None,
    env_name: str,
    default: str | None = None,
) -> str | None:
    return normalize_optional_text(explicit) or normalize_optional_text(os.environ.get(env_name)) or default


def material_matches_lecture(entry: dict[str, Any], active_lecture_key: str | None) -> bool:
    if not active_lecture_key:
        return True
    entry_lecture_key = normalize_lecture_key(str(entry.get("lecture_key") or ""))
    if entry_lecture_key == active_lecture_key:
        return True
    for key in entry.get("lecture_keys") or []:
        if normalize_lecture_key(str(key or "")) == active_lecture_key:
            return True
    return False


def attach_setup_version(entry: dict[str, Any], *, setup_version: str | None, active_lecture_key: str | None) -> None:
    if setup_version and material_matches_lecture(entry, active_lecture_key):
        entry["setup_version"] = setup_version


def lecture_from_name(name: str) -> str | None:
    match = re.search(r"\b(W\d{1,2}L\d)\b", name, flags=re.IGNORECASE)
    if not match:
        return None
    return normalize_lecture_key(match.group(1))


def canonical_material_name(source_name: str) -> str:
    name = canonical_source_name(source_name)
    lecture_key = lecture_from_name(name)
    if lecture_key:
        name = re.sub(r"\bW\d{1,2}L\d\b", lecture_key, name, count=1, flags=re.IGNORECASE)
    return name


def material_identity_name(source_name: str) -> str:
    return re.sub(r"\.[^.]+$", "", canonical_material_name(source_name))


def source_name_from_request_log(path: Path) -> str:
    name = path.name
    if name.endswith(".request.error.json"):
        return name[: -len(".request.error.json")]
    if name.endswith(".request.json"):
        return name[: -len(".request.json")]
    return name


def source_name_from_mp3_path(value: Any, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return Path(value).name
    return fallback


def source_understanding_snapshot(show_root: Path, repo_root: Path) -> dict[str, Any]:
    source_root = show_root / "source_intelligence"
    index_path = source_root / "index.json"
    synthesis_path = source_root / "course_synthesis.json"
    index = maybe_load_json(index_path) or {}
    synthesis = maybe_load_json(synthesis_path) or {}
    synthesis_build = synthesis.get("build") if isinstance(synthesis, dict) else {}
    return {
        "index_path": relpath(index_path, repo_root),
        "index_generated_at": index.get("generated_at") if isinstance(index, dict) else None,
        "index_sha256": sha256_file(index_path),
        "course_synthesis_path": relpath(synthesis_path, repo_root),
        "course_synthesis_generated_at": synthesis.get("generated_at") if isinstance(synthesis, dict) else None,
        "course_synthesis_sha256": sha256_file(synthesis_path),
        "course_synthesis_prompt_version": (
            synthesis_build.get("prompt_version") if isinstance(synthesis_build, dict) else None
        ),
    }


def build_media_maps(show_root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    media_by_name: dict[str, dict[str, Any]] = {}
    inventory_by_name: dict[str, dict[str, Any]] = {}

    media = maybe_load_json(show_root / "media_manifest.r2.json")
    if isinstance(media, dict):
        for item in media.get("items") or []:
            if not isinstance(item, dict):
                continue
            for key in (item.get("source_name"), Path(str(item.get("source_path") or "")).name):
                if str(key or "").strip():
                    raw_key = str(key)
                    media_by_name[raw_key] = item
                    media_by_name[canonical_material_name(raw_key)] = item

    inventory = maybe_load_json(show_root / "episode_inventory.json")
    if isinstance(inventory, dict):
        for episode in inventory.get("episodes") or []:
            if not isinstance(episode, dict):
                continue
            for key in (episode.get("source_name"), Path(str(episode.get("source_path") or "")).name):
                if str(key or "").strip():
                    raw_key = str(key)
                    inventory_by_name[raw_key] = episode
                    inventory_by_name[canonical_material_name(raw_key)] = episode

    return media_by_name, inventory_by_name


def source_name_from_surface_item(item: dict[str, Any]) -> str:
    for key in ("source_name", "name"):
        value = str(item.get(key) or "").strip()
        if value:
            return Path(value).name
    for key in ("source_path", "object_key", "source_storage_key", "key"):
        value = str(item.get(key) or "").strip()
        if value:
            return Path(value).name
    return ""


def collect_published_podcast_entries(*, show_root: Path, repo_root: Path) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    media_by_name, inventory_by_name = build_media_maps(show_root)

    def upsert(source_name: str, *, media_item: dict[str, Any] | None, inventory_item: dict[str, Any] | None) -> None:
        source_name = source_name.strip()
        if not source_name:
            return
        canonical_name = canonical_material_name(source_name)
        material_id = f"podcast:{stable_id(canonical_name)}"
        tags = parse_config_tags(source_name)
        entry = entries.setdefault(
            material_id,
            {
                "material_id": material_id,
                "family": "podcast",
                "material_type": "audio",
                "lecture_key": lecture_from_name(source_name),
                "source_name": source_name,
                "canonical_source_name": canonical_name,
                "config_tags": tags,
                "config_hash": tags.get("hash"),
                "status": "published_media",
                "artifact_paths": {},
                "attempts": [],
            },
        )
        if inventory_item:
            entry["status"] = "published_active"
            entry["feed_title"] = inventory_item.get("title")
            entry["episode_kind"] = inventory_item.get("episode_kind")
            entry["podcast_kind"] = inventory_item.get("podcast_kind")
            entry["episode_key"] = inventory_item.get("episode_key")
            entry["feed_published_at"] = inventory_item.get("published_at")
            entry["published_at"] = inventory_item.get("published_at") or entry.get("published_at")
            entry["public_url"] = inventory_item.get("audio_url")
            entry["artifact_paths"]["episode_inventory"] = relpath(show_root / "episode_inventory.json", repo_root)
        if media_item:
            entry["media_published_at"] = media_item.get("published_at")
            entry["published_at"] = entry.get("published_at") or media_item.get("published_at")
            entry["public_url"] = media_item.get("public_url") or entry.get("public_url")
            entry["media_sha256"] = media_item.get("sha256")
            entry["media_size"] = media_item.get("size")
            if media_item.get("stable_guid"):
                entry["stable_guid"] = media_item.get("stable_guid")
            entry["artifact_paths"]["media_manifest"] = relpath(show_root / "media_manifest.r2.json", repo_root)

    inventory = maybe_load_json(show_root / "episode_inventory.json")
    if isinstance(inventory, dict):
        for item in inventory.get("episodes") or []:
            if not isinstance(item, dict):
                continue
            source_name = source_name_from_surface_item(item)
            canonical_name = canonical_material_name(source_name) if source_name else ""
            media_item = media_by_name.get(source_name) or media_by_name.get(canonical_name)
            upsert(source_name, media_item=media_item, inventory_item=item)

    media = maybe_load_json(show_root / "media_manifest.r2.json")
    if isinstance(media, dict):
        for item in media.get("items") or []:
            if not isinstance(item, dict):
                continue
            source_name = source_name_from_surface_item(item)
            canonical_name = canonical_material_name(source_name) if source_name else ""
            inventory_item = inventory_by_name.get(source_name) or inventory_by_name.get(canonical_name)
            upsert(source_name, media_item=item, inventory_item=inventory_item)

    return entries


def merge_attempt(existing: dict[str, Any], attempt: dict[str, Any]) -> None:
    attempts = existing.setdefault("attempts", [])
    if not isinstance(attempts, list):
        attempts = []
        existing["attempts"] = attempts
    key = (
        attempt.get("status"),
        attempt.get("created_at"),
        attempt.get("request_log_path"),
        attempt.get("error"),
    )
    for item in attempts:
        if not isinstance(item, dict):
            continue
        other = (
            item.get("status"),
            item.get("created_at"),
            item.get("request_log_path"),
            item.get("error"),
        )
        if other == key:
            return
    attempts.append(attempt)
    attempts.sort(key=lambda item: str(item.get("created_at") or ""))


def collect_podcast_entries(
    *,
    output_root: Path,
    repo_root: Path,
    show_root: Path,
    campaign: str | None,
    queue_job_id: str | None,
    active_lecture_key: str | None,
    setup_version: str | None,
) -> dict[str, dict[str, Any]]:
    media_by_name, inventory_by_name = build_media_maps(show_root)
    entries = collect_published_podcast_entries(show_root=show_root, repo_root=repo_root)
    active_lecture_key = normalize_lecture_key(active_lecture_key)

    log_paths = sorted(output_root.glob("**/*.mp3.request*.json")) if output_root.exists() else []
    for log_path in log_paths:
        source_name = source_name_from_request_log(log_path)
        payload = maybe_load_json(log_path)
        if not isinstance(payload, dict):
            continue
        auth = payload.get("auth") if isinstance(payload.get("auth"), dict) else {}
        output_name = source_name_from_mp3_path(payload.get("output_path"), source_name)
        canonical_name = canonical_material_name(output_name)
        material_id = f"podcast:{stable_id(canonical_name)}"
        lecture_key = lecture_from_name(output_name) or lecture_from_name(source_name)
        mp3_path = Path(str(payload.get("output_path") or ""))
        if not mp3_path.is_absolute():
            mp3_path = (repo_root / mp3_path).resolve()
        success = log_path.name.endswith(".request.json")
        media_item = media_by_name.get(output_name) or media_by_name.get(source_name) or media_by_name.get(canonical_name)
        inventory_item = (
            inventory_by_name.get(output_name) or inventory_by_name.get(source_name) or inventory_by_name.get(canonical_name)
        )
        status = "generated_local" if success else "failed_generation"
        if success and media_item:
            status = "published_media"
        if success and inventory_item:
            status = "published_active"

        is_new_entry = material_id not in entries
        entry = entries.setdefault(
            material_id,
            {
                "material_id": material_id,
                "family": "podcast",
                "material_type": "audio",
                "lecture_key": lecture_key,
                "source_name": output_name,
                "canonical_source_name": canonical_name,
                "status": status,
                "attempts": [],
            },
        )
        existing_status = str(entry.get("status") or "")
        if success or existing_status in {"", "failed_generation"}:
            entry["status"] = status
        entry["canonical_source_name"] = canonical_name
        if success or is_new_entry or not str(entry.get("source_name") or "").strip():
            entry["source_name"] = output_name
            entry["config_tags"] = parse_config_tags(output_name)
            entry["config_hash"] = entry["config_tags"].get("hash")
        entry["lecture_key"] = lecture_key
        if inventory_item:
            entry["feed_title"] = inventory_item.get("title")
            entry["episode_kind"] = inventory_item.get("episode_kind")
            entry["podcast_kind"] = inventory_item.get("podcast_kind")
            entry["episode_key"] = inventory_item.get("episode_key")
            entry["feed_published_at"] = inventory_item.get("published_at")
            entry["published_at"] = inventory_item.get("published_at") or entry.get("published_at")
        if media_item:
            entry["media_published_at"] = media_item.get("published_at")
            entry["published_at"] = entry.get("published_at") or media_item.get("published_at")
            entry["public_url"] = media_item.get("public_url")
            entry["media_sha256"] = media_item.get("sha256")
        if success:
            entry["generated_at"] = payload.get("created_at")
            entry["artifact_id"] = payload.get("artifact_id")
            entry["prompt_sha256"] = sha256_text(str(payload.get("instructions") or ""))
            entry["prompt_length"] = len(str(payload.get("instructions") or ""))
            entry["auth"] = {
                "profile": auth.get("profile"),
                "source": auth.get("source"),
                "profiles_file": auth.get("profiles_file"),
            }
            artifact_paths = entry.get("artifact_paths") if isinstance(entry.get("artifact_paths"), dict) else {}
            artifact_paths.update(
                {
                    "mp3": relpath(mp3_path, repo_root),
                    "request_log": relpath(log_path, repo_root),
                }
            )
            entry["artifact_paths"] = artifact_paths
            if mp3_path.exists():
                entry["local_size"] = mp3_path.stat().st_size
                entry["local_sha256"] = sha256_file(mp3_path)
        if campaign and (not active_lecture_key or active_lecture_key == lecture_key):
            entry["campaign"] = campaign
        if queue_job_id and (not active_lecture_key or active_lecture_key == lecture_key):
            entry["queue_job_id"] = queue_job_id
        attach_setup_version(entry, setup_version=setup_version, active_lecture_key=active_lecture_key)

        attempt = {
            "status": "success" if success else "failed",
            "created_at": payload.get("created_at"),
            "request_log_path": relpath(log_path, repo_root),
            "auth_profile": auth.get("profile"),
            "auth_source": auth.get("source"),
        }
        if not success:
            attempt["error"] = payload.get("error") or payload.get("status")
        merge_attempt(entry, attempt)

    for entry in entries.values():
        attach_setup_version(entry, setup_version=setup_version, active_lecture_key=active_lecture_key)

    return entries


def quiz_id_from_link(link: dict[str, Any]) -> str | None:
    for key in ("quiz_id", "relative_path", "quiz_url", "url"):
        raw = str(link.get(key) or "").strip()
        if raw:
            stem = Path(raw.split("?", 1)[0]).stem
            if stem:
                return stem
    return None


def quiz_path_from_link(link: dict[str, Any]) -> str | None:
    raw = str(link.get("relative_path") or link.get("quiz_url") or link.get("url") or "").strip()
    if not raw:
        return None
    parsed_path = urlparse(raw).path
    if parsed_path:
        raw = parsed_path
    if raw.startswith("/q/"):
        return raw[3:]
    if raw.startswith("q/"):
        return raw[2:]
    return raw.lstrip("/")


def iter_quiz_link_items(payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    items: list[tuple[str, dict[str, Any]]] = []
    by_name = payload.get("by_name")
    if not isinstance(by_name, dict):
        return items
    for source_name, raw_entry in by_name.items():
        if not isinstance(raw_entry, dict):
            continue
        raw_links = raw_entry.get("links")
        links = [link for link in raw_links if isinstance(link, dict)] if isinstance(raw_links, list) else []
        if not links:
            links = [raw_entry]
        for link in links:
            items.append((str(source_name), link))
    return items


def content_manifest_contexts(show_root: Path, repo_root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    manifest_path = show_root / "content_manifest.json"
    payload = maybe_load_json(manifest_path)
    quiz_contexts: dict[str, dict[str, Any]] = {}
    slide_contexts: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(payload, dict):
        return quiz_contexts, slide_contexts

    def add_quiz(raw_quiz: Any, context: dict[str, Any]) -> None:
        if not isinstance(raw_quiz, dict):
            return
        quiz_id = quiz_id_from_link(raw_quiz)
        if not quiz_id:
            return
        quiz_contexts[quiz_id] = {
            **context,
            "quiz_url": raw_quiz.get("quiz_url"),
            "episode_title": raw_quiz.get("episode_title"),
            "content_manifest_path": relpath(manifest_path, repo_root),
        }

    for lecture in payload.get("lectures") or []:
        if not isinstance(lecture, dict):
            continue
        lecture_key = normalize_lecture_key(str(lecture.get("lecture_key") or ""))
        lecture_title = lecture.get("lecture_title")
        lecture_context = {"scope": "lecture", "lecture_key": lecture_key, "lecture_title": lecture_title}

        lecture_assets = lecture.get("lecture_assets") if isinstance(lecture.get("lecture_assets"), dict) else {}
        for quiz in lecture_assets.get("quizzes") or []:
            add_quiz(quiz, lecture_context)

        for reading in lecture.get("readings") or []:
            if not isinstance(reading, dict):
                continue
            context = {
                "scope": "reading",
                "lecture_key": lecture_key,
                "lecture_title": lecture_title,
                "source_id": reading.get("reading_key"),
                "source_title": reading.get("reading_title"),
            }
            assets = reading.get("assets") if isinstance(reading.get("assets"), dict) else {}
            for quiz in assets.get("quizzes") or []:
                add_quiz(quiz, context)

        for slide in lecture.get("slides") or []:
            if not isinstance(slide, dict):
                continue
            slide_key = str(slide.get("slide_key") or "").strip()
            context = {
                "scope": "slide",
                "lecture_key": lecture_key,
                "lecture_title": lecture_title,
                "slide_key": slide_key,
                "slide_title": slide.get("title"),
                "slide_subcategory": slide.get("subcategory"),
                "slide_relative_path": slide.get("relative_path"),
            }
            if slide_key:
                slide_contexts.setdefault(slide_key, []).append(
                    {
                        "lecture_key": lecture_key,
                        "lecture_title": lecture_title,
                        "subcategory": slide.get("subcategory"),
                        "title": slide.get("title"),
                        "relative_path": slide.get("relative_path"),
                        "content_manifest_path": relpath(manifest_path, repo_root),
                    }
                )
            assets = slide.get("assets") if isinstance(slide.get("assets"), dict) else {}
            for quiz in assets.get("quizzes") or []:
                add_quiz(quiz, context)

    return quiz_contexts, slide_contexts


def collect_local_quiz_entries(*, output_root: Path, repo_root: Path) -> dict[tuple[str, str], dict[str, Any]]:
    entries: dict[tuple[str, str], dict[str, Any]] = {}
    if not output_root.exists():
        return entries
    for quiz_path in sorted(output_root.glob("**/*.json")):
        if ".request" in quiz_path.name or quiz_path.name == "quiz_json_manifest.json":
            continue
        tags = parse_config_tags(quiz_path.name)
        if tags.get("type") != "quiz":
            continue
        difficulty = str(tags.get("difficulty") or "unknown").strip() or "unknown"
        identity_name = material_identity_name(quiz_path.name)
        request_path = Path(f"{quiz_path}.request.json")
        request_payload = maybe_load_json(request_path)
        if not isinstance(request_payload, dict):
            request_payload = {}
        auth = request_payload.get("auth") if isinstance(request_payload.get("auth"), dict) else {}
        key = (identity_name, difficulty)
        entry = {
            "material_id": f"quiz:{stable_id(identity_name, difficulty)}",
            "family": "quiz",
            "material_type": "quiz",
            "status": "generated_local",
            "lecture_key": lecture_from_name(quiz_path.name),
            "source_name": quiz_path.name,
            "canonical_source_name": canonical_material_name(quiz_path.name),
            "source_identity": identity_name,
            "difficulty": difficulty,
            "format": tags.get("download") or quiz_path.suffix.lstrip("."),
            "config_tags": tags,
            "config_hash": tags.get("hash"),
            "generated_at": request_payload.get("created_at"),
            "artifact_id": request_payload.get("artifact_id"),
            "local_size": quiz_path.stat().st_size,
            "local_sha256": sha256_file(quiz_path),
            "artifact_paths": {"json": relpath(quiz_path, repo_root)},
        }
        if request_path.exists():
            entry["artifact_paths"]["request_log"] = relpath(request_path, repo_root)
        instructions = str(request_payload.get("instructions") or "")
        if instructions:
            entry["prompt_sha256"] = sha256_text(instructions)
            entry["prompt_length"] = len(instructions)
        if auth:
            entry["auth"] = {
                "profile": auth.get("profile"),
                "source": auth.get("source"),
                "profiles_file": auth.get("profiles_file"),
            }
        entries[key] = entry
    return entries


def collect_quiz_entries(*, show_root: Path, output_root: Path, repo_root: Path) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    quiz_links_path = show_root / "quiz_links.json"
    quiz_links = maybe_load_json(quiz_links_path)
    local_entries = collect_local_quiz_entries(output_root=output_root, repo_root=repo_root)
    quiz_contexts, _slide_contexts = content_manifest_contexts(show_root, repo_root)

    consumed_local_keys: set[tuple[str, str]] = set()
    if isinstance(quiz_links, dict):
        for source_name, link in iter_quiz_link_items(quiz_links):
            quiz_id = quiz_id_from_link(link)
            quiz_path = quiz_path_from_link(link)
            if not quiz_id or not quiz_path:
                continue
            difficulty = str(link.get("difficulty") or parse_config_tags(source_name).get("difficulty") or "unknown")
            identity_name = material_identity_name(source_name)
            source_config_tags = parse_config_tags(source_name)
            local_key = (identity_name, difficulty)
            local_entry = local_entries.get(local_key)
            context = quiz_contexts.get(quiz_id)
            status = "published_active" if context else "published_linked"
            material_id = f"quiz:{quiz_id}"
            entry: dict[str, Any] = {
                "material_id": material_id,
                "family": "quiz",
                "material_type": "quiz",
                "status": status,
                "lecture_key": lecture_from_name(source_name),
                "source_name": source_name,
                "canonical_source_name": canonical_material_name(source_name),
                "source_identity": identity_name,
                "quiz_id": quiz_id,
                "difficulty": difficulty,
                "format": link.get("format") or Path(quiz_path).suffix.lstrip("."),
                "subject_slug": link.get("subject_slug"),
                "source_config_tags": source_config_tags,
                "source_config_hash": source_config_tags.get("hash"),
                "public_relative_path": f"/q/{quiz_path}",
                "artifact_paths": {"quiz_links": relpath(quiz_links_path, repo_root)},
            }
            if context:
                entry["content_manifest"] = context
                entry["artifact_paths"]["content_manifest"] = context["content_manifest_path"]
                entry["lecture_key"] = context.get("lecture_key") or entry["lecture_key"]
                if context.get("source_title"):
                    entry["source_title"] = context.get("source_title")
                if context.get("slide_title"):
                    entry["source_title"] = context.get("slide_title")
            if local_entry:
                consumed_local_keys.add(local_key)
                entry["generated_at"] = local_entry.get("generated_at")
                entry["artifact_id"] = local_entry.get("artifact_id")
                entry["local_size"] = local_entry.get("local_size")
                entry["local_sha256"] = local_entry.get("local_sha256")
                entry["config_tags"] = local_entry.get("config_tags")
                entry["config_hash"] = local_entry.get("config_hash")
                if local_entry.get("auth"):
                    entry["auth"] = local_entry["auth"]
                if local_entry.get("prompt_sha256"):
                    entry["prompt_sha256"] = local_entry["prompt_sha256"]
                    entry["prompt_length"] = local_entry.get("prompt_length")
                local_paths = local_entry.get("artifact_paths") if isinstance(local_entry.get("artifact_paths"), dict) else {}
                entry["artifact_paths"].update(local_paths)
            entries[material_id] = entry

    for key, entry in local_entries.items():
        if key not in consumed_local_keys:
            entries[str(entry["material_id"])] = entry
    return entries


def collect_slide_entries(*, show_root: Path, repo_root: Path) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    slides_catalog_path = show_root / "slides_catalog.json"
    payload = maybe_load_json(slides_catalog_path)
    if not isinstance(payload, dict):
        return entries
    _quiz_contexts, slide_contexts = content_manifest_contexts(show_root, repo_root)
    catalog_generated_at = payload.get("generated_at")
    for slide in payload.get("slides") or []:
        if not isinstance(slide, dict):
            continue
        slide_key = str(slide.get("slide_key") or "").strip()
        if not slide_key:
            continue
        contexts = slide_contexts.get(slide_key, [])
        raw_lecture_keys = slide.get("lecture_keys")
        lecture_keys = [normalize_lecture_key(str(slide.get("lecture_key") or ""))]
        if isinstance(raw_lecture_keys, list):
            lecture_keys.extend(normalize_lecture_key(str(item or "")) for item in raw_lecture_keys)
        if contexts:
            lecture_keys.extend(normalize_lecture_key(str(item.get("lecture_key") or "")) for item in contexts)
        lecture_keys = sorted({key for key in lecture_keys if key})
        relative_path = str(slide.get("relative_path") or "").strip()
        entry: dict[str, Any] = {
            "material_id": f"slide:{slide_key}",
            "family": "slide",
            "material_type": "slide_deck",
            "status": "published_active" if contexts else "cataloged",
            "lecture_key": lecture_keys[0] if lecture_keys else None,
            "lecture_keys": lecture_keys,
            "slide_key": slide_key,
            "slide_subcategory": slide.get("subcategory"),
            "source_title": slide.get("title"),
            "source_filename": slide.get("source_filename"),
            "matched_by": slide.get("matched_by"),
            "local_relative_path": slide.get("local_relative_path"),
            "catalog_generated_at": catalog_generated_at,
            "artifact_paths": {"slides_catalog": relpath(slides_catalog_path, repo_root)},
        }
        if relative_path:
            entry["relative_path"] = relative_path
            entry["public_relative_path"] = f"/slides/personlighedspsykologi/{relative_path}"
        if contexts:
            entry["content_manifest"] = contexts
            entry["artifact_paths"]["content_manifest"] = contexts[0]["content_manifest_path"]
        entries[str(entry["material_id"])] = entry
    return entries


def rendered_scaffold_paths(scaffold_json: Path, repo_root: Path) -> list[str]:
    rendered: list[str] = []
    for child in sorted(scaffold_json.parent.iterdir()):
        if child == scaffold_json:
            continue
        if child.suffix.lower() in {".md", ".pdf"}:
            rendered.append(relpath(child, repo_root))
    return rendered


def printout_setup_fingerprint_payload(
    *,
    payload: dict[str, Any],
    generator: dict[str, Any],
    generation_config: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": payload.get("schema_version"),
        "artifact_type": payload.get("artifact_type"),
        "generator": {
            "provider": generator.get("provider"),
            "model": generator.get("model"),
            "prompt_version": generator.get("prompt_version"),
            "generation_config": generation_config,
        },
    }


def collect_printout_entries(
    *,
    output_root: Path,
    repo_root: Path,
    setup_version: str | None,
    active_lecture_key: str | None,
) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    if not output_root.exists():
        return entries
    active_lecture_key = normalize_lecture_key(active_lecture_key)
    for scaffold_path in sorted(output_root.glob("*/scaffolding/*/reading-scaffolds.json")):
        payload = maybe_load_json(scaffold_path)
        if not isinstance(payload, dict):
            continue
        source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
        generator = payload.get("generator") if isinstance(payload.get("generator"), dict) else {}
        generation_config = generator.get("generation_config") if isinstance(generator.get("generation_config"), dict) else {}
        course_understanding = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
        config_fingerprint = sha256_json(
            printout_setup_fingerprint_payload(
                payload=payload,
                generator=generator,
                generation_config=generation_config,
            )
        )
        course_understanding_fingerprint = sha256_json(course_understanding) if course_understanding else None
        source_id = str(source.get("source_id") or scaffold_path.parent.name)
        material_id = f"printout:reading_scaffolds:{source_id}"
        entry = {
            "material_id": material_id,
            "family": "printout",
            "material_type": "reading_scaffolds",
            "status": "generated_local",
            "schema_version": payload.get("schema_version"),
            "config_hash": short_hash(config_fingerprint),
            "config_fingerprint": config_fingerprint,
            "lecture_key": source.get("lecture_key"),
            "source_id": source_id,
            "source_title": source.get("title"),
            "source_family": source.get("source_family"),
            "generated_at": payload.get("generated_at"),
            "generator": {
                "provider": generator.get("provider"),
                "model": generator.get("model"),
                "prompt_version": generator.get("prompt_version"),
                "generation_config_version": generation_config.get("version"),
                "generation_config": generation_config,
            },
            "course_understanding": course_understanding,
            "course_understanding_fingerprint": course_understanding_fingerprint,
            "artifact_paths": {
                "json": relpath(scaffold_path, repo_root),
                "rendered": rendered_scaffold_paths(scaffold_path, repo_root),
            },
        }
        attach_setup_version(entry, setup_version=setup_version, active_lecture_key=active_lecture_key)
        entries[material_id] = entry
    return entries


REVISION_HISTORY_KEYS = (
    "status",
    "source_name",
    "setup_version",
    "config_hash",
    "config_fingerprint",
    "source_config_hash",
    "prompt_sha256",
    "course_understanding_fingerprint",
    "generated_at",
    "published_at",
    "feed_published_at",
    "media_published_at",
    "media_sha256",
    "local_sha256",
    "public_relative_path",
    "public_url",
)


def revision_snapshot(entry: dict[str, Any]) -> dict[str, Any]:
    snapshot = {
        key: entry.get(key)
        for key in REVISION_HISTORY_KEYS
        if entry.get(key) not in (None, "", {}, [])
    }
    return snapshot


def merge_revision_history(previous: dict[str, Any], entry: dict[str, Any]) -> None:
    history = [
        item
        for item in previous.get("revision_history") or []
        if isinstance(item, dict)
    ]
    previous_snapshot = revision_snapshot(previous)
    current_snapshot = revision_snapshot(entry)
    if previous_snapshot and current_snapshot and previous_snapshot != current_snapshot and previous_snapshot not in history:
        history.append(previous_snapshot)
    if history:
        entry["revision_history"] = history[-25:]


def merge_entries(existing: dict[str, dict[str, Any]], discovered: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    merged = dict(existing)
    for material_id, entry in discovered.items():
        previous = merged.get(material_id)
        if previous and previous.get("attempts") and entry.get("attempts"):
            for attempt in previous.get("attempts") or []:
                if isinstance(attempt, dict):
                    merge_attempt(entry, attempt)
        if previous:
            if not entry.get("setup_version") and previous.get("setup_version"):
                entry["setup_version"] = previous["setup_version"]
            merge_revision_history(previous, entry)
        merged[material_id] = entry
    return sorted(
        merged.values(),
        key=lambda item: (
            str(item.get("family") or ""),
            str(item.get("lecture_key") or ""),
            str(item.get("source_title") or item.get("source_name") or ""),
            str(item.get("material_id") or ""),
        ),
    )


def existing_entries(path: Path) -> dict[str, dict[str, Any]]:
    payload = maybe_load_json(path)
    if not isinstance(payload, dict):
        return {}
    entries: dict[str, dict[str, Any]] = {}
    for item in payload.get("materials") or []:
        if isinstance(item, dict) and str(item.get("material_id") or "").strip():
            entries[str(item["material_id"])] = item
    return entries


def summarize(materials: list[dict[str, Any]]) -> dict[str, Any]:
    by_family: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for item in materials:
        family = str(item.get("family") or "unknown")
        status = str(item.get("status") or "unknown")
        material_type = str(item.get("material_type") or "unknown")
        by_family[family] = by_family.get(family, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
        by_type[material_type] = by_type.get(material_type, 0) + 1
    return {
        "total": len(materials),
        "by_family": dict(sorted(by_family.items())),
        "by_status": dict(sorted(by_status.items())),
        "by_material_type": dict(sorted(by_type.items())),
    }


def build_registry(
    *,
    repo_root: Path,
    show_root: Path,
    output_root: Path,
    registry_path: Path,
    generated_at: str,
    campaign: str | None,
    queue_job_id: str | None,
    lecture_key: str | None,
    podcast_setup_version: str | None,
    printout_setup_version: str | None,
) -> dict[str, Any]:
    lecture_key = normalize_lecture_key(lecture_key)
    discovered: dict[str, dict[str, Any]] = {}
    discovered.update(
        collect_printout_entries(
            output_root=output_root,
            repo_root=repo_root,
            setup_version=printout_setup_version,
            active_lecture_key=lecture_key,
        )
    )
    discovered.update(
        collect_quiz_entries(
            show_root=show_root,
            output_root=output_root,
            repo_root=repo_root,
        )
    )
    discovered.update(
        collect_slide_entries(
            show_root=show_root,
            repo_root=repo_root,
        )
    )
    discovered.update(
        collect_podcast_entries(
            output_root=output_root,
            repo_root=repo_root,
            show_root=show_root,
            campaign=campaign,
            queue_job_id=queue_job_id,
            active_lecture_key=lecture_key,
            setup_version=podcast_setup_version,
        )
    )
    materials = merge_entries(existing_entries(registry_path), discovered)
    return {
        "schema_version": 3,
        "show_slug": "personlighedspsykologi-en",
        "subject_slug": "personlighedspsykologi",
        "generated_at": generated_at,
        "purpose": (
            "Durable ledger of learner-facing materials regenerated while iterating "
            "on the Course Understanding Pipeline and downstream prompt/output layers."
        ),
        "current_run": {
            "campaign": campaign,
            "queue_job_id": queue_job_id,
            "lecture_key": lecture_key,
            "podcast_setup_version": podcast_setup_version,
            "printout_setup_version": printout_setup_version,
        },
        "source_understanding_snapshot": source_understanding_snapshot(show_root, repo_root),
        "summary": summarize(materials),
        "materials": materials,
    }


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).expanduser().resolve()
    show_root = (repo_root / args.show_root).resolve() if not Path(args.show_root).is_absolute() else Path(args.show_root)
    output_root = (
        (repo_root / args.output_root).resolve()
        if not Path(args.output_root).is_absolute()
        else Path(args.output_root).resolve()
    )
    registry_path = (
        (repo_root / args.registry).resolve()
        if not Path(args.registry).is_absolute()
        else Path(args.registry).resolve()
    )
    default_setup_version = resolve_setup_version(
        explicit=args.setup_version,
        env_name=SETUP_VERSION_ENV,
    )
    podcast_setup_version = resolve_setup_version(
        explicit=args.podcast_setup_version,
        env_name=PODCAST_SETUP_VERSION_ENV,
        default=default_setup_version,
    )
    printout_setup_version = resolve_setup_version(
        explicit=args.printout_setup_version,
        env_name=PRINTOUT_SETUP_VERSION_ENV,
        default=default_setup_version,
    )
    payload = build_registry(
        repo_root=repo_root,
        show_root=show_root,
        output_root=output_root,
        registry_path=registry_path,
        generated_at=args.generated_at or utc_now_iso(),
        campaign=args.campaign,
        queue_job_id=args.queue_job_id,
        lecture_key=args.lecture_key,
        podcast_setup_version=podcast_setup_version,
        printout_setup_version=printout_setup_version,
    )
    if args.dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))
        return 0
    changed = write_json_if_changed(registry_path, payload)
    print(f"{'Updated' if changed else 'No changes'}: {relpath(registry_path, repo_root)}")
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
