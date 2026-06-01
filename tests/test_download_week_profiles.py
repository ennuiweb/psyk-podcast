from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "notebooklm-podcast-auto"
    / "personlighedspsykologi"
    / "scripts"
    / "download_week.py"
)
SPEC = importlib.util.spec_from_file_location("personlighedspsykologi_download_week", MODULE_PATH)
download_week = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(download_week)


def test_collect_storage_candidates_prefers_request_log_owner_current_profile(
    tmp_path: Path, monkeypatch
) -> None:
    owner_current_storage = tmp_path / "owner-current.json"
    fallback_storage = tmp_path / "fallback.json"
    owner_old_storage = tmp_path / "owner-old.json"
    for path in (owner_current_storage, fallback_storage, owner_old_storage):
        path.write_text("{}", encoding="utf-8")
    profiles_file = tmp_path / "profiles.host.json"
    profiles_file.write_text(
        json.dumps(
            {
                "profiles": {
                    "owner": str(owner_current_storage),
                    "fallback": str(fallback_storage),
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NOTEBOOKLM_PROFILES_FILE", str(profiles_file))
    monkeypatch.setenv("NOTEBOOKLM_PROFILE_STATE_FILE", str(tmp_path / "profile_state.json"))

    candidates = download_week.collect_storage_candidates(
        tmp_path,
        storage=None,
        profile=None,
        profiles_file=None,
        profile_priority="fallback,owner",
        log_auth={
            "profile": "owner",
            "profiles_file": str(profiles_file),
            "storage_path": str(owner_old_storage),
        },
    )

    assert candidates[:3] == [
        (str(owner_current_storage.resolve()), "log-profile:owner"),
        (str(owner_old_storage), "log:storage"),
        (str(fallback_storage.resolve()), "profiles:fallback"),
    ]


def test_collect_storage_candidates_skips_auth_stale_profile_state(
    tmp_path: Path, monkeypatch
) -> None:
    stale_storage = tmp_path / "stale.json"
    fresh_storage = tmp_path / "fresh.json"
    stale_storage.write_text("{}", encoding="utf-8")
    fresh_storage.write_text("{}", encoding="utf-8")
    last_used = 1_800_000_000
    profiles_file = tmp_path / "profiles.host.json"
    profiles_file.write_text(
        json.dumps(
            {
                "profiles": {
                    "stale": str(stale_storage),
                    "fresh": str(fresh_storage),
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
                    "stale": {
                        "last_error": "auth",
                        "last_used": last_used,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NOTEBOOKLM_PROFILES_FILE", str(profiles_file))
    monkeypatch.setenv("NOTEBOOKLM_PROFILE_STATE_FILE", str(state_file))
    os_mtime = last_used - 60
    os.utime(stale_storage, (os_mtime, os_mtime))

    candidates = download_week.collect_storage_candidates(
        tmp_path,
        storage=None,
        profile=None,
        profiles_file=None,
        profile_priority="stale,fresh",
        log_auth=None,
    )

    assert candidates == [(str(fresh_storage.resolve()), "profiles:fresh")]


def test_collect_storage_candidates_keeps_cli_profile_override_first(
    tmp_path: Path, monkeypatch
) -> None:
    owner_storage = tmp_path / "owner.json"
    cli_storage = tmp_path / "cli.json"
    fallback_storage = tmp_path / "fallback.json"
    for path in (owner_storage, cli_storage, fallback_storage):
        path.write_text("{}", encoding="utf-8")
    profiles_file = tmp_path / "profiles.host.json"
    profiles_file.write_text(
        json.dumps(
            {
                "profiles": {
                    "owner": str(owner_storage),
                    "cli": str(cli_storage),
                    "fallback": str(fallback_storage),
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NOTEBOOKLM_PROFILES_FILE", str(profiles_file))
    monkeypatch.setenv("NOTEBOOKLM_PROFILE_STATE_FILE", str(tmp_path / "profile_state.json"))

    candidates = download_week.collect_storage_candidates(
        tmp_path,
        storage=None,
        profile="cli",
        profiles_file=None,
        profile_priority="fallback",
        log_auth={
            "profile": "owner",
            "profiles_file": str(profiles_file),
            "storage_path": str(owner_storage),
        },
    )

    assert candidates[0] == (str(cli_storage.resolve()), "cli:profile")


def test_fetch_artifact_status_classifies_account_routing_as_auth(monkeypatch, tmp_path: Path) -> None:
    def fake_run_cmd(command: list[str]) -> tuple[bool, str]:
        return (
            False,
            "RPC rLM1Ne returned null result with status code 7 "
            "(Permission denied). account-routing mismatch; set authuser.",
        )

    monkeypatch.setattr(download_week, "run_cmd", fake_run_cmd)

    ok, status, reason = download_week.fetch_artifact_status(
        tmp_path / "notebooklm",
        str(tmp_path / "default.json"),
        "notebook-id",
        "artifact-id",
    )

    assert ok is False
    assert status is None
    assert reason == "auth"


def test_wait_and_download_rotates_on_wait_auth_failure(monkeypatch, tmp_path: Path) -> None:
    def fake_run_cmd(command: list[str]) -> tuple[bool, str]:
        assert command[:2] == [str(tmp_path / "notebooklm"), "--storage"]
        return False, "Permission denied: account-routing mismatch"

    monkeypatch.setattr(download_week, "run_cmd", fake_run_cmd)

    ok, reason = download_week.wait_and_download(
        tmp_path / "notebooklm",
        "artifact-id",
        "notebook-id",
        "audio",
        tmp_path / "episode.mp3",
        60,
        60,
        str(tmp_path / "wrong-profile.json"),
        None,
    )

    assert ok is False
    assert reason == "auth"


def test_wait_and_download_keeps_real_wait_timeout_as_wait(monkeypatch, tmp_path: Path) -> None:
    def fake_run_cmd(command: list[str]) -> tuple[bool, str]:
        return False, "Timeout after 60s"

    monkeypatch.setattr(download_week, "run_cmd", fake_run_cmd)

    ok, reason = download_week.wait_and_download(
        tmp_path / "notebooklm",
        "artifact-id",
        "notebook-id",
        "audio",
        tmp_path / "episode.mp3",
        60,
        60,
        str(tmp_path / "owner-profile.json"),
        None,
    )

    assert ok is False
    assert reason == "wait"


def test_wait_and_download_retries_completed_artifact_media_html(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    sleeps: list[int] = []

    def fake_run_cmd(command: list[str]) -> tuple[bool, str]:
        calls.append(command)
        if "artifact" in command and "wait" in command:
            return True, "completed"
        if len([call for call in calls if "download" in call]) == 1:
            return (
                False,
                "Download failed: received HTML instead of media file. "
                "Authentication may have expired.",
            )
        return True, "downloaded"

    monkeypatch.setattr(download_week, "run_cmd", fake_run_cmd)
    monkeypatch.setattr(download_week.time, "sleep", lambda seconds: sleeps.append(seconds))

    ok, reason = download_week.wait_and_download(
        tmp_path / "notebooklm",
        "artifact-id",
        "notebook-id",
        "audio",
        tmp_path / "episode.mp3",
        60,
        5,
        str(tmp_path / "owner-profile.json"),
        None,
    )

    assert ok is True
    assert reason == "ok"
    assert sleeps == [5]
    assert len([call for call in calls if "download" in call]) == 2
