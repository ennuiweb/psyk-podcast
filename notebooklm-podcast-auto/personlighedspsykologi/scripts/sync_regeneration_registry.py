#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from regeneration_identity import (  # noqa: E402
    canonical_source_name,
    classify_episode,
    extract_lecture_key,
    logical_episode_id,
    parse_config_tags,
)

PROMPT_TYPE_ORDER = {
    "weekly_readings_only": 0,
    "single_reading": 1,
    "single_slide": 2,
    "short": 3,
    "tts": 4,
    "unknown": 9,
}


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
def default_rollout(prompt_type: str, campaign: str) -> dict:
    in_scope = prompt_type != "tts"
    return {
        "campaign": campaign if in_scope else None,
        "in_scope": in_scope,
        "state": "original_only" if in_scope else "out_of_scope",
        "notes": [],
        "activated_at": None,
    }


def default_variant(slot: str) -> dict:
    if slot == "A":
        return {
            "status": "missing",
            "source_name": None,
            "canonical_source_name": None,
            "config_tags": {},
            "config_hash": None,
            "episode_key": None,
            "audio_url": None,
            "published_at": None,
            "title": None,
            "audio_sha256": None,
        }
    return {
        "status": "not_generated",
        "source_name": None,
        "canonical_source_name": None,
        "config_tags": {},
        "config_hash": None,
        "episode_key": None,
        "audio_url": None,
        "published_at": None,
        "title": None,
        "local_audio_path": None,
        "staging_drive_id": None,
        "audio_sha256": None,
        "generated_at": None,
        "uploaded_at": None,
        "registered_at": None,
        "transcribed_at": None,
        "judged_at": None,
        "review_outcome": None,
        "size_bytes": None,
        "drive_md5": None,
        "history": [],
    }


def build_baseline_variant(episode: dict) -> dict:
    source_name = str(episode.get("source_name") or "").strip()
    tags = parse_config_tags(source_name)
    return {
        "status": "published",
        "source_name": source_name,
        "canonical_source_name": canonical_source_name(source_name),
        "config_tags": tags,
        "config_hash": tags.get("hash"),
        "episode_key": episode.get("episode_key"),
        "audio_url": episode.get("audio_url"),
        "published_at": episode.get("published_at"),
        "title": episode.get("title"),
        "audio_sha256": None,
    }


def media_manifest_source_name(item: dict) -> str:
    source_name = str(item.get("source_name") or item.get("name") or "").strip()
    if source_name:
        return source_name
    object_key = str(
        item.get("object_key")
        or item.get("source_storage_key")
        or item.get("key")
        or item.get("source_path")
        or ""
    ).strip()
    return Path(object_key).name if object_key else ""


def media_manifest_episode_key(item: dict) -> str | None:
    for key in (
        "object_key",
        "source_storage_key",
        "key",
        "episode_key",
        "source_drive_file_id",
        "source_path",
    ):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return None


def build_regenerated_variant(item: dict, *, title: object) -> dict:
    source_name = media_manifest_source_name(item)
    tags = parse_config_tags(source_name)
    return {
        "status": "published",
        "source_name": source_name,
        "canonical_source_name": canonical_source_name(source_name),
        "config_tags": tags,
        "config_hash": tags.get("hash"),
        "episode_key": media_manifest_episode_key(item),
        "audio_url": item.get("public_url") or item.get("audio_url"),
        "published_at": item.get("published_at") or item.get("createdTime") or item.get("modified_at"),
        "title": title,
        "local_audio_path": None,
        "staging_drive_id": None,
        "audio_sha256": item.get("sha256") or item.get("audio_sha256"),
        "generated_at": None,
        "uploaded_at": item.get("published_at") or item.get("uploaded_at"),
        "registered_at": utc_now(),
        "transcribed_at": None,
        "judged_at": None,
        "review_outcome": "queue_auto_activated",
        "size_bytes": item.get("size"),
        "drive_md5": None,
    }


