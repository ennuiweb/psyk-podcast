#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from regeneration_identity import logical_episode_id  # noqa: E402


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def storage_key_candidates(episode: dict) -> list[str]:
    candidates: list[str] = []
    for value in (
        episode.get("source_drive_file_id"),
        episode.get("source_storage_key"),
        episode.get("episode_key"),
    ):
        text = str(value or "").strip()
        if text and text not in candidates:
            candidates.append(text)
    return candidates


def _is_repo_relative_storage_key(value: str, show_slug: str) -> bool:
    normalized_show_slug = show_slug.strip().strip("/")
    prefix = f"shows/{normalized_show_slug}/"
    return value.startswith(prefix) and value.endswith(".mp3")


def episode_key_matches(
    expected_episode_key: str,
    episode: dict,
    *,
    inventory_storage_provider: str,
    show_slug: str,
) -> bool:
    expected = str(expected_episode_key or "").strip()
    if not expected:
        return True

    candidates = storage_key_candidates(episode)
    if expected in candidates:
        return True

    provider = str(inventory_storage_provider or "").strip().lower()
    if provider and provider != "drive":
        # During R2-backed publication we still validate logical/source identity,
        # but the concrete storage key may legitimately migrate from legacy Drive
        # ids to repo-relative object keys.
        return any(_is_repo_relative_storage_key(candidate, show_slug) for candidate in candidates)

    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate that episode_inventory matches regeneration_registry active variants."
    )
    parser.add_argument(
        "--show-slug",
        default="personlighedspsykologi-en",
        help="Show slug under shows/<show-slug>/.",
    )
    parser.add_argument(
        "--registry",
        help="Optional explicit registry path. Defaults to shows/<show-slug>/regeneration_registry.json.",
    )
    parser.add_argument(
        "--inventory",
        help="Optional explicit inventory path. Defaults to shows/<show-slug>/episode_inventory.json.",
    )
    parser.add_argument(
        "--weeks",
        help="Optional comma-separated lecture keys to validate, e.g. W11L1,W11L2.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    show_dir = REPO_ROOT / "shows" / args.show_slug
    registry_path = Path(args.registry).resolve() if args.registry else show_dir / "regeneration_registry.json"
    inventory_path = Path(args.inventory).resolve() if args.inventory else show_dir / "episode_inventory.json"
    weeks = {
        week.strip().upper()
        for week in str(args.weeks or "").split(",")
        if week.strip()
    }

    registry = read_json(registry_path)
    inventory = read_json(inventory_path)
    inventory_storage_provider = str(inventory.get("storage_provider") or "").strip().lower()

    inventory_by_lid: dict[str, list[dict]] = {}
    for episode in inventory.get("episodes", []):
        if not isinstance(episode, dict):
            continue
        source_name = str(episode.get("source_name") or "").strip()
        if not source_name:
            continue
        logical_id = logical_episode_id(source_name)
        inventory_by_lid.setdefault(logical_id, []).append(episode)

    errors: list[str] = []
    checked = 0
    migrated_storage_keys = 0
    for entry in registry.get("entries", []):
        if not isinstance(entry, dict):
            continue
        lecture_key = str(entry.get("lecture_key") or "").strip().upper()
        if weeks and lecture_key not in weeks:
            continue
        logical_id = str(entry.get("logical_episode_id") or "").strip()
        if not logical_id:
            continue
        variants = entry.get("variants") if isinstance(entry.get("variants"), dict) else {}
        active_slot = str(entry.get("active_variant") or "A").strip().upper()
        if active_slot not in {"A", "B"}:
            active_slot = "A"
        active_variant = variants.get(active_slot) if isinstance(variants.get(active_slot), dict) else {}
        expected_source_name = str(active_variant.get("source_name") or "").strip()
        expected_episode_key = str(active_variant.get("episode_key") or "").strip()
        matches = inventory_by_lid.get(logical_id, [])
        if not matches:
            errors.append(f"{logical_id}: missing from inventory")
            continue
        if len(matches) != 1:
            errors.append(
                f"{logical_id}: expected exactly 1 inventory episode, found {len(matches)}"
            )
            continue
        checked += 1
        episode = matches[0]
        actual_source_name = str(episode.get("source_name") or "").strip()
        if expected_source_name and actual_source_name != expected_source_name:
            errors.append(
                f"{logical_id}: expected source_name {expected_source_name!r}, got {actual_source_name!r}"
            )
        if expected_episode_key and not episode_key_matches(
            expected_episode_key,
            episode,
            inventory_storage_provider=inventory_storage_provider,
            show_slug=args.show_slug,
        ):
            actual_episode_key = ", ".join(storage_key_candidates(episode)) or "<missing>"
            errors.append(
                f"{logical_id}: expected episode_key {expected_episode_key!r}, got {actual_episode_key!r}"
            )
        elif (
            expected_episode_key
            and inventory_storage_provider
            and inventory_storage_provider != "drive"
            and expected_episode_key not in storage_key_candidates(episode)
        ):
            migrated_storage_keys += 1

    if errors:
        print("Regeneration inventory validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    scope = f" weeks={sorted(weeks)}" if weeks else ""
    migration_note = f" migrated_storage_keys={migrated_storage_keys}" if migrated_storage_keys else ""
    print(f"Validated regeneration inventory: entries={checked}{scope}{migration_note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
