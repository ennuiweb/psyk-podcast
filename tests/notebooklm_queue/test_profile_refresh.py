from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path

from notebooklm_queue.profile_capacity import inspect_profile_capacity
from notebooklm_queue.profile_refresh import ProfileRefreshOptions, refresh_profiles
from notebooklm_queue.store import QueueStore


def _write_profiles_file(tmp_path: Path, profiles: dict[str, Path]) -> Path:
    path = tmp_path / "profiles.host.json"
    path.write_text(
        json.dumps({"profiles": {name: str(storage) for name, storage in profiles.items()}}),
        encoding="utf-8",
    )
    return path


async def _successful_refresher(_name: str, storage_path: Path) -> None:
    storage_path.write_text(storage_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")


async def _auth_failure_refresher(_name: str, _storage_path: Path) -> None:
    raise ValueError("Authentication expired or invalid. Run 'notebooklm login'.")


async def _transient_failure_refresher(_name: str, _storage_path: Path) -> None:
    raise RuntimeError("temporary network failure")


def test_refresh_profiles_repairs_auth_stale_profile_state(tmp_path: Path) -> None:
    now = datetime(2026, 5, 23, 12, tzinfo=UTC)
    storage = tmp_path / "default.json"
    storage.write_text("{}", encoding="utf-8")
    last_used = (now - timedelta(minutes=10)).timestamp()
    os.utime(storage, (last_used - 60, last_used - 60))
    profiles_file = _write_profiles_file(tmp_path, {"default": storage})
    state_file = tmp_path / "profile_state.json"
    state_file.write_text(
        json.dumps(
            {
                "profiles": {
                    "default": {
                        "last_used": last_used,
                        "last_error": "auth",
                        "cooldown_until": (now + timedelta(hours=1)).timestamp(),
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    before = inspect_profile_capacity(
        profiles_file=profiles_file,
        profile_state_file=state_file,
        now=now,
    )
    assert before["profiles"][0]["status"] == "auth_stale"

    result = refresh_profiles(
        store=QueueStore(tmp_path / "queue"),
        options=ProfileRefreshOptions(
            profiles_file=profiles_file,
            profile_state_file=state_file,
            force=True,
            use_lock=False,
        ),
        refresher=_successful_refresher,
        now=now,
    )

    assert result["status"] == "ok"
    assert result["summary"] == {"refreshed": 1}
    assert Path(result["report_path"]).exists()
    latest_report = tmp_path / "queue" / "profile-refresh" / "latest.json"
    assert latest_report.exists()
    state = json.loads(state_file.read_text(encoding="utf-8"))
    entry = state["profiles"]["default"]
    assert entry["last_error"] is None
    assert entry["cooldown_until"] == 0
    assert entry["last_refresh_status"] == "success"

    after = inspect_profile_capacity(
        profiles_file=profiles_file,
        profile_state_file=state_file,
        now=now,
    )
    assert after["profiles"][0]["status"] == "usable"


def test_refresh_profiles_can_reclaim_after_auth_recovery(tmp_path: Path, monkeypatch) -> None:
    now = datetime(2026, 5, 23, 12, tzinfo=UTC)
    storage = tmp_path / "default.json"
    storage.write_text("{}", encoding="utf-8")
    profiles_file = _write_profiles_file(tmp_path, {"default": storage})
    state_file = tmp_path / "profile_state.json"
    state_file.write_text(
        json.dumps(
            {
                "profiles": {
                    "default": {
                        "last_used": (now - timedelta(minutes=10)).timestamp(),
                        "last_error": "auth",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    reclaim_calls = []

    def fake_reclaim_notebooks(*, store, options, **_kwargs):
        reclaim_calls.append((store, options))
        return {
            "status": "ok",
            "summary": {"dry_run": 1},
            "profiles": [{"name": "default", "status": "dry_run"}],
        }

    monkeypatch.setattr(
        "notebooklm_queue.notebook_reclaim.reclaim_notebooks",
        fake_reclaim_notebooks,
    )

    result = refresh_profiles(
        store=QueueStore(tmp_path / "queue"),
        options=ProfileRefreshOptions(
            profiles_file=profiles_file,
            profile_state_file=state_file,
            force=True,
            use_lock=False,
            reclaim_on_auth_recovery=True,
            reclaim_target_free_slots=17,
            reclaim_max_deletions=9,
        ),
        refresher=_successful_refresher,
        now=now,
    )

    assert result["status"] == "ok"
    assert result["profiles"][0]["recovered_from_error"] == "auth"
    assert result["reclaim_reports"][0]["summary"] == {"dry_run": 1}
    assert len(reclaim_calls) == 1
    _, options = reclaim_calls[0]
    assert options.profiles == ("default",)
    assert options.target_free_slots == 17
    assert options.max_deletions == 9
    assert options.dry_run is True
    assert options.use_lock is False
    assert options.actor == "operator:auth-recovery"


def test_refresh_profiles_can_reclaim_after_cooldown_recovery(tmp_path: Path, monkeypatch) -> None:
    now = datetime(2026, 5, 23, 12, tzinfo=UTC)
    storage = tmp_path / "limited.json"
    storage.write_text("{}", encoding="utf-8")
    profiles_file = _write_profiles_file(tmp_path, {"limited": storage})
    state_file = tmp_path / "profile_state.json"
    state_file.write_text(
        json.dumps(
            {
                "profiles": {
                    "limited": {
                        "last_error": "rate_limit",
                        "cooldown_until": (now - timedelta(minutes=1)).timestamp(),
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    reclaim_calls = []

    def fake_reclaim_notebooks(*, store, options, **_kwargs):
        reclaim_calls.append((store, options))
        return {
            "status": "ok",
            "summary": {"dry_run": 1},
            "profiles": [{"name": "limited", "status": "dry_run"}],
        }

    monkeypatch.setattr(
        "notebooklm_queue.notebook_reclaim.reclaim_notebooks",
        fake_reclaim_notebooks,
    )

    result = refresh_profiles(
        store=QueueStore(tmp_path / "queue"),
        options=ProfileRefreshOptions(
            profiles_file=profiles_file,
            profile_state_file=state_file,
            force=True,
            use_lock=False,
            reclaim_on_recovery=True,
        ),
        refresher=_successful_refresher,
        now=now,
    )

    assert result["status"] == "ok"
    assert result["profiles"][0]["recovered_from_error"] == "rate_limit"
    assert result["profiles"][0]["recovered_from_cooldown"] is True
    assert result["reclaim_reports"][0]["summary"] == {"dry_run": 1}
    assert len(reclaim_calls) == 1
    _, options = reclaim_calls[0]
    assert options.profiles == ("limited",)
    assert options.actor == "operator:profile-recovery"
    assert options.use_lock is False


def test_refresh_profiles_auth_recovery_flag_does_not_reclaim_cooldown_recovery(
    tmp_path: Path,
    monkeypatch,
) -> None:
    now = datetime(2026, 5, 23, 12, tzinfo=UTC)
    storage = tmp_path / "limited.json"
    storage.write_text("{}", encoding="utf-8")
    profiles_file = _write_profiles_file(tmp_path, {"limited": storage})
    state_file = tmp_path / "profile_state.json"
    state_file.write_text(
        json.dumps(
            {
                "profiles": {
                    "limited": {
                        "last_error": "rate_limit",
                        "cooldown_until": (now - timedelta(minutes=1)).timestamp(),
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    reclaim_calls = []

    def fake_reclaim_notebooks(*, store, options, **_kwargs):
        reclaim_calls.append((store, options))
        return {"status": "ok", "summary": {"dry_run": 1}, "profiles": []}

    monkeypatch.setattr(
        "notebooklm_queue.notebook_reclaim.reclaim_notebooks",
        fake_reclaim_notebooks,
    )

    result = refresh_profiles(
        store=QueueStore(tmp_path / "queue"),
        options=ProfileRefreshOptions(
            profiles_file=profiles_file,
            profile_state_file=state_file,
            force=True,
            use_lock=False,
            reclaim_on_auth_recovery=True,
        ),
        refresher=_successful_refresher,
        now=now,
    )

    assert result["status"] == "ok"
    assert result["profiles"][0]["recovered_from_cooldown"] is True
    assert "reclaim_reports" not in result
    assert reclaim_calls == []


def test_refresh_profiles_preserves_rate_limit_cooldown(tmp_path: Path) -> None:
    now = datetime(2026, 5, 23, 12, tzinfo=UTC)
    storage = tmp_path / "limited.json"
    storage.write_text("{}", encoding="utf-8")
    profiles_file = _write_profiles_file(tmp_path, {"limited": storage})
    state_file = tmp_path / "profile_state.json"
    cooldown_until = (now + timedelta(minutes=20)).timestamp()
    state_file.write_text(
        json.dumps(
            {
                "profiles": {
                    "limited": {
                        "last_error": "rate_limit",
                        "cooldown_until": cooldown_until,
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    result = refresh_profiles(
        store=QueueStore(tmp_path / "queue"),
        options=ProfileRefreshOptions(
            profiles_file=profiles_file,
            profile_state_file=state_file,
            force=True,
            use_lock=False,
        ),
        refresher=_successful_refresher,
        now=now,
    )

    assert result["summary"] == {"refreshed": 1}
    state = json.loads(state_file.read_text(encoding="utf-8"))
    entry = state["profiles"]["limited"]
    assert entry["last_error"] == "rate_limit"
    assert entry["cooldown_until"] == cooldown_until


def test_refresh_profiles_marks_auth_failure_stale(tmp_path: Path) -> None:
    now = datetime(2026, 5, 23, 12, tzinfo=UTC)
    storage = tmp_path / "default.json"
    storage.write_text("{}", encoding="utf-8")
    profiles_file = _write_profiles_file(tmp_path, {"default": storage})
    state_file = tmp_path / "profile_state.json"

    result = refresh_profiles(
        store=QueueStore(tmp_path / "queue"),
        options=ProfileRefreshOptions(
            profiles_file=profiles_file,
            profile_state_file=state_file,
            use_lock=False,
        ),
        refresher=_auth_failure_refresher,
        now=now,
    )

    assert result["status"] == "failed"
    assert result["profiles"][0]["error_type"] == "auth"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    entry = state["profiles"]["default"]
    assert entry["last_error"] == "auth"
    assert entry["last_refresh_status"] == "failed"


def test_refresh_profiles_does_not_turn_transient_failure_into_auth_stale(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 5, 23, 12, tzinfo=UTC)
    storage = tmp_path / "default.json"
    storage.write_text("{}", encoding="utf-8")
    profiles_file = _write_profiles_file(tmp_path, {"default": storage})
    state_file = tmp_path / "profile_state.json"
    state_file.write_text(json.dumps({"profiles": {"default": {}}}), encoding="utf-8")

    result = refresh_profiles(
        store=QueueStore(tmp_path / "queue"),
        options=ProfileRefreshOptions(
            profiles_file=profiles_file,
            profile_state_file=state_file,
            use_lock=False,
        ),
        refresher=_transient_failure_refresher,
        now=now,
    )

    assert result["status"] == "failed"
    assert result["profiles"][0]["error_type"] == "transient"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    entry = state["profiles"]["default"]
    assert entry.get("last_error") is None
    assert entry["last_refresh_status"] == "failed"


def test_refresh_profiles_respects_capacity_lock(tmp_path: Path) -> None:
    store = QueueStore(tmp_path / "queue")
    profiles_file = _write_profiles_file(tmp_path, {"default": tmp_path / "default.json"})

    with store.acquire_global_lock("notebooklm-capacity"):
        result = refresh_profiles(
            store=store,
            options=ProfileRefreshOptions(profiles_file=profiles_file),
            refresher=_successful_refresher,
            now=datetime(2026, 5, 23, 12, tzinfo=UTC),
        )

    assert result["status"] == "lock_held"
    assert result["summary"] == {"lock_held": 1}