def build_entry(episode: dict, campaign: str) -> dict:
    source_name = str(episode.get("source_name") or "").strip()
    prompt_type = classify_episode(source_name)
    return {
        "logical_episode_id": logical_episode_id(source_name),
        "prompt_type": prompt_type,
        "lecture_key": extract_lecture_key(source_name),
        "title": episode.get("title"),
        "canonical_source_name": canonical_source_name(source_name),
        "inventory_present": True,
        "active_variant": "A",
        "rollout": default_rollout(prompt_type, campaign),
        "variants": {
            "A": build_baseline_variant(episode),
            "B": default_variant("B"),
        },
    }


def merge_entry(existing: dict | None, episode: dict, campaign: str) -> dict:
    fresh = build_entry(episode, campaign)
    if not existing:
        return fresh

    merged = dict(existing)
    merged.update(
        {
            "logical_episode_id": fresh["logical_episode_id"],
            "prompt_type": fresh["prompt_type"],
            "lecture_key": fresh["lecture_key"],
            "title": fresh["title"],
            "canonical_source_name": fresh["canonical_source_name"],
            "inventory_present": True,
        }
    )
    merged["active_variant"] = merged.get("active_variant") if merged.get("active_variant") in {"A", "B"} else "A"

    rollout = dict(default_rollout(fresh["prompt_type"], campaign))
    existing_rollout = merged.get("rollout")
    if isinstance(existing_rollout, dict):
        rollout.update(existing_rollout)
        if fresh["prompt_type"] == "tts":
            rollout["in_scope"] = False
            rollout["campaign"] = None
            rollout["state"] = "out_of_scope"
        else:
            rollout["in_scope"] = True
            rollout["campaign"] = rollout.get("campaign") or campaign
    merged["rollout"] = rollout

    existing_variants = merged.get("variants")
    variants = {"A": default_variant("A"), "B": default_variant("B")}
    if isinstance(existing_variants, dict):
        for slot in ("A", "B"):
            if isinstance(existing_variants.get(slot), dict):
                variants[slot].update(existing_variants[slot])
    variants["A"].update(fresh["variants"]["A"])
    merged["variants"] = variants
    return merged


def summarize(entries: list[dict]) -> dict:
    prompt_type_counts: dict[str, int] = {}
    rollout_state_counts: dict[str, int] = {}
    active_variant_counts: dict[str, int] = {}
    in_scope = 0
    out_of_scope = 0
    for entry in entries:
        prompt_type = str(entry.get("prompt_type") or "unknown")
        prompt_type_counts[prompt_type] = prompt_type_counts.get(prompt_type, 0) + 1
        active = str(entry.get("active_variant") or "unknown")
        active_variant_counts[active] = active_variant_counts.get(active, 0) + 1
        rollout = entry.get("rollout") if isinstance(entry.get("rollout"), dict) else {}
        state = str(rollout.get("state") or "unknown")
        rollout_state_counts[state] = rollout_state_counts.get(state, 0) + 1
        if rollout.get("in_scope"):
            in_scope += 1
        else:
            out_of_scope += 1
    return {
        "total_entries": len(entries),
        "in_scope_entries": in_scope,
        "out_of_scope_entries": out_of_scope,
        "prompt_type_counts": dict(sorted(prompt_type_counts.items())),
        "rollout_state_counts": dict(sorted(rollout_state_counts.items())),
        "active_variant_counts": dict(sorted(active_variant_counts.items())),
    }


def should_preserve_stale_entry(entry: dict) -> bool:
    if str(entry.get("active_variant") or "") == "B":
        return True
    rollout = entry.get("rollout") if isinstance(entry.get("rollout"), dict) else {}
    state = str(rollout.get("state") or "")
    if state not in {"", "original_only", "out_of_scope"}:
        return True
    variants = entry.get("variants") if isinstance(entry.get("variants"), dict) else {}
    variant_b = variants.get("B") if isinstance(variants.get("B"), dict) else {}
    status = str(variant_b.get("status") or "")
    if status not in {"", "not_generated"}:
        return True
    for key in (
        "source_name",
        "local_audio_path",
        "staging_drive_id",
        "audio_sha256",
        "generated_at",
        "uploaded_at",
        "registered_at",
        "transcribed_at",
        "judged_at",
        "review_outcome",
        "size_bytes",
        "drive_md5",
        "history",
    ):
        if variant_b.get(key):
            return True
    return False


