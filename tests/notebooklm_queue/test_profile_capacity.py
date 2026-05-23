from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path

from notebooklm_queue.profile_capacity import inspect_profile_capacity, summarize_profile_capacity


def test_inspect_profile_capacity_is_permissive_without_profiles_file(monkeypatch) -> None:
    monkeypatch.delenv("NOTEBOOKLM_PROFILES_FILE", raising=False)

    capacity = inspect_profile_capacity(now=datetime(2026, 5, 20, 12, tzinfo=UTC))

    assert capacity["configured"] is False
    assert capacity["has_capacity"] is True
    assert capacity["reason"] == "profiles_file_not_configured"


def test_inspect_profile_capacity_classifies_active_profiles(tmp_path: Path) -> None:
    now = datetime(2026, 5, 20, 12, tzinfo=UTC)
    default_storage = tmp_path / "default.json"
    cooled_storage = tmp_path / "cooled.json"
    stale_storage = tmp_path / "stale.json"
    refreshed_storage = tmp_path / "refreshed.json"
    for path in (default_storage, cooled_storage, stale_storage, refreshed_storage):
        path.write_text("{}", encoding="utf-8")

    last_used = now.timestamp() - 300
    os.utime(stale_storage, (last_used - 60, last_used - 60))
    os.utime(refreshed_storage, (last_used + 60, last_used + 60))

    profiles_file = tmp_path / "profiles.host.json"
    profiles_file.write_text(
        json.dumps(
            {
                "profiles": {
                    "default": str(default_storage),
                    "cooled": str(cooled_storage),
                    "missing": str(tmp_path / "missing.json"),
                    "stale": str(stale_storage),
                    "refreshed": str(refreshed_storage),
                }
            }
        ),
        encoding="utf-8",
    )
    state_file = tmp_path / "profile_state.json"
    state_file.write_text(
        json.dumps(
            {
                "profiles": {
                    "cooled": {
                        "cooldown_until": (now + timedelta(minutes=5)).timestamp(),
                        "last_error": "rate_limit",
                    },
                    "stale": {
                        "last_used": last_used,
                        "last_error": "auth",
                    },
                    "refreshed": {
                        "last_used": last_used,
                        "last_error": "auth",
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    capacity = inspect_profile_capacity(
        profiles_file=profiles_file,
        profile_priority="cooled,default,unknown",
        profile_state_file=state_file,
        now=now,
    )
    statuses = {profile["name"]: profile["status"] for profile in capacity["profiles"]}

    assert capacity["has_capacity"] is True
    assert capacity["usable_profiles"] == ["default", "refreshed"]
    assert set(capacity["blocked_profiles"]) == {"cooled", "missing", "stale"}
    assert capacity["unknown_priority_profiles"] == ["unknown"]
    assert statuses["cooled"] == "cooldown"
    assert statuses["missing"] == "missing_storage"
    assert statuses["stale"] == "auth_stale"
    assert statuses["refreshed"] == "usable"

    summary = summarize_profile_capacity(capacity)
    assert summary["status_counts"] == {
        "auth_stale": 1,
        "cooldown": 1,
        "missing_storage": 1,
        "usable": 2,
    }


def test_inspect_profile_capacity_reports_next_available_when_all_profiles_cooled(tmp_path: Path) -> None:
    now = datetime(2026, 5, 20, 12, tzinfo=UTC)
    storage = tmp_path / "default.json"
    storage.write_text("{}", encoding="utf-8")
    profiles_file = tmp_path / "profiles.host.json"
    profiles_file.write_text(json.dumps({"profiles": {"default": str(storage)}}), encoding="utf-8")
    state_file = tmp_path / "profile_state.json"
    state_file.write_text(
        json.dumps(
            {
                "profiles": {
                    "default": {
                        "cooldown_until": (now + timedelta(seconds=90)).timestamp(),
                        "last_error": "rate_limit",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    capacity = inspect_profile_capacity(
        profiles_file=profiles_file,
        profile_state_file=state_file,
        now=now,
    )

    assert capacity["has_capacity"] is False
    assert capacity["manual_intervention_required"] is False
    assert capacity["wait_seconds"] == 90
    assert capacity["next_available_at"] == "2026-05-20T12:01:30+00:00"


def test_inspect_profile_capacity_reports_auth_stale_before_auth_cooldown(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 5, 20, 12, tzinfo=UTC)
    storage = tmp_path / "default.json"
    storage.write_text("{}", encoding="utf-8")
    last_used = now.timestamp() - 60
    os.utime(storage, (last_used - 30, last_used - 30))
    profiles_file = tmp_path / "profiles.host.json"
    profiles_file.write_text(json.dumps({"profiles": {"default": str(storage)}}), encoding="utf-8")
    state_file = tmp_path / "profile_state.json"
    state_file.write_text(
        json.dumps(
            {
                "profiles": {
                    "default": {
                        "cooldown_until": (now + timedelta(hours=1)).timestamp(),
                        "last_error": "auth",
                        "last_used": last_used,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    capacity = inspect_profile_capacity(
        profiles_file=profiles_file,
        profile_state_file=state_file,
        now=now,
    )

    assert capacity["has_capacity"] is False
    assert capacity["manual_intervention_required"] is True
    assert capacity["next_available_at"] is None
    assert capacity["profiles"][0]["status"] == "auth_stale"


def test_failed_auth_refresh_keeps_profile_stale_even_after_storage_sync(tmp_path: Path) -> None:
    now = datetime(2026, 5, 20, 12, tzinfo=UTC)
    storage = tmp_path / "default.json"
    storage.write_text("{}", encoding="utf-8")
    last_used = now.timestamp() - 600
    os.utime(storage, (now.timestamp(), now.timestamp()))
    profiles_file = tmp_path / "profiles.host.json"
    profiles_file.write_text(json.dumps({"profiles": {"default": str(storage)}}), encoding="utf-8")
    state_file = tmp_path / "profile_state.json"
    state_file.write_text(
        json.dumps(
            {
                "profiles": {
                    "default": {
                        "last_error": "auth",
                        "last_refresh_error_type": "auth",
                        "last_refresh_status": "failed",
                        "last_used": last_used,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    capacity = inspect_profile_capacity(
        profiles_file=profiles_file,
        profile_state_file=state_file,
        now=now,
    )

    assert capacity["has_capacity"] is False
    assert capacity["manual_intervention_required"] is True
    assert capacity["profiles"][0]["status"] == "auth_stale"
    assert capacity["profiles"][0]["reason"] == "last_refresh_failed_auth"
