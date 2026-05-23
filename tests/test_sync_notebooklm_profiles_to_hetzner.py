from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "sync_notebooklm_profiles_to_hetzner.py"
SPEC = importlib.util.spec_from_file_location("sync_notebooklm_profiles_to_hetzner", MODULE_PATH)
sync_profiles = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(sync_profiles)


def test_single_profile_sync_bundle_keeps_every_configured_profile() -> None:
    profiles = {
        "default": Path("/tmp/default.json"),
        "freudagsbaren": Path("/tmp/freudagsbaren.json"),
        "nopeeeh": Path("/tmp/nopeeeh.json"),
    }

    selected = sync_profiles.selected_profile_names(profiles, ["nopeeeh"])
    bundle = sync_profiles.build_remote_bundle(sorted(profiles), "/etc/podcasts/notebooklm-queue/profiles")

    assert selected == ["nopeeeh"]
    assert bundle == {
        "default": "/etc/podcasts/notebooklm-queue/profiles/default.json",
        "freudagsbaren": "/etc/podcasts/notebooklm-queue/profiles/freudagsbaren.json",
        "nopeeeh": "/etc/podcasts/notebooklm-queue/profiles/nopeeeh.json",
    }


def test_bundle_only_sync_uploads_no_storage_by_default() -> None:
    profiles = {
        "default": Path("/tmp/default.json"),
        "nopeeeh": Path("/tmp/nopeeeh.json"),
    }

    assert sync_profiles.selected_profile_names(profiles, []) == []


def test_upload_all_selects_every_configured_profile() -> None:
    profiles = {
        "default": Path("/tmp/default.json"),
        "nopeeeh": Path("/tmp/nopeeeh.json"),
    }

    assert sync_profiles.selected_profile_names(profiles, [], upload_all=True) == [
        "default",
        "nopeeeh",
    ]
