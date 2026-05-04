from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "validate_regeneration_inventory.py"
SPEC = importlib.util.spec_from_file_location("validate_regeneration_inventory", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_episode_key_matches_drive_requires_exact_candidate() -> None:
    episode = {
        "source_drive_file_id": "drive-file-id",
        "episode_key": "drive-file-id",
    }
    assert MODULE.episode_key_matches(
        "drive-file-id",
        episode,
        inventory_storage_provider="drive",
        show_slug="personlighedspsykologi-en",
    )
    assert not MODULE.episode_key_matches(
        "different-drive-id",
        episode,
        inventory_storage_provider="drive",
        show_slug="personlighedspsykologi-en",
    )


def test_episode_key_matches_accepts_repo_relative_r2_storage_keys() -> None:
    episode = {
        "source_storage_key": (
            "shows/personlighedspsykologi-en/W01L1/"
            "W01L1 - Example [EN] {type=audio lang=en format=deep-dive length=long}.mp3"
        ),
        "episode_key": (
            "shows/personlighedspsykologi-en/W01L1/"
            "W01L1 - Example [EN] {type=audio lang=en format=deep-dive length=long}.mp3"
        ),
    }
    assert MODULE.episode_key_matches(
        "legacy-drive-id",
        episode,
        inventory_storage_provider="r2",
        show_slug="personlighedspsykologi-en",
    )


def test_episode_key_matches_non_drive_still_rejects_non_repo_relative_keys() -> None:
    episode = {
        "source_storage_key": "some-other-key",
        "episode_key": "some-other-key",
    }
    assert not MODULE.episode_key_matches(
        "legacy-drive-id",
        episode,
        inventory_storage_provider="r2",
        show_slug="personlighedspsykologi-en",
    )
