#!/usr/bin/env python3
"""Build the Personlighedspsykologi learning-material regeneration registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from regeneration_identity import canonical_source_name, parse_config_tags  # noqa: E402


DEFAULT_SHOW_ROOT = "shows/personlighedspsykologi-en"
DEFAULT_OUTPUT_ROOT = "notebooklm-podcast-auto/personlighedspsykologi/output"
DEFAULT_REGISTRY = "shows/personlighedspsykologi-en/learning_material_regeneration_registry.json"


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


def normalize_lecture_key(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"\bW(\d{1,2})L(\d)\b", value, flags=re.IGNORECASE)
    if not match:
        return None
    return f"W{int(match.group(1)):02d}L{int(match.group(2))}"


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
) -> dict[str, dict[str, Any]]:
    media_by_name, inventory_by_name = build_media_maps(show_root)
    entries: dict[str, dict[str, Any]] = {}
    if not output_root.exists():
        return entries
    active_lecture_key = normalize_lecture_key(active_lecture_key)

    for log_path in sorted(output_root.glob("**/*.mp3.request*.json")):
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
        entry["lecture_key"] = lecture_key
        if inventory_item:
            entry["feed_title"] = inventory_item.get("title")
            entry["episode_kind"] = inventory_item.get("episode_kind")
            entry["podcast_kind"] = inventory_item.get("podcast_kind")
            entry["episode_key"] = inventory_item.get("episode_key")
        if media_item:
            entry["published_at"] = media_item.get("published_at")
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
            entry["artifact_paths"] = {
                "mp3": relpath(mp3_path, repo_root),
                "request_log": relpath(log_path, repo_root),
            }
            if mp3_path.exists():
                entry["local_size"] = mp3_path.stat().st_size
                entry["local_sha256"] = sha256_file(mp3_path)
        if campaign and (not active_lecture_key or active_lecture_key == lecture_key):
            entry["campaign"] = campaign
        if queue_job_id and (not active_lecture_key or active_lecture_key == lecture_key):
            entry["queue_job_id"] = queue_job_id

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

    return entries


def rendered_scaffold_paths(scaffold_json: Path, repo_root: Path) -> list[str]:
    rendered: list[str] = []
    for child in sorted(scaffold_json.parent.iterdir()):
        if child == scaffold_json:
            continue
        if child.suffix.lower() in {".md", ".pdf"}:
            rendered.append(relpath(child, repo_root))
    return rendered


def collect_printout_entries(*, output_root: Path, repo_root: Path) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    if not output_root.exists():
        return entries
    for scaffold_path in sorted(output_root.glob("*/scaffolding/*/reading-scaffolds.json")):
        payload = maybe_load_json(scaffold_path)
        if not isinstance(payload, dict):
            continue
        source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
        generator = payload.get("generator") if isinstance(payload.get("generator"), dict) else {}
        generation_config = generator.get("generation_config") if isinstance(generator.get("generation_config"), dict) else {}
        source_id = str(source.get("source_id") or scaffold_path.parent.name)
        material_id = f"printout:reading_scaffolds:{source_id}"
        entry = {
            "material_id": material_id,
            "family": "printout",
            "material_type": "reading_scaffolds",
            "status": "generated_local",
            "schema_version": payload.get("schema_version"),
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
            },
            "course_understanding": payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {},
            "artifact_paths": {
                "json": relpath(scaffold_path, repo_root),
                "rendered": rendered_scaffold_paths(scaffold_path, repo_root),
            },
        }
        entries[material_id] = entry
    return entries


def merge_entries(existing: dict[str, dict[str, Any]], discovered: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    merged = dict(existing)
    for material_id, entry in discovered.items():
        previous = merged.get(material_id)
        if previous and previous.get("attempts") and entry.get("attempts"):
            for attempt in previous.get("attempts") or []:
                if isinstance(attempt, dict):
                    merge_attempt(entry, attempt)
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
) -> dict[str, Any]:
    discovered: dict[str, dict[str, Any]] = {}
    discovered.update(
        collect_printout_entries(
            output_root=output_root,
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
        )
    )
    materials = merge_entries(existing_entries(registry_path), discovered)
    return {
        "schema_version": 1,
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
    payload = build_registry(
        repo_root=repo_root,
        show_root=show_root,
        output_root=output_root,
        registry_path=registry_path,
        generated_at=args.generated_at or utc_now_iso(),
        campaign=args.campaign,
        queue_job_id=args.queue_job_id,
        lecture_key=args.lecture_key,
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