def _normalize_lecture_keys(values: Iterable[str] | None) -> set[str]:
    return {str(value or "").strip().upper() for value in (values or []) if str(value or "").strip()}


def _media_manifest_candidates(
    media_manifest_path: Path | None,
    activate_lecture_keys: set[str],
) -> dict[str, list[dict]]:
    if media_manifest_path is None or not activate_lecture_keys or not media_manifest_path.exists():
        return {}
    payload = read_json(media_manifest_path)
    items = payload.get("items")
    if not isinstance(items, list):
        return {}
    by_lid: dict[str, list[dict]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        artifact_type = str(item.get("artifact_type") or "audio").strip().lower()
        if artifact_type and artifact_type != "audio":
            continue
        source_name = media_manifest_source_name(item)
        if not source_name:
            continue
        lecture_key = extract_lecture_key(source_name).upper()
        if lecture_key not in activate_lecture_keys:
            continue
        lid = logical_episode_id(source_name)
        by_lid.setdefault(lid, []).append(item)
    return by_lid


def _candidate_matches_declared_variant(candidate: dict, variants: dict) -> bool:
    source_name = media_manifest_source_name(candidate)
    episode_key = media_manifest_episode_key(candidate)
    for slot in ("A", "B"):
        variant = variants.get(slot) if isinstance(variants.get(slot), dict) else {}
        if not variant:
            continue
        if source_name and source_name == str(variant.get("source_name") or "").strip():
            return True
        if episode_key and episode_key == str(variant.get("episode_key") or "").strip():
            return True
    return False


def _candidate_sort_key(candidate: dict) -> tuple[str, str, str]:
    return (
        str(candidate.get("published_at") or candidate.get("modified_at") or candidate.get("createdTime") or ""),
        media_manifest_source_name(candidate),
        media_manifest_episode_key(candidate) or "",
    )


def activate_regenerated_variants(
    entries: list[dict],
    *,
    media_manifest_path: Path | None,
    activate_lecture_keys: Iterable[str] | None,
    activation_campaign: str | None,
) -> None:
    normalized_lecture_keys = _normalize_lecture_keys(activate_lecture_keys)
    candidates_by_lid = _media_manifest_candidates(media_manifest_path, normalized_lecture_keys)
    if not candidates_by_lid:
        return

    activated_at = utc_now()
    for entry in entries:
        logical_id = str(entry.get("logical_episode_id") or "").strip()
        candidates = candidates_by_lid.get(logical_id) if logical_id else None
        if not candidates:
            continue
        variants = entry.get("variants") if isinstance(entry.get("variants"), dict) else {}
        if not isinstance(variants, dict):
            variants = {}
        new_candidates = [
            candidate for candidate in candidates if not _candidate_matches_declared_variant(candidate, variants)
        ]
        if not new_candidates:
            continue
        selected = sorted(new_candidates, key=_candidate_sort_key)[-1]
        existing_b = variants.get("B") if isinstance(variants.get("B"), dict) else {}
        updated_b = default_variant("B")
        updated_b.update(existing_b)
        history = updated_b.get("history")
        if not isinstance(history, list):
            history = []
        history = list(history)
        history.append(
            {
                "at": activated_at,
                "event": "queue_auto_activated",
                "source_name": media_manifest_source_name(selected),
                "episode_key": media_manifest_episode_key(selected),
                "campaign": activation_campaign,
            }
        )
        updated_b.update(build_regenerated_variant(selected, title=entry.get("title")))
        updated_b["history"] = history
        variants["B"] = updated_b
        if not isinstance(variants.get("A"), dict):
            variants["A"] = default_variant("A")
        entry["variants"] = variants
        entry["active_variant"] = "B"
        rollout = dict(default_rollout(str(entry.get("prompt_type") or "unknown"), activation_campaign or ""))
        existing_rollout = entry.get("rollout")
        if isinstance(existing_rollout, dict):
            rollout.update(existing_rollout)
        rollout["in_scope"] = str(entry.get("prompt_type") or "") != "tts"
        rollout["campaign"] = activation_campaign or rollout.get("campaign")
        rollout["state"] = "b_active" if rollout["in_scope"] else "out_of_scope"
        rollout["activated_at"] = activated_at if rollout["in_scope"] else None
        entry["rollout"] = rollout


def entry_sort_key(entry: dict) -> tuple:
    prompt_type = str(entry.get("prompt_type") or "unknown")
    lecture_key = str(entry.get("lecture_key") or "")
    logical_id = str(entry.get("logical_episode_id") or "")
    return (PROMPT_TYPE_ORDER.get(prompt_type, 99), lecture_key.casefold(), logical_id.casefold())


def sync_registry(
    inventory_path: Path,
    registry_path: Path,
    campaign: str,
    *,
    media_manifest_path: Path | None = None,
    activate_lecture_keys: Iterable[str] | None = None,
    activation_campaign: str | None = None,
) -> dict:
    inventory = read_json(inventory_path)
    existing = read_json(registry_path) if registry_path.exists() else {}
    existing_entries = existing.get("entries") if isinstance(existing, dict) else None
    existing_by_id = {
        str(entry.get("logical_episode_id")): entry
        for entry in (existing_entries or [])
        if isinstance(entry, dict) and entry.get("logical_episode_id")
    }

    synced_entries: list[dict] = []
    seen_ids: set[str] = set()
    for episode in inventory.get("episodes", []):
        if not isinstance(episode, dict):
            continue
        source_name = str(episode.get("source_name") or "").strip()
        if not source_name:
            continue
        lid = logical_episode_id(source_name)
        synced_entries.append(merge_entry(existing_by_id.get(lid), episode, campaign))
        seen_ids.add(lid)

    for lid, entry in existing_by_id.items():
        if lid in seen_ids:
            continue
        if not should_preserve_stale_entry(entry):
            continue
        stale = dict(entry)
        stale["inventory_present"] = False
        synced_entries.append(stale)

    activate_regenerated_variants(
        synced_entries,
        media_manifest_path=media_manifest_path,
        activate_lecture_keys=activate_lecture_keys,
        activation_campaign=activation_campaign or campaign,
    )
    synced_entries.sort(key=entry_sort_key)
    return {
        "schema_version": 1,
        "subject_slug": "personlighedspsykologi-en",
        "source_inventory_path": str(inventory_path),
        "generated_at": utc_now(),
        "campaign": campaign,
        "summary": summarize(synced_entries),
        "entries": synced_entries,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sync regeneration A/B registry from episode inventory.")
    parser.add_argument(
        "--inventory",
        default="shows/personlighedspsykologi-en/episode_inventory.json",
        help="Episode inventory JSON used as the baseline A source.",
    )
    parser.add_argument(
        "--registry",
        default="shows/personlighedspsykologi-en/regeneration_registry.json",
        help="Registry output path.",
    )
    parser.add_argument(
        "--campaign",
        default="prompt-rollout-2026-04",
        help="Default campaign assigned to in-scope entries.",
    )
    parser.add_argument(
        "--media-manifest",
        help="Optional media manifest used to auto-activate newly uploaded regenerated files.",
    )
    parser.add_argument(
        "--activate-lecture",
        action="append",
        default=[],
        help="Lecture key whose newly uploaded media-manifest items should become active regenerated variants.",
    )
    parser.add_argument(
        "--activation-campaign",
        help="Campaign recorded when auto-activating regenerated variants. Defaults to --campaign.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    inventory_path = (REPO_ROOT / args.inventory).resolve()
    registry_path = (REPO_ROOT / args.registry).resolve()
    media_manifest_path = (REPO_ROOT / args.media_manifest).resolve() if args.media_manifest else None
    payload = sync_registry(
        inventory_path,
        registry_path,
        args.campaign,
        media_manifest_path=media_manifest_path,
        activate_lecture_keys=args.activate_lecture,
        activation_campaign=args.activation_campaign,
    )
    write_json(registry_path, payload)
    summary = payload["summary"]
    print(f"Wrote {registry_path}")
    print(
        "entries={total_entries} in_scope={in_scope_entries} out_of_scope={out_of_scope_entries}".format(
            **summary
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
