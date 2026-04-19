#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

CONFIG_TAG_RE = re.compile(r"\s+\{[^{}]+\}(?=\.[^.]+$)")
SHORT_PREFIX_RE = re.compile(r"^\[(?:Short|Brief)\]\s+", re.IGNORECASE)
TTS_PREFIX_RE = re.compile(r"^\[TTS\]\s+", re.IGNORECASE)
WEEK_KEY_RE = re.compile(r"\bW\d+L\d+\b", re.IGNORECASE)
TAG_TOKEN_RE = re.compile(r"([a-z0-9_]+)=([^}\s]+)", re.IGNORECASE)

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


def strip_cfg_tag_from_filename(name: str) -> str:
    value = CONFIG_TAG_RE.sub("", name)
    return Path(value).name


def strip_leading_variant_prefix(name: str) -> str:
    value = SHORT_PREFIX_RE.sub("", name.strip())
    value = TTS_PREFIX_RE.sub("", value)
    return value.strip()


def parse_config_tags(name: str) -> dict[str, str]:
    match = re.search(r"\{([^{}]+)\}(?=\.[^.]+$)", name)
    if not match:
        return {}
    parsed: dict[str, str] = {}
    for key, value in TAG_TOKEN_RE.findall(match.group(1)):
        parsed[key] = value
    return parsed


def classify_episode(source_name: str) -> str:
    value = source_name.strip()
    if not value:
        return "unknown"
    if TTS_PREFIX_RE.match(value):
        return "tts"
    if SHORT_PREFIX_RE.match(value):
        return "short"
    if "Alle kilder (undtagen slides)" in value:
        return "weekly_readings_only"
    if "Slide lecture:" in value or "Slide exercise:" in value:
        return "single_slide"
    return "single_reading"


def extract_lecture_key(text: str) -> str | None:
    match = WEEK_KEY_RE.search(text)
    return match.group(0).upper() if match else None


def slugify(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", text.lower())
    return value.strip("_") or "sample"


def canonical_source_name(source_name: str) -> str:
    return strip_cfg_tag_from_filename(source_name).strip()


def logical_episode_id(source_name: str) -> str:
    prompt_type = classify_episode(source_name)
    lecture_key = (extract_lecture_key(source_name) or "unknown").lower()
    canonical = canonical_source_name(source_name)
    trimmed = strip_leading_variant_prefix(canonical)
    trimmed = trimmed.replace(".mp3", "")
    trimmed = re.sub(r"^w\d+l\d+\s*-\s*", "", trimmed, flags=re.IGNORECASE)
    trimmed = re.sub(r"^slide\s+(lecture|exercise):\s*", "", trimmed, flags=re.IGNORECASE)
    trimmed = re.sub(r"^alle kilder \(undtagen slides\)$", "alle_kilder_undtagen_slides", trimmed, flags=re.IGNORECASE)
    return f"{prompt_type}__{lecture_key}__{slugify(trimmed)}"


def default_rollout(prompt_type: str, campaign: str) -> dict:
    in_scope = prompt_type != "tts"
    return {
        "campaign": campaign if in_scope else None,
        "in_scope": in_scope,
        "state": "original_only" if in_scope else "out_of_scope",
        "notes": [],
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
        "transcribed_at": None,
        "judged_at": None,
        "review_outcome": None,
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
    for key in ("source_name", "local_audio_path", "staging_drive_id", "audio_sha256", "generated_at", "uploaded_at", "transcribed_at", "judged_at", "review_outcome"):
        if variant_b.get(key):
            return True
    return False


def entry_sort_key(entry: dict) -> tuple:
    prompt_type = str(entry.get("prompt_type") or "unknown")
    lecture_key = str(entry.get("lecture_key") or "")
    logical_id = str(entry.get("logical_episode_id") or "")
    return (PROMPT_TYPE_ORDER.get(prompt_type, 99), lecture_key.casefold(), logical_id.casefold())


def sync_registry(inventory_path: Path, registry_path: Path, campaign: str) -> dict:
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
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = Path(__file__).resolve().parents[3]
    inventory_path = (root / args.inventory).resolve()
    registry_path = (root / args.registry).resolve()
    payload = sync_registry(inventory_path, registry_path, args.campaign)
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
